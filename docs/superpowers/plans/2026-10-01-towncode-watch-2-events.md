# Towncode watch Phase 2: the event stream — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the read-only watch event stream (`events.py`, `observer.py`, `watch.py`) and a `towncode watch PATH --events` mode that prints one line per event, with no drawing.

**Architecture:** `Observer` polls one worktree folder via `git ls-files -co --exclude-standard` and `lstat`, emitting path-level changes after an initial baseline poll. `Watch` discovers worktrees in `__init__` then every 5 s, scans ledger file names, tails transcripts (including new subagent files), detects commits and merges, maps paths to modules/sites/buildings, and holds the “who is working where” state Phase 3 will draw. Mid-build scaffolding, sites, and implementer positions come from git diff vs merge base plus untracked listings — not from a first-poll event flood. A injectable clock drives all poll intervals; tests never sleep and always pass a temporary `survey_dir` and `home`. `towncode watch --events` loops `Watch.poll()` with an injectable `sleep` defaulting to `time.sleep`.

**Tech Stack:** Python 3.10+ standard library only (`dataclasses`, `subprocess`, `json`, `glob`, `unittest`), git CLI.

**Spec:** docs/superpowers/specs/2026-10-01-towncode-watch-design.md (Phase 2)

## Global Constraints

- Worktree list: `git worktree list --porcelain` from main, on **`Watch.__init__`** and every **5 s** thereafter.
- File observer: every **1 s** for shown worktrees, every **10 s** for others; first `poll()` per observer is a baseline (emits nothing).
- Branch tip (`git rev-parse HEAD` in each worktree): every **1 s** for shown worktrees.
- Main tip (`git rev-parse HEAD` in main): every **1 s**.
- Task ledgers (file names in `<worktree>/.superpowers/sdd/*/`): every **1 s** for shown worktrees.
- Main transcripts: tail new lines every **1 s**; transcript folders rescanned every **10 s**; only files modified in the last **2 hours**.
- Diff stats (`git diff --numstat <merge base>`): refreshed at most every **2 s** per worktree, **only after that worktree's file events** in the same poll cycle.
- **Read-only:** never writes inside the repository or its worktrees; writes only `watch.json` in the survey folder (`towncode.output_dir`), and only when team colour assignments change.
- **Read-only:** lists untracked non-ignored file names and sizes and ledger file names; opens neither.
- **Read-only:** never shows file contents; never runs code; git read commands only.
- **Principle 8:** A Clawd only goes where its agent was seen. The one exception is the reviewer's tour, which shows the files under review and is labelled as such.
- **Ledger name patterns:** `task-N-brief.md` → `start`; `task-N-report.md` → `finish`; `review-*.md` without `-result` → `review_start`; `<stem>-result.md` → `review_finish`.
- **Team branch pattern:** `team/<team>/<slug>`; any other branch uses the worktree folder name as its team.
- Every git command uses `repo.GIT_FLAGS` and `GIT_OPTIONAL_LOCKS=0`; never run `git status`.
- Standard library only. Do not edit `focus.py`, `cake.py`, `roles.py`, or `mock_roles.py`.
- Full test suite must pass: `.venv/bin/python -m unittest` (463 tests today).
- **Tests:** every `Watch(...)` call passes a temporary `survey_dir`; transcript tests pass a temporary `home` (never read `~/.cursor` or `~/.claude`).

## File Structure

| File | Responsibility |
| --- | --- |
| `events.py` | `Agent` and `Event` dataclasses (shared with v3 later) |
| `observer.py` | File observer for one folder: `ls-files` + size/mtime, no opens |
| `watch.py` | Worktree discovery, ledger, transcripts, merge detection, path mapping, `WatchState`, colour persistence |
| `towncode.py` | Add `watch PATH [--events]` subcommand |
| `fixture.py` | Add `worktree()` helper for tests |
| `test_events.py` | Dataclass smoke tests |
| `test_observer.py` | Observer behaviour and read-only guarantees |
| `test_watch.py` | Worktrees, ledger, transcripts, mapping, colours, merge, mid-build, diff stats |
| `test_watch_e2e.py` | Full fake run event order and untouched fingerprint |

---

### Task 1: Event dataclasses

**Files:**
- Create: `events.py`
- Test: `test_events.py`

**Interfaces:**
- Produces:
  - `events.Agent(id: str, role: str, team: str | None, worktree: str | None)` — frozen dataclass
  - `events.Event(kind: str, agent: Agent | None, path: str | None = None, seen: float = 0.0)` — frozen dataclass
  - Kinds used in Phase 2: `start`, `read`, `edit`, `create`, `delete`, `commit`, `finish`, `review_start`, `review_finish`, `merge`, `leave`

- [ ] **Step 1: Write the failing test**

Create `test_events.py`:

```python
import unittest

from events import Agent, Event


class EventsTest(unittest.TestCase):
    def test_agent_and_event_fields(self):
        agent = Agent("w2-world/task-1", "implementer", "world", "w2-world")
        event = Event("edit", agent, "tools/x.py", seen=42.0)
        self.assertEqual(event.kind, "edit")
        self.assertEqual(event.agent.id, "w2-world/task-1")
        self.assertEqual(event.path, "tools/x.py")
        self.assertEqual(event.seen, 42.0)

    def test_events_are_frozen(self):
        event = Event("merge", None)
        with self.assertRaises(AttributeError):
            event.kind = "edit"


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m unittest test_events -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'events'`

- [ ] **Step 3: Write minimal implementation**

Create `events.py`:

```python
"""Agents and events for watch and v3."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Agent:
    id: str
    role: str
    team: str | None
    worktree: str | None


@dataclass(frozen=True)
class Event:
    kind: str
    agent: Agent | None
    path: str | None = None
    seen: float = 0.0
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m unittest test_events -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add events.py test_events.py
git commit -m "Add Agent and Event dataclasses for watch"
```

---

### Task 2: File observer

**Files:**
- Create: `observer.py`
- Test: `test_observer.py`

**Interfaces:**
- Consumes: `repo.GIT_FLAGS`, `repo.GIT_ENV` (import `GIT_ENV` from `repo`)
- Produces:
  - `observer.Observer(root: str)` — one worktree folder
  - `observer.Observer.poll() -> list[tuple[str, str]]` — `(kind, rel_path)` where kind is `edit`, `create`, or `delete`; rename is `delete` then `create`; **first** `poll()` seeds baseline and returns `[]`

- [ ] **Step 1: Write the failing test**

Create `test_observer.py`:

