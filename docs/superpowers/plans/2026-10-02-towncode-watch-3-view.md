# Towncode watch Phase 3 (the watch view) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Phase 3 placeholder with a live terminal view: Clawds walk the town while agents work, scaffolding and sites show unmerged changes, the camera auto-follows or locks to follow keys, merges re-survey `main`, and `towncode snapshot --watch` captures one frame.

**Architecture:** Phase 2's `Watch` produces `(events, WatchState)` on a worker thread; the UI thread drains snapshots through `WatchViewer.ingest()` and never calls `poll()`. Pure simulation lives in `crowd.py`. Drawing extensions live in `drawtown.py` and `watch_sites.py`. Status lines and label assembly live in `watch_ui.py`. Merge re-survey runs through an injectable `resurvey_runner` (thread in production, synchronous in tests).

**Tech Stack:** Python 3.14 standard library only. Tests: `.venv/bin/python -m unittest` from repo root. Branch: `towncode-watch-3` on `towncode-watch-2`.

**Spec:** `docs/superpowers/specs/2026-10-01-towncode-watch-design.md` (Phase 3). Camera, labels, frame rate, Clawd start tile: `docs/superpowers/specs/2026-10-01-codetown-point-and-click-design.md` §1, §2, §3, §7.

## Global Constraints

- Standard library only; no new dependencies.
- Read-only toward repo and worktrees: watch writes only `watch.json` in the survey folder; never writes in repo/worktrees; never shows file contents; never runs code; git read only (`repo.GIT_FLAGS`, `GIT_OPTIONAL_LOCKS=0`).
- Do not edit `focus.py`, `cake.py`, `roles.py`, `mock_roles.py`, `session.py`.
- Tests use `test_watch.temp_survey`, `test_watch.temp_wts`, `watch.FakeClock`; never `time.sleep`.
- Frame rate (v3 §7): 24 FPS moving, 12 FPS still, 12 FPS after frame > 35 ms (`viewer.FRAME_BUDGET = 0.035`).
- Walking: `game.STEP_TIME` (0.16 s/tile), paths from `roads.route`; Clawd goals are `standing_spot()` tiles, not building centres.
- Crowd time: `Crowd.apply(..., now)` sets `_now`; `Crowd.step(dt)` advances `_now += dt`; hammer/idle/peer/tour/hop read `_now`.
- Watch drawing: `TownScene.set_watch(layer, zoom)` then `render()` depth-sorts watch drawables with buildings (not a post-`render()` overlay).
- Camera: `camera.EASE = 6.5`.
- Follow keys `1`–`9`; orchestrator gets no number; `0` = auto.
- Principle 8: Clawd only goes where its agent was seen, except labelled reviewer tour.
- `labels.place` keeps request order: Clawd labels, Town Hall, scaffolded names (≤8, nearest camera, street zoom).

## File Structure

| File | Responsibility |
| --- | --- |
| `watch.py` | Adjusted `PALETTE`, `RESERVED`, `rgb_distance`, idempotent `close()`, `note_resurvey()` |
| `crowd.py` | Clawd simulation, standing spots, provisional scaffold, `CameraDirector`, `town_hall_tile` |
| `watch_sites.py` | Site yard layout (Task 2; from `mock_roles.construction`, no Pillow import) |
| `drawtown.py` | Watch drawables, drop easing, town markers |
| `watch_ui.py` | Status lines and label assembly |
| `viewer.py` | `WatchSnapshot`, `WatchPoller`, `WatchViewer`, `run_watch`, resurvey hooks |
| `towncode.py` | `watch PATH [--zoom]`, `snapshot OUT --watch` |
| `scripts/benchmark_watch_frame.py` | Median frame time benchmark (not unit suite) |
| `test_watch_colours.py` | Palette distance |
| `test_crowd.py` | Every spec crowd behaviour |
| `test_watch_camera.py` | CameraDirector |
| `test_watch_draw.py` | Drawing pixel/depth tests |
| `test_watch_ui.py` | Verbatim status/label strings |
| `test_watch_viewer.py` | ingest/tick, poll isolation, moving() |
| `test_watch_merge.py` | Re-survey |
| `test_watch_e2e_view.py` | View end-state + fingerprint |
| `test_towncode.py`, `test_watch_e2e.py` | CLI updates |

---

### Task 1: Team colours and reserved-distance test

**Files:**
- Modify: `watch.py` (`PALETTE`, `import math`, `RESERVED`, `rgb_distance`, `min_palette_distance`)
- Create: `test_watch_colours.py`

**Interfaces:**
- Produces: `watch.RESERVED`, `watch.rgb_distance(a,b)`, `watch.min_palette_distance()`, `watch.min_palette_pairwise_distance()`, `PALETTE` verified ≥80 from reserved (min 80.7) and ≥60 pairwise (min 60.0)

- [ ] **Step 1: Write the failing test**

Create `test_watch_colours.py`:

```python
import os
import shutil
import tempfile
import unittest

import watch


class WatchColoursTest(unittest.TestCase):
    def test_every_scarf_colour_is_far_from_reserved_colours(self):
        self.assertGreaterEqual(watch.min_palette_distance(), 80)

    def test_rgb_distance_is_euclidean(self):
        self.assertAlmostEqual(watch.rgb_distance((0, 0, 0), (3, 4, 0)), 5.0)

    def test_palette_colours_are_distinct_from_each_other(self):
        self.assertGreaterEqual(watch.min_palette_pairwise_distance(), 60)

    def test_team_keeps_colour_across_sessions(self):
        survey = tempfile.mkdtemp(prefix="watch-colours-")
        self.addCleanup(shutil.rmtree, survey)
        teams, last_used = {}, {}
        idx = watch.assign_colour("world", teams, last_used, 1.0)
        watch.save_colours_if_changed(survey, teams, last_used, {})
        self.assertEqual(watch.load_colours(survey)[0]["world"], idx)
        self.assertTrue(os.path.isfile(os.path.join(survey, "watch.json")))

    def test_reserved_copies_match_mock_roles_when_available(self):
        try:
            import mock_roles
            import focus as focus_mod
        except ImportError:
            raise unittest.SkipTest("mock_roles not importable")
        self.assertEqual(watch.RESERVED["uses"], mock_roles.ROAD_COLORS[focus_mod.USES])
        self.assertEqual(watch.RESERVED["site"], mock_roles.SITE)
        self.assertEqual(watch.RESERVED["reviewer_grey"], mock_roles.GRAY)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m unittest test_watch_colours -v`
Expected: FAIL — `min_palette_distance` missing or min distance < 80

- [ ] **Step 3: Write minimal implementation**

In `watch.py`:

```python
import math

import labels

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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m unittest test_watch_colours -v`
Expected: PASS (8 tests)

- [ ] **Step 5: Commit**

```bash
git add watch.py test_watch_colours.py
git commit -m "$(cat <<'EOF'
fix(watch): adjust team palette and add reserved-colour distance test.

EOF
)"
```

---

### Task 2: Crowd simulation (`crowd.py`)

Pure model: clock-injected, no drawing, no git, no threads.

**Files:**
- Create: `watch_sites.py` (yard layout — consumed by crowd create routing; Task 4 reuses)
- Create: `crowd.py`
- Create: `test_crowd.py`

**Interfaces:**
- Consumes: `events.Agent`, `events.Event`, `watch.WatchState`, `watch.map_path`, `watch.nearest_building`, `game.STEP_TIME`, `roads.route`, `townmap.TownMap`, `townmap.Building`
- Produces: `Crowd.retown(tmap, roads, model, tracked, town_hall)`, `_tour_tile(mod)`, plus Step 3 public API

- [ ] **Step 1: Write the failing test**

Create `test_crowd.py` (one test per spec table row plus walking/standing/principle-8/mid-build/follow tests):

