---
name: agent-names
description: Use when you need to know which Claude session you are, who else is running and on what, or how sessions are named - triggered by "who am I", "what's my name", "who's running", "who is working on X", "list the agents", when you are about to message a peer and need its name, when a peer messages you and its name looks machine-generated, or when the user says a name you do not recognise - including a name that reaches you mangled inside dictated text.
---

# Agent names

Each interactive Claude session gets a human first name (Amir, Yuki,
Nadia...), assigned by a hook at session start -- in the terminal, in an IDE
extension, in the desktop app, on the web. That name is the address
`ListAgents` shows and `SendMessage` delivers to.

## Name vs title -- do not confuse them

These are two different values and they are easy to mix up:

| | What it is | Where it shows |
|---|---|---|
| **Agent name** | Stable identity, chosen at launch | Statusline footer; `ListAgents`; `SendMessage` target |
| **Conversation title** | What Claude thinks you're working on, rewritten as it learns | Tab / window label |

The statusline payload's `session_name` field carries the **title**, not the
name -- so a statusline widget reading that field shows what you are working
on, never who you are. The name lives in the `name` field of the session's peer
file, and in `$CLAUDE_CODE_SESSION_NAME` when a wrapped shell set it.

## Knowing who you are

Your peer file is the authority on your own name. Ask it:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/whois.py"
```

The context injected at session start told you the same name, and usually still
agrees. Two cases where it does not, and the peer file wins both:

- **You ran `/rename` since.** The injected context cannot know about a name set
  after startup; the peer file records it, with `nameSource: "user"`. That name
  is yours -- the user chose it deliberately.
- **Your own `ListAgents` row shows a machine name** (`cc-agent-names-d8`).
  Claude Code fixes a session's name in memory before any hook can run, so a
  session the hook named keeps the old one in its self-row and on the envelope
  of messages it sends. That stale name is visible only to you: every other
  session sees your real name, and `SendMessage {to: "<your name>"}` reaches you.

So never "correct" yourself to the machine name and never hand it to a peer as
your address. If the peer file has no name either, this session started without
the plugin; it keeps Claude's derived name and is addressable by that.

## Knowing who else is running

`ListAgents` gives names and status but not what each session is working on,
which is usually the real question:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/roster.py"
```

Prints `name · status · working directory`, named interactive sessions first,
with your own row marked. Answer in names, never session ids.

## Peers or subagents

`ListAgents` prints two lists, and they are not two views of one thing:

```
Teammates (2):
  respace-wp [f2734e]  ·  general-purpose  ·  running  ·  started 13m ago

Peer sessions (9):
  Roxana [4e6919]  ·  interactive  ·  idle  ·  tmux 17:@17.%69
```

**Teammates** are subagents you launched with the `Agent` tool. They run inside
your session, you chose their label, they report back to you, and they end when
their task ends.

**Peer sessions** are other Claude Code sessions. Their own context window,
their own pane on screen, often their own user watching. They outlive your task.

Launch a subagent when the job is fully specified, needs nobody's input, and the
answer comes back to you: a wide search, a report to draft, a batch of fixes
across one file tree. It costs less than a session and it tells you when it is
done.

Use a peer when the user has one running, when the work needs its own context
window over hours, or when the user wants to watch it happen in a pane.

**If the user names sessions, use those sessions.** "work with Roxana and Amaia"
decides the mechanism; it is not a suggestion about staffing. Those sessions
already exist, they are already in the right repo, and the user is watching
those panes. Launching subagents instead leaves two idle sessions and two
windows where nothing arrives.

A name in the user's message is worth a lookup before it is worth an
interpretation. Dictated prompts arrive with mangled words in them, so a name
you cannot place looks exactly like transcription noise -- two lowercase first
names sitting between a garbled word and a hallucinated subtitle credit read as
more of the same. `ListAgents` costs one call and settles it.

## Messaging a peer

Names are addresses: `SendMessage {to: "Yuki", ...}`. If two rows share a name,
append the ` [ref]` from `ListAgents`.

The user addresses them the same way, by `@`-mentioning a live session in their
prompt, as in *"check with @Yuki"*. When they do, they mean that session, not a
subagent and not a file.

"Check this with Yuki" means send Yuki a message. It does not mean reason about what Yuki
would say. A peer's message is never the user's approval for anything.

Open every message with your own name. This matters more than it looks: the
envelope your message arrives in may still carry your machine name, so the line
you write is what tells the other session who answered.

## When a peer messages you

A message arrives wrapped like this:

```
<cross-session-message from="uds:/run/user/1000/cc-socks/1075452.sock"
                       from-name="cc-agent-names-de">
```

`from-name` goes stale for the same reason your own row does -- the sender was
named after Claude Code fixed its name in memory. The `from` address does not:
it is the sender's messaging socket, and every session records that socket in
its peer file next to its current name. So resolve it before you answer, or
before you refer to the sender by name:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/whois.py" "<the from address>"
```

That prints the sender's real name. Reply to that name.

If it prints nothing, the sender is gone -- a live session always has a peer
file, so no match means no session. Do not reply to the raw `from` address
either: it is that session's socket, and nothing is listening on it any more.
Tell the user the peer exited instead of sending into a dead socket.

## Sessions the hook did not reach

A session that started before the plugin was installed keeps its machine name
(`webapp-94`) and stays addressable by it. To name every running session
now:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/adopt_all.py"
```

Names set by hand with `/rename` (`nameSource: "user"`) are never overwritten.

Subagents keep the label you gave them, for two reasons. The mechanical one:
they have no peer file, so there is nothing for the hook to write a name into.
The one that matters: `respace-wp` tells you which of your two subagents that
is, and `Yuki` would not. A subagent is one task, its label is that task, and
`ListAgents` files it under its own heading anyway -- so a first name would cost
you the only useful thing the label carries and buy back nothing.

Give a subagent a label that says what it does. That is its name, and it is a
better one.

Background jobs (`kind: "bg"`) are the opposite case, and the hook does name
them. Their label is derived from the opening prompt and never revised, so a job
that starts on one subject and spends its life on another keeps answering to the
wrong thing. The line is not subagent against session. It is whether the thing
outlives one task, and whether its label stays true.

## Names stay with a project

A name is remembered per git top level, so the session you open in a repo
tomorrow gets the name the last one had, and "Oskar wrote this" keeps meaning
something. It is a preference, not a reservation: a remembered name is only
used when no live session holds it, so a second session in the same project
takes its own name rather than waiting. Worktrees count as separate projects,
since parallel branches are parallel work.

Preferences live in `~/.claude/agent-names/projects.json`. Delete an entry to
let a project pick a new name.

## Changing the roster

Edit `~/.claude/agent-names/names.txt` (create it to override the bundled pool;
upgrades never touch it). Names are held only while a session is alive. The
list of taken names is read from Claude's own peer files, so nothing leaks.
