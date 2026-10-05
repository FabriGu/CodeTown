import fcntl
import os
import pty
import select
import shutil
import struct
import sys
import tempfile
import termios
import time
import unittest

import fixture
from test_survey import MONOREPO_LIKE

HERE = os.path.dirname(os.path.abspath(__file__))


def drain(fd, seconds):
    out = b""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        ready, _, _ = select.select([fd], [], [], 0.05)
        if ready:
            try:
                chunk = os.read(fd, 65536)
            except OSError:
                break
            if not chunk:
                break
            out += chunk
    return out


def wait_exit(pid, seconds):
    """The child's exit status, or None if it is still running after `seconds`."""
    deadline = time.monotonic() + seconds
    while True:
        done, status = os.waitpid(pid, os.WNOHANG)
        if done:
            return status
        if time.monotonic() >= deadline:
            return None
        time.sleep(0.02)


class SmokeTest(unittest.TestCase):
    def play(self, argv, keys, startup, per_key, env=None):
        """Run a program in a 120x40 terminal, press keys then q, and return what it drew."""
        pid, fd = pty.fork()
        if pid == 0:
            fcntl.ioctl(0, termios.TIOCSWINSZ, struct.pack("HHHH", 40, 120, 0, 0))
            os.environ["COLORTERM"] = "truecolor"
            os.environ.update(env or {})
            os.chdir(HERE)
            os.execv(sys.executable, [sys.executable, *argv])
        try:
            out = drain(fd, startup)
            for key in keys:
                os.write(fd, key)
                out += drain(fd, per_key)
            os.write(fd, b"q")
            out += drain(fd, 1.5)
            status = wait_exit(pid, 3.0)
            if status is None:
                os.kill(pid, 9)
                os.waitpid(pid, 0)
                self.fail(f"{argv[0]} did not exit after pressing q")
        finally:
            os.close(fd)
        text = out.decode("utf-8", errors="ignore")
        self.assertEqual(os.waitstatus_to_exitcode(status), 0, text[-500:])
        return text

    def test_game_draws_walks_talks_and_quits_cleanly(self):
        text = self.play(["town.py"], (b"d", b"d", b"\x1b[A", b"e"), startup=1.0, per_key=0.3)
        self.assertIn("\x1b[?1049h", text)
        self.assertIn("\u2588\u2588", text)
        self.assertIn("38;2;217;119;87", text)  # Clawd orange
        self.assertIn("\x1b[?1049l", text)
        self.assertIn("Thanks for visiting", text)

    def test_towncode_view_draws_jumps_inspects_zooms_and_quits_cleanly(self):
        root = fixture.make_repo(self, MONOREPO_LIKE)
        out_dir = tempfile.mkdtemp(prefix="towncode-out-")
        self.addCleanup(shutil.rmtree, out_dir)
        keys = (b"n", b"\r", b"d", b"\x1b[B", b"-", b"-", b"+")
        text = self.play(["towncode.py", "view", root], keys, startup=3.0, per_key=0.4,
                         env={"TOWNCODE_SURVEY_DIR": out_dir})
        self.assertIn("\x1b[?1049h", text)
        self.assertIn("\u2588\u2588", text)
        self.assertIn("problem 1 of", text)
        self.assertIn("\x1b[?1049l", text)
        self.assertIn("Saved to", text)


if __name__ == "__main__":
    unittest.main()
