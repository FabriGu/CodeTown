"""The live half of watch, shared by the terminal and the browser.

LiveTown holds the crowd, seeds it from the first state, applies each poll's events, re-surveys
main after a clean merge and writes the merge status line. It draws nothing: each view keeps its
own camera and CameraDirector and feeds the director the events ingest() returns.
"""

import copy
import queue
import threading
from dataclasses import dataclass

import crowd
import drawtown
import problems
import survey
import watch
import watch_sites
import watch_ui
from layers import Rows
from plat import Plat
from roads import Roads
from townmap import TownMap


@dataclass
class WatchSnapshot:
    events: list
    state: watch.WatchState


class WatchPoller(threading.Thread):
    name = "WatchPoller"

    def __init__(self, watch_obj, out_queue, clock, interval=1.0):
        super().__init__(daemon=True)
        self._watch = watch_obj
        self._queue = out_queue
        self._clock = clock
        self._interval = interval
        self.close_event = threading.Event()
        self.inbox = queue.Queue()

    def _drain_inbox(self):
        while not self.inbox.empty():
            model, tip = self.inbox.get_nowait()
            self._watch.note_resurvey(model, tip)

    def run(self):
        self._drain_inbox()
        self._queue.put(WatchSnapshot([], self._watch.state()))
        while not self.close_event.is_set():
            self.close_event.wait(self._interval)
            if self.close_event.is_set():
                break
            self._drain_inbox()
            try:
                events = self._watch.poll()
            except Exception:
                continue
            self._queue.put(WatchSnapshot(events, self._watch.state()))


def default_resurvey_runner(fn):
    threading.Thread(target=fn, name="Resurvey", daemon=True).start()


def resurvey_main(repo_root, plat, rows):
    model = survey.survey(repo_root)
    new_rows = Rows(dict(rows.districts), dict(rows.modules)).update(model)
    new_plat = Plat({name: copy.deepcopy(d) for name, d in plat.districts.items()},
                    list(plat.harbor)).update(model, new_rows)
    return model, new_rows, new_plat


def survey_diff(old_model, new_model):
    old_ids = set(old_model.modules)
    new_ids = set(new_model.modules)
    added = len(new_ids - old_ids)
    changed = sum(1 for mid in old_ids & new_ids
                  if old_model.modules[mid] != new_model.modules[mid])
    return added, changed


def _n(count, word):
    return f"{count} {word}" if count == 1 else f"{count} {word}s"


class TargetRecorder:
    """A camera that only remembers where the director pointed it (the server has no screen)."""

    def __init__(self):
        self.target = None

    def set_target(self, x, y):
        self.target = (x, y)