```python
import os
import stat
import unittest

import fixture
from observer import Observer


class ObserverTest(unittest.TestCase):
    def setUp(self):
        self.root = fixture.make_repo(self, {"a.py": "x = 1\n", "pkg/b.py": "y = 2\n"})

    def test_create_edit_delete_and_rename(self):
        obs = Observer(self.root)
        self.assertEqual(obs.poll(), [])
        with open(os.path.join(self.root, "new.py"), "w", encoding="utf-8") as f:
            f.write("z = 3\n")
        self.assertEqual(obs.poll(), [("create", "new.py")])
        with open(os.path.join(self.root, "a.py"), "a", encoding="utf-8") as f:
            f.write("# edit\n")
        self.assertEqual(obs.poll(), [("edit", "a.py")])
        os.rename(os.path.join(self.root, "pkg/b.py"), os.path.join(self.root, "pkg/c.py"))
        self.assertEqual(obs.poll(), [("delete", "pkg/b.py"), ("create", "pkg/c.py")])
        os.remove(os.path.join(self.root, "new.py"))
        self.assertEqual(obs.poll(), [("delete", "new.py")])

    def test_ignored_files_are_never_reported(self):
        os.makedirs(os.path.join(self.root, "build"), exist_ok=True)
        with open(os.path.join(self.root, "build", "out.o"), "w", encoding="utf-8") as f:
            f.write("binary\n")
        with open(os.path.join(self.root, ".gitignore"), "w", encoding="utf-8") as f:
            f.write("build/\n")
        obs = Observer(self.root)
        self.assertEqual(obs.poll(), [])

    def test_unreadable_files_still_produce_events(self):
        path = os.path.join(self.root, "a.py")
        os.chmod(path, 0)
        self.addCleanup(os.chmod, path, stat.S_IRUSR | stat.S_IWUSR)
        obs = Observer(self.root)
        obs.poll()
        os.utime(path, None)
        kinds = [k for k, _ in obs.poll()]
        self.assertIn("edit", kinds)

    def test_observer_never_opens_tracked_files(self):
        opened = []
        real = open

        def spy(path, *args, **kwargs):
            if os.path.realpath(path).startswith(os.path.realpath(self.root)):
                opened.append(os.path.relpath(path, self.root))
            return real(path, *args, **kwargs)

        with __import__("unittest").mock.patch("builtins.open", spy):
            obs = Observer(self.root)
            obs.poll()
            with open(os.path.join(self.root, "a.py"), "a", encoding="utf-8") as f:
                f.write("# touch\n")
            obs.poll()
        self.assertEqual(opened, [])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m unittest test_observer -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'observer'`

- [ ] **Step 3: Write minimal implementation**

Create `observer.py`:

```python
"""File observer for one worktree folder: size and mtime only, never opens files."""

import os
import subprocess

from repo import GIT_ENV, GIT_FLAGS


class Observer:
    def __init__(self, root):
        self.root = os.path.realpath(root)
        self._prev: dict[str, tuple[int, int]] = {}

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
        if not self._prev:
            self._prev = now
            return []
        events = []
        for rel, st in now.items():
            if rel not in self._prev:
                events.append(("create", rel))
            elif self._prev[rel] != st:
                events.append(("edit", rel))
        for rel in self._prev:
            if rel not in now:
                events.append(("delete", rel))
        self._prev = now
        return events
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m unittest test_observer -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add observer.py test_observer.py
git commit -m "Watch a folder's files by size and modification time"
```

---

### Task 3: Worktree discovery, teams, ledger, and commits

**Files:**
- Create: `watch.py` (first half: clock, worktrees, teams, shown logic, ledger, branch tips, leave)
- Modify: `fixture.py` (add `worktree()`)
- Test: `test_watch.py` (worktree/ledger sections only — file grows in later tasks)

**Interfaces:**
- Consumes: `events.Agent`, `events.Event`, `observer.Observer`, `repo.GIT_FLAGS`, `repo.GIT_ENV`
- Produces:
  - `watch.RealClock` with `.monotonic() -> float` and `.time() -> float`
  - `watch.FakeClock(start=0.0)` with `.monotonic()`, `.time()`, `.advance(seconds: float)`
  - `watch.team_of(branch: str, worktree_name: str) -> str`
  - `watch.parse_worktrees(text: str) -> list[watch.WorktreeInfo]`
  - `watch.WorktreeInfo(name, path, branch, team)` — frozen dataclass
  - `watch.scan_ledger(wt_path: str) -> list[tuple[str, str, str]]` — `(kind, agent_id, ledger_rel)` from file names only
  - `watch.Watch(repo_root: str, *, home="~", clock=None, survey_dir=None)`
  - `watch.Watch.poll() -> list[Event]`
  - `watch.Watch.worktrees() -> list[WorktreeInfo]`
  - `watch.Watch._shown(wt: WorktreeInfo) -> bool`

- [ ] **Step 1: Write the failing tests**

Add to `fixture.py`:

```python
def worktree(main, path, branch, files=None):
    """Add a linked worktree on `branch`; optional `files` are written inside it."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    git(main, "worktree", "add", "-b", branch, path)
    if files:
        write(path, files)
    return path
```

Create `test_watch.py` (partial — more tests appended in later tasks). Every test class uses a temporary survey folder:

```python
import glob
import os
import shutil
import stat
import tempfile
import unittest

import fixture
import watch
from events import Agent


def temp_survey(test):
    out = tempfile.mkdtemp(prefix="watch-survey-")
    test.addCleanup(shutil.rmtree, out)
    return out


class WatchWorktreesTest(unittest.TestCase):
    def setUp(self):
        self.main = fixture.make_repo(self, {"hub/a.py": "x = 1\n"})
        self.wts = os.path.join(os.path.dirname(self.main), "wts")
        self.clock = watch.FakeClock()
        self.survey = temp_survey(self)

    def _watch(self):
        return watch.Watch(self.main, clock=self.clock, survey_dir=self.survey)

    def test_team_from_branch_or_folder_name(self):
        self.assertEqual(watch.team_of("team/world/demo", "ignored"), "world")
        self.assertEqual(watch.team_of("feature/x", "my-folder"), "my-folder")

    def test_two_worktrees_on_team_branches(self):
        a = fixture.worktree(self.main, os.path.join(self.wts, "wa"), "team/a/x")
        b = fixture.worktree(self.main, os.path.join(self.wts, "wb"), "team/b/y")
        names = {w.name: w.team for w in self._watch().worktrees()}
        self.assertEqual(names, {"wa": "a", "wb": "b"})
        self.assertEqual({w.path for w in self._watch().worktrees()}, {self.main, a, b})

    def test_merged_branch_worktree_is_not_shown(self):
        wt = fixture.worktree(self.main, os.path.join(self.wts, "done"), "team/done/x",
                              {"hub/b.py": "y = 2\n"})
        fixture.git(wt, "add", "hub/b.py")
        fixture.git(wt, "commit", "-q", "-m", "work")
        fixture.git(self.main, "merge", "--no-ff", "-q", "team/done/x", "-m", "merge done")
        w = self._watch()
        w.poll()
        shown = {i.name for i in w.worktrees() if w._shown(i)}
        self.assertNotIn("done", shown)

    def test_removed_worktree_emits_leave(self):
        wt = fixture.worktree(self.main, os.path.join(self.wts, "gone"), "team/gone/x")
        w = self._watch()
        w.poll()
        fixture.git(self.main, "worktree", "remove", "--force", wt)
        self.clock.advance(5)
        kinds = [e.kind for e in w.poll()]
        self.assertIn("leave", kinds)


class WatchLedgerTest(unittest.TestCase):
    def setUp(self):
        self.main = fixture.make_repo(self, {"hub/a.py": "x = 1\n"})
        self.wts = os.path.join(os.path.dirname(self.main), "wts")
        self.wt = fixture.worktree(self.main, os.path.join(self.wts, "w1"), "team/world/demo")
        self.clock = watch.FakeClock()
        self.survey = temp_survey(self)
        self.ledger = os.path.join(self.wt, ".superpowers/sdd/run-1")
        os.makedirs(self.ledger, exist_ok=True)

    def _write(self, name, text="x"):
        path = os.path.join(self.ledger, name)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        return path

    def test_ledger_names_emit_lifecycle_events(self):
        w = watch.Watch(self.main, clock=self.clock, survey_dir=self.survey)
        w.poll()
        self._write("task-1-brief.md")
        self.clock.advance(1)
        kinds = [e.kind for e in w.poll()]
        self.assertIn("start", kinds)
        with open(os.path.join(self.wt, "hub/a.py"), "a", encoding="utf-8") as f:
            f.write("# e\n")
        self.clock.advance(1)
        w.poll()
        self._write("task-1-report.md")
        self.clock.advance(1)
        self.assertIn("finish", [e.kind for e in w.poll()])
        self._write("review-task-1.md")
        self.clock.advance(1)
        self.assertIn("review_start", [e.kind for e in w.poll()])
        self._write("review-task-1-result.md")
        self.clock.advance(1)
        self.assertIn("review_finish", [e.kind for e in w.poll()])

    def test_ledger_files_never_opened_even_when_unreadable(self):
        brief = self._write("task-2-brief.md")
        os.chmod(brief, 0)
        self.addCleanup(os.chmod, brief, stat.S_IRUSR | stat.S_IWUSR)
        w = watch.Watch(self.main, clock=self.clock, survey_dir=self.survey)
        w.poll()
        self.clock.advance(1)
        self.assertIn("start", [e.kind for e in w.poll()])


class WatchCommitsTest(unittest.TestCase):
    def setUp(self):
        self.main = fixture.make_repo(self, {"hub/a.py": "x = 1\n"})
        self.wts = os.path.join(os.path.dirname(self.main), "wts")
        self.wt = fixture.worktree(self.main, os.path.join(self.wts, "w1"), "team/world/demo")
        self.clock = watch.FakeClock()
        self.survey = temp_survey(self)

    def test_branch_tip_commit_emits_commit(self):
        w = watch.Watch(self.main, clock=self.clock, survey_dir=self.survey)
        w.poll()
        fixture.commit(self.wt, {"hub/a.py": "x = 2\n"})
        self.clock.advance(1)
        commits = [e for e in w.poll() if e.kind == "commit"]
        self.assertEqual(len(commits), 1)
        self.assertEqual(commits[0].agent.role, "implementer")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m unittest test_watch.WatchWorktreesTest test_watch.WatchLedgerTest test_watch.WatchCommitsTest -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'watch'`

