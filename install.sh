#!/usr/bin/env bash
# Install claude-agent-names.
#
# Two changes, both reversible with ./uninstall.sh:
#   1. sources scripts/shell-init.sh from your shell rc, so new sessions get a
#      name before Claude starts
#   2. points your statusLine at scripts/statusline.py, which shows the name and
#      then runs whatever statusline you already had
#
#   WRAP_STATUSLINE=0 ./install.sh   # skip the statusline change
#   NO_SHELL_RC=1     ./install.sh   # skip the shell rc change
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
CFG="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
SETTINGS="$CFG/settings.json"
STATE="$CFG/agent-names"
MARK_BEGIN="# >>> claude-agent-names >>>"
MARK_END="# <<< claude-agent-names <<<"

[[ -d $CFG ]] || { echo "No Claude config at $CFG" >&2; exit 1; }
command -v python3 >/dev/null || { echo "python3 is required" >&2; exit 1; }

mkdir -p "$STATE"

# --- shell rc -------------------------------------------------------------
if [[ ${NO_SHELL_RC:-0} != 1 ]]; then
    for rc in "$HOME/.bashrc" "$HOME/.zshrc"; do
        [[ -f $rc ]] || continue
        if grep -qF "$MARK_BEGIN" "$rc"; then
            echo "shell rc already wired: $rc"
            continue
        fi
        cp "$rc" "$rc.bak.agent-names.$(date +%s)"
        {
            printf '\n%s\n' "$MARK_BEGIN"
            printf 'source "%s/scripts/shell-init.sh"\n' "$ROOT"
            printf '%s\n' "$MARK_END"
        } >> "$rc"
        echo "wired $rc"
    done
fi

# --- statusline -----------------------------------------------------------
if [[ ${WRAP_STATUSLINE:-1} == 1 ]]; then
    if [[ -f $SETTINGS ]]; then
        backup="$SETTINGS.bak.agent-names.$(date +%s)"
        cp "$SETTINGS" "$backup"
        echo "backed up settings to $backup"
    else
        printf '{}' > "$SETTINGS"
    fi

    ROOT="$ROOT" SETTINGS="$SETTINGS" STATE="$STATE" python3 <<'PY'
import json, os, shutil

root, settings_path, state = os.environ["ROOT"], os.environ["SETTINGS"], os.environ["STATE"]
wrapper = f"{root}/scripts/statusline.py"

with open(settings_path, encoding="utf-8") as fh:
    settings = json.load(fh)

config_path = os.path.join(state, "config.json")
try:
    with open(config_path, encoding="utf-8") as fh:
        cfg = json.load(fh)
except (OSError, ValueError):
    cfg = {}

current = settings.get("statusLine")
if isinstance(current, dict):
    cmd = current.get("command", "")
    # Preserve the statusline you already had; never re-wrap our own wrapper.
    if cmd and cmd != wrapper:
        cfg["statusline"] = cmd

inner = cfg.get("statusline", "")

# A vendored copy avoids `npx` re-resolving the package on every render, which
# costs seconds. Only relevant for the fallback path, but worth having.
vendored = os.path.join(state, "vendor/node_modules/ccstatusline/dist/ccstatusline.js")
if "ccstatusline" in inner and "npx" in inner and os.path.exists(vendored) and shutil.which("node"):
    # Remember what was really there, so uninstall restores it faithfully
    # rather than leaving our optimisation behind.
    cfg.setdefault("statusline_original", inner)
    cfg["statusline"] = f"node {vendored}"
    print(f"inner statusline repointed at vendored copy (was: {inner})")

# The fast renderer only understands ccstatusline configs, so only enable it
# when that is what is actually being replaced. It falls back on its own if the
# config uses anything it cannot reproduce exactly.
cfg["fast"] = "ccstatusline" in cfg.get("statusline", "")

with open(config_path, "w", encoding="utf-8") as fh:
    json.dump(cfg, fh, indent=2)

padding = current.get("padding", 0) if isinstance(current, dict) else 0
settings["statusLine"] = {"type": "command", "command": wrapper, "padding": padding}

with open(settings_path, "w", encoding="utf-8") as fh:
    json.dump(settings, fh, indent=2)

print(f"statusLine wrapped (fast renderer: {'on' if cfg['fast'] else 'off'})")
PY
fi

# --- adopt sessions that are already running --------------------------------
# Without this, sessions open at install time keep names like `webapp-94`
# until they are restarted.
echo
echo "Naming sessions that are already running:"
CLAUDE_CONFIG_DIR="$CFG" python3 "$ROOT/scripts/adopt_all.py" || true

echo
echo "Done. Open a NEW terminal (or: source ~/.bashrc) so new sessions are"
echo "named at launch."
