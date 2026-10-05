# Watch in 3D, live: Implementation Plan (plan 2 of 2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `towncode watch PATH --browser` serves the live watch town in 3D: voxel Clawds walk the
streets to the files their agents edit, with scaffolding, sites, flags, labels, the status bar,
the automatic camera, follow keys, and the town rebuilding after a merge.

**Architecture:** Python keeps all the work. The live half of `WatchViewer` moves into
`livetown.LiveTown`, which both the terminal viewer and a new simulation thread drive. The
simulation thread steps the crowd every 0.1 s, turns it into JSON-ready live state
(`townjson.live_state`), diffs it against the last state sent, and streams `state`, `tick` and
`town` messages over Server-Sent Events at `/events`. The browser (`web/town3d.js`) only draws and
animates what it is told, with its pure logic in `web/live.js` so Node can test it.

**Tech Stack:** Python 3.14 standard library (`http.server`, `threading`, `queue`, `json`),
`unittest`; Three.js r186 vendored in `web/vendor/` (already there); browser ES modules, no npm,
no build step; `node --test` for `web/live.js` (skipped when Node is absent);
`playwright-cli` for the hand-run smoke check.

**Spec:** `docs/superpowers/specs/2026-10-02-towncode-watch-3d-design.md` (steps 2–4 of its Build
order). Watch behaviour is defined by `docs/superpowers/specs/2026-10-01-towncode-watch-design.md`.

## Global Constraints

- `towncode watch PATH --browser [--port N] [--no-open]`; `--browser` can't be combined with
  `--events`. It doesn't need an interactive terminal. `Ctrl-C` stops the server and closes the
  watch.
- Python sends meanings (kinds, indexes, paths), never colours. Every colour and size the browser
  uses is in `web/look.js`, and `town3d.js` lists any key it needs that `look.js` doesn't define.
- The server binds `127.0.0.1` only, refuses a `Host` other than `127.0.0.1:PORT` /
  `localhost:PORT` with 403, accepts GET only (405 otherwise), serves static files only from the
  fixed `STATIC` table, sends no CORS headers, and every response (including `/events`) carries
  the strict `Content-Security-Policy`.
- The repository and its worktrees stay read-only. Watch writes only `watch.json`.
- What never crosses the wire: file contents, transcript text, commands, and tool arguments. Only
  repository-relative paths, roles, team names, labels, and the facts and counts the terminal
  already shows.
- Repository text reaches the page only as `textContent`, never as HTML.
- `townjson.py`, `webserve.py` and `livetown.py` use only the standard library, so their tests
  run under both `.venv/bin/python` and the system `python3`.
- Terminal watch behaves exactly as before. Every existing test passes unchanged.
- Movement contract: a Clawd's record is sent again only when its path, pose, label, follow
  number or flag changes, not each time it steps to the next tile of the same path.
- Simulation thread interval 0.1 s; `/events` heartbeat every 15 s; a client more than 100
  messages behind is disconnected.
- Performance targets: 60 fps for a town of a couple of hundred buildings with 10 Clawds on a recent laptop, `/town.json` under
  1 MB, the simulation thread under 5% of one core.
- Commit messages are one plain sentence in the imperative, like the branch's existing ones
  ("Serve the 3D town's page on this machine only, GET only, with a strict policy").

## Base and conventions

- Worktree `~/codetown-live3d`, branch `watch-3d-live`, based on `5fd8b2c` (main with watch
  phases 1–3, merged with `live-visuals` and the static 3D town).
- `.venv` in the worktree is a symlink to `~/codetown/.venv` (tree-sitter lives there).
- Focused tests: `.venv/bin/python -m unittest test_livetown -v` (and so on). Full suites:
  `.venv/bin/python -m unittest` and `python3 -m unittest`. Baseline at `5fd8b2c`: both OK
  (venv skipped=1, system skipped=202).
- Browser checks: `python3 smoke_web.py` (static) and, from Task 6, `python3 smoke_web.py --watch`.
  They need `npx`; `PWCLI` defaults to `~/.codex/skills/playwright/scripts/playwright_cli.sh`.

## Files

| File | Status | Responsibility |
|---|---|---|
| `livetown.py` | new | `LiveTown` (crowd, seeding, events, re-survey, merge line, status lines), `WatchSnapshot`, `WatchPoller`, `resurvey_main`, `TargetRecorder`. No drawing. |
| `viewer.py` | changed | `WatchViewer` wraps a `LiveTown` and keeps only the camera and pixel drawing. Re-exports the moved names. |
| `crowd.py` | changed | `CameraDirector.auto_agent`. |
| `townjson.py` | changed | `town(..., live=)` adds `hall`, `step_time`, `live`; `clawd`, `live_state`, `state_message`, `tick_message`, `town_message`. |
| `webserve.py` | changed | `sse`, `LiveSite`, `Simulation`, `/events`, `/static/live.js`, `serve(..., on_close=)`. |
| `towncode.py` | changed | `watch --browser/--port/--no-open`, `_watch_browser`. |
| `web/live.js` | new | Pure live logic: clocks, walking, poses, applying messages, camera modes, legend, label fade, nearest scaffolding, new buildings. |
| `web/live.test.mjs` | new | `node --test` tests for `live.js`. Not served. |
| `web/town3d.js` | changed | Live layer: Clawds, lectern, scaffolding, sites, flags; labels; status bar; automatic camera and follow keys; rebuild on `town`; reconnect. |
| `web/look.js` | changed | Watch looks: scarves, Clawd voxels, poses, scaffolding, sites, flags, lectern, labels, drop, follow camera. |
| `web/index.html`, `web/town3d.css` | changed | Label layer and label styles. |
| `smoke_web.py` | changed | `--watch` mode: a scripted worktree, Clawds drawn, a walk seen. |
| `scripts/benchmark_watch_browser.py` | new | Simulation-thread CPU share and `/town.json` size for a repo, read-only. |
| `README.md` | changed | `towncode watch PATH --browser`. |
| `test_livetown.py`, `test_townjson_live.py`, `test_webserve_live.py`, `test_watch_browser.py`, `test_web_live.py` | new | Unit and end-to-end tests. |

---

### Task 1: The shared live core (`LiveTown`) and `CameraDirector.auto_agent`

Spec: "Why `LiveTown`", Build order step 2. Terminal watch must behave the same and every test
pass unchanged — including the ten tests that patch `viewer.resurvey_main` and the tests that
read `v._crowd`, `v._latest_state`, `v._latest_event`, `v._drops`, `v._resurvey_error` and
`v._merge_line2`.

**Files:**
- Create: `livetown.py`, `test_livetown.py`
- Modify: `viewer.py` (move `WatchSnapshot`, `WatchPoller`, `_default_resurvey_runner`,
  `resurvey_main`, `_survey_diff` and the live half of `WatchViewer` out), `crowd.py`
  (`CameraDirector`)

**Interfaces:**
- Produces (`livetown.py`):
  - `WatchSnapshot(events: list, state: watch.WatchState)` (moved, same dataclass)
  - `WatchPoller(watch_obj, out_queue, clock, interval=1.0)` (moved unchanged; `.inbox`,
    `.close_event`)
  - `resurvey_main(repo_root, plat, rows) -> (model, rows, plat)` (moved unchanged)
  - `survey_diff(old_model, new_model) -> (added, changed)` (was `viewer._survey_diff`)
  - `default_resurvey_runner(fn)` (was `viewer._default_resurvey_runner`)
  - `class TargetRecorder` with `target` (None or `(x, y)`) and `set_target(x, y)`
  - `class LiveTown(tmap, roads, model, rows, plat, repo_name, main_tip, repo_root, clock, *,
    resurvey_runner=None, note_resurvey=None, resurvey=None)` with attributes
    `m, roads, model, rows, plat, found, repo_name, main_tip, repo_root, t, version, crowd,
    state, latest_event, drops, resurvey_error, merge_line2, resurvey_runner, note_resurvey`
    and methods `ingest(snapshot) -> list[Event]`, `step(dt, now) -> bool`, `moving() -> bool`,
    `lines() -> tuple[str, str]`, `team_colours() -> dict[str, int]`,
    `scaffold() -> dict[str, str]`, `sites() -> dict[str, tuple[int, int, int, str]]`,
    `flags() -> dict[str, tuple[str, str]]`
  - `version` starts at 1 and goes up by 1 each time a re-survey lands.
- Produces (`crowd.py`): `CameraDirector.auto_agent` — read-only property: the id of the Clawd
  the automatic camera has chosen, or `None` when there is none or it has left.
- Produces (`viewer.py`): `WatchViewer.live` (its `LiveTown`); `viewer.WatchSnapshot`,
  `viewer.WatchPoller`, `viewer.resurvey_main` stay importable from `viewer`.

- [ ] **Step 1: Write the failing tests** — `test_livetown.py`:

```python
import unittest
from unittest import mock

import crowd
import fixture
import livetown
import viewer
import watch
from events import Agent, Event
from plat import Plat
from roads import Roads
from test_townmap import build as build_town
from test_watch import temp_survey

A = Agent("w1/task-1", "implementer", "world", "w1")


def _live(*, runner=None, resurvey=None):
    model, rows, found, tmap = build_town()
    roads = Roads(tmap, model, found)
    plat = Plat().update(model, rows)
    return livetown.LiveTown(tmap, roads, model, rows, plat, "showcase", "deadbeef", "/nowhere",
                             watch.FakeClock(), resurvey_runner=runner or (lambda fn: fn()),
                             resurvey=resurvey)


class LiveTownTest(unittest.TestCase):
    def test_first_ingest_seeds_and_returns_the_events(self):
        live = _live()
        st = watch.WatchState(agents=[watch.AgentState(A, "working", "app/main.py")])
        self.assertEqual(live.ingest(livetown.WatchSnapshot([], st)), [])
        self.assertEqual([c.agent_id for c in live.crowd.clawds()], ["w1/task-1"])
        ev = Event("edit", A, "app/main.py", 1.0)
        self.assertEqual(live.ingest(livetown.WatchSnapshot([ev], st)), [ev])
        self.assertIs(live.latest_event, ev)
        self.assertIs(live.state, st)

    def test_step_walks_the_crowd(self):
        live = _live()
        live.ingest(livetown.WatchSnapshot([Event("start", A, None, 0.0),
                                            Event("edit", A, "app/main.py", 0.5)],
                                           watch.WatchState()))
        self.assertTrue(live.step(0.1, 0.1))
        self.assertEqual(live.t, 0.1)
        self.assertEqual(live.crowd.clawds()[0].pose, "walk")

    def test_lines_are_the_terminal_status_lines(self):
        live = _live()
        st = watch.WatchState(agents=[watch.AgentState(A, "working", "app/main.py")],
                              main_tip="deadbeef")
        live.ingest(livetown.WatchSnapshot([Event("edit", A, "app/main.py", 1.0)], st))
        line1, line2 = live.lines()
        self.assertEqual(line1, "showcase: 1 agents: world. main at deadbeef")
        self.assertEqual(line2, "world task 1 edited app/main.py")

    def test_a_landed_resurvey_bumps_the_version_and_writes_the_merge_line(self):
        model, rows, found, tmap = build_town()
        live = _live(resurvey=lambda repo, plat, rows_: (model, rows_, plat))
        st = watch.WatchState(main_moved_clean=True, main_tip="abc1234",
                              worktree_branches={"w1": "team/world/w1"})
        live.ingest(livetown.WatchSnapshot([Event("merge", A, None, 1.0)], st))
        self.assertEqual(live.version, 2)
        self.assertEqual(live.merge_line2, "merged team/world/w1")
        self.assertEqual(live.lines()[1], "merged team/world/w1")

    def test_a_failed_resurvey_keeps_the_town_and_says_so(self):
        def boom(repo, plat, rows):
            raise RuntimeError("disk full")
        live = _live(resurvey=boom)
        before = set(live.m.buildings)
        live.ingest(livetown.WatchSnapshot([], watch.WatchState(main_moved_clean=True,
                                                                main_tip="abc1234")))
        self.assertEqual(live.version, 1)
        self.assertEqual(set(live.m.buildings), before)
        self.assertEqual(live.lines()[0], "couldn't re-survey main: disk full")

    def test_note_resurvey_hears_each_landed_survey(self):
        heard = []
        live = _live(resurvey=lambda repo, plat, rows: (live.model, rows, plat))
        live.note_resurvey = lambda model, tip: heard.append(tip)
        live.ingest(livetown.WatchSnapshot([], watch.WatchState(main_moved_clean=True,
                                                                main_tip="abc1234")))
        self.assertEqual(heard, ["abc1234"])


class TargetRecorderTest(unittest.TestCase):
    def test_it_records_the_last_target(self):
        cam = livetown.TargetRecorder()
        self.assertIsNone(cam.target)
        cam.set_target(3.0, 4.0)
        self.assertEqual(cam.target, (3.0, 4.0))


class AutoAgentTest(unittest.TestCase):
    def test_auto_agent_names_the_chosen_clawd_until_it_leaves(self):
        live = _live()
        director = crowd.CameraDirector(livetown.TargetRecorder(), live.crowd, live.m)
        self.assertIsNone(director.auto_agent)
        events = live.ingest(livetown.WatchSnapshot([Event("start", A, None, 1.0)],
                                                    watch.WatchState()))
        director.apply_events(events, live.t)
        director.step(0.1, 0.1)
        self.assertEqual(director.auto_agent, "w1/task-1")
        live.ingest(livetown.WatchSnapshot([Event("leave", A, None, 2.0)], watch.WatchState()))
        self.assertIsNone(director.auto_agent)


class WatchViewerSharesLiveTownTest(unittest.TestCase):
    def test_the_viewer_drives_a_live_town(self):
        main = fixture.make_repo(self, {"hub/a.py": "x = 1\n"})
        survey = temp_survey(self)
        model, rows, found, tmap = build_town()
        w = watch.Watch(main, survey_dir=survey)
        self.addCleanup(w.close)
        v = viewer.WatchViewer(tmap, Roads(tmap, model, found), model, rows,
                               Plat().update(model, rows), "demo", "abc1234", survey, main, w)
        self.assertIsInstance(v.live, livetown.LiveTown)
        self.assertIs(v._crowd, v.live.crowd)
        self.assertIs(viewer.WatchSnapshot, livetown.WatchSnapshot)
        self.assertIs(viewer.WatchPoller, livetown.WatchPoller)

    def test_patching_viewer_resurvey_main_still_reaches_the_viewer(self):
        main = fixture.make_repo(self, {"hub/a.py": "x = 1\n"})
        survey = temp_survey(self)
        model, rows, found, tmap = build_town()
        w = watch.Watch(main, survey_dir=survey)
        self.addCleanup(w.close)
        v = viewer.WatchViewer(tmap, Roads(tmap, model, found), model, rows,
                               Plat().update(model, rows), "demo", "abc1234", survey, main, w,
                               resurvey_runner=lambda fn: fn())
        with mock.patch("viewer.resurvey_main", side_effect=RuntimeError("disk full")):
            v.ingest(viewer.WatchSnapshot([], watch.WatchState(main_moved_clean=True,
                                                               main_tip="abc1234")))
        self.assertEqual(v._resurvey_error, "disk full")


if __name__ == "__main__":
    unittest.main()
```