- [ ] **Step 3: Write minimal implementation**

Create `watch.py` (Task 3 portion — later tasks append to this file):

```python
"""Discover worktrees, tail transcripts, and merge sources into one event stream."""

import glob
import os
import re
import subprocess
import time
from dataclasses import dataclass

import towncode
from events import Agent, Event
from observer import Observer
from repo import GIT_ENV, GIT_FLAGS

TEAM_BRANCH = re.compile(r"^team/([^/]+)/")
LEDGER = re.compile(
    r"^(task-(\d+)-brief\.md|task-(\d+)-report\.md|(review-[^/\\]+)\.md|(review-[^/\\]+)-result\.md)$")
ACTIVE_SECONDS = 2 * 3600
WORKTREE_INTERVAL = 5
SHOWN_POLL = 1
HIDDEN_POLL = 10
MAIN_POLL = 1


class RealClock:
    def monotonic(self):
        return time.monotonic()

    def time(self):
        return time.time()


class FakeClock:
    def __init__(self, start=0.0):
        self._mono = start
        self._wall = start

    def monotonic(self):
        return self._mono

    def time(self):
        return self._wall

    def advance(self, seconds):
        self._mono += seconds
        self._wall += seconds


def team_of(branch, worktree_name):
    found = TEAM_BRANCH.match(branch)
    return found.group(1) if found else worktree_name


def _git(root, *args):
    result = subprocess.run(["git", "-C", root, *GIT_FLAGS, *args],
                            check=True, capture_output=True,
                            env=dict(os.environ, **GIT_ENV))
    return result.stdout.decode("utf-8", errors="replace")


@dataclass(frozen=True)
class WorktreeInfo:
    name: str
    path: str
    branch: str
    team: str


def parse_worktrees(text):
    found = []
    block = {}
    for line in text.splitlines() + [""]:
        if not line.strip():
            if block:
                path = block["worktree"]
                branch = block.get("branch", "").removeprefix("refs/heads/")
                name = os.path.basename(path.rstrip("/"))
                found.append(WorktreeInfo(name, path, branch, team_of(branch, name)))
                block = {}
            continue
        key, _, value = line.partition(" ")
        block[key] = value
    return found


def scan_ledger(wt_path):
    events = []
    base = os.path.join(wt_path, ".superpowers", "sdd")
    if not os.path.isdir(base):
        return events
    name = os.path.basename(wt_path.rstrip("/"))
    for path in glob.glob(os.path.join(base, "*", "*")):
        if not os.path.isfile(path):
            continue
        fname = os.path.basename(path)
        m = LEDGER.match(fname)
        if not m:
            continue
        rel = os.path.relpath(path, wt_path)
        if fname.endswith("-brief.md"):
            events.append(("start", f"{name}/task-{m.group(2)}", rel))
        elif fname.endswith("-report.md"):
            events.append(("finish", f"{name}/task-{m.group(3)}", rel))
        elif fname.endswith("-result.md"):
            events.append(("review_finish", f"{name}/{m.group(5)}", rel))
        elif fname.startswith("review-") and not fname.endswith("-result.md"):
            events.append(("review_start", f"{name}/{m.group(4)}", rel))
    return events


def _is_ancestor(main_root, maybe_ancestor, rev):
    if not maybe_ancestor:
        return False
    return subprocess.run(["git", "-C", main_root, *GIT_FLAGS, "merge-base", "--is-ancestor",
                           maybe_ancestor, rev],
                          env=dict(os.environ, **GIT_ENV)).returncode == 0


class Watch:
    def __init__(self, repo_root, *, home="~", clock=None, survey_dir=None):
        self.repo_root = os.path.realpath(repo_root)
        self.home = os.path.expanduser(home)
        self.clock = clock or RealClock()
        self.survey_dir = survey_dir or towncode.output_dir(repo_root)
        self._worktrees: list[WorktreeInfo] = []
        self._observers: dict[str, Observer] = {}
        self._last_poll: dict[str, float] = {}
        self._last_main_poll = 0.0
        self._last_commit: dict[str, str] = {}
        self._main_tip = _git(self.repo_root, "rev-parse", "HEAD").strip()
        self._seen_ledger: set[tuple[str, str, str]] = set()
        self._known_wt_names: set[str] = set()
        self._recent: dict[str, float] = {}
        self._open_briefs: dict[str, set[int]] = {}
        self._open_reviews: dict[str, set[str]] = {}
        self._latest_path: dict[str, str] = {}
        self._refresh_worktrees()
        self._last_wt_list = self.clock.monotonic()
        self._known_wt_names = {w.name for w in self._worktrees if w.path != self.repo_root}
        for wt in self._worktrees:
            if wt.path != self.repo_root:
                self._last_commit[wt.name] = _git(wt.path, "rev-parse", "HEAD").strip()

    def worktrees(self):
        return list(self._worktrees)

    def _refresh_worktrees(self):
        self._worktrees = parse_worktrees(_git(self.repo_root, "worktree", "list", "--porcelain"))

    def _shown(self, wt: WorktreeInfo) -> bool:
        if wt.path == self.repo_root:
            return False
        if wt.branch and _is_ancestor(self.repo_root, wt.branch, "HEAD"):
            return False
        if self._open_briefs.get(wt.name) or self._open_reviews.get(wt.name):
            return True
        last = self._recent.get(wt.name, 0.0)
        return self.clock.time() - last < ACTIVE_SECONDS

    def _agent(self, agent_id, role, wt: WorktreeInfo) -> Agent:
        return Agent(agent_id, role, wt.team, wt.name)

    def _implementer(self, wt: WorktreeInfo) -> Agent:
        briefs = sorted(self._open_briefs.get(wt.name, set()))
        if briefs:
            return self._agent(f"{wt.name}/task-{briefs[-1]}", "implementer", wt)
        return self._agent(wt.name, "implementer", wt)

    def _note_activity(self, wt_name):
        self._recent[wt_name] = self.clock.time()

    def _poll_worktree(self, wt: WorktreeInfo, interval: float) -> list[Event]:
        now = self.clock.monotonic()
        if now - self._last_poll.get(wt.name, 0) < interval:
            return []
        self._last_poll[wt.name] = now
        events = []
        agent = self._implementer(wt)
        obs = self._observers.setdefault(wt.path, Observer(wt.path))
        for kind, path in obs.poll():
            self._note_activity(wt.name)
            self._latest_path[agent.id] = path
            events.append(Event(kind, agent, path, now))
        for kind, agent_id, _ledger in scan_ledger(wt.path):
            key = (wt.name, kind, agent_id)
            if key in self._seen_ledger:
                continue
            self._seen_ledger.add(key)
            role = {"start": "implementer", "finish": "implementer",
                    "review_start": "reviewer", "review_finish": "reviewer"}[kind]
            events.append(Event(kind, self._agent(agent_id, role, wt), None, now))
            if kind == "start":
                self._open_briefs.setdefault(wt.name, set()).add(int(agent_id.rsplit("-", 1)[-1]))
            elif kind == "finish":
                self._open_briefs.get(wt.name, set()).discard(int(agent_id.rsplit("-", 1)[-1]))
            elif kind == "review_start":
                self._open_reviews.setdefault(wt.name, set()).add(agent_id.split("/", 1)[1])
            elif kind == "review_finish":
                self._open_reviews.get(wt.name, set()).discard(agent_id.split("/", 1)[1])
        tip = _git(wt.path, "rev-parse", "HEAD").strip()
        prev = self._last_commit.get(wt.name)
        if prev is not None and tip != prev:
            self._note_activity(wt.name)
            events.append(Event("commit", agent, None, now))
        self._last_commit[wt.name] = tip
        return events

    def poll(self) -> list[Event]:
        now = self.clock.monotonic()
        events = []
        if now - self._last_wt_list >= WORKTREE_INTERVAL:
            self._refresh_worktrees()
            self._last_wt_list = now
            names = {w.name for w in self._worktrees if w.path != self.repo_root}
            for gone in self._known_wt_names - names:
                wt = WorktreeInfo(gone, "", "", "")
                events.append(Event("leave", self._agent(gone, "implementer", wt), None, now))
            self._known_wt_names = names
        for wt in self._worktrees:
            if wt.path == self.repo_root:
                continue
            interval = SHOWN_POLL if self._shown(wt) else HIDDEN_POLL
            events.extend(self._poll_worktree(wt, interval))
        return events
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m unittest test_watch.WatchWorktreesTest test_watch.WatchLedgerTest test_watch.WatchCommitsTest -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add watch.py fixture.py test_watch.py
git commit -m "Discover worktrees and emit ledger and commit events"
```

