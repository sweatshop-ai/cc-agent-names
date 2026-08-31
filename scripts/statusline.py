#!/usr/bin/env python3
"""The statusline: the session's human name, then your usual statusline.

One process does everything -- parse the payload, read config, render, prefix --
because a statusline runs constantly and every extra interpreter startup is
~130ms of pure overhead paid on each render, in every open session.

Rendering strategy:
  * If "fast" is enabled, reproduce the ccstatusline config natively. That is
    ~10x quicker than loading ccstatusline's 3MB bundle, and is verified
    byte-for-byte against it.
  * If this config uses anything the fast renderer cannot reproduce exactly, run
    the real command from "statusline" instead. Slower is fine; different is not.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

NBSP = " "

# ccstatusline's 256-colour palette. Only entries confirmed against its real
# output are listed; an unlisted colour triggers fallback rather than a guess.
COLORS = {"cyan": 30, "brightBlack": 59, "magenta": 96, "yellow": 178}
SUPPORTED = {"model", "separator", "context-length", "git-branch", "git-changes"}


class Unsupported(Exception):
    """This config is beyond the fast renderer."""


def config_dir():
    return Path(os.environ.get("CLAUDE_CONFIG_DIR", str(Path.home() / ".claude")))


def load_our_config():
    try:
        with (config_dir() / "agent-names" / "config.json").open(encoding="utf-8") as fh:
            cfg = json.load(fh)
        return cfg if isinstance(cfg, dict) else {}
    except (OSError, ValueError):
        return {}


def load_ccstatusline_config():
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    try:
        with (Path(base) / "ccstatusline" / "settings.json").open(encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        raise Unsupported("no readable ccstatusline config")


def widgets_of(cfg):
    if cfg.get("powerline", {}).get("enabled"):
        raise Unsupported("powerline mode")
    if cfg.get("globalBold"):
        raise Unsupported("globalBold")
    if cfg.get("colorLevel") != 2:
        raise Unsupported("colorLevel is not 256-colour")
    lines = cfg.get("lines") or []
    if any(line for line in lines[1:]):
        raise Unsupported("more than one row")
    if not lines or not lines[0]:
        raise Unsupported("empty statusline")
    for w in lines[0]:
        if w.get("type") not in SUPPORTED:
            raise Unsupported(f"widget {w.get('type')!r}")
        if w.get("color") is not None and w["color"] not in COLORS:
            raise Unsupported(f"colour {w.get('color')!r}")
    return lines[0]


def git(args, cwd):
    try:
        r = subprocess.run(["git", *args], cwd=cwd, capture_output=True,
                           text=True, timeout=2)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout if r.returncode == 0 else None


def human_tokens(n):
    """55152 -> '55.2k', matching ccstatusline's formatting."""
    if n < 1000:
        return str(n)
    v = n / 1000
    return f"{v:.1f}k" if v < 1000 else f"{v / 1000:.1f}M"


def numstat_totals(chunks):
    added = removed = 0
    for chunk in chunks:
        for line in chunk.splitlines():
            parts = line.split("\t")
            if len(parts) >= 2:
                if parts[0].isdigit():
                    added += int(parts[0])
                if parts[1].isdigit():
                    removed += int(parts[1])
    return added, removed


def render_widget(w, data, cwd):
    kind = w.get("type")
    if kind == "separator":
        return f"{NBSP}|{NBSP}"

    if kind == "model":
        name = (data.get("model") or {}).get("display_name") or ""
        text = f"Model:{NBSP}" + name.replace(" ", NBSP)
    elif kind == "context-length":
        tokens = (data.get("context_window") or {}).get("total_input_tokens")
        if tokens is None:
            raise Unsupported("no context_window in payload")
        text = f"Ctx:{NBSP}{human_tokens(tokens)}"
    elif kind == "git-branch":
        branch = git(["rev-parse", "--abbrev-ref", "HEAD"], cwd)
        text = f"⎇{NBSP}no{NBSP}git" if branch is None \
            else f"⎇{NBSP}" + branch.strip().replace(" ", NBSP)
    elif kind == "git-changes":
        # Verified against ccstatusline: it sums the unstaged AND staged diffs.
        # `git diff HEAD` nets them out instead, giving a different number
        # whenever a file is staged and then modified again.
        unstaged = git(["diff", "--numstat"], cwd)
        staged = git(["diff", "--cached", "--numstat"], cwd)
        if unstaged is None or staged is None:
            text = f"(no{NBSP}git)"
        else:
            added, removed = numstat_totals((unstaged, staged))
            text = f"(+{added},-{removed})"
    else:
        raise Unsupported(kind)

    color = w.get("color")
    return text if color is None else f"\x1b[38;5;{COLORS[color]}m{text}\x1b[39m"


