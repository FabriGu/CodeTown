import unittest

import crowd
import drawtown
import iso
import labels
import roads
import watch
import watch_ui
from events import Agent, Event
from test_townmap import build as build_town


def _overlay_cells(overlays):
    cells = set()
    for ov in overlays:
        col = int(round(ov.x * 2))
        for i in range(len(ov.text)):
            cells.add((col + i, ov.y))
    return cells


def _crowd(tmap, model, found):
    hall = crowd.town_hall_tile(tmap)
    return crowd.Crowd(tmap, roads.Roads(tmap, model, found), model, set(model.modules), hall,
                       watch.FakeClock())


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

    def test_line2_merge_branch(self):
        ev = Event("merge", Agent("w1/t1", "implementer", "world", "w1"), None, 0.0)
        st = watch.WatchState()
        self.assertEqual(
            watch_ui.line2(ev, st, "game-web",
                           merge_line2="merged team/world/w2-corridors: 4 new buildings, 9 changed"),
            "merged team/world/w2-corridors: 4 new buildings, 9 changed")

    def test_line2_merge_main_move(self):
        ev = Event("merge", None, None, 0.0)
        st = watch.WatchState()
        self.assertEqual(
            watch_ui.line2(ev, st, "game-web",
                           merge_line2="main moved to cab317f: 4 new buildings, 9 changed"),
            "main moved to cab317f: 4 new buildings, 9 changed")

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

    def test_agent_label_bare_worktree_id(self):
        impl = Agent("w2-04-A", "implementer", "characters", "w2-04-A")
        self.assertEqual(watch_ui.agent_label(impl, "implementer", "characters", (926, 59), None),
                         "characters · w2-04-A  +926 −59")

    def test_agent_label_team_equals_worktree(self):
        impl = Agent("solo-wt", "implementer", "solo-wt", "solo-wt")
        self.assertEqual(watch_ui.agent_label(impl, "implementer", "solo-wt", (10, 2), None),
                         "solo-wt  +10 −2")

    def test_line2_edit_bare_worktree(self):
        ev = Event("edit", Agent("w2-04-A", "implementer", "characters", "w2-04-A"),
                   "src/foo.py", 0.0)
        self.assertEqual(watch_ui.line2(ev, watch.WatchState(), "repo"),
                         "characters w2-04-A edited src/foo.py")

    def test_line2_edit_team_equals_worktree(self):
        ev = Event("edit", Agent("solo-wt", "implementer", "solo-wt", "solo-wt"),
                   "src/foo.py", 0.0)
        self.assertEqual(watch_ui.line2(ev, watch.WatchState(), "repo"),
                         "solo-wt edited src/foo.py")

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

    def test_agent_label_review_fix1(self):
        rev = Agent("w2-world/review-fix1", "reviewer", "world", "w2-world")
        self.assertEqual(watch_ui.agent_label(rev, "reviewer", "world", (0, 0), None),
                         "review · world fix1")

    def test_clawd_and_hall_labels_share_scene_space(self):
        model, rows, found, tmap = build_town()
        hall = crowd.town_hall_tile(tmap)
        c = _crowd(tmap, model, found)
        a = Agent("w1/task-1", "implementer", "world", "w1")
        c.apply([Event("start", a, None, 0.0)], watch.WatchState(), {"world": 0}, 0.0)
        c.clawds()[0].tile = hall
        scene = drawtown.TownScene.whole(tmap, visible=())
        reqs = watch_ui.label_requests(
            c, crowd.CameraDirector(__import__("camera").Camera((0, 0)), c, tmap),
            scene, watch.WatchState(), {"world": 0}, (0.0, 0.0), "district")
        clawd_req, hall_req = reqs[0], reqs[1]
        self.assertAlmostEqual(clawd_req.anchor_x, hall_req.anchor_x, delta=2)
        self.assertAlmostEqual(clawd_req.anchor_y, hall_req.anchor_y,
                               delta=iso.HALF_H + watch_ui._CLAWD_LABEL_LIFT)

    def test_labels_avoid_clawd_sprite_cells(self):
        model, rows, found, tmap = build_town()
        c = _crowd(tmap, model, found)
        for i in range(3):
            a = Agent(f"w{i}/task-1", "implementer", "world", f"w{i}")
            c.apply([Event("start", a, None, float(i))], watch.WatchState(),
                    {"world": 0}, float(i))
        b = tmap.buildings["app/main.py"]
        for clawd in c.clawds():
            clawd.tile = b.door()
        scene = drawtown.TownScene.whole(tmap, visible=())
        focus_x, _ = scene.centre_px(b)
        st = watch.WatchState(scaffolded={"app/main.py": "world", "core/tower.py": "world"})
        reqs = watch_ui.label_requests(
            c, crowd.CameraDirector(__import__("camera").Camera((focus_x, 0)), c, tmap),
            scene, st, {"world": 0}, (focus_x, 0), "street",
            scaffolded=c.effective_scaffold(st))
        taken = watch_ui.clawd_taken_cells(scene, c.clawds(), {"world": 0})
        overlays = labels.place(reqs, scene.fb.w, scene.fb.h, taken)
        self.assertTrue(overlays)
        overlap = _overlay_cells(overlays) & taken
        self.assertFalse(overlap, f"labels overlap clawd cells: {overlap}")

    def test_scaffold_labels_ranked_by_scene_camera(self):
        model, rows, found, tmap = build_town()
        c = _crowd(tmap, model, found)
        scene = drawtown.TownScene.whole(tmap, visible=())
        near, far = "app/main.py", "core/tower.py"
        focus_x, _ = scene.centre_px(scene.m.buildings[near])
        st = watch.WatchState(scaffolded={near: "world", far: "world"})
        reqs = watch_ui.label_requests(
            c, crowd.CameraDirector(__import__("camera").Camera((focus_x, 0)), c, tmap),
            scene, st, {"world": 0}, (focus_x, 0), "street",
            scaffolded=c.effective_scaffold(st))
        building_labels = [r.text for r in reqs if r.text.startswith("●")]
        self.assertEqual(len(building_labels), 2)
        self.assertIn(labels.shorten(near), building_labels[0])
        self.assertIn(labels.shorten(far), building_labels[1])

    def test_label_order_and_taken_cells(self):
        model, rows, found, tmap = build_town()
        c = _crowd(tmap, model, found)
        a = Agent("w1/task-1", "implementer", "world", "w1")
        c.apply([Event("start", a, None, 0.0)], watch.WatchState(), {"world": 0}, 0.0)
        st = watch.WatchState(scaffolded={"app/main.py": "world", "core/notes.py": "world"})
        scene = drawtown.TownScene.whole(tmap, visible=())
        focus_x, _ = scene.centre_px(scene.m.buildings["app/main.py"])
        reqs = watch_ui.label_requests(
            c, crowd.CameraDirector(__import__("camera").Camera((focus_x, 0)), c, tmap),
            scene, st, {"world": 0}, (focus_x, 0), "street",
            scaffolded=c.effective_scaffold(st))
        texts = [r.text for r in reqs]
        self.assertTrue(texts[0].startswith("world"))
        self.assertEqual(texts[1], "Town Hall")
        building_labels = [t for t in texts[2:] if t.startswith("●")]
        self.assertLessEqual(len(building_labels), 8)
        taken = watch_ui.clawd_taken_cells(scene, c.clawds(), {"world": 0})
        labels.place(reqs, scene.fb.w, scene.fb.h, taken)