---

### Task 4: Transcript tailing, subagent read counts, orchestrator reads

**Files:**
- Modify: `watch.py` (add transcript helpers, `TranscriptTail`, subagent handling)
- Modify: `test_watch.py` (append transcript tests)

**Interfaces:**
- Consumes: `session.read_steps`, `session.Step`, `session.TOOLS`, `session.PATH_KEYS`, `session._relative`, `session.READ`
- Produces:
  - `watch.discover_transcripts(home, now) -> list[str]`
  - `watch.match_subagent(paths, worktrees) -> str | None`
  - `watch.subagent_read_count(path, repo_root) -> int`
  - `watch.TranscriptTail(path, repo_root, worktrees, on_subagent=None)` — `on_subagent(wt_name, count)` when a new `subagents/*.jsonl` appears
  - `watch.Watch.finish_read_count(worktree_name) -> int` — read count from latest subagent transcript for that worktree
  - `watch.Watch.finish_summary(worktree_name) -> str` — e.g. `read 2 files, changed 5` from subagent count + diff numstat totals
  - `Watch.poll()` emits `read` events from main transcripts

- [ ] **Step 1: Write the failing tests**

Append to `test_watch.py`:

```python
import json

import session


def write_lines(path, entries):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.writelines(json.dumps(e) + "\n" for e in entries)


def use(name, **args):
    return {"type": "tool_use", "name": name, "input": args}


class WatchTranscriptsTest(unittest.TestCase):
    def setUp(self):
        self.main = fixture.make_repo(self, {"hub/a.py": "x = 1\n"})
        self.wts = os.path.join(os.path.dirname(self.main), "wts")
        self.wt = fixture.worktree(self.main, os.path.join(self.wts, "w1"), "team/world/demo")
        self.home = tempfile.mkdtemp(prefix="watch-home-")
        self.addCleanup(shutil.rmtree, self.home)
        self.survey = temp_survey(self)
        self.clock = watch.FakeClock(start=1_000_000.0)
        slug = os.path.realpath(self.main).replace("/", "-").replace(".", "-").replace("_", "-")
        self.main_transcript = os.path.join(
            self.home, ".cursor", "projects", slug.lstrip("-"),
            "agent-transcripts", "chat-1", "chat-1.jsonl")

    def _watch(self):
        return watch.Watch(self.main, home=self.home, clock=self.clock, survey_dir=self.survey)

    def test_cursor_reads_become_relative_paths(self):
        write_lines(self.main_transcript, [
            {"role": "assistant", "message": {"content": [
                use("Read", path=os.path.join(self.main, "hub/a.py"))]}}])
        os.utime(self.main_transcript, (self.clock.time(), self.clock.time()))
        w = self._watch()
        w.poll()
        self.clock.advance(1)
        reads = [e for e in w.poll() if e.kind == "read"]
        self.assertEqual(reads[0].path, "hub/a.py")
        self.assertEqual(reads[0].agent.role, "agent")

    def test_partial_last_line_waits_for_newline(self):
        os.makedirs(os.path.dirname(self.main_transcript), exist_ok=True)
        with open(self.main_transcript, "w", encoding="utf-8") as f:
            f.write('{"role":"assistant","message":{"content":[]}')
        os.utime(self.main_transcript, (self.clock.time(), self.clock.time()))
        w = self._watch()
        w.poll()
        self.assertEqual([], [e for e in w.poll() if e.kind == "read"])
        with open(self.main_transcript, "a", encoding="utf-8") as f:
            f.write('}}\n')
        self.clock.advance(1)
        self.assertEqual(1, len([e for e in w.poll() if e.kind == "read"]))

    def test_shrinking_transcript_is_reread_from_start(self):
        write_lines(self.main_transcript, [
            {"role": "assistant", "message": {"content": [
                use("Read", path=os.path.join(self.main, "hub/a.py"))]}}])
        os.utime(self.main_transcript, (self.clock.time(), self.clock.time()))
        w = self._watch()
        w.poll()
        self.clock.advance(1)
        w.poll()
        write_lines(self.main_transcript, [
            {"role": "assistant", "message": {"content": [
                use("Read", path=os.path.join(self.main, "hub/b.py"))]}}])
        os.utime(self.main_transcript, (self.clock.time(), self.clock.time()))
        self.clock.advance(1)
        paths = [e.path for e in w.poll() if e.kind == "read"]
        self.assertIn("hub/b.py", paths)

    def test_subagent_folder_makes_orchestrator(self):
        write_lines(self.main_transcript, [{"role": "assistant", "message": {"content": []}}])
        sub = os.path.join(os.path.dirname(self.main_transcript), "subagents", "sub1.jsonl")
        write_lines(sub, [{"role": "assistant", "message": {"content": [
            use("Read", path=os.path.join(self.main, "hub/a.py"))]}}])
        os.utime(self.main_transcript, (self.clock.time(), self.clock.time()))
        w = self._watch()
        w.poll()
        self.clock.advance(1)
        orch = [e for e in w.poll() if e.kind == "read" and e.agent.role == "orchestrator"]
        self.assertEqual(len(orch), 1)

    def test_new_subagent_records_read_count_for_finish(self):
        write_lines(self.main_transcript, [{"role": "assistant", "message": {"content": []}}])
        os.utime(self.main_transcript, (self.clock.time(), self.clock.time()))
        w = self._watch()
        w.poll()
        sub = os.path.join(os.path.dirname(self.main_transcript), "subagents", "agent-x.jsonl")
        write_lines(sub, [{"role": "assistant", "message": {"content": [
            use("Read", path=os.path.join(self.wt, "hub/a.py")),
            use("Read", path=os.path.join(self.wt, "hub/a.py"))]}}])
        self.clock.advance(1)
        w.poll()
        self.assertEqual(w.finish_read_count("w1"), 2)
        self.assertIn("read 2", w.finish_summary("w1"))

    def test_match_subagent_picks_worktree_with_most_paths(self):
        w = self._watch()
        paths = ["hub/a.py", "hub/a.py", "other/x.py"]
        self.assertEqual(watch.match_subagent(["hub/a.py", "hub/a.py"], w.worktrees()), "w1")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m unittest test_watch.WatchTranscriptsTest -v`
