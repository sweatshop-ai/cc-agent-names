#!/usr/bin/env python3
"""The status line shows a boss and a concierge with their role; the name stays bare.

Run: python3 tests/test_role_label.py

The label is for the owner's eyes. The peer record, which SendMessage and
ListAgents resolve names from, must never gain it. The concierge case runs a
private tmux server on its own TMUX_TMPDIR, with TMUX unset and `-t` on every
call, so it can never touch the server the owner is working in.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATUSLINE = ROOT / "scripts" / "statusline.py"
SID = "22222222-2222-2222-2222-222222222222"
ANSI = re.compile(r"\x1b\[[0-9;]*m")


class Label(unittest.TestCase):
    def setUp(self):
        self.cfg = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.cfg, True)
        (self.cfg / "sessions").mkdir()
        self.peer = self.cfg / "sessions" / "4242.json"
        self.peer.write_text(json.dumps({"sessionId": SID, "name": "Fatima", "nameSource": "assigned"}))

    def env(self, **extra):
        env = {k: v for k, v in os.environ.items() if k not in ("TMUX", "TMUX_PANE", "CLAUDE_CODE_SESSION_NAME")}
        env.update(CLAUDE_CONFIG_DIR=str(self.cfg), CLAUDE_CODE_SESSION_NAME="Fatima", AGENT_NAME_COLOR="off")
        env.update(extra)
        return env

    def line(self, **extra):
        r = subprocess.run([sys.executable, str(STATUSLINE)], input=json.dumps({"session_id": SID}),
                           capture_output=True, text=True, timeout=30, env=self.env(**extra))
        self.assertEqual(r.returncode, 0, r.stderr)
        return ANSI.sub("", r.stdout).strip()

    def mark(self):
        d = self.cfg / "pm" / ".boss-sessions"
        d.mkdir(parents=True)
        (d / SID).write_text("boss-efficiency\n")

    def test_a_plain_worker_reads_its_bare_name(self):
        self.assertEqual(self.line(), "Fatima")

    def test_a_registered_boss_reads_name_boss(self):
        self.mark()
        self.assertEqual(self.line(), "Fatima [boss]")

    def test_a_marker_that_is_a_symlink_is_no_boss(self):
        d = self.cfg / "pm" / ".boss-sessions"
        d.mkdir(parents=True)
        (d / SID).symlink_to(self.cfg / "elsewhere")
        self.assertEqual(self.line(), "Fatima")

    def test_a_label_never_reaches_the_peer_record(self):
        before = self.peer.read_text()
        self.mark()
        self.line()
        self.assertEqual(self.peer.read_text(), before)
        self.assertNotIn("[", json.loads(self.peer.read_text())["name"])

    def test_the_label_is_built_after_the_name_is_resolved(self):
        # session_name() is what hooks and the registry read; it stays bare.
        sys.path.insert(0, str(ROOT / "scripts"))
        import statusline
        self.mark()
        os.environ["CLAUDE_CONFIG_DIR"] = str(self.cfg)
        os.environ["CLAUDE_CODE_SESSION_NAME"] = "Fatima"
        try:
            self.assertEqual(statusline.session_name({"session_id": SID}), "Fatima")
            self.assertEqual(statusline.role_of({"session_id": SID}), "boss")
        finally:
            os.environ.pop("CLAUDE_CODE_SESSION_NAME", None)
            os.environ.pop("CLAUDE_CONFIG_DIR", None)

    @unittest.skipUnless(shutil.which("tmux"), "tmux not installed")
    def test_a_concierge_pane_reads_name_concierge_and_a_bare_pane_does_not(self):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, True)
        env = self.env(TMUX_TMPDIR=tmp)
        sh = Path(tmp) / "run.sh"
        sh.write_text('set -e\n'
                      'tmux -f /dev/null new-session -d -s t -x 80 -y 24 sleep 60\n'
                      'tmux display-message -p -t t:0.0 "#{socket_path}"\n'
                      'tmux display-message -p -t t:0.0 "#{pane_id}"\n')
        out = subprocess.run(["bash", str(sh)], capture_output=True, text=True, timeout=30, env=env)
        self.addCleanup(subprocess.run, ["tmux", "kill-server"], env=env, capture_output=True)
        self.assertEqual(out.returncode, 0, out.stderr)
        sock, pane = out.stdout.split()
        self.assertTrue(sock.startswith(tmp), "not the private server: " + sock)
        self.assertEqual(self.line(TMUX_TMPDIR=tmp, TMUX_PANE=pane), "Fatima")
        subprocess.run(["tmux", "set-option", "-p", "-t", pane, "@worker_role", "concierge"],
                       env=env, check=True, capture_output=True)
        self.assertEqual(self.line(TMUX_TMPDIR=tmp, TMUX_PANE=pane), "Fatima [concierge]")

    def test_a_pane_that_tmux_cannot_answer_reads_the_bare_name(self):
        self.assertEqual(self.line(TMUX_TMPDIR=str(self.cfg), TMUX_PANE="%99"), "Fatima")


if __name__ == "__main__":
    unittest.main()
