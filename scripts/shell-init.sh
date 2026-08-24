# claude-agent-names -- give each new session a human name.
#
# Source this from your shell rc. It wraps `claude` so a name is chosen BEFORE
# the process starts, via CLAUDE_CODE_SESSION_NAME. That timing is the whole
# point: naming a session later (from a UserPromptSubmit hook) also overwrites
# the conversation title, costing you the topic name in your tab.
#
# Deliberately not `exec` -- your shell must survive Claude exiting.

# Resolved once, at source time, so the function stays path-independent.
if [ -n "${BASH_SOURCE[0]:-}" ]; then
    CLAUDE_AGENT_NAMES_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
elif [ -n "${(%):-%x}" ] 2>/dev/null; then
    CLAUDE_AGENT_NAMES_ROOT="$(cd -- "$(dirname -- "${(%):-%x}")/.." && pwd)"
fi
export CLAUDE_AGENT_NAMES_ROOT

claude() {
    # Already named (nested shell, or you set it yourself): don't touch it.
    if [ -n "${CLAUDE_CODE_SESSION_NAME:-}" ]; then
        command claude "$@"
        return
    fi
    local __name
    __name="$(python3 "${CLAUDE_AGENT_NAMES_ROOT}/scripts/pick_name.py" 2>/dev/null)"
    if [ -n "$__name" ]; then
        CLAUDE_CODE_SESSION_NAME="$__name" command claude "$@"
    else
        command claude "$@"   # naming must never block starting Claude
    fi
}
