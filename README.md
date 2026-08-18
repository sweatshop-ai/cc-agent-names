# claude-agent-names

Give every Claude Code session a human first name — shown in the statusline, and
usable as the address other sessions send messages to.

```
👤 Yuki │ Model: Opus 5 | Ctx: 42k | ⎇ dev | (+3,-1)
```

Instead of `webapp-bc`, `backend-75` and `projects-16`, you get Yuki, Amir and
Nadia. You can then say *"check that with Yuki"* and mean something precise,
because `Yuki` is the literal address `SendMessage` delivers to.

## Why this works

Claude Code already names every session — it derives something like
`projects-16` from the working directory, and that string is what `ListAgents`
shows and `SendMessage` targets. This plugin replaces the derived name with a
human one, using two facts about the CLI:

- A `UserPromptSubmit` hook that returns `sessionTitle` **rewrites the peer
  name**, not just the conversation title.
- The statusline's stdin JSON carries `session_name`, so rendering it needs no
  lookup.

Nothing is monkey-patched and no launch wrapper is needed. It works for sessions
started from the terminal, from the IDE, or by another tool.

## Install

```bash
git clone https://github.com/<you>/claude-agent-names.git
cd claude-agent-names
./install.sh
```

The installer backs up `~/.claude/settings.json` first, adds two hooks, and
wraps whatever statusline you already use so your existing display is preserved
with the name prepended. To leave your statusline alone:

```bash
WRAP_STATUSLINE=0 ./install.sh
```

Open a new session and send it any prompt — it claims a name on first use.
Sessions already running keep their current name until restarted.

To remove everything, including restoring your original statusline:

```bash
./uninstall.sh
```

## How names are handed out

Names come from `data/names.txt` — 212 short, phonetically distinct first names
from a wide spread of languages, chosen so "Yuki" is never misheard as "Yuri".

- A name is claimed on a session's **first prompt** and released when it ends.
- Claims are guarded by an exclusive lock, so twenty sessions starting at once
  get twenty different names.
- A session that dies without cleaning up has its name reaped on the next claim,
  using Claude's own peer files as the liveness signal.
- If you run more sessions than you have names, you get `Yuki-2` rather than a
  collision. Add more names if you see that.

## What does *not* get a name

- **Background subagents** keep their task label (`Merge to main`) — more useful
  than a first name.
- **Headless `claude -p` runs** — cron jobs and systemd timers — are skipped, so
  automation doesn't churn through the pool.
- **Sessions that never receive a prompt** stay unnamed.

## Customising

Everything user-editable lives in `~/.claude/agent-names/`:

| File | Purpose |
|---|---|
| `names.txt` | Your own roster. Create it to override the bundled pool; upgrades never touch it. |
| `config.json` | `{"statusline": "<your statusline command>"}` — run inside the wrapper. |
| `registry.json` | Live session → name. Machine-managed; safe to delete. |

Set `AGENT_NAME_BADGE` to change the `👤` prefix, or to an empty string to drop it.

To rename a session by hand, use Claude Code's own `/rename <name>`. A hand-set
name is respected permanently — the hook checks `nameSource` and never
overrides it.

## Requirements

Claude Code ≥ 2.1, `python3`, and a POSIX shell. Tested on Linux.

## License

MIT
