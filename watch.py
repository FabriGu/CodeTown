"""Discover worktrees, tail transcripts, and merge sources into one event stream."""

import glob
import json
import math
import os
import re
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

import focus
import labels
import session
import survey
from events import Agent, Event
from observer import Observer
from repo import GIT_ENV, GIT_FLAGS
from session import Step, WRITE
from transcripts import TranscriptTail, WorktreePaths, discover_transcripts

TEAM_BRANCH = re.compile(r"^team/([^/]+)/")
LEDGER = re.compile(
    r"^(task-(\d+)-brief\.md|task-(\d+)-report\.md|(review-[^/\\]+)-result\.md|(review-[^/\\]+)\.md)$")
LEDGER_KIND_RANK = {"start": 0, "finish": 1, "review_start": 2, "review_finish": 3}
ACTIVE_SECONDS = 2 * 3600
WORKTREE_INTERVAL = 5
SHOWN_POLL = 1
HIDDEN_POLL = 10
MAIN_POLL = 1
DIFF_INTERVAL = 2
TRANSCRIPT_INTERVAL = 1
TRANSCRIPT_RESCAN = 10
LEDGER_PREFIX = ".superpowers/"
LEDGER_EXCLUDE = ":(exclude).superpowers"

# Copied from mock_roles (production must not import mock_roles — it pulls Pillow).
_USES = (80, 168, 255)
_USED_BY = (236, 96, 196)
_FOCUS = (250, 250, 250)
_SITE = (232, 128, 48)
_REVIEWER_GREY = (150, 150, 156)

RESERVED = {
    "fire": labels.FIRE_BG,
    "amber": labels.LOUD_BG,
    "uses": _USES,
    "used_by": _USED_BY,
    "focus": _FOCUS,
    "site": _SITE,
    "reviewer_grey": _REVIEWER_GREY,
}

# Verified 80.72 min distance to every reserved colour; 60.04 min pairwise.
PALETTE = [(165, 91, 91), (140, 113, 35), (165, 165, 74), (85, 89, 49), (103, 165, 41), (27, 89, 22), (49, 140, 49), (91, 165, 103)]


def rgb_distance(a, b):
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


def min_palette_distance():
    return min(rgb_distance(c, r) for c in PALETTE for r in RESERVED.values())


def min_palette_pairwise_distance():
    return min(rgb_distance(PALETTE[i], PALETTE[j])
                for i in range(len(PALETTE)) for j in range(i + 1, len(PALETTE)))


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


def _git_safe(root, *args):
    try:
        return _git(root, *args)
    except subprocess.CalledProcessError:
        return None


@dataclass(frozen=True)
class WorktreeInfo:
    name: str
    path: str
    branch: str
    team: str


def _parse_worktree_blocks(text):
    found = []
    block = {}
    for line in text.splitlines() + [""]:
        if not line.strip():
            if block:
                path = block["worktree"]
                branch = block.get("branch", "").removeprefix("refs/heads/")
                name = os.path.basename(path.rstrip("/"))
                prunable = "prunable" in block
                found.append((WorktreeInfo(name, path, branch, team_of(branch, name)), prunable))
                block = {}
            continue
        key, _, value = line.partition(" ")
        block[key] = value
    return found


def parse_worktrees(text):
    return [info for info, _prunable in _parse_worktree_blocks(text)]


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
        try:
            mtime = os.path.getmtime(path)
        except OSError:
            mtime = 0.0
        if fname.endswith("-brief.md"):
            kind = "start"
            agent_id = f"{name}/task-{m.group(2)}"
        elif fname.endswith("-report.md"):
            kind = "finish"
            agent_id = f"{name}/task-{m.group(3)}"
        elif fname.endswith("-result.md"):
            kind = "review_finish"
            agent_id = f"{name}/{m.group(4)}"
        else:
            kind = "review_start"
            agent_id = f"{name}/{m.group(5)}"
        events.append((kind, agent_id, rel, mtime))
    events.sort(key=lambda item: (item[3], LEDGER_KIND_RANK[item[0]]))
    return [(kind, agent_id, rel) for kind, agent_id, rel, _mtime in events]


