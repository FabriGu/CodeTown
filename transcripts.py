"""Tail Cursor/Claude transcripts and match subagents to worktrees."""

import glob
import json
import os

import session
from events import Agent


class WorktreePaths:
    """Realpath cache for repo and worktree roots; refreshed on worktree list changes."""

    def __init__(self, repo_root, worktrees):
        self.repo_root = os.path.realpath(repo_root)
        self.wt_roots = {w.name: os.path.realpath(w.path) for w in worktrees}
        self._path_cache: dict[str, str] = {}

    def realpath(self, path):
        if path not in self._path_cache:
            if os.path.isabs(path):
                full = path
            else:
                full = os.path.join(self.repo_root, path)
            self._path_cache[path] = os.path.realpath(full)
        return self._path_cache[path]

    def _inside(self, full, root):
        return full == root or full.startswith(root + os.sep)

    def worktree_for_path(self, path):
        full = self.realpath(path)
        for name, wt_path in self.wt_roots.items():
            if wt_path != self.repo_root and self._inside(full, wt_path) and full != wt_path:
                return name
        return None

    def in_repo_or_worktree(self, path):
        full = self.realpath(path)
        if self._inside(full, self.repo_root):
            return True
        for wt_path in self.wt_roots.values():
            if self._inside(full, wt_path):
                return True
        return False

    def rel_for_worktree(self, path):
        if path is None:
            return None
        full = self.realpath(path)
        for name, wt_path in self.wt_roots.items():
            if wt_path != self.repo_root and self._inside(full, wt_path) and full != wt_path:
                return os.path.relpath(full, wt_path)
        if self._inside(full, self.repo_root):
            return os.path.relpath(full, self.repo_root)
        return path

    def match_subagent(self, paths):
        counts = {}
        for p in paths:
            if not p:
                continue
            wt_name = self.worktree_for_path(p)
            if wt_name:
                counts[wt_name] = counts.get(wt_name, 0) + 1
        if not counts:
            return None
        return max(counts, key=counts.get)


def discover_transcripts(home, now, active_seconds):
    found = []
    cutoff = now - active_seconds
    for pattern in (
        os.path.join(home, ".cursor", "projects", "*", "agent-transcripts", "*", "*.jsonl"),
        os.path.join(home, ".claude", "projects", "*", "*.jsonl"),
    ):
        for path in glob.glob(pattern):
            try:
                if os.path.getmtime(path) >= cutoff:
                    found.append(path)
            except OSError:
                continue
    return sorted(found, key=os.path.getmtime)


def _tool_uses_from_line(line):
    try:
        entry = json.loads(line)
    except ValueError:
        return []
    content = (entry.get("message") or {}).get("content")
    found = []
    for block in content if isinstance(content, list) else ():
        if isinstance(block, dict) and block.get("type") == "tool_use":
            found.append((block.get("name"), block.get("input") or {}))
    return found


def _steps_from_line(line, root):
    steps = []
    for name, args in _tool_uses_from_line(line):
        kind = session.TOOLS.get(name)
        if kind != session.READ:
            continue
        raw = next((args[k] for k in session.PATH_KEYS if args.get(k)), None)
        if raw is None:
            continue
        steps.append(session.Step(kind, name, path=session._relative(raw, root)))
    return steps


def match_subagent(paths, worktrees, *, repo_root=None, worktree_paths=None):
    if worktree_paths is not None:
        return worktree_paths.match_subagent(paths)
    wt_paths = WorktreePaths(repo_root or "", worktrees)
    return wt_paths.match_subagent(paths)


def _raw_read_paths(path):
    paths = []
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                for name, args in _tool_uses_from_line(line):
                    if name != "Read":
                        continue
                    raw = next((args[k] for k in session.PATH_KEYS if args.get(k)), None)
                    if raw is not None:
                        paths.append(raw)
    except OSError:
        pass
    return paths


def subagent_read_count(path, repo_root):
    return sum(1 for s in session.read_steps(path, repo_root) if s.kind == session.READ)


def _transcript_stem_id(path):
    return f"agent:{os.path.splitext(os.path.basename(path))[0][:8]}"


