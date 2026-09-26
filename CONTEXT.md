# Context

Terms this repo uses, and that agentview and claude-boss use the same way.

**Session registry** — the peer files Claude Code writes, one per running
session, at `$CLAUDE_CONFIG_DIR/sessions/<pid>.json`. They are named by pid,
not by session id, and are not always removed when a session ends.
`scripts/registry.py` is the only reader; agentview and claude-boss carry a
vendored copy of it.

**Live session** — a registry record whose pid exists, whose `/proc/<pid>/stat`
start time equals the record's `procStart`, that is not a zombie, and that —
when started from a terminal (`entrypoint: cli`) — still has a controlling
terminal. A suspended (Ctrl-Z) session is live. A record without `procStart`
is not.

**Name** — the `name` field of a registry record. This plugin picks it and
writes it; others read it, and set it only through `bin/agent-name`.

**Assigned name** — a name given to a session from outside the plugin
(`agent-name set`), by the boss or by agentview's restore. Remembered with
`assigned: true`; the hook never replaces it and a resume gives it back. It
need not be on the roster.