Expected: FAIL

- [ ] **Step 3: Write minimal implementation**

Append to `watch.py`:

```python
import json

import session

TRANSCRIPT_INTERVAL = 1
TRANSCRIPT_RESCAN = 10


def discover_transcripts(home, now):
    found = []
    cutoff = now - ACTIVE_SECONDS
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


def _steps_from_line(line, root):
    try:
        entry = json.loads(line)
    except ValueError:
        return []
    content = (entry.get("message") or {}).get("content")
    steps = []
    for block in content if isinstance(content, list) else ():
        if not isinstance(block, dict) or block.get("type") != "tool_use":
            continue
        kind = session.TOOLS.get(block.get("name"))
        if kind != session.READ:
            continue
        args = block.get("input") or {}
        raw = next((args[k] for k in session.PATH_KEYS if args.get(k)), None)
        if raw is None:
            continue
        steps.append(session.Step(kind, block["name"], path=session._relative(raw, root)))
    return steps


def _rel_for_worktree(path, repo_root, worktrees):
    if path is None:
        return None
    full = path if os.path.isabs(path) else os.path.join(repo_root, path)
    for wt in worktrees:
        if full.startswith(wt.path + os.sep):
            return os.path.relpath(full, wt.path)
    if towncode._inside(full, repo_root):
        return os.path.relpath(full, repo_root)
    return path


def _touches_repo(steps, repo_root, worktrees):
    roots = {repo_root} | {w.path for w in worktrees}
    for s in steps:
        if s.path is None:
            continue
        full = s.path if os.path.isabs(s.path) else os.path.join(repo_root, s.path)
        for root in roots:
            if full == root or full.startswith(root + os.sep):
                return True
    return False


def _role_for_transcript(path, steps, worktrees, repo_root):
    sub_dir = os.path.join(os.path.dirname(path), "subagents")
    has_sub = bool(glob.glob(os.path.join(sub_dir, "*.jsonl")))
    tool_names = {s.tool for s in steps}
    if "Task" in tool_names or has_sub:
        return Agent("orchestrator", "orchestrator", None, None)
    wt = _worktree_for_steps(steps, worktrees, repo_root)
    return Agent("agent", "agent", wt.team if wt else None, wt.name if wt else None)


def _worktree_for_steps(steps, worktrees, repo_root):
    counts = {}
    for s in steps:
        if not s.path:
            continue
        full = s.path if os.path.isabs(s.path) else os.path.join(repo_root, s.path)
        for wt in worktrees:
            if full.startswith(wt.path + os.sep):
                counts[wt.name] = counts.get(wt.name, 0) + 1
    if not counts:
        return None
    return max(worktrees, key=lambda w: counts.get(w.name, 0))


def match_subagent(paths, worktrees):
    counts = {}
    for p in paths:
        for wt in worktrees:
            if p == wt.name or p.startswith(wt.name + "/"):
                counts[wt.name] = counts.get(wt.name, 0) + 1
                break
            if os.path.lexists(os.path.join(wt.path, p)):
                counts[wt.name] = counts.get(wt.name, 0) + 1
    return max(counts, key=counts.get) if counts else None


def subagent_read_count(path, repo_root):
    return sum(1 for s in session.read_steps(path, repo_root) if s.kind == session.READ)


class TranscriptTail:
    def __init__(self, path, repo_root, worktrees, on_subagent=None):
        self.path = path
        self.repo_root = repo_root
        self.worktrees = worktrees
        self._on_subagent = on_subagent
        self._offset = 0
        self._partial = ""
        self._agent = None
        self._seen_subagents: set[str] = set()
        self._bootstrap()

    def _bootstrap(self):
        steps = session.read_steps(self.path, self.repo_root)
        self._agent = (_role_for_transcript(self.path, steps, self.worktrees, self.repo_root)
                       if _touches_repo(steps, self.repo_root, self.worktrees) else None)
        try:
            self._offset = os.path.getsize(self.path)
        except OSError:
            self._offset = 0
        self._scan_subagents()

    def _scan_subagents(self):
        sub_dir = os.path.join(os.path.dirname(self.path), "subagents")
        for sub in sorted(glob.glob(os.path.join(sub_dir, "*.jsonl"))):
            if sub in self._seen_subagents:
                continue
            self._seen_subagents.add(sub)
            steps = session.read_steps(sub, self.repo_root)
            rels = [_rel_for_worktree(s.path, self.repo_root, self.worktrees)
                    for s in steps if s.path]
            wt_name = match_subagent(rels, self.worktrees)
            if wt_name and self._on_subagent:
                self._on_subagent(wt_name, subagent_read_count(sub, self.repo_root))

    def _read_new(self):
        try:
            size = os.path.getsize(self.path)
        except OSError:
            return b""
        if size < self._offset:
            self._offset = 0
            self._partial = ""
            self._bootstrap()
            return b""
        with open(self.path, "rb") as f:
            f.seek(self._offset)
            data = f.read()
        self._offset += len(data)
        return data

    def poll(self):
        if self._agent is None:
            self._scan_subagents()
            return []
        chunk = self._read_new().decode("utf-8", errors="replace")
        self._scan_subagents()
        if not chunk:
            return []
        text = self._partial + chunk
        lines = text.split("\n")
        self._partial = "" if text.endswith("\n") else lines.pop()
        events = []
        for line in lines:
            if not line.strip():
                continue
            for step in _steps_from_line(line, self.repo_root):
                if step.kind != session.READ:
                    continue
                events.append((self._agent, _rel_for_worktree(step.path, self.repo_root, self.worktrees)))
        return events
```

Extend `Watch.__init__`:

```python
        self._transcripts: dict[str, TranscriptTail] = {}
        self._last_transcript_scan = 0.0
        self._last_transcript_poll = 0.0
        self._subagent_reads: dict[str, int] = {}
```

Add method:

```python
    def finish_read_count(self, worktree_name):
        return self._subagent_reads.get(worktree_name, 0)

    def finish_summary(self, worktree_name):
        reads = self.finish_read_count(worktree_name)
        added, removed = self._diff_stats.get(worktree_name, (0, 0))
        changed = added + removed
        return f"read {reads} files, changed {changed}"

    def _on_subagent(self, wt_name, count):
        self._subagent_reads[wt_name] = count
```

