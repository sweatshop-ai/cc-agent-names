#!/usr/bin/env bash
# Install claude-agent-names into this machine's Claude Code config.
#
# Adds two hooks and (by default) wraps your existing statusline so the name
# appears in front of it. Everything it writes is reversible with ./uninstall.sh.
#
#   WRAP_STATUSLINE=0 ./install.sh   # hooks only, leave the statusline alone
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
CFG="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
SETTINGS="$CFG/settings.json"
STATE="$CFG/agent-names"

[[ -d $CFG ]] || { echo "No Claude config at $CFG" >&2; exit 1; }
command -v python3 >/dev/null || { echo "python3 is required" >&2; exit 1; }

mkdir -p "$STATE"
[[ -f $STATE/registry.json ]] || printf '{}' > "$STATE/registry.json"

if [[ -f $SETTINGS ]]; then
    backup="$SETTINGS.bak.agent-names.$(date +%s)"
    cp "$SETTINGS" "$backup"
    echo "backed up settings to $backup"
else
    printf '{}' > "$SETTINGS"
fi

ROOT="$ROOT" SETTINGS="$SETTINGS" STATE="$STATE" \
WRAP="${WRAP_STATUSLINE:-1}" python3 <<'PY'
import json, os

root = os.environ["ROOT"]
settings_path = os.environ["SETTINGS"]
state = os.environ["STATE"]
wrap = os.environ["WRAP"] == "1"
wrapper = f"{root}/scripts/statusline.sh"

with open(settings_path, encoding="utf-8") as fh:
    settings = json.load(fh)

def ensure_hook(event, command, is_async=False):
    """Add a hook unless an identical command is already registered."""
    groups = settings.setdefault("hooks", {}).setdefault(event, [])
    for group in groups:
        for hook in group.get("hooks", []):
            if hook.get("command") == command:
                return False
    entry = {"type": "command", "command": command}
    if is_async:
        entry["async"] = True
    groups.append({"hooks": [entry]})
    return True

done = []
if ensure_hook("UserPromptSubmit", f'"{root}/hooks/assign-name.sh"'):
    done.append("UserPromptSubmit hook")
if ensure_hook("SessionEnd", f'"{root}/hooks/release-name.sh"', is_async=True):
    done.append("SessionEnd hook")

if wrap:
    current = settings.get("statusLine")
    config_path = os.path.join(state, "config.json")
    try:
        with open(config_path, encoding="utf-8") as fh:
            cfg = json.load(fh)
    except (OSError, ValueError):
        cfg = {}

    # Preserve whatever statusline was already configured by running it inside
    # ours. Guard against re-wrapping our own wrapper on a second install.
    if isinstance(current, dict):
        cmd = current.get("command", "")
        if cmd and cmd != wrapper:
            cfg["statusline"] = cmd

    with open(config_path, "w", encoding="utf-8") as fh:
        json.dump(cfg, fh, indent=2)

    padding = current.get("padding", 0) if isinstance(current, dict) else 0
    if not (isinstance(current, dict) and current.get("command") == wrapper):
        done.append(f"statusLine wrapped (inner: {cfg.get('statusline') or 'built-in'})")
    settings["statusLine"] = {"type": "command", "command": wrapper, "padding": padding}

with open(settings_path, "w", encoding="utf-8") as fh:
    json.dump(settings, fh, indent=2)

print("installed: " + (", ".join(done) if done else "nothing new (already installed)"))
PY

echo
echo "Done. Open a new Claude session and send it any prompt to claim a name."
echo "Sessions already running keep their current name until restarted."
