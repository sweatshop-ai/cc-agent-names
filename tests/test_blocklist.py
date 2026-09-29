#!/usr/bin/env python3
"""Names you never want handed out -- a colleague's first name, say.

Run: python3 tests/test_blocklist.py

`~/.claude/agent-names/blocklist.txt` is subtracted from whichever pool is
active, bundled or your own. It governs every route a name takes: the random
pick, the overflow suffix, a remembered project name, a session's own name on
resume, and `agent-name set`. It never renames a session that is already
running.
"""
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PICK = ROOT / "scripts" / "pick_name.py"
HOOK = ROOT / "hooks" / "session_start_name.py"
AGENT_NAME = ROOT / "bin" / "agent-name"
BUNDLED = [ln.strip() for ln in (ROOT / "data" / "names.txt").read_text().splitlines()
           if ln.strip() and not ln.startswith("#")]

failures = []


def check(label, condition, detail=""):
    print(f"{'ok  ' if condition else 'FAIL'} {label}{'' if condition else '  -- ' + detail}")
    if not condition:
        failures.append(label)


class Cfg:
    """A private config dir, optionally with its own roster and blocklist."""

    def __init__(self, roster=None, blocked=None):
        self.tmp = tempfile.TemporaryDirectory()
        self.cfg = Path(self.tmp.name)
        self.state = self.cfg / "agent-names"
        self.state.mkdir()
        (self.cfg / "sessions").mkdir()
        if roster is not None:
            (self.state / "names.txt").write_text("\n".join(roster) + "\n")
        if blocked is not None:
            (self.state / "blocklist.txt").write_text("\n".join(blocked) + "\n")
        self.env = dict(os.environ, CLAUDE_CONFIG_DIR=str(self.cfg))
        self.env.pop("CAN_NAMES", None)
        self.cwd = os.path.realpath(self.tmp.name)

    def pick(self, sid="s-1"):
        env = dict(self.env, CAN_CWD=self.cwd, CAN_SESSION=sid)
        return subprocess.run([sys.executable, str(PICK)], env=env, capture_output=True,
                              text=True, timeout=30).stdout.strip()

    def write(self, name, data):
        (self.state / name).write_text(json.dumps(data))

    def agent_name(self, *args):
        return subprocess.run([str(AGENT_NAME), *args], env=self.env, capture_output=True,
                              text=True, timeout=30)

    def close(self):
        self.tmp.cleanup()


# --- the pick never lands on a blocked name ----------------------------------

c = Cfg(roster=["Anna", "Bo", "Cy"], blocked=["Anna"])
picks = set()
for i in range(12):
    c.write("reservations.json", {})
    picks.add(c.pick(f"s-{i}"))
check("a blocked name is never picked", picks and "Anna" not in picks, repr(picks))
check("the other names still are", picks <= {"Bo", "Cy"} and picks, repr(picks))
c.close()

# --- it is subtracted from the bundled pool too ------------------------------

everyone_else = [n for n in BUNDLED if n != "Tomas"]
c = Cfg(blocked=everyone_else)
check("the blocklist applies to the bundled pool",
      c.pick() == "Tomas", "did not resolve to the one name left")
c.close()

# --- file syntax: case, comments, blank lines --------------------------------

c = Cfg(roster=["Anna", "Bo"], blocked=["# colleagues", "", "  anna  "])
check("matching is case-insensitive; # comments and blank lines are skipped",
      c.pick() == "Bo")
c.close()

c = Cfg(roster=["Anna", "Bo"])
check("no blocklist file is no blocking", c.pick() in ("Anna", "Bo"))
c.close()

# --- the overflow suffix ------------------------------------------------------
#
# More sessions than names appends -2 to a name from the pool. It must come from
# the filtered pool, or blocking Anna still produces Anna-2.

c = Cfg(roster=["Anna", "Bo"], blocked=["Anna"])
seen = set()
for i in range(10):
    c.write("reservations.json", {"Bo": {"at": time.time(), "sid": "someone-else"}})
    seen.add(c.pick(f"s-{i}"))
check("overflow never suffixes a blocked name", seen == {"Bo-2"}, repr(seen))
c.close()

# --- a name that is blocked after it was remembered --------------------------

c = Cfg(roster=["Anna", "Bo"], blocked=["Anna"])
c.write("projects.json", {c.cwd: {"name": "Anna", "last_used": int(time.time())}})
check("a project's remembered name that is now blocked is not resurrected",
      c.pick() == "Bo")
c.close()

for assigned in (False, True):
    c = Cfg(roster=["Anna", "Bo"], blocked=["Anna"])
    entry = {"name": "Anna", "last_used": int(time.time())}
    if assigned:
        entry["assigned"] = True
    c.write("sessions.json", {"s-old": entry})
    check(f"a resumed session's own name that is now blocked is not handed back "
          f"({'assigned' if assigned else 'picked'})", c.pick("s-old") == "Bo")
    c.close()

# --- agent-name set refuses a blocked name -----------------------------------

c = Cfg(roster=["Anna", "Bo"], blocked=["Anna"])
for name in ("Anna", "anna", "Anna-2"):
    out = c.agent_name("set", "s-x", name)
    check(f"agent-name set refuses {name!r}",
          out.returncode == 1 and out.stdout == "" and "blocklist" in out.stderr,
          repr((out.returncode, out.stdout, out.stderr)))
check("and remembers nothing for it", not (c.state / "sessions.json").exists())
out = c.agent_name("set", "s-x", "Bo")
check("an unblocked name is still accepted",
      out.returncode == 0 and out.stdout.strip() == "Bo", repr((out.returncode, out.stderr)))
c.close()

# --- a running session is never renamed --------------------------------------
#
# The hook treats "on the roster" as "a name we gave". A session already called
# Anna when Anna is blocked is still ours; it keeps the name until it ends.

c = Cfg(roster=["Anna", "Bo"], blocked=["Anna"])
peer = c.cfg / "sessions" / "4242.json"
peer.write_text(json.dumps({"pid": 4242, "sessionId": "s-live", "cwd": c.cwd,
                            "kind": "bg", "name": "Anna", "jobId": "j1"}))
subprocess.run([sys.executable, str(HOOK)], env=c.env, capture_output=True, text=True,
               timeout=30, input=json.dumps({"session_id": "s-live",
                                             "hook_event_name": "UserPromptSubmit",
                                             "cwd": c.cwd}))
check("a session already holding a name that is then blocked keeps it",
      json.loads(peer.read_text())["name"] == "Anna", peer.read_text())
c.close()


print()
if failures:
    print(f"{len(failures)} failing: " + ", ".join(failures))
    raise SystemExit(1)
print("all passing")