Extend `Watch.poll()` (after worktree loop, before return):

```python
        if now - self._last_transcript_scan >= TRANSCRIPT_RESCAN:
            for path in discover_transcripts(self.home, self.clock.time()):
                if path not in self._transcripts:
                    self._transcripts[path] = TranscriptTail(
                        path, self.repo_root, self._worktrees, on_subagent=self._on_subagent)
            self._last_transcript_scan = now
        if now - self._last_transcript_poll >= TRANSCRIPT_INTERVAL:
            self._last_transcript_poll = now
            for tail in self._transcripts.values():
                for agent, path in tail.poll():
                    events.append(Event("read", agent, path, now))
        return events
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m unittest test_watch.WatchTranscriptsTest -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add watch.py test_watch.py
git commit -m "Tail transcripts and record subagent read counts"
```

---

### Task 5: Path mapping, merge detection, mid-build state, diff stats, and team colours

**Files:**
- Modify: `watch.py` (mapping, `WatchState`, merge, diff stats, colours, mid-build seeding)
- Modify: `test_watch.py` (mapping, merge, colours, mid-build, diff tests)

**Interfaces:**
- Consumes: `focus.unbuilt`, `survey.survey`, `session.Step`, `session.WRITE`
- Produces:
  - `watch.branch_steps(wt_path, merge_base) -> list[Step]` — added files from diff + untracked from `ls-files -co`
  - `watch.map_path(...)`, `watch.nearest_building(...)`
  - `watch.load_colours(survey_dir) -> tuple[dict[str,int], dict[str,float]]`
  - `watch.save_colours_if_changed(survey_dir, teams, last_used, saved_snapshot) -> dict`
  - `watch.assign_colour(team, teams, last_used, now) -> int` — ninth team reuses LRU colour
  - `watch.WatchState`, `watch.Watch.state() -> WatchState`
  - `Watch.poll()` emits `merge` (main tip, 1 s gate, clean `ls-files -u`); `WatchState.diff_stats` populated

- [ ] **Step 1: Write the failing tests**

Append to `test_watch.py`:

```python
from test_survey import MONOREPO_LIKE

import focus
import survey
from session import Step, WRITE


class WatchMappingTest(unittest.TestCase):
    def setUp(self):
        self.main = fixture.make_repo(self, MONOREPO_LIKE)
        self.model = survey.survey(self.main)
        self.tracked = set(__import__("repo").Repo(self.main).files())

    def test_path_maps_to_module(self):
        kind, target = watch.map_path("hub/app.py", self.model, [], self.tracked)
        self.assertEqual((kind, target), ("module", "hub/app.py"))

    def test_unbuilt_path_maps_to_site(self):
        steps = [Step(WRITE, "Write", path="hub/newmod.py")]
        kind, target = watch.map_path("hub/newmod.py", self.model, steps, self.tracked)
        self.assertEqual(kind, "site")

    def test_unknown_file_maps_to_nearest_building(self):
        mod = watch.nearest_building("hub/deep/x.json", self.model)
        self.assertTrue(mod.startswith("hub/"))


class WatchDiffStatsTest(unittest.TestCase):
    def setUp(self):
        self.main = fixture.make_repo(self, {"hub/a.py": "x = 1\n"})
        self.wts = os.path.join(os.path.dirname(self.main), "wts")
        self.wt = fixture.worktree(self.main, os.path.join(self.wts, "w1"), "team/world/demo")
        self.clock = watch.FakeClock()
        self.survey = temp_survey(self)

    def test_diff_stats_after_file_event(self):
        w = watch.Watch(self.main, clock=self.clock, survey_dir=self.survey)
        w.poll()
        with open(os.path.join(self.wt, "hub/a.py"), "a", encoding="utf-8") as f:
            f.write("# two more lines\n#line2\n")
        self.clock.advance(1)
        w.poll()
        stats = w.state().diff_stats.get("w1")
        self.assertIsNotNone(stats)
        self.assertGreater(stats[0] + stats[1], 0)


class WatchMergeTest(unittest.TestCase):
    def setUp(self):
        self.main = fixture.make_repo(self, {"hub/a.py": "x = 1\n"})
        self.wts = os.path.join(os.path.dirname(self.main), "wts")
        self.wt = fixture.worktree(self.main, os.path.join(self.wts, "w1"), "team/world/demo")
        self.clock = watch.FakeClock()
        self.survey = temp_survey(self)

    def test_merge_emitted_when_main_moves_and_clean(self):
        fixture.commit(self.wt, {"hub/a.py": "x = 2\n"})
        fixture.git(self.main, "merge", "--no-ff", "-q", "team/world/demo", "-m", "merge")
        w = watch.Watch(self.main, clock=self.clock, survey_dir=self.survey)
        w.poll()
        self.clock.advance(1)
        merges = [e for e in w.poll() if e.kind == "merge"]
        self.assertEqual(len(merges), 1)
        self.assertTrue(w.state().main_moved_clean)


class WatchColoursTest(unittest.TestCase):
    def setUp(self):
        self.main = fixture.make_repo(self, {"a.py": "x\n"})
        self.survey = temp_survey(self)
        self.clock = watch.FakeClock()

    def test_team_keeps_colour_and_ninth_reuses_lru(self):
        teams, last = watch.load_colours(self.survey)
        now = self.clock.time()
        indices = []
        for name in ("t1", "t2", "t3", "t4", "t5", "t6", "t7", "t8", "t9"):
            self.clock.advance(10)
            indices.append(watch.assign_colour(name, teams, last, self.clock.time()))
        saved = watch.save_colours_if_changed(self.survey, teams, last, {})
        teams2, _ = watch.load_colours(self.survey)
        self.assertEqual(teams2["t1"], teams["t1"])
        self.assertEqual(indices[8], indices[0])


class WatchMidBuildTest(unittest.TestCase):
    def setUp(self):
        self.main = fixture.make_repo(self, MONOREPO_LIKE)
        self.wts = os.path.join(os.path.dirname(self.main), "wts")
        self.wt = fixture.worktree(self.main, os.path.join(self.wts, "w1"), "team/world/demo")
        self.clock = watch.FakeClock()
        self.survey = temp_survey(self)
        ledger = os.path.join(self.wt, ".superpowers/sdd/r1")
        os.makedirs(ledger, exist_ok=True)
        with open(os.path.join(ledger, "task-1-brief.md"), "w", encoding="utf-8") as f:
            f.write("brief\n")
        with open(os.path.join(self.wt, "hub/app.py"), "a", encoding="utf-8") as f:
            f.write("# mid\n")

    def test_mid_build_places_implementer_at_latest_change(self):
        w = watch.Watch(self.main, clock=self.clock, survey_dir=self.survey)
        w.poll()
        st = w.state()
        impl = [a for a in st.agents if a.agent.role == "implementer"][0]
        self.assertEqual(impl.latest_path, "hub/app.py")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m unittest test_watch.WatchMappingTest test_watch.WatchDiffStatsTest test_watch.WatchMergeTest test_watch.WatchColoursTest test_watch.WatchMidBuildTest -v`
Expected: FAIL

- [ ] **Step 3: Write minimal implementation**

Append to `watch.py`:

