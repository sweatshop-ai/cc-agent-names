#!/usr/bin/env bash
# Install claude-agent-names.
#
# All changes are reversible with ./uninstall.sh:
#   1. registers a SessionStart hook, so every interactive session gets a name --
#      terminal, IDE extension, desktop app, web
#   2. points your statusLine at scripts/statusline.py, which shows the name and
#      then runs whatever statusline you already had
#   3. optionally sources scripts/shell-init.sh from your shell rc
#
# The shell rc is opt-in because the hook already names everything. What it buys
# is the one thing a hook cannot: Claude Code fixes a session's name in memory
# before any hook runs, so a hook-named session still signs its outgoing peer
# messages with the machine name it was born with. A name set in the environment
# before launch is set in time, so those envelopes read "Yuki" instead.
#
#   SHELL_RC=1        ./install.sh   # also wrap `claude` in your shell
#   WRAP_STATUSLINE=0 ./install.sh   # skip the statusline change
#   NO_HOOK=1         ./install.sh   # skip the hook (leaves nothing that names)
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
CFG="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
SETTINGS="$CFG/settings.json"
STATE="$CFG/agent-names"
MARK_BEGIN="# >>> claude-agent-names >>>"
MARK_END="# <<< claude-agent-names <<<"

[[ -d $CFG ]] || { echo "No Claude config at $CFG" >&2; exit 1; }
command -v python3 >/dev/null || { echo "python3 is required" >&2; exit 1; }

# A scoped CLAUDE_CONFIG_DIR means this is not the real user config -- a test
# install, a second profile, a container. Editing $HOME/.bashrc anyway would
# reach outside the scope the caller asked for, so don't.
scoped_config() { [[ -n ${CLAUDE_CONFIG_DIR:-} && $CLAUDE_CONFIG_DIR != "$HOME/.claude" ]]; }

mkdir -p "$STATE"

# --- naming hook ----------------------------------------------------------
# This is what actually names sessions. It runs wherever Claude Code runs, and
# writes the name into the session's peer file rather than returning
# `sessionTitle`, so your tab keeps saying what you are working on.
if [[ ${NO_HOOK:-0} != 1 ]]; then
    if [[ -f $SETTINGS ]]; then
        cp "$SETTINGS" "$SETTINGS.bak.agent-names-hook.$(date +%s)"
    else
        printf '{}' > "$SETTINGS"
    fi
    ROOT="$ROOT" SETTINGS="$SETTINGS" python3 <<'HOOKPY'
import json, os, shlex

root, settings_path = os.environ["ROOT"], os.environ["SETTINGS"]
script = f"{root}/hooks/session_start_name.py"
# Claude Code runs a command hook through a shell, so a checkout under
# "My Projects" would otherwise register a hook that cannot execute. Quoting is
# a no-op for ordinary paths, so normal installs look exactly as before.
command = shlex.quote(script)

with open(settings_path, encoding="utf-8") as fh:
    settings = json.load(fh)

groups = settings.setdefault("hooks", {}).setdefault("SessionStart", [])


KNOWN = {script, command}


def is_ours(entry):
    """Match on the program a command runs, however it was spelled.

    Installs before quoting wrote the path raw, so a checkout under
    "My Projects" left a command shlex cannot split back into that one path.
    Compare the raw string too, or an upgrade stacks a duplicate and uninstall
    removes neither.
    """
    raw = entry.get("command", "")
    if raw in KNOWN:
        return True
    try:
        parts = shlex.split(raw)
    except ValueError:
        return False
    return bool(parts) and parts[0] in KNOWN


# Re-running the installer must not stack duplicate hooks.
if any(is_ours(h) for g in groups for h in g.get("hooks", [])):
    print("SessionStart hook already registered")
else:
    groups.append({"hooks": [{"type": "command", "command": command, "timeout": 10}]})
    with open(settings_path, "w", encoding="utf-8") as fh:
        json.dump(settings, fh, indent=2)
    print("SessionStart hook registered")
HOOKPY
fi

# --- shell rc (opt-in) ----------------------------------------------------
if [[ ${SHELL_RC:-0} == 1 ]] && ! scoped_config; then
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
import json, os, shlex, shutil

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
    if cmd and cmd not in (wrapper, shlex.quote(wrapper)):
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
# Same reason as the hook: this string is run by a shell.
settings["statusLine"] = {"type": "command", "command": shlex.quote(wrapper),
                          "padding": padding}

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
if [[ ${SHELL_RC:-0} == 1 ]]; then
    echo "Done. Open a NEW terminal (or: source ~/.bashrc) so new sessions are"
    echo "named before Claude starts."
else
    echo "Done. New sessions are named by the hook -- nothing to reload."
    echo "Your shell rc was not touched. Run with SHELL_RC=1 if you also want"
    echo "outgoing peer messages to carry the name (see the README)."
fi