```python
import unittest

import crowd
import game
import watch_sites
import roads
import watch
from events import Agent, Event
from test_townmap import build as build_town


def _stand(tmap, module, occupied=frozenset()):
    b = tmap.buildings[module]
    return crowd.standing_spot(tmap, b, set(occupied))


def _agent(n="w1", team="world", role="implementer", task=1):
    return Agent(f"{n}/task-{task}", role, team, n)


class CrowdTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.model, cls.rows, cls.found, cls.tmap = build_town()
        cls.roads = roads.Roads(cls.tmap, cls.model, cls.found)
        cls.tracked = set(cls.model.modules)
        cls.hall = crowd.town_hall_tile(cls.tmap)

    def _crowd(self, t=0.0):
        c = crowd.Crowd(self.tmap, self.roads, self.model, self.tracked, self.hall,
                        watch.FakeClock(t))
        return c

    def _apply(self, c, events, state=None, colours=None, now=0.0):
        c.apply(events, state or watch.WatchState(), colours or {"world": 0}, now)

    def test_town_hall_on_frontmost_avenue_near_centre(self):
        tx, ty = self.hall
        self.assertEqual(self.tmap.kind(tx, ty), "avenue")
        front_y = max(y for y in range(self.tmap.height)
                      if any(self.tmap.kind(x, y) == "avenue" and self.tmap.walkable(x, y)
                             for x in range(self.tmap.width)))
        self.assertEqual(ty, front_y)

    def test_start_routes_to_town_hall_and_waits(self):
        c = self._crowd()
        self._apply(c, [Event("start", _agent(), None, 0.0)])
        while c.clawds()[0].pose == "walk":
            c.step(0.05)
        self.assertEqual(c.clawds()[0].tile, self.hall)
        self.assertTrue(c.clawds()[0].at_hall)

    def test_edit_scaffolds_every_touched_building_clawd_to_most_recent(self):
        c = self._crowd()
        a = _agent()
        self._apply(c, [
            Event("edit", a, "app/main.py", 0.0),
            Event("edit", a, "core/notes.py", 1.0),
        ])
        sc = c.effective_scaffold(watch.WatchState())
        self.assertEqual(sc["app/main.py"], "world")
        self.assertEqual(sc["core/notes.py"], "world")
        self.assertEqual(c.clawds()[0].path[-1], _stand(self.tmap, "core/notes.py"))

    def test_create_walks_to_site(self):
        c = self._crowd()
        st = watch.WatchState(sites=["app/new.py"])
        self._apply(c, [Event("create", _agent(), "app/new.py", 0.0)], st)
        sites = watch_sites.layout_sites(self.tmap, c.effective_sites(st))
        lot = sites["app/new.py"]
        self.assertEqual(c.clawds()[0].path[-1], (lot[0], lot[1]))

    def test_delete_scaffolds_like_edit(self):
        c = self._crowd()
        self._apply(c, [Event("delete", _agent(), "app/main.py", 0.0)])
        self.assertIn("app/main.py", c.effective_scaffold(watch.WatchState()))

    def test_commit_hammer_pose(self):
        c = self._crowd()
        self._apply(c, [Event("commit", _agent(), None, 0.0)], now=0.0)
        self.assertEqual(c.clawds()[0].pose, "hammer")
        c.step(0.1)   # _now == 0.1 < HAMMER_TIME
        self.assertEqual(c.clawds()[0].pose, "hammer")
        c.step(0.5)   # _now == 0.6 >= HAMMER_TIME
        self.assertNotEqual(c.clawds()[0].pose, "hammer")

    def test_idle_after_20_seconds(self):
        c = self._crowd(100.0)
        self._apply(c, [Event("edit", _agent(), "app/main.py", 0.0)], now=0.0)
        while c.clawds()[0].pose == "walk":
            c.step(0.05)
        c.step(20.0)
        self.assertEqual(c.clawds()[0].pose, "idle")

    def test_finish_flag_then_town_hall(self):
        c = self._crowd()
        st = watch.WatchState(flags={"w1": "app/main.py"})
        self._apply(c, [Event("finish", _agent(), None, 0.0)], st)
        self.assertEqual(c.clawds()[0].flag_building, "app/main.py")
        while c.clawds()[0].pose == "walk":
            c.step(0.05)
        self.assertEqual(c.clawds()[0].tile, self.hall)

    def test_fix_after_finish_clears_flag(self):
        c = self._crowd()
        st = watch.WatchState(flags={"w1": "app/main.py"})
        self._apply(c, [Event("finish", _agent(), None, 0.0)], st)
        self._apply(c, [Event("edit", _agent(), "app/main.py", 1.0)], st, now=1.0)
        self.assertIsNone(c.clawds()[0].flag_building)

    def test_merge_hops_15_8_4_then_leaves(self):
        c = self._crowd()
        a = _agent()
        self._apply(c, [Event("merge", a, None, 0.0)])
        for px in (15, 8, 4):
            c.step(HOP_TIME := 0.15)
            self.assertAlmostEqual(c.clawds()[0].hop_y, px, delta=1)
        while c.clawds():
            c.step(0.05)
        self.assertIn(a.id, c.departed())

    def test_review_start_tours_four_seconds_each(self):
        c = self._crowd()
        rev = Agent("w1/review-task-1", "reviewer", "world", "w1")
        st = watch.WatchState(reviewer_tours={rev.id: ["app/main.py", "core/notes.py"]})
        self._apply(c, [Event("review_start", rev, None, 0.0)], st)
        while c.clawds()[0].tile != self.hall:
            c.step(0.05)
        first = _stand(self.tmap, "app/main.py")
        c.step(4.0)
        self.assertEqual(c.clawds()[0].tile, first)

    def test_review_finish_leaves(self):
        c = self._crowd()
        rev = Agent("w1/review-task-1", "reviewer", "world", "w1")
        self._apply(c, [Event("review_finish", rev, None, 0.0)])
        while c.clawds():
            c.step(0.05)
        self.assertIn(rev.id, c.departed())

    def test_orchestrator_read_peers_three_seconds(self):
        c = self._crowd()
        orch = Agent("orchestrator", "orchestrator", None, None)
        self._apply(c, [Event("read", orch, "app/main.py", 0.0)])
        self.assertEqual(c.clawds()[0].pose, "peer")
        c.step(2.0)
        self.assertEqual(c.clawds()[0].pose, "peer")
        c.step(1.5)
        while c.clawds()[0].pose == "walk":
            c.step(0.05)
        self.assertEqual(c.clawds()[0].tile, self.hall)

    def test_orchestrator_second_read_extends_peer(self):
        c = self._crowd()
        orch = Agent("orchestrator", "orchestrator", None, None)
        self._apply(c, [Event("read", orch, "app/main.py", 0.0)])
        c.step(2.0)
        self._apply(c, [Event("read", orch, "core/notes.py", 2.0)], now=2.0)
        c.step(2.0)
        self.assertEqual(c.clawds()[0].pose, "peer")

    def test_leave_drops_provisional_scaffold_and_sites(self):
        c = self._crowd()
        a = _agent()
        self._apply(c, [Event("edit", a, "app/main.py", 0.0)])
        self.assertIn("app/main.py", c.effective_scaffold(watch.WatchState()))
        self._apply(c, [Event("leave", a, None, 1.0)], now=1.0)
        self.assertEqual([], c.clawds())
        self.assertNotIn("app/main.py", c.effective_scaffold(watch.WatchState()))

    def test_walk_advances_one_tile_per_step_time(self):
        c = self._crowd()
        self._apply(c, [Event("edit", _agent(), "app/main.py", 0.0)])
        start = c.clawds()[0].tile
        c.step(game.STEP_TIME * 0.5)
        self.assertEqual(c.clawds()[0].tile, start)
        c.step(game.STEP_TIME * 0.6)
        self.assertNotEqual(c.clawds()[0].tile, start)

    def test_new_target_replaces_path_from_next_tile(self):
        c = self._crowd()
        a = _agent()
        self._apply(c, [Event("edit", a, "app/main.py", 0.0)])
        c.step(game.STEP_TIME * 0.5)
        self._apply(c, [Event("edit", a, "core/notes.py", 1.0)], now=1.0)
        self.assertEqual(c.clawds()[0].path[-1], _stand(self.tmap, "core/notes.py"))

    def test_standing_spots_not_shared(self):
        b = self.tmap.buildings["app/main.py"]
        occ = set()
        s1 = crowd.standing_spot(self.tmap, b, occ)
        occ.add(s1)
        s2 = crowd.standing_spot(self.tmap, b, occ)
        self.assertNotEqual(s1, s2)

    def test_no_building_file_nearest_no_scaffold(self):
        c = self._crowd()
        self._apply(c, [Event("edit", _agent(), "web/extra/data.json", 0.0)])
        sc = c.effective_scaffold(watch.WatchState())
        self.assertEqual(sc, {})
        nb = watch.nearest_building("web/extra/data.json", self.model)
        self.assertEqual(c.clawds()[0].path[-1], _stand(self.tmap, nb))

    def test_principle_8_all_targets_justified(self):
        c = self._crowd()
        rev = Agent("w1/review-task-1", "reviewer", "world", "w1")
        st = watch.WatchState(reviewer_tours={rev.id: ["app/main.py"]})
        events = [
            Event("start", _agent("w1"), None, 0.0),
            Event("edit", _agent("w1"), "app/main.py", 1.0),
            Event("review_start", rev, None, 2.0),
            Event("read", Agent("orchestrator", "orchestrator", None, None), "core/notes.py", 3.0),
        ]
        for i, ev in enumerate(events):
            self._apply(c, [ev], st, now=float(i))
            for _ in range(40):
                c.step(0.05)
        allowed = c.allowed_targets(events, st)
        for agent_id, tile, reason in c.target_log:
            self.assertIn((tile, reason), allowed[agent_id])

    def test_mid_build_seed_without_replay(self):
        c = self._crowd()
        st = watch.WatchState(
            agents=[watch.AgentState(_agent(), "working", "app/main.py")],
            flags={"w1": "core/notes.py"},
            reviewer_tours={"w1/review-task-1": ["app/main.py"]},
        )
        c.seed(st, {"world": 0})
        impl = next(x for x in c.clawds() if x.role == "implementer")
        self.assertEqual(impl.path[-1] if impl.path else impl.tile,
                         _stand(self.tmap, "app/main.py"))

    def test_follow_numbers_lowest_free_reused(self):
        c = self._crowd()
        agents = [_agent(f"w{i}", f"t{i}") for i in range(10)]
        for i, a in enumerate(agents[:9]):
            self._apply(c, [Event("start", a, None, float(i))], colours={a.team: i}, now=float(i))
        slots = {x.follow for x in c.clawds()}
        self.assertEqual(slots, set(range(1, 10)))
        self._apply(c, [Event("start", agents[9], None, 9.0)], now=9.0)
        self.assertIsNone(next(x for x in c.clawds() if x.agent_id == agents[9].id).follow)
        self._apply(c, [Event("merge", agents[0], None, 10.0)], now=10.0)
        while agents[0].id in {x.agent_id for x in c.clawds()}:
            c.step(0.05)
        self._apply(c, [Event("start", agents[9], None, 11.0)], now=11.0)
        self.assertEqual(next(x for x in c.clawds() if x.agent_id == agents[9].id).follow, 1)


    def test_retown_keeps_walking_clawd_goal(self):
        c = self._crowd()
        self._apply(c, [Event("edit", _agent(), "app/main.py", 0.0)])
        clawd = c.clawds()[0]
        goal_before = clawd.path[-1]
        c.step(game.STEP_TIME * 0.5)
        c.retown(self.tmap, self.roads, self.model, self.tracked, self.hall)
        self.assertEqual(c.clawds()[0].path[-1], _stand(self.tmap, "app/main.py"))

    def test_retown_merge_implementer_still_hops_and_leaves(self):
        c = self._crowd()
        a = _agent()
        self._apply(c, [Event("merge", a, None, 0.0)])
        c.retown(self.tmap, self.roads, self.model, self.tracked, self.hall)
        for _ in range(3):
            c.step(HOP_TIME := 0.15)
        while c.clawds():
            c.step(0.05)
        self.assertIn(a.id, c.departed())

    def test_retown_site_goal_becomes_building_standing_spot(self):
        c = self._crowd()
        st = watch.WatchState(sites=["app/new.py"])
        self._apply(c, [Event("create", _agent(), "app/new.py", 0.0)], st)
        clawd = c.clawds()[0]
        clawd.goal_module = "app/new.py"
        clawd.goal_kind = "site"
        model2, rows2, found2, tmap2 = build_town()
        tmap2.buildings["app/new.py"] = tmap2.buildings["app/helper.py"]
        c.retown(tmap2, roads.Roads(tmap2, model2, found2), model2,
                 self.tracked | {"app/new.py"}, crowd.town_hall_tile(tmap2))
        self.assertEqual(c.clawds()[0].path[-1], _stand(tmap2, "app/new.py"))

    def test_mid_build_orchestrator_at_hall(self):
        c = self._crowd()
        st = watch.WatchState(
            agents=[watch.AgentState(Agent("orch", "orchestrator", None, None), "idle", None)])
        c.seed(st, {})
        orch = next(x for x in c.clawds() if x.role == "orchestrator")
        self.assertEqual(orch.tile, self.hall)
        self.assertTrue(orch.at_hall)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m unittest test_crowd -v`
Expected: FAIL — `No module named 'crowd'`

- [ ] **Step 3: Write minimal implementation**

Create `watch_sites.py` first (same file as Task 4 — crowd create routing needs it):

```python
"""Construction site yards along the front of the town (from mock_roles.construction)."""

SITE_COLUMNS = 6


def _top_folder(path):
    return path.split("/")[0] + "/" if "/" in path else path


def layout_sites(tmap, site_paths):
    lots = {m: (b.x, b.y, b.size) for m, b in tmap.buildings.items()}
    if not site_paths:
        return {}
    folders = {}
    for p in site_paths:
        folders.setdefault(_top_folder(p), []).append(p)
    top = max(y + s for _, y, s in lots.values()) + 1
    width = tmap.width - 2
    sites, x, y, deepest = {}, 0, top, 0
    for members in folders.values():
        cols = min(SITE_COLUMNS, len(members))
        if x and x + cols > width:
            x, y = 0, y + deepest + 1
        for i, p in enumerate(sorted(members)):
            sites[p] = (x + i % cols, y + i // cols, 1)
        deepest = max(deepest, -(-len(members) // cols))
        x += cols + 1
    return sites
```

Create `crowd.py` (complete file):

