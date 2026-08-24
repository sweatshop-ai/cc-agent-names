# Changelog

## 0.4.0

Sessions are named by a `SessionStart` hook instead of a shell wrapper, and a
name now stays with a project.

- **Named everywhere.** The hook ships inside the plugin and fires wherever
  Claude Code runs: terminal, IDE extensions, the desktop app, the web. The
  installer no longer edits your shell rc unless you ask it to (`SHELL_RC=1`),
  and the hook path works on Windows.
- **The session knows its own name.** It arrives as injected context, so a
  session answers "what's your name" and signs its replies to peers, instead of
  only appearing in a statusline it cannot read.
- **Names stay with a project.** Remembered per git top level, so "Oskar wrote
  this" survives a restart. A preference, never a reservation: a remembered name
  is only handed out when no live session holds it.
- **`scripts/whois.py`** resolves a peer's real name from the address on its
  message, and its own name when called with no argument.
- The bundled skill teaches both: resolve an incoming sender, and trust the peer
  file over a stale self-row.

Known limit: Claude Code fixes a session's name in memory at startup, before any
hook can run, so a hook-named session still shows the machine name in its *own*
`ListAgents` row and on the envelope of messages it sends. Peers see the real
name. The optional shell wrapper closes that last gap.

## 0.3.0

- Name sessions that are already running, in place, without restarting them.
- Name sessions at launch via `CLAUDE_CODE_SESSION_NAME`, leaving the
  conversation title alone.
- Native statusline renderer: 0.18s per render, falling back to ccstatusline
  whenever it cannot reproduce your config byte-for-byte.
