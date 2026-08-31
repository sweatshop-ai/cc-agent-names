#!/usr/bin/env bash
# Shared helpers for cc-agent-names.

# Where Claude Code keeps its config. Honour CLAUDE_CONFIG_DIR like the CLI does.
cfg_dir() { printf '%s' "${CLAUDE_CONFIG_DIR:-$HOME/.claude}"; }

# Our own writable state lives beside Claude's config, never inside the plugin
# directory (which may be a read-only marketplace cache).
state_dir() { printf '%s' "$(cfg_dir)/agent-names"; }
registry_file() { printf '%s' "$(state_dir)/registry.json"; }
config_file() { printf '%s' "$(state_dir)/config.json"; }

# Root of this plugin, derived from the script location so nothing is hardcoded.
plugin_root() {
    printf '%s' "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
}

# The name pool: a user override wins over the bundled roster, so upgrading the
# plugin never overwrites a customised team.
names_file() {
    local override; override="$(state_dir)/names.txt"
    if [[ -s $override ]]; then printf '%s' "$override"
    else printf '%s' "$(plugin_root)/data/names.txt"; fi
}

ensure_state() {
    mkdir -p "$(state_dir)" 2>/dev/null || return 1
    [[ -f $(registry_file) ]] || printf '{}' > "$(registry_file)"
}

# A session is "live" iff Claude Code still has a peer record for it. Those pid
# files are written at startup and removed on exit, which makes them the
# authoritative liveness signal -- better than tracking pids ourselves.
live_session_ids() {
    local d; d="$(cfg_dir)/sessions"
    [[ -d $d ]] || return 0
    grep -ho '"sessionId":"[^"]*"' "$d"/*.json 2>/dev/null | cut -d'"' -f4
}

# Peer record for one session id, or nothing if it has none.
peer_record() {
    local sid=$1 d; d="$(cfg_dir)/sessions"
    [[ -d $d && -n $sid ]] || return 1
    grep -l "\"sessionId\":\"$sid\"" "$d"/*.json 2>/dev/null | head -1
}
