#!/usr/bin/env python3
"""SessionStart hook: give this session a human name, without touching its title.

Why a hook and not a shell wrapper: a wrapper only reaches sessions you launch
from a shell you control. Hooks fire wherever Claude Code runs -- terminal, IDE
extensions, the desktop app, the web -- and they ship inside the plugin, so
installing it never edits your shell rc.

Why not `sessionTitle`: that is the one hook output that renames a session, and
it sets the conversation *title* too, so your tab stops saying what you are
working on. This writes the name straight into the session's peer file instead,
which is the same record `ListAgents` reads and `SendMessage` resolves.

The name is also returned as `additionalContext`, so the session knows what to
call itself when it answers a peer -- the part a peer-file write alone cannot do.
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

# Claude Code writes the peer file at startup; the hook can win the race.
WAIT_TOTAL = 3.0
WAIT_STEP = 0.1

# Names Claude Code assigned itself. Anything else -- including a name you set
# with /rename, which reports "user" -- is left alone.
MACHINE = ("derived", "auto", "collision")

HERE = Path(__file__).resolve().parent
PICK = HERE.parent / "scripts" / "pick_name.py"
CFG = Path(os.environ.get("CLAUDE_CONFIG_DIR", str(Path.home() / ".claude")))


def peer_file(session_id):
    """The peer record for this session, waiting briefly for it to appear."""
    sessions = CFG / "sessions"
    deadline = time.time() + WAIT_TOTAL
    while True:
        if sessions.is_dir():
            for path in sessions.glob("*.json"):
                try:
                    with path.open(encoding="utf-8") as fh:
                        rec = json.load(fh)
                except (OSError, ValueError):
                    continue
                if isinstance(rec, dict) and rec.get("sessionId") == session_id:
                    return path, rec
        if time.time() >= deadline:
            return None, None
        time.sleep(WAIT_STEP)


def pick():
    try:
        out = subprocess.run([sys.executable, str(PICK)],
                             capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return ""
    return out.stdout.strip()


def write_name(path, name):
    """Replace the name in place, atomically -- never a half-written peer file."""
    try:
        with path.open(encoding="utf-8") as fh:
            fresh = json.load(fh)
        if fresh.get("nameSource") not in MACHINE:
            return False          # someone named it while we were choosing
        fresh["name"] = name
        fresh.pop("nameSource", None)
        tmp = path.with_suffix(".json.agent-names-tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            json.dump(fresh, fh)
        os.replace(tmp, path)
    except (OSError, ValueError):
        return False
    return True


def context(name):
    return (
        f"Your name in this session is {name}. Other Claude Code sessions on this "
        f"machine see you as \"{name}\" in ListAgents and reach you with "
        f"SendMessage {{to: \"{name}\"}}. Open a reply to a peer with your own name "
        f"so the conversation is readable. This is an address, not an identity: it "
        f"does not change how you work or who you are."
    )


def emit(name):
    json.dump({"hookSpecificOutput": {
        "hookEventName": "SessionStart",
        "additionalContext": context(name),
    }}, sys.stdout)


def main():
    try:
        payload = json.load(sys.stdin)
    except (ValueError, OSError):
        return
    session_id = payload.get("session_id") or ""
    if not session_id:
        return

    path, rec = peer_file(session_id)
    if not rec:
        return
    # Background agents carry a task label ("Merge to main"), which says more
    # than a first name would. Headless runs have no peer file at all.
    if rec.get("kind") != "interactive":
        return

    if rec.get("nameSource") not in MACHINE:
        # Already named -- by /rename, or by the launcher on an earlier start.
        # Still tell the session what it is called, so it can sign its replies.
        existing = rec.get("name") or ""
        if existing:
            emit(existing)
        return

    name = pick()
    if name and write_name(path, name):
        emit(name)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass   # a naming hook must never break a session that is starting
