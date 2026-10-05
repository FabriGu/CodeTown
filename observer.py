"""File observer for one worktree folder: size and mtime only, never opens files."""

import os
import subprocess

from repo import GIT_ENV, GIT_FLAGS


class Observer:
    def __init__(self, root):
        self.root = os.path.realpath(root)
        self._prev: dict[str, tuple[int, int]] | None = None

    def _listed(self):
        result = subprocess.run(
            ["git", "-C", self.root, *GIT_FLAGS, "ls-files", "-co", "--exclude-standard", "-z"],
            check=True, capture_output=True, env=dict(os.environ, **GIT_ENV))
        return [p for p in result.stdout.decode("utf-8", errors="replace").split("\0") if p]

    def _stat(self, rel):
        try:
            st = os.lstat(os.path.join(self.root, rel))
        except OSError:
            return None
        return st.st_size, st.st_mtime_ns

    def poll(self):
        now = {}
        for rel in self._listed():
            st = self._stat(rel)
            if st is not None:
                now[rel] = st
        if self._prev is None:
            self._prev = now
            return []
        events = []
        for rel in self._prev:
            if rel not in now:
                events.append(("delete", rel))
        for rel, st in now.items():
            if rel not in self._prev:
                events.append(("create", rel))
            elif self._prev[rel] != st:
                events.append(("edit", rel))
        self._prev = now
        return events