```python
"""Clawd crowd simulation for towncode watch (pure, no I/O, no drawing)."""

from __future__ import annotations

from dataclasses import dataclass, field

import game
import roads as R
import watch
from events import Agent, Event
from townmap import Building, TownMap

IDLE_AFTER = 20.0
HAMMER_TIME = 0.5
PEER_TIME = 3.0
TOUR_STAY = 4.0
HOP_HEIGHTS = (15, 8, 4)
HOP_TIME = 0.15
MIN_STAY = 4.0

EVENT_PRIORITY = {
    "edit": 0, "create": 0, "delete": 0, "commit": 0, "merge": 0,
    "finish": 1,
    "read": 2, "start": 2, "review_start": 2,
}


def town_hall_tile(tmap: TownMap) -> tuple[int, int]:
    front_y = max(y for y in range(tmap.height)
                  if any(tmap.kind(x, y) == "avenue" and tmap.walkable(x, y)
                         for x in range(tmap.width)))
    cx = tmap.width // 2
    cands = [(x, front_y) for x in range(tmap.width) if tmap.walkable(x, front_y)]
    return min(cands, key=lambda t: (abs(t[0] - cx), t[1], t[0]))


def standing_spot(tmap: TownMap, building: Building,
                  occupied: set[tuple[int, int]]) -> tuple[int, int]:
    door = building.door()
    order = [building.front()]
    for dist in range(1, tmap.width + tmap.height):
        ring = []
        for dx in range(-dist, dist + 1):
            for dy in (-dist, dist):
                ring.append((door[0] + dx, door[1] + dy))
            for dy in range(-dist + 1, dist):
                ring.append((door[0] + dist, door[1] + dy))
                ring.append((door[0] - dist, door[1] + dy))
        for tile in ring:
            if tmap.walkable(*tile) and tile not in order:
                order.append(tile)
    order.sort(key=lambda t: (abs(t[0] - door[0]) + abs(t[1] - door[1]), t[1], t[0]))
    for tile in order:
        if tile not in occupied:
            return tile
    return order[0]


@dataclass
class CrowdClawd:
    agent_id: str
    role: str
    team: str | None
    colour: int
    worktree: str | None
    tile: tuple[int, int]
    facing: tuple[int, int] = (0, 1)
    pose: str = "idle"
    walk_t: float = 1.0
    walk_frame: int = 0
    path: tuple[tuple[int, int], ...] = ()
    path_i: int = 0
    follow: int | None = None
    flag_building: str | None = None
    hop_y: float = 0.0
    hop_i: int = 0
    hop_phase: float = 0.0
    idle_phase: float = 0.0
    last_event: float = 0.0
    hammer_until: float = 0.0
    peer_until: float = 0.0
    tour: tuple[str, ...] = ()
    tour_i: int = 0
    tour_until: float = 0.0
    at_hall: bool = False
    leaving: bool = False
    goal_module: str | None = None
    goal_kind: str | None = None


class Crowd:
    def __init__(self, tmap, roads, model, tracked, town_hall, clock):
        self.tmap = tmap
        self.roads = roads
        self.model = model
        self.tracked = tracked
        self.town_hall = town_hall
        self.clock = clock
        self._clawds: dict[str, CrowdClawd] = {}
        self._departed: set[str] = set()
        self._provisional: dict[str, str] = {}
        self._slots: dict[int, str] = {}
        self._free: list[int] = []
        self._standing: set[tuple[int, int]] = set()
        self.target_log: list[tuple[str, tuple[int, int], str]] = []
        self._site_paths: set[str] = set()
        self._now = 0.0

    def clawds(self):
        return list(self._clawds.values())

    def departed(self):
        return set(self._departed)

    def _slot_for(self, agent_id, role):
        if role == "orchestrator":
            return None
        if agent_id in {v for v in self._slots.values()}:
            return next(k for k, v in self._slots.items() if v == agent_id)
        if self._free:
            n = self._free.pop(0)
        else:
            used = set(self._slots)
            free = [n for n in range(1, 10) if n not in used]
            if not free:
                return None
            n = min(free)
        self._slots[n] = agent_id
        return n

    def _free_slot(self, agent_id):
        for n, aid in list(self._slots.items()):
            if aid == agent_id:
                del self._slots[n]
                self._free.append(n)
                self._free.sort()
                return

    def _ensure(self, agent: Agent, colour_idx: int) -> CrowdClawd:
        if agent.id in self._clawds:
            return self._clawds[agent.id]
        c = CrowdClawd(agent.id, agent.role, agent.team, colour_idx, agent.worktree,
                       self.town_hall, follow=self._slot_for(agent.id, agent.role))
        self._clawds[agent.id] = c
        return c

    def _route(self, start, goal):
        path = R.route(self.tmap, start, goal)
        return path or (start, goal)

    def _goal_tile(self, path: str, state: watch.WatchState):
        kind, target = watch.map_path(path, self.model, [], self.tracked)
        if kind == "module":
            b = self.tmap.buildings[target]
            return self._stand_tile(b), target, kind
        if kind == "site":
            import watch_sites
            sites = watch_sites.layout_sites(self.tmap, [target])
            tx, ty, _ = sites[target]
            return (tx, ty), target, kind
        nb = watch.nearest_building(path, self.model)
        if nb:
            return self._stand_tile(self.tmap.buildings[nb]), nb, "nearest"
        return self.town_hall, path, "file"

    def _stand_tile(self, building: Building):
        tile = standing_spot(self.tmap, building, self._standing)
        return tile

    def _send(self, c: CrowdClawd, goal, reason: str, now: float, *, module: str | None = None):
        if c.pose == "walk" and c.walk_t < 1.0:
            start = c.path[c.path_i] if c.path_i < len(c.path) else c.tile
        else:
            start = c.tile
        c.path = self._route(start, goal)
        c.path_i = 0
        c.walk_t = 0.0
        c.pose = "walk"
        c.at_hall = goal == self.town_hall
        c.last_event = now
        c.goal_module = module
        c.goal_kind = reason
        self.target_log.append((c.agent_id, goal, reason))

    def _tour_tile(self, mod: str) -> tuple[int, int]:
        if mod not in self.tmap.buildings:
            return self.town_hall
        return standing_spot(self.tmap, self.tmap.buildings[mod], self._standing)

    def _nearest_walkable(self, tile: tuple[int, int]) -> tuple[int, int]:
        if self.tmap.walkable(*tile):
            return tile
        tx, ty = tile
        for dist in range(1, self.tmap.width + self.tmap.height):
            for dx in range(-dist, dist + 1):
                for dy in (-dist, dist):
                    t = (tx + dx, ty + dy)
                    if self.tmap.walkable(*t):
                        return t
        return self.town_hall

    def _retown_goal(self, c: CrowdClawd) -> tuple[int, int]:
        if c.goal_module:
            tile, _, kind = self._goal_tile(c.goal_module, watch.WatchState())
            return tile
        if c.path:
            return c.path[-1]
        return c.tile

    def retown(self, tmap, roads, model, tracked, town_hall):
        """Swap town map without resetting Clawds (re-survey)."""
        self.tmap = tmap
        self.roads = roads
        self.model = model
        self.tracked = tracked
        self.town_hall = town_hall
        self._standing.clear()
        for c in self._clawds.values():
            if not tmap.walkable(*c.tile):
                c.tile = self._nearest_walkable(c.tile)
            if c.at_hall:
                c.tile = town_hall
            if c.path or c.goal_module:
                goal = self._retown_goal(c)
                start = c.path[c.path_i] if c.pose == "walk" and c.path_i < len(c.path) else c.tile
                c.path = self._route(start, goal)
                c.path_i = 0
                c.walk_t = 0.0
                c.pose = "walk"

    def apply(self, events: list[Event], state: watch.WatchState,
              team_colours: dict[str, int], now: float):
        self._now = now
        for ev in sorted(events, key=lambda e: e.seen):
            if ev.agent is None:
                continue
            idx = team_colours.get(ev.agent.team or "", 0)
            c = self._ensure(ev.agent, idx)
            c.last_event = now
            if ev.kind == "leave":
                wt = ev.agent.worktree or ""
                self._provisional = {k: v for k, v in self._provisional.items() if v != ev.agent.team}
                self._site_paths = {p for p in self._site_paths
                                    if not p.startswith(wt + "/") and p.split("/")[0] != wt}
                self._free_slot(ev.agent.id)
                self._clawds.pop(ev.agent.id, None)
                self._departed.add(ev.agent.id)
                continue
            if ev.kind == "start":
                self._send(c, self.town_hall, "hall", now)
                c.at_hall = True
            elif ev.kind in ("edit", "delete"):
                if ev.path:
                    tile, mod, kind = self._goal_tile(ev.path, state)
                    if kind == "module":
                        self._provisional[mod] = ev.agent.team or ""
                    self._send(c, tile, kind, now, module=mod if kind in ("module", "site", "nearest") else None)
            elif ev.kind == "create" and ev.path:
                self._site_paths.add(ev.path)
                tile, mod, kind = self._goal_tile(ev.path, state)
                self._send(c, tile, "site", now, module=ev.path)
            elif ev.kind == "commit":
                c.pose = "hammer"
                c.hammer_until = now + HAMMER_TIME
            elif ev.kind == "finish":
                wt = ev.agent.worktree or ""
                fb = state.flags.get(wt)
                c.flag_building = fb
                self._send(c, self.town_hall, "hall", now)
            elif ev.kind == "merge":
                c.pose = "hop"
                c.hop_i = 0
                c.hop_y = HOP_HEIGHTS[0]
                c.hop_phase = 0.0
            elif ev.kind == "review_start":
                c.tour = tuple(state.reviewer_tours.get(ev.agent.id, ()))
                c.tour_i = 0
                c.tour_until = 0.0
                self._send(c, self.town_hall, "hall", now)
            elif ev.kind == "review_finish":
                self._send(c, self.town_hall, "hall", now)
                c.leaving = True
            elif ev.kind == "read" and ev.agent.role == "orchestrator" and ev.path:
                tile, _, _ = self._goal_tile(ev.path, state)
                self._send(c, tile, "read", now)
                c.pose = "peer"
                c.peer_until = now + PEER_TIME
            if ev.kind in ("edit", "create", "delete") and c.flag_building:
                c.flag_building = None

    def effective_scaffold(self, state: watch.WatchState) -> dict[str, str]:
        out = dict(state.scaffolded)
        for mod, team in self._provisional.items():
            out.setdefault(mod, team)
            if mod in state.scaffolded:
                out[mod] = state.scaffolded[mod]
        return out

    def effective_sites(self, state: watch.WatchState) -> list[str]:
        return sorted(set(state.sites) | self._site_paths)

    def seed(self, state: watch.WatchState, team_colours: dict[str, int]):
        self._clawds.clear()
        for astate in state.agents:
            a = astate.agent
            idx = team_colours.get(a.team or "", 0)
            c = self._ensure(a, idx)
            if a.role == "orchestrator" or astate.status == "waiting":
                c.tile = self.town_hall
                c.at_hall = True
            elif a.role == "reviewer" and a.id in state.reviewer_tours:
                c.tour = tuple(state.reviewer_tours[a.id])
                c.tour_i = 0
                if c.tour:
                    c.tile = self._tour_tile(c.tour[0])
            elif astate.latest_path:
                tile, _, _ = self._goal_tile(astate.latest_path, state)
                c.tile = tile
            if state.flags.get(a.worktree or ""):
                c.flag_building = state.flags[a.worktree]

    def step(self, dt: float) -> bool:
        self._now += dt
        moving = False
        self._standing.clear()
        now = self._now
        for c in list(self._clawds.values()):
            if c.pose == "hammer" and now >= c.hammer_until:
                c.pose = "idle"
            if c.pose == "peer" and now >= c.peer_until:
                self._send(c, self.town_hall, "hall", now)
            if c.pose == "hop":
                moving = True
                c.hop_y = float(HOP_HEIGHTS[min(c.hop_i, len(HOP_HEIGHTS) - 1)])
                c.hop_phase += dt
                if c.hop_phase >= HOP_TIME:
                    c.hop_phase = 0.0
                    c.hop_i += 1
                    if c.hop_i >= len(HOP_HEIGHTS):
                        c.pose = "leave"
                        c.leaving = True
                        c.hop_y = 0.0
            if c.leaving:
                goal = (c.tile[0], self.tmap.height)
                self._send(c, goal, "exit", now)
                c.leaving = False
            if c.tour and c.at_hall and not c.path:
                if c.tour_i < len(c.tour):
                    mod = c.tour[c.tour_i]
                    tile = self._tour_tile(mod)
                    self._send(c, tile, "tour", now, module=mod)
                    c.tour_until = now + TOUR_STAY
                    c.tour_i += 1
            if c.tour and c.tour_until and now >= c.tour_until and c.pose != "walk":
                if c.tour_i >= len(c.tour):
                    c.tour = ()
                else:
                    mod = c.tour[c.tour_i]
                    self._send(c, self._tour_tile(mod), "tour", now, module=mod)
                    c.tour_i += 1
                    c.tour_until = now + TOUR_STAY
            if c.pose == "walk" and c.path:
                c.walk_t += dt / game.STEP_TIME
                moving = True
                while c.walk_t >= 1.0 and c.path_i + 1 < len(c.path):
                    c.path_i += 1
                    c.tile = c.path[c.path_i]
                    c.walk_t -= 1.0
                    c.walk_frame = 1 + (c.walk_frame % 2)
                if c.path_i + 1 >= len(c.path) and c.walk_t >= 1.0:
                    c.pose = "idle"
                    c.walk_t = 1.0
            elif c.pose == "idle" and now - c.last_event >= IDLE_AFTER:
                c.pose = "idle"
                c.idle_phase += dt
                c.facing = (0, 1) if int(c.idle_phase) % 2 == 0 else (1, 0)
                moving = True
            if c.pose == "idle" and not c.path:
                self._standing.add(c.tile)
            if c.leaving and c.tile[1] >= self.tmap.height - 1:
                self._free_slot(c.agent_id)
                self._clawds.pop(c.agent_id, None)
                self._departed.add(c.agent_id)
        return moving

    def is_moving(self) -> bool:
        """Pure query: any timed pose or walk/hop/leave active at self._now."""
        now = self._now
        for c in self._clawds.values():
            if c.pose in ("walk", "hop") or c.leaving:
                return True
            if c.pose == "hammer" and now < c.hammer_until:
                return True
            if c.pose == "peer" and now < c.peer_until:
                return True
            if c.tour_until and now < c.tour_until:
                return True
        return False

    def allowed_targets(self, events, state):
        allowed = {}
        for ev in events:
            if not ev.agent:
                continue
            a = allowed.setdefault(ev.agent.id, set())
            a.add((self.town_hall, "hall"))
            if ev.path:
                tile, _, kind = self._goal_tile(ev.path, state)
                a.add((tile, kind))
            if ev.kind == "review_start":
                for mod in state.reviewer_tours.get(ev.agent.id, ()):
                    a.add((self._tour_tile(mod), "tour"))
        for c in self._clawds.values():
            allowed.setdefault(c.agent_id, set()).add(
                (c.tile, "exit") if c.leaving else (c.tile, "stand"))
        return allowed

    def sprite_cells(self):
        """Terminal cells occupied by Clawd bodies (for labels.place `taken`)."""
        import sprites
        cells = set()
        for c in self._clawds.values():
            rows = sprites.clawd_rows(c.facing, c.walk_frame)
            width = max(len(r) for r in rows)
            base_col = c.tile[0] * 2
            base_row = c.tile[1] - len(rows)
            for dy, row in enumerate(rows):
                for dx, ch in enumerate(row):
                    if ch != ".":
                        cells.add((base_col + dx, base_row + dy))
        return cells
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m unittest test_crowd -v`
Expected: PASS (26 tests)

- [ ] **Step 5: Commit**

```bash
git add crowd.py test_crowd.py
git commit -m "$(cat <<'EOF'
feat(watch): add crowd simulation covering every Clawd behaviour in the spec.

EOF
)"
```

---

### Task 3: Camera director (`CameraDirector` in `crowd.py`)

**Files:**
- Modify: `crowd.py` (append `clawd_focus_px`, `CameraDirector`)
- Create: `test_watch_camera.py`

**Interfaces:**
- Produces:
  - `crowd.clawd_focus_px(tmap, clawd) -> tuple[float, float]`
  - `crowd.CameraDirector(camera, crowd, tmap)` with `press`, `apply_events`, `step`, `follow_labels`, `mode`, `follow_slot`

- [ ] **Step 1: Write the failing test**

Create `test_watch_camera.py`:

```python
import unittest

import camera
import crowd
import roads
import watch
from events import Agent, Event
from test_townmap import build as build_town


class WatchCameraTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.model, cls.rows, cls.found, cls.tmap = build_town()
        cls.roads = roads.Roads(cls.tmap, cls.model, cls.found)
        cls.hall = crowd.town_hall_tile(cls.tmap)

    def _setup(self):
        cam = camera.Camera((0.0, 0.0))
        c = crowd.Crowd(self.tmap, self.roads, self.model, set(self.model.modules),
                        self.hall, watch.FakeClock())
        d = crowd.CameraDirector(cam, c, self.tmap)
        return cam, c, d

    def test_auto_waits_four_seconds(self):
        cam, c, d = self._setup()
        a1 = Agent("w1/task-1", "implementer", "world", "w1")
        a2 = Agent("w2/task-1", "implementer", "render", "w2")
        d.apply_events([Event("edit", a1, "app/main.py", 0.0)], 0.0)
        d.step(0.0, 0.0)
        first = list(cam.target)
        d.apply_events([Event("edit", a2, "core/notes.py", 0.5)], 0.5)
        d.step(0.0, 3.0)
        self.assertEqual(list(cam.target), first)
        d.step(0.0, 4.5)
        self.assertNotEqual(list(cam.target), first)

    def test_edit_beats_finish_after_stay(self):
        cam, c, d = self._setup()
        fin = Agent("w1/task-1", "implementer", "world", "w1")
        ed = Agent("w2/task-1", "implementer", "render", "w2")
        d.apply_events([Event("finish", fin, None, 0.0)], 0.0)
        d.step(0.0, 0.0)
        d.apply_events([Event("edit", ed, "app/main.py", 4.1)], 4.1)
        c.apply([Event("edit", ed, "app/main.py", 4.1)], watch.WatchState(), {"render": 1}, 4.1)
        d.step(0.0, 4.1)
        self.assertEqual(d._auto_agent, ed.id)

    def test_lower_priority_never_steals_inside_stay(self):
        cam, c, d = self._setup()
        ed = Agent("w1/task-1", "implementer", "world", "w1")
        fin = Agent("w2/task-1", "implementer", "render", "w2")
        d.apply_events([Event("edit", ed, "app/main.py", 0.0)], 0.0)
        d.step(0.0, 0.0)
        held = list(cam.target)
        d.apply_events([Event("finish", fin, None, 1.0)], 1.0)
        d.step(0.0, 1.0)
        self.assertEqual(list(cam.target), held)

    def test_follow_holds_until_zero_or_departure(self):
        cam, c, d = self._setup()
        agent = Agent("w1/task-1", "implementer", "world", "w1")
        c.apply([Event("start", agent, None, 0.0)], watch.WatchState(), {"world": 0}, 0.0)
        d.press("1")
        d.step(0.0, 0.0)
        held = list(cam.target)
        d.apply_events([Event("edit", Agent("w2/task-1", "implementer", "x", "w2"),
                              "hub/records.py", 10.0)], 10.0)
        d.step(0.0, 10.0)
        self.assertEqual(list(cam.target), held)
        d.press("0")
        self.assertEqual(d.mode, "auto")
        c.apply([Event("merge", agent, None, 11.0)], watch.WatchState(), {"world": 0}, 11.0)
        while c.clawds():
            c.step(0.05)
        d.step(0.0, 20.0)
        self.assertEqual(d.mode, "auto")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m unittest test_watch_camera -v`
Expected: FAIL — `CameraDirector` missing

- [ ] **Step 3: Write minimal implementation**

Append to `crowd.py`:

