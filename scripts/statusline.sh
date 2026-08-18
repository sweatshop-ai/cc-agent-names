#!/usr/bin/env bash
# Statusline wrapper: prepend the session's human name, then hand the untouched
# payload to whatever statusline you were already using.
#
# Claude Code puts `session_name` in the statusline stdin JSON, so no lookup is
# needed -- but stdin can only be read once, hence the buffer.
#
# Configure the inner command in ~/.claude/agent-names/config.json:
#     { "statusline": "npx -y ccstatusline@latest" }
# Omit it and you get a minimal built-in line instead.
set -uo pipefail
source "$(dirname -- "${BASH_SOURCE[0]}")/lib.sh"

payload=$(cat)

read -r -d '' _py <<'PY' || true
import json, os, sys
try:
    d = json.loads(sys.stdin.read() or "{}")
except ValueError:
    d = {}
name = d.get("session_name") or ""
model = (d.get("model") or {}).get("display_name") or ""
cwd = d.get("workspace", {}).get("current_dir") or d.get("cwd") or ""
print(name)
print(model)
print(os.path.basename(cwd))
PY
mapfile -t parts < <(printf '%s' "$payload" | python3 -c "$_py" 2>/dev/null)
name=${parts[0]:-}
model=${parts[1]:-}
dir=${parts[2]:-}

inner=""
cf=$(config_file)
if [[ -f $cf ]]; then
    inner=$(python3 -c \
      'import json,sys
try: print(json.load(open(sys.argv[1])).get("statusline","") or "")
except Exception: pass' "$cf" 2>/dev/null)
fi

badge=""
[[ -n $name ]] && badge="${AGENT_NAME_BADGE:-👤} ${name}"

if [[ -n $inner ]]; then
    # Feed the original payload through untouched, and prefix only the first
    # line so multi-line statuslines keep their shape.
    out=$(printf '%s' "$payload" | eval "$inner" 2>/dev/null)
    if [[ -z $badge ]]; then printf '%s\n' "$out"; exit 0; fi
    if [[ -z $out ]]; then printf '%s\n' "$badge"; exit 0; fi
    first=1
    while IFS= read -r line; do
        if (( first )); then printf '%s │ %s\n' "$badge" "$line"; first=0
        else printf '%s\n' "$line"; fi
    done <<< "$out"
    exit 0
fi

# No inner statusline configured: a small useful default.
line=""
[[ -n $badge ]] && line="$badge"
[[ -n $model ]] && line="${line:+$line │ }$model"
[[ -n $dir ]] && line="${line:+$line │ }$dir"
printf '%s\n' "$line"
