#!/usr/bin/env python3
"""Hook behaviour, exercised against throwaway peer files.

Run: python3 tests/test_naming.py

No pytest, no fixtures library -- the plugin has no dependencies and neither do
its tests. Each case builds a private CLAUDE_CONFIG_DIR, drops one peer file in
it, feeds the hook a payload on stdin, and reads the file back.
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HOOK = ROOT / "hooks" / "session_start_name.py"
ROSTER = [ln.strip() for ln in (ROOT / "data" / "names.txt").read_text().splitlines()
          if ln.strip() and not ln.startswith("#")]

failures = []


def run_hook(record, event="SessionStart"):
    """Run the hook over one peer record. Returns (new_record, stdout)."""
    with tempfile.TemporaryDirectory() as tmp:
        cfg = Path(tmp)
        sessions = cfg / "sessions"
        sessions.mkdir()
        peer = sessions / "4242.json"
        peer.write_text(json.dumps(record))
        env = dict(os.environ, CLAUDE_CONFIG_DIR=str(cfg))
        payload = json.dumps({
            "session_id": record["sessionId"],
            "hook_event_name": event,
            "cwd": record.get("cwd", "/tmp/project"),
        })
        proc = subprocess.run([sys.executable, str(HOOK)], input=payload,
                              capture_output=True, text=True, timeout=30, env=env)
        return json.loads(peer.read_text()), proc.stdout


def peer(**over):
    rec = {"pid": 4242, "sessionId": "s-0001", "cwd": "/tmp/project",
           "kind": "interactive", "name": "some-derived-label",
           "nameSource": "derived"}
    rec.update(over)
    return rec


def check(label, condition, detail=""):
    print(f"{'ok  ' if condition else 'FAIL'} {label}{'' if condition else '  -- ' + detail}")
    if not condition:
        failures.append(label)


# --- background jobs: the case this plugin used to skip ----------------------

rec, out = run_hook(peer(kind="bg", name="claude process cleanup audit",
                         nameSource=None, jobId="7e46656f"), "UserPromptSubmit")
check("a job's auto label is replaced with a name", rec["name"] in ROSTER,
      f"name is {rec['name']!r}")
check("the job is told what it is called",
      "hookSpecificOutput" in out and rec["name"] in out, out[:120])

# A job carries no nameSource, so roster membership is the only signal that the
# name is already ours. Without it every prompt would pick a fresh name.
rec, out = run_hook(peer(kind="bg", name=ROSTER[0], nameSource=None,
                         jobId="7e46656f"), "UserPromptSubmit")
check("a job already holding a roster name keeps it", rec["name"] == ROSTER[0],
      f"name became {rec['name']!r}")
check("and is not re-announced on every prompt", out.strip() == "", out[:120])

# --- names a person chose ----------------------------------------------------

rec, _ = run_hook(peer(kind="bg", name="deploy-watcher", nameSource="user"),
                  "UserPromptSubmit")
check("/rename on a job is never overwritten", rec["name"] == "deploy-watcher",
      f"name became {rec['name']!r}")

rec, _ = run_hook(peer(name="my-session", nameSource="user"))
check("/rename on an interactive session is never overwritten",
      rec["name"] == "my-session", f"name became {rec['name']!r}")

# --- interactive sessions: unchanged behaviour -------------------------------

rec, out = run_hook(peer())
check("an interactive session is still named at SessionStart",
      rec["name"] in ROSTER, f"name is {rec['name']!r}")
check("nameSource is cleared so Claude Code stops re-deriving",
      "nameSource" not in rec, str(rec.get("nameSource")))

rec, out = run_hook(peer(name=ROSTER[1], nameSource=None))
check("an already-named session is re-told its name at SessionStart",
      rec["name"] == ROSTER[1] and ROSTER[1] in out, out[:120])

# --- everything else is left alone -------------------------------------------

rec, out = run_hook(peer(kind="subagent", name="Merge to main", nameSource=None),
                    "UserPromptSubmit")
check("a task subagent keeps its task label", rec["name"] == "Merge to main",
      f"name became {rec['name']!r}")
check("and produces no output", out.strip() == "", out[:120])

# --- a hook must never break the session it is naming ------------------------

proc = subprocess.run([sys.executable, str(HOOK)], input="not json",
                      capture_output=True, text=True, timeout=30)
check("garbage on stdin exits cleanly", proc.returncode == 0,
      f"exit {proc.returncode}: {proc.stderr[:120]}")

proc = subprocess.run([sys.executable, str(HOOK)], input=json.dumps(
    {"session_id": "nonexistent", "hook_event_name": "UserPromptSubmit"}),
    capture_output=True, text=True, timeout=30)
check("a session with no peer file exits cleanly", proc.returncode == 0,
      f"exit {proc.returncode}: {proc.stderr[:120]}")

print()
if failures:
    print(f"{len(failures)} failing: " + ", ".join(failures))
    raise SystemExit(1)
print("all passing")