```python
import iso


def clawd_focus_px(tmap, clawd: CrowdClawd) -> tuple[float, float]:
    if clawd.path and clawd.walk_t < 1.0 and clawd.path_i + 1 < len(clawd.path):
        a = clawd.path[clawd.path_i]
        b = clawd.path[clawd.path_i + 1]
        t = clawd.walk_t
        fx, fy = a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t
    else:
        fx, fy = clawd.tile[0] + 0.5, clawd.tile[1] + 0.5
    sx, sy = iso.to_screen(fx, fy)
    return float(sx), float(sy) - clawd.hop_y


class CameraDirector:
    def __init__(self, camera, crowd: Crowd, tmap):
        self.camera = camera
        self.crowd = crowd
        self.tmap = tmap
        self.mode = "auto"
        self.follow_slot = None
        self._auto_agent = None
        self._auto_seen = 0.0
        self._stay_until = 0.0
        self._pending: list[tuple[int, float, str]] = []

    def press(self, key: str):
        if key == "0":
            self.mode = "auto"
            self.follow_slot = None
            return
        if len(key) == 1 and key.isdigit() and key != "0":
            self.mode = "follow"
            self.follow_slot = int(key)

    def apply_events(self, events: list[Event], now: float):
        for ev in events:
            if ev.agent is None:
                continue
            pr = EVENT_PRIORITY.get(ev.kind, 9)
            self._pending.append((pr, ev.seen, ev.agent.id))
        self._pending.sort()

    def follow_labels(self) -> dict[str, int]:
        out = {}
        for n, aid in self.crowd._slots.items():
            c = self.crowd._clawds.get(aid)
            if c and c.role != "orchestrator":
                out[aid] = n
        return out

    def step(self, dt: float, now: float):
        if self.mode == "follow" and self.follow_slot is not None:
            aid = self.crowd._slots.get(self.follow_slot)
            if aid is None or aid in self.crowd.departed():
                self.mode = "auto"
                self.follow_slot = None
            else:
                c = self.crowd._clawds[aid]
                self.camera.set_target(*clawd_focus_px(self.tmap, c))
                return
        if self._pending and now >= self._stay_until:
            pr, seen, agent_id = self._pending.pop(0)
            self._auto_agent = agent_id
            self._auto_seen = seen
            self._stay_until = now + MIN_STAY
        if self._auto_agent and self._auto_agent in self.crowd._clawds:
            c = self.crowd._clawds[self._auto_agent]
            self.camera.set_target(*clawd_focus_px(self.tmap, c))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m unittest test_watch_camera -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add crowd.py test_watch_camera.py
git commit -m "$(cat <<'EOF'
feat(watch): add camera director with 4s stay and follow keys.

EOF
)"
```

---

### Task 4: Site yards and watch drawing (`watch_sites.py`, `drawtown.py`)

**Files:**
- Modify: `drawtown.py` (`watch_sites.py` from Task 2) (append watch drawing after `draw_prop`)
- Create: `test_watch_draw.py`

**Interfaces:**
- Consumes: `townmap.TownMap`, `crowd.CrowdClawd`, `sprites.clawd_rows`, `sprites.parse`, `sprites.CLAWD`, `watch.PALETTE`, `watch.RESERVED`, `cake.half_width`, `cake.wall_columns`, `iso.to_screen`, `iso.HALF_H`, `render.shade`
- Produces:
  - `drawtown.DROP_HEIGHT = 48`, `drawtown.DROP_TIME = 0.42`, `drawtown.drop_offset(t) -> float`
  - `drawtown.SCAFFOLD`, `drawtown.SITE_ORANGE`, `drawtown.HAT`, `drawtown.LECTERN`
  - `@dataclass drawtown.WatchLayer`
  - `drawtown.clawd_palette`, `drawtown.clawd_extra_rows`, `drawtown.scarf_pixel_positions`, `drawtown.hat_pixel_positions`, `drawtown.clawd_marker_px`
  - `drawtown._tier_block(fb, sx, sy, half, z0, z1, c)` — copied from `mock_roles.tier` (no Pillow import)
  - `TownScene.set_watch(layer, zoom)` — attach watch layer before `render()`
  - `TownScene.render()` — depth-sorted pass interleaves watch drawables (scaffolding, Clawds, flags, lectern, sites, dropping buildings) with buildings

- [ ] **Step 1: Write the failing test**

Create `test_watch_draw.py`:

```python
import unittest

import crowd
import drawtown
import roads
import watch
import watch_sites
from events import Agent
from test_townmap import build as build_town


def _layer(tmap, clawds=(), scaffolded=None, sites=None, flags=None, drops=None):
    return drawtown.WatchLayer(
        scaffolded=scaffolded or {},
        team_colours={"world": 0},
        sites=sites or {},
        flags=flags or {},
        drops=drops or {},
        clawds=list(clawds),
        town_hall=crowd.town_hall_tile(tmap),
    )


class WatchDrawTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.model, cls.rows, cls.found, cls.tmap = build_town()
        cls.roads = roads.Roads(cls.tmap, cls.model, cls.found)

    def _scene(self):
        return drawtown.TownScene.whole(self.tmap, visible=self.roads.visible())

    def test_drop_offset_is_48_at_zero_and_zero_at_042(self):
        self.assertAlmostEqual(drawtown.drop_offset(0.0), 48.0)
        self.assertAlmostEqual(drawtown.drop_offset(0.42), 0.0, places=1)
        self.assertAlmostEqual(drawtown.drop_offset(1.0), 0.0)

    def test_scaffold_covers_building_pixel_in_depth_order(self):
        scene = self._scene()
        mod = "app/main.py"
        b = self.tmap.buildings[mod]
        fb_before = scene.render()
        tx, ty = b.x + b.size // 2, b.y + b.size // 2
        sx, sy = scene.screen(tx, ty)
        wall_colour = fb_before.get(sx, sy)
        layer = _layer(self.tmap, scaffolded={mod: "world"})
        scene.set_watch(layer, "street")
        fb = scene.render()
        self.assertNotEqual(wall_colour, drawtown.SCAFFOLD)
        self.assertEqual(fb.get(sx, sy), drawtown.SCAFFOLD)

    def test_three_clawds_scarf_grey_and_hat_colours(self):
        scene = self._scene()
        def _clawd(aid, role, team, tile, follow):
            return crowd.CrowdClawd(aid, role, team, 0, None, tile, (0, 1), "idle",
                                    1.0, 0, (), 0, follow, None, 0.0, 0, 0.0, 0.0, 0.0,
                                    0.0, 0.0, (), 0, 0.0, False, False)
        impl = _clawd("w/task-1", "implementer", "world", (10, 10), 1)
        rev = _clawd("w/rev", "reviewer", "world", (12, 10), 2)
        orch = _clawd("orch", "orchestrator", None, (14, 10), None)
        layer = _layer(self.tmap, clawds=[impl, rev, orch])
        scene.set_watch(layer, "street")
        fb = scene.render()
        for clawd, expected in ((impl, watch.PALETTE[0]), (rev, watch.RESERVED["reviewer_grey"])):
            for x, y in drawtown.scarf_pixel_positions(scene, clawd, layer.team_colours):
                self.assertEqual(fb.get(x, y), expected)
        for x, y in drawtown.hat_pixel_positions(scene, orch):
            self.assertEqual(fb.get(x, y), drawtown.HAT)

    def test_site_and_flag_use_team_or_orange(self):
        scene = self._scene()
        sites = watch_sites.layout_sites(self.tmap, ["app/new.py"])
        layer = _layer(self.tmap, sites=sites, flags={"w1": "app/main.py"})
        scene.set_watch(layer, "street")
        fb = scene.render()
        colours = {c for row in fb.rows for c in row}
        self.assertTrue(drawtown.SITE_ORANGE in colours or watch.PALETTE[0] in colours)

    def test_lectern_on_town_hall_tile(self):
        scene = self._scene()
        hall = crowd.town_hall_tile(self.tmap)
        layer = _layer(self.tmap)
        scene.set_watch(layer, "street")
        fb = scene.render()
        sx, sy = scene.screen(*hall)
        self.assertEqual(fb.get(sx, sy - 2), drawtown.LECTERN)

    def test_clawd_behind_building_is_partly_hidden(self):
        scene = self._scene()
        b = self.tmap.buildings["core/tower.py"]
        front = b.front()
        def _clawd(aid, tile):
            return crowd.CrowdClawd(aid, "implementer", "world", 0, None, tile, (0, 1), "idle",
                                    1.0, 0, (), 0, 1, None, 0.0, 0, 0.0, 0.0, 0.0,
                                    0.0, 0.0, (), 0, 0.0, False, False)
        behind = _clawd("behind", (front[0], front[1] - 1))
        layer = _layer(self.tmap, clawds=[behind])
        scene.set_watch(layer, "street")
        fb = scene.render()
        visible_scarf = sum(1 for x, y in drawtown.scarf_pixel_positions(scene, behind, layer.team_colours)
                            if fb.get(x, y) == watch.PALETTE[0])
        self.assertGreater(visible_scarf, 0)
        self.assertLess(visible_scarf, len(list(drawtown.scarf_pixel_positions(scene, behind, layer.team_colours))))

    def test_town_zoom_markers_are_three_pixels(self):
        scene = self._scene()
        c = crowd.CrowdClawd("w/t", "implementer", "world", 0, None, (5, 5), (0, 1), "idle",
                             1.0, 0, (), 0, 1, None, 0.0, 0, 0.0, 0.0, 0.0,
                             0.0, 0.0, (), 0, 0.0, False, False)
        layer = _layer(self.tmap, clawds=[c])
        scene.set_watch(layer, "town")
        fb = scene.render()
        px, py = drawtown.clawd_marker_px(scene, c)
        marker = {(px + dx, py + dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1)}
        self.assertEqual(len(marker), 9)
        for x, y in marker:
            if 0 <= x < fb.w and 0 <= y < fb.h:
                self.assertEqual(fb.get(x, y), watch.PALETTE[0])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m unittest test_watch_draw -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'watch_sites'`

- [ ] **Step 3: Write minimal implementation**

`watch_sites.py` already exists from Task 2.

Append to `drawtown.py`:

