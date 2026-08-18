#!/usr/bin/env bash
# Remove claude-agent-names: unwire the shell rc and restore your statusline.
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
CFG="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
SETTINGS="$CFG/settings.json"
STATE="$CFG/agent-names"
MARK_BEGIN="# >>> claude-agent-names >>>"
MARK_END="# <<< claude-agent-names <<<"

for rc in "$HOME/.bashrc" "$HOME/.zshrc"; do
    [[ -f $rc ]] || continue
    grep -qF "$MARK_BEGIN" "$rc" || continue
    cp "$rc" "$rc.bak.agent-names-uninstall.$(date +%s)"
    python3 - "$rc" "$MARK_BEGIN" "$MARK_END" <<'PY'
import sys
path, begin, end = sys.argv[1], sys.argv[2], sys.argv[3]
with open(path, encoding="utf-8") as fh:
    lines = fh.readlines()
out, skipping = [], False
for line in lines:
    if line.strip() == begin:
        skipping = True
        # Drop the blank line the installer added before the block.
        if out and out[-1].strip() == "":
            out.pop()
        continue
    if line.strip() == end:
        skipping = False
        continue
    if not skipping:
        out.append(line)
with open(path, "w", encoding="utf-8") as fh:
    fh.writelines(out)
PY
    echo "unwired $rc"
done

if [[ -f $SETTINGS ]]; then
    cp "$SETTINGS" "$SETTINGS.bak.agent-names-uninstall.$(date +%s)"
    ROOT="$ROOT" SETTINGS="$SETTINGS" STATE="$STATE" python3 <<'PY'
import json, os

root, settings_path, state = os.environ["ROOT"], os.environ["SETTINGS"], os.environ["STATE"]
wrapper = f"{root}/scripts/statusline.py"

with open(settings_path, encoding="utf-8") as fh:
    settings = json.load(fh)

# Remove hooks from older installs, and any hook-mode hooks pointing at us.
ours = {f'"{root}/hooks/assign-name.sh"', f'"{root}/hooks/release-name.sh"',
        f'"{root}/optional/hook-mode/assign-name.sh"',
        f'"{root}/optional/hook-mode/release-name.sh"'}
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

if isinstance(settings.get("statusLine"), dict) and settings["statusLine"].get("command") == wrapper:
    inner = ""
    try:
        with open(os.path.join(state, "config.json"), encoding="utf-8") as fh:
            saved = json.load(fh)
        # Prefer the command that was there before we optimised it.
        inner = saved.get("statusline_original") or saved.get("statusline", "")
    except (OSError, ValueError):
        pass
    if inner:
        settings["statusLine"] = {"type": "command", "command": inner,
                                  "padding": settings["statusLine"].get("padding", 0)}
        print(f"statusLine restored to: {inner}")
    else:
        settings.pop("statusLine", None)
        print("statusLine removed")

with open(settings_path, "w", encoding="utf-8") as fh:
    json.dump(settings, fh, indent=2)
PY
fi

echo "Done. State in $STATE was left in place -- delete it by hand if you want it gone."
