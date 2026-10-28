#!/usr/bin/env python3
"""Work areas: a client folder or a repo family, each with a small roster.

`$CLAUDE_CONFIG_DIR/agent-names/areas.json` (or the file `CAN_AREAS` names):

    {"areas": {
      "thinkingtoo/klium": {"paths": ["~/Projects/thinkingtoo*/clients/klium"],
                            "roster": ["Dmitri", "Leila", "Tomas"]}
    }}

A session belongs to an area when its directory is a path glob of the area or
lies anywhere under one. A glob is matched one path component at a time, so `*`
never crosses a `/`: `~/Projects/thinkingtoo*` covers the main checkout and
every `thinkingtoo-wt-*` worktree beside it, and everything below them. When
several areas match, the one whose glob has the most components wins, so a
client folder beats the repo family it lives in.

A path no area matches is named the way it always was, per project. Without an
areas.json nothing changes at all.
"""
import fnmatch
import json
import os
import re
from pathlib import Path


def path_of(state):
    """Where areas.json lives: `CAN_AREAS`, like `CAN_NAMES`, can point elsewhere."""
    return Path(os.environ.get("CAN_AREAS") or (Path(state) / "areas.json"))


def load_raw(path):
    try:
        with Path(path).open(encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def load(path):
    """Area name -> {"paths": [...], "roster": [...]}, with malformed entries dropped."""
    areas = load_raw(path).get("areas")
    if not isinstance(areas, dict):
        return {}
    out = {}
    for name, area in areas.items():
        if not isinstance(area, dict):
            continue
        paths = [p for p in area.get("paths") or [] if isinstance(p, str) and p]
        roster = [n for n in area.get("roster") or [] if isinstance(n, str) and n.strip()]
        if paths:
            out[name] = {"paths": paths, "roster": [n.strip() for n in roster]}
    return out


def _parts(path):
    return [p for p in os.path.normpath(path).split(os.sep) if p]


def _covers(pattern, cwd_parts):
    """The number of components of a glob that covers cwd, or 0."""
    pat = _parts(os.path.expanduser(pattern))
    if not os.path.isabs(os.path.expanduser(pattern)) or len(pat) > len(cwd_parts):
        return 0
    if all(fnmatch.fnmatchcase(c, p) for c, p in zip(cwd_parts, pat)):
        return len(pat)
    return 0


def match(cwd, areas):
    """(name, area) of the deepest area covering cwd, or (None, None)."""
    cwd_parts = _parts(os.path.abspath(cwd))
    best, depth = (None, None), 0
    for name, area in areas.items():
        d = max((_covers(p, cwd_parts) for p in area["paths"]), default=0)
        if d > depth:
            best, depth = (name, area), d
    return best


def names(areas):
    """Every name some area's roster holds."""
    return {n for area in areas.values() for n in area["roster"]}


def names_in(state):
    """Every area roster name of the areas.json in this state directory.

    A job's label carries no nameSource, so the hook and adopt_all know a name
    is the plugin's own only by finding it among the names it hands out; an
    area's names are among them even when names.txt does not have them.
    """
    return names(load(path_of(state)))


def grow(path, area_name, name):
    """Add a name to an area's roster for good, keeping the rest of the file as it is.

    The caller holds the picker's lock.
    """
    path = Path(path)
    data = load_raw(path)
    area = (data.get("areas") or {}).get(area_name)
    if not isinstance(area, dict):
        return
    roster = area.setdefault("roster", [])
    if name in roster:
        return
    roster.append(name)
    tmp = path.with_suffix(".tmp")
    try:
        with tmp.open("w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=1, ensure_ascii=False)
            fh.write("\n")
        os.replace(tmp, path)
    except OSError:
        pass


# --- a first areas.json, proposed from projects.json --------------------------

SCRATCHPAD = re.compile(r"^/tmp/claude-\d+/([^/]+)/[0-9a-f-]{36}/scratchpad(/|$)")
ROSTER_SIZE = 3


def _encode(path):
    # How Claude Code files a directory: every non-alphanumeric becomes a dash.
    return re.sub(r"[^a-zA-Z0-9]", "-", path)


def _family_root(path, keys):
    """The main checkout a worktree belongs to, or the path itself.

    Three layouts are recognised: `X/.claude/worktrees/<n>`, `X-wt` and
    `X-wt/<n>`, and a sibling `X-<anything>` when `X` itself is a project. They
    are followed to the end, so `X-wt-160` and `X-mira-libmcp` reach `X`.
    """
    for _ in range(16):              # each step shortens the path; 16 is ample
        root = _one_up(path, keys)
        if root == path:
            break
        path = root
    return path


def _one_up(path, keys):
    if "/.claude/worktrees/" in path:
        return path.split("/.claude/worktrees/")[0]
    parent, base = os.path.split(path)
    grand, pbase = os.path.split(parent)
    if pbase.endswith("-wt"):
        return os.path.join(grand, pbase[:-3])
    if base.endswith("-wt"):
        return os.path.join(parent, base[:-3])
    best = ""
    for key in keys:
        kparent, kbase = os.path.split(key)
        if kparent == parent and base.startswith(kbase + "-") and len(kbase) > len(best):
            best = kbase
    return os.path.join(parent, best) if best else path


def _subfolder(root, rest):
    """The folder under root whose dashed spelling is `rest`, or None."""
    tokens = rest.split("-")
    if not rest or len(tokens) > 8:
        return None
    found = None
    for cuts in range(1 << (len(tokens) - 1)):
        parts, word = [], tokens[0]
        for i, tok in enumerate(tokens[1:]):
            if cuts >> i & 1:
                parts.append(word)
                word = tok
            else:
                word += "-" + tok
        parts.append(word)
        if os.path.isdir(os.path.join(root, *parts)):
            if found is None or len(parts) > len(found):
                found = parts
    return "/".join(found) if found else None


def propose(projects, home=None):
    """An areas.json proposal from projects.json; projects.json is only read.

    A repo family -- a main checkout with the worktrees beside it -- becomes an
    area when it has more than one checkout. A client folder becomes an area
    when a session's scratchpad shows it was worked in. A roster takes the main
    checkout's name first, then the most recent, three at most, and never a
    name an earlier area took. Everything else stays named per project.
    """
    home = os.path.normpath(home or os.path.expanduser("~"))

    def tilde(path):
        return "~" + path[len(home):] if path == home or path.startswith(home + "/") else path

    named = {k: v for k, v in projects.items() if isinstance(v, dict) and v.get("name")}
    keys = [k for k in named if k.startswith(home + "/") and not SCRATCHPAD.match(k)]

    families = {}
    for key in keys:
        families.setdefault(_family_root(key, keys), []).append(key)

    def area_name(path):
        rel = tilde(path)[2:]
        return rel[len("Projects/"):] if rel.startswith("Projects/") else rel

    taken_by_areas = set()

    def crew(members, first=None):
        """Up to three names these checkouts carry, none an earlier area took."""
        order = sorted(members, key=lambda k: -(named[k].get("last_used") or 0))
        if first in named:
            order = [first] + [k for k in order if k != first]
        out = []
        for key in order:
            name = named[key]["name"]
            if name not in out and name not in taken_by_areas:
                out.append(name)
        return out[:ROSTER_SIZE]

    # Client folders, from the scratchpads of sessions that ran in one.
    exact = {_encode(k) for k in keys}
    roots = sorted(set(families) | set(keys), key=len, reverse=True)
    clients = {}
    for key in named:
        m = SCRATCHPAD.match(key)
        if not m or m.group(1) in exact:
            continue
        for root in roots:
            prefix = _encode(root) + "-"
            if m.group(1).startswith(prefix):
                sub = _subfolder(root, m.group(1)[len(prefix):])
                if sub:
                    clients.setdefault((_family_root(root, keys), sub), []).append(key)
                    break

    out, covered = {}, 0
    for root in sorted(set(families) | {r for r, _ in clients}):
        members = families.get(root, [])
        if len(members) > 1:
            names_of = crew(members, root)
            out[area_name(root)] = {"paths": [tilde(root), tilde(root) + "-*"],
                                    "roster": names_of}
            taken_by_areas.update(names_of)
            covered += len(members)
        for (croot, sub), seen in sorted(clients.items()):
            if croot != root:
                continue
            names_of = crew(seen)
            if names_of:
                out[f"{area_name(root)}/{sub}"] = {
                    "paths": [f"{tilde(root)}/{sub}", f"{tilde(root)}-*/{sub}"],
                    "roster": names_of}
                taken_by_areas.update(names_of)
    return out, covered
