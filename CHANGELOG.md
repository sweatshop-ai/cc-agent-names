# Changelog

## Unreleased

- **The skill says which worker a job wants.** It covered naming and messaging
  sessions and said nothing about subagents, so a session with idle named peers
  could reasonably launch its own workers instead. A new *Peers or subagents*
  section puts the two `ListAgents` lists side by side, says when each is right,
  and makes the rule explicit: if the user names sessions, use those sessions.
- **The skill fires on a name it does not recognise.** Its triggers assumed you
  already knew you needed a peer's name. A name in the user's message is now one
  of them, dictated text included -- two first names buried in a garbled voice
  prompt read as transcription noise, which is exactly when a `ListAgents` call
  is worth more than an interpretation.
- **Why subagents keep their labels, honestly.** The old line said a task label
  says more than a first name. True, and not the whole reason: subagents have no
  peer file for the hook to write into, and `ListAgents` already lists them
  under their own heading. The contrast with `bg` jobs -- which *are* named,
  because their label goes stale -- is now stated where it belongs.

- **The shell wrapper picks its branch by shell, not by guesswork.** It tested
  `BASH_SOURCE` to decide whether it was in bash, which worked but leaned on
  zsh happening to return empty for an unset bash array. It now reads
  `ZSH_VERSION` / `BASH_VERSION`. Behaviour in bash and zsh is unchanged --
  verified under bash 5.2 and zsh 5.9.
- **Sourcing from a third shell no longer dies on `Bad substitution`.** dash is
  `/bin/sh` on Debian and Ubuntu, and the old bash test was a parse error there,
  which aborted the file before its own fallback could run. Unrecognised shells
  now get one line on stderr and an untouched `claude`.
- **An unresolvable plugin root says so.** It used to export an empty root and
  leave a wrapper that started every session unnamed, silently, forever.
- `tests/test_shell_init.py` covers all of the above, per shell, asserting on
  the name that actually reached the `claude` process.

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
