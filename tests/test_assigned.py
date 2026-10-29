#!/usr/bin/env python3
"""Names assigned from outside -- by the boss, by a restore -- and kept.

Run: python3 tests/test_assigned.py

`bin/agent-name set` is how another tool gives a session a name. The name need
not be on the roster, and it has to survive what the hook does next: the next
prompt, and a resume.
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HOOK = ROOT / "hooks" / "session_start_name.py"
AGENT_NAME = ROOT / "bin" / "agent-name"

failures = []


def check(label, condition, detail=""):
    print(f"{'ok  ' if condition else 'FAIL'} {label}{'' if condition else '  -- ' + detail}")
    if not condition:
        failures.append(label)


class Life:
    """A config dir whose sessions are real `sleep` processes, as in test_naming."""

    def __init__(self, cwd="/tmp/project"):
        self.tmp = tempfile.TemporaryDirectory()
        self.cfg = Path(self.tmp.name)
        (self.cfg / "sessions").mkdir()
        self.cwd = cwd
        self.real = {}
        self.env = dict(os.environ, CLAUDE_CONFIG_DIR=str(self.cfg))

    def start(self, key, sid, name="derived-label", source="derived"):
        """A session starts (or resumes) under `sid`; `key` names it in the test."""
        self.real[key] = subprocess.Popen(["sleep", "300"], stdout=subprocess.DEVNULL,
                                          stderr=subprocess.DEVNULL)
        pid = self.real[key].pid
        stat = Path(f"/proc/{pid}/stat").read_text()
        rec = {"pid": pid, "sessionId": sid, "cwd": self.cwd, "kind": "interactive",
               "name": name, "procStart": stat[stat.rindex(")") + 2:].split()[19]}
        if source:
            rec["nameSource"] = source
        self.path(key).write_text(json.dumps(rec))

    def stop(self, key):
        self.path(key).unlink()
        proc = self.real.pop(key)
        proc.kill()
        proc.wait()

    def path(self, key):
        return self.cfg / "sessions" / f"{self.real[key].pid}.json"

    def name(self, key):
        return json.loads(self.path(key).read_text()).get("name")

    def fire(self, sid, event):
        """Run the hook for this session; returns what it printed."""
        return subprocess.run([sys.executable, str(HOOK)], env=self.env, capture_output=True,
                       text=True, timeout=30,
                       input=json.dumps({"session_id": sid, "hook_event_name": event,
                                         "cwd": self.cwd})).stdout

    def agent_name(self, *args):
        return subprocess.run([str(AGENT_NAME), *args], env=self.env, capture_output=True,
                              text=True, timeout=30)

    def close(self):
        for proc in self.real.values():
            proc.kill()
            proc.wait()
        self.tmp.cleanup()


# --- an assigned name survives the next prompt --------------------------------

life = Life()
life.start("w", "s-w")
life.fire("s-w", "SessionStart")
out = life.agent_name("set", "s-w", "reviewer-1")
life.fire("s-w", "UserPromptSubmit")
check("a name assigned with agent-name set survives the next prompt",
      out.returncode == 0 and life.name("w") == "reviewer-1",
      f"exit {out.returncode} {out.stderr.strip()!r}, name {life.name('w')!r}")
life.close()

# --- and a resume -------------------------------------------------------------
#
# The hook names a resumed session from what it remembers for that session id.
# It used to remember only its own pick, so the boss's name was lost.

for assigned in ("reviewer-1", "Marek"):                      # off the roster, and on it
    life = Life()
    life.start("w", "s-w")
    life.fire("s-w", "SessionStart")
    first = life.name("w")
    life.agent_name("set", "s-w", assigned)
    life.stop("w")                                            # the session exits
    life.start("w2", "s-w")                                   # ... and is resumed
    life.fire("s-w", "SessionStart")
    check(f"an assigned name ({assigned}) comes back on resume, not the first pick",
          life.name("w2") == assigned, f"first {first!r}, resumed as {life.name('w2')!r}")
    life.close()

# --- a restart under a new session id keeps the pane's name (#5) -------------
#
# The boss restarts a worker in its worktree: a new process, a new session id.
# Naming it after SessionStart is too late, the session has been told another
# name. So the boss chooses the id, sets the name, then starts the session.

for assigned in ("reviewer-1", "Marek"):                      # off the roster, and on it
    life = Life()
    life.start("w", "s-1")
    life.fire("s-1", "SessionStart")
    first = life.name("w")
    life.agent_name("set", "s-1", assigned)
    life.stop("w")                                            # the worker is restarted
    life.agent_name("set", "s-2", assigned)                   # under an id chosen first
    life.start("w2", "s-2")
    told = life.fire("s-2", "SessionStart")
    check(f"a restarted worker starts as {assigned} and is told so, not {first}",
          life.name("w2") == assigned and f"is {assigned}." in told,
          f"named {life.name('w2')!r}, told {told[:120]!r}")
    check("and is not told again on its first prompt",
          life.fire("s-2", "UserPromptSubmit") == "")
    life.start("w3", "s-3")                                   # a session of its own beside it
    life.fire("s-3", "SessionStart")
    check(f"a session nobody named, alongside it, is not {assigned} too",
          life.name("w3") not in (assigned, "derived-label"), repr(life.name("w3")))
    check("and is not told its name on every prompt",
          life.fire("s-3", "UserPromptSubmit") == "" and life.fire("s-3", "UserPromptSubmit") == "")
    life.close()

# --- a session is told when its name is changed from outside (#5) -------------

life = Life()
life.start("w", "s-w")
life.fire("s-w", "SessionStart")
life.agent_name("set", "s-w", "reviewer-1")
told = life.fire("s-w", "UserPromptSubmit")
check("the next prompt tells the session its new name",
      "is reviewer-1." in told, repr(told[:200]))
check("and only once", life.fire("s-w", "UserPromptSubmit") == "")
# The statusline re-picks on its own schedule; that rewrites the entry.
subprocess.run([sys.executable, str(ROOT / "scripts" / "pick_name.py")], capture_output=True,
               env=dict(life.env, CAN_CWD=life.cwd, CAN_SESSION="s-w"), timeout=30)
check("and not again after a re-pick", life.fire("s-w", "UserPromptSubmit") == "")
life.close()

# --- a name you chose yourself wins -------------------------------------------

life = Life()
life.start("w", "s-w", name="my-own", source="user")          # /rename
out = life.agent_name("set", "s-w", "reviewer-1")
check("set never overwrites a name set with /rename, and says which name is in effect",
      life.name("w") == "my-own" and out.stdout.strip() == "my-own",
      f"name {life.name('w')!r}, printed {out.stdout.strip()!r}")
life.close()

# --- naming a conversation before it resumes (agentview's restore) ------------

life = Life()
life.agent_name("set", "s-back", "Oskar-restored")            # nothing running yet
life.start("w", "s-back")
life.fire("s-back", "SessionStart")
check("a name set before the session starts is the name it starts with",
      life.name("w") == "Oskar-restored", repr(life.name("w")))
out = life.agent_name("get", "s-back")
check("get prints the session's name", out.stdout.strip() == "Oskar-restored", repr(out.stdout))
life.stop("w")
life.agent_name("forget", "s-back")
out = life.agent_name("get", "s-back")
check("forget drops it: get has nothing and exits 1",
      out.returncode == 1 and out.stdout == "", repr((out.returncode, out.stdout)))
life.start("w2", "s-back")
life.fire("s-back", "SessionStart")
check("and a later resume picks from the roster again",
      life.name("w2") not in ("Oskar-restored", "derived-label"), repr(life.name("w2")))
life.close()


print()
if failures:
    print(f"{len(failures)} failing: " + ", ".join(failures))
    raise SystemExit(1)
print("all passing")