```python
import focus
import survey
from dataclasses import dataclass, field
from session import Step, WRITE

DIFF_INTERVAL = 2

PALETTE = [
    (90, 180, 90), (90, 140, 220), (200, 120, 200), (220, 180, 80),
    (120, 200, 180), (180, 100, 100), (140, 120, 200), (200, 200, 100),
]


@dataclass
class AgentState:
    agent: Agent
    status: str
    latest_path: str | None = None


@dataclass
class WatchState:
    agents: list[AgentState] = field(default_factory=list)
    scaffolded: dict[str, str] = field(default_factory=dict)
    sites: list[str] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)
    reviewer_tours: dict[str, list[str]] = field(default_factory=dict)
    diff_stats: dict[str, tuple[int, int]] = field(default_factory=dict)
    main_mid_merge: bool = False
    main_moved_clean: bool = False


def branch_steps(wt_path, merge_base):
    steps = []
    for line in _git(wt_path, "diff", "--name-status", merge_base).splitlines():
        parts = line.split("\t")
        if parts[0] == "A" and len(parts) > 1:
            steps.append(Step(WRITE, "Write", path=parts[1]))
    tracked = set(_git(wt_path, "ls-files").splitlines())
    listed = [p for p in _git(wt_path, "ls-files", "-co", "--exclude-standard", "-z").split("\0") if p]
    for rel in listed:
        if rel not in tracked:
            steps.append(Step(WRITE, "Write", path=rel))
    return steps


def _most_recent_path(wt_path, merge_base):
    best, best_m = None, -1
    for rel in {s.path for s in branch_steps(wt_path, merge_base)}:
        try:
            m = os.lstat(os.path.join(wt_path, rel)).st_mtime_ns
        except OSError:
            continue
        if m > best_m:
            best, best_m = rel, m
    return best


def _diff_numstat(wt_path, merge_base):
    added = removed = 0
    for line in _git(wt_path, "diff", "--numstat", merge_base).splitlines():
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        if parts[0] != "-":
            added += int(parts[0])
        if parts[1] != "-":
            removed += int(parts[1])
    return added, removed


def nearest_building(path, model):
    best, best_len = None, -1
    for mid, mod in model.modules.items():
        for candidate in [mid] + list(mod.members):
            folder = candidate.rsplit("/", 1)[0] + "/" if "/" in candidate else ""
            if path.startswith(folder) and len(folder) > best_len:
                best, best_len = mid, len(folder)
    return best


def map_path(path, model, steps, tracked):
    if path in model.modules or any(path in m.members for m in model.modules.values()):
        mid = path if path in model.modules else next(
            m.id for m in model.modules.values() if path in m.members)
        return "module", mid
    if path in focus.unbuilt(steps, model, tracked):
        return "site", path
    building = nearest_building(path, model)
    if building:
        return "building", building
    return "file", path


def _colours_path(survey_dir):
    return os.path.join(survey_dir, "watch.json")


def load_colours(survey_dir):
    path = _colours_path(survey_dir)
    if not os.path.isfile(path):
        return {}, {}
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    teams = {k: int(v) for k, v in data.get("teams", {}).items()}
    last_used = {k: float(v) for k, v in data.get("last_used", {}).items()}
    return teams, last_used


def save_colours_if_changed(survey_dir, teams, last_used, saved):
    current = {"teams": teams, "last_used": last_used}
    if saved.get("teams") == teams and saved.get("last_used") == last_used:
        return saved
    os.makedirs(survey_dir, exist_ok=True)
    with open(_colours_path(survey_dir), "w", encoding="utf-8") as f:
        json.dump(current, f, indent=2, sort_keys=True)
    return current


def assign_colour(team, teams, last_used, now):
    if team in teams:
        last_used[team] = now
        return teams[team]
    used = set(teams.values())
    free = [i for i in range(len(PALETTE)) if i not in used]
    if free:
        idx = free[0]
    else:
        lru_team = min(last_used, key=last_used.get)
        idx = teams[lru_team]
        del teams[lru_team]
        del last_used[lru_team]
    teams[team] = idx
    last_used[team] = now
    return idx
```

Extend `Watch.__init__`:

```python
        self._model = survey.survey(self.repo_root)
        self._tracked = set(__import__("repo").Repo(self.repo_root).files())
        self._teams, self._last_used = load_colours(self.survey_dir)
        self._colours_saved = {"teams": dict(self._teams), "last_used": dict(self._last_used)}
        self._last_diff: dict[str, float] = {}
        self._diff_stats: dict[str, tuple[int, int]] = {}
        self._main_mid_merge = False
        self._main_moved_clean = False
        self._reviewer_files: dict[str, list[str]] = {}
        self._flags: set[str] = set()
        for wt in self._worktrees:
            if wt.path == self.repo_root or not wt.branch:
                continue
            base = _git(self.repo_root, "merge-base", "HEAD", wt.branch).strip()
            for kind, agent_id, _ in scan_ledger(wt.path):
                if kind == "start":
                    self._open_briefs.setdefault(wt.name, set()).add(int(agent_id.rsplit("-", 1)[-1]))
                elif kind == "review_start":
                    self._open_reviews.setdefault(wt.name, set()).add(agent_id.split("/", 1)[1])
            impl = self._implementer(wt)
            latest = _most_recent_path(wt.path, base)
            if latest:
                self._latest_path[impl.id] = latest
```

Update `_poll_worktree` to refresh diff stats after file events:

```python
        had_files = False
        for kind, path in obs.poll():
            had_files = True
            ...
        if had_files:
            self._maybe_refresh_diff(wt, now)
```

Add helpers:

```python
    def _merge_base(self, wt):
        return _git(self.repo_root, "merge-base", "HEAD", wt.branch).strip()

    def _maybe_refresh_diff(self, wt, now):
        if now - self._last_diff.get(wt.name, 0) < DIFF_INTERVAL:
            return
        self._last_diff[wt.name] = now
        self._diff_stats[wt.name] = _diff_numstat(wt.path, self._merge_base(wt))

    def _poll_main(self, now):
        if now - self._last_main_poll < MAIN_POLL:
            return []
        self._last_main_poll = now
        events = []
        tip = _git(self.repo_root, "rev-parse", "HEAD").strip()
        unmerged = bool(_git(self.repo_root, "ls-files", "-u").strip())
        self._main_mid_merge = unmerged
        if tip != self._main_tip:
            if unmerged:
                self._main_tip = tip
            else:
                self._main_moved_clean = True
                events.append(Event("merge", None, None, now))
                self._main_tip = tip
        return events
```

Call `events.extend(self._poll_main(now))` at start of `poll()`.

On `review_start` in `_poll_worktree`:

```python
                base = self._merge_base(wt)
                tip = _git(wt.path, "rev-parse", "HEAD").strip()
                self._reviewer_files[agent_id] = [
                    l for l in _git(wt.path, "diff", "--name-only", f"{base}..{tip}").splitlines() if l]
```

Add `state()`:

```python
    def state(self) -> WatchState:
        agents = []
        for wt in self._worktrees:
            if wt.path == self.repo_root:
                continue
            if self._open_briefs.get(wt.name):
                impl = self._implementer(wt)
                if impl.id not in self._latest_path and wt.branch:
                    latest = _most_recent_path(wt.path, self._merge_base(wt))
                    if latest:
                        self._latest_path[impl.id] = latest
                status = "waiting" if impl.id not in self._latest_path else "working"
                agents.append(AgentState(impl, status, self._latest_path.get(impl.id)))
            for stem in self._open_reviews.get(wt.name, ()):
                rev = self._agent(f"{wt.name}/{stem}", "reviewer", wt)
                agents.append(AgentState(rev, "touring", None))
        for tail in self._transcripts.values():
            if tail._agent and tail._agent.role == "orchestrator":
                agents.append(AgentState(tail._agent, "idle", None))
        sites = []
        for wt in self._worktrees:
            if wt.path == self.repo_root or not self._shown(wt) or not wt.branch:
                continue
            steps = branch_steps(wt.path, self._merge_base(wt))
            assign_colour(wt.team, self._teams, self._last_used, self.clock.time())
            sites.extend(focus.unbuilt(steps, self._model, self._tracked))
        self._colours_saved = save_colours_if_changed(
            self.survey_dir, self._teams, self._last_used, self._colours_saved)
        return WatchState(agents, {}, sorted(set(sites)), sorted(self._flags),
                          dict(self._reviewer_files), dict(self._diff_stats),
                          self._main_mid_merge, self._main_moved_clean)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m unittest test_watch.WatchMappingTest test_watch.WatchDiffStatsTest test_watch.WatchMergeTest test_watch.WatchColoursTest test_watch.WatchMidBuildTest -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add watch.py test_watch.py
git commit -m "Map paths to modules and sites and detect merges"
```

