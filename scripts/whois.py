#!/usr/bin/env python3
"""Resolve a peer's real name from the address on its message.

A cross-session message arrives wrapped as

    <cross-session-message from="uds:/run/user/1000/cc-socks/1075452.sock"
                           from-name="cc-agent-names-de">

The `from-name` can be stale: Claude Code fixes a session's name in memory at
startup, so a session named after that -- by our SessionStart hook -- keeps
signing its envelopes with the machine name it was born with. The `from`
address does not go stale. It is the session's messaging socket, and every
session records that socket in its own peer file alongside its current name.

So the mapping is exact, not a guess: match the address, read the name.

    whois.py uds:/run/user/1000/cc-socks/1075452.sock   ->  Thea

Called with no argument it answers the same question about you, reading the peer
file for $CLAUDE_CODE_SESSION_ID. That file is the authority on your own name
too: it holds whatever you were given at startup, or the name you set later with
/rename, which the context injected at startup cannot know about.

Prints nothing if the address belongs to no live session.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import registry  # noqa: E402


def resolve(address):
    # Envelopes carry a `uds:` scheme; the peer file stores the bare path.
    sock = address[4:] if address.startswith("uds:") else address
    for rec in registry.live():
        if rec.get("messagingSocketPath") == sock:
            return rec.get("name") or ""
    return ""


def own_name():
    rec = registry.own()
    return (rec or {}).get("name") or ""


if __name__ == "__main__":
    name = resolve(sys.argv[1]) if len(sys.argv) > 1 else own_name()
    if name:
        print(name)
