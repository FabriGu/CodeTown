"""Read-only access to a git repository.

Only files git tracks are ever opened, symlinks are never followed, and git
runs with optional locks off so it does not even refresh its own index.
"""

import os
import subprocess

GIT_ENV = {"GIT_OPTIONAL_LOCKS": "0", "GIT_TERMINAL_PROMPT": "0"}
GIT_FLAGS = ["--no-pager", "-c", "core.fsmonitor=false", "-c", "core.untrackedCache=false",
             "-c", "core.quotepath=false"]
MAX_TEXT_BYTES = 1_000_000


class NotTracked(Exception):
    """Raised when asked to read a file git does not track."""


class Repo:
    def __init__(self, root):
        self.root = os.path.realpath(root)
        self._files = None
        self._tracked = set()

    def _git(self, *args):
        result = subprocess.run(["git", "-C", self.root, *GIT_FLAGS, *args],
                                check=True, capture_output=True,
                                env=dict(os.environ, **GIT_ENV))
        return result.stdout.decode("utf-8", errors="replace")

    def files(self):
        if self._files is None:
            self._files = sorted(p for p in self._git("ls-files", "-z").split("\0") if p)
            self._tracked = set(self._files)
        return self._files

    def read_text(self, rel):
        """Tracked file contents as text, or None if binary, huge, missing or a symlink."""
        self.files()
        if rel not in self._tracked:
            raise NotTracked(rel)
        path = os.path.join(self.root, rel)
        try:
            if os.path.islink(path) or os.path.getsize(path) > MAX_TEXT_BYTES:
                return None
            with open(path, "rb") as f:
                return f.read().decode("utf-8")
        except (OSError, UnicodeDecodeError):
            return None

    def churn(self, days=90):
        counts = {}
        out = self._git("log", f"--since={days}.days", "--no-renames", "--name-only", "--format=")
        for line in out.splitlines():
            if line.strip():
                counts[line] = counts.get(line, 0) + 1
        return counts

    def renames(self):
        """Old path -> the path it has now, following chains of renames to the end."""
        out = self._git("log", "--reverse", "-M", "--diff-filter=R", "--name-status",
                        "--format=")
        found = {}
        for line in out.splitlines():
            parts = line.split("\t")
            if len(parts) != 3 or not parts[0].startswith("R"):
                continue
            old, new = parts[1], parts[2]
            for earlier, now in found.items():
                if now == old:
                    found[earlier] = new
            found[old] = new
        return {old: new for old, new in sorted(found.items()) if old != new}