---

### Task 6: CLI, end-to-end event order, read-only guarantees, full suite

**Files:**
- Modify: `towncode.py` (add `watch` subcommand with injectable `sleep`)
- Create: `test_watch_e2e.py`
- Modify: `test_towncode.py` (plain watch exits non-zero)

**Interfaces:**
- Produces:
  - `towncode._watch(args, sleep=time.sleep)` — CLI loop; tests call `_watch` with `sleep=lambda _: None`
  - `towncode watch PATH --events` prints `{kind}\t{agent_id|-}\t{path|-}`
  - `towncode watch PATH` → stderr message, exit **2**

- [ ] **Step 1: Write the failing tests**

Create `test_watch_e2e.py`:

```python
import contextlib
import io
import os
import shutil
import tempfile
import unittest

import fixture
import towncode
import untouched
import watch


class WatchE2ETest(unittest.TestCase):
    def setUp(self):
        self.main = fixture.make_repo(self, {"hub/a.py": "x = 1\n"})
        self.wts = os.path.join(os.path.dirname(self.main), "wts")
        self.clock = watch.FakeClock()
        self.survey = tempfile.mkdtemp(prefix="watch-e2e-")
        self.addCleanup(shutil.rmtree, self.survey)

    def _run_script(self):
        wt = fixture.worktree(self.main, os.path.join(self.wts, "demo"), "team/world/demo")
        ledger = os.path.join(wt, ".superpowers/sdd/run-1")
        os.makedirs(ledger, exist_ok=True)
        events = []
        w = watch.Watch(self.main, clock=self.clock, survey_dir=self.survey)

        def poll():
            events.extend(w.poll())
            self.clock.advance(1)

        poll()
        with open(os.path.join(ledger, "task-1-brief.md"), "w", encoding="utf-8") as f:
            f.write("brief\n")
        poll()
        with open(os.path.join(wt, "hub/a.py"), "a", encoding="utf-8") as f:
            f.write("# e\n")
        poll()
        with open(os.path.join(wt, "hub/new.py"), "w", encoding="utf-8") as f:
            f.write("y = 2\n")
        poll()
        fixture.commit(wt, {"hub/a.py": "x = 2\n", "hub/new.py": "y = 2\n"},
                       paths=["hub/a.py", "hub/new.py"])
        poll()
        with open(os.path.join(ledger, "task-1-report.md"), "w", encoding="utf-8") as f:
            f.write("done\n")
        poll()
        with open(os.path.join(ledger, "review-task-1.md"), "w", encoding="utf-8") as f:
            f.write("review\n")
        poll()
        with open(os.path.join(ledger, "review-task-1-result.md"), "w", encoding="utf-8") as f:
            f.write("ok\n")
        poll()
        fixture.git(self.main, "merge", "--no-ff", "-q", "team/world/demo", "-m", "merge")
        poll()
        fixture.git(self.main, "worktree", "remove", "--force", wt)
        self.clock.advance(5)
        poll()
        return [e.kind for e in events]

    def test_event_order_for_fake_run(self):
        kinds = self._run_script()
        expected = ["start", "edit", "create", "commit", "finish",
                    "review_start", "review_finish", "merge", "leave"]
        filtered = [k for k in kinds if k in expected]
        self.assertEqual(filtered, expected)

    def test_watch_leaves_repo_and_worktrees_untouched(self):
        before_main = untouched.fingerprint(self.main)
        wt_path = fixture.worktree(self.main, os.path.join(self.wts, "x"), "team/x/y")
        before_wt = untouched.fingerprint(wt_path)
        w = watch.Watch(self.main, clock=self.clock, survey_dir=self.survey)
        for _ in range(5):
            w.poll()
            self.clock.advance(1)
        self.assertEqual(untouched.differences(before_main, untouched.fingerprint(self.main)), {})
        self.assertEqual(untouched.differences(before_wt, untouched.fingerprint(wt_path)), {})


class TowncodeWatchCLITest(unittest.TestCase):
    def setUp(self):
        self.root = fixture.make_repo(self, {"a.py": "x\n"})

    def test_plain_watch_exits_nonzero(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            code = towncode.main(["watch", self.root])
        self.assertEqual(code, 2)
        self.assertIn("Phase 3", err.getvalue())

    def test_events_loop_uses_injectable_sleep(self):
        root = fixture.make_repo(self, {"a.py": "x\n"})
        sleeps = []
        args = towncode._parser().parse_args(["watch", root, "--events"])
        with contextlib.redirect_stdout(io.StringIO()):
            code = towncode._watch(args, sleep=lambda s: sleeps.append(s) or (_ for _ in ()).throw(
                KeyboardInterrupt))
        self.assertEqual(code, 0)
        self.assertEqual(sleeps, [1])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m unittest test_watch_e2e -v`
Expected: FAIL

- [ ] **Step 3: Write minimal implementation**

Add to `towncode.py`:

```python
import watch as watch_mod


def _format_event(event):
    agent = event.agent.id if event.agent else "-"
    path = event.path or "-"
    return f"{event.kind}\t{agent}\t{path}"


def _watch(args, sleep=time.sleep):
    if not args.events:
        print("the watch view arrives in Phase 3", file=sys.stderr)
        return 2
    w = watch_mod.Watch(args.path)
    try:
        while True:
            for event in w.poll():
                print(_format_event(event))
            sleep(1)
    except KeyboardInterrupt:
        pass
    return 0
```

Add parser and `COMMANDS["watch"] = _watch`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m unittest test_watch_e2e -v`
Expected: PASS

- [ ] **Step 5: Run full test suite**

Run: `.venv/bin/python -m unittest`
Expected: all tests PASS

- [ ] **Step 6: Commit**

```bash
git add towncode.py test_watch_e2e.py
git commit -m "Add towncode watch --events and end-to-end event stream test"
```

---

## Self-Review

**Spec coverage:** Observer baseline + changes — Task 2. Worktrees on init + 5 s — Task 3. Ledger, commits, leave — Task 3. Transcripts + subagent read counts — Task 4. Mapping, sites (added + untracked), diff numstat, mid-build from git, merge, colours LRU — Task 5. CLI + e2e + untouched — Task 6. RGB distance test remains **Phase 3**. Re-survey on merge remains **Phase 3** (`main_moved_clean` only).

**Placeholder scan:** No TBD/TODO; single `match_subagent` and `_role_for_transcript`; all test `Watch` calls pass `survey_dir`; transcript tests pass `home`.

**Type consistency:** `load_colours -> (teams, last_used)`; `save_colours_if_changed`; `finish_read_count(worktree_name)`; `_latest_path` set in `_poll_worktree` and seeded from git in `__init__`/`state()`.

**Rulings:** Plain watch exit 2; event format tab-separated; orchestrator via `subagents/*.jsonl` or `Task` tool name; CLI `sleep` injectable for tests only.