```python
import math
from dataclasses import dataclass

import cake
import crowd
import iso
import sprites
import watch

DROP_HEIGHT = 48
DROP_TIME = 0.42
SCAFFOLD = (150, 112, 74)
SITE_ORANGE = (232, 128, 48)
SITE_WIDTH = 0.7
SITE_HEIGHT = 3
HAT = (60, 60, 70)
LECTERN = (120, 90, 60)
GLASSES = (30, 26, 24)

# sprites.clawd_rows(facing, frame) = _CLAWD_BODY + _CLAWD_LEGS[frame]:
#   row 0 ".OOOOOOO."  row 1 ".OOOOOOO." (eyes on row 1 when facing south/east)
#   row 2 "OOOOOOOOO"  row 3 ".ooooooo."  <- scarf: recolour every 'o' here
#   then leg row(s) e.g. ".o.o.o.o."
_SCARF_ROW = 3
# Pointed hat rows appended above clawd_rows (relative to body, negative y in sprite space).
_HAT_ROWS = ["..PPP..", ".PPPPP."]
_HAT_PALETTE = {"P": HAT}


def drop_offset(t):
    """48 px at t=0, 0 at t>=0.42. Ease-out with slight overshoot (v3 intro building drop)."""
    if t <= 0:
        return float(DROP_HEIGHT)
    if t >= DROP_TIME:
        return 0.0
    u = t / DROP_TIME
    base = (1 - u) ** 2
    return DROP_HEIGHT * base * (1 + 0.12 * math.sin(u * math.pi))


@dataclass
class WatchLayer:
    scaffolded: dict
    team_colours: dict
    sites: dict
    flags: dict
    drops: dict
    clawds: list
    town_hall: tuple


def clawd_extra_rows(clawd):
    if clawd.role == "orchestrator":
        return list(_HAT_ROWS)
    return []


def clawd_palette(clawd, team_colours):
    base = dict(sprites.CLAWD)
    if clawd.role == "implementer":
        colour = watch.PALETTE[team_colours.get(clawd.team or "", clawd.colour)]
        return {**base, "o": colour}
    if clawd.role == "reviewer":
        return {**base, "o": watch.RESERVED["reviewer_grey"], "E": GLASSES}
    if clawd.role == "orchestrator":
        return {**base, ** _HAT_PALETTE}
    return base


def clawd_sprite_cells(clawd, ax, ay, rows):
    cells = set()
    y0 = ay - len(rows) + 1
    for y, row in enumerate(rows):
        for x, ch in enumerate(row):
            if ch == ".":
                continue
            px = ax - 4 + x
            py = y0 + y
            cells.add((px, py))  # terminal row; x handled in labels
    return cells


def clawd_marker_px(scene, clawd):
    sx, sy = scene.screen(clawd.tile[0] + 0.5, clawd.tile[1] + 0.5)
    return sx, sy


def _clawd_anchor(scene, clawd):
    fx, fy = iso.to_screen(clawd.tile[0] + 0.5, clawd.tile[1] + 0.5)
    ax = round(fx) + scene.ox
    ay = round(fy) + scene.oy + iso.HALF_H - int(clawd.hop_y)
    return ax, ay


def scarf_pixel_positions(scene, clawd, team_colours):
    ax, ay = _clawd_anchor(scene, clawd)
    rows = sprites.clawd_rows(clawd.facing, clawd.walk_frame)
    palette = clawd_palette(clawd, team_colours)
    y0 = ay - len(rows) + 1
    x0 = ax - 4
    out = []
    for x, y, c in sprites.parse(rows, palette):
        if rows[y].count("o") and c == palette.get("o"):
            out.append((x0 + x, y0 + y))
    return out


def hat_pixel_positions(scene, clawd):
    ax, ay = _clawd_anchor(scene, clawd)
    rows = clawd_extra_rows(clawd) + sprites.clawd_rows(clawd.facing, clawd.walk_frame)
    palette = clawd_palette(clawd, {})
    y0 = ay - len(rows) + 1
    x0 = ax - 4
    return [(x0 + x, y0 + y) for x, y, c in sprites.parse(rows, palette) if c == HAT]


def _draw_sprite(fb, ax, ay, rows, palette, ghost, y_offset=0):
    y0 = ay - len(rows) + 1 - y_offset
    x0 = ax - 4
    for x, y, c in sprites.parse(rows, palette):
        fb.set(x0 + x, y0 + y, c)
        ghost.append((x0 + x, y0 + y, c))


def _tier_block(fb, sx, sy, half, z0, z1, c):
    """One building tier block (copied from mock_roles.tier — no Pillow)."""
    from render import shade
    walls = {"left": shade(c, 0.95), "right": shade(c, 0.74)}
    for face, dx, t in cake.wall_columns(half):
        col = sx + dx
        for k in range(z0, z1):
            y = sy + t // 2 - k
            fb.set(col, y, shade(walls[face], 0.6) if k == z0 else walls[face])
        for y in range(sy - t // 2 - z1, sy + t // 2 - z1 + 1):
            fb.set(col, y, shade(c, 1.08))


def TownScene_set_watch(self, layer: WatchLayer, zoom: str):
    self._watch = layer
    self._watch_zoom = zoom


TownScene.set_watch = TownScene_set_watch


def _append_watch_drawables(scene, drawables):
    layer = scene._watch
    if layer is None:
        return
    zoom = scene._watch_zoom
    m = scene.m
    t = scene.t

    def add(depth_tx, depth_ty, layer_i, draw_fn):
        drawables.append((depth_tx + depth_ty, layer_i, depth_tx, draw_fn))

    for mod, team in layer.scaffolded.items():
        if mod not in m.buildings:
            continue
        b = m.buildings[mod]
        colour = watch.PALETTE[layer.team_colours.get(team, 0)]

        def draw_scaffold(b=b, colour=colour):
            for tx, ty in b.tiles():
                sx, sy = scene.screen(tx, ty)
                scene.fb.set(sx, sy, SCAFFOLD)
            for tx in range(b.x, b.x + b.size):
                sx, sy = scene.screen(tx, b.y + b.size)
                for dy in range(3):
                    scene.fb.set(sx, sy + dy, colour)

        add(b.x + b.size, b.y + b.size, 2, draw_scaffold)

    for path, (tx, ty, size) in layer.sites.items():
        def draw_site(tx=tx, ty=ty, path=path):
            sx, sy = scene.screen(tx + 0.5, ty + 0.5)
            _tier_block(scene.fb, round(sx), round(sy), cake.half_width(size, SITE_WIDTH),
                        0, SITE_HEIGHT, SITE_ORANGE)
        add(tx, ty, 2, draw_site)

    for wt, mod in layer.flags.items():
        if mod not in m.buildings:
            continue
        b = m.buildings[mod]
        colour = watch.PALETTE[layer.team_colours.get(wt, 0)]

        def draw_flag(b=b, colour=colour):
            fx, fy = scene.screen(b.x + b.size, b.y)
            for i in range(4):
                scene.fb.set(fx + i, fy - i, colour)

        add(b.x + b.size, b.y, 2, draw_flag)

    hx, hy = scene.screen(layer.town_hall[0] + 0.5, layer.town_hall[1] + 0.5)

    def draw_lectern():
        for dy in range(4):
            scene.fb.set(hx, hy - dy, LECTERN)

    add(layer.town_hall[0], layer.town_hall[1], 2, draw_lectern)

    for mod, start in layer.drops.items():
        if mod not in m.buildings:
            continue
        b = m.buildings[mod]
        off = int(drop_offset(t - start))

        def draw_drop(b=b, off=off):
            if off <= 0:
                return
            cx, cy = scene.centre_px(b)
            for dy in range(off):
                for dx in range(-2, 3):
                    scene.fb.set(cx + dx, cy - dy, scene.fb.get(cx, cy))

        add(b.x + b.size // 2, b.y + b.size // 2, 2, draw_drop)

    if zoom == "town":
        for c in layer.clawds:
            if c.role == "orchestrator":
                continue
            mx, my = clawd_marker_px(scene, c)
            col = watch.PALETTE[c.colour]

            def draw_marker(mx=mx, my=my, col=col):
                for dx in (-1, 0, 1):
                    for dy in (-1, 0, 1):
                        scene.fb.set(mx + dx, my + dy, col)

            add(c.tile[0], c.tile[1], 3, draw_marker)
        return

    for c in layer.clawds:
        def draw_clawd(c=c):
            ax, ay = _clawd_anchor(scene, c)
            rows = clawd_extra_rows(c) + sprites.clawd_rows(c.facing, c.walk_frame)
            _draw_sprite(scene.fb, ax, ay, rows, clawd_palette(c, layer.team_colours), scene.ghost)

        add(c.tile[0], c.tile[1], 2, draw_clawd)
```

Modify `TownScene.render` in `drawtown.py` (insert after the annex loop, before `drawables.sort`):

```python
        for b in m.buildings.values():
            if b.tested:
                tx, ty = b.x + b.size, b.y
                sx, sy = self.screen(tx, ty)
                if self.visible(sx, sy):
                    drawables.append((tx + ty, 1, tx, partial(self.draw_annex, sx, sy)))
        if getattr(self, "_watch", None):
            _append_watch_drawables(self, drawables)
        drawables.sort(key=lambda d: d[:3])
        for *_, draw in drawables:
            draw()
        self.draw_ghost()
        return self.fb
```

(Replace the existing `drawables.sort` … `return self.fb` tail of `render()` with the block above.)

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m unittest test_watch_draw -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add watch_sites.py drawtown.py test_watch_draw.py
git commit -m "$(cat <<'EOF'
feat(watch): draw scaffolding, sites, flags, lectern and Clawd variants.

EOF
)"
```

---

### Task 5: Status lines and labels (`watch_ui.py`)

**Files:**
- Create: `watch_ui.py`
- Create: `test_watch_ui.py`

**Interfaces:**
- Produces exact strings per spec; `line1(..., resurvey_error=None, mid_merge=False)`; `label_requests(...) -> list[LabelRequest]`

- [ ] **Step 1: Write the failing test**

Create `test_watch_ui.py` with exact-string tests:

```python
import unittest

import crowd
import labels
import roads
import watch
import watch_ui
from events import Agent, Event
from test_townmap import build as build_town


class WatchUiTest(unittest.TestCase):
    def test_line1_busy_exact(self):
        agents = [
            watch.AgentState(Agent("w1/t1", "implementer", "world", "w1"), "working", None),
            watch.AgentState(Agent("w2/t1", "implementer", "render", "w2"), "working", None),
            watch.AgentState(Agent("w3/t1", "implementer", "gameplay", "w3"), "working", None),
            watch.AgentState(Agent("w4/t1", "implementer", "gameplay", "w4"), "working", None),
            watch.AgentState(Agent("w5/t1", "implementer", "qa", "w5"), "working", None),
            watch.AgentState(Agent("w6/r", "reviewer", "review", "w6"), "touring", None),
            watch.AgentState(Agent("orch", "orchestrator", None, None), "idle", None),
        ]
        st = watch.WatchState(agents=agents)
        line = watch_ui.line1("game-web", st, "cab317f", 3, resurvey_error=None, mid_merge=False)
        self.assertEqual(line,
                         "game-web: 7 agents: world, render, gameplay ×2, qa, review, orchestrator. main at cab317f")

    def test_line1_idle_exact(self):
        line = watch_ui.line1("game-web", watch.WatchState(), "cab317f", 3)
        self.assertEqual(line,
                         "game-web: no agents working. Watching main and 3 worktrees.")

    def test_line1_resurvey_error(self):
        line = watch_ui.line1("game-web", watch.WatchState(), "abc", 0,
                              resurvey_error="disk full")
        self.assertEqual(line, "couldn't re-survey main: disk full")

    def test_line1_mid_merge(self):
        line = watch_ui.line1("game-web", watch.WatchState(main_mid_merge=True), "abc", 0,
                              mid_merge=True)
        self.assertEqual(line, "main is mid-merge")

    def test_line2_edit_exact(self):
        ev = Event("edit", Agent("w2-world/task-1", "implementer", "world", "w2-world"),
                   "tools/blender/env/kit/bake.py", 0.0)
        self.assertEqual(watch_ui.line2(ev, watch.WatchState(), "game-web"),
                         "world task 1 edited tools/blender/env/kit/bake.py")

    def test_line2_merge_exact(self):
        ev = Event("merge", None, None, 0.0)
        st = watch.WatchState()
        self.assertEqual(
            watch_ui.line2(ev, st, "game-web",
                          merge_summary="team/world/w2-corridors: 4 new buildings, 9 changed"),
            "merged team/world/w2-corridors: 4 new buildings, 9 changed")

    def test_line2_commit(self):
        ev = Event("commit", Agent("w1/task-1", "implementer", "world", "w1"), None, 0.0)
        self.assertEqual(watch_ui.line2(ev, watch.WatchState(), "x"),
                         "world task 1 committed")

    def test_line3_exact(self):
        model, rows, found, tmap = build_town()
        hall = crowd.town_hall_tile(tmap)
        c = crowd.Crowd(tmap, roads.Roads(tmap, model, found), model, set(model.modules), hall,
                        watch.FakeClock())
        d = crowd.CameraDirector(__import__("camera").Camera((0, 0)), c, tmap)
        for i, team in enumerate(["world", "render", "gameplay", "gameplay", "qa", "review"], 1):
            a = Agent(f"w{i}/task-1", "implementer", team, f"w{i}")
            c.apply([Event("start", a, None, float(i))], watch.WatchState(),
                    {team: i}, float(i))
        line = watch_ui.line3(d, "district")
        self.assertEqual(line,
                         "0 auto  1 world  2 render  3 gameplay  4 gameplay  5 qa  6 review   +/- zoom   q quit   [district]")

    def test_agent_labels_exact(self):
        impl = Agent("w2-world/task-1", "implementer", "world", "w2-world")
        self.assertEqual(watch_ui.agent_label(impl, "implementer", "world", (212, 14), None),
                         "world · task 1  +212 −14")
        rev = Agent("w2-world/review-task-1", "reviewer", "world", "w2-world")
        self.assertEqual(watch_ui.agent_label(rev, "reviewer", "world", (0, 0), 6),
                         "review · world task 1 (6 files)")
        self.assertEqual(watch_ui.agent_label(Agent("orch", "orchestrator", None, None),
                                              "orchestrator", None, (0, 0), None), "orchestrator")
        self.assertEqual(watch_ui.agent_label(Agent("agent:x", "agent", None, None),
                                              "agent", None, (0, 0), None), "agent")

    def test_label_order_and_taken_cells(self):
        model, rows, found, tmap = build_town()
        hall = crowd.town_hall_tile(tmap)
        c = crowd.Crowd(tmap, roads.Roads(tmap, model, found), model, set(model.modules), hall,
                        watch.FakeClock())
        a = Agent("w1/task-1", "implementer", "world", "w1")
        c.apply([Event("start", a, None, 0.0)], watch.WatchState(), {"world": 0}, 0.0)
        st = watch.WatchState(scaffolded={"app/main.py": "world", "core/notes.py": "world"})
        scene = __import__("drawtown").TownScene.whole(tmap, visible=())
        reqs = watch_ui.label_requests(c, crowd.CameraDirector(__import__("camera").Camera((0, 0)), c, tmap),
                                       scene, st, {"world": 0}, (100.0, 100.0), "street",
                                       scaffolded=c.effective_scaffold(st))
        texts = [r.text for r in reqs]
        self.assertTrue(texts[0].startswith("world"))
        self.assertEqual(texts[1], "Town Hall")
        building_labels = [t for t in texts[2:] if t.startswith("●")]
        self.assertLessEqual(len(building_labels), 8)
        taken = c.sprite_cells()
        labels.place(reqs, 80, 30, taken)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m unittest test_watch_ui -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'watch_ui'`

- [ ] **Step 3: Write minimal implementation**

Create `watch_ui.py`:

```python
"""Watch status lines and label assembly."""

import labels
import watch
from events import Event


def _task_num(agent_id: str) -> str:
    for part in agent_id.split("/"):
        if part.startswith("task-"):
            return part.replace("task-", "")
    return "1"


def _review_stem(agent_id: str) -> str:
    stem = agent_id.split("/", 1)[-1]
    if stem.startswith("review-"):
        return stem.replace("review-", "").replace("-result", "")
    return stem


def agent_label(agent, role, team, diff_stats, review_file_count):
    if role == "orchestrator":
        return "orchestrator"
    if role == "agent" or not team:
        return "agent"
    if role == "reviewer":
        stem = _review_stem(agent.id)
        files = f" ({review_file_count} files)" if review_file_count else ""
        return f"review · {team} {stem}{files}"
    added, removed = diff_stats
    return f"{team} · task {_task_num(agent.id)}  +{added} −{removed}"


def _team_line(agents):
    order = []
    counts = {}
    for a in agents:
        if a.agent.role == "orchestrator":
            continue
        if a.agent.role == "reviewer":
            name = "review"
        else:
            name = a.agent.team or "agent"
        if name not in counts:
            order.append(name)
        counts[name] = counts.get(name, 0) + 1
    parts = []
    for name in order:
        n = counts[name]
        parts.append(f"{name} ×{n}" if n > 1 else name)
    if any(a.agent.role == "orchestrator" for a in agents):
        parts.append("orchestrator")
    return ", ".join(parts)


def line1(repo_name, state, main_tip, worktree_count, *, resurvey_error=None, mid_merge=False):
    if resurvey_error:
        return f"couldn't re-survey main: {resurvey_error}"
    if mid_merge or state.main_mid_merge:
        return "main is mid-merge"
    if not state.agents:
        return f"{repo_name}: no agents working. Watching main and {worktree_count} worktrees."
    active = [a for a in state.agents if a.status in ("working", "touring")]
    if not active and not any(a.agent.role == "orchestrator" for a in state.agents):
        return f"{repo_name}: no agents working. Watching main and {worktree_count} worktrees."
    teams = _team_line(state.agents)
    tip = main_tip[:7]
    return f"{repo_name}: {len(state.agents)} agents: {teams}. main at {tip}"


