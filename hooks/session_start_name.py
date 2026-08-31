#!/usr/bin/env python3
"""Give this session a human name, without touching its title.

Runs on two events. SessionStart covers interactive sessions, which are named
once and keep it. UserPromptSubmit covers background jobs, which cannot be
named once: Claude Code relabels a `bg` session about two minutes in, with a
phrase derived from its opening prompt, and that write lands long after
SessionStart has finished. So for jobs the name is re-asserted on each prompt --
idempotent, and it heals the label the moment it appears.

Why a hook and not a shell wrapper: a wrapper only reaches sessions you launch
from a shell you control, and never reaches a background job at all. Hooks fire wherever Claude Code runs -- terminal, IDE
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

# Interactive sessions and background jobs. Both are long-lived, both are
# addressed by name in ListAgents, and a job's auto label is worse than a name:
# it is derived from the opening prompt and never revised, so a job that starts
# on one subject and spends its life on another answers to the wrong thing.
# Genuine task subagents are still skipped -- their label IS the task.
NAMED_KINDS = ("interactive", "bg")

HERE = Path(__file__).resolve().parent
PICK = HERE.parent / "scripts" / "pick_name.py"
CFG = Path(os.environ.get("CLAUDE_CONFIG_DIR", str(Path.home() / ".claude")))


def roster():
    """The names this plugin hands out.

    A job's name has no nameSource to check -- Claude Code writes the label
    without one -- so membership of the roster is what distinguishes a name we
    gave from a label we should replace.
    """
    cfg_names = CFG / "agent-names" / "names.txt"
    path = cfg_names if cfg_names.is_file() else (HERE.parent / "data" / "names.txt")
    try:
        with path.open(encoding="utf-8") as fh:
            return {ln.strip() for ln in fh if ln.strip() and not ln.startswith("#")}
    except OSError:
        return set()


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


def pick(cwd):
    # The session's own directory decides which project's name it inherits.
    env = dict(os.environ, CAN_CWD=cwd or os.getcwd())
    try:
        out = subprocess.run([sys.executable, str(PICK)], env=env,
                             capture_output=True, text=True, timeout=8)
    except (OSError, subprocess.SubprocessError):
        return ""
    return out.stdout.strip()


def release(name):
    try:
        subprocess.run([sys.executable, str(PICK), "--release", name],
                       capture_output=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        pass


def replaceable(rec, pool):
    """True when this session's current name is Claude Code's, not a person's.

    Two shapes of machine name exist. An interactive session carries
    nameSource "derived"; a background job carries a label with no nameSource
    at all, so the only way to recognise it is that it is not a name from our
    roster. A name set with /rename reports "user" and is never touched.
    """
    source = rec.get("nameSource")
    if source == "user":
        return False
    if source in MACHINE:
        return True
    return (rec.get("name") or "") not in pool


def write_name(path, name, pool):
    """Replace the name in place, atomically -- never a half-written peer file."""
    try:
        with path.open(encoding="utf-8") as fh:
            fresh = json.load(fh)
        if not replaceable(fresh, pool):
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


def emit(name, event="SessionStart"):
    json.dump({"hookSpecificOutput": {
        "hookEventName": event,
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
    event = payload.get("hook_event_name") or "SessionStart"

    path, rec = peer_file(session_id)
    if not rec:
        return
    # Task subagents keep their label, which says more about them than a first
    # name would.
    #
    # Headless `claude -p` runs are NOT excluded here, and cannot be: measured
    # on 2.1.252, a headless run writes a peer file like any other and reports
    # `kind: "interactive"`, so nothing in the record tells it apart. It takes a
    # name for as long as it runs and gives it back on exit. Harmless against
    # the bundled 217, but worth knowing if you cut the roster down to a few.
    if rec.get("kind") not in NAMED_KINDS:
        return

    pool = roster()
    if not replaceable(rec, pool):
        # Already named -- by /rename, by us on an earlier start, or by us on an
        # earlier prompt. Tell the session what it is called only at the start of
        # a session; repeating it on every prompt would be noise.
        existing = rec.get("name") or ""
        if existing and event == "SessionStart":
            emit(existing)
        return

    name = pick(rec.get("cwd") or payload.get("cwd") or "")
    if not name:
        return
    if write_name(path, name, pool):
        # The peer file now says the name is taken, so the reservation that
        # covered the gap has nothing left to cover. Dropping it here is what
        # keeps a short-lived session from locking its project out of its own
        # name on the next launch.
        release(name)
        emit(name, event)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass   # a naming hook must never break a session that is starting
