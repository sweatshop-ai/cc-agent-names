#!/usr/bin/env python3
"""scripts/shell-init.sh, sourced from every shell that might source it.

Run: python3 tests/test_shell_init.py

This file exists because the shell wrapper is the one part of the plugin whose
correctness depends on which shell is reading it, and the project was only ever
run on bash. zsh is the default login shell on macOS, so the zsh branch is the
one most users take and the one least exercised here.

The failure this guards against is silent: a root that does not resolve leaves a
`claude` wrapper that shells out to "/scripts/pick_name.py", gets nothing back,
and starts Claude unnamed forever without printing anything. A test that only
checked "did the shell exit 0" would pass on that. So every case below asserts
on the name that actually reached the `claude` process.
"""
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INIT = os.path.join(ROOT, "scripts", "shell-init.sh")
failures = []


def check(label, condition, detail=""):
    print(f"{'ok  ' if condition else 'FAIL'} {label}{'' if condition else '  -- ' + detail}")
    if not condition:
        failures.append(label)


def source_and_run(shell, snippet, bindir, cfg, name=None):
    """Source shell-init.sh in `shell`, then run `snippet`.

    The environment is scrubbed of both variables the script sets, because the
    developer running these tests may well have the plugin wired into their own
    rc -- in which case an inherited value would make a broken script look fine.
    """
    env = dict(os.environ, PATH=bindir + os.pathsep + os.environ["PATH"],
               CLAUDE_CONFIG_DIR=cfg)
    env.pop("CLAUDE_AGENT_NAMES_ROOT", None)
    env.pop("CLAUDE_CODE_SESSION_NAME", None)
    if name is not None:
        env["CLAUDE_CODE_SESSION_NAME"] = name
    return subprocess.run([shell, "-c", f". {INIT}; {snippet}"], env=env,
                          capture_output=True, text=True, timeout=60)


with tempfile.TemporaryDirectory() as tmp:
    # A stand-in for the real CLI: it reports the name it was handed, so each
    # case can assert on what Claude would actually have been launched with.
    bindir = os.path.join(tmp, "bin")
    os.makedirs(bindir)
    fake = os.path.join(bindir, "claude")
    with open(fake, "w", encoding="utf-8") as fh:
        fh.write('#!/usr/bin/env bash\necho "NAME=${CLAUDE_CODE_SESSION_NAME:-}"\n')
    os.chmod(fake, 0o755)
    cfg = os.path.join(tmp, "cfg")
    os.makedirs(cfg)

    for shell in ("bash", "zsh"):
        if not shutil.which(shell):
            print(f"skip {shell} (not installed)")
            continue

        r = source_and_run(shell, 'printf "ROOT=%s\\n" "$CLAUDE_AGENT_NAMES_ROOT"',
                           bindir, cfg)
        check(f"{shell}: resolves the plugin root",
              f"ROOT={ROOT}" in r.stdout, repr(r.stdout) + repr(r.stderr))
        check(f"{shell}: sourcing is silent",
              r.stderr.strip() == "", repr(r.stderr))

        r = source_and_run(shell, "claude", bindir, cfg)
        got = next((l[5:] for l in r.stdout.splitlines() if l.startswith("NAME=")), "")
        check(f"{shell}: the wrapper names the session", bool(got),
              repr(r.stdout) + repr(r.stderr))

        # A name already in the environment is someone's deliberate choice --
        # a nested shell, or `CLAUDE_CODE_SESSION_NAME=x claude`. Never reroll it.
        r = source_and_run(shell, "claude", bindir, cfg, name="Giacomo")
        check(f"{shell}: an existing name passes through untouched",
              "NAME=Giacomo" in r.stdout, repr(r.stdout))

    # A shell that is neither bash nor zsh must not eat a syntax error on the
    # branch meant for the other one. dash is /bin/sh on Debian and Ubuntu, so
    # this is reachable by anyone who sources the file from the wrong place.
    if shutil.which("dash"):
        r = source_and_run("dash", "claude", bindir, cfg)
        check("dash: degrades with a warning, not a substitution error",
              "Bad substitution" not in r.stderr and "cc-agent-names:" in r.stderr,
              repr(r.stderr))
        check("dash: claude still starts", "NAME=" in r.stdout,
              repr(r.stdout) + repr(r.stderr))
    else:
        print("skip dash (not installed)")

print()
if failures:
    print(f"{len(failures)} failing: " + ", ".join(failures))
    raise SystemExit(1)
print("all passing")
