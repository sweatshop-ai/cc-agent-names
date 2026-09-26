#!/usr/bin/env python3
"""Pick a free human name for a session that is about to start.

Prints the name on stdout, or nothing if none could be chosen.

Which names are taken is never bookkept. Claude Code already writes a peer file
per live session containing its name, so the system's own state answers it --
nothing to drift, nothing to clean up, and a crashed session releases its name
the moment its peer file disappears.

The one gap is the window between choosing a name and Claude writing its peer
file. A short-lived reservation file covers exactly that window.

What a session was called *is* remembered, per session id. A session can need
naming more than once -- Claude Code rewrites the peer record on its own
schedule, and a rewrite puts a derived name back -- and without that memory the
second pick is a fresh roll of the dice, so a session peers already know by name
starts answering to another one. Like project stickiness this is a preference,
never a reservation: a remembered name is only ever handed back if no live
session holds it.

Names are sticky per project: the session you open in a repo tomorrow gets the
name the last one had, so "Oskar wrote this" keeps meaning something across
sessions. Stickiness is a preference, never a reservation -- a name is only
ever handed out if no live session holds it, so Oskar is still exactly one
session at a time. Open a second session in the same project and it gets its
own name rather than waiting for the first to exit.
"""
import fcntl
import json
import os
import random
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import registry  # noqa: E402

# A reservation only has to cover the gap between choosing a name and Claude
# writing its peer file -- a second or two. After that the peer file itself says
# the name is taken, so the reservation is redundant. Holding one for longer just
# means a session that exits soon after starting keeps its project's name locked
# out of the next launch.
RESERVE_TTL = 30

# A session id never comes back once its session is gone for good, so the memory
# of what it was called is only useful while a resume is still plausible.
SESSION_TTL = 30 * 24 * 3600

cfg = Path(os.environ.get("CLAUDE_CONFIG_DIR", str(Path.home() / ".claude")))
state = cfg / "agent-names"
names_file = Path(os.environ.get("CAN_NAMES") or (state / "names.txt"))
if not names_file.is_file():
    names_file = Path(__file__).resolve().parent.parent / "data" / "names.txt"


def reservation(entry):
    """A held name's (timestamp, session id), old format or new.

    Reservations used to be a bare timestamp. One written by an older version is
    still honoured -- it just belongs to nobody, so it holds against everyone.
    """
    if isinstance(entry, dict):
        return entry.get("at") or 0, entry.get("sid") or ""
    if isinstance(entry, (int, float)):
        return entry, ""
    return 0, ""


def live_names(mine=""):
    """Names currently held by live sessions, per Claude's own registry.

    A session's own record is skipped. Otherwise a session asking to be renamed
    -- which is what a `collision` or a re-derived label amounts to -- would find
    its own name in the taken set and be pushed off it by itself.

    Only live sessions count. A peer file that outlived its session used to
    hold its name forever.
    """
    return {rec["name"] for rec in registry.live(cfg)
            if rec.get("name") and not (mine and rec.get("sessionId") == mine)}


def project_key(cwd):
    """What counts as "the same project" for the purposes of keeping a name.

    The git top level, so every session in a repo shares one identity no matter
    which subdirectory you start from. A worktree reports its own top level, so
    parallel branches get their own names -- which is what you want, since they
    are parallel work.
    """
    try:
        out = subprocess.run(["git", "-C", cwd, "rev-parse", "--show-toplevel"],
                             capture_output=True, text=True, timeout=3)
    except (OSError, subprocess.SubprocessError):
        out = None
    if out is not None and out.returncode == 0:
        top = out.stdout.strip()
        if top:
            return top
    return os.path.realpath(cwd)


