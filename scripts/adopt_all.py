#!/usr/bin/env python3
"""Give a human name to every running session that still has a machine one.

Useful right after installing, so sessions that were already open don't keep
names like `webapp-94` until you restart them. New sessions don't need this:
the launcher names them, and the statusline adopts any that slip through.

Names set by hand with /rename (`nameSource: "user"`) are never touched.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
MACHINE_NAMED = ("derived", "auto", "collision")

cfg = Path(os.environ.get("CLAUDE_CONFIG_DIR", str(Path.home() / ".claude")))
dry_run = "--dry-run" in sys.argv


def pick():
    try:
        out = subprocess.run([sys.executable, str(HERE / "pick_name.py")],
                             capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return ""
    return out.stdout.strip()


def main():
    sessions = cfg / "sessions"
    if not sessions.is_dir():
        print("no sessions directory")
        return

    renamed = skipped = 0
    for path in sorted(sessions.glob("*.json")):
        try:
            with path.open(encoding="utf-8") as fh:
                rec = json.load(fh)
        except (OSError, ValueError):
            continue
        if not isinstance(rec, dict) or rec.get("kind") != "interactive":
            continue
        if rec.get("nameSource") not in MACHINE_NAMED:
            skipped += 1
            continue

        old = rec.get("name") or "?"
        new = pick()
        if not new:
            continue
        if dry_run:
            print(f"  would rename {old} -> {new}")
            renamed += 1
            continue

        try:
            with path.open(encoding="utf-8") as fh:
                fresh = json.load(fh)
            if fresh.get("nameSource") not in MACHINE_NAMED:
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
        print(f"  {old} -> {new}   ({cwd})")
        renamed += 1

    verb = "would rename" if dry_run else "renamed"
    print(f"\n{verb} {renamed}; left alone {skipped} already-named")


if __name__ == "__main__":
    main()