def _is_ledger_path(path):
    return path == ".superpowers" or path.startswith(LEDGER_PREFIX)


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
    flags: dict[str, str] = field(default_factory=dict)
    reviewer_tours: dict[str, list[str]] = field(default_factory=dict)
    diff_stats: dict[str, tuple[int, int]] = field(default_factory=dict)
    main_mid_merge: bool = False
    main_moved_clean: bool = False
    team_colours: dict[str, int] = field(default_factory=dict)
    worktree_count: int = 0
    worktree_teams: dict[str, str] = field(default_factory=dict)
    site_teams: dict[str, str] = field(default_factory=dict)
    main_tip: str = ""
    worktree_branches: dict[str, str] = field(default_factory=dict)


@dataclass
class _BranchView:
    steps: list
    diff_stats: tuple[int, int]
    latest_path: str | None
    module_times: dict[str, tuple[str, float]]


def branch_steps(wt_path, merge_base):
    steps = []
    for line in _git(wt_path, "diff", "--name-status", merge_base, "--", ".", LEDGER_EXCLUDE).splitlines():
        parts = line.split("\t")
        if parts and parts[0].startswith("A") and len(parts) > 1:
            steps.append(Step(WRITE, "Write", path=parts[1]))
    tracked = set(_git(wt_path, "ls-files").splitlines())
    listed = [p for p in _git(wt_path, "ls-files", "-co", "--exclude-standard", "-z").split("\0") if p]
    for rel in listed:
        if rel not in tracked and not _is_ledger_path(rel):
            steps.append(Step(WRITE, "Write", path=rel))
    return steps


def _branch_changed_paths(wt_path, merge_base):
    paths = []
    for line in _git(wt_path, "diff", "--name-status", merge_base, "--", ".", LEDGER_EXCLUDE).splitlines():
        parts = line.split("\t")
        if not parts:
            continue
        status = parts[0]
        if status.startswith("D"):
            paths.append((parts[1], "D"))
        elif status.startswith("R") and len(parts) >= 3:
            paths.append((parts[2], status[0]))
        elif len(parts) >= 2:
            paths.append((parts[1], status[0]))
    tracked = set(_git(wt_path, "ls-files").splitlines())
    for rel in _git(wt_path, "ls-files", "-co", "--exclude-standard", "-z").split("\0"):
        if rel and rel not in tracked and not _is_ledger_path(rel):
            paths.append((rel, "A"))
    return paths


def _path_mtime(wt_path, rel):
    try:
        return os.lstat(os.path.join(wt_path, rel)).st_mtime_ns
    except OSError:
        return None


def _latest_changed_path(wt_path, merge_base):
    best, best_m = None, -1
    for rel, status in _branch_changed_paths(wt_path, merge_base):
        if status == "D":
            continue
        m = _path_mtime(wt_path, rel)
        if m is not None and m > best_m:
            best, best_m = rel, m
    return best


def _diff_numstat(wt_path, merge_base):
    added = removed = 0
    for line in _git(wt_path, "diff", "--numstat", merge_base, "--", ".", LEDGER_EXCLUDE).splitlines():
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
    if saved.get("teams") == teams:
        return saved
    current = {"teams": dict(teams), "last_used": dict(last_used)}
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
    teams[team] = idx
    last_used[team] = now
    return idx


