#!/usr/bin/env bash
# Remove claude-agent-names from this machine's Claude Code config.
# Restores whatever statusline you had before installing.
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
CFG="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
SETTINGS="$CFG/settings.json"
STATE="$CFG/agent-names"

[[ -f $SETTINGS ]] || { echo "No settings at $SETTINGS"; exit 0; }
cp "$SETTINGS" "$SETTINGS.bak.agent-names-uninstall.$(date +%s)"

ROOT="$ROOT" SETTINGS="$SETTINGS" STATE="$STATE" python3 <<'PY'
import json, os

root = os.environ["ROOT"]
settings_path = os.environ["SETTINGS"]
state = os.environ["STATE"]
wrapper = f"{root}/scripts/statusline.sh"

with open(settings_path, encoding="utf-8") as fh:
    settings = json.load(fh)

ours = {f'"{root}/hooks/assign-name.sh"', f'"{root}/hooks/release-name.sh"'}
for event, groups in list(settings.get("hooks", {}).items()):
    kept = []
    for group in groups:
        hooks = [h for h in group.get("hooks", []) if h.get("command") not in ours]
        if hooks:
            group["hooks"] = hooks
            kept.append(group)
    if kept:
        settings["hooks"][event] = kept
    else:
        settings["hooks"].pop(event, None)
if not settings.get("hooks"):
    settings.pop("hooks", None)

if settings.get("statusLine", {}).get("command") == wrapper:
    inner = ""
    try:
        with open(os.path.join(state, "config.json"), encoding="utf-8") as fh:
            inner = json.load(fh).get("statusline", "")
    except (OSError, ValueError):
        pass
    if inner:
        settings["statusLine"] = {
            "type": "command",
            "command": inner,
            "padding": settings["statusLine"].get("padding", 0),
        }
        print(f"statusLine restored to: {inner}")
    else:
        settings.pop("statusLine", None)
        print("statusLine removed")

with open(settings_path, "w", encoding="utf-8") as fh:
    json.dump(settings, fh, indent=2)
print("hooks removed")
PY

echo "Done. State in $STATE was left in place -- delete it by hand if you want it gone."
