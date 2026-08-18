#!/usr/bin/env bash
# SessionEnd hook: hand the name back to the pool.
#
# Not strictly required -- claim_name.py reaps dead sessions anyway -- but
# releasing eagerly keeps `agent-names who` honest between sessions.
set -uo pipefail
source "$(dirname -- "${BASH_SOURCE[0]}")/../scripts/lib.sh"

payload=$(cat)
sid=$(printf '%s' "$payload" | python3 -c \
  'import json,sys
try: print(json.load(sys.stdin).get("session_id","") or "")
except Exception: pass' 2>/dev/null)
[[ -n $sid ]] || exit 0

reg=$(registry_file)
[[ -f $reg ]] || exit 0

CAN_SESSION_ID="$sid" CAN_REGISTRY="$reg" python3 - <<'PY' 2>/dev/null
import fcntl, json, os, sys
sid = os.environ["CAN_SESSION_ID"]
path = os.environ["CAN_REGISTRY"]
with open(path + ".lock", "a+") as lock:
    fcntl.flock(lock, fcntl.LOCK_EX)
    try:
        with open(path, encoding="utf-8") as fh:
            reg = json.load(fh)
    except (OSError, ValueError):
        sys.exit(0)
    if not isinstance(reg, dict) or sid not in reg:
        sys.exit(0)
    reg.pop(sid, None)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(reg, fh, indent=2, sort_keys=True)
    os.replace(tmp, path)
PY
exit 0
