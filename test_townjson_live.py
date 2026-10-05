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


CLAWD = {"id": "a", "role": "implementer", "team": "world", "scarf": 0, "label": "world · task 1",
         "follow": 1, "tile": [0, 0], "facing": [1, 0], "pose": "idle", "path": [[0, 0]],
         "path_i": 0, "walk_t": 0.0, "flag": None}


def _live(**kw):
    base = {"version": 1, "clawds": {"a": dict(CLAWD)}, "scaffold": {}, "sites": [], "flags": [],
            "status": ["line1", "line2"], "camera": "a"}
    base.update(kw)
    return base


class TickFieldTest(unittest.TestCase):
    def _tick(self, prev, cur):
        msg = townjson.tick_message(prev, cur, 1.0)
        self.assertIsNotNone(msg)
        return msg

    def test_a_pose_change_resends_that_clawd_only(self):
        cur = _live(clawds={"a": {**CLAWD, "pose": "hammer"}})
        msg = self._tick(_live(), cur)
        self.assertEqual(list(msg), ["clawds", "t"])
        self.assertEqual([r["id"] for r in msg["clawds"]], ["a"])
        self.assertEqual(msg["clawds"][0]["pose"], "hammer")

    def test_a_label_change_resends_that_clawd_only(self):
        cur = _live(clawds={"a": {**CLAWD, "label": "new label"}})
        msg = self._tick(_live(), cur)
        self.assertEqual(list(msg), ["clawds", "t"])
        self.assertEqual(msg["clawds"][0]["label"], "new label")

    def test_a_follow_change_resends_that_clawd_only(self):
        cur = _live(clawds={"a": {**CLAWD, "follow": 2}})
        msg = self._tick(_live(), cur)
        self.assertEqual(list(msg), ["clawds", "t"])
        self.assertEqual(msg["clawds"][0]["follow"], 2)

    def test_a_flag_change_resends_that_clawd_only(self):
        cur = _live(clawds={"a": {**CLAWD, "flag": "app/main.py"}})
        msg = self._tick(_live(), cur)
        self.assertEqual(list(msg), ["clawds", "t"])
        self.assertEqual(msg["clawds"][0]["flag"], "app/main.py")

    def test_scaffold_alone(self):
        msg = self._tick(_live(), _live(scaffold={"app/main.py": 3}))
        self.assertEqual(list(msg), ["scaffold", "t"])
        self.assertEqual(msg["scaffold"], {"app/main.py": 3})

    def test_sites_alone(self):
        sites = [{"path": "hub/new.py", "tile": [1, 2], "size": 1, "scarf": 3}]
        msg = self._tick(_live(), _live(sites=sites))
        self.assertEqual(list(msg), ["sites", "t"])
        self.assertEqual(msg["sites"], sites)

    def test_flags_alone(self):
        flags = [{"agent": "a", "building": "app/main.py", "scarf": 3}]
        msg = self._tick(_live(), _live(flags=flags))
        self.assertEqual(list(msg), ["flags", "t"])
        self.assertEqual(msg["flags"], flags)

    def test_status_alone(self):
        msg = self._tick(_live(), _live(status=["new1", "new2"]))
        self.assertEqual(list(msg), ["status", "t"])
        self.assertEqual(msg["status"], ["new1", "new2"])

    def test_camera_alone(self):
        msg = self._tick(_live(), _live(camera="b"))
        self.assertEqual(list(msg), ["camera", "t"])
        self.assertEqual(msg["camera"], "b")


if __name__ == "__main__":
    unittest.main()