def line2(event: Event | None, state, repo_name, *, merge_summary=None):
    if event is None:
        return ""
    if event.kind == "merge" and merge_summary:
        return f"merged {merge_summary}"
    if event.kind == "commit" and event.agent:
        team = event.agent.team or event.agent.worktree or "agent"
        return f"{team} task {_task_num(event.agent.id)} committed"
    if event.kind in ("edit", "create", "delete") and event.agent and event.path:
        team = event.agent.team or "agent"
        verb = {"edit": "edited", "create": "created", "delete": "deleted"}[event.kind]
        return f"{team} task {_task_num(event.agent.id)} {verb} {event.path}"
    if event.kind == "read" and event.agent and event.path:
        return f"orchestrator read {event.path}"
    return ""


def line3(director, zoom):
    """follow_labels() -> {agent_id: slot}; emit slots ascending."""
    labels_map = director.follow_labels()
    parts = ["0 auto"]
    for slot in sorted(labels_map.values()):
        agent_id = director.crowd._slots[slot]
        team = director.crowd._clawds[agent_id].team or "?"
        parts.append(f"{slot} {team}")
    parts.append("+/- zoom   q quit")
    parts.append(f"[{zoom}]")
    return "  ".join(parts)


def label_requests(crowd, director, scene, state, team_colours, camera_focus, zoom, *,
                    scaffolded=None):
    requests = []
    scaff = scaffolded if scaffolded is not None else crowd.effective_scaffold(state)
    for c in crowd.clawds():
        diff = state.diff_stats.get(c.worktree or "", (0, 0))
        nfiles = len(state.reviewer_tours.get(c.agent_id, ()))
        text = agent_label(
            __import__("events").Agent(c.agent_id, c.role, c.team, c.worktree),
            c.role, c.team, diff, nfiles if c.role == "reviewer" else None)
        fx, fy = crowd.clawd_focus_px(scene.m, c)
        fg, bg = labels.style_agent(labels.LIGHT, labels.DARK_GREY)
        requests.append(labels.LabelRequest(text, fx, int(fy) - 8, fg, bg))
    hx, hy = scene.screen(crowd.town_hall[0] + 0.5, crowd.town_hall[1] + 0.5)
    requests.append(labels.LabelRequest("Town Hall", float(hx), int(hy) - 10,
                                        *labels.style_name((112, 112, 124))))
    if zoom == "street":
        ranked = sorted(scaff, key=lambda m: abs(scene.centre_px(scene.m.buildings[m])[0] - camera_focus[0])
                        if m in scene.m.buildings else 9999)[:8]
        for mod in ranked:
            if mod not in scene.m.buildings:
                continue
            bx, by = scene.centre_px(scene.m.buildings[mod])
            path = labels.shorten(mod)
            requests.append(labels.LabelRequest(f"● {path}", float(bx), int(by) - 12,
                                                *labels.style_name((112, 112, 124))))
    return requests
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m unittest test_watch_ui -v`
Expected: PASS (10 tests)

- [ ] **Step 5: Commit**

```bash
git add watch_ui.py test_watch_ui.py
git commit -m "$(cat <<'EOF'
feat(watch): add status lines and label assembly with exact spec strings.

EOF
)"
```

---


### Task 6: `WatchViewer` with `ingest` / `tick` (no `poll` on UI thread)

**Files:**
- Modify: `viewer.py`, `watch.py` (idempotent `close()`)
- Create: `test_watch_viewer.py`

**Interfaces:**
- `@dataclass WatchSnapshot(events: list[Event], state: WatchState)`
- `WatchViewer.ingest(snapshot)` — apply `snapshot.events`, then replace `_latest_state`; queue draining applies every snapshot in order
- `WatchViewer.tick(dt, now) -> bool` — crowd, director, camera, drops
- `WatchViewer.moving() -> bool` — any Clawd walk/hop/drop or camera gliding
- `WatchPoller` — only thread that calls `Watch.poll()` / `Watch.state()`
- `run_watch(viewer, watch_obj, truecolor, clock, *, poller_factory, resurvey_runner)`

- [ ] **Step 1: Write the failing test**

Create `test_watch_viewer.py`:

```python
import os
import queue
import tempfile
import threading
import unittest

import camera
import crowd
import drawtown
import fixture
import viewer
import watch
from events import Agent, Event
from test_survey import MONOREPO_LIKE
from test_townmap import build as build_town
from test_watch import temp_survey


def _viewer(main=None, survey=None):
    model, rows, found, tmap = build_town()
    from roads import Roads
    from plat import Plat
    roads = Roads(tmap, model, found)
    plat = Plat().update(model, rows)
    repo = main or fixture.make_repo(None, {"a.py": "x\n"})
    survey = survey or tempfile.mkdtemp()
    w = watch.Watch(repo, survey_dir=survey)
    return viewer.WatchViewer(
        tmap, roads, model, rows, plat, "showcase", "deadbeef",
        {"world": 0}, survey, repo, w)


class IngestOrderTest(unittest.TestCase):
    def test_draining_applies_every_snapshot_in_order(self):
        v = _viewer()
        a = Agent("w1/task-1", "implementer", "world", "w1")
        v.ingest(viewer.WatchSnapshot([Event("start", a, None, 0.0)], watch.WatchState()))
        v.ingest(viewer.WatchSnapshot([Event("edit", a, "app/main.py", 1.0)],
                                      watch.WatchState(scaffolded={"app/main.py": "world"})))
        self.assertEqual(v._latest_event.kind, "edit")
        self.assertIn("app/main.py", v._crowd.effective_scaffold(v._latest_state))

    def test_queue_drain_never_drops_events(self):
        v = _viewer()
        a = Agent("w1/task-1", "implementer", "world", "w1")
        snaps = [
            viewer.WatchSnapshot([Event("start", a, None, float(i))], watch.WatchState())
            for i in range(3)
        ]
        for s in snaps:
            v.ingest(s)
        self.assertEqual(len(v._crowd.clawds()), 1)


class PollIsolationTest(unittest.TestCase):
    def test_ui_never_calls_poll(self):
        main = fixture.make_repo(self, MONOREPO_LIKE)
        survey = temp_survey(self)
        allowed = []

        class Guard(watch.Watch):
            def poll(self):
                if threading.current_thread().name != "WatchPoller":
                    raise AssertionError("poll outside poller thread")
                allowed.append(1)
                return super().poll()

        w = Guard(main, survey_dir=survey)
        q = queue.Queue()
        poller = viewer.WatchPoller(w, q, watch.FakeClock(), interval=0.01)
        poller.start()
        q.get(timeout=2)
        poller.close_event.set()
        poller.join(timeout=2)
        w.close()
        self.assertEqual(len(allowed), 1)



class DistrictFrameTest(unittest.TestCase):
    def test_district_zoom_includes_scaffold_in_frame(self):
        from viewer import WatchViewer, DISTRICT
        model, rows, found, tmap = build_town()
        from roads import Roads
        from plat import Plat
        roads = Roads(tmap, model, found)
        plat = Plat().update(model, rows)
        w = watch.Watch("/tmp", survey_dir="/tmp")
        v = WatchViewer(tmap, roads, model, rows, plat, "x", "t", {"world": 0}, "/tmp", "/tmp", w,
                        zoom=DISTRICT)
        v.ingest(viewer.WatchSnapshot([], watch.WatchState(scaffolded={"app/main.py": "world"})))
        fb = v.frame(80, 40)
        self.assertIn(drawtown.SCAFFOLD, {c for row in fb.rows for c in row})
        w.close()


class CloseTest(unittest.TestCase):
    def test_close_idempotent(self):
        main = fixture.make_repo(self, MONOREPO_LIKE)
        survey = temp_survey(self)
        w = watch.Watch(main, survey_dir=survey)
        w.close()
        w.close()


class SeedTest(unittest.TestCase):
    def test_seeds_crowd_from_initial_watch_state(self):
        model, rows, found, tmap = build_town()
        from roads import Roads
        from plat import Plat
        roads = Roads(tmap, model, found)
        plat = Plat().update(model, rows)
        main = fixture.make_repo(self, {"a.py": "x\n"})
        survey = temp_survey(self)
        w = watch.Watch(main, survey_dir=survey)
        # Mid-build: brief without report — implementer at latest_path building
        ledger = os.path.join(main, ".superpowers/sdd/run-1")
        os.makedirs(ledger, exist_ok=True)
        open(os.path.join(ledger, "task-1-brief.md"), "w").close()
        v = viewer.WatchViewer(tmap, roads, model, rows, plat, "x", "tip", {"world": 0},
                               survey, main, w)
        self.assertTrue(any(c.role == "implementer" for c in v._crowd.clawds()))
        w.close()


class MovingTest(unittest.TestCase):
    def test_moving_while_clawd_walks_or_camera_glides(self):
        model, rows, found, tmap = build_town()
        from roads import Roads
        roads = Roads(tmap, model, found)
        from plat import Plat
        plat = Plat().update(model, rows)
        hall = crowd.town_hall_tile(tmap)
        clock = watch.FakeClock()
        w = watch.Watch("/tmp", survey_dir="/tmp", clock=clock)
        v = viewer.WatchViewer(tmap, roads, model, rows, plat, "x", "tip", {}, "/tmp", "/tmp", w)
        a = Agent("w1/task-1", "implementer", "world", "w1")
        v.ingest(viewer.WatchSnapshot([Event("edit", a, "app/main.py", 0.0)], watch.WatchState()))
        self.assertTrue(v.moving())
        while v.moving():
            v.tick(0.05, v.t + 0.05)
        v.camera.set_target(999.0, 999.0)
        self.assertTrue(v.moving())
        for _ in range(200):
            if not v.moving():
                break
            v.tick(1 / 24, v.t + 1 / 24)
        self.assertFalse(v.moving())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m unittest test_watch_viewer -v`
Expected: FAIL — `WatchSnapshot` / `WatchViewer` missing

- [ ] **Step 3: Write minimal implementation**

In `watch.py`, replace `close`:

```python
def close(self):
    pool = getattr(self, "_observer_pool", None)
    if pool is not None:
        pool.shutdown(wait=True)
        self._observer_pool = None
```

Append to `viewer.py` (after existing imports add `queue`, `threading`, `dataclass`; reuse `_crop`, `shrink`, `STYLES`, `STATUS_LINES`, `MIN_COLS`, `MIN_LINES`, `parse_keys`, `FramePace`, `DISTRICT_FACTOR`, `TownScene`, `Framebuffer`):

```python
import queue
import threading
from dataclasses import dataclass

import crowd
import drawtown
import watch
import watch_sites
import watch_ui


WATCH_KEYMAP = {"0": "auto", "1": "1", "2": "2", "3": "3", "4": "4", "5": "5",
                "6": "6", "7": "7", "8": "8", "9": "9",
                "+": "zoom in", "=": "zoom in", "-": "zoom out", "_": "zoom out",
                "q": "quit", "\x03": "quit"}


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

    def run(self):
        while not self.close_event.is_set():
            self._queue.put(WatchSnapshot(self._watch.poll(), self._watch.state()))
            self.close_event.wait(self._interval)


