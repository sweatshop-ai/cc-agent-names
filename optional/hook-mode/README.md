# Hook mode (opt-in, with a real cost)

The default setup names sessions from a shell wrapper, before Claude starts.
That leaves Claude's own conversation titles alone, so your tab keeps saying
what you're working on.

These scripts implement the alternative: a `UserPromptSubmit` hook that names a
session on its first prompt.

**The trade-off:** the only hook output that can rename a session is
`sessionTitle`, and it sets the conversation title *as well as* the peer name.
So your tab stops showing the topic ("USB stick bootable Ubuntu Studio setup")
and shows the agent's name instead ("Jonas"). For most people that is a bad
trade, which is why this is not the default.

**When it is still worth it:** hook mode names *every* interactive session,
including ones you didn't launch from your shell: started by an IDE, by a
supervisor process, or by another tool. The shell wrapper cannot reach those.

To use it, register the hooks in `~/.claude/settings.json` yourself:

```json
{
  "hooks": {
    "UserPromptSubmit": [
      {"hooks": [{"type": "command", "command": "/path/to/optional/hook-mode/assign-name.sh"}]}
    ],
    "SessionEnd": [
      {"hooks": [{"type": "command", "command": "/path/to/optional/hook-mode/release-name.sh", "async": true}]}
    ]
  }
}
```

Note these scripts use the older session-id registry
(`~/.claude/agent-names/registry.json`), not the reservation file the shell
wrapper uses. Running both modes at once is not supported.
