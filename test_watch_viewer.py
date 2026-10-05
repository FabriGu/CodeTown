import os
import queue
import shutil
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


class _BenchCleanup(unittest.TestCase):
    pass


_BENCH = _BenchCleanup()


def _viewer(test=None, main=None, survey=None, *, ingest=True):
    test = test or _BENCH
    model, rows, found, tmap = build_town()
    from roads import Roads
    from plat import Plat
    roads = Roads(tmap, model, found)
    plat = Plat().update(model, rows)
    repo = main or fixture.make_repo(test, {"a.py": "x\n"})
    if survey is None:
        survey = tempfile.mkdtemp(prefix="watch-survey-")
        test.addCleanup(shutil.rmtree, survey, ignore_errors=True)
    w = watch.Watch(repo, survey_dir=survey)
    v = viewer.WatchViewer(
        tmap, roads, model, rows, plat, "showcase", "deadbeef",
        survey, repo, w)
    if ingest:
        v.ingest(viewer.WatchSnapshot([], w.state()))
    test.addCleanup(w.close)
    return v


class IngestOrderTest(unittest.TestCase):
    def test_draining_applies_every_snapshot_in_order(self):
        v = _viewer(self)
        a = Agent("w1/task-1", "implementer", "world", "w1")
        v.ingest(viewer.WatchSnapshot([Event("start", a, None, 0.0)], watch.WatchState()))
        v.ingest(viewer.WatchSnapshot([Event("edit", a, "app/main.py", 1.0)],
                                      watch.WatchState(scaffolded={"app/main.py": "world"})))
        self.assertEqual(v._latest_event.kind, "edit")
        self.assertIn("app/main.py", v._crowd.effective_scaffold(v._latest_state))

    def test_queue_drain_never_drops_events(self):
        v = _viewer(self)
        a = Agent("w1/task-1", "implementer", "world", "w1")
        snaps = [
            viewer.WatchSnapshot([Event("start", a, None, float(i))], watch.WatchState())
            for i in range(3)
        ]
        q = queue.Queue()
        for s in snaps:
            q.put(s)
        viewer.drain_viewer(v, q)
        self.assertEqual(len(v._crowd.clawds()), 1)


class PollResilienceTest(unittest.TestCase):
    def test_poller_survives_poll_exception(self):
        q = queue.Queue()
        calls = [0]

        class FlakyWatch(_BareWatch):
            def poll(self):
                calls[0] += 1
                if calls[0] == 1:
                    raise RuntimeError("poll failed")
                return []

        w = FlakyWatch()
        poller = viewer.WatchPoller(w, q, watch.FakeClock(), interval=0.05)
        poller.start()
        first = q.get(timeout=2)
        self.assertEqual(first.events, [])
        second = q.get(timeout=2)
        self.assertEqual(second.events, [])
        self.assertGreaterEqual(calls[0], 1)
        poller.close_event.set()
        poller.join(timeout=2)
        self.assertFalse(poller.is_alive())


class PollIsolationTest(unittest.TestCase):
    def test_ui_never_calls_poll(self):
        main = fixture.make_repo(self, {"a.py": "x\n"})
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
        poller = viewer.WatchPoller(w, q, watch.FakeClock(), interval=0.05)
        poller.start()
        first = q.get(timeout=2)
        self.assertEqual(first.events, [])
        q.get(timeout=5)
        poller.close_event.set()
        poller.join(timeout=2)
        w.close()
        self.assertEqual(len(allowed), 1)


class _BareWatch:
    clock = watch.FakeClock()

    def state(self):
        return watch.WatchState()

    def close(self):
        pass