def load_map(path):
    try:
        with path.open(encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def save_map(path, data):
    tmp = path.with_suffix(".tmp")
    try:
        with tmp.open("w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=1, sort_keys=True)
        os.replace(tmp, path)
    except OSError:
        pass


def base_name(name):
    """The root a suffixed name hangs off: `Anna-2` is Anna's.

    Retiring Anna from names.txt has to retire Anna-2 with her, or a remembered
    name could outlive the roster it came from.
    """
    root = name.rsplit("-", 1)
    if len(root) == 2 and root[1].isdigit():
        return root[0]
    return name


def load_pool():
    seen, pool = set(), []
    try:
        with names_file.open(encoding="utf-8") as fh:
            for line in fh:
                name = line.strip()
                if name and not name.startswith("#") and name not in seen:
                    seen.add(name)
                    pool.append(name)
    except OSError:
        return []
    return pool


def release(name):
    """Drop a reservation, because the name is now in the peer file.

    The caller that writes the peer file itself -- the SessionStart hook -- can
    say so the moment it lands, microseconds after choosing. Then no reservation
    outlives its purpose, and a session that exits seconds later never keeps its
    project locked out of its own name. The shell wrapper cannot do this: it
    chooses before Claude exists, so it has to fall back on RESERVE_TTL.
    """
    reservations = state / "reservations.json"
    try:
        with open(state / "pick.lock", "a+") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            try:
                with reservations.open(encoding="utf-8") as fh:
                    held = json.load(fh)
            except (OSError, ValueError):
                return
            if not isinstance(held, dict) or name not in held:
                return
            held.pop(name, None)
            tmp = reservations.with_suffix(".tmp")
            with tmp.open("w", encoding="utf-8") as fh:
                json.dump(held, fh)
            os.replace(tmp, reservations)
    except OSError:
        pass


def main():
    if len(sys.argv) > 2 and sys.argv[1] == "--release":
        release(sys.argv[2])
        return

    pool = load_pool()
    if not pool:
        return

    state.mkdir(parents=True, exist_ok=True)
    reservations = state / "reservations.json"

    with open(state / "pick.lock", "a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)

        now = time.time()
        try:
            with reservations.open(encoding="utf-8") as fh:
                held = json.load(fh)
        except (OSError, ValueError):
            held = {}
        if not isinstance(held, dict):
            held = {}
        # Drop reservations whose session has had ample time to register: if the
        # name were still in use, a live peer file would say so.
        held = {n: e for n, e in held.items()
                if now - reservation(e)[0] < RESERVE_TTL}

        projects_file = state / "projects.json"
        projects = load_map(projects_file)
        key = project_key(os.environ.get("CAN_CWD") or os.getcwd())

        # What each session has been called. Pruned by age: a session id that
        # has not been seen in a month is not coming back.
        sid = os.environ.get("CAN_SESSION") or ""
        sessions_file = state / "sessions.json"
        sessions = {s: v for s, v in load_map(sessions_file).items()
                    if isinstance(v, dict)
                    and now - (v.get("last_used") or 0) < SESSION_TTL}

        # A session's own reservation must not count against it. The statusline
        # can adopt the same session twice inside the window, and the second pass
        # would otherwise find the name it just chose already spoken for.
        taken = live_names(sid) | {n for n, e in held.items()
                                   if not sid or reservation(e)[1] != sid}
        free = [n for n in pool if n not in taken]

        remembered = (projects.get(key) or {}).get("name")
        # Editing a name out of names.txt is how you retire it. A preference
        # recorded before that must not resurrect it.
        if remembered and remembered not in pool:
            remembered = None
        # Every name another project has claimed, so a new project starts with
        # an identity of its own rather than borrowing one already in use.
        spoken_for = {(v or {}).get("name") for k, v in projects.items() if k != key}

        # What this session was called the last time it was named. It outranks
        # the project's usual name, which a sibling session may well be holding:
        # keeping one session on one name matters more than which name a project
        # tends to use, and peers have already been told this one.
        entry = (sessions.get(sid) or {}) if sid else {}
        mine = entry.get("name")
        # A name assigned from outside (`agent-name set`) was never the roster's
        # to retire; anything else leaves with its roster entry.
        if mine and not entry.get("assigned") and base_name(mine) not in pool:
            mine = None

        if mine and mine not in taken:
            chosen = mine                          # this session's own name, free
        elif remembered and remembered not in taken:
            chosen = remembered                    # this project's usual name, free
        elif free:
            fresh = [n for n in free if n not in spoken_for]
            chosen = random.choice(fresh or free)
            if not remembered:
                # First session in this project: this becomes its name.
                projects[key] = {"name": chosen, "last_used": int(now)}
                save_map(projects_file, projects)
        else:
            # More sessions than names. Suffix rather than collide.
            base = random.choice(pool)
            n = 2
            while f"{base}-{n}" in taken:
                n += 1
            chosen = f"{base}-{n}"

        if remembered == chosen:
            projects[key]["last_used"] = int(now)
            save_map(projects_file, projects)

        if sid:
            sessions[sid] = {"name": chosen, "last_used": int(now)}
            if chosen == mine and entry.get("assigned"):
                sessions[sid]["assigned"] = True
            save_map(sessions_file, sessions)

        held[chosen] = {"at": now, "sid": sid}
        tmp = reservations.with_suffix(".tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            json.dump(held, fh)
        os.replace(tmp, reservations)

    print(chosen)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass  # never block a session from starting
