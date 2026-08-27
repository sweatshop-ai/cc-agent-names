#!/usr/bin/env python3
"""install.sh / uninstall.sh round-trip, against a throwaway CLAUDE_CONFIG_DIR.

Run: python3 tests/test_install.py

The wiring is the half of this plugin that is easy to get wrong quietly: the code
can be perfect and the feature still absent because settings.json never learned
about the second event. These cases pin that down, plus the promise uninstall.sh
makes in its own header -- that it leaves settings.json as it found it.
"""
import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOK = "session_start_name.py"
failures = []


def run(script, cfg):
    env = dict(os.environ, CLAUDE_CONFIG_DIR=cfg)
    return subprocess.run(["bash", os.path.join(ROOT, script)], env=env,
                          capture_output=True, text=True, timeout=120, input="\n")


def ours_per_event(cfg):
    """How many of OUR hooks each event carries -- 2 would mean a stacked install."""
    with open(os.path.join(cfg, "settings.json"), encoding="utf-8") as fh:
        hooks = json.load(fh).get("hooks", {})
    return {event: sum(1 for group in groups for h in group.get("hooks", [])
                       if HOOK in h.get("command", ""))
            for event, groups in hooks.items()}


def check(label, condition, detail=""):
    print(f"{'ok  ' if condition else 'FAIL'} {label}{'' if condition else '  -- ' + detail}")
    if not condition:
        failures.append(label)


def write(cfg, settings):
    path = os.path.join(cfg, "settings.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(settings, fh, indent=2)
    return path


# --- a fresh install wires both events ---------------------------------------

with tempfile.TemporaryDirectory() as cfg:
    before = {"theme": "dark", "hooks": {"SessionStart": [
        {"hooks": [{"type": "command", "command": "/other/thing.sh"}]}]}}
    original = json.dumps(before, indent=2)
    write(cfg, before)

    run("install.sh", cfg)
    counts = ours_per_event(cfg)
    check("install wires SessionStart", counts.get("SessionStart") == 1, str(counts))
    check("install wires UserPromptSubmit", counts.get("UserPromptSubmit") == 1, str(counts))

    run("install.sh", cfg)
    counts = ours_per_event(cfg)
    check("re-running the installer stacks nothing",
          counts.get("SessionStart") == 1 and counts.get("UserPromptSubmit") == 1, str(counts))

    with open(os.path.join(cfg, "settings.json"), encoding="utf-8") as fh:
        kept = json.load(fh)
    check("a foreign hook on the same event survives",
          any(h.get("command") == "/other/thing.sh"
              for g in kept["hooks"]["SessionStart"] for h in g.get("hooks", [])))
    check("unrelated settings survive", kept.get("theme") == "dark")

    run("uninstall.sh", cfg)
    with open(os.path.join(cfg, "settings.json"), encoding="utf-8") as fh:
        after = fh.read()
    check("uninstall restores settings.json as it was",
          json.loads(after) == json.loads(original), after[:200])

# --- upgrading a SessionStart-only install adds the missing event ------------
# The shape every existing user is in: our hook already on SessionStart, nothing
# on UserPromptSubmit. The installer must add one and leave the other alone.

with tempfile.TemporaryDirectory() as cfg:
    script = os.path.join(ROOT, "hooks", HOOK)
    write(cfg, {"hooks": {"SessionStart": [
        {"hooks": [{"type": "command", "command": script, "timeout": 10}]}]}})

    out = run("install.sh", cfg)
    counts = ours_per_event(cfg)
    check("upgrade adds UserPromptSubmit", counts.get("UserPromptSubmit") == 1, str(counts))
    check("upgrade does not duplicate SessionStart", counts.get("SessionStart") == 1, str(counts))
    check("upgrade says which event it skipped",
          "SessionStart hook already registered" in out.stdout, out.stdout[:200])

print()
if failures:
    print(f"{len(failures)} failing: " + ", ".join(failures))
    raise SystemExit(1)
print("all passing")