class LiveTown:
    def __init__(self, tmap, roads, model, rows, plat, repo_name, main_tip, repo_root, clock, *,
                 resurvey_runner=None, note_resurvey=None, resurvey=None):
        self.m, self.roads, self.model, self.rows, self.plat = tmap, roads, model, rows, plat
        self.found = problems.find(model, rows)
        self.repo_name, self.main_tip, self.repo_root = repo_name, main_tip, repo_root
        self.t = 0.0
        self.version = 1
        self.state = watch.WatchState()
        self.latest_event = None
        self.drops = {}
        self.crowd = crowd.Crowd(tmap, roads, model, set(model.modules),
                                 crowd.town_hall_tile(tmap), clock)
        self.resurvey_runner = resurvey_runner or default_resurvey_runner
        self.note_resurvey = note_resurvey or (lambda model, tip: None)
        self._resurvey = resurvey or resurvey_main
        self._seeded = False
        self._queue = queue.Queue()
        self._inflight = False
        self.resurvey_error = None
        self._applied_tip = None
        self._failed_tip = None
        self._merge_base = None
        self.merge_line2 = None

    def ingest(self, snapshot):
        if not self._seeded:
            self.crowd.seed(snapshot.state, snapshot.state.team_colours)
            self._seeded = True
        for ev in snapshot.events:
            if ev.kind == "merge":
                self._capture_merge(ev, snapshot.state)
        applied = []
        if snapshot.events:
            self.crowd.apply(snapshot.events, snapshot.state,
                             snapshot.state.team_colours, self.t)
            self.latest_event = snapshot.events[-1]
            applied = snapshot.events
        self.state = snapshot.state
        self.main_tip = snapshot.state.main_tip
        self._drain_resurvey()
        self._maybe_start_resurvey(snapshot.state)
        self._drain_resurvey()
        return applied

    def _capture_merge(self, ev, state):
        if ev.agent:
            wt = ev.agent.worktree or ""
            branch = state.worktree_branches.get(wt, wt)
            self._merge_base = f"merged {branch}"
        else:
            self._merge_base = f"main moved to {state.main_tip[:7]}"
        self.merge_line2 = self._merge_base

    def _maybe_start_resurvey(self, state):
        if not state.main_moved_clean or state.main_mid_merge:
            return
        tip = state.main_tip
        if not tip or self._inflight:
            return
        if tip == self._applied_tip or tip == self._failed_tip:
            return
        self._inflight = True
        plat, rows = self.plat, self.rows
        repo = self.repo_root

        def work():
            try:
                result = self._resurvey(repo, plat, rows)
                self._queue.put(("ok", tip, result))
            except Exception as e:
                self._queue.put(("err", tip, e))

        self.resurvey_runner(work)

    def _drain_resurvey(self):
        while True:
            try:
                kind, tip, payload = self._queue.get_nowait()
            except queue.Empty:
                break
            self._inflight = False
            if tip != self.state.main_tip:
                continue
            if kind == "err":
                self.resurvey_error = str(payload)
                self._failed_tip = tip
                continue
            self._apply_resurvey(tip, payload)

    def _apply_resurvey(self, tip, payload):
        old_model = self.model
        model, rows, plat = payload
        new_n, changed_n = survey_diff(old_model, model)
        old_ids = set(old_model.modules)
        new_ids = set(model.modules)
        found = problems.find(model, rows)
        tmap = TownMap(model, plat, rows, found)
        roads = Roads(tmap, model, found)
        hall = crowd.town_hall_tile(tmap)
        self.crowd.retown(tmap, roads, model, set(model.modules), hall)
        self.m = tmap
        self.roads = roads
        self.model = model
        self.rows = rows
        self.plat = plat
        self.found = found
        self.main_tip = tip
        now = self.t
        for mod in new_ids - old_ids:
            if mod in tmap.buildings:
                self.drops[mod] = now
        self.resurvey_error = None
        self._failed_tip = None
        self._applied_tip = tip
        if self._merge_base is not None:
            parts = []
            if new_n:
                parts.append(_n(new_n, "new building"))
            if changed_n:
                parts.append(f"{changed_n} changed")
            suffix = ", ".join(parts)
            self.merge_line2 = f"{self._merge_base}: {suffix}" if suffix else self._merge_base
        self.note_resurvey(model, tip)
        self.version += 1

    def step(self, dt, now):
        self._drain_resurvey()
        self._maybe_start_resurvey(self.state)
        self.t = now
        self.crowd._now = now
        crowd_moving = self.crowd.step(dt)
        return crowd_moving or self._dropping()

    def _dropping(self):
        return any(drawtown.drop_offset(self.t - start) > 0.01 for start in self.drops.values())

    def moving(self):
        return self.crowd.is_moving() or self._dropping()

    def lines(self):
        line1 = watch_ui.line1(self.repo_name, self.state, self.main_tip,
                               self.state.worktree_count, resurvey_error=self.resurvey_error,
                               mid_merge=self.state.main_mid_merge)
        ev = self.latest_event
        merge = self.merge_line2 if ev and ev.kind == "merge" else None
        return line1, watch_ui.line2(ev, self.state, self.repo_name, merge_line2=merge)

    def team_colours(self):
        tc = dict(self.state.team_colours)
        state = self.state
        for team in state.scaffolded.values():
            tc.setdefault(team, 0)
        for team in state.site_teams.values():
            tc.setdefault(team, 0)
        for team in state.worktree_teams.values():
            tc.setdefault(team, 0)
        for c in self.crowd.clawds():
            if c.team:
                tc.setdefault(c.team, c.colour)
        return tc

    def scaffold(self):
        return self.crowd.effective_scaffold(self.state)

    def sites(self):
        site_paths = self.crowd.effective_sites(self.state)
        layout = watch_sites.layout_sites(self.m, site_paths)
        return {p: (*layout[p], self.state.site_teams.get(p, "world")) for p in layout}

    def flags(self):
        return {wt: (mod, self.state.worktree_teams.get(wt, "world"))
                for wt, mod in self.state.flags.items()}
