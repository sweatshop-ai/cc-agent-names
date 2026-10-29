#!/usr/bin/env python3
"""Give a human name to every running session that still has a machine one.

Useful right after installing, so sessions that were already open don't keep
names like `webapp-94` until you restart them. New sessions don't need this:
the launcher names them, and the statusline adopts any that slip through.

Names set by hand with /rename (`nameSource: "user"`) are never touched.

Background jobs are adopted too. Their label carries no nameSource, so the test
for "already ours" is membership of the roster rather than that field.

`--dry-run` is a real run on a throwaway copy of the peer files and the
plugin's state, so its preview is what a real run would do -- names an earlier
rename frees, a roster an earlier one grows -- and nothing of yours is written.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import areas  # noqa: E402
import registry  # noqa: E402

HERE = Path(__file__).resolve().parent
MACHINE_NAMED = ("derived", "auto", "collision")
NAMED_KINDS = ("interactive", "bg")

cfg = Path(os.environ.get("CLAUDE_CONFIG_DIR", str(Path.home() / ".claude")))
dry_run = "--dry-run" in sys.argv


def pick(cwd, session_id=""):
    """Choose a name for a session, keyed to the directory that session is in.

    Not to ours: adopting a batch of sessions from one terminal must still give
    each of them the name its own project remembers, or every adopted session
    would record a preference against whatever directory this command was run
    from.

    Keyed to its id too, so a session adopted here answers to the same name
    afterwards rather than being re-picked the next time Claude Code relabels it.
    """
    env = dict(os.environ, CAN_CWD=cwd or os.getcwd(), CAN_SESSION=session_id)
    # CAN_NAME belongs to the shell this runs from, not to the sessions it adopts.
    env.pop("CAN_NAME", None)
    try:
        out = subprocess.run([sys.executable, str(HERE / "pick_name.py")], env=env,
                             capture_output=True, text=True, timeout=8)
    except (OSError, subprocess.SubprocessError):
        return ""
    return out.stdout.strip()


def roster():
    """The names this plugin hands out: the files pick_name.py reads, areas included."""
    override = cfg / "agent-names" / "names.txt"
    path = override if override.is_file() else (HERE.parent / "data" / "names.txt")
    in_areas = areas.names_in(cfg / "agent-names")
    try:
        with path.open(encoding="utf-8") as fh:
            return in_areas | {ln.strip() for ln in fh if ln.strip() and not ln.startswith("#")}
    except OSError:
        return in_areas


def sandbox():
    """Point this run, and the pickers it starts, at a copy of the state."""
    global cfg
    tmp = Path(tempfile.mkdtemp(prefix="agent-names-dry-run-"))
    for sub in ("sessions", "agent-names"):
        if (cfg / sub).is_dir():
            shutil.copytree(cfg / sub, tmp / sub)
    (tmp / "sessions").mkdir(exist_ok=True)
    areas_file = os.environ.get("CAN_AREAS")
    if areas_file and Path(areas_file).is_file():
        shutil.copy(areas_file, tmp / "areas-dry-run.json")
        os.environ["CAN_AREAS"] = str(tmp / "areas-dry-run.json")
    cfg = tmp
    os.environ["CLAUDE_CONFIG_DIR"] = str(tmp)
    return tmp


def main():
    if dry_run:
        tmp = sandbox()
        try:
            adopt()
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    else:
        adopt()


def adopt():
    pool = roster()
    renamed = skipped = 0
    # Live sessions only: a peer file its session left behind has nobody to
    # answer to the name.
    for rec in registry.live(cfg):
        path = Path(rec["path"])
        if rec.get("kind") not in NAMED_KINDS:
            continue
        # A background job carries a label with no nameSource, so roster
        # membership is the only signal that the name is already ours.
        if rec.get("nameSource") not in MACHINE_NAMED and (rec.get("name") or "") in pool:
            skipped += 1
            continue
        if rec.get("nameSource") == "user":
            skipped += 1
            continue

        old = rec.get("name") or "?"
        new = pick(rec.get("cwd") or "", rec.get("sessionId") or "")
        if not new:
            continue

        try:
            with path.open(encoding="utf-8") as fh:
                fresh = json.load(fh)
            if fresh.get("nameSource") == "user":
                continue
            if fresh.get("nameSource") not in MACHINE_NAMED and (fresh.get("name") or "") in pool:
                continue
            fresh["name"] = new
            fresh.pop("nameSource", None)
            tmp = path.with_suffix(".json.agent-names-tmp")
            with tmp.open("w", encoding="utf-8") as fh:
                json.dump(fresh, fh)
            os.replace(tmp, path)      # atomic: never a half-written peer file
        except (OSError, ValueError):
            continue
        cwd = (fresh.get("cwd") or "").replace(str(Path.home()), "~")
        print(f"  {'would rename ' if dry_run else ''}{old} -> {new}   ({cwd})")
        renamed += 1

    verb = "would rename" if dry_run else "renamed"
    print(f"\n{verb} {renamed}; left alone {skipped} already-named")


if __name__ == "__main__":
    main()
