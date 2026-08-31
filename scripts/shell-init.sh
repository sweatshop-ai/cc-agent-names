# claude-agent-names -- give each new session a human name.
#
# Source this from your shell rc. It wraps `claude` so a name is chosen BEFORE
# the process starts, via CLAUDE_CODE_SESSION_NAME. That timing is the whole
# point: naming a session later (from a UserPromptSubmit hook) also overwrites
# the conversation title, costing you the topic name in your tab.
#
# Deliberately not `exec` -- your shell must survive Claude exiting.

# Resolved once, at source time, so the function stays path-independent.
#
# There is no portable way to ask "what file am I?" from a sourced script, so
# each shell gets its own branch: %x is zsh's prompt escape for the file being
# executed, BASH_SOURCE is bash's array. Branch on the shell rather than on
# which variable happens to be set -- zsh returning empty for an unset bash
# array is an accident of its array semantics, not a promise. Neither test
# touches the other shell's syntax, which is what lets a third shell -- dash as
# /bin/sh, say -- fall through both branches to the guard below instead of
# dying on "Bad substitution" while expanding a condition meant for bash.
# (ZSH_VERSION and BASH_VERSION are shell variables, not exported, so a bash
# child of a zsh shell correctly sees only its own.)
if [ -n "${ZSH_VERSION:-}" ]; then
    CLAUDE_AGENT_NAMES_ROOT="$(cd -- "$(dirname -- "${(%):-%x}")/.." && pwd)"
elif [ -n "${BASH_VERSION:-}" ]; then
    CLAUDE_AGENT_NAMES_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
fi

# Naming must never stop `claude` from starting -- but it must not fail silently
# either. An unresolved root leaves a wrapper that shells out to
# "/scripts/pick_name.py", gets nothing, and starts Claude unnamed forever with
# no hint as to why. Say it once, and leave `claude` untouched, so the command
# behaves exactly as it would without this file.
if [ -z "${CLAUDE_AGENT_NAMES_ROOT:-}" ]; then
    printf '%s\n' "claude-agent-names: could not locate the plugin from this shell; sessions will not be named. Supported: bash, zsh." >&2
    return 0 2>/dev/null || exit 0
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
