import copy
import unittest
from unittest import mock

import drawtown
import fixture
import viewer
import watch
import watch_ui
from events import Agent, Event
from model import Module
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

    def _resurvey_payload(self, model):
        from layers import Rows
        from plat import Plat
        rows = Rows(dict(self.rows.districts), dict(self.rows.modules)).update(model)
        plat = Plat({n: copy.deepcopy(d) for n, d in self.plat.districts.items()},
                    list(self.plat.harbor)).update(model, rows)
        return model, rows, plat

    def _viewer(self, runner):
        w = watch.Watch(self.main, survey_dir=self.survey)
        return viewer.WatchViewer(
            self.tmap, self.roads, self.model, self.rows, self.plat,
            "demo", "abc1234", self.survey, self.main, w,
            resurvey_runner=runner), w

    def test_runs_once_while_inflight(self):
        queued = []
        v, w = self._viewer(lambda fn: queued.append(fn))
        st = watch.WatchState(main_moved_clean=True, main_tip="abc1234")
        v.ingest(viewer.WatchSnapshot([], st))
        v.ingest(viewer.WatchSnapshot([], st))
        self.assertEqual(len(queued), 1)
        w.close()

    def test_mid_merge_skips_resurvey(self):
        calls = []
        v, w = self._viewer(lambda fn: calls.append(1) or fn())
        v.ingest(viewer.WatchSnapshot([], watch.WatchState(
            main_moved_clean=True, main_mid_merge=True, main_tip="abc1234")))
        self.assertEqual(calls, [])
        w.close()

    def test_failure_keeps_old_town(self):
        v, w = self._viewer(lambda fn: fn())
        old_modules = set(v.m.buildings)
        st = watch.WatchState(main_moved_clean=True, main_tip="abc1234")
        with mock.patch("viewer.resurvey_main", side_effect=RuntimeError("disk full")):
            v.ingest(viewer.WatchSnapshot([], st))
        self.assertEqual(set(v.m.buildings), old_modules)
        self.assertEqual(v._resurvey_error, "disk full")
        w.close()

    def test_failure_retries_only_on_new_main_tip(self):
        v, w = self._viewer(lambda fn: fn())
        st = watch.WatchState(main_moved_clean=True, main_tip="tipaaaa")
        with mock.patch("viewer.resurvey_main", side_effect=RuntimeError("disk full")):
            v.ingest(viewer.WatchSnapshot([], st))
        calls = []
        with mock.patch("viewer.resurvey_main", side_effect=lambda *a: calls.append(1)):
            v.ingest(viewer.WatchSnapshot([], watch.WatchState(
                main_moved_clean=True, main_tip="tipaaaa")))
        self.assertEqual(calls, [])
        with mock.patch("viewer.resurvey_main",
                        return_value=self._resurvey_payload(self.model)):
            v.ingest(viewer.WatchSnapshot([], watch.WatchState(
                main_moved_clean=True, main_tip="tipbbbb")))
        self.assertIsNone(v._resurvey_error)
        w.close()

    def test_success_retowns_without_resetting_clawds(self):
        v, w = self._viewer(lambda fn: fn())
        a = Agent("w1/task-1", "implementer", "world", "w1")
        v.ingest(viewer.WatchSnapshot([Event("start", a, None, 0.0)], watch.WatchState()))
        ids_before = {c.agent_id for c in v._crowd.clawds()}
        st = watch.WatchState(main_moved_clean=True, main_tip="abc1234")
        with mock.patch("viewer.resurvey_main",
                        return_value=self._resurvey_payload(self.model)):
            v.ingest(viewer.WatchSnapshot([], st))
        self.assertIsNone(v._resurvey_error)
        self.assertEqual(ids_before, {c.agent_id for c in v._crowd.clawds()})
        w.close()

    def test_line1_shows_resurvey_error(self):
        v, w = self._viewer(lambda fn: fn())
        v._resurvey_error = "disk full"
        line = watch_ui.line1("x", v._latest_state, "tip", 0, resurvey_error=v._resurvey_error)
        self.assertEqual(line, "couldn't re-survey main: disk full")
        w.close()

    def test_new_buildings_drop_then_expire(self):
        new_model = type(self.model)(repo=self.model.repo, modules=dict(self.model.modules),
                                     edges=dict(self.model.edges),
                                     externals=dict(self.model.externals),
                                     renames=dict(self.model.renames))
        new_model.modules["hub/new.py"] = Module(
            "hub/new.py", "hub", "source", loc=10, complexity=1, exports=["run"])
        v, w = self._viewer(lambda fn: fn())
        st = watch.WatchState(main_moved_clean=True, main_tip="deadbeef")
        with mock.patch("viewer.resurvey_main",
                        return_value=self._resurvey_payload(new_model)):
            v.ingest(viewer.WatchSnapshot([], st))
        self.assertIn("hub/new.py", v._drops)
        self.assertTrue(v.moving())
        v.t = v._drops["hub/new.py"] + drawtown.DROP_TIME + 0.01
        self.assertFalse(v.moving())
        w.close()

    def test_merge_summary_before_and_after_resurvey(self):
        branch = "team/world/demo"
        queued = []
        v, w = self._viewer(lambda fn: queued.append(fn))
        a = Agent("w1/task-1", "implementer", "world", "w1")
        ev = Event("merge", a, None, 0.0)
        st = watch.WatchState(main_moved_clean=True, main_tip="deadbeef",
                              worktree_branches={"w1": branch})
        v.ingest(viewer.WatchSnapshot([ev], st))
        self.assertEqual(v.status(80)[1].strip(), f"merged {branch}")
        new_model = type(self.model)(repo=self.model.repo, modules=dict(self.model.modules),
                                     edges=dict(self.model.edges),
                                     externals=dict(self.model.externals),
                                     renames=dict(self.model.renames))
        new_model.modules["hub/new.py"] = Module(
            "hub/new.py", "hub", "source", loc=10, complexity=1, exports=["run"])
        changed = new_model.modules["app/main.py"]
        new_model.modules["app/main.py"] = Module(
            changed.id, changed.district, changed.kind, loc=changed.loc + 1,
            complexity=changed.complexity, exports=changed.exports)
        with mock.patch("viewer.resurvey_main",
                        return_value=self._resurvey_payload(new_model)):
            queued[0]()
            v._drain_resurvey()
        self.assertEqual(v.status(80)[1].strip(),
                         "merged team/world/demo: 1 new building, 1 changed")
        w.close()

    def test_merge_summary_plural_new_buildings_unchanged_changed(self):
        branch = "team/world/demo"
        queued = []
        v, w = self._viewer(lambda fn: queued.append(fn))
        a = Agent("w1/task-1", "implementer", "world", "w1")
        ev = Event("merge", a, None, 0.0)
        st = watch.WatchState(main_moved_clean=True, main_tip="deadbeef",
                              worktree_branches={"w1": branch})
        v.ingest(viewer.WatchSnapshot([ev], st))
        new_model = type(self.model)(repo=self.model.repo, modules=dict(self.model.modules),
                                     edges=dict(self.model.edges),
                                     externals=dict(self.model.externals),
                                     renames=dict(self.model.renames))
        for name in ("hub/new_a.py", "hub/new_b.py"):
            new_model.modules[name] = Module(
                name, "hub", "source", loc=10, complexity=1, exports=["run"])
        for mid in ("app/main.py", "app/helper.py"):
            m = new_model.modules[mid]
            new_model.modules[mid] = Module(
                m.id, m.district, m.kind, loc=m.loc + 1,
                complexity=m.complexity, exports=m.exports)
        with mock.patch("viewer.resurvey_main",
                        return_value=self._resurvey_payload(new_model)):
            queued[0]()
            v._drain_resurvey()
        self.assertEqual(v.status(80)[1].strip(),
                         "merged team/world/demo: 2 new buildings, 2 changed")
        w.close()

    def test_main_move_summary_before_and_after_resurvey(self):
        queued = []
        v, w = self._viewer(lambda fn: queued.append(fn))
        ev = Event("merge", None, None, 0.0)
        st = watch.WatchState(main_moved_clean=True, main_tip="deadbeef")
        v.ingest(viewer.WatchSnapshot([ev], st))
        self.assertEqual(v.status(80)[1].strip(), "main moved to deadbee")
        new_model = type(self.model)(repo=self.model.repo, modules=dict(self.model.modules),
                                     edges=dict(self.model.edges),
                                     externals=dict(self.model.externals),
                                     renames=dict(self.model.renames))
        new_model.modules["hub/new.py"] = Module(
            "hub/new.py", "hub", "source", loc=10, complexity=1, exports=["run"])
        with mock.patch("viewer.resurvey_main",
                        return_value=self._resurvey_payload(new_model)):
            queued[0]()
            v._drain_resurvey()
        self.assertEqual(v.status(80)[1].strip(),
                         "main moved to deadbee: 1 new building")
        w.close()

    def test_note_resurvey_handoff_to_watch(self):
        notes = []
        w = watch.Watch(self.main, survey_dir=self.survey)
        v = viewer.WatchViewer(
            self.tmap, self.roads, self.model, self.rows, self.plat,
            "demo", "abc1234", self.survey, self.main, w,
            resurvey_runner=lambda fn: fn(),
            note_resurvey=lambda model, tip: notes.append((model, tip)))
        st = watch.WatchState(main_moved_clean=True, main_tip="deadbeef")
        with mock.patch("viewer.resurvey_main",
                        return_value=self._resurvey_payload(self.model)):
            v.ingest(viewer.WatchSnapshot([], st))
        self.assertEqual(len(notes), 1)
        self.assertIs(notes[0][0], self.model)
        self.assertEqual(notes[0][1], "deadbeef")
        w.close()


class WatchStateTipTest(unittest.TestCase):
    def test_state_includes_main_tip_and_worktree_branches(self):
        main = fixture.make_repo(self, MONOREPO_LIKE)
        survey = temp_survey(self)
        w = watch.Watch(main, survey_dir=survey)
        st = w.state()
        self.assertTrue(st.main_tip)
        self.assertIsInstance(st.worktree_branches, dict)
        w.close()