class TranscriptTail:
    def __init__(self, path, repo_root, worktrees, on_subagent=None, worktree_paths=None):
        self.path = path
        self.repo_root = repo_root
        self.worktrees = worktrees
        self.worktree_paths = worktree_paths or WorktreePaths(repo_root, worktrees)
        self._on_subagent = on_subagent
        self._offset = 0
        self._partial = ""
        self._agent = None
        self._has_task = False
        self._matched_subagent = False
        self._repo_paths: list[str] = []
        self._seen_subagents: set[str] = set()
        self._file_identity: tuple[int, int] | None = None
        self._seek_end()
        self._scan_subagents()

    def _record_identity(self):
        try:
            st = os.stat(self.path)
            self._file_identity = (st.st_dev, st.st_ino)
        except OSError:
            self._file_identity = None

    def _seek_end(self):
        try:
            size = os.path.getsize(self.path)
            with open(self.path, "rb") as f:
                data = f.read()
        except OSError:
            self._offset = 0
            self._partial = ""
            self._file_identity = None
            return
        if data and not data.endswith(b"\n"):
            partial = data[data.rfind(b"\n") + 1:]
            self._partial = partial.decode("utf-8", errors="replace")
        else:
            self._partial = ""
        self._offset = size
        self._record_identity()

    def _has_subagent_files(self):
        sub_dir = os.path.join(os.path.dirname(self.path), "subagents")
        return bool(glob.glob(os.path.join(sub_dir, "*.jsonl")))

    def _update_agent(self):
        if (self._has_task or self._has_subagent_files()) and self._matched_subagent:
            self._agent = Agent("orchestrator", "orchestrator", None, None)
            return
        if not self._repo_paths:
            self._agent = None
            return
        wt_name = self.worktree_paths.match_subagent(self._repo_paths)
        wt = next((w for w in self.worktrees if w.name == wt_name), None) if wt_name else None
        self._agent = Agent(_transcript_stem_id(self.path), "agent",
                            wt.team if wt else None, wt.name if wt else None)

    def _scan_subagents(self):
        sub_dir = os.path.join(os.path.dirname(self.path), "subagents")
        for sub in sorted(glob.glob(os.path.join(sub_dir, "*.jsonl"))):
            if sub in self._seen_subagents:
                continue
            self._seen_subagents.add(sub)
            paths = _raw_read_paths(sub)
            wt_name = self.worktree_paths.match_subagent(paths)
            if wt_name:
                self._matched_subagent = True
                if self._on_subagent:
                    self._on_subagent(wt_name, subagent_read_count(sub, self.repo_root))
        self._update_agent()

    def _reset_transcript(self):
        self._offset = 0
        self._partial = ""
        self._agent = None
        self._has_task = False
        self._matched_subagent = False
        self._repo_paths = []
        self._seen_subagents = set()
        self._scan_subagents()

    def _read_new(self):
        try:
            st = os.stat(self.path)
            size = st.st_size
            identity = (st.st_dev, st.st_ino)
        except OSError:
            return b""
        if self._file_identity is not None and identity != self._file_identity:
            self._reset_transcript()
        elif size < self._offset:
            self._reset_transcript()
        with open(self.path, "rb") as f:
            f.seek(self._offset)
            data = f.read()
        self._offset += len(data)
        self._file_identity = identity
        return data

    def poll(self):
        chunk = self._read_new().decode("utf-8", errors="replace")
        if not chunk and not self._partial:
            self._scan_subagents()
            return []
        text = self._partial + chunk
        lines = text.split("\n")
        self._partial = "" if text.endswith("\n") else lines.pop()
        events = []
        for line in lines:
            if not line.strip():
                continue
            for name, _args in _tool_uses_from_line(line):
                if name == "Task":
                    self._has_task = True
            for step in _steps_from_line(line, self.repo_root):
                if step.path and self.worktree_paths.in_repo_or_worktree(step.path):
                    self._repo_paths.append(step.path)
            self._update_agent()
            if self._agent is None:
                continue
            for step in _steps_from_line(line, self.repo_root):
                if step.kind != session.READ:
                    continue
                if not step.path or not self.worktree_paths.in_repo_or_worktree(step.path):
                    continue
                events.append((self._agent, self.worktree_paths.rel_for_worktree(step.path)))
        self._scan_subagents()
        return events