Checked on the base: `watch.AgentState(agent, status, latest_path)` is the field order;
`test_townmap.build()`'s showcase has `app/main.py`; a `start` event puts a new Clawd at Town Hall
standing still (`idle`), and it walks only after an `edit`; `Crowd.retown` keeps every Clawd, so
the director hearing a poll's events after a synchronous re-survey (rather than before, as
`WatchViewer.ingest` does today) sees the same crowd.

- [ ] **Step 2: Run them to see them fail**

Run: `.venv/bin/python -m unittest test_livetown -v`
Expected: FAIL / ERROR — `ModuleNotFoundError: No module named 'livetown'`.

- [ ] **Step 3: Write `livetown.py`**

Move the code, don't rewrite it: `WatchSnapshot`, `WatchPoller`, `_default_resurvey_runner`
(rename `default_resurvey_runner`), `resurvey_main` and `_survey_diff` (rename `survey_diff`) move
verbatim from `viewer.py`. `LiveTown` takes the live half of `WatchViewer.__init__`, `ingest`,
`_capture_merge`, `_maybe_start_resurvey`, `_drain_resurvey`, `_apply_resurvey`, `tick`,
`moving`, `_effective_team_colours` and the data half of `_watch_layer`:

```python
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
    ...  # moved verbatim from viewer.py


def default_resurvey_runner(fn):
    threading.Thread(target=fn, name="Resurvey", daemon=True).start()


def resurvey_main(repo_root, plat, rows):
    ...  # moved verbatim


def survey_diff(old_model, new_model):
    ...  # moved verbatim


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
```

`ingest(snapshot)` is `WatchViewer.ingest` without the director call and without
`_town_cache_key`; it returns `snapshot.events` when it applied them, else `[]`.
`_maybe_start_resurvey` calls `self._resurvey(repo, plat, rows)` inside `work()` instead of
`resurvey_main(...)`. `_apply_resurvey` keeps everything that isn't drawing (model, rows, plat,
found, `crowd.retown`, `main_tip`, drops for new buildings at `self.t`, errors, tips, merge line,
`note_resurvey`) and ends with `self.version += 1`. It no longer builds `TownScene`s or touches a
director. `step(dt, now)` is the live half of `WatchViewer.tick`:

```python
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
```

`team_colours()` is `_effective_team_colours`. `scaffold()` is
`self.crowd.effective_scaffold(self.state)`. `sites()` is
`{p: (x, y, size, team)}` exactly as `_watch_layer` builds `sites` today (`watch_sites.layout_sites`
over `crowd.effective_sites`, team from `state.site_teams`, default `"world"`). `flags()` is
`{worktree: (module, team)}` exactly as `_watch_layer` builds `flags`.

- [ ] **Step 4: Make `WatchViewer` wrap a `LiveTown`**

In `viewer.py`, delete the moved code and import it back so every old name still works:

```python
from livetown import (LiveTown, WatchPoller, WatchSnapshot, default_resurvey_runner,
                      resurvey_main, survey_diff)
```

`WatchViewer.__init__` keeps its signature. It builds
`self.live = LiveTown(tmap, roads, model, rows, plat, repo_name, main_tip, repo_root, clock,
resurvey_runner=resurvey_runner, note_resurvey=note_resurvey,
resurvey=lambda repo, plat_, rows_: resurvey_main(repo, plat_, rows_))` — the lambda looks
`resurvey_main` up in `viewer` at call time, so `mock.patch("viewer.resurvey_main")` still
reaches it. It keeps the camera, its `CameraDirector` (on `self.live.crowd`), the whole-scene
offsets, hall pixels and the frame caches, plus `self._town_version = self.live.version`.

Add read-only properties that delegate to `self.live`: `m`, `roads`, `model`, `rows`, `plat`,
`main_tip`, `_crowd`, `_latest_state` (→ `state`), `_latest_event`, `_drops`, `_merge_line2`;
and properties with setters for `t`, `_resurvey_error` (`test_watch_merge` sets it),
`_resurvey_runner` and `_note_resurvey` (`run_watch` assigns the last two). Tests also call
`v._drain_resurvey()`, so keep it as a method:

```python
    def _drain_resurvey(self):
        self.live._drain_resurvey()
        self._sync_town()
```

Tests read `v._whole_town`, `v._target_for_cursor` and `v._last_street_scene`; those are
drawing state and stay on `WatchViewer` unchanged.

```python
    def ingest(self, snapshot):
        events = self.live.ingest(snapshot)
        if events:
            self._director.apply_events(events, self.live.t)
        self._town_cache_key = None
        self._sync_town()

    def _sync_town(self):
        """Redo the drawing state when a re-survey has swapped the town."""
        if self.live.version == self._town_version:
            return
        self._town_version = self.live.version
        whole = TownScene.whole(self.m, visible=self.roads.visible())
        self._director.update_town(self.m, (whole.ox, whole.oy))
        self._whole_ox, self._whole_oy = whole.ox, whole.oy
        self._whole_w, self._whole_h = whole.fb.w, whole.fb.h
        self._town_cache_key = None
        self._hall_reserved = frozenset(
            drawtown.hall_tile_pixels(whole, crowd.town_hall_tile(self.m), self.m))
        self._reserved_key = None

    def tick(self, dt, now):
        live_moving = self.live.step(dt, now)
        self._sync_town()
        self._director.step(dt, now)
        return self.camera.step(dt) or live_moving

    def moving(self):
        return self.camera.gliding() or self.live.moving()
```

`status` uses `self.live.lines()` for lines 1 and 2; `_watch_layer` uses `self.live.scaffold()`,
`self.live.team_colours()`, `self.live.sites()`, `self.live.flags()` and `self.live.drops`.

- [ ] **Step 5: Add `CameraDirector.auto_agent`** in `crowd.py`:

```python
    @property
    def auto_agent(self) -> str | None:
        """The Clawd the automatic camera has chosen, if it is still in town."""
        aid = self._auto_agent
        return aid if aid is not None and self._present(aid) else None
```

- [ ] **Step 6: Run the new tests, then every watch test**

Run: `.venv/bin/python -m unittest test_livetown -v`
Expected: PASS.
Run: `.venv/bin/python -m unittest test_watch_viewer test_watch_merge test_watch_e2e test_watch_e2e_view test_watch_ui test_watch_camera test_watch_draw test_crowd test_towncode test_viewer -v`
Expected: PASS, with no test file edited.

- [ ] **Step 7: Run both full suites**