class Watch:
    def __init__(self, repo_root, *, home="~", clock=None, survey_dir=None, model=None):
        self.repo_root = os.path.realpath(repo_root)
        self.home = os.path.expanduser(home)
        self.clock = clock or RealClock()
        if survey_dir is None:
            import towncode
            survey_dir = towncode.output_dir(repo_root)
        self.survey_dir = survey_dir
        self._worktrees: list[WorktreeInfo] = []
        self._observers: dict[str, Observer] = {}
        self._last_poll: dict[str, float] = {}
        self._last_obs_poll: dict[str, float] = {}
        self._last_ledger_poll: dict[str, float] = {}
        self._last_main_poll = 0.0
        self._last_commit: dict[str, str] = {}
        self._main_tip = _git(self.repo_root, "rev-parse", "HEAD").strip()
        self._seen_ledger: set[tuple[str, str, str]] = set()
        self._known_wt_names: set[str] = set()
        self._recent: dict[str, float] = {}
        self._open_briefs: dict[str, set[int]] = {}
        self._open_reviews: dict[str, set[str]] = {}
        self._finished_impl: dict[str, str] = {}
        self._latest_path: dict[str, str] = {}
        self._prunable_names: set[str] = set()
        self._merged_cache: dict[str, tuple[str, str, bool]] = {}
        self._merged_branches: set[str] = set()
        self._merged_tips_key: tuple | None = None
        self._creation_tip_cache: dict[str, str | None] = {}
        self._main_branch: str | None = None
        self._unmerged_checked = False
        self._force_unmerged_check = False
        self._observer_pool = ThreadPoolExecutor(max_workers=8)
        self._wt_paths: WorktreePaths | None = None
        common = _git(self.repo_root, "rev-parse", "--git-common-dir").strip()
        if not os.path.isabs(common):
            common = os.path.join(self.repo_root, common)
        self._git_common_dir = os.path.realpath(common)
        self._poll_main_tip = self._main_tip
        self._transcripts: dict[str, TranscriptTail] = {}
        self._last_transcript_scan = 0.0
        self._last_transcript_poll = 0.0
        self._subagent_reads: dict[str, int] = {}
        self._diff_stats: dict[str, tuple[int, int]] = {}
        self._model = model if model is not None else survey.survey(self.repo_root)
        self._tracked = set(__import__("repo").Repo(self.repo_root).files())
        self._teams, self._last_used = load_colours(self.survey_dir)
        self._colours_saved = {"teams": dict(self._teams), "last_used": dict(self._last_used)}
        self._surveyed_main_tip = self._main_tip
        self._remembered_main_tip = self._main_tip
        self._main_mid_merge = False
        self._main_moved_clean = False
        self._reviewer_files: dict[str, list[str]] = {}
        self._flags: dict[str, str] = {}
        self._scaffolded: dict[str, str] = {}
        self._sites: list[str] = []
        self._branch_views: dict[str, _BranchView] = {}
        self._branch_dirty: dict[str, bool] = {}
        self._last_diff: dict[str, float] = {}
        self._merge_base_cache: dict[str, tuple[tuple[str, str], str]] = {}
        self._path_times: dict[tuple[str, str], float] = {}
        self._branch_tips: dict[str, str] = {}
        self._wt_seeded = False
        self._refresh_main_branch()
        self._refresh_worktrees()
        self._last_wt_list = self.clock.monotonic()
        self._known_wt_names = {w.name for w in self._worktrees if w.path != self.repo_root}
        self._refresh_branch_tips()
        self._update_main_tip_from_batch()
        self._remembered_main_tip = self._poll_main_tip
        self._refresh_merged_branches()
        for wt in self._worktrees:
            if wt.path != self.repo_root:
                tip = self._worktree_tip(wt)
                if tip is not None:
                    self._last_commit[wt.name] = tip
        self._init_worktrees()
        self._wt_seeded = True

    def close(self):
        pool = getattr(self, "_observer_pool", None)
        if pool is not None:
            pool.shutdown(wait=True)
            self._observer_pool = None

    def note_resurvey(self, model, surveyed_tip: str):
        self._model = model
        self._surveyed_main_tip = surveyed_tip
        self._main_moved_clean = False

    def worktrees(self):
        return list(self._worktrees)

    def state(self) -> WatchState:
        agents = []
        for wt in self._worktrees:
            if wt.path == self.repo_root or not self._shown(wt):
                continue
            impl = self._implementer(wt)
            if self._open_briefs.get(wt.name) or self._latest_path.get(impl.id):
                status = "waiting" if impl.id not in self._latest_path else "working"
                agents.append(AgentState(impl, status, self._latest_path.get(impl.id)))
            for stem in self._open_reviews.get(wt.name, ()):
                rev = self._agent(f"{wt.name}/{stem}", "reviewer", wt)
                agents.append(AgentState(rev, "touring", None))
        for tail in self._transcripts.values():
            if tail._agent and tail._agent.role == "orchestrator":
                agents.append(AgentState(tail._agent, "idle", None))
        site_teams = self._site_teams()
        worktree_teams = {wt.name: wt.team for wt in self._worktrees
                          if wt.path != self.repo_root}
        worktree_count = len(worktree_teams)
        worktree_branches = {wt.name: wt.branch for wt in self._worktrees
                             if wt.path != self.repo_root and wt.branch}
        return WatchState(
            agents, dict(self._scaffolded), list(self._sites), dict(self._flags),
            dict(self._reviewer_files), dict(self._diff_stats),
            self._main_mid_merge, self._main_moved_clean,
            dict(self._teams), worktree_count, worktree_teams, site_teams,
            main_tip=self._poll_main_tip, worktree_branches=worktree_branches)

    def _site_teams(self):
        teams = {}
        for wt in self._worktrees:
            if wt.path == self.repo_root or not wt.branch:
                continue
            view = self._branch_views.get(wt.name)
            if not view:
                continue
            for path in focus.unbuilt(view.steps, self._model, self._tracked):
                teams[path] = wt.team
        return teams

    def finish_read_count(self, worktree_name):
        return self._subagent_reads.get(worktree_name, 0)

    def finish_summary(self, worktree_name):
        reads = self.finish_read_count(worktree_name)
        added, removed = self._diff_stats.get(worktree_name, (0, 0))
        changed = added + removed
        return f"read {reads} files, changed {changed}"

    def _on_subagent(self, wt_name, count):
        self._subagent_reads[wt_name] = count

    def _ensure_team_colour(self, team):
        if not team:
            return
        before = dict(self._teams)
        assign_colour(team, self._teams, self._last_used, self.clock.time())
        if self._teams != before:
            self._colours_saved = save_colours_if_changed(
                self.survey_dir, self._teams, self._last_used, self._colours_saved)

    def _touch_team(self, wt):
        if wt.team:
            self._last_used[wt.team] = self.clock.time()

    def _merge_base(self, wt):
        wt_tip = self._last_commit.get(wt.name)
        if wt_tip is None:
            out = _git_safe(wt.path, "rev-parse", "HEAD")
            wt_tip = out.strip() if out else ""
        main_tip = self._poll_main_tip
        key = (wt_tip, main_tip)
        cached = self._merge_base_cache.get(wt.name)
        if cached and cached[0] == key:
            return cached[1]
        if not wt.branch:
            return ""
        out = _git_safe(self.repo_root, "merge-base", "HEAD", wt.branch)
        if not out or not out.strip():
            return ""
        base = out.strip()
        self._merge_base_cache[wt.name] = (key, base)
        return base

    def _path_change_time(self, wt, path):
        key = (wt.name, path)
        if key in self._path_times:
            return self._path_times[key]
        m = _path_mtime(wt.path, path)
        return m / 1e9 if m is not None else self.clock.time()

    def _refresh_branch_view(self, wt):
        if not wt.branch:
            return False
        try:
            base = self._merge_base(wt)
            if not base:
                return False
            changed = _branch_changed_paths(wt.path, base)
            steps = branch_steps(wt.path, base)
            diff_stats = _diff_numstat(wt.path, base)
            latest = None
            best_m = -1
            module_times = {}
            for path, status in changed:
                if status != "D":
                    m = _path_mtime(wt.path, path)
                    if m is not None and m > best_m:
                        latest, best_m = path, m
                if _is_ledger_path(path):
                    continue
                kind, target = map_path(path, self._model, steps, self._tracked)
                if kind != "module":
                    continue
                module_times[target] = (wt.team, self._path_change_time(wt, path))
            self._branch_views[wt.name] = _BranchView(steps, diff_stats, latest, module_times)
            self._diff_stats[wt.name] = diff_stats
            if latest:
                self._latest_path.setdefault(self._implementer(wt).id, latest)
            return True
        except subprocess.CalledProcessError:
            return False

    def _recompute_derived(self):
        scaffold: dict[str, tuple[str, float]] = {}
        for wt in self._worktrees:
            if wt.path == self.repo_root or not wt.branch or self._is_merged(wt):
                continue
            view = self._branch_views.get(wt.name)
            if not view:
                continue
            for mod, (team, when) in view.module_times.items():
                prev = scaffold.get(mod)
                if prev is None or when >= prev[1]:
                    scaffold[mod] = (team, when)
        self._scaffolded = {mod: team for mod, (team, _when) in scaffold.items()}
        sites = []
        for wt in self._worktrees:
            if wt.path == self.repo_root or not self._shown(wt) or not wt.branch:
                continue
            view = self._branch_views.get(wt.name)
            if view:
                sites.extend(focus.unbuilt(view.steps, self._model, self._tracked))
        self._sites = sorted(set(sites))

    def _drop_worktree_view(self, name):
        self._branch_views.pop(name, None)
        self._diff_stats.pop(name, None)
        self._branch_dirty.pop(name, None)
        self._last_diff.pop(name, None)
        self._merge_base_cache.pop(name, None)

    def _maybe_refresh_branch(self, wt, now):
        if not self._branch_dirty.get(wt.name):
            return
        if now - self._last_diff.get(wt.name, 0) < DIFF_INTERVAL:
            return
        self._last_diff[wt.name] = now
        if self._refresh_branch_view(wt):
            self._branch_dirty[wt.name] = False
            self._recompute_derived()

    def _seed_worktree_view(self, wt):
        if wt.path == self.repo_root or not wt.branch or self._is_merged(wt):
            return
        tip = self._worktree_tip(wt)
        if tip is not None:
            self._last_commit[wt.name] = tip
        self._branch_dirty[wt.name] = True
        if self._refresh_branch_view(wt):
            self._branch_dirty[wt.name] = False
            view = self._branch_views.get(wt.name)
            if view and (view.latest_path or view.diff_stats != (0, 0)):
                self._note_activity(wt.name)

    def _apply_ledger(self, wt, kind, agent_id):
        if kind == "start":
            self._open_briefs.setdefault(wt.name, set()).add(int(agent_id.rsplit("-", 1)[-1]))
        elif kind == "finish":
            self._open_briefs.get(wt.name, set()).discard(int(agent_id.rsplit("-", 1)[-1]))
            self._finished_impl[wt.name] = agent_id
        elif kind == "review_start":
            self._open_reviews.setdefault(wt.name, set()).add(agent_id.split("/", 1)[1])
        elif kind == "review_finish":
            self._open_reviews.get(wt.name, set()).discard(agent_id.split("/", 1)[1])

    def _seed_ledger(self, wt):
        for kind, agent_id, _rel in scan_ledger(wt.path):
            self._apply_ledger(wt, kind, agent_id)
            self._seen_ledger.add((wt.name, kind, agent_id))

    def _init_worktrees(self):
        for wt in self._worktrees:
            if wt.path == self.repo_root or not wt.branch:
                continue
            self._ensure_team_colour(wt.team)
            self._seed_ledger(wt)
            if not self._is_merged(wt):
                self._seed_worktree_view(wt)
        self._recompute_derived()

    def _plant_flag(self, wt, agent_id):
        path = self._latest_path.get(agent_id)
        if not path:
            return
        kind, target = map_path(path, self._model,
                                self._branch_views.get(wt.name, _BranchView([], (0, 0), None, {})).steps,
                                self._tracked)
        building = target if kind == "module" else nearest_building(path, self._model)
        if building:
            self._flags[wt.name] = building

    def _refresh_main_branch(self):
        out = _git_safe(self.repo_root, "symbolic-ref", "-q", "HEAD")
        self._main_branch = out.strip().removeprefix("refs/heads/") if out else None

    def _update_main_tip_from_batch(self):
        if self._main_branch and self._main_branch in self._branch_tips:
            self._poll_main_tip = self._branch_tips[self._main_branch]
        else:
            tip_out = _git_safe(self.repo_root, "rev-parse", "HEAD")
            if tip_out:
                self._poll_main_tip = tip_out.strip()

    def _refresh_merged_branches(self):
        main_tip = self._poll_main_tip
        tips_key = (main_tip, frozenset(self._branch_tips.items()))
        if tips_key == self._merged_tips_key:
            return
        out = _git_safe(self.repo_root, "for-each-ref", f"--merged={main_tip}",
                        "--format=%(refname:short)", "refs/heads")
        self._merged_branches = {line for line in out.splitlines() if line} if out else set()
        self._merged_tips_key = tips_key
        self._merged_cache.clear()

    def _refresh_wt_paths(self):
        self._wt_paths = WorktreePaths(self.repo_root, self._worktrees)
        for tail in self._transcripts.values():
            tail.worktree_paths = self._wt_paths

    def _poll_main(self, now):
        if now - self._last_main_poll < MAIN_POLL:
            return []
        self._last_main_poll = now
        events = []
        self._update_main_tip_from_batch()
        tip = self._poll_main_tip
        tip_moved = tip != self._remembered_main_tip
        if (not self._unmerged_checked or tip_moved or self._main_mid_merge
                or self._force_unmerged_check):
            unmerged_out = _git_safe(self.repo_root, "ls-files", "-u")
            unmerged = bool(unmerged_out and unmerged_out.strip())
            self._main_mid_merge = unmerged
            self._unmerged_checked = True
            self._force_unmerged_check = False
        self._main_moved_clean = tip != self._surveyed_main_tip and not self._main_mid_merge
        if tip == self._remembered_main_tip:
            return events
        if self._main_mid_merge:
            return events
        merged_wts = [wt for wt in self._worktrees
                      if wt.path != self.repo_root and wt.branch and self._is_merged(wt)]
        if merged_wts:
            for wt in merged_wts:
                events.append(Event("merge", self._merged_implementer(wt), None, now))
                self._flags.pop(wt.name, None)
                self._drop_worktree_view(wt.name)
        else:
            events.append(Event("merge", None, None, now))
        self._remembered_main_tip = tip
        if merged_wts:
            self._recompute_derived()
        return events

    def _refresh_worktrees(self):
        out = _git_safe(self.repo_root, "worktree", "list", "--porcelain")
        if out is None:
            return
        blocks = _parse_worktree_blocks(out)
        prev_names = {w.name for w in self._worktrees if w.path != self.repo_root}
        prev_teams = {w.name: w.team for w in self._worktrees}
        self._worktrees = [info for info, _prunable in blocks]
        self._prunable_names = {info.name for info, prunable in blocks if prunable}
        for wt in self._worktrees:
            if wt.path == self.repo_root:
                continue
            if wt.name not in prev_teams or prev_teams.get(wt.name) != wt.team:
                self._ensure_team_colour(wt.team)
            if self._wt_seeded and wt.name not in prev_names and not self._is_merged(wt):
                self._seed_worktree_view(wt)
        gone = prev_names - {w.name for w in self._worktrees if w.path != self.repo_root}
        new = {w.name for w in self._worktrees if w.path != self.repo_root} - prev_names
        for name in gone:
            self._drop_worktree_view(name)
        if gone or new:
            self._recompute_derived()
        self._refresh_wt_paths()

    def _branch_creation_tip(self, branch):
        if branch in self._creation_tip_cache:
            return self._creation_tip_cache[branch]
        tip = self._branch_creation_tip_from_file(branch)
        if tip is None:
            out = _git_safe(self.repo_root, "log", "-g", "--format=%H", f"refs/heads/{branch}")
            if out:
                lines = [line for line in out.splitlines() if line.strip()]
                tip = lines[-1].strip() if lines else None
        self._creation_tip_cache[branch] = tip
        return tip

    def _branch_creation_tip_from_file(self, branch):
        log_path = os.path.join(self._git_common_dir, "logs", "refs", "heads", *branch.split("/"))
        try:
            with open(log_path, encoding="utf-8", errors="replace") as f:
                first = f.readline().strip()
                if first:
                    parts = first.split()
                    if len(parts) >= 2:
                        return parts[1]
        except OSError:
            pass
        return None

    def _branch_merged(self, wt: WorktreeInfo, wt_tip: str, main_tip: str) -> bool:
        if not wt.branch:
            return False
        if wt.branch not in self._merged_branches:
            return False
        oldest = self._branch_creation_tip(wt.branch)
        if oldest is not None:
            return wt_tip != oldest
        return wt_tip != main_tip

    def _refresh_branch_tips(self):
        tips = {}
        out = _git_safe(self.repo_root, "for-each-ref", "--format=%(refname) %(objectname)",
                        "refs/heads")
        if out:
            for line in out.splitlines():
                parts = line.split(None, 1)
                if len(parts) == 2:
                    tips[parts[0].removeprefix("refs/heads/")] = parts[1]
        self._branch_tips = tips

    def _worktree_tip(self, wt: WorktreeInfo) -> str | None:
        if wt.branch and wt.branch in self._branch_tips:
            return self._branch_tips[wt.branch]
        out = _git_safe(wt.path, "rev-parse", "HEAD")
        return out.strip() if out else None

    def _is_merged(self, wt: WorktreeInfo) -> bool:
        wt_tip = self._worktree_tip(wt)
        if wt_tip is None:
            return False
        main_tip = self._poll_main_tip
        cached = self._merged_cache.get(wt.name)
        if cached and cached[0] == wt_tip and cached[1] == main_tip:
            return cached[2]
        merged = self._branch_merged(wt, wt_tip, main_tip)
        self._merged_cache[wt.name] = (wt_tip, main_tip, merged)
        return merged

    def _ledger_open(self, wt: WorktreeInfo) -> bool:
        return bool(self._open_briefs.get(wt.name) or self._open_reviews.get(wt.name))

    def _shown(self, wt: WorktreeInfo) -> bool:
        if wt.path == self.repo_root:
            return False
        if self._is_merged(wt):
            return False
        if wt.name in self._flags:
            return True
        if self._ledger_open(wt):
            return True
        last = self._recent.get(wt.name)
        if last is None:
            return False
        return self.clock.time() - last < ACTIVE_SECONDS

    def _agent(self, agent_id, role, wt: WorktreeInfo) -> Agent:
        return Agent(agent_id, role, wt.team, wt.name)

    def _implementer(self, wt: WorktreeInfo) -> Agent:
        briefs = sorted(self._open_briefs.get(wt.name, set()))
        if briefs:
            return self._agent(f"{wt.name}/task-{briefs[-1]}", "implementer", wt)
        return self._agent(wt.name, "implementer", wt)

    def _merged_implementer(self, wt: WorktreeInfo) -> Agent:
        agent_id = self._finished_impl.get(wt.name)
        if agent_id:
            return self._agent(agent_id, "implementer", wt)
        return self._implementer(wt)

    def _leave_agent(self, name):
        wt = WorktreeInfo(name, "", "", "")
        agent_id = self._finished_impl.get(name)
        if agent_id:
            return self._agent(agent_id, "implementer", wt)
        return self._implementer(wt)

    def _note_activity(self, wt_name):
        self._recent[wt_name] = self.clock.time()

    def _apply_observer_events(self, wt: WorktreeInfo, obs_events, now) -> tuple[list[Event], bool]:
        events = []
        had_files = False
        agent = self._implementer(wt)
        for kind, path in obs_events:
            if _is_ledger_path(path):
                continue
            had_files = True
            self._note_activity(wt.name)
            self._touch_team(wt)
            self._path_times[(wt.name, path)] = self.clock.time()
            self._flags.pop(wt.name, None)
            self._latest_path[agent.id] = path
            events.append(Event(kind, agent, path, now))
        return events, had_files

    def _poll_observer(self, wt: WorktreeInfo):
        obs = self._observers.setdefault(wt.path, Observer(wt.path))
        return obs.poll()

    def _poll_worktree(self, wt: WorktreeInfo, interval: float,
                       observer_events=None) -> list[Event]:
        now = self.clock.monotonic()
        self._last_poll[wt.name] = now
        events = []
        agent = self._implementer(wt)
        had_files = False
        if not self._is_merged(wt):
            if observer_events is not None:
                try:
                    obs_events, had_files = self._apply_observer_events(
                        wt, observer_events, now)
                    events.extend(obs_events)
                except subprocess.CalledProcessError:
                    return events
            else:
                last_obs = self._last_obs_poll.get(wt.name)
                if last_obs is None or now - last_obs >= interval:
                    self._last_obs_poll[wt.name] = now
                    try:
                        obs_events, had_files = self._apply_observer_events(
                            wt, self._poll_observer(wt), now)
                        events.extend(obs_events)
                    except subprocess.CalledProcessError:
                        return events
        last_ledger = self._last_ledger_poll.get(wt.name)
        if last_ledger is None or now - last_ledger >= interval:
            self._last_ledger_poll[wt.name] = now
            for kind, agent_id, _ledger in scan_ledger(wt.path):
                key = (wt.name, kind, agent_id)
                if key in self._seen_ledger:
                    continue
                self._seen_ledger.add(key)
                self._touch_team(wt)
                role = {"start": "implementer", "finish": "implementer",
                        "review_start": "reviewer", "review_finish": "reviewer"}[kind]
                events.append(Event(kind, self._agent(agent_id, role, wt), None, now))
                self._apply_ledger(wt, kind, agent_id)
                if kind == "finish":
                    self._plant_flag(wt, agent_id)
                elif kind == "review_start":
                    base = self._merge_base(wt)
                    wt_tip = self._worktree_tip(wt) or ""
                    self._reviewer_files[agent_id] = [
                        p for p in _git(wt.path, "diff", "--name-only",
                                       f"{base}..{wt_tip}").splitlines()
                        if p and not _is_ledger_path(p)]
            tip = self._worktree_tip(wt)
            if tip is None:
                if had_files:
                    self._branch_dirty[wt.name] = True
                    self._maybe_refresh_branch(wt, now)
                return events
            prev = self._last_commit.get(wt.name)
            if prev is not None and tip != prev:
                self._note_activity(wt.name)
                self._touch_team(wt)
                self._branch_dirty[wt.name] = True
                events.append(Event("commit", agent, None, now))
            self._last_commit[wt.name] = tip
        if had_files:
            self._branch_dirty[wt.name] = True
        self._maybe_refresh_branch(wt, now)
        return events

    def poll(self) -> list[Event]:
        now = self.clock.monotonic()
        events = []
        self._refresh_branch_tips()
        self._update_main_tip_from_batch()
        self._refresh_merged_branches()
        events.extend(self._poll_main(now))
        if now - self._last_wt_list >= WORKTREE_INTERVAL:
            self._refresh_main_branch()
            self._force_unmerged_check = True
            self._refresh_worktrees()
            self._last_wt_list = now
            names = {w.name for w in self._worktrees
                     if w.path != self.repo_root and w.name not in self._prunable_names}
            gone = self._known_wt_names - names
            for name in gone:
                events.append(Event("leave", self._leave_agent(name), None, now))
                self._open_briefs.pop(name, None)
                self._open_reviews.pop(name, None)
                self._finished_impl.pop(name, None)
                self._flags.pop(name, None)
                self._drop_worktree_view(name)
            if gone:
                self._recompute_derived()
            self._known_wt_names = names
        observer_due: list[WorktreeInfo] = []
        observer_intervals: dict[str, float] = {}
        for wt in self._worktrees:
            if wt.path == self.repo_root or wt.name in self._prunable_names:
                continue
            if wt.name not in self._last_poll:
                interval = SHOWN_POLL
            else:
                interval = SHOWN_POLL if self._shown(wt) else HIDDEN_POLL
            observer_intervals[wt.name] = interval
            if (self._shown(wt) and not self._is_merged(wt)
                    and (self._last_obs_poll.get(wt.name) is None
                         or now - self._last_obs_poll.get(wt.name, 0) >= SHOWN_POLL)):
                observer_due.append(wt)
        observer_results: dict[str, list] = {}
        if observer_due:
            futures = [(wt, self._observer_pool.submit(self._poll_observer, wt))
                       for wt in observer_due]
            for wt, fut in futures:
                try:
                    observer_results[wt.name] = fut.result()
                    self._last_obs_poll[wt.name] = now
                except subprocess.CalledProcessError:
                    observer_results[wt.name] = None
        for wt in self._worktrees:
            if wt.path == self.repo_root or wt.name in self._prunable_names:
                continue
            if self._shown(wt) and wt.branch and wt.name not in self._branch_views:
                self._seed_worktree_view(wt)
                self._recompute_derived()
            interval = observer_intervals.get(wt.name, SHOWN_POLL)
            obs_ev = observer_results.get(wt.name)
            if wt.name in observer_results and observer_results[wt.name] is None:
                continue
            events.extend(self._poll_worktree(
                wt, interval, observer_events=obs_ev if wt.name in observer_results else None))
            self._maybe_refresh_branch(wt, now)
        if now - self._last_transcript_scan >= TRANSCRIPT_RESCAN:
            for path in discover_transcripts(self.home, self.clock.time(), ACTIVE_SECONDS):
                if path not in self._transcripts:
                    self._transcripts[path] = TranscriptTail(
                        path, self.repo_root, self._worktrees, on_subagent=self._on_subagent,
                        worktree_paths=self._wt_paths)
            self._last_transcript_scan = now
        if now - self._last_transcript_poll >= TRANSCRIPT_INTERVAL:
            self._last_transcript_poll = now
            for tail in self._transcripts.values():
                for agent, path in tail.poll():
                    events.append(Event("read", agent, path, now))
        return events
