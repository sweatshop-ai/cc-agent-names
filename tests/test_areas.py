#!/usr/bin/env python3
"""Names per work area: `areas.json`, its rosters, and `CAN_NAME`.

Run: python3 tests/test_areas.py

A work area is a client folder or a repo family, matched by path glob so every
worktree of it counts as the same area. Each area has a small roster: the first
free name goes to the next session, a parallel session takes the next one, and
a spent roster grows by a free name that stays in it for good. The cases are
the ones the prototype settled (`14-names-per-client.html`): three worktrees of
clients/klium and four sessions, the growing roster, the same names back the
next day, and a resident named by `CAN_NAME`.
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
ROSTER = [ln.strip() for ln in (ROOT / "data" / "names.txt").read_text().splitlines()
          if ln.strip() and not ln.startswith("#")]

failures = []


def check(label, condition, detail=""):
    print(f"{'ok  ' if condition else 'FAIL'} {label}{'' if condition else '  -- ' + detail}")
    if not condition:
        failures.append(label)


class Laptop:
    """A config dir with an areas.json, and sessions backed by real processes.

    Only a live session holds a name, so each session is a `sleep` whose pid and
    start time go into its peer file, the way Claude Code writes them.
    """

    def __init__(self, areas=None):
        self.tmp = tempfile.TemporaryDirectory()
        self.cfg = Path(self.tmp.name)
        self.home = self.cfg / "home"
        (self.cfg / "sessions").mkdir()
        (self.cfg / "agent-names").mkdir()
        if areas is not None:
            self.areas_file.write_text(json.dumps({"areas": areas}, indent=1))
        self.real = {}
        self.cwd = {}
        self.n = 0

    @property
    def areas_file(self):
        return self.cfg / "agent-names" / "areas.json"

    def path(self, rel):
        return str(self.home / rel)

    def start(self, cwd, sid=None, env=None, kind="interactive", event="SessionStart"):
        """A session starts in `cwd` and the hook names it. Returns its session id."""
        self.n += 1
        sid = sid or f"s-{self.n}"
        self.real[sid] = subprocess.Popen(["sleep", "300"], stdout=subprocess.DEVNULL,
                                          stderr=subprocess.DEVNULL)
        self.cwd[sid] = cwd
        self.write(sid, "some-derived-label", "derived", kind)
        self.fire(sid, env, event)
        return sid

    def write(self, sid, name, source="derived", kind="interactive"):
        pid = self.real[sid].pid
        stat = Path(f"/proc/{pid}/stat").read_text()
        rec = {"pid": pid, "sessionId": sid, "cwd": self.cwd[sid], "kind": kind,
               "name": name, "procStart": stat[stat.rindex(")") + 2:].split()[19]}
        if source:
            rec["nameSource"] = source
        self._peer(sid).write_text(json.dumps(rec))

    def fire(self, sid, env=None, event="UserPromptSubmit"):
        """Run the hook for this session; returns what it printed."""
        return subprocess.run([sys.executable, str(HOOK)], env=self.env(env), capture_output=True,
                       text=True, timeout=30,
                       input=json.dumps({"session_id": sid, "hook_event_name": event,
                                         "cwd": self.cwd[sid]})).stdout

    def env(self, extra=None):
        env = dict(os.environ, CLAUDE_CONFIG_DIR=str(self.cfg), HOME=str(self.home))
        env.pop("CAN_NAME", None)
        env.pop("CAN_AREAS", None)
        env.update(extra or {})
        return env

    def stop(self, sid):
        self._peer(sid).unlink()
        proc = self.real.pop(sid)
        proc.kill()
        proc.wait()

    def stop_all(self):
        for sid in list(self.real):
            self.stop(sid)

    def name(self, sid):
        return json.loads(self._peer(sid).read_text()).get("name")

    def roster(self, area):
        return json.loads(self.areas_file.read_text())["areas"][area]["roster"]

    def _peer(self, sid):
        return self.cfg / "sessions" / f"{self.real[sid].pid}.json"

    def close(self):
        for proc in self.real.values():
            proc.kill()
            proc.wait()
        self.tmp.cleanup()


KLIUM = {"thinkingtoo/klium": {"paths": ["~/Projects/thinkingtoo*/clients/klium"],
                               "roster": ["Dmitri", "Leila", "Tomas"]}}
WORKTREES = ["Projects/thinkingtoo/clients/klium",
             "Projects/thinkingtoo-wt-chiara/clients/klium",
             "Projects/thinkingtoo-wt-bf/clients/klium/blog"]


# --- three worktrees, three sessions ----------------------------------------

lap = Laptop(KLIUM)
sids = [lap.start(lap.path(w)) for w in WORKTREES]
got = [lap.name(s) for s in sids]
check("three sessions in three worktrees of clients/klium are Dmitri, Leila, Tomas",
      got == ["Dmitri", "Leila", "Tomas"], f"got {got}")
print(f"     {', '.join(got)}")

# --- a fourth, while the three still run ------------------------------------

fourth = lap.start(lap.path(WORKTREES[0]))
newcomer = lap.name(fourth)
check("a fourth session gets a new name, not a suffix",
      newcomer in ROSTER and newcomer not in got, f"got {newcomer!r}")
check("and the new name joins the area's roster for good",
      lap.roster("thinkingtoo/klium") == ["Dmitri", "Leila", "Tomas", newcomer],
      f"roster is {lap.roster('thinkingtoo/klium')}")
print(f"     fourth: {newcomer}; roster now {', '.join(lap.roster('thinkingtoo/klium'))}")

# --- the next day -------------------------------------------------------------

lap.stop_all()
monday = [lap.start(lap.path(w)) for w in reversed(WORKTREES)]
monday.append(lap.start(lap.path(WORKTREES[1])))
got = [lap.name(s) for s in monday]
check("the next day the first session is Dmitri again, and the same four come back",
      got == ["Dmitri", "Leila", "Tomas", newcomer], f"got {got}")
print(f"     next day: {', '.join(got)}")
check("and the roster does not grow again",
      lap.roster("thinkingtoo/klium") == ["Dmitri", "Leila", "Tomas", newcomer],
      f"roster is {lap.roster('thinkingtoo/klium')}")
lap.close()

# --- the newcomer is nobody else's --------------------------------------------

taken_elsewhere = [n for n in ROSTER if n not in ("Dmitri", "Leila", "Tomas")][:-3]
lap = Laptop(dict(KLIUM, other={"paths": ["~/elsewhere"], "roster": taken_elsewhere}))
for w in WORKTREES:
    lap.start(lap.path(w))
fourth = lap.start(lap.path(WORKTREES[0]))
check("a newcomer is a name no other area holds",
      lap.name(fourth) in ROSTER[-3:] and lap.name(fourth) not in taken_elsewhere,
      f"got {lap.name(fourth)!r}")
lap.close()

# --- deepest match wins, and the rest stays per project -----------------------

lap = Laptop(dict(KLIUM, thinkingtoo={"paths": ["~/Projects/thinkingtoo*"],
                                      "roster": ["Amir", "Yuki"]}))
klium = lap.start(lap.path("Projects/thinkingtoo-wt-bf/clients/klium"))
docs = lap.start(lap.path("Projects/thinkingtoo-wt-bf/docs"))
check("a client folder beats the repo family it lives in",
      lap.name(klium) == "Dmitri" and lap.name(docs) == "Amir",
      f"klium {lap.name(klium)!r}, docs {lap.name(docs)!r}")
outside = lap.start(lap.path("Projects/elsewhere"))
projects = json.loads((lap.cfg / "agent-names" / "projects.json").read_text())
check("a path no area matches is named per project, as before",
      lap.name(outside) in ROSTER and lap.name(outside) not in ("Dmitri", "Leila", "Tomas", "Amir", "Yuki")
      and [v["name"] for v in projects.values()] == [lap.name(outside)],
      f"name {lap.name(outside)!r}, projects {projects}")
check("an area session never writes projects.json",
      len(projects) == 1, f"projects {projects}")
lap.close()

# --- a session keeps its own name -------------------------------------------

lap = Laptop(KLIUM)
first = lap.start(lap.path(WORKTREES[0]))
second = lap.start(lap.path(WORKTREES[1]))
lap.stop(first)
lap.write(second, "another-derived-label")              # Claude Code relabels
lap.fire(second)
check("a relabelled Leila stays Leila while Dmitri is free",
      lap.name(second) == "Leila", f"became {lap.name(second)!r}")
lap.close()

# --- a roster name that names.txt does not have -------------------------------
#
# A job's label carries no nameSource, so the hook knows a name is its own only
# by finding it in the roster. An area's names count as roster names.

lap = Laptop({"box": {"paths": ["~/srv"], "roster": ["Hermes"]}})
job = lap.start(lap.path("srv/digest"), kind="bg", event="UserPromptSubmit")
out = lap.fire(job)
check("a job keeps an area name that names.txt does not have",
      lap.name(job) == "Hermes", f"became {lap.name(job)!r}")
check("and is not re-announced on every prompt", out.strip() == "", out[:120])
lap.close()

# --- a resident named by CAN_NAME -------------------------------------------
#
# A night job on the box is a headless `claude -p` run with CAN_NAME=James in
# its service unit. Every run is James, wherever it starts, with no roster draw.

lap = Laptop(KLIUM)
james = {"CAN_NAME": "James"}
runs = []
for _ in range(3):
    sid = lap.start(lap.path(WORKTREES[0]), env=james)
    runs.append(lap.name(sid))
    lap.stop(sid)
check("CAN_NAME=James registers as James on every run",
      runs == ["James"] * 3, f"got {runs}")
print(f"     three runs: {', '.join(runs)}")
check("and draws nothing from the area's roster",
      lap.roster("thinkingtoo/klium") == ["Dmitri", "Leila", "Tomas"],
      f"roster is {lap.roster('thinkingtoo/klium')}")

job = lap.start(lap.path("srv/james"), env=james, kind="bg", event="UserPromptSubmit")
lap.fire(job, env=james)
check("a James background job keeps James on the next prompt",
      lap.name(job) == "James", f"became {lap.name(job)!r}")
lap.write(job, "Dmitri", source=None, kind="bg")        # named before CAN_NAME was set
lap.fire(job, env=james)
check("a session carrying a roster name becomes James once CAN_NAME is set",
      lap.name(job) == "James", f"stayed {lap.name(job)!r}")
overlap = lap.start(lap.path("srv/james"), env=james)
check("a run that overlaps the last one is James too",
      lap.name(overlap) == "James", f"got {lap.name(overlap)!r}")
lap.stop_all()

plain = lap.start(lap.path(WORKTREES[0]))
check("a session without CAN_NAME is not James",
      lap.name(plain) == "Dmitri", f"got {lap.name(plain)!r}")
lap.close()

# --- agent-name areas --from-projects ---------------------------------------
#
# Today every worktree is a project of its own in projects.json. The migration
# reads that file, never writes it, and prints an areas.json to review: a repo
# family per main checkout and its worktrees, and a client folder wherever a
# session's scratchpad shows one was worked in.

lap = Laptop()
H = lap.home
(H / "Projects/thinkingtoo/clients/klium").mkdir(parents=True)


def scratchpad(cwd, sid):
    enc = "".join(c if c.isalnum() else "-" for c in str(cwd))
    return f"/tmp/claude-1000/{enc}/{sid}/scratchpad"


store = {
    str(H / "Projects/thinkingtoo"): {"name": "Dmitri", "last_used": 300},
    str(H / "Projects/thinkingtoo-wt-chiara"): {"name": "Fatima", "last_used": 100},
    str(H / "Projects/thinkingtoo-pablo"): {"name": "Amir", "last_used": 200},
    str(H / "Projects/thinkingtoo/.claude/worktrees/bettina"): {"name": "Roxana", "last_used": 50},
    str(H / "Projects/thinkingtoo-mira"): {"name": "Viktor", "last_used": 30},
    str(H / "Projects/thinkingtoo-mira-libmcp"): {"name": "Mikkel", "last_used": 20},
    str(H / "Projects/thinkingtoo-mira-memostage"): {"name": "Nabil", "last_used": 20},
    str(H / "Projects/render-doc-wt-160"): {"name": "Nia", "last_used": 20},
    str(H / "Projects/render-doc-wt-161"): {"name": "Selin", "last_used": 20},
    str(H / "Projects/render-doc"): {"name": "Pablo", "last_used": 300},
    str(H / "Projects/render-doc-wt"): {"name": "Mira", "last_used": 200},
    str(H / "Projects/render-doc-wt/hilde"): {"name": "Sahar", "last_used": 250},
    str(H / "Projects/solo"): {"name": "Oskar", "last_used": 300},
    scratchpad(H / "Projects/thinkingtoo/clients/klium",
               "18ef1ff9-1761-49f3-89f0-188641ae4eb7"): {"name": "Leila", "last_used": 10},
    scratchpad(H / "Projects/thinkingtoo",
               "9f96cf96-9504-4303-83ed-3bec9ee4dab5"): {"name": "Elske", "last_used": 10},
    "/tmp": {"name": "Milos", "last_used": 10},
}
store_file = lap.cfg / "agent-names" / "projects.json"
store_file.write_text(json.dumps(store, indent=1, sort_keys=True))
before = store_file.read_bytes()

out = subprocess.run([str(AGENT_NAME), "areas", "--from-projects"], env=lap.env(),
                     capture_output=True, text=True, timeout=30)
try:
    proposal = json.loads(out.stdout)
except ValueError:
    proposal = {}
got = proposal.get("areas") or {}
check("the migration prints an areas.json proposal",
      out.returncode == 0 and set(got) == {"thinkingtoo", "thinkingtoo/clients/klium",
                                           "render-doc"},
      f"exit {out.returncode}, areas {sorted(got)}, stderr {out.stderr[:200]}")
check("a repo family covers its main checkout and every worktree beside it",
      got.get("thinkingtoo", {}).get("paths") == ["~/Projects/thinkingtoo",
                                                  "~/Projects/thinkingtoo-*"],
      str(got.get("thinkingtoo")))
check("its roster is the main checkout's name, then the most recent, three at most",
      got.get("thinkingtoo", {}).get("roster") == ["Dmitri", "Amir", "Fatima"],
      str(got.get("thinkingtoo")))
check("a client folder seen in a scratchpad becomes an area of its own",
      got.get("thinkingtoo/clients/klium") == {
          "paths": ["~/Projects/thinkingtoo/clients/klium",
                    "~/Projects/thinkingtoo-*/clients/klium"],
          "roster": ["Leila"]},
      str(got.get("thinkingtoo/clients/klium")))
check("a worktree of a worktree belongs to the main checkout's family",
      "thinkingtoo-mira" not in got and "render-doc-wt" not in got, f"areas {sorted(got)}")
check("a family of nested worktrees is found too",
      got.get("render-doc", {}).get("roster") == ["Pablo", "Sahar", "Mira"],
      str(got.get("render-doc")))
check("the proposal says how many entries it read",
      "16 entries" in proposal.get("_proposal", ""), proposal.get("_proposal", ""))
check("and projects.json is left as it was", store_file.read_bytes() == before)
check("and no areas.json is written", not lap.areas_file.exists())
lap.close()

# --- no areas.json: nothing changes -----------------------------------------

lap = Laptop()
sid = lap.start(lap.path(WORKTREES[0]))
check("without areas.json a session is named per project, as before",
      lap.name(sid) in ROSTER and not lap.areas_file.exists()
      and len(json.loads((lap.cfg / "agent-names" / "projects.json").read_text())) == 1,
      f"got {lap.name(sid)!r}")
lap.close()


print()
if failures:
    print(f"{len(failures)} failing: " + ", ".join(failures))
    raise SystemExit(1)
print("all passing")
