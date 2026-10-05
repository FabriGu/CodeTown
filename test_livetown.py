import os
import subprocess
import sys
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

HERE = os.path.dirname(os.path.abspath(__file__))

A = Agent("w1/task-1", "implementer", "world", "w1")


def _live(*, runner=None, resurvey=None):
    model, rows, found, tmap = build_town()
    roads = Roads(tmap, model, found)
    plat = Plat().update(model, rows)
    return livetown.LiveTown(tmap, roads, model, rows, plat, "showcase", "deadbeef", "/nowhere",
                             watch.FakeClock(), resurvey_runner=runner or (lambda fn: fn()),
                             resurvey=resurvey)


class LivetownImportTest(unittest.TestCase):
    def test_import_livetown_first_in_fresh_interpreter(self):
        result = subprocess.run(
            [sys.executable, "-c", "import livetown"],
            cwd=HERE,
            capture_output=True,
            text=True,
        )
        self.assertEqual(
            result.returncode,
            0,
            f"import livetown failed:\nstdout: {result.stdout}\nstderr: {result.stderr}",
        )


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
        self.assertEqual(line1, "showcase: 1 agents: world. main at deadbee")
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
