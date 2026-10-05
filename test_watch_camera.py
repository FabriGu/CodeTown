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

    def _advance_crowd(self, c, to: float):
        dt = to - c._now
        if dt > 0:
            c.step(dt)

    def test_auto_waits_four_seconds(self):
        cam, c, d = self._setup()
        a1 = Agent("w1/task-1", "implementer", "world", "w1")
        a2 = Agent("w2/task-1", "implementer", "render", "w2")
        st = watch.WatchState()
        ev1 = Event("edit", a1, "app/main.py", 0.0)
        c.apply([ev1], st, {"world": 0, "render": 1}, 0.0)
        d.apply_events([ev1], 0.0)
        d.step(0.0, 0.0)
        self.assertEqual(d._auto_agent, a1.id)
        ev2 = Event("edit", a2, "core/notes.py", 0.5)
        c.apply([ev2], st, {"world": 0, "render": 1}, 0.5)
        self._advance_crowd(c, 0.5)
        d.apply_events([ev2], 0.5)
        self._advance_crowd(c, 3.0)
        d.step(0.0, 3.0)
        self.assertEqual(d._auto_agent, a1.id)
        self._advance_crowd(c, 4.5)
        d.step(0.0, 4.5)
        self.assertEqual(d._auto_agent, a2.id)
        a2_focus = crowd.clawd_focus_px(self.tmap, c._clawds[a2.id])
        self.assertEqual(list(cam.target), list(a2_focus))

    def test_auto_picks_newest_same_priority_after_stay(self):
        cam, c, d = self._setup()
        a1 = Agent("w1/task-1", "implementer", "world", "w1")
        a2 = Agent("w2/task-1", "implementer", "render", "w2")
        st = watch.WatchState()
        colours = {"world": 0, "render": 1}
        c.apply([Event("start", a1, None, 0.0), Event("start", a2, None, 0.0)],
                st, colours, 0.0)
        ev1 = Event("edit", a1, "app/main.py", 1.0)
        c.apply([ev1], st, colours, 1.0)
        d.apply_events([ev1], 1.0)
        d.step(0.0, 1.0)
        self.assertEqual(d._auto_agent, a1.id)
        ev2 = Event("edit", a2, "core/notes.py", 2.0)
        c.apply([ev2], st, colours, 2.0)
        self._advance_crowd(c, 2.0)
        d.apply_events([ev2], 2.0)
        self._advance_crowd(c, 4.0)
        d.step(0.0, 4.0)
        self.assertEqual(d._auto_agent, a1.id)
        self._advance_crowd(c, 5.1)
        d.step(0.0, 5.1)
        self.assertEqual(d._auto_agent, a2.id)

    def test_edit_beats_finish_after_stay(self):
        cam, c, d = self._setup()
        fin = Agent("w1/task-1", "implementer", "world", "w1")
        ed = Agent("w2/task-1", "implementer", "render", "w2")
        st = watch.WatchState()
        colours = {"world": 0, "render": 1}
        c.apply([Event("start", fin, None, 0.0), Event("start", ed, None, 0.0)],
                st, colours, 0.0)
        c.apply([Event("finish", fin, None, 0.0)], st, colours, 0.0)
        d.apply_events([Event("finish", fin, None, 0.0)], 0.0)
        d.step(0.0, 0.0)
        ev = Event("edit", ed, "app/main.py", 4.1)
        c.apply([ev], st, colours, 4.1)
        d.apply_events([ev], 4.1)
        d.step(0.0, 4.1)
        self.assertEqual(d._auto_agent, ed.id)

    def test_lower_priority_never_steals_inside_stay(self):
        cam, c, d = self._setup()
        ed = Agent("w1/task-1", "implementer", "world", "w1")
        fin = Agent("w2/task-1", "implementer", "render", "w2")
        st = watch.WatchState()
        colours = {"world": 0, "render": 1}
        c.apply([Event("start", ed, None, 0.0), Event("start", fin, None, 0.0)],
                st, colours, 0.0)
        c.apply([Event("edit", ed, "app/main.py", 0.0)], st, colours, 0.0)
        d.apply_events([Event("edit", ed, "app/main.py", 0.0)], 0.0)
        d.step(0.0, 0.0)
        held = list(cam.target)
        c.apply([Event("finish", fin, None, 1.0)], st, colours, 1.0)
        d.apply_events([Event("finish", fin, None, 1.0)], 1.0)
        self._advance_crowd(c, 1.0)
        d.step(0.0, 1.0)
        self.assertEqual(list(cam.target), held)

    def test_follow_holds_until_zero(self):
        cam, c, d = self._setup()
        agent = Agent("w1/task-1", "implementer", "world", "w1")
        st = watch.WatchState()
        c.apply([Event("start", agent, None, 0.0)], st, {"world": 0}, 0.0)
        d.press("1")
        d.step(0.0, 0.0)
        held = list(cam.target)
        c.apply([Event("edit", Agent("w2/task-1", "implementer", "x", "w2"),
                       "hub/records.py", 10.0)], st, {"world": 0, "x": 1}, 10.0)
        d.apply_events([Event("edit", Agent("w2/task-1", "implementer", "x", "w2"),
                                "hub/records.py", 10.0)], 10.0)
        self._advance_crowd(c, 10.0)
        d.step(0.0, 10.0)
        self.assertEqual(list(cam.target), held)
        d.press("0")
        self.assertEqual(d.mode, "auto")

    def test_follow_returns_auto_on_departure(self):
        cam, c, d = self._setup()
        agent = Agent("w1/task-1", "implementer", "world", "w1")
        other = Agent("w2/task-1", "implementer", "render", "w2")
        st = watch.WatchState()
        colours = {"world": 0, "render": 1}
        c.apply([Event("start", agent, None, 0.0), Event("start", other, None, 0.0)],
                st, colours, 0.0)
        ev = Event("edit", other, "core/notes.py", 0.0)
        c.apply([ev], st, colours, 0.0)
        d.apply_events([ev], 0.0)
        d.step(0.0, 0.0)
        d.press("1")
        d.step(0.0, 1.0)
        follow_target = list(cam.target)
        self.assertEqual(d.mode, "follow")
        c.apply([Event("merge", agent, None, 11.0)], st, colours, 11.0)
        while agent.id not in c.departed():
            c.step(0.05)
        self._advance_crowd(c, 12.0)
        d.step(0.0, 12.0)
        self.assertEqual(d.mode, "auto")
        self.assertEqual(d._auto_agent, other.id)
        self.assertNotEqual(list(cam.target), follow_target)

    def test_pending_clears_after_stay_picks_best_new_events(self):
        cam, c, d = self._setup()
        a1 = Agent("w1/task-1", "implementer", "world", "w1")
        a2 = Agent("w2/task-1", "implementer", "render", "w2")
        a3 = Agent("w3/task-1", "implementer", "core", "w3")
        st = watch.WatchState()
        colours = {"world": 0, "render": 1, "core": 2}
        for a in (a1, a2, a3):
            c.apply([Event("start", a, None, 0.0)], st, colours, 0.0)
        c.apply([Event("edit", a1, "app/main.py", 0.0)], st, colours, 0.0)
        d.apply_events([Event("edit", a1, "app/main.py", 0.0)], 0.0)
        d.step(0.0, 0.0)
        self.assertEqual(d._auto_agent, a1.id)
        for t, agent, path in ((1.0, a2, "core/notes.py"), (2.0, a3, "core/tower.py"),
                               (3.0, a2, "app/helper.py")):
            ev = Event("edit", agent, path, t)
            c.apply([ev], st, colours, t)
            d.apply_events([ev], t)
        self._advance_crowd(c, 4.1)
        d.step(0.0, 4.1)
        self.assertEqual(d._auto_agent, a2.id)
        d.apply_events([Event("edit", a3, "core/broken.py", 5.0)], 5.0)
        self._advance_crowd(c, 8.2)
        d.step(0.0, 8.2)
        self.assertEqual(d._auto_agent, a3.id)
        self.assertEqual(d._pending, {})
