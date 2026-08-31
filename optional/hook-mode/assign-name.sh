#!/usr/bin/env bash
# UserPromptSubmit hook: give this session a human name, once.
#
# Why UserPromptSubmit and not SessionStart: `sessionTitle` is only honoured on
# UserPromptSubmit, and it is the only hook output that rewrites the peer name
# other sessions address with SendMessage. SessionStart can return context but
# cannot rename. The cost is that a session stays unnamed until its first
# prompt, which is a feature: sessions you open and never use burn no names.
#
# This runs on EVERY prompt, so the already-named path must stay cheap and must
# never write anything to stdout.
set -uo pipefail
source "$(dirname -- "${BASH_SOURCE[0]}")/../../scripts/lib.sh"

payload=$(cat)
[[ -n $payload ]] || exit 0

sid=$(printf '%s' "$payload" | python3 -c \
  'import json,sys
try: print(json.load(sys.stdin).get("session_id","") or "")
except Exception: pass' 2>/dev/null)
[[ -n $sid ]] || exit 0

ensure_state || exit 0

# Only interactive sessions get human names. Background subagents already carry
# a descriptive task label ("Merge to main"), which beats a first name.
# Headless `claude -p` routines are not excluded: they report themselves as
# interactive, so this check lets them through and they do take a name.
record=$(peer_record "$sid") || exit 0
[[ -n $record ]] || exit 0
grep -q '"kind":"interactive"' "$record" 2>/dev/null || exit 0

# Respect a hand-set name: if you typed /rename, that wins forever.
grep -q '"nameSource":"user"' "$record" 2>/dev/null && exit 0

name=$(CAN_SESSION_ID="$sid" CAN_LIVE="$(live_session_ids)" \
       CAN_REGISTRY="$(registry_file)" CAN_NAMES="$(names_file)" \
       python3 "$(dirname -- "${BASH_SOURCE[0]}")/claim_name.py" 2>/dev/null)

# Empty output means "already named" (the common case) or a failure. Either way
# stay silent: a hook that prints junk corrupts the turn.
[[ -n $name ]] || exit 0

python3 - "$name" <<'PY'
import json, sys
name = sys.argv[1]
context = (
    f"Your name in this session is {name}. Other Claude Code sessions running on "
    f"this machine can see you as \"{name}\" in ListAgents and reach you with "
    f"SendMessage. When you reply to a peer session, identify yourself as {name} "
    f"so the conversation is readable. This is a label for addressing you; it "
    f"does not change how you work or who you are."
)
print(json.dumps({"hookSpecificOutput": {
    "hookEventName": "UserPromptSubmit",
    "sessionTitle": name,
    "additionalContext": context,
}}))
PY
exit 0