def fast_render(data):
    widgets = widgets_of(load_ccstatusline_config())
    cwd = (data.get("workspace") or {}).get("current_dir") or data.get("cwd") or "."
    parts = [render_widget(w, data, cwd) for w in widgets]
    return "\x1b[0m" + "".join(parts)


def peer_record(sid):
    """(path, record) for this session's peer file, or (None, None)."""
    sessions = config_dir() / "sessions"
    if not sid or not sessions.is_dir():
        return None, None
    for path in sessions.glob("*.json"):
        try:
            with path.open(encoding="utf-8") as fh:
                rec = json.load(fh)
        except (OSError, ValueError):
            continue
        if isinstance(rec, dict) and rec.get("sessionId") == sid:
            return path, rec
    return None, None


def adopt(path, rec):
    """Give a machine-named session a human name, in place.

    Claude Code re-reads this file when it updates status, so a name written
    here sticks and `SendMessage` starts resolving it immediately -- which is
    how sessions that started before this was installed, or outside a wrapped
    shell, get named without being restarted.

    Only `derived`/`auto`/`collision` names are replaced. A name you set with
    /rename reports `nameSource: "user"` and is never touched.
    """
    if rec.get("nameSource") not in ("derived", "auto", "collision"):
        return ""
    try:
        chosen = subprocess.run(
            [sys.executable, str(Path(__file__).resolve().parent / "pick_name.py")],
            capture_output=True, text=True, timeout=5,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""
    if not chosen:
        return ""
    try:
        # Re-read: Claude may have rewritten status since we looked.
        with path.open(encoding="utf-8") as fh:
            fresh = json.load(fh)
        if fresh.get("nameSource") not in ("derived", "auto", "collision"):
            return fresh.get("name") or ""
        fresh["name"] = chosen
        fresh.pop("nameSource", None)
        tmp = path.with_suffix(".json.agent-names-tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            json.dump(fresh, fh)
        os.replace(tmp, path)          # atomic: never a half-written peer file
    except (OSError, ValueError):
        return ""
    return chosen


def session_name(data):
    """The session's agent name -- NOT the payload's `session_name`.

    Those are different things: the payload field carries the *conversation
    title*, which Claude rewrites as it works out what you are doing ("Bootable
    USB stick for Ubuntu Studio"). The agent name is the stable identity other
    sessions address with SendMessage.
    """
    name = os.environ.get("CLAUDE_CODE_SESSION_NAME", "").strip()
    if name:
        return name

    # Started outside a wrapped shell: read, and adopt if still machine-named.
    path, rec = peer_record(data.get("session_id"))
    if not rec:
        return ""
    if rec.get("nameSource") in ("derived", "auto", "collision"):
        return adopt(path, rec)
    found = rec.get("name") or ""
    # Don't echo the conversation title back at the user.
    return "" if found == data.get("session_name") else found


def run_inner(command, payload):
    try:
        r = subprocess.run(command, shell=True, input=payload, capture_output=True,
                           text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return ""
    return r.stdout.rstrip("\n")


def main():
    payload = sys.stdin.read()
    try:
        data = json.loads(payload or "{}")
    except ValueError:
        data = {}

    cfg = load_our_config()
    body = ""

    if cfg.get("fast"):
        try:
            body = fast_render(data)
        except Unsupported:
            body = ""
        except Exception:
            body = ""

    if not body and cfg.get("statusline"):
        body = run_inner(cfg["statusline"], payload)

    name = session_name(data)
    badge = os.environ.get("AGENT_NAME_BADGE", "")
    label = f"{badge} {name}".strip() if name else ""
    # The name is the one thing on this line that is an identity rather than a
    # reading, so it should not be the dimmest thing on it. Bold, and bright
    # white unless told otherwise -- next to ccstatusline's yellows and cyans a
    # plain-weight grey name loses every time, which is backwards.
    if label:
        colour = os.environ.get("AGENT_NAME_COLOR", "1;97")
        label = f"\033[{colour}m{label}\033[0m" if colour != "off" else label

    if not label:
        print(body)
        return
    if not body:
        print(label)
        return

    # Prefix only the first row, so multi-row statuslines keep their shape.
    rows = body.split("\n")
    rows[0] = f"{label} │ {rows[0]}"
    print("\n".join(rows))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        sys.exit(0)  # never break someone's statusline
