#!/usr/bin/env python3
"""The session registry, read against a throwaway config dir and a fake /proc.

Run: python3 tests/test_registry.py

Every case builds its own CLAUDE_CONFIG_DIR with peer files in `sessions/`,
and its own /proc tree with a `stat` per pid, so liveness is decided by the
files the test wrote and never by what happens to be running on the machine.
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import registry  # noqa: E402

failures = []

PTS = (136 << 8) | 4          # /dev/pts/4, as the kernel numbers it


def check(label, condition, detail=""):
    print(f"{'ok  ' if condition else 'FAIL'} {label}{'' if condition else '  -- ' + detail}")
    if not condition:
        failures.append(label)


class World:
    """A config dir and a /proc, both empty until a test fills them."""

    def __init__(self):
        self._tmp = tempfile.TemporaryDirectory()
        base = Path(self._tmp.name)
        self.cfg = base / "claude"
        self.proc = base / "proc"
        (self.cfg / "sessions").mkdir(parents=True)
        self.proc.mkdir()

    def process(self, pid, start=1000, state="S", tty=PTS, ppid=1):
        d = self.proc / str(pid)
        d.mkdir()
        # Fields after the command: state ppid pgrp session tty_nr ... and
        # starttime is the 20th of them (field 22 of the whole line). The
        # command carries a space and a parenthesis on purpose.
        rest = [state, str(ppid), "0", "0", str(tty)] + ["0"] * 14 + [str(start)] + ["0"] * 30
        (d / "stat").write_text(f"{pid} (claude (x) y) " + " ".join(rest) + "\n")

    def peer(self, pid, sid, start=1000, **over):
        rec = {"pid": pid, "sessionId": sid, "cwd": "/tmp/project",
               "procStart": str(start), "kind": "interactive", "entrypoint": "cli",
               "name": "Petra"}
        rec.update(over)
        (self.cfg / "sessions" / f"{pid}.json").write_text(json.dumps(rec))
        return rec

    def live_ids(self):
        return sorted(r["sessionId"] for r in registry.live(cfg=self.cfg, proc=self.proc))

    def close(self):
        self._tmp.cleanup()


# --- liveness -----------------------------------------------------------------

w = World()
w.process(100, start=5000)
w.peer(100, "s-live", start=5000)
w.process(200, start=7777)
w.peer(200, "s-reused", start=5000)            # pid 200 now belongs to someone else
w.peer(300, "s-gone")                          # no process at all
check("live() keeps a session whose pid and start time match, and drops a reused or gone pid",
      w.live_ids() == ["s-live"], repr(w.live_ids()))
w.close()

w = World()
w.process(100, tty=0)
w.peer(100, "s-orphan")                                   # window closed on it
w.process(200, tty=0)
w.peer(200, "s-routine", entrypoint="sdk-cli")            # never had a terminal
check("a terminal session that lost its terminal is not live; a headless one is",
      w.live_ids() == ["s-routine"], repr(w.live_ids()))
w.close()

w = World()
w.process(100, state="Z")
w.peer(100, "s-zombie")
w.process(200, state="T")
w.peer(200, "s-suspended")                                # Ctrl-Z in an open window
w.process(300)
w.peer(300, "s-no-start", procStart=None)
check("a zombie is not live, a suspended session is, and a record without procStart is not",
      w.live_ids() == ["s-suspended"], repr(w.live_ids()))
w.close()

# --- lookups ------------------------------------------------------------------

w = World()
w.peer(100, "s-resumed", name="Old")                     # the window before the resume
w.process(200)
w.peer(200, "s-resumed", name="New")                     # the resume, live
w.peer(300, "s-stale", name="Ghost")
hit = registry.by_sid("s-resumed", cfg=w.cfg, proc=w.proc)
check("by_sid prefers the live record when a stale file shares the session id",
      hit and hit["name"] == "New" and hit["path"].endswith("200.json"), repr(hit))
hit = registry.by_sid("s-stale", cfg=w.cfg, proc=w.proc)
check("by_sid still finds a record that is not live",
      hit and hit["name"] == "Ghost", repr(hit))
check("by_sid answers None for an unknown session",
      registry.by_sid("s-nobody", cfg=w.cfg, proc=w.proc) is None)
hit = registry.by_pid(300, cfg=w.cfg)
check("by_pid reads the peer file named after the pid",
      hit and hit["sessionId"] == "s-stale", repr(hit))
check("by_pid answers None when there is no such file",
      registry.by_pid(999, cfg=w.cfg) is None)
w.close()

w = World()
w.process(100)
w.peer(100, "s-mine")
w.process(400, ppid=100)                                  # the shell Claude started
w.process(500, ppid=400)                                  # this script
hit = registry.own(pid=500, cfg=w.cfg, proc=w.proc)
check("own() walks up the parents to the session this runs under",
      hit and hit["sessionId"] == "s-mine", repr(hit))
w.process(600, ppid=1)
check("own() answers None outside any session",
      registry.own(pid=600, cfg=w.cfg, proc=w.proc, env={}) is None)
hit = registry.own(pid=600, cfg=w.cfg, proc=w.proc, env={"CLAUDE_CODE_SESSION_ID": "s-mine"})
check("own() falls back to CLAUDE_CODE_SESSION_ID when the parents do not say",
      hit and hit["sessionId"] == "s-mine", repr(hit))
w.close()

# --- transcripts --------------------------------------------------------------

w = World()
here = w.cfg / "projects" / "-home-u--claude-my-skills"          # dots become dashes too
here.mkdir(parents=True)
(here / "s-here.jsonl").write_text("{}\n")
moved = w.cfg / "projects" / "-home-u-elsewhere"
moved.mkdir(parents=True)
(moved / "s-moved.jsonl").write_text("{}\n")
got = registry.transcript_of({"sessionId": "s-here", "cwd": "/home/u/.claude/my-skills"}, cfg=w.cfg)
check("transcript_of finds the transcript under the encoded cwd",
      got == here / "s-here.jsonl", repr(got))
got = registry.transcript_of({"sessionId": "s-moved", "cwd": "/home/u/now-here"}, cfg=w.cfg)
check("transcript_of finds a session whose cwd changed since it started",
      got == moved / "s-moved.jsonl", repr(got))
check("transcript_of answers None when there is none",
      registry.transcript_of({"sessionId": "s-none", "cwd": "/x"}, cfg=w.cfg) is None)
w.close()

# --- the CLI, against the real /proc ------------------------------------------

w = World()
child = subprocess.Popen(["sleep", "30"])
try:
    stat = Path(f"/proc/{child.pid}/stat").read_text()
    start = stat[stat.rindex(")") + 2:].split()[19]
    w.peer(child.pid, "s-child", start=start, entrypoint="sdk-cli")
    w.peer(child.pid + 100000, "s-dead")
    env = dict(os.environ, CLAUDE_CONFIG_DIR=str(w.cfg))
    cli = [sys.executable, str(ROOT / "scripts" / "registry.py")]
    out = subprocess.run(cli + ["live"], capture_output=True, text=True, env=env)
    ids = [json.loads(ln)["sessionId"] for ln in out.stdout.splitlines()]
    check("registry.py live prints one JSON record per live session",
          out.returncode == 0 and ids == ["s-child"], repr((out.returncode, ids, out.stderr)))
    out = subprocess.run(cli + ["by-sid", "s-dead"], capture_output=True, text=True, env=env)
    check("registry.py by-sid prints the record",
          out.returncode == 0 and json.loads(out.stdout)["sessionId"] == "s-dead", repr(out))
    out = subprocess.run(cli + ["by-pid", str(child.pid)], capture_output=True, text=True, env=env)
    check("registry.py by-pid prints the record",
          out.returncode == 0 and json.loads(out.stdout)["sessionId"] == "s-child", repr(out))
    out = subprocess.run(cli + ["by-sid", "s-nobody"], capture_output=True, text=True, env=env)
    check("registry.py exits 1 with nothing on stdout when there is no such session",
          out.returncode == 1 and out.stdout == "", repr(out))
finally:
    child.kill()
    child.wait()
w.close()


print()
if failures:
    print(f"{len(failures)} failing: " + ", ".join(failures))
    raise SystemExit(1)
print("all passing")