class WatchViewer:
    def __init__(self, tmap, roads, model, rows, plat, repo_name, main_tip,
                 team_colours, survey_dir, repo_root, watch_obj, zoom=DISTRICT, *,
                 resurvey_runner=None):
        self.m = tmap
        self.roads = roads
        self.model = model
        self.rows = rows
        self.plat = plat
        self.repo_name = repo_name
        self.main_tip = main_tip
        self.repo_root = repo_root
        self.team_colours = team_colours
        self.survey_dir = survey_dir
        self._watch = watch_obj
        self.zoom = zoom
        self.t = 0.0
        self._latest_state = watch.WatchState()
        self._latest_event = None
        self._resurvey_error = None
        self._resurvey_inflight = False
        self._drops = {}
        self._resurvey_runner = resurvey_runner or (lambda fn: fn())
        hall = crowd.town_hall_tile(tmap)
        clock = getattr(watch_obj, "clock", watch.FakeClock())
        self._crowd = crowd.Crowd(tmap, roads, model, set(model.modules), hall, clock)
        initial = watch_obj.state()
        self._crowd.seed(initial, team_colours)
        self._latest_state = initial
        self._seeded = True
        self.camera = camera.Camera((0.0, 0.0))
        self._director = crowd.CameraDirector(self.camera, self._crowd, tmap)
        if self._crowd.clawds():
            focus = crowd.clawd_focus_px(tmap, self._crowd.clawds()[0])
        else:
            focus = crowd.clawd_focus_px(tmap, crowd.CrowdClawd(
                "_", "implementer", "world", 0, None, hall, (0, 1), "idle",
                1.0, 0, (), 0, None, None, 0.0, 0, 0.0, 0.0, 0.0,
                0.0, 0.0, (), 0, 0.0, True, False))
        self.camera.jump(*focus)

    def ingest(self, snapshot: WatchSnapshot):
        if snapshot.events:
            self._crowd.apply(snapshot.events, snapshot.state, self.team_colours, self.t)
            self._director.apply_events(snapshot.events, self.t)
            self._latest_event = snapshot.events[-1]
        self._latest_state = snapshot.state
        if snapshot.state.main_moved_clean and not snapshot.state.main_mid_merge:
            if not self._resurvey_inflight:
                self._resurvey_inflight = True
                self._resurvey_runner(lambda: self._do_resurvey())

    def tick(self, dt, now):
        self.t = now
        moving = self._crowd.step(dt)
        self._director.step(dt, now)
        moving = moving or self.camera.step(dt)
        moving = moving or any(drawtown.drop_offset(now - start) > 0.01
                               for start in self._drops.values())
        return moving

    def moving(self):
        """Pure query — no stepping (feeds FramePace 24/12 FPS)."""
        if self.camera.gliding():
            return True
        if self._crowd.is_moving():
            return True
        return any(drawtown.drop_offset(self.t - start) > 0.01 for start in self._drops.values())

    def press(self, key):
        if key in ("zoom in", "zoom out"):
            idx = ZOOMS.index(self.zoom)
            self.zoom = ZOOMS[max(0, min(len(ZOOMS) - 1, idx + (-1 if key == "zoom in" else 1)))]
        elif key == "auto" or (len(key) == 1 and key.isdigit()):
            self._director.press(key)
        elif key == "quit":
            raise KeyboardInterrupt

    def status(self, cols):
        wt_count = len(getattr(self._watch, "_worktrees", []) or [])
        line1 = watch_ui.line1(self.repo_name, self._latest_state, self.main_tip, wt_count,
                               resurvey_error=self._resurvey_error,
                               mid_merge=self._latest_state.main_mid_merge)
        line2 = watch_ui.line2(self._latest_event, self._latest_state, self.repo_name)
        line3 = watch_ui.line3(self._director, self.zoom)
        width = max(10, cols - 2)
        return [f" {s[:width]}" for s in (line1, line2, line3)]

    def overlays(self, w, h):
        if self.zoom != STREET:
            return []
        scene = TownScene.whole(self.m, visible=self.roads.visible())
        reqs = watch_ui.label_requests(
            self._crowd, self._director, scene, self._latest_state,
            self.team_colours, tuple(self.camera.focus), self.zoom,
            scaffolded=self._crowd.effective_scaffold(self._latest_state))
        return labels.place(reqs, w, h, self._crowd.sprite_cells())

    def frame(self, w, h):
        sites = watch_sites.layout_sites(self.m, self._crowd.effective_sites(self._latest_state))
        layer = drawtown.WatchLayer(
            self._crowd.effective_scaffold(self._latest_state), self.team_colours,
            sites, self._latest_state.flags, self._drops, self._crowd.clawds(),
            crowd.town_hall_tile(self.m))
        if self.zoom == STREET:
            whole = TownScene.whole(self.m, visible=self.roads.visible())
            whole.render()
            fx, fy = self.camera.focus
            sx, sy = fx - whole.ox, fy - whole.oy
            scene = TownScene(self.m, w, h, w // 2 - round(sx), h // 2 - round(sy),
                              t=self.t, visible=self.roads.visible())
            scene.set_watch(layer, STREET)
            return scene.render()
        whole = TownScene.whole(self.m, visible=self.roads.visible())
        whole.set_watch(layer, self.zoom)
        whole.render()
        factor = DISTRICT_FACTOR if self.zoom == DISTRICT else max(
            DISTRICT_FACTOR + 1, math.ceil(whole.fb.w / w), math.ceil(whole.fb.h / h))
        if self.zoom == TOWN:
            cx, cy = whole.fb.w // 2, whole.fb.h // 2
        else:
            cx, cy = round(self.camera.focus[0]), round(self.camera.focus[1])
        left, top = cx - w * factor // 2, cy - h * factor // 2
        cropped = _crop(whole.fb, left, top, w * factor, h * factor)
        return shrink(cropped, factor)

    def _do_resurvey(self):
        try:
            model, rows, plat = resurvey_main(self.repo_root, self.plat, self.rows)
            self.apply_resurvey(model, rows, plat)
            self._watch.note_resurvey(model, self._watch._poll_main_tip)
        except Exception as e:
            self._resurvey_error = str(e)
        finally:
            self._resurvey_inflight = False

    def apply_resurvey(self, model, rows, plat):
        from problems import find
        from townmap import TownMap
        from roads import Roads
        old = set(self.m.buildings)
        self.model, self.rows, self.plat = model, rows, plat
        found = find(model, rows)
        self.m = TownMap(model, plat, rows, found)
        self.roads = Roads(self.m, model, found)
        hall = crowd.town_hall_tile(self.m)
        self._crowd.retown(self.m, self.roads, model, set(model.modules), hall)
        self._director.crowd = self._crowd
        self._director.tmap = self.m
        for mod in set(self.m.buildings) - old:
            self._drops[mod] = self.t
        self._resurvey_error = None


def resurvey_main(repo_root, plat, rows):
    model = survey.survey(repo_root)
    rows = rows.update(model)
    plat = plat.update(model, rows)
    return model, rows, plat


