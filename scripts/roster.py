#!/usr/bin/env python3
"""Print the current roster: who is running, where, and how busy.

ListAgents already shows names, but not what each session is working on. This
joins Claude's peer files into a "who is on what" view, which is the question
you actually ask before sending someone a message.
"""
import json
import os
import sys
from pathlib import Path

cfg = Path(os.environ.get("CLAUDE_CONFIG_DIR", str(Path.home() / ".claude")))
sessions_dir = cfg / "sessions"
me = os.environ.get("CLAUDE_SESSION_ID", "")

rows = []
if sessions_dir.is_dir():
    for path in sorted(sessions_dir.glob("*.json")):
        try:
            d = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(d, dict):
            continue
        rows.append({
            "name": d.get("name") or "(unnamed)",
            "named": d.get("nameSource") is None,
            "kind": d.get("kind") or "?",
            "status": d.get("status") or "?",
            "cwd": d.get("cwd") or "",
            "tmux": d.get("tmux") or "",
            "sid": d.get("sessionId") or "",
        })

if not rows:
    print("No Claude sessions are registered.")
    sys.exit(0)

# Named interactive sessions first -- those are the ones you can address.
rows.sort(key=lambda r: (r["kind"] != "interactive", not r["named"], r["name"].lower()))

width = max(len(r["name"]) for r in rows)
home = str(Path.home())
for r in rows:
    where = r["cwd"].replace(home, "~") if r["cwd"] else "-"
    mark = " <- you" if me and r["sid"] == me else ""
    tag = "" if r["kind"] == "interactive" else f" [{r['kind']}]"
    print(f"{r['name']:<{width}}  {r['status']:<6}  {where}{tag}{mark}")
