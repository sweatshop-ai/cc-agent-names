# claude-agent-names

Give every Claude Code session a human first name, shown in the statusline and
usable as the address other sessions send messages to.

```
Tomas │ Model: Opus 5 | Ctx: 70.4k | ⎇ master | (+1,-0)
```

Instead of `webapp-bc`, `backend-75` and `projects-16`, you get Tomas, Yuki and
Amir — so *"check that with Yuki"* means something precise, because `Yuki` is
the literal address `SendMessage` delivers to.

It also makes your statusline dramatically faster: **6.4s → 0.18s per render**
in the setup it was built against.

## Name and title are different things

This is the distinction the whole design turns on:

| | What it is | Where you see it |
|---|---|---|
| **Agent name** | Stable identity, fixed at launch | Statusline footer, `ListAgents`, `SendMessage` |
| **Conversation title** | What Claude thinks you're doing, rewritten as it learns | Tab / window label |

You want both: the tab should say *"Bootable USB stick for Ubuntu Studio"*,
while the footer says *Tomas*.

That rules out the obvious implementation. A `UserPromptSubmit` hook returning
`sessionTitle` does rename the session — but it sets the **title** too, so your
tabs stop telling you what you're working on. Instead this sets
`CLAUDE_CODE_SESSION_NAME` before Claude starts, which sets the name and leaves
the title alone.

## Install

```bash
git clone https://github.com/<you>/claude-agent-names.git
cd claude-agent-names
./install.sh
```

The installer backs up everything it touches, then:

1. sources `scripts/shell-init.sh` from your shell rc, wrapping `claude` so a
   free name is chosen before launch
2. points `statusLine` at `scripts/statusline.py`, which shows the name followed
   by whatever statusline you already had

```bash
WRAP_STATUSLINE=0 ./install.sh   # leave the statusline alone
NO_SHELL_RC=1     ./install.sh   # leave the shell rc alone
```

Open a new terminal and start Claude. Running sessions keep their current name.

`./uninstall.sh` reverses both, restoring your original statusline command and
leaving your rc byte-identical.

## Why it is faster

Two things were slow, and both are fixed:

- **`npx -y ccstatusline@latest` re-resolves the package on every render** —
  about 4.5s of pure overhead, paid per render, per open session. The installer
  repoints at a locally vendored copy.
- **ccstatusline is a 3MB bundle**; node spends over a second parsing it before
  drawing anything. So `statusline.py` renders the common widgets natively.

The fast renderer is held to a strict rule: it reproduces your ccstatusline
config **byte-for-byte**, or it refuses. Powerline mode, extra rows, an unknown
widget, a colour it hasn't confirmed — any of those and it silently runs the
real ccstatusline instead. Verified identical across clean, unstaged, staged,
mixed staged+modified, deleted-file and slashed-branch repository states.

| | per render |
|---|---|
| `npx -y ccstatusline@latest` | 6.4s |
| vendored copy via node | 3.3s |
| native fast renderer | **0.18s** |

Supported widgets: `model`, `context-length`, `git-branch`, `git-changes`,
`separator`. Anything else falls back automatically.

## How names are handed out

Names come from `data/names.txt` — 212 short, phonetically distinct first names
from a wide spread of languages, picked so "Yuki" is never misheard as "Yuri".

There is no registry to maintain. Claude Code already writes a peer file per
live session containing its name, so *"which names are taken"* is answered from
the system's own state: nothing to drift, nothing to clean up, and a crashed
session frees its name the moment its peer file disappears. A short-lived
reservation file covers the gap between choosing a name and Claude registering.

Run more sessions than you have names and you get `Yuki-2` rather than a
collision.

## Customising

Everything user-editable lives in `~/.claude/agent-names/`:

| File | Purpose |
|---|---|
| `names.txt` | Your own roster. Create it to override the bundled pool; upgrades never touch it. |
| `config.json` | `statusline` (inner command), `fast` (use the native renderer). |
| `reservations.json` | Machine-managed; safe to delete. |

Set `AGENT_NAME_BADGE` to put a prefix before the name (e.g. an emoji). Empty by
default — the same icon on every session adds nothing.

## Sessions this does not name

Only shells that source `shell-init.sh` are wrapped, so sessions started by an
IDE or another tool keep Claude's derived name. They remain addressable by it.

If you would rather name *every* session and can live without topic titles, see
[`optional/hook-mode/`](optional/hook-mode/README.md) for the hook-based
alternative and its trade-off.

## Requirements

Claude Code ≥ 2.1, `python3`, bash or zsh. Tested on Linux.

## License

MIT
