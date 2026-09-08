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


# --- a session keeps one name for its whole life -----------------------------
#
# Claude Code rewrites the peer record on its own schedule, and a rewrite puts a
# derived name back -- which makes the record replaceable again. The picker then
# starts from scratch. When the project's usual name is free that is harmless:
# it picks the same one. When a second session in the same project already holds
# it, there is nothing left to anchor the choice and the picker rolls the dice
# again, so a session peers already know by name answers to a different one.
#
# Measured on 2206 real transcripts: 10 sessions were told two or more names.
# One piano-music-database session ran through four (Lina, Imani, Ignacio, Nour)
# while a sibling session held the project's name.

class Life:
    """One config dir, many hook firings -- a session's life, not a snapshot."""

    def __init__(self, cwd="/tmp/project"):
        self.tmp = tempfile.TemporaryDirectory()
        self.cfg = Path(self.tmp.name)
        (self.cfg / "sessions").mkdir()
        self.cwd = cwd

    def peer_write(self, pid, sid, name, source="derived", kind="interactive"):
        rec = {"pid": pid, "sessionId": sid, "cwd": self.cwd,
               "kind": kind, "name": name}
        if source:
            rec["nameSource"] = source
        (self.cfg / "sessions" / f"{pid}.json").write_text(json.dumps(rec))

    def peer_drop(self, pid):
        (self.cfg / "sessions" / f"{pid}.json").unlink()

    def peer_name(self, pid):
        return json.loads((self.cfg / "sessions" / f"{pid}.json").read_text()).get("name")

    def fire(self, sid, event="UserPromptSubmit"):
        env = dict(os.environ, CLAUDE_CONFIG_DIR=str(self.cfg))
        payload = json.dumps({"session_id": sid, "hook_event_name": event,
                              "cwd": self.cwd})
        subprocess.run([sys.executable, str(HOOK)], input=payload,
                       capture_output=True, text=True, timeout=30, env=env)

    def close(self):
        self.tmp.cleanup()


def second_session_in_project():
    """Two sessions, one project. Returns the life and the second session's name.

    The first takes the project's remembered name, so the second cannot -- which
    is the state the picker has no answer for.
    """
    life = Life()
    life.peer_write(4242, "s-first", "some-derived-label")
    life.fire("s-first", "SessionStart")
    life.peer_write(5000, "s-second", "another-derived-label")
    life.fire("s-second", "SessionStart")
    return life, life.peer_name(5000)


life, mine = second_session_in_project()
life.peer_write(5000, "s-second", "another-derived-label")   # Claude Code relabels
life.fire("s-second", "UserPromptSubmit")
check("a relabelled session gets its own name back, not a fresh one",
      life.peer_name(5000) == mine,
      f"was {mine!r}, became {life.peer_name(5000)!r}")
life.close()

life, mine = second_session_in_project()
for _ in range(3):                                            # relabelled repeatedly
    life.peer_write(5000, "s-second", "another-derived-label")
    life.fire("s-second", "UserPromptSubmit")
check("and does not drift further on every later prompt",
      life.peer_name(5000) == mine,
      f"was {mine!r}, became {life.peer_name(5000)!r}")
life.close()

life, mine = second_session_in_project()
life.peer_drop(5000)                                          # the session exits
life.peer_write(5001, "s-second", "another-derived-label")    # ... and is resumed
life.fire("s-second", "SessionStart")
check("a resumed session answers to the name it had before",
      life.peer_name(5001) == mine,
      f"was {mine!r}, became {life.peer_name(5001)!r}")
life.close()

# The preference must never become a reservation: a name a live session actually
# holds is still off limits, whoever used it yesterday.
life, mine = second_session_in_project()
life.peer_drop(5000)
life.peer_write(6000, "s-third", mine, source=None)           # taken meanwhile
life.peer_write(5001, "s-second", "another-derived-label")
life.fire("s-second", "SessionStart")
resumed = life.peer_name(5001)
check("but never takes a name a live session already holds",
      resumed != mine and resumed in ROSTER, f"became {resumed!r}")
life.close()

# --- the statusline adopts too, and must not re-pick either ------------------
#
# It renders on every turn. Running with neither the session's id nor its
# directory, each render of a machine-named record was an independent draw.

STATUSLINE = ROOT / "scripts" / "statusline.py"


def render(life, sid):
    env = dict(os.environ, CLAUDE_CONFIG_DIR=str(life.cfg))
    env.pop("CLAUDE_CODE_SESSION_NAME", None)      # else it short-circuits
    subprocess.run([sys.executable, str(STATUSLINE)],
                   input=json.dumps({"session_id": sid, "cwd": life.cwd}),
                   capture_output=True, text=True, timeout=30, env=env)


life, mine = second_session_in_project()
life.peer_write(5000, "s-second", "another-derived-label")
render(life, "s-second")
after_first = life.peer_name(5000)
life.peer_write(5000, "s-second", "another-derived-label")
render(life, "s-second")
check("the statusline re-adopts a session under the same name",
      after_first == mine and life.peer_name(5000) == mine,
      f"was {mine!r}, became {after_first!r} then {life.peer_name(5000)!r}")
life.close()


print()
if failures:
    print(f"{len(failures)} failing: " + ", ".join(failures))
    raise SystemExit(1)
print("all passing")