def run_watch(viewer, watch_obj, truecolor, clock=time.monotonic, *,
              poller_factory=WatchPoller, resurvey_runner=None):
    viewer._resurvey_runner = resurvey_runner or (lambda fn: fn())
    q = queue.Queue()
    poller = poller_factory(watch_obj, q, clock)
    poller.start()
    screen = term.Screen(truecolor)
    pace = FramePace(clock)
    with term.Terminal() as t:
        t.write("\x1b]0;CodeTown watch\x07")
        start = clock()
        timeout = 0.0
        try:
            while True:
                frame_start = clock()
                while not q.empty():
                    viewer.ingest(q.get_nowait())
                now = clock() - start
                for key in parse_keys(t.read(timeout), WATCH_KEYMAP):
                    if key == "quit":
                        return
                    viewer.press(key)
                viewer.t = now
                cols, lines = t.size()
                if cols >= MIN_COLS and lines >= MIN_LINES:
                    fb = viewer.frame(cols // 2, lines - STATUS_LINES)
                    status = [style + line for style, line in zip(STYLES, viewer.status(cols))]
                    t.write(screen.frame(fb, status, viewer.overlays(fb.w, fb.h)))
                moving = viewer.tick(clock() - frame_start, now)
                timeout = pace.after_frame(clock() - frame_start, moving)
        finally:
            poller.close_event.set()
            poller.join(timeout=2)
            watch_obj.close()
```

Also extend existing `viewer.parse_keys` (do not add a second parser):

```python
def parse_keys(data, keymap=KEYMAP):
    return term.parse_keys(data, keymap)
```

Add to `test_watch_viewer.py`:

```python
    def test_parse_keys_reads_digits_for_watch(self):
        from viewer import parse_keys, WATCH_KEYMAP
        self.assertEqual(parse_keys("0123456789q", WATCH_KEYMAP),
                         ["0", "1", "2", "3", "4", "5", "6", "7", "8", "9", "quit"])
```

Add `import survey` at top of `viewer.py` if not present.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m unittest test_watch_viewer -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add viewer.py watch.py test_watch_viewer.py
git commit -m "$(cat <<'EOF'
feat(watch): add WatchViewer ingest/tick loop and poll isolation.

EOF
)"
```

---

### Task 7: Merges and re-survey

**Files:**
- Modify: `watch.py` (`note_resurvey`), `viewer.py` (resurvey hooks)
- Create: `test_watch_merge.py`

**Interfaces:**
- `watch.note_resurvey(model, surveyed_tip)` — clears `main_moved_clean`, updates model and tip
- Injectable `resurvey_runner` — production runs `_do_resurvey` on worker thread; tests call synchronously
- Re-survey once per `main_moved_clean` flag, not once per frame; skip when `main_mid_merge`

- [ ] **Step 1: Write the failing test**

Create `test_watch_merge.py`:

```python
import os
import unittest
from unittest import mock

import fixture
import viewer
import watch
from test_survey import MONOREPO_LIKE
from test_townmap import build as build_town
from test_watch import temp_survey


class NoteResurveyTest(unittest.TestCase):
    def test_clears_main_moved_clean(self):
        main = fixture.make_repo(self, MONOREPO_LIKE)
        survey = temp_survey(self)
        w = watch.Watch(main, survey_dir=survey)
        w._main_moved_clean = True
        w.note_resurvey(w._model, "deadbeef")
        self.assertFalse(w._main_moved_clean)
        self.assertEqual(w._surveyed_main_tip, "deadbeef")
        w.close()


class ResurveyRunnerTest(unittest.TestCase):
    def setUp(self):
        model, rows, found, tmap = build_town()
        from roads import Roads
        from plat import Plat
        self.tmap, self.model, self.rows, self.plat = tmap, model, rows, Plat().update(model, rows)
        self.roads = Roads(tmap, model, found)
        self.main = fixture.make_repo(self, MONOREPO_LIKE)
        self.survey = temp_survey(self)

    def _viewer(self, runner):
        w = watch.Watch(self.main, survey_dir=self.survey)
        return viewer.WatchViewer(
            self.tmap, self.roads, self.model, self.rows, self.plat,
            "demo", "abc1234", {}, self.survey, self.main, w,
            resurvey_runner=runner), w

    def test_runs_once_while_inflight(self):
        calls = []
        v, w = self._viewer(lambda fn: calls.append(1) or fn())
        st = watch.WatchState(main_moved_clean=True)
        v.ingest(viewer.WatchSnapshot([], st))
        v.ingest(viewer.WatchSnapshot([], st))
        self.assertEqual(len(calls), 1)
        w.close()

    def test_mid_merge_skips_resurvey(self):
        calls = []
        v, w = self._viewer(lambda fn: calls.append(1) or fn())
        v.ingest(viewer.WatchSnapshot([], watch.WatchState(main_moved_clean=True, main_mid_merge=True)))
        self.assertEqual(calls, [])
        w.close()

    def test_failure_keeps_old_town(self):
        v, w = self._viewer(lambda fn: fn())
        old_modules = set(v.m.buildings)
        with mock.patch("viewer.resurvey_main", side_effect=RuntimeError("disk full")):
            v._do_resurvey()
        self.assertEqual(set(v.m.buildings), old_modules)
        self.assertEqual(v._resurvey_error, "disk full")
        w.close()

    def test_success_retowns_without_resetting_clawds(self):
        v, w = self._viewer(lambda fn: fn())
        a = Agent("w1/task-1", "implementer", "world", "w1")
        v._crowd.apply([Event("start", a, None, 0.0)], watch.WatchState(), {"world": 0}, 0.0)
        ids_before = {c.agent_id for c in v._crowd.clawds()}
        with mock.patch("viewer.resurvey_main", return_value=(self.model, self.rows, self.plat)):
            v._do_resurvey()
        self.assertIsNone(v._resurvey_error)
        self.assertEqual(ids_before, {c.agent_id for c in v._crowd.clawds()})
        w.close()

    def test_line1_shows_resurvey_error(self):
        v, w = self._viewer(lambda fn: fn())
        v._resurvey_error = "disk full"
        line = watch_ui.line1("x", v._latest_state, "tip", 0, resurvey_error=v._resurvey_error)
        self.assertEqual(line, "couldn't re-survey main: disk full")
        w.close()
```

Add at top of test file: `import watch_ui`

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m unittest test_watch_merge -v`
Expected: FAIL — `note_resurvey` missing

- [ ] **Step 3: Write minimal implementation**

In `watch.py`:

```python
def note_resurvey(self, model, surveyed_tip: str):
    self._model = model
    self._surveyed_main_tip = surveyed_tip
    self._main_moved_clean = False
```

(`WatchViewer._do_resurvey` and `apply_resurvey` are in Task 6; ensure `note_resurvey` is called on success.)

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m unittest test_watch_merge -v`
Expected: PASS (8 tests)

- [ ] **Step 5: Commit**

```bash
git add watch.py viewer.py test_watch_merge.py
git commit -m "$(cat <<'EOF'
feat(watch): re-survey main on clean merge with injectable runner.

EOF
)"
```

---

### Task 8: CLI — `towncode watch` and `snapshot --watch`

**Files:**
- Modify: `towncode.py`, `test_towncode.py`, `test_watch_e2e.py`

Mirror `_view` non-tty behaviour exactly:

```python
if not sys.stdin.isatty():
    raise SystemExit("towncode watch needs an interactive terminal.")
```

- [ ] **Step 1: Write the failing test**

In `test_watch_e2e.py`, replace `test_plain_watch_exits_nonzero`:

```python
    def test_plain_watch_starts_viewer_with_tty(self):
        with mock.patch("sys.stdin.isatty", return_value=True):
            with mock.patch("viewer.run_watch", side_effect=KeyboardInterrupt):
                code = towncode.main(["watch", self.root])
        self.assertEqual(code, 0)

    def test_watch_requires_tty_like_view(self):
        with mock.patch("sys.stdin.isatty", return_value=False):
            with self.assertRaises(SystemExit) as ctx:
                towncode.main(["watch", self.root])
            self.assertIn("interactive terminal", str(ctx.exception))
```

In `test_towncode.py`, add:

```python
    def test_snapshot_watch_writes_png(self):
        import tempfile
        out = os.path.join(tempfile.mkdtemp(), "frame.png")
        self.addCleanup(shutil.rmtree, os.path.dirname(out))
        towncode.run(self.root)
        code = towncode.main(["snapshot", self.root, out, "--watch", "--size", "40x20", "--scale", "1"])
        self.assertEqual(code, 0)
        self.assertTrue(os.path.isfile(out))
        self.assertGreater(os.path.getsize(out), 100)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m unittest test_watch_e2e.TowncodeWatchCLITest test_towncode -v`
Expected: FAIL — plain watch still exits 2; `--watch` unknown

- [ ] **Step 3: Write minimal implementation**

In `towncode.py`:

```python
def _load_saved(repo_root):
    out = output_dir(repo_root)
    from model import Model
    from layers import Rows
    from plat import Plat
    model = _saved(os.path.join(out, "model.json"), Model.load, "model", "re-survey")
    rows = _saved(os.path.join(out, "rows.json"), lambda p: Rows.load(p).update(model), "rows", "rebuild")
    plat = _saved(os.path.join(out, "plat.json"), lambda p: Plat.load(p).update(model, rows), "plat", "re-layout")
    return model, rows, plat, out


def _watch_viewer(args, *, home="~", survey_dir=None):
    import watch as watch_mod
    model, rows, plat, out = _load_saved(args.path)
    found = problems.find(model, rows)
    tmap = TownMap(model, plat, rows, found)
    w = watch_mod.Watch(args.path, home=home, survey_dir=survey_dir or out)
    teams, _ = watch_mod.load_colours(survey_dir or out)
    tip = w._poll_main_tip[:7]
    repo_name = os.path.basename(os.path.realpath(args.path))
    zoom = getattr(args, "zoom", viewer.DISTRICT)
    return viewer.WatchViewer(
        tmap, Roads(tmap, model, found), model, rows, plat,
        repo_name, tip, teams, survey_dir or out, args.path, w, zoom=zoom)


def _watch(args, sleep=time.sleep, *, home="~", survey_dir=None):
    import watch as watch_mod
    if args.events:
        w = watch_mod.Watch(args.path, home=home, clock=None, survey_dir=survey_dir)
        try:
            while True:
                for event in w.poll():
                    print(_format_event(event))
                sys.stdout.flush()
                sleep(1)
        except KeyboardInterrupt:
            pass
        except BrokenPipeError:
            sys.stdout = open(os.devnull, "w")
        finally:
            w.close()
        return 0
    if not sys.stdin.isatty():
        raise SystemExit("towncode watch needs an interactive terminal.")
    v = _watch_viewer(args, home=home, survey_dir=survey_dir)
    truecolor = term.supports_truecolor()
    try:
        viewer.run_watch(v, v._watch, truecolor)
    except KeyboardInterrupt:
        pass
    return 0
```

Update `_snapshot`:

```python
def _snapshot(args):
    if _inside(args.out, args.path):
        raise SystemExit(f"refusing to write inside the surveyed repository: {args.out}")
    w, h = _parse_size(args.size)
    if getattr(args, "watch", False):
        v = _watch_viewer(args)
        fb = v.frame(w, h)
        snapshot.write_png(args.out, fb, args.scale)
        print(f"wrote {args.out}")
        return 0
    model, rows, plat, _ = run(args.path)
    v = town(model, rows, plat)
    if args.at:
        tile = v.m.centre(args.at)
        if tile is None:
            raise SystemExit(f"no building or plot for {args.at}")
        v.cursor, v.problem = tile, None
        v.sync_camera()
    v.zoom = args.zoom
    snapshot.write_png(args.out, v.frame(w, h), args.scale)
    print(f"wrote {args.out}")
    return 0
```

Replace `_parser` watch and snapshot sections:

```python
    cmd = commands.add_parser("watch", help="watch agents working in a git repository")
    cmd.add_argument("path")
    cmd.add_argument("--events", action="store_true", help="stream lifecycle events")
    cmd.add_argument("--zoom", choices=viewer.ZOOMS, default=viewer.DISTRICT)
    snap = commands.add_parser("snapshot", help="survey a repository and draw its town to a PNG")
    snap.add_argument("path")
    snap.add_argument("out")
    snap.add_argument("--zoom", choices=viewer.ZOOMS, default=viewer.TOWN)
    snap.add_argument("--at", help="module to centre on (default: the worst problem)")
    snap.add_argument("--size", default="160x90", help="frame in pixels, WxH")
    snap.add_argument("--scale", type=int, default=4)
    snap.add_argument("--watch", action="store_true",
                      help="one frame of live watch state (no terminal required)")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m unittest test_watch_e2e.TowncodeWatchCLITest test_towncode -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add towncode.py test_towncode.py test_watch_e2e.py
git commit -m "$(cat <<'EOF'
feat(towncode): add watch view CLI and snapshot --watch.

EOF
)"
```

---

### Task 9: End-to-end view state and benchmark

**Files:**
- Create: `test_watch_e2e_view.py`, `scripts/benchmark_watch_frame.py`, `test_benchmark_smoke.py`

- [ ] **Step 1: Write the failing test**

Create `test_watch_e2e_view.py`:

```python
import os
import shutil
import tempfile
import unittest

import fixture
import untouched
import viewer
import watch
from test_transcripts import write_lines, use
from test_watch import add_worktree, temp_survey, temp_wts
from test_watch_e2e import WatchE2ETest


class WatchViewEndStateTest(WatchE2ETest):
    def _seed_orchestrator(self):
        slug = os.path.realpath(self.main).replace("/", "-").replace(".", "-").replace("_", "-")
        tr = os.path.join(self.home, ".cursor", "projects", slug.lstrip("-"),
                          "agent-transcripts", "chat-1", "chat-1.jsonl")
        write_lines(tr, [{"role": "assistant", "message": {"content": [
            {"type": "tool_use", "name": "Task", "input": {"subagent": True}}]}}])
        sub = os.path.join(os.path.dirname(tr), "subagents", "sub1.jsonl")
        wt = os.path.join(self.wts, "demo")
        write_lines(sub, [{"role": "assistant", "message": {"content": [
            use("Read", path=os.path.join(wt, "hub/a.py"))]}}])
        os.utime(tr, (self.clock.time(), self.clock.time()))

    def test_view_end_state_matches_spec(self):
        before_main = untouched.fingerprint(self.main)
        wt_path = add_worktree(self, self.main, os.path.join(self.wts, "demo"), "team/world/demo")
        before_wt = untouched.fingerprint(wt_path)
        self._seed_orchestrator()
        kinds = self._run_script()
        self.assertEqual(kinds[-2:], ["merge", "leave"])
        import towncode
        model, rows, plat, out = towncode.run(self.main)
        from townmap import TownMap
        from roads import Roads
        from problems import find
        found = find(model, rows)
        tmap = TownMap(model, plat, rows, found)
        w = watch.Watch(self.main, home=self.home, clock=self.clock, survey_dir=self.survey)
        v = viewer.WatchViewer(
            tmap, Roads(tmap, model, found), model, rows, plat,
            "demo", w._poll_main_tip[:7], {"world": 0}, self.survey, self.main, w,
            resurvey_runner=lambda fn: fn())
        for _ in range(30):
            snap = viewer.WatchSnapshot(w.poll(), w.state())
            v.ingest(snap)
            v.tick(1.0, v.t + 1.0)
            self.clock.advance(1)
        self.assertIn("hub/new.py", v.m.buildings)
        self.assertEqual(v._crowd.effective_scaffold(v._latest_state), {})
        self.assertEqual(v._crowd.effective_sites(v._latest_state), [])
        roles = {c.role for c in v._crowd.clawds()}
        self.assertEqual(roles, {"orchestrator"})
        self.assertEqual(untouched.differences(before_main, untouched.fingerprint(self.main)), {})
        self.assertEqual(untouched.differences(before_wt, untouched.fingerprint(wt_path)), {})
        w.close()
```

Create `test_benchmark_smoke.py`:

```python
import importlib.util
import os
import unittest


class BenchmarkSmokeTest(unittest.TestCase):
    def test_build_frame_runs_once(self):
        path = os.path.join(os.path.dirname(__file__), "scripts", "benchmark_watch_frame.py")
        spec = importlib.util.spec_from_file_location("benchmark_watch_frame", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        mod.build_frame()
```

Create `scripts/benchmark_watch_frame.py`:

```python
#!/usr/bin/env python3
"""Median street frame time with 10 Clawds at 120x57. Exit 1 if median > 35 ms."""
import statistics
import sys
import time

import crowd
import drawtown
import fixture
import roads
import survey
import towncode
import viewer
import watch
import watch_sites
import watch_ui
from events import Agent, Event
from labels import place
from test_survey import MONOREPO_LIKE


def build_frame():
    root = fixture.make_repo(None, MONOREPO_LIKE)
    model, rows, plat, out = towncode.run(root)
    from problems import find
    from townmap import TownMap
    found = find(model, rows)
    tmap = TownMap(model, plat, rows, found)
    rds = roads.Roads(tmap, model, found)
    clock = watch.FakeClock()
    w = watch.Watch(root, survey_dir=out, clock=clock)
    v = viewer.WatchViewer(tmap, rds, model, rows, plat, "bench", "tip", {"world": 0},
                           out, root, w, zoom=viewer.STREET)
    teams = ["world", "render", "gameplay", "qa", "review"]
    for i, team in enumerate(teams):
        a = Agent(f"w{i}/task-1", "implementer", team, f"w{i}")
        v.ingest(viewer.WatchSnapshot([Event("start", a, None, float(i))],
                                      watch.WatchState(scaffolded={"hub/app.py": team})))
    for i in range(5):
        a = Agent(f"x{i}/task-1", "implementer", "world", f"x{i}")
        v.ingest(viewer.WatchSnapshot([Event("edit", a, "hub/records.py", float(i))],
                                      watch.WatchState()))
    v.tick(0.1, 0.1)
    fb = v.frame(120, 57)
    overlays = v.overlays(fb.w, fb.h)
    place(overlays, fb.w, fb.h, v._crowd.sprite_cells())
    return fb


def main():
    times = []
    for _ in range(11):
        t0 = time.perf_counter()
        build_frame()
        times.append((time.perf_counter() - t0) * 1000)
    med = statistics.median(times[1:])
    label = "OK" if med <= 35 else "SLOW"
    print(f"{label}: {med:.1f} ms")
    return 1 if med > 35 else 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m unittest test_watch_e2e_view test_benchmark_smoke -v`
Expected: FAIL

- [ ] **Step 3: Write minimal implementation**

Implement `test_watch_e2e_view.py`, `scripts/benchmark_watch_frame.py`, and `test_benchmark_smoke.py` as shown above. Drive the viewer synchronously: after each `w.poll()`, call `v.ingest(WatchSnapshot(...))` then `v.tick(1.0, v.t + 1.0)`. Use `resurvey_runner=lambda fn: fn()` so merge re-survey completes in-process. Seed orchestrator before `_run_script()` via `_seed_orchestrator()` (main transcript + subagent under `subagents/`).

- [ ] **Step 4: Run test to verify it passes**

Expected: PASS (e2e may need merge/resurvey mocked if survey slow — use `resurvey_runner` sync)

- [ ] **Step 5: Commit**

```bash
git add test_watch_e2e_view.py scripts/benchmark_watch_frame.py test_benchmark_smoke.py
git commit -m "$(cat <<'EOF'
test(watch): add view end-state e2e and frame benchmark script.

EOF
)"
```

---

### Task 10: Full-suite verification

- [ ] Run targeted suite:

`.venv/bin/python -m unittest test_watch_colours test_crowd test_watch_camera test_watch_draw test_watch_ui test_watch_viewer test_watch_merge test_watch_e2e test_watch_e2e_view test_benchmark_smoke test_watch test_towncode -v`

- [ ] Run full suite:

`.venv/bin/python -m unittest`

- [ ] Run benchmark manually (not in unit suite):

`.venv/bin/python scripts/benchmark_watch_frame.py`

Expected: prints `OK: X.X ms` or `SLOW: X.X ms`; exit 1 if over 35 ms.

- [ ] Commit any fixes from verification.

---

## Self-Review (spec Testing + Success)

| Spec bullet | Test |
| --- | --- |
| Observer create/edit/delete/rename | Phase 2 `test_observer.py` |
| Worktrees, teams, merged hidden, leave | Phase 2 `test_watch.py` |
| Ledger start/finish/review_* | Phase 2 `test_watch.py` |
| Transcripts partial line, shrink, relative paths, orchestrator | `test_transcripts.py` |
| map_path, unbuilt sites, nearest building | Phase 2 `test_watch.py` |
| Crowd standing spots, path replace, merge departure, flag up/down, mid-build orchestrator | `test_crowd.py` (23 tests, every spec table row) |
| Camera 4 s stay, priority, follow until 0/departure | `test_watch_camera.py` |
| Colours distance + persistence | `test_watch_colours.py` |
| Drawing depth order, scaffold in front, Clawd partly hidden, all zooms | `test_watch_draw.py` |
| E2E event order | `test_watch_e2e.test_event_order_for_fake_run` |
| E2E view end state + fingerprint | `test_watch_e2e_view.test_view_end_state_matches_spec` |
| Within 2 s scaffold (provisional) | `test_crowd.test_edit_scaffolds_every_touched_building...` |
| Within 3 s re-survey | `test_watch_merge` + manual on game-web |
| Principle 8 targets justified | `test_crowd.test_principle_8_all_targets_justified` |
| Mid-build seed | `test_crowd.test_mid_build_seed_without_replay` |
| Follow numbers 1–9 | `test_crowd.test_follow_numbers_lowest_free_reused` |
| Status lines verbatim | `test_watch_ui.py` |
| Mid-build seed on viewer open | `test_watch_viewer.test_seeds_crowd_from_initial_watch_state` |
| ingest drains all snapshots | `test_watch_viewer.test_queue_drain_never_drops_events` |
| UI never calls poll | `test_watch_viewer.test_ui_never_calls_poll` |
| moving() for FramePace | `test_watch_viewer.test_moving_while_clawd_walks_or_camera_glides` |
| mid-merge line 1 | `test_watch_ui.test_line1_mid_merge` |
| re-survey failure line 1 | `test_watch_ui.test_line1_resurvey_error` |
| Benchmark ≤35 ms | `scripts/benchmark_watch_frame.py` |
| Read-only fingerprint | `test_watch_e2e_view` + Phase 2 `test_watch_leaves_repo...` |
| 24/12 FPS rule | `viewer.FramePace` + `WatchViewer.moving()` |

## Rulings

1. Town Hall tile: frontmost avenue, nearest centre column; ties `(y, x)`.
2. Reserved colours: import `labels.FIRE_BG`, `labels.LOUD_BG`; copy mock_roles-only values into `watch.RESERVED` with skipUnless test against mock_roles.
3. PALETTE verified ≥80 from reserved (min 80.72) and ≥60 pairwise (min 60.04) before writing plan values.
4. Provisional scaffold in `Crowd.effective_scaffold`; labels use same merged dict.
5. Poll handoff via `WatchPoller`; UI uses `ingest`/`tick` only.
6. `Watch.close()` idempotent.
7. Re-survey in-memory only via `Plat.update`; writes nothing except existing `watch.json`.
8. Site yards in `watch_sites.py` (Task 2); no mock_roles import in production.
9. **Orchestrator required in e2e view test** — fake transcript with subagent dispatch.
10. Merge hop uses merge event's implementer `Event.agent`.
11. `main is mid-merge` on status line 1 (Merges step 1).
12. Drop easing inline in `drawtown.drop_offset` (v3 intro not in repo).
13. Benchmark not in unit suite; smoke test only.
14. Watch drawables interleaved in `TownScene.render()` depth pass via `set_watch()` — not painted after `render()`.
15. Scarf on `sprites.clawd_rows` row 3; `_tier_block` copied from `mock_roles.tier` for sites.
16. `Crowd._now` advanced in `step(dt)`; `apply(..., now)` sets it; all timed behaviour reads `_now`.
17. `moving()` is pure query via `Crowd.is_moving()` — never calls `step`.
18. `viewer.parse_keys(data, keymap=KEYMAP)` extended for watch digits; `run_watch` passes `WATCH_KEYMAP`.
19. Re-survey calls `Crowd.retown()` — never rebuilds/reseeds the crowd (preserves merge hop-and-leave).
