#!/usr/bin/env python3
"""Give a session a name from outside the plugin, and keep it.

    agent-name set SESSION_ID NAME   name the session, and remember the name as assigned
    agent-name get SESSION_ID        the name it has now, or the one it will get back
    agent-name forget SESSION_ID     drop what this session was called

The boss names a worker this way, and agentview names a conversation it is
about to resume. The name need not be on the roster. An assigned name is
remembered in `sessions.json` with `assigned: true`, which is what keeps it:
the hook leaves a session alone while it carries its assigned name, and hands
the name back when the session resumes.

A name you set yourself with /rename (`nameSource: "user"`) is never
overwritten; `set` prints the name in effect either way.

This is the only way in for other tools. The files under
`$CLAUDE_CONFIG_DIR/agent-names/` are this plugin's own.
"""
import fcntl
import json
import os
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import registry  # noqa: E402


def state_dir(cfg=None):
    return registry.config_dir(cfg) / "agent-names"


def _load(path):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _save(path, data):
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name, suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=1, sort_keys=True)
    os.replace(tmp, path)


def _locked(cfg, change):
    """Run change(sessions) under the picker's lock and save what it returns."""
    state = state_dir(cfg)
    state.mkdir(parents=True, exist_ok=True)
    with open(state / "pick.lock", "a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        path = state / "sessions.json"
        sessions = _load(path)
        if change(sessions) is not False:
            _save(path, sessions)


def assigned(session_id, cfg=None):
    """The name assigned to this session, or None."""
    entry = _load(state_dir(cfg) / "sessions.json").get(session_id)
    if isinstance(entry, dict) and entry.get("assigned"):
        return entry.get("name") or None
    return None


def _write_peer(path, name):
    """Put the name in the peer file unless a person named the session."""
    fresh = json.loads(path.read_text(encoding="utf-8"))
    if fresh.get("nameSource") == "user":
        return fresh.get("name") or ""
    fresh["name"] = name
    fresh.pop("nameSource", None)
    tmp = path.with_suffix(".json.agent-names-tmp")
    tmp.write_text(json.dumps(fresh), encoding="utf-8")
    os.replace(tmp, path)
    return name


def set_name(session_id, name, cfg=None, proc="/proc"):
    """Name the session and remember it as assigned. Returns the name in effect."""
    rec = registry.by_sid(session_id, cfg, proc)
    if rec and registry.is_live(rec, proc) and rec.get("nameSource") == "user":
        return rec.get("name") or ""

    def remember(sessions):
        sessions[session_id] = {"name": name, "last_used": int(time.time()), "assigned": True}
    _locked(cfg, remember)

    if rec and registry.is_live(rec, proc):
        try:
            return _write_peer(Path(rec["path"]), name)
        except (OSError, ValueError):
            pass
    return name


def get_name(session_id, cfg=None, proc="/proc"):
    rec = registry.by_sid(session_id, cfg, proc)
    if rec and registry.is_live(rec, proc) and rec.get("name"):
        return rec["name"]
    entry = _load(state_dir(cfg) / "sessions.json").get(session_id)
    return (entry or {}).get("name") or "" if isinstance(entry, dict) else ""


def forget(session_id, cfg=None):
    def drop(sessions):
        if session_id not in sessions:
            return False
        del sessions[session_id]
    _locked(cfg, drop)


def main(argv):
    cmd, args = (argv[0] if argv else ""), argv[1:]
    if cmd == "set" and len(args) == 2 and args[1].strip():
        print(set_name(args[0], args[1].strip()))
        return 0
    if cmd == "get" and len(args) == 1:
        name = get_name(args[0])
        if not name:
            return 1
        print(name)
        return 0
    if cmd == "forget" and len(args) == 1:
        forget(args[0])
        return 0
    print(__doc__.strip().split("\n\n")[1], file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