class DistrictFrameTest(unittest.TestCase):
    def test_district_zoom_includes_scaffold_in_frame(self):
        from viewer import WatchViewer, DISTRICT
        model, rows, found, tmap = build_town()
        from roads import Roads
        from plat import Plat
        roads = Roads(tmap, model, found)
        plat = Plat().update(model, rows)
        w = _BareWatch()
        v = WatchViewer(tmap, roads, model, rows, plat, "x", "t", "/tmp", "/tmp", w,
                        zoom=DISTRICT)
        v.ingest(viewer.WatchSnapshot([], watch.WatchState(
            scaffolded={"app/main.py": "world"}, team_colours={"world": 0})))
        fb = v.frame(80, 40)
        team = watch.PALETTE[0]
        shades = {drawtown.scaffold_shade(team, i, 24) for i in range(24)}
        pixels = {c for row in fb.rows for c in row}
        self.assertTrue(pixels & shades, "scaffold team colour visible at district zoom")
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
        main = fixture.make_repo(self, {"a.py": "x\n", "app/main.py": "x\n"})
        survey = temp_survey(self)
        wts = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, wts, ignore_errors=True)
        wt = fixture.worktree(main, os.path.join(wts, "w1"), "team/world/x",
                              {"app/main.py": "changed\n"})
        ledger = os.path.join(wt, ".superpowers/sdd/run-1")
        os.makedirs(ledger, exist_ok=True)
        open(os.path.join(ledger, "task-1-brief.md"), "w").close()
        w = watch.Watch(main, survey_dir=survey)
        v = viewer.WatchViewer(tmap, roads, model, rows, plat, "x", "tip", survey, main, w)
        st = w.state()
        v.ingest(viewer.WatchSnapshot([], st))
        self.assertTrue(any(c.role == "implementer" for c in v._crowd.clawds()))
        n = len(v._crowd.clawds())
        a = next(a for a in st.agents if a.agent.role == "implementer")
        v.ingest(viewer.WatchSnapshot([Event("start", a.agent, None, 1.0)], st))
        self.assertEqual(len(v._crowd.clawds()), n)
        w.close()


class MovingTest(unittest.TestCase):
    def test_moving_while_clawd_walks_or_camera_glides(self):
        model, rows, found, tmap = build_town()
        from roads import Roads
        roads = Roads(tmap, model, found)
        from plat import Plat
        plat = Plat().update(model, rows)
        clock = watch.FakeClock()
        w = _BareWatch()
        w.clock = clock
        v = viewer.WatchViewer(tmap, roads, model, rows, plat, "x", "tip", "/tmp", "/tmp", w)
        v.ingest(viewer.WatchSnapshot([], watch.WatchState()))
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

    def test_tick_steps_crowd_and_camera_together(self):
        model, rows, found, tmap = build_town()
        from roads import Roads
        from plat import Plat
        roads = Roads(tmap, model, found)
        plat = Plat().update(model, rows)
        w = _BareWatch()
        v = viewer.WatchViewer(tmap, roads, model, rows, plat, "x", "t", "/tmp", "/tmp", w)
        v.ingest(viewer.WatchSnapshot([], watch.WatchState()))
        a = Agent("w1/task-1", "implementer", "world", "w1")
        v.ingest(viewer.WatchSnapshot([Event("edit", a, "app/main.py", 0.0)],
                                      watch.WatchState(team_colours={"world": 0})))
        c = v._crowd._clawds[a.id]
        walk_t0 = c.walk_t
        focus0 = list(v.camera.focus)
        v.camera.set_target(focus0[0] + 100.0, focus0[1] + 100.0)
        v.tick(0.05, 0.05)
        self.assertNotEqual(c.walk_t, walk_t0)
        self.assertNotEqual(list(v.camera.focus), focus0)


class ParseKeysTest(unittest.TestCase):
    def test_parse_keys_reads_digits_for_watch(self):
        from viewer import parse_keys, WATCH_KEYMAP
        self.assertEqual(parse_keys("0123456789q", WATCH_KEYMAP),
                         ["0", "1", "2", "3", "4", "5", "6", "7", "8", "9", "quit"])