Run: `.venv/bin/python -m unittest` and `python3 -m unittest`
Expected: OK (only the baseline skips, plus `test_livetown` under system `python3` if it is
skipped there for tree-sitter — it shouldn't be).

- [ ] **Step 8: Commit**

```bash
git add livetown.py test_livetown.py viewer.py crowd.py
git commit -m "Move watch's live half into LiveTown so the terminal and the browser drive the same crowd"
```

---

### Task 2: Live state as JSON, and the diffs between two states

Spec: "Data and messages" (`/town.json`'s `hall` and `step_time`, `/events` messages, a Clawd's
record, other live fields), "Movement contract", Testing "Diffs".

**Files:**
- Modify: `townjson.py`
- Create: `test_townjson_live.py`

**Interfaces:**
- Consumes: `LiveTown` (Task 1: `crowd`, `state`, `version`, `lines()`, `team_colours()`,
  `scaffold()`, `sites()`, `flags()`), `CameraDirector.follow_labels() -> {agent_id: n}`,
  `CameraDirector.auto_agent`.
- Produces (`townjson.py`):
  - `town(tmap, roads, describe, *, repo, version=1, live=False)` — the existing document plus
    `"hall": [x, y]` (`crowd.town_hall_tile`), `"step_time": game.STEP_TIME` and `"live": live`.
  - `MOTION = ("tile", "facing", "path_i", "walk_t")` — record fields that never cause a resend.
  - `clawd(c, live, follow, team_colours) -> dict` — one record:
    `{"id", "role", "team", "scarf", "label", "follow", "tile", "facing", "pose", "path",
    "path_i", "walk_t", "flag"}`.
  - `live_state(live, director) -> dict` —
    `{"version", "clawds": {id: record}, "scaffold": {path: scarf}, "sites": [{"path",
    "tile", "size", "scarf"}], "flags": [{"agent", "building", "scarf"}], "status": [l1, l2],
    "camera": id or None}`.
  - `state_message(cur, t) -> dict` — `cur` with `clawds` as a list (sorted by id), plus `"t"`.
  - `tick_message(prev, cur, t) -> dict | None` — only what changed, plus `"t"`; `None` when
    nothing did.
  - `town_message(version, t) -> {"t": t, "version": version}`.

- [ ] **Step 1: Write the failing tests** — `test_townjson_live.py`:

```python
import json
import unittest

import crowd
import game
import livetown
import townjson
import watch
from events import Agent, Event
from plat import Plat
from roads import Roads
from test_townmap import build as build_town
from viewer import Viewer

A = Agent("w1/task-1", "implementer", "world", "w1")
R = Agent("w1/review-task-1", "reviewer", "world", "w1")


class Fixture:
    def __init__(self):
        model, rows, found, tmap = build_town()
        self.roads = Roads(tmap, model, found)
        self.live = livetown.LiveTown(tmap, self.roads, model, rows, Plat().update(model, rows),
                                      "showcase", "deadbeef", "/nowhere", watch.FakeClock(),
                                      resurvey_runner=lambda fn: None)
        self.director = crowd.CameraDirector(livetown.TargetRecorder(), self.live.crowd, tmap)
        self.t = 0.0

    def feed(self, events, state=None):
        st = state or watch.WatchState(team_colours={"world": 3})
        applied = self.live.ingest(livetown.WatchSnapshot(events, st))
        self.director.apply_events(applied, self.live.t)

    def step(self, dt=0.1):
        self.t += dt
        self.live.step(dt, self.t)
        self.director.step(dt, self.t)
        return townjson.live_state(self.live, self.director)


class TownExtrasTest(unittest.TestCase):
    def test_the_town_names_its_hall_step_time_and_mode(self):
        f = Fixture()
        v = Viewer(f.live.m, f.roads, f.live.model, f.live.found)
        doc = townjson.town(f.live.m, f.roads, v.describe, repo="showcase", live=True)
        self.assertEqual(doc["hall"], list(crowd.town_hall_tile(f.live.m)))
        self.assertEqual(doc["step_time"], game.STEP_TIME)
        self.assertIs(doc["live"], True)
        static = townjson.town(f.live.m, f.roads, v.describe, repo="showcase")
        self.assertIs(static["live"], False)


WALK = [Event("start", A, None, 1.0), Event("edit", A, "app/main.py", 1.5)]


class RecordTest(unittest.TestCase):
    def test_a_record_has_the_spec_fields_and_the_terminal_label(self):
        f = Fixture()
        f.feed(WALK)
        rec = f.step()["clawds"]["w1/task-1"]
        self.assertEqual(set(rec), {"id", "role", "team", "scarf", "label", "follow", "tile",
                                    "facing", "pose", "path", "path_i", "walk_t", "flag"})
        self.assertEqual(rec["role"], "implementer")
        self.assertEqual(rec["team"], "world")
        self.assertEqual(rec["scarf"], 3)
        self.assertEqual(rec["label"], "world · task 1  +0 −0")
        self.assertEqual(rec["follow"], 1)
        self.assertEqual(rec["pose"], "walk")
        self.assertTrue(len(rec["path"]) >= 2)

    def test_the_whole_state_is_json_and_carries_no_file_contents(self):
        f = Fixture()
        f.feed(WALK)
        cur = f.step()
        text = json.dumps(townjson.state_message(cur, 0.1))
        self.assertNotIn("def ", text)
        msg = json.loads(text)
        self.assertEqual(set(msg), {"t", "version", "clawds", "scaffold", "sites", "flags",
                                    "status", "camera"})
        self.assertEqual(msg["status"][1], "world task 1 edited app/main.py")
        self.assertEqual(msg["camera"], "w1/task-1")


class TickTest(unittest.TestCase):
    def test_a_quiet_step_sends_nothing(self):
        f = Fixture()
        a = f.step()
        self.assertIsNone(townjson.tick_message(a, f.step(), 0.2))

    def test_walking_the_same_path_sends_nothing(self):
        f = Fixture()
        f.feed(WALK)
        a = f.step()
        b = f.step(0.2)
        self.assertNotEqual(a["clawds"]["w1/task-1"]["walk_t"], b["clawds"]["w1/task-1"]["walk_t"])
        self.assertIsNone(townjson.tick_message(a, b, 0.3))

    def test_a_new_path_sends_that_clawd_only(self):
        f = Fixture()
        f.feed([Event("start", A, None, 1.0), Event("start", R, None, 1.0)])
        a = f.step()
        f.feed([Event("edit", A, "app/main.py", 2.0)])
        msg = townjson.tick_message(a, f.step(), 0.2)
        self.assertEqual([r["id"] for r in msg["clawds"]], ["w1/task-1"])
        self.assertEqual(msg["t"], 0.2)

    def test_a_departure_lands_in_gone(self):
        f = Fixture()
        f.feed([Event("start", A, None, 1.0)])
        a = f.step()
        f.feed([Event("leave", A, None, 2.0)])
        msg = townjson.tick_message(a, f.step(), 0.2)
        self.assertEqual(msg["gone"], ["w1/task-1"])

    def test_scaffold_and_status_are_sent_whole_when_they_change(self):
        f = Fixture()
        f.feed([Event("start", A, None, 1.0)])
        a = f.step()
        f.feed([Event("edit", A, "app/main.py", 2.0)],
               watch.WatchState(scaffolded={"app/main.py": "world"}, team_colours={"world": 3}))
        msg = townjson.tick_message(a, f.step(), 0.2)
        self.assertEqual(msg["scaffold"], {"app/main.py": 3})
        self.assertIn("status", msg)

    def test_town_message(self):
        self.assertEqual(townjson.town_message(2, 5.0), {"t": 5.0, "version": 2})


if __name__ == "__main__":
    unittest.main()
```

Checked on the base: the label for an implementer with no diff stats reads
`world · task 1  +0 −0` (`watch_ui.agent_label`); the first implementer's follow number is 1;
an edit adds the module to the crowd's provisional scaffolding, so `scaffold` changes on the
edit's step and not after it; line 2 for that edit reads `world task 1 edited app/main.py`.

- [ ] **Step 2: Run them to see them fail**

Run: `.venv/bin/python -m unittest test_townjson_live -v`
Expected: FAIL — `town()` has no `live`, `townjson` has no `live_state`.

- [ ] **Step 3: Implement** in `townjson.py` (add imports `crowd`, `game`, `watch_ui`,
`from events import Agent`):

```python
MOTION = ("tile", "facing", "path_i", "walk_t")
LIVE_FIELDS = ("scaffold", "sites", "flags", "status", "camera")


def clawd(c, live, follow, team_colours):
    """One Clawd as the browser needs it: who it is, its label, and where it is walking."""
    state = live.state
    diff = state.diff_stats.get(c.worktree or "", (0, 0))
    files = len(state.reviewer_tours.get(c.agent_id, ())) if c.role == "reviewer" else None
    label = watch_ui.agent_label(Agent(c.agent_id, c.role, c.team, c.worktree), c.role, c.team,
                                 diff, files)
    return {"id": c.agent_id, "role": c.role, "team": c.team,
            "scarf": team_colours.get(c.team or "", c.colour), "label": label,
            "follow": follow.get(c.agent_id), "tile": list(c.tile), "facing": list(c.facing),
            "pose": c.pose, "path": [list(t) for t in c.path], "path_i": c.path_i,
            "walk_t": round(c.walk_t, 3), "flag": c.flag_building}


def live_state(live, director):
    """Everything moving in the town, as meanings: Clawds, scaffolding, sites, flags, status."""
    tc = live.team_colours()
    follow = director.follow_labels()
    present = {c.worktree: c.agent_id for c in live.crowd.clawds()
               if c.role == "implementer" and c.worktree}
    return {
        "version": live.version,
        "clawds": {c.agent_id: clawd(c, live, follow, tc)
                   for c in sorted(live.crowd.clawds(), key=lambda c: c.agent_id)},
        "scaffold": {m: tc.get(team, 0) for m, team in sorted(live.scaffold().items())},
        "sites": [{"path": p, "tile": [x, y], "size": size, "scarf": tc.get(team, 0)}
                  for p, (x, y, size, team) in sorted(live.sites().items())],
        "flags": [{"agent": present.get(wt, wt), "building": mod, "scarf": tc.get(team, 0)}
                  for wt, (mod, team) in sorted(live.flags().items())],
        "status": list(live.lines()),
        "camera": director.auto_agent,
    }


def state_message(cur, t):
    return {"t": t, **cur, "clawds": list(cur["clawds"].values())}


def _key(record):
    return {k: v for k, v in record.items() if k not in MOTION}


def tick_message(prev, cur, t):
    """What changed since prev; None if nothing did. Walking on along a path changes nothing."""
    out = {}
    changed = [r for aid, r in cur["clawds"].items()
               if aid not in prev["clawds"] or _key(prev["clawds"][aid]) != _key(r)]
    if changed:
        out["clawds"] = changed
    gone = sorted(set(prev["clawds"]) - set(cur["clawds"]))
    if gone:
        out["gone"] = gone
    for name in LIVE_FIELDS:
        if prev[name] != cur[name]:
            out[name] = cur[name]
    if not out:
        return None
    out["t"] = t
    return out


def town_message(version, t):
    return {"t": t, "version": version}
```

`town(...)` gains `live=False` and adds the three keys:

```python
        "hall": list(crowd.town_hall_tile(tmap)),
        "step_time": game.STEP_TIME,
        "live": live,
```

- [ ] **Step 4: Run the tests**

Run: `.venv/bin/python -m unittest test_townjson_live test_townjson -v` and
`python3 -m unittest test_townjson_live test_townjson -v`
Expected: PASS under both.

- [ ] **Step 5: Commit**

```bash
git add townjson.py test_townjson_live.py
git commit -m "Describe the live town as JSON and send only what changed between two moments"
```

---

### Task 3: The event stream: SSE framing, `LiveSite`, the simulation thread and `/events`

Spec: "`GET /events`", "The server" (simulation thread, re-survey, clients, threads),
"Errors" (stream drops), "Safety", Testing "SSE framing" and "Server".

**Files:**
- Modify: `webserve.py`
- Create: `test_webserve_live.py`

**Interfaces:**
- Consumes: Task 2's `townjson.live_state`, `state_message`, `tick_message`, `town_message`;
  Task 1's `LiveTown.ingest/step/version`, `CameraDirector.apply_events/step`.
- Produces (`webserve.py`):
  - `TICK = 0.1`, `HEARTBEAT = 15.0`, `MAX_BEHIND = 100`
  - `sse(kind, data) -> bytes`; `HEARTBEAT_BYTES = b": heartbeat\n\n"`
  - `class LiveSite(Site)`: `subscribe() -> (queue.Queue, dict | None)`, `unsubscribe(q)`,
    `publish(state_dict)` (the latest `state_message` for new clients), `broadcast(kind, data)`,
    `retown(town, select)`, `close()`
  - `class Simulation(threading.Thread)(live, director, site, snapshots, build_town, *,
    clock=time.monotonic, interval=TICK)`: `step_once(dt, now)`, `stop()`; `build_town(live)
    -> (town_doc, select)`
  - `/events` on a `LiveSite`; 404 on a plain `Site`. `/static/live.js` in `STATIC`.
  - `serve(site, port=DEFAULT_PORT, *, open_browser=True, opener=webbrowser.open,
    on_close=None)` — calls `site.close()` (when it has one) and `on_close()` on the way out.
  - `Server.heartbeat` (default `HEARTBEAT`; tests shorten it).

- [ ] **Step 1: Write the failing tests** — `test_webserve_live.py`:

```python
import contextlib
import http.client
import io
import json
import queue
import threading
import unittest
from unittest import mock

import townjson
import webserve


def _site():
    return webserve.LiveSite({"version": 1, "live": True}, lambda **kw: None)


def _read_message(resp):
    kind, data = None, None
    while True:
        line = resp.fp.readline().decode("utf-8")
        if not line:
            raise EOFError("the stream ended")
        if line == "\n" and (kind or data):
            return kind, data
        if line.startswith(":"):
            return "comment", line.strip()
        if line.startswith("event: "):
            kind = line[7:].strip()
        elif line.startswith("data: "):
            data = json.loads(line[6:])


class FramingTest(unittest.TestCase):
    def test_one_event_line_one_data_line_and_a_blank_line(self):
        raw = webserve.sse("tick", {"t": 1.5, "status": ["a\nb", "c"]})
        self.assertEqual(raw.decode("utf-8"),
                         'event: tick\ndata: {"t":1.5,"status":["a\\nb","c"]}\n\n')

    def test_the_heartbeat_is_a_comment(self):
        self.assertEqual(webserve.HEARTBEAT_BYTES, b": heartbeat\n\n")


class LiveSiteTest(unittest.TestCase):
    def test_a_new_client_gets_the_latest_state(self):
        site = _site()
        site.publish({"t": 0.0, "clawds": []})
        q, state = site.subscribe()
        self.assertEqual(state, {"t": 0.0, "clawds": []})

    def test_broadcast_reaches_every_client(self):
        site = _site()
        a, _ = site.subscribe()
        b, _ = site.subscribe()
        site.broadcast("tick", {"t": 1.0})
        self.assertEqual(a.get_nowait(), webserve.sse("tick", {"t": 1.0}))
        self.assertEqual(b.get_nowait(), webserve.sse("tick", {"t": 1.0}))

    def test_a_client_too_far_behind_is_dropped(self):
        site = _site()
        q, _ = site.subscribe()
        for i in range(webserve.MAX_BEHIND + 1):
            site.broadcast("tick", {"t": float(i)})
        items = [q.get_nowait() for _ in range(q.qsize())]
        self.assertIsNone(items[-1])
        site.broadcast("tick", {"t": 999.0})
        self.assertTrue(q.empty())

    def test_close_ends_every_stream(self):
        site = _site()
        q, _ = site.subscribe()
        site.close()
        self.assertIsNone(q.get_nowait())


class FakeLive:
    def __init__(self):
        self.version, self.t, self.ingested, self.steps = 1, 0.0, [], []

    def ingest(self, snapshot):
        self.ingested.append(snapshot)
        return ["ev"]

    def step(self, dt, now):
        self.t = now
        self.steps.append((dt, now))
        return False


class FakeDirector:
    def __init__(self):
        self.applied, self.steps = [], []

    def apply_events(self, events, now):
        self.applied.append(events)

    def step(self, dt, now):
        self.steps.append(now)


class SimulationTest(unittest.TestCase):
    def setUp(self):
        self.live, self.director, self.site = FakeLive(), FakeDirector(), _site()
        self.snapshots = queue.Queue()
        self.states = [{"version": 1, "clawds": {}, "scaffold": {}, "sites": [], "flags": [],
                        "status": ["a", ""], "camera": None}]
        self.builds = []
        patcher = mock.patch.object(townjson, "live_state",
                                    side_effect=lambda live, d: self.states[-1])
        patcher.start()
        self.addCleanup(patcher.stop)
        self.sim = webserve.Simulation(self.live, self.director, self.site, self.snapshots,
                                       lambda live: self.builds.append(live.version) or
                                       ({"version": live.version}, None))

    def test_a_step_drains_snapshots_into_the_town_and_the_director(self):
        self.snapshots.put("snap")
        self.sim.step_once(0.1, 0.1)
        self.assertEqual(self.live.ingested, ["snap"])
        self.assertEqual(self.director.applied, [["ev"]])
        self.assertEqual(self.director.steps, [0.1])

    def test_the_first_step_publishes_state_and_sends_no_tick(self):
        q, _ = self.site.subscribe()
        self.sim.step_once(0.0, 0.0)
        self.assertTrue(q.empty())
        _, state = self.site.subscribe()
        self.assertEqual(state["status"], ["a", ""])

    def test_a_change_is_broadcast_as_a_tick(self):
        self.sim.step_once(0.0, 0.0)
        q, _ = self.site.subscribe()
        self.states.append({**self.states[-1], "status": ["b", ""]})
        self.sim.step_once(0.1, 0.1)
        self.assertEqual(q.get_nowait(),
                         webserve.sse("tick", {"status": ["b", ""], "t": 0.1}))

    def test_a_new_version_rebuilds_the_town_and_sends_town(self):
        self.sim.step_once(0.0, 0.0)
        q, _ = self.site.subscribe()
        self.live.version = 2
        self.sim.step_once(0.1, 0.1)
        self.assertEqual(self.builds, [2])
        self.assertEqual(self.site.town, {"version": 2})
        self.assertEqual(q.get_nowait(), webserve.sse("town", {"t": 0.1, "version": 2}))


class EventsEndpointTest(unittest.TestCase):
    def setUp(self):
        self.site = _site()
        self.site.publish({"t": 0.0, "version": 1, "clawds": [], "scaffold": {}, "sites": [],
                           "flags": [], "status": ["hello", ""], "camera": None})
        self.server = webserve.make_server(self.site, 0)
        self.server.heartbeat = 0.2
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.addCleanup(self.site.close)

    def _open(self, host=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        conn.request("GET", "/events", headers={"Host": host or f"127.0.0.1:{self.port}"})
        return conn.getresponse()

    def test_events_starts_with_state_then_ticks_and_heartbeats(self):
        resp = self._open()
        self.assertEqual(resp.status, 200)
        self.assertEqual(resp.getheader("Content-Type"), "text/event-stream; charset=utf-8")
        self.assertIn("default-src 'self'", resp.getheader("Content-Security-Policy"))
        self.assertIsNone(resp.getheader("Access-Control-Allow-Origin"))
        kind, data = _read_message(resp)
        self.assertEqual((kind, data["status"]), ("state", ["hello", ""]))
        self.site.broadcast("tick", {"t": 1.0, "camera": "a"})
        self.assertEqual(_read_message(resp), ("tick", {"t": 1.0, "camera": "a"}))
        self.assertEqual(_read_message(resp), ("comment", ": heartbeat"))

    def test_events_refuses_another_host(self):
        self.assertEqual(self._open(host="evil.example:80").status, 403)

    def test_a_static_site_has_no_events(self):
        plain = webserve.make_server(webserve.Site({}, lambda **kw: None), 0)
        threading.Thread(target=plain.serve_forever, daemon=True).start()
        self.addCleanup(plain.server_close)
        self.addCleanup(plain.shutdown)
        port = plain.server_address[1]
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        conn.request("GET", "/events", headers={"Host": f"127.0.0.1:{port}"})
        self.assertEqual(conn.getresponse().status, 404)

    def test_live_js_is_served_and_its_test_is_not(self):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        for path, status in (("/static/live.js", 200), ("/static/live.test.mjs", 404)):
            conn.request("GET", path, headers={"Host": f"127.0.0.1:{self.port}"})
            resp = conn.getresponse()
            resp.read()
            self.assertEqual(resp.status, status, path)


class ServeClosesTest(unittest.TestCase):
    def test_ctrl_c_closes_the_site_and_calls_on_close(self):
        site, closed = _site(), []
        with mock.patch.object(webserve.Server, "serve_forever", side_effect=KeyboardInterrupt), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(webserve.serve(site, 0, open_browser=False,
                                            on_close=lambda: closed.append(True)), 0)
        self.assertEqual(closed, [True])
        self.assertTrue(site.closed)

    def test_a_port_in_use_still_calls_on_close(self):
        closed = []
        with mock.patch.object(webserve, "make_server", side_effect=SystemExit("in use")):
            with self.assertRaises(SystemExit):
                webserve.serve(_site(), 0, open_browser=False,
                               on_close=lambda: closed.append(True))
        self.assertEqual(closed, [True])


if __name__ == "__main__":
    unittest.main()
```

`web/live.js` doesn't exist until Task 5: create it in this task as a one-line module
(`export const LIVE = true;`) so `/static/live.js` is servable; Task 5 replaces it.

- [ ] **Step 2: Run them to see them fail**

Run: `.venv/bin/python -m unittest test_webserve_live -v`
Expected: FAIL — `webserve` has no `sse`, `LiveSite`, `Simulation`.

- [ ] **Step 3: Implement** in `webserve.py` (add `import queue`, `import threading`,
`import time`, `import townjson`):

```python
TICK = 0.1
HEARTBEAT = 15.0
MAX_BEHIND = 100
HEARTBEAT_BYTES = b": heartbeat\n\n"
EVENTS = "text/event-stream; charset=utf-8"


def sse(kind, data):
    """One Server-Sent Event. json.dumps escapes newlines, so data stays on one line."""
    body = json.dumps(data, separators=(",", ":"), ensure_ascii=False)
    return f"event: {kind}\ndata: {body}\n\n".encode("utf-8")


class LiveSite(Site):
    """A Site whose town moves: it keeps the latest state and a queue per /events client."""

    def __init__(self, town, select):
        super().__init__(town, select)
        self._lock = threading.Lock()
        self._clients = set()
        self._state = None
        self.closed = False

    def subscribe(self):
        q = queue.Queue()
        with self._lock:
            if self.closed:
                q.put(None)
            else:
                self._clients.add(q)
            return q, self._state

    def unsubscribe(self, q):
        with self._lock:
            self._clients.discard(q)

    def publish(self, state):
        with self._lock:
            self._state = state

    def retown(self, town, select):
        with self._lock:
            self.town, self.select = town, select

    def broadcast(self, kind, data):
        message = sse(kind, data)
        with self._lock:
            for q in list(self._clients):
                if q.qsize() >= MAX_BEHIND:
                    self._clients.discard(q)
                    q.put(None)
                else:
                    q.put(message)

    def close(self):
        with self._lock:
            self.closed = True
            for q in self._clients:
                q.put(None)
            self._clients.clear()


class Simulation(threading.Thread):
    """Steps the live town every TICK and streams what changed. The only thread that touches it."""

    name = "Simulation"

    def __init__(self, live, director, site, snapshots, build_town, *, clock=time.monotonic,
                 interval=TICK):
        super().__init__(daemon=True)
        self._live, self._director, self._site = live, director, site
        self._snapshots, self._build_town = snapshots, build_town
        self._clock, self._interval = clock, interval
        self._version = live.version
        self._prev = None
        self._halt = threading.Event()

    def step_once(self, dt, now):
        while True:
            try:
                snapshot = self._snapshots.get_nowait()
            except queue.Empty:
                break
            events = self._live.ingest(snapshot)
            if events:
                self._director.apply_events(events, self._live.t)
        self._live.step(dt, now)
        self._director.step(dt, now)
        if self._live.version != self._version:
            self._version = self._live.version
            self._site.retown(*self._build_town(self._live))
            self._site.broadcast("town", townjson.town_message(self._version, now))
        cur = townjson.live_state(self._live, self._director)
        self._site.publish(townjson.state_message(cur, now))
        if self._prev is not None:
            tick = townjson.tick_message(self._prev, cur, now)
            if tick is not None:
                self._site.broadcast("tick", tick)
        self._prev = cur

    def run(self):
        start = self._clock()
        prev = self._live.t
        while not self._halt.wait(self._interval):
            now = self._clock() - start
            self.step_once(now - prev, now)
            prev = now

    def stop(self):
        self._halt.set()
```

The handler routes `/events` before the static table, after the Host check:

```python
    def _events(self):
        site = self.server.site
        if not isinstance(site, LiveSite):
            return self._not_found()
        q, state = site.subscribe()
        try:
            self.send_response(200)
            self.send_header("Content-Type", EVENTS)
            self.send_header("Content-Security-Policy", self.server.policy)
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            if state is not None:
                self.wfile.write(sse("state", state))
                self.wfile.flush()
            while True:
                try:
                    message = q.get(timeout=self.server.heartbeat)
                except queue.Empty:
                    message = HEARTBEAT_BYTES
                if message is None:
                    return
                self.wfile.write(message)
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            return
        finally:
            site.unsubscribe(q)
```

`do_GET` routes `if path == "/events": return self._events()` right after the Host check.
`Server.__init__` sets `self.heartbeat = HEARTBEAT`. `STATIC` gains
`"/static/live.js": ("live.js", JS)`. `serve` gains `on_close=None`, called however `serve`
ends — Ctrl-C, a port in use, or the browser opener failing:

```python
def serve(site, port=DEFAULT_PORT, *, open_browser=True, opener=webbrowser.open,
          on_close=None):
    """Serve until Ctrl-C, after printing the address and opening it in a browser."""
    try:
        server = make_server(site, port)
        try:
            url = f"http://127.0.0.1:{server.server_address[1]}/"
            print(f"Town at {url}  (Ctrl-C to stop)", flush=True)
            if open_browser and not opener(url):
                print("Couldn't open a browser. Open the address above.", flush=True)
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            if isinstance(site, LiveSite):
                site.close()
            server.server_close()
    finally:
        if on_close is not None:
            on_close()
    return 0
```

`Server` already has `daemon_threads = True`, so `server_close()` doesn't wait for open
`/events` streams; `site.close()` ends them first anyway.

- [ ] **Step 4: Run the tests, old and new**

Run: `.venv/bin/python -m unittest test_webserve_live test_webserve -v` and
`python3 -m unittest test_webserve_live test_webserve -v`
Expected: PASS under both.

- [ ] **Step 5: Commit**

```bash
git add webserve.py web/live.js test_webserve_live.py
git commit -m "Stream the live town over Server-Sent Events from one simulation thread"
```

---

### Task 4: `towncode watch PATH --browser`, end to end

Spec: "How it runs", "Errors" (port in use, survey fails at start, re-survey fails, no browser),
Testing `LiveTown` (terminal watch unchanged).

**Files:**
- Modify: `towncode.py`
- Create: `test_watch_browser.py`

**Interfaces:**
- Consumes: Tasks 1–3.
- Produces (`towncode.py`): `--browser`, `--port N`, `--no-open` on `watch`;
  `_watch_browser(args, *, home="~", survey_dir=None, serve=None, clock=time.monotonic) -> int`;
  `_watch_live(args, *, home="~", survey_dir=None, clock=time.monotonic, watch_obj=None,
  resurvey_runner=None) -> types.SimpleNamespace(live, director, site, sim, poller, watch,
  snapshots)` — the wiring with no thread started, so tests can drive `sim.step_once`.

- [ ] **Step 1: Write the failing tests** — `test_watch_browser.py`. The end-to-end test runs
Phase 2's scripted worktree (`WatchE2ETest._run_script`) and, at each poll, feeds the snapshot
through the same wiring the server uses, collecting every message a browser would receive:

```python
import argparse
import json
import os
import shutil
import tempfile
import unittest

import fixture
import livetown
import towncode
import untouched
from test_watch import temp_survey
from test_watch_e2e import WatchE2ETest
from test_watch_e2e_view import WatchViewEndStateTest


def _args(path):
    return argparse.Namespace(path=path, browser=True, events=False, port=0, no_open=True)


def _decode(raw):
    head, data = raw.decode("utf-8").split("\n")[:2]
    return head[len("event: "):], json.loads(data[len("data: "):])


class WatchBrowserEndToEndTest(WatchE2ETest):
    _seed_orchestrator = WatchViewEndStateTest._seed_orchestrator

    def test_a_browser_sees_the_whole_run(self):
        """Phase 2's scripted run, fed through the server's own wiring, as a browser hears it."""
        self._seed_orchestrator(os.path.join(self.wts, "demo"))
        self.clock.advance(10)
        lw, messages = {}, []

        def drive(w, poll_once):
            if not lw:
                lw["it"] = towncode._watch_live(_args(self.main), home=self.home,
                                                survey_dir=self.survey, watch_obj=w,
                                                resurvey_runner=lambda fn: fn())
                lw["q"], state = lw["it"].site.subscribe()
                messages.append(("state", state))
                lw["w"] = w
                self.addCleanup(w.close)
            it = lw["it"]
            before = untouched.fingerprint(self.main)
            it.poller._drain_inbox()
            it.snapshots.put(livetown.WatchSnapshot(poll_once(), w.state()))
            for _ in range(10):
                it.sim.step_once(0.1, it.live.t + 0.1)
            while not lw["q"].empty():
                raw = lw["q"].get_nowait()
                if raw is not None:
                    messages.append(_decode(raw))
            self.assertEqual(untouched.differences(before, untouched.fingerprint(self.main)), {})

        self._run_script(on_poll=drive)
        it, w = lw["it"], lw["w"]
        for _ in range(120):
            if not any(c.role != "orchestrator" for c in it.live.crowd.clawds()):
                break

            def poll_once():
                batch = w.poll()
                self.clock.advance(1)
                return batch

            drive(w, poll_once)
        else:
            self.fail("non-orchestrator Clawds did not leave within 120 polls")

        ticks = [m for kind, m in messages if kind == "tick"]
        records = [r for t in ticks for r in t.get("clawds", [])]
        poses = {r["pose"] for r in records if r["id"] == "demo/task-1"}
        self.assertTrue({"walk", "hammer", "hop"} <= poses, poses)
        self.assertTrue(any("hub/a.py" in t.get("scaffold", {}) for t in ticks))
        self.assertTrue(any(s["path"] == "hub/new.py" for t in ticks for s in t.get("sites", [])))
        self.assertTrue(any("demo/task-1" in t.get("gone", []) for t in ticks))
        self.assertTrue(any(t.get("status", ["", ""])[1].startswith("merged team/world/demo")
                            for t in ticks))
        self.assertEqual([m["version"] for kind, m in messages if kind == "town"], [2])
        self.assertIn("hub/new.py", {b["path"] for b in it.site.town["buildings"]})
        self.assertEqual(it.site.town["version"], 2)
        _, final = it.site.subscribe()
        self.assertEqual((final["scaffold"], final["sites"]), ({}, []))
        self.assertEqual({r["role"] for r in final["clawds"]}, {"orchestrator"})
        for _kind, m in messages:
            self.assertNotIn("# e", json.dumps(m, ensure_ascii=False))


class WatchBrowserCLITest(unittest.TestCase):
    def setUp(self):
        self.main = fixture.make_repo(self, {"hub/a.py": "x = 1\n"})
        self.survey = temp_survey(self)
        self.home = tempfile.mkdtemp(prefix="watch-browser-home-")
        self.addCleanup(shutil.rmtree, self.home)

    def test_browser_and_events_dont_mix(self):
        with self.assertRaises(SystemExit) as cm:
            towncode.main(["watch", self.main, "--browser", "--events"])
        self.assertIn("--browser can't be combined with --events", str(cm.exception))

    def test_the_server_starts_with_state_and_closes_the_watch(self):
        served = {}

        def fake_serve(site, port, *, open_browser, on_close):
            served.update(site=site, port=port, open_browser=open_browser)
            served["state"] = site.subscribe()[1]
            on_close()
            served["closed"] = True
            return 0

        code = towncode._watch_browser(_args(self.main), home=self.home, survey_dir=self.survey,
                                       serve=fake_serve)
        self.assertEqual(code, 0)
        self.assertEqual((served["port"], served["open_browser"]), (0, False))
        self.assertIs(served["site"].town["live"], True)
        name = os.path.basename(os.path.realpath(self.main))
        self.assertEqual(served["state"]["status"][0],
                         f"{name}: no agents working. Watching main and 0 worktrees.")
        self.assertEqual(served["state"]["clawds"], [])
        self.assertTrue(served["closed"])


if __name__ == "__main__":
    unittest.main()
```

`poller._drain_inbox()` before each poll is exactly what `WatchPoller.run` does, so a landed
re-survey reaches the `Watch` the same way it does under the real poller thread.

- [ ] **Step 2: Run them to see them fail**

Run: `.venv/bin/python -m unittest test_watch_browser -v`
Expected: FAIL — no `_watch_live` / `_watch_browser`, `--browser` unknown to `watch`.

- [ ] **Step 3: Implement** in `towncode.py` (add `import crowd`, `import livetown`,
`import queue`, `import types` where missing; `townjson`, `webserve` and `partial` are already
imported for `view --browser`):

```python
def _watch_live(args, *, home="~", survey_dir=None, clock=time.monotonic, watch_obj=None,
                resurvey_runner=None):
    """Everything watch --browser runs, wired but not started."""
    import watch as watch_mod
    model, rows, plat, out = _watch_town(args.path)
    found = problems.find(model, rows)
    tmap = TownMap(model, plat, rows, found)
    sd = survey_dir or out
    w = watch_obj or watch_mod.Watch(args.path, home=home, survey_dir=sd, model=model)
    try:
        repo_name = os.path.basename(os.path.realpath(args.path))
        live = livetown.LiveTown(tmap, Roads(tmap, model, found), model, rows, plat, repo_name,
                                 w.state().main_tip, args.path, w.clock,
                                 resurvey_runner=resurvey_runner)
        director = crowd.CameraDirector(livetown.TargetRecorder(), live.crowd, tmap)
        snapshots = queue.Queue()
        poller = livetown.WatchPoller(w, snapshots, clock)
        live.note_resurvey = lambda m, tip: poller.inbox.put((m, tip))

        def build_town(lt):
            v = viewer.Viewer(lt.m, lt.roads, lt.model, lt.found)
            return (townjson.town(lt.m, lt.roads, v.describe, repo=repo_name,
                                  version=lt.version, live=True),
                    partial(townjson.selection, lt.m, lt.roads, lt.model))

        site = webserve.LiveSite(*build_town(live))
        sim = webserve.Simulation(live, director, site, snapshots, build_town, clock=clock)
        sim.step_once(0.0, 0.0)
    except Exception:
        if watch_obj is None:
            w.close()
        raise
    return types.SimpleNamespace(live=live, director=director, site=site, sim=sim,
                                 poller=poller, watch=w, snapshots=snapshots)


def _watch_browser(args, *, home="~", survey_dir=None, serve=None, clock=time.monotonic):
    """watch --browser: poll and simulate on threads, serve until Ctrl-C, then close the watch."""
    lw = _watch_live(args, home=home, survey_dir=survey_dir, clock=clock)
    lw.poller.start()
    lw.sim.start()

    def close():
        lw.sim.stop()
        lw.poller.close_event.set()
        lw.sim.join(timeout=2)
        lw.poller.join(timeout=2)
        lw.watch.close()

    return (serve or webserve.serve)(lw.site, port=args.port, open_browser=not args.no_open,
                                     on_close=close)
```

In `_watch`, before the `--events` branch:

```python
    if getattr(args, "browser", False):
        if args.events:
            raise SystemExit("watch --browser can't be combined with --events")
        return _watch_browser(args, home=home, survey_dir=survey_dir)
```

The `watch` parser gains the same three options `view` has:

```python
    cmd.add_argument("--browser", action="store_true",
                     help="watch in 3D in a browser tab on this machine")
    cmd.add_argument("--port", type=int, default=webserve.DEFAULT_PORT,
                     help=f"port for --browser (default {webserve.DEFAULT_PORT}; 0 picks any free port)")
    cmd.add_argument("--no-open", action="store_true",
                     help="with --browser, print the address without opening a browser")
```

`_watch_live` must not start any thread: `WatchPoller` and `Simulation` start only in
`_watch_browser`, so the end-to-end test drives `sim.step_once` itself.

- [ ] **Step 4: Run the tests, then the CLI and watch tests**

Run: `.venv/bin/python -m unittest test_watch_browser -v`
Expected: PASS.
Run: `.venv/bin/python -m unittest test_towncode test_watch_e2e test_watch_e2e_view -v`
Expected: PASS.

- [ ] **Step 5: Try it for real on a scratch repo**

```bash
.venv/bin/python towncode.py watch "$(mktemp -d)" --browser --no-open --port 0
```

Expected: `not a git repository`-style error from `_require_repo`, the same as terminal watch.
Then on this checkout: `.venv/bin/python towncode.py watch . --browser --no-open --port 0`
prints `Town at http://127.0.0.1:NNNN/  (Ctrl-C to stop)`; `curl -sN
http://127.0.0.1:NNNN/events | head -2` shows `event: state` and a `data:` line; `Ctrl-C` exits 0.

- [ ] **Step 6: Commit**

```bash
git add towncode.py test_watch_browser.py
git commit -m "Add towncode watch --browser: the live town served in 3D on this machine"
```

---

### Task 5: The browser's live logic, tested with Node

Spec: "Movement contract" (browser side), "What you can do" (keys, modes), "What you see"
(labels fade, up to 8 scaffolded names, poses' fixed lengths), "Status bar" line 3.

**Files:**
- Create: `web/live.js` (replaces Task 3's one-liner), `web/live.test.mjs`, `test_web_live.py`

**Interfaces:**
- Produces (`web/live.js`, ES module, imports nothing):
  - `offsetFor(clientSeconds, t) -> number` (client − server)
  - `walkPosition(rec, now, stepTime) -> {x, z, facing: [dx, dz], moving: bool, step: int}`;
    `rec.at` is the server time the record arrived
  - `poseLift(rec, now, poses, pxPerUnit) -> number` (tiles up; hammer bounce, hop arcs)
  - `dropLift(elapsed, drop, pxPerUnit) -> number` (tiles up; `drawtown.drop_offset`'s curve)
  - `applyState(msg) -> live`, `applyTick(live, msg) -> live`; `live = {version, clawds: Map,
    scaffold, sites, flags, status, camera}`; every stored record gets `at = msg.t`
  - `AUTO = {kind: "auto"}`, `PAUSED = {kind: "paused"}`, `follow(n) -> {kind: "follow", n}`
  - `pressKey(mode, key, live) -> mode`, `userMoved(mode) -> mode`,
    `settle(mode, live) -> mode` (a follow whose Clawd is gone becomes auto),
    `cameraClawd(mode, live) -> record | null`
  - `legend(live, mode) -> string`
  - `labelOpacity(distance, fade) -> number` (`fade = {start, end}`)
  - `nearestScaffold(scaffold, centres, target, n = 8) -> [path]`
  - `newBuildings(oldDoc, newDoc) -> Set(path)`

- [ ] **Step 1: Write the failing tests** — `web/live.test.mjs`:

```js
import { test } from "node:test";
import assert from "node:assert/strict";
import * as L from "./live.js";

const walker = { id: "a", pose: "walk", tile: [0, 0], facing: [1, 0], follow: 1, team: "world",
  path: [[0, 0], [1, 0], [2, 0]], path_i: 0, walk_t: 0, at: 10 };

test("a walk advances one tile per step_time from path_i + walk_t", () => {
  assert.deepEqual(L.walkPosition(walker, 10, 0.16), { x: 0.5, z: 0.5, facing: [1, 0], moving: true, step: 0 });
  const half = L.walkPosition(walker, 10.08, 0.16);
  assert.ok(Math.abs(half.x - 1.0) < 1e-9 && half.z === 0.5 && half.moving);
  const done = L.walkPosition(walker, 20, 0.16);
  assert.deepEqual(done, { x: 2.5, z: 0.5, facing: [1, 0], moving: false, step: 2 });
});

test("a walk resumes from walk_t", () => {
  const p = L.walkPosition({ ...walker, path_i: 1, walk_t: 0.5 }, 10, 0.16);
  assert.ok(Math.abs(p.x - 2.0) < 1e-9);
});

test("standing Clawds stand on their tile facing their way", () => {
  const p = L.walkPosition({ ...walker, pose: "idle", tile: [4, 7], facing: [0, 1] }, 99, 0.16);
  assert.deepEqual(p, { x: 4.5, z: 7.5, facing: [0, 1], moving: false, step: 0 });
});

test("hops fall 15, 8 then 4 px and stop", () => {
  const poses = { hop: { heights_px: [15, 8, 4], time: 0.15 }, hammer: { time: 0.5, bounces: 3, height_px: 3 } };
  const hop = { pose: "hop", at: 0 };
  assert.ok(Math.abs(L.poseLift(hop, 0.075, poses, 1) - 15) < 1e-9);
  assert.ok(Math.abs(L.poseLift(hop, 0.225, poses, 1) - 8) < 1e-9);
  assert.equal(L.poseLift(hop, 1.0, poses, 1), 0);
  assert.equal(L.poseLift({ pose: "hammer", at: 0 }, 0.6, poses, 1), 0);
  assert.ok(L.poseLift({ pose: "hammer", at: 0 }, 0.08, poses, 1) > 0);
});

test("a dropping building starts 48 px up and lands at 0.42 s", () => {
  const drop = { height_px: 48, time: 0.42 };
  assert.equal(L.dropLift(0, drop, 1), 48);
  assert.equal(L.dropLift(0.42, drop, 1), 0);
  assert.ok(L.dropLift(0.21, drop, 1) > 0 && L.dropLift(0.21, drop, 1) < 48);
});

test("state then ticks keep a map of records stamped with their time", () => {
  let live = L.applyState({ t: 1, version: 1, clawds: [walker], scaffold: {}, sites: [], flags: [], status: ["a", ""], camera: null });
  assert.equal(live.clawds.get("a").at, 1);
  live = L.applyTick(live, { t: 2, clawds: [{ ...walker, pose: "idle" }], camera: "a" });
  assert.equal(live.clawds.get("a").pose, "idle");
  assert.equal(live.clawds.get("a").at, 2);
  assert.equal(live.camera, "a");
  live = L.applyTick(live, { t: 3, gone: ["a"], status: ["b", ""] });
  assert.equal(live.clawds.size, 0);
  assert.deepEqual(live.status, ["b", ""]);
});

test("keys: digits follow, 0 is auto, moving the camera pauses, a gone Clawd ends a follow", () => {
  const live = L.applyState({ t: 0, version: 1, clawds: [walker], scaffold: {}, sites: [], flags: [], status: ["", ""], camera: "a" });
  assert.deepEqual(L.pressKey(L.AUTO, "1", live), L.follow(1));
  assert.deepEqual(L.pressKey(L.AUTO, "2", live), L.AUTO);
  assert.deepEqual(L.pressKey(L.follow(1), "0", live), L.AUTO);
  assert.deepEqual(L.userMoved(L.AUTO), L.PAUSED);
  assert.deepEqual(L.userMoved(L.follow(1)), L.PAUSED);
  assert.deepEqual(L.pressKey(L.PAUSED, "0", live), L.AUTO);
  assert.equal(L.cameraClawd(L.AUTO, live).id, "a");
  assert.equal(L.cameraClawd(L.follow(1), live).id, "a");
  assert.equal(L.cameraClawd(L.PAUSED, live), null);
  const empty = L.applyTick(live, { t: 1, gone: ["a"] });
  assert.deepEqual(L.settle(L.follow(1), empty), L.AUTO);
});

test("the legend lists follow numbers and the mode", () => {
  const live = L.applyState({ t: 0, version: 1, clawds: [walker, { ...walker, id: "b", follow: 2, team: "render" }, { ...walker, id: "o", follow: null, team: null }], scaffold: {}, sites: [], flags: [], status: ["", ""], camera: null });
  assert.equal(L.legend(live, L.AUTO),
    "0 auto  1 world  2 render  ·  drag orbit  scroll zoom  click inspect  Esc clear   [auto]");
  assert.ok(L.legend(live, L.follow(2)).endsWith("[following 2]"));
  assert.ok(L.legend(live, L.PAUSED).endsWith("[paused, 0 resumes]"));
});

test("labels fade between start and end", () => {
  const fade = { start: 30, end: 60 };
  assert.equal(L.labelOpacity(10, fade), 1);
  assert.equal(L.labelOpacity(45, fade), 0.5);
  assert.equal(L.labelOpacity(90, fade), 0);
});

test("the 8 scaffolded buildings nearest the target", () => {
  const centres = new Map(Array.from({ length: 10 }, (_, i) => [`p${i}`, [i, 0]]));
  const scaffold = Object.fromEntries([...centres.keys()].map((p) => [p, 0]));
  assert.deepEqual(L.nearestScaffold(scaffold, centres, [9, 0]), ["p9", "p8", "p7", "p6", "p5", "p4", "p3", "p2"]);
  assert.deepEqual(L.nearestScaffold({ missing: 0 }, centres, [0, 0]), []);
});

test("new buildings are the paths the old town didn't have", () => {
  const old = { buildings: [{ path: "a" }] }, now = { buildings: [{ path: "a" }, { path: "b" }] };
  assert.deepEqual([...L.newBuildings(old, now)], ["b"]);
});
```

`test_web_live.py`:

```python
import os
import shutil
import subprocess
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))


@unittest.skipUnless(shutil.which("node"), "node is not installed")
class WebLiveTest(unittest.TestCase):
    def test_the_browser_live_logic(self):
        done = subprocess.run(["node", "--test", os.path.join(HERE, "web", "live.test.mjs")],
                              capture_output=True, text=True, timeout=120)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run them to see them fail**

Run: `node --test web/live.test.mjs`
Expected: FAIL — `live.js` exports none of these.

- [ ] **Step 3: Write `web/live.js`**

```js
// The live watch's logic, with no drawing, so node --test can check it. Python decides where
// each Clawd goes; this only works out where it is now and what the camera should look at.

export const AUTO = { kind: "auto" };
export const PAUSED = { kind: "paused" };
export const follow = (n) => ({ kind: "follow", n });
const HINTS = "drag orbit  scroll zoom  click inspect  Esc clear";

export function offsetFor(clientSeconds, t) {
  return clientSeconds - t;
}

// Python's crowd interpolates between path[path_i] and path[path_i + 1] by walk_t and moves on
// one tile per step_time; this walks on from where the record left off.
export function walkPosition(rec, now, stepTime) {
  const path = rec.path || [];
  if (rec.pose !== "walk" || path.length < 2) {
    return { x: rec.tile[0] + 0.5, z: rec.tile[1] + 0.5, facing: rec.facing, moving: false, step: 0 };
  }
  const last = path.length - 1;
  const progress = rec.path_i + rec.walk_t + Math.max(0, now - rec.at) / stepTime;
  if (progress >= last) {
    const [x, z] = path[last], [px, pz] = path[last - 1];
    return { x: x + 0.5, z: z + 0.5, facing: [x - px, z - pz], moving: false, step: last };
  }
  const i = Math.floor(progress), f = progress - i;
  const [ax, az] = path[i], [bx, bz] = path[i + 1];
  return { x: ax + 0.5 + (bx - ax) * f, z: az + 0.5 + (bz - az) * f, facing: [bx - ax, bz - az],
    moving: true, step: i };
}

export function poseLift(rec, now, poses, pxPerUnit) {
  const elapsed = Math.max(0, now - rec.at);
  if (rec.pose === "hop") {
    const { heights_px: heights, time } = poses.hop;
    const i = Math.floor(elapsed / time);
    if (i >= heights.length) return 0;
    const f = (elapsed - i * time) / time;
    return (heights[i] * 4 * f * (1 - f)) / pxPerUnit;
  }
  if (rec.pose === "hammer") {
    const { time, bounces, height_px: h } = poses.hammer;
    if (elapsed >= time) return 0;
    return (h * Math.abs(Math.sin((Math.PI * bounces * elapsed) / time))) / pxPerUnit;
  }
  return 0;
}

// drawtown.drop_offset: ease-out with a slight overshoot.
export function dropLift(elapsed, drop, pxPerUnit) {
  if (elapsed <= 0) return drop.height_px / pxPerUnit;
  if (elapsed >= drop.time) return 0;
  const u = elapsed / drop.time;
  return (drop.height_px * (1 - u) ** 2 * (1 + 0.12 * Math.sin(u * Math.PI))) / pxPerUnit;
}

export function applyState(msg) {
  return {
    version: msg.version,
    clawds: new Map(msg.clawds.map((r) => [r.id, { ...r, at: msg.t }])),
    scaffold: msg.scaffold, sites: msg.sites, flags: msg.flags, status: msg.status,
    camera: msg.camera,
  };
}

export function applyTick(live, msg) {
  for (const r of msg.clawds || []) live.clawds.set(r.id, { ...r, at: msg.t });
  for (const id of msg.gone || []) live.clawds.delete(id);
  for (const key of ["scaffold", "sites", "flags", "status", "camera"]) {
    if (key in msg) live[key] = msg[key];
  }
  return live;
}

const byFollow = (live, n) => [...live.clawds.values()].find((r) => r.follow === n) || null;

export function pressKey(mode, key, live) {
  if (key === "0") return AUTO;
  if (/^[1-9]$/.test(key) && byFollow(live, Number(key))) return follow(Number(key));
  return mode;
}

export function userMoved(mode) {
  return PAUSED;
}

export function settle(mode, live) {
  return mode.kind === "follow" && !byFollow(live, mode.n) ? AUTO : mode;
}

export function cameraClawd(mode, live) {
  if (mode.kind === "follow") return byFollow(live, mode.n);
  if (mode.kind === "auto" && live.camera) return live.clawds.get(live.camera) || null;
  return null;
}

export function legend(live, mode) {
  const parts = ["0 auto", ...[...live.clawds.values()].filter((r) => r.follow != null)
    .sort((a, b) => a.follow - b.follow).map((r) => `${r.follow} ${r.team || "?"}`)];
  const state = mode.kind === "follow" ? `[following ${mode.n}]`
    : mode.kind === "paused" ? "[paused, 0 resumes]" : "[auto]";
  return `${parts.join("  ")}  ·  ${HINTS}   ${state}`;
}

export function labelOpacity(distance, fade) {
  if (distance <= fade.start) return 1;
  if (distance >= fade.end) return 0;
  return 1 - (distance - fade.start) / (fade.end - fade.start);
}

export function nearestScaffold(scaffold, centres, target, n = 8) {
  return Object.keys(scaffold).filter((p) => centres.has(p))
    .map((p) => [p, Math.hypot(centres.get(p)[0] - target[0], centres.get(p)[1] - target[1])])
    .sort((a, b) => a[1] - b[1] || (a[0] < b[0] ? -1 : 1)).slice(0, n).map(([p]) => p);
}

export function newBuildings(oldDoc, newDoc) {
  const had = new Set(oldDoc.buildings.map((b) => b.path));
  return new Set(newDoc.buildings.filter((b) => !had.has(b.path)).map((b) => b.path));
}
```

`userMoved` ignores `mode` on purpose: any camera move by hand pauses, from auto or from a
follow (ruling recorded in the ledger); keep the parameter so callers read naturally.

- [ ] **Step 4: Run the tests**

Run: `node --test web/live.test.mjs` then `.venv/bin/python -m unittest test_web_live -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add web/live.js web/live.test.mjs test_web_live.py
git commit -m "Work out where each Clawd is and what the camera follows in the browser, tested with node"
```

---

### Task 6: Clawds, Town Hall, scaffolding, sites and flags in the 3D town

Spec: "What you see" — Watch on top (Clawds, Town Hall, scaffolding, sites, flags), Scale;
"Data and messages" (`/events`); Performance (one merged mesh per Clawd).

**Files:**
- Modify: `web/town3d.js`, `web/look.js`, `smoke_web.py`

**Interfaces:**
- Consumes: Task 3's `/events`; Task 2's `town.json` `hall`, `step_time`, `live`; Task 5's
  `live.js`.
- Produces (`town3d.js`): `view.townGroup` (all static meshes; Task 8 swaps it),
  `view.liveGroup` (everything live), `view.live` (the `live.js` state),
  `view.offset` (client − server seconds), `clawdObject(rec)` / `placeClawds(now)`;
  `town3d.report()` gains `clawds` (count drawn), `scaffolded`, `sites`, `flags`,
  `poses` ({id: pose}), `live` (stream connected).
- Produces (`look.js`): `SCARVES`, `CLAWD`, `POSES`, `SCAFFOLD`, `SITE`, `FLAG`, `LECTERN`.

- [ ] **Step 1: Add the looks** to `web/look.js` (starting values copied from `watch.PALETTE`,
`sprites.CLAWD`, `watch._REVIEWER_GREY`, `drawtown.HAT/GLASSES/LECTERN/SITE_ORANGE`,
`crowd.HAMMER_TIME/HOP_HEIGHTS/HOP_TIME`):

```js
// Watch. SCARVES are watch's team palette, in the order watch.json assigns them.
export const SCARVES = [[165, 91, 91], [140, 113, 35], [165, 165, 74], [85, 89, 49],
  [103, 165, 41], [27, 89, 22], [49, 140, 49], [91, 165, 103]];
// A Clawd is boxes in voxels: [x, y, z, width, height, depth, part], feet at y = 0, facing +z.
export const CLAWD = {
  voxel: 0.08,
  colours: { body: [217, 119, 87], dark: [178, 92, 64], eyes: [28, 24, 22],
    reviewer: [150, 150, 156], glasses: [30, 26, 24], hat: [60, 60, 70] },
  body: [[0, 5, 0, 7, 2, 4, "body"], [0, 3.5, 0, 9, 1, 4, "body"], [0, 2.5, 0, 7, 1, 4, "dark"],
    [-1.5, 5.3, 2.05, 1, 1, 0.1, "eyes"], [1.5, 5.3, 2.05, 1, 1, 0.1, "eyes"]],
  legs: [
    [[-3, 1, 0, 1, 2, 1, "dark"], [-1, 1, 0, 1, 2, 1, "dark"], [1, 1, 0, 1, 2, 1, "dark"], [3, 1, 0, 1, 2, 1, "dark"]],
    [[-3, 1, 0, 1, 2, 1, "dark"], [-1, 1.5, 0, 1, 1, 1, "dark"], [1, 1, 0, 1, 2, 1, "dark"], [3, 1.5, 0, 1, 1, 1, "dark"]],
    [[-3, 1.5, 0, 1, 1, 1, "dark"], [-1, 1, 0, 1, 2, 1, "dark"], [1, 1.5, 0, 1, 1, 1, "dark"], [3, 1, 0, 1, 2, 1, "dark"]],
  ],
  scarf: [[0, 4.2, 0, 7.4, 0.6, 4.4, "scarf"], [2.4, 3.4, 2.3, 1, 1.4, 0.3, "scarf"]],
  glasses: [[-1.5, 5.3, 2.15, 1.6, 1.4, 0.12, "glasses"], [1.5, 5.3, 2.15, 1.6, 1.4, 0.12, "glasses"],
    [0, 5.5, 2.15, 1.4, 0.3, 0.12, "glasses"]],
  hat: [[0, 6.5, 0, 5, 1, 3.6, "hat"], [0, 7.5, 0, 3.4, 1, 2.6, "hat"], [0, 8.4, 0, 2, 0.8, 1.6, "hat"],
    [0, 9.1, 0, 0.8, 0.6, 0.8, "hat"]],
  bob_px: 1,
};
export const POSES = { hammer: { time: 0.5, bounces: 3, height_px: 3 },
  hop: { heights_px: [15, 8, 4], time: 0.15 }, peer: { lean_deg: 18 } };
export const SCAFFOLD = { pole: 0.06, rail: 0.04, rail_every_px: 6, inset: 0.04 };
export const SITE = { colour: [232, 128, 48], width: 0.7, height_px: 3, frame: 0.05 };
export const FLAG = { pole: [220, 220, 228], pole_height: 1.1, pole_width: 0.04,
  cloth_width: 0.36, cloth_height: 0.22 };
export const LECTERN = { colour: [120, 90, 60], width: 0.42, height: 0.55, top: 0.12 };
```

Add every new key to `NEEDED` in `town3d.js`.

- [ ] **Step 2: Restructure the scene** so static meshes live in `view.townGroup` and the live
layer in `view.liveGroup` (both children of `view.scene`); `build(doc)` fills `townGroup` only,
so Task 8 can rebuild it without touching Clawds.

- [ ] **Step 3: Build Clawd meshes** — one merged `BufferGeometry` per Clawd per leg frame, with
vertex colours, from the `CLAWD` boxes:

```js
// One mesh from many coloured boxes: their geometries baked together, so a Clawd is one draw.
function mergeBoxes(boxes, colours) {
  const positions = [], colors = [], indices = [];
  const m = new THREE.Matrix4(), p = new THREE.Vector3(), s = new THREE.Vector3();
  const q = new THREE.Quaternion();
  for (const [x, y, z, w, h, d, part] of boxes) {
    const g = view.box.clone();
    g.applyMatrix4(m.compose(p.set(x, y, z), q, s.set(w, h, d)));
    const base = positions.length / 3, c = colour(colours[part]);
    const pos = g.getAttribute("position"), shade = g.getAttribute("color");
    for (let i = 0; i < pos.count; i++) {
      positions.push(pos.getX(i), pos.getY(i), pos.getZ(i));
      colors.push(c.r * shade.getX(i), c.g * shade.getY(i), c.b * shade.getZ(i));
    }
    for (const i of g.getIndex().array) indices.push(base + i);
    g.dispose();
  }
  const out = new THREE.BufferGeometry();
  out.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
  out.setAttribute("color", new THREE.Float32BufferAttribute(colors, 3));
  out.setIndex(indices);
  return out;
}

function clawdObject(rec) {
  const C = LOOK.CLAWD;
  const colours = { ...C.colours,
    scarf: LOOK.SCARVES[(rec.scarf ?? 0) % LOOK.SCARVES.length],
    dark: rec.role === "reviewer" ? C.colours.reviewer : C.colours.dark };
  const extra = rec.role === "implementer" ? C.scarf : rec.role === "reviewer" ? C.glasses
    : rec.role === "orchestrator" ? C.hat : [];
  const material = new THREE.MeshBasicMaterial({ vertexColors: true });
  const group = new THREE.Group();
  group.scale.setScalar(C.voxel);
  const frames = C.legs.map((legs) => {
    const mesh = new THREE.Mesh(mergeBoxes([...C.body, ...extra, ...legs], colours), material);
    mesh.visible = false;
    group.add(mesh);
    return mesh;
  });
  frames[0].visible = true;
  group.userData = { frames, role: rec.role, scarf: rec.scarf };
  return group;
}
```

A Clawd's object is rebuilt only when its `role` or `scarf` changes.

- [ ] **Step 4: Connect to `/events`** when `doc.live` is true:

```js
function connect() {
  const source = new EventSource("/events");
  const stamp = (msg) => { view.offset = L.offsetFor(performance.now() / 1000, msg.t); };
  source.addEventListener("state", (e) => {
    const msg = JSON.parse(e.data);
    stamp(msg);
    view.live = L.applyState(msg);
    town3d.live = true;
    syncLive();
  });
  source.addEventListener("tick", (e) => {
    const msg = JSON.parse(e.data);
    stamp(msg);
    if (view.live) {
      view.live = L.applyTick(view.live, msg);
      syncLive();
    }
  });
  source.onerror = () => { town3d.live = false; };
  view.source = source;
}
```

`syncLive()` adds an object for each new record, removes objects whose ids are gone, and
rebuilds the scaffolding, site and flag meshes from `view.live.scaffold/sites/flags` (they are
small: build them as one instanced `Boxes` mesh each with `Boxes` from the static code).

- [ ] **Step 5: Place everything each frame** (call from the animation loop before rendering):

```js
function serverNow() {
  return performance.now() / 1000 - view.offset;
}

function placeClawds(now) {
  if (!view.live) return;
  for (const [id, rec] of view.live.clawds) {
    const obj = view.clawds.get(id);
    const at = L.walkPosition(rec, now, view.doc.step_time);
    const lift = L.poseLift(rec, now, LOOK.POSES, LOOK.PX_PER_UNIT);
    const step = at.moving ? 1 + (Math.floor((now - rec.at) / view.doc.step_time) % 2) : 0;
    obj.userData.frames.forEach((m, i) => { m.visible = i === step; });
    const bob = at.moving && step === 1 ? LOOK.CLAWD.bob_px / LOOK.PX_PER_UNIT : 0;
    obj.position.set(at.x, lift + bob, at.z);
    obj.rotation.set(rec.pose === "peer" ? THREE.MathUtils.degToRad(LOOK.POSES.peer.lean_deg) : 0,
      Math.atan2(at.facing[0], at.facing[1]), 0);
  }
}
```

- [ ] **Step 6: Draw the watch props** (each from `look.js` only):
  - **Town Hall:** a lectern (`LECTERN`: a box with a slanted top box) on `doc.hall`.
  - **Scaffolding:** for each `scaffold` path in `view.doc.buildings`, poles at the four corners
    of its bottom tier (inset `SCAFFOLD.inset`), height = its top tier's `z1` in px, and rails
    around the building every `SCAFFOLD.rail_every_px`, in `SCARVES[scarf]`.
  - **Sites:** for each `{tile, size, scarf}`, an orange box `SITE.width × size` wide and
    `SITE.height_px` tall, plus a low frame of `SITE.frame`-thick boxes in `SCARVES[scarf]`.
  - **Flags:** for each `{building, scarf}`, a pole (`FLAG.pole`) by the building's lot corner
    nearest the front, with a cloth box (`FLAG.cloth_*`) in `SCARVES[scarf]`.

- [ ] **Step 7: Report it** — `town3d.report()` adds
`clawds: view.clawds.size, scaffolded: Object.keys(view.live?.scaffold || {}).length,
sites: (view.live?.sites || []).length, flags: (view.live?.flags || []).length,
poses: Object.fromEntries([...(view.live?.clawds || new Map()).values()].map((r) => [r.id, r.pose])),
live: town3d.live`.

- [ ] **Step 8: Teach the smoke check `--watch`** — in `smoke_web.py`, `--watch` builds the smoke
repo, adds a worktree `wt-demo` on branch `team/world/demo` with a ledger
`.superpowers/sdd/run-1/task-1-brief.md`, starts `towncode.py watch ROOT --browser --no-open
--port 0`, waits for `window.town3d.ready && window.town3d.report().clawds >= 1` (60 s), appends
a line to `app/main.py` in the worktree, waits until `report().poses["wt-demo/task-1"] === "walk"`
or `report().scaffolded >= 1` (30 s), saves `/tmp/towncode-3d-watch.png`, and checks
`report().missing` is empty. Remove the worktree and repo afterwards.

- [ ] **Step 9: Verify**

Run: `.venv/bin/python -m unittest test_webserve test_webserve_live test_web_live -v`
Expected: PASS.
Run: `python3 smoke_web.py` then `python3 smoke_web.py --watch`
Expected: both print their checks passing and the screenshot path; look at
`/tmp/towncode-3d-watch.png` and confirm a Clawd and scaffolding are visible.

- [ ] **Step 10: Commit**

```bash
git add web/town3d.js web/look.js smoke_web.py
git commit -m "Draw voxel Clawds walking the 3D town, with Town Hall, scaffolding, sites and flags"
```

---

### Task 7: Labels, the status bar, the automatic camera and follow keys

Spec: "What you see" — Labels, Status bar; "What you can do" — Camera, Automatic camera, Keys.

**Files:**
- Modify: `web/town3d.js`, `web/look.js`, `web/index.html`, `web/town3d.css`, `smoke_web.py`

**Interfaces:**
- Consumes: Task 5's `pressKey`, `userMoved`, `settle`, `cameraClawd`, `legend`,
  `labelOpacity`, `nearestScaffold`; Task 6's `view.live`, `view.clawds`, `placeClawds`.
- Produces: `view.mode` (a `live.js` mode); `town3d.report()` gains `mode` (`"auto"`,
  `"follow 2"`, `"paused"`), `labels` (count shown), `line1`, `line2`, `line3`;
  `town3d.press(key)` for the smoke check.
- Produces (`look.js`): `LABEL = { fade: { start: 30, end: 70 }, lift: 0.35, max_scaffold: 8 }`,
  and `CAMERA` gains `follow_ease: 2.5` (per second) and `follow_distance: 18` (tiles).

- [ ] **Step 1: Add the label layer** — `index.html` gets `<div id="labels"></div>` after
`<header id="status">…</header>`; `town3d.css` gets:

```css
#labels { position: fixed; inset: 0; pointer-events: none; overflow: hidden; }
#labels .label { position: absolute; transform: translate(-50%, -100%); white-space: pre;
  padding: 1px 5px; border-radius: 3px; font-size: 12px; background: rgba(14, 18, 32, 0.78);
  color: rgb(236, 236, 236); }
#labels .label.place { color: rgb(200, 200, 210); background: rgba(14, 18, 32, 0.6); }
```

(CSS isn't a colour Python sends; look.js stays the home of scene colours. Keep label colours
in the CSS file, as plan 1 did for the status bar.)

- [ ] **Step 2: Place labels each frame** — one `div.label` per Clawd (text = `rec.label`), at the
Clawd's head (`obj.position` + `LABEL.lift`) projected with `camera`; hidden when behind the
camera; opacity `L.labelOpacity(distance from camera, LABEL.fade)`. A `div.label.place` reading
`Town Hall` over `doc.hall`. Up to `LABEL.max_scaffold` `div.label.place` labels reading `● path`
for `L.nearestScaffold(view.live.scaffold, centres, [target.x, target.z])` where `centres` maps a
building path to its lot centre and `target` is `controls.target`. Set text with `textContent`
only. Reuse `div`s by key; remove those no longer wanted.

- [ ] **Step 3: The status bar** — on every `state`/`tick`, `#line1` and `#line2` get
`view.live.status[0]` and `[1]`; `#line3` gets `L.legend(view.live, view.mode)`. Before the
stream connects, keep plan 1's line 1 and `HINT`.

- [ ] **Step 4: The automatic camera** — each frame, `view.mode = L.settle(view.mode, view.live)`;
`const rec = L.cameraClawd(view.mode, view.live)`; if `rec`, ease `controls.target` toward the
Clawd's current position and the camera's distance toward `CAMERA.follow_distance`, moving the
camera by the same delta as the target so the viewing angle is kept:

```js
function followCamera(camera, controls, dt) {
  const rec = view.live && L.cameraClawd(view.mode, view.live);
  if (!rec) return;
  const obj = view.clawds.get(rec.id);
  if (!obj) return;
  const k = 1 - Math.exp(-LOOK.CAMERA.follow_ease * dt);
  const goal = new THREE.Vector3(obj.position.x, 0, obj.position.z);
  const delta = goal.sub(controls.target).multiplyScalar(k);
  controls.target.add(delta);
  camera.position.add(delta);
  const offset = camera.position.clone().sub(controls.target);
  const d = offset.length();
  offset.setLength(d + (LOOK.CAMERA.follow_distance - d) * k);
  camera.position.copy(controls.target).add(offset);
}
```

OrbitControls fires `start` only for user input: `controls.addEventListener("start", () => {
view.mode = L.userMoved(view.mode); })`. The camera still starts looking at Town Hall
(`controls.target` = `doc.hall` centre at load when `doc.live`).

- [ ] **Step 5: Keys** — in the existing `keydown` handler, digits `0`–`9` call
`view.mode = L.pressKey(view.mode, e.key, view.live)` and refresh `#line3`; `Escape` still
clears the selection. Expose `town3d.press = (key) => { … same … }`.

- [ ] **Step 6: Extend `smoke_web.py --watch`** — after the walk is seen: check
`report().labels >= 1`, `report().line1` equals the last `status[0]` (read it from a fresh
`/events` connection's `state`), `report().mode === "auto"`; call `town3d.press("1")` and check
`mode === "follow 1"`; `press("0")` → `"auto"`. Screenshot `/tmp/towncode-3d-watch-labels.png`.

- [ ] **Step 7: Verify**

Run: `node --test web/live.test.mjs`, `.venv/bin/python -m unittest test_webserve test_webserve_live -v`
Expected: PASS (the CSP still matches: the import map is unchanged).
Run: `python3 smoke_web.py --watch`
Expected: passes; the labels screenshot shows the Clawd's label and the status bar.

- [ ] **Step 8: Commit**

```bash
git add web/town3d.js web/look.js web/index.html web/town3d.css smoke_web.py
git commit -m "Label the Clawds, show watch's status lines, and follow the activity with the camera"
```

---

### Task 8: Merges, reconnecting, the error cases, performance, and the README

Spec: Build order step 4; "What you see" Merges; "Errors"; "Performance"; README.

**Files:**
- Modify: `web/town3d.js`, `web/look.js`, `smoke_web.py`, `README.md`
- Create: `scripts/benchmark_watch_browser.py`, `test_benchmark_watch_browser.py`

**Interfaces:**
- Consumes: Task 3's `town` message and rebuilt `/town.json`; Task 5's `newBuildings`,
  `dropLift`; Task 6's `view.townGroup`.
- Produces (`look.js`): `DROP = { height_px: 48, time: 0.42 }`.
- Produces: `scripts/benchmark_watch_browser.py [REPO] [--seconds N]` prints
  `town.json: N bytes; simulation: P% of one core over S s (C Clawds)` and exits 1 if
  `town.json` ≥ 1 MB or the share ≥ 5%.

- [ ] **Step 1: Rebuild on `town`** — on a `town` message, fetch `/town.json`; compute
`fresh = L.newBuildings(view.doc, doc)`; dispose every geometry and material in
`view.townGroup`, rebuild it with `build(doc)`, keep `view.liveGroup` and every Clawd object;
set `view.doc = doc`; for each fresh path, remember `view.drops.set(path, serverNow())`. While
a drop is active, the building's tier, window and roof instances are offset up by
`L.dropLift(now - start, LOOK.DROP, LOOK.PX_PER_UNIT)` (update those instance matrices each
frame; delete the drop once it lands). Clear a selection whose building no longer exists.
`town3d.report()` gains `version` (`view.doc.version`) and `dropping` (`view.drops.size`).

- [ ] **Step 2: Reconnecting** — `source.onerror` sets `#line2` to `reconnecting…` and
`town3d.live = false`; `EventSource` retries by itself; the next `state` replaces
`view.live` whole and `syncLive()` rebuilds the live layer (remove every Clawd object first).
If the `state`'s `version` differs from `view.doc.version`, refetch `/town.json` as for `town`.

- [ ] **Step 3: No WebGL** — when the renderer can't be made, keep the message, still
`connect()`, and keep updating `#line1`–`#line3` from the stream (the status lines as text).

- [ ] **Step 4: Write the benchmark** — `scripts/benchmark_watch_browser.py`:

```python
"""How much the live 3D server costs: /town.json's size and the simulation thread's CPU share.

    python3 scripts/benchmark_watch_browser.py [REPO] [--seconds N]

REPO is read only; its survey goes to a temporary folder. Without REPO it uses a small fixture
repository. Exits 1 if town.json is 1 MB or more, or the simulation thread uses
5% of one core or more.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

import fixture  # noqa: E402
import towncode  # noqa: E402

LIMIT_BYTES = 1_000_000
LIMIT_SHARE = 0.05


def measure(repo, seconds):
    args = argparse.Namespace(path=repo, browser=True, events=False, port=0, no_open=True)
    survey_dir = tempfile.mkdtemp(prefix="towncode-bench-survey-")
    lw = towncode._watch_live(args, survey_dir=survey_dir)
    size = len(json.dumps(lw.site.town, separators=(",", ":")).encode("utf-8"))
    lw.poller.start()
    used = [0.0]

    def run():
        start, prev = time.monotonic(), 0.0
        cpu0 = time.thread_time()
        while time.monotonic() - start < seconds:
            time.sleep(0.1)
            now = time.monotonic() - start
            lw.sim.step_once(now - prev, now)
            prev = now
        used[0] = time.thread_time() - cpu0

    try:
        t = threading.Thread(target=run, name="Simulation")
        t.start()
        t.join()
    finally:
        lw.poller.close_event.set()
        lw.poller.join(timeout=2)
        lw.watch.close()
        shutil.rmtree(survey_dir, ignore_errors=True)
    return size, used[0] / seconds, len(lw.live.crowd.clawds())


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("repo", nargs="?")
    p.add_argument("--seconds", type=float, default=10.0)
    a = p.parse_args(argv)
    repo = a.repo or _fixture()
    try:
        size, share, clawds = measure(repo, a.seconds)
    finally:
        if not a.repo:
            shutil.rmtree(repo, ignore_errors=True)
    print(f"town.json: {size} bytes; simulation: {share:.1%} of one core over "
          f"{a.seconds:g} s ({clawds} Clawds)")
    return 0 if size < LIMIT_BYTES and share < LIMIT_SHARE else 1


def _fixture():
    root = tempfile.mkdtemp(prefix="towncode-bench-repo-")
    subprocess.run(["git", "init", "-q", "-b", "main", root], check=True, capture_output=True)
    fixture.write(root, {"app/main.py": "x = 1\n", "core/base.py": "y = 2\n"})
    fixture.git(root, "add", "-A")
    fixture.git(root, "commit", "-q", "-m", "bench")
    return root


if __name__ == "__main__":
    sys.exit(main())
```

The share is the simulation work only (`thread_time` of the stepping thread); the poller's git
calls are watch's cost, already budgeted by watch phase 2. `test_benchmark_watch_browser.py`
runs `main(["--seconds", "1"])` on the fixture and asserts it returns 0 and prints the line.

- [ ] **Step 5: README** — under the 3D section, add:

```
python3 towncode.py watch PATH --browser [--port N] [--no-open]
```

"…watches PATH's agents in the 3D town: each agent is a Clawd walking to the file it's editing,
with scaffolding on edited buildings, orange sites for new files, flags for finished tasks, and
the town rebuilt after a merge. The camera follows the newest activity; `1`–`9` follow one
Clawd, `0` goes back to automatic, and moving the camera yourself pauses it. It serves this
machine only and never changes the repository." Keep the existing `view --browser` text.

- [ ] **Step 6: Extend the smoke check** — `smoke_web.py --watch` ends by committing the
worktree change, merging `team/world/demo` into the smoke repo's `main` (`git merge --no-ff`),
and waiting until `report().version === 2` (60 s) and the line-2 status starts with `merged`.
Then it kills the server, waits 2 s, restarts it on the same port and checks the page reconnects
(`report().live === true` within 30 s). Screenshot `/tmp/towncode-3d-watch-merged.png`.

- [ ] **Step 7: Verify**

Run: `.venv/bin/python -m unittest` and `python3 -m unittest`
Expected: OK.
Run: `python3 scripts/benchmark_watch_browser.py` and
`.venv/bin/python scripts/benchmark_watch_browser.py ~/game-web --seconds 20`
Expected: both exit 0; record the numbers in the ledger.
Run: `python3 smoke_web.py` and `python3 smoke_web.py --watch`
Expected: pass; report `town3d.report().fps` from the last run in the ledger.

- [ ] **Step 8: Commit**

```bash
git add web/town3d.js web/look.js smoke_web.py README.md scripts/benchmark_watch_browser.py test_benchmark_watch_browser.py
git commit -m "Rebuild the 3D town after a merge, reconnect after a drop, and check the live server's cost"
```

---

## Self-review against the spec

- Build order 2 (LiveTown, auto_agent): Task 1. 3 (simulation thread, `/events`, diffs): Tasks
  2–4; (Clawds, poses, scaffolding, sites, flags): Task 6; (labels, status, camera, keys):
  Task 7. 4 (`town` and rebuilding, dropping buildings, reconnecting, error cases, smoke,
  performance): Task 8.
- Errors: port in use (existing `make_server`, now also reached by `watch --browser`), survey
  fails at start (`_watch_town` raises before any server, Task 4), re-survey fails (line 1 via
  `LiveTown.lines`, Task 1), stream drops (Task 8), no WebGL (Task 8), no browser (existing
  `serve`).
- Safety: `/events` goes through the Host check and carries the CSP (Task 3); the static table
  gains only `live.js`; `live.test.mjs` is not served (Task 3 test).
- Testing: Diffs (Task 2), SSE framing and Server (Task 3), LiveTown (Task 1), end-to-end
  (Task 4), browser logic (Task 5), smoke (Tasks 6–8), performance (Task 8).
