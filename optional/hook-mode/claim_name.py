#!/usr/bin/env python3
"""Claim a human name for one session, atomically.

Prints the claimed name on stdout, or nothing at all if this session already
has one. Silence is the common case: the hook runs on every prompt.

Concurrency matters here -- sixteen sessions can submit prompts in the same
second and must not all be handed "Amir". The registry is guarded by an
exclusive flock held across the whole read-modify-write.
"""
import fcntl
import json
import os
import random
import sys

session_id = os.environ.get("CAN_SESSION_ID", "").strip()
registry_path = os.environ.get("CAN_REGISTRY", "")
names_path = os.environ.get("CAN_NAMES", "")
live = {s for s in os.environ.get("CAN_LIVE", "").split() if s}

if not (session_id and registry_path and names_path):
    sys.exit(0)


def load_pool(path):
    names = []
    seen = set()
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            name = line.strip()
            if not name or name.startswith("#") or name in seen:
                continue
            seen.add(name)
            names.append(name)
    return names


lock_path = registry_path + ".lock"
with open(lock_path, "a+") as lock:
    fcntl.flock(lock, fcntl.LOCK_EX)

    try:
        with open(registry_path, encoding="utf-8") as fh:
            registry = json.load(fh)
        if not isinstance(registry, dict):
            registry = {}
    except (OSError, ValueError):
        registry = {}

    if session_id in registry:
        sys.exit(0)  # already named; say nothing

    # Reap names whose session is gone. `live` is derived from Claude's own peer
    # files, so a crashed session releases its name on the next claim rather
    # than leaking it forever.
    if live:
        registry = {sid: n for sid, n in registry.items() if sid in live}

    try:
        pool = load_pool(names_path)
    except OSError:
        sys.exit(0)
    if not pool:
        sys.exit(0)

    taken = set(registry.values())
    free = [n for n in pool if n not in taken]

    if free:
        # Deterministic per session, so the same session claiming twice after a
        # registry wipe tends to land on the same name.
        chosen = random.Random(session_id).choice(free)
    else:
        # Pool exhausted: more live sessions than names. Suffix rather than
        # collide, and tell the user to grow the roster.
        base = random.Random(session_id).choice(pool)
        n = 2
        while f"{base}-{n}" in taken:
            n += 1
        chosen = f"{base}-{n}"

    registry[session_id] = chosen

    tmp = registry_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(registry, fh, indent=2, sort_keys=True)
    os.replace(tmp, registry_path)

print(chosen)
