#!/usr/bin/env python3
"""Names that must never be handed to a session -- a colleague's first name.

`~/.claude/agent-names/blocklist.txt`, one name per line, `#` comments and blank
lines skipped, same as names.txt. It is subtracted from whichever pool is
active, so the bundled roster keeps growing with upgrades while your colleagues
stay out of it. `CAN_BLOCKLIST` points somewhere else, as `CAN_NAMES` does for
the roster.

Matching is case-insensitive, and `Anna-2` is Anna's: blocking Anna blocks the
overflow names that hang off her too.
"""
import os
from pathlib import Path


def base_name(name):
    """The root a suffixed name hangs off: `Anna-2` is Anna's.

    Retiring Anna from names.txt, or blocking her, has to take Anna-2 with her,
    or a remembered name could outlive the list it came from.
    """
    root = name.rsplit("-", 1)
    if len(root) == 2 and root[1].isdigit():
        return root[0]
    return name


def load(cfg):
    """The blocked names, case-folded. A missing or unreadable file blocks nothing."""
    path = Path(os.environ.get("CAN_BLOCKLIST") or Path(cfg) / "agent-names" / "blocklist.txt")
    try:
        with path.open(encoding="utf-8") as fh:
            lines = [ln.strip() for ln in fh]
    except OSError:
        return set()
    return {ln.casefold() for ln in lines if ln and not ln.startswith("#")}


def is_blocked(name, blocked):
    name = (name or "").strip()
    return name.casefold() in blocked or base_name(name).casefold() in blocked
