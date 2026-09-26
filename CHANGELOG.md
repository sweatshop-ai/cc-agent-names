# Changelog

## 0.7.0

A name given to a session from outside the plugin is kept.

- **`agent-name set <session-id> <name>`**, on the PATH of every session.
  The boss named workers by writing the peer file itself, and the hook took a
  name that was not on the roster for Claude Code's own label: it was replaced
  on the next prompt. A roster name survived the prompt but not a resume,
  because only the hook's own pick was remembered. An assigned name is now
  remembered as such, left alone by the hook, and handed back on resume.
- **`agent-name get` and `agent-name forget`.** Other tools stop reading and
  writing `agent-names/sessions.json`; it is this plugin's own file.
- A name set with `/rename` is still never overwritten.

## 0.6.0

Only a live session holds a name, and every script reads Claude Code's session
registry the same way.

- **A name held by a leftover peer file is free again.** Claude Code does not
  always remove `sessions/<pid>.json` when a session ends, and a file was
  enough to keep its name taken. A session is now live only when its pid
  exists with the start time the file records (`procStart`), it is not a
  zombie, and a terminal session still has its terminal. A suspended (Ctrl-Z)
  session is live.
- **A resumed session is named in its own peer file.** A resume gets a new pid
  while the previous run's file can linger under the same session id; the hook
  wrote the name into whichever the directory listing met first, and the
  resumed session stayed unnamed.
- **`roster.py` marks your own session again.** It looked for
  `CLAUDE_SESSION_ID`, which Claude Code never sets.
- **`scripts/registry.py`** is the one reader of the registry: `live()`,
  `by_pid()`, `by_sid()`, `own()`, `transcript_of()`, and a CLI for shell
  scripts. agentview and claude-boss carry a vendored copy. `CONTEXT.md`
  defines the terms.
- **Removed `optional/hook-mode` and `scripts/lib.sh`**, the older hook path
  with its own `registry.json`. It could not run beside the main path.
  `uninstall.sh` still unwires an old registration of it.

## 0.5.0

The plugin moves to the sweatshop-ai org, and a session stops being renamed
mid-conversation.

- **The plugin lives at `sweatshop-ai/cc-agent-names` now.** The repo moved out
  of the `thinkingtoo` org, so the marketplace is named `sweatshop-ai` and the
  install line is `/plugin install agent-names@sweatshop-ai`. GitHub redirects
  the old URL, so existing clones and `git pull` keep working untouched. Anyone
  who added the marketplace under the old name has to add it again -- a
  marketplace name is an identifier, not a link, and nothing redirects it.
- **A session keeps one name for its whole life.** Claude Code rewrites the peer
  record on its own schedule, and a rewrite puts a derived name back, which made
  the session eligible for naming a second time. Nothing tied that second pick to
  the first, so it drew again at random and a session peers already knew by name
  began answering to another one. Across 2206 transcripts, 10 sessions had been
  told two or more names; one ran through four in four hours while a sibling
  session in the same project held the name that project remembers. What a
  session was called is now remembered by session id, ranked above project
  stickiness, and handed back on any later pick. It stays a preference -- a name
  a live session actually holds is still off limits.
- **Three other paths picked from scratch too.** `adopt_all.py` passed the
  session's directory but not its id. The statusline passed neither, so every
  render of a machine-named record was an independent draw. A session's own
  reservation also counted against it, which pushed it off the name it had just
  chosen when it was adopted twice inside the 30-second window; reservations now
  record who made them, and honour the older bare-timestamp format on the way in.
- **A session's own peer record no longer counts against it.** A `collision` or a
  re-derived label asks for a rename while the record still holds our name, and
  that name being in the taken set guaranteed the session was moved off it.
- `tests/test_naming.py` covers the five cases, driving the hook and the
  statusline across a session's whole life rather than a single firing.

- **The skill says which worker a job wants.** It covered naming and messaging
  sessions and said nothing about subagents, so a session with idle named peers
  could reasonably launch its own workers instead. A new *Peers or subagents*
  section puts the two `ListAgents` lists side by side, says when each is right,
  and makes the rule explicit: if the user names sessions, use those sessions.
- **The skill fires on a name it does not recognise.** Its triggers assumed you
  already knew you needed a peer's name. A name in the user's message is now one
  of them, dictated text included -- two first names buried in a garbled voice
  prompt read as transcription noise, which is when a `ListAgents` call is worth
  more than an interpretation.
- **One test says what gets a name.** A name is worth having when the thing
  outlives its opening task. A subagent never does, so its label is true for its
  whole life and a first name would only add a lookup; a session does, which is
  why its name has to survive the drift its title follows. `bg` jobs sit on the
  session side for the same reason. The skill and the README used to give the
  weaker reason -- that a task label says more than a first name -- and the
  README's version of it was wrong for `bg` jobs, which this plugin does name.

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
