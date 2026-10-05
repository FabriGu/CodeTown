import unittest
from unittest import mock

import crowd
import fixture
import game
import problems
import roads
import survey
import watch
import watch_sites
from events import Agent, Event
from layers import Rows
from plat import Plat
from test_survey import MONOREPO_LIKE
from test_townmap import build as build_town


def _stand(tmap, module, occupied=frozenset()):
    b = tmap.buildings[module]
    return crowd.standing_spot(tmap, b, set(occupied))


def _spots_in_order(tmap, module, count):
    occ: set[tuple[int, int]] = set()
    spots = []
    for _ in range(count):
        spot = _stand(tmap, module, occ)
        spots.append(spot)
        occ.add(spot)
    return spots


def _hall_spots_in_order(tmap, hall, count):
    occ: set[tuple[int, int]] = set()
    spots = []
    for _ in range(count):
        spot = crowd.hall_standing_spot(tmap, hall, occ)
        spots.append(spot)
        occ.add(spot)
    return spots


def _until_idle(c):
    for _ in range(2000):
        if all(cl.pose != "walk" for cl in c.clawds()):
            return
        c.step(0.05)


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
        cl = c.clawds()[0]
        self.assertEqual(cl.pose, "idle")
        facings = set()
        for _ in range(6):
            c.step(1.0)
            facings.add(c.clawds()[0].facing)
        self.assertEqual(facings, {(0, 1), (1, 0)})
        self._apply(c, [Event("edit", _agent(), "core/notes.py", 100.0)], now=100.0)
        self.assertEqual(c.clawds()[0].pose, "walk")
        self.assertEqual(c.clawds()[0].idle_phase, 0.0)

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

    def test_review_tour_repeats_after_full_lap(self):
        c = self._crowd()
        rev = Agent("w1/review-task-1", "reviewer", "world", "w1")
        st = watch.WatchState(reviewer_tours={rev.id: ["app/main.py", "core/notes.py"]})
        self._apply(c, [Event("review_start", rev, None, 0.0)], st)
        while c.clawds()[0].tile != self.hall:
            c.step(0.05)
        first = _stand(self.tmap, "app/main.py")
        second = _stand(self.tmap, "core/notes.py")
        seen_second = False
        back_at_first = False
        for _ in range(3000):
            c.step(0.05)
            cl = c.clawds()[0]
            if cl.tile == second and cl.pose == "idle" and cl.goal_kind == "tour":
                seen_second = True
            if seen_second and cl.tile == first and cl.pose == "idle" and cl.goal_kind == "tour":
                back_at_first = True
                break
        self.assertTrue(seen_second)
        self.assertTrue(back_at_first)
        self.assertEqual(c.clawds()[0].tour, ("app/main.py", "core/notes.py"))
        for _ in range(3000):
            c.step(0.05)
            if c.clawds()[0].tile == second and c.clawds()[0].pose == "idle":
                break
        self.assertEqual(c.clawds()[0].tile, second)

    def test_review_tour_uses_updated_list_on_next_lap(self):
        c = self._crowd()
        rev = Agent("w1/review-task-1", "reviewer", "world", "w1")
        st = watch.WatchState(reviewer_tours={rev.id: ["app/main.py", "core/notes.py"]})
        self._apply(c, [Event("review_start", rev, None, 0.0)], st)
        while c.clawds()[0].tile != self.hall:
            c.step(0.05)
        second = _stand(self.tmap, "core/notes.py")
        helper = _stand(self.tmap, "app/helper.py")
        for _ in range(3000):
            c.step(0.05)
            if c.clawds()[0].tile == second and c.clawds()[0].pose == "idle":
                break
        self._apply(c, [], watch.WatchState(reviewer_tours={rev.id: ["app/helper.py"]}), now=50.0)
        for _ in range(3000):
            c.step(0.05)
            cl = c.clawds()[0]
            if cl.tile == helper and cl.pose == "idle" and cl.goal_kind == "tour":
                break
        self.assertEqual(c.clawds()[0].tile, helper)
        self.assertEqual(c.clawds()[0].tour, ("app/helper.py",))

    def test_review_finish_leaves(self):
        c = self._crowd()
        rev = Agent("w1/review-task-1", "reviewer", "world", "w1")
        self._apply(c, [Event("review_finish", rev, None, 0.0)])
        while c.clawds():
            c.step(0.05)
        self.assertIn(rev.id, c.departed())

    def test_review_finish_walks_to_hall_before_exit(self):
        c = self._crowd()
        rev = Agent("w1/review-task-1", "reviewer", "world", "w1")
        st = watch.WatchState(
            agents=[watch.AgentState(rev, "touring", None)],
            reviewer_tours={rev.id: ["app/main.py"]},
        )
        c.seed(st, {"world": 0})
        start_tile = c.clawds()[0].tile
        self.assertNotEqual(start_tile, self.hall)
        self._apply(c, [Event("review_finish", rev, None, 0.0)], st)
        clawd = c.clawds()[0]
        hall_goal = clawd.path[-1]
        self.assertEqual(clawd.goal_kind, "hall")
        self.assertIn(hall_goal, _hall_spots_in_order(self.tmap, self.hall, 3))
        stood_at_hall = False
        saw_exit = False
        for _ in range(3000):
            if rev.id in c.departed():
                break
            clawd = c.clawds()[0]
            if clawd.tile == hall_goal and clawd.pose == "idle" and clawd.goal_kind == "hall":
                stood_at_hall = True
            if stood_at_hall and clawd.goal_kind == "exit":
                saw_exit = True
                self.assertNotIn(hall_goal, c._standing)
            c.step(0.05)
        self.assertTrue(stood_at_hall)
        self.assertTrue(saw_exit)
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

    def test_leave_clears_sites_for_worktree(self):
        c = self._crowd()
        a = _agent()
        self._apply(c, [Event("create", a, "hub/new.py", 0.0)])
        self.assertIn("hub/new.py", c.effective_sites(watch.WatchState()))
        self._apply(c, [Event("leave", a, None, 1.0)], now=1.0)
        self.assertEqual([], c.effective_sites(watch.WatchState()))

    def test_leave_only_clears_own_worktree_scaffold_and_sites(self):
        c = self._crowd()
        a1 = Agent("w1/task-1", "implementer", "gameplay", "w1")
        a2 = Agent("w2/task-1", "implementer", "gameplay", "w2")
        self._apply(c, [Event("edit", a1, "app/main.py", 0.0)])
        self._apply(c, [Event("create", a2, "hub/new.py", 1.0)], now=1.0)
        st = watch.WatchState()
        self.assertIn("app/main.py", c.effective_scaffold(st))
        self.assertIn("hub/new.py", c.effective_sites(st))
        self._apply(c, [Event("leave", a1, None, 2.0)], now=2.0)
        self.assertNotIn("app/main.py", c.effective_scaffold(st))
        self.assertIn("hub/new.py", c.effective_sites(st))
        self.assertEqual(["w2/task-1"], [cl.agent_id for cl in c.clawds()])

    def test_leave_drops_bare_worktree_id_clawd(self):
        c = self._crowd()
        a = Agent("w1", "implementer", "world", "w1")
        self._apply(c, [Event("start", a, None, 0.0)])
        self.assertEqual(1, len(c.clawds()))
        self._apply(c, [Event("leave", a, None, 1.0)], now=1.0)
        self.assertEqual([], c.clawds())

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

    def test_crowd_three_clawds_same_building_distinct_spots(self):
        c = self._crowd()
        module = "app/main.py"
        agents = [_agent(f"w{i}", f"t{i}") for i in range(1, 4)]
        colours = {a.team: i for i, a in enumerate(agents)}
        self._apply(c, [Event("edit", a, module, 0.0) for a in agents], colours=colours)
        expected = _spots_in_order(self.tmap, module, 3)
        self.assertEqual([cl.path[-1] for cl in c.clawds()], expected)
        _until_idle(c)
        tiles = [cl.tile for cl in c.clawds()]
        self.assertEqual(len(set(tiles)), 3)
        self.assertEqual(set(tiles), set(expected))

    def test_crowd_standing_spots_sequential_arrival(self):
        c = self._crowd()
        module = "core/notes.py"
        a1, a2 = _agent("w1", "t1"), _agent("w2", "t2")
        self._apply(c, [Event("edit", a1, module, 0.0)], colours={"t1": 0})
        _until_idle(c)
        self._apply(c, [Event("edit", a2, module, 1.0)], colours={"t1": 0, "t2": 1}, now=1.0)
        _until_idle(c)
        expected = _spots_in_order(self.tmap, module, 2)
        tiles = sorted((cl.agent_id, cl.tile) for cl in c.clawds())
        self.assertEqual(tiles[0][1], expected[0])
        self.assertEqual(tiles[1][1], expected[1])

    def test_merge_releases_standing_spot_during_hop(self):
        c = self._crowd()
        module = "app/main.py"
        a1, a2 = _agent("w1", "t1"), _agent("w2", "t2")
        self._apply(c, [Event("edit", a1, module, 0.0)], colours={"t1": 0})
        first_spot = c.clawds()[0].path[-1]
        self._apply(c, [Event("merge", a1, None, 1.0)], colours={"t1": 0}, now=1.0)
        self.assertEqual(c.clawds()[0].pose, "hop")
        self.assertNotIn(first_spot, c._standing)
        self._apply(c, [Event("edit", a2, module, 1.0)], colours={"t1": 0, "t2": 1}, now=1.0)
        self.assertEqual(
            next(cl.path[-1] for cl in c.clawds() if cl.agent_id == a2.id), first_spot)

    def test_retown_during_hop_does_not_re_reserve_building(self):
        c = self._crowd()
        module = "app/main.py"
        a1, a2 = _agent("w1", "t1"), _agent("w2", "t2")
        self._apply(c, [Event("edit", a1, module, 0.0)], colours={"t1": 0})
        first_spot = c.clawds()[0].path[-1]
        self._apply(c, [Event("merge", a1, None, 1.0)], now=1.0)
        c.retown(self.tmap, self.roads, self.model, self.tracked, self.hall)
        self.assertNotIn(first_spot, c._reservations.values())
        self._apply(c, [Event("edit", a2, module, 2.0)], colours={"t1": 0, "t2": 1}, now=2.0)
        self.assertEqual(
            next(cl.path[-1] for cl in c.clawds() if cl.agent_id == a2.id), first_spot)

    def test_hall_standing_spots_distinct_on_start(self):
        c = self._crowd()
        agents = [_agent(f"w{i}", f"t{i}") for i in range(1, 4)]
        colours = {a.team: i for i, a in enumerate(agents)}
        self._apply(c, [Event("start", a, None, 0.0) for a in agents], colours=colours)
        expected = _hall_spots_in_order(self.tmap, self.hall, 3)
        self.assertEqual([cl.path[-1] for cl in c.clawds()], expected)
        _until_idle(c)
        tiles = [cl.tile for cl in c.clawds()]
        self.assertEqual(len(set(tiles)), 3)
        self.assertEqual(tiles[0], self.hall)

    def test_seed_hall_standing_spots_distinct(self):
        c = self._crowd()
        st = watch.WatchState(agents=[
            watch.AgentState(_agent("w1", "t1"), "waiting", None),
            watch.AgentState(_agent("w2", "t2"), "waiting", None),
            watch.AgentState(Agent("orch", "orchestrator", None, None), "idle", None),
        ])
        c.seed(st, {"t1": 0, "t2": 1})
        expected = _hall_spots_in_order(self.tmap, self.hall, 3)
        tiles = sorted(cl.tile for cl in c.clawds())
        self.assertEqual(len(set(tiles)), 3)
        self.assertEqual(set(tiles), set(expected))
        self.assertIn(self.hall, tiles)

    def test_crowd_standing_spot_released_and_reused(self):
        c = self._crowd()
        module = "app/main.py"
        agents = [_agent(f"w{i}", f"t{i}") for i in range(1, 4)]
        colours = {a.team: i for i, a in enumerate(agents)}
        self._apply(c, [Event("edit", a, module, 0.0) for a in agents], colours=colours)
        _until_idle(c)
        first_spot = _spots_in_order(self.tmap, module, 1)[0]
        self.assertEqual(
            next(cl.tile for cl in c.clawds() if cl.agent_id == agents[0].id), first_spot)
        self._apply(c, [Event("leave", agents[0], None, 1.0)], now=1.0)
        newcomer = _agent("w4", "t4")
        self._apply(c, [Event("edit", newcomer, module, 2.0)],
                     colours={**colours, "t4": 3}, now=2.0)
        self.assertEqual(c.clawds()[-1].path[-1], first_spot)

    def test_no_building_file_nearest_no_scaffold(self):
        c = self._crowd()
        path = "web/extra/data.json"
        self._apply(c, [Event("edit", _agent(), path, 0.0)])
        sc = c.effective_scaffold(watch.WatchState())
        self.assertEqual(sc, {})
        nb = watch.nearest_building(path, self.model)
        if nb not in self.tmap.buildings:
            nb = None
            best_len = -1
            for mid in self.tmap.buildings:
                mod = self.model.modules[mid]
                for candidate in [mid] + list(mod.members):
                    folder = candidate.rsplit("/", 1)[0] + "/" if "/" in candidate else ""
                    if path.startswith(folder) and len(folder) > best_len:
                        nb, best_len = mid, len(folder)
        expected = _stand(self.tmap, nb) if nb else self.hall
        self.assertEqual(c.clawds()[0].path[-1], expected)

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

    def test_mid_build_seed_waiting_implementer_with_flag(self):
        c = self._crowd()
        st = watch.WatchState(
            agents=[watch.AgentState(_agent(), "waiting", None)],
            flags={"w1": "app/main.py"},
        )
        c.seed(st, {"world": 0})
        impl = next(x for x in c.clawds() if x.role == "implementer")
        self.assertEqual(impl.tile, self.hall)
        self.assertTrue(impl.at_hall)
        self.assertEqual(impl.flag_building, "app/main.py")

    def test_mid_build_seed_reviewer_on_tour(self):
        c = self._crowd()
        rev = Agent("w1/review-task-1", "reviewer", "world", "w1")
        tour = ["app/main.py", "core/notes.py"]
        st = watch.WatchState(
            agents=[watch.AgentState(rev, "touring", None)],
            reviewer_tours={rev.id: tour},
        )
        c.seed(st, {"world": 0})
        rev_clawd = next(x for x in c.clawds() if x.role == "reviewer")
        self.assertEqual(rev_clawd.tour, tuple(tour))
        self.assertEqual(rev_clawd.tile, _stand(self.tmap, tour[0]))
        self.assertEqual(rev_clawd.goal_kind, "tour")
        self.assertEqual(rev_clawd.reserved_tile, rev_clawd.tile)


def _ref_hall_standing_spot(tmap, hall, occupied):
    hx, hy = hall
    order = [hall]
    for dist in range(1, tmap.width + tmap.height):
        ring = []
        for dx in range(-dist, dist + 1):
            for dy in (-dist, dist):
                ring.append((hx + dx, hy + dy))
            for dy in range(-dist + 1, dist):
                ring.append((hx + dist, hy + dy))
                ring.append((hx - dist, hy + dy))
        for tile in ring:
            if tmap.walkable(*tile) and tile not in order:
                order.append(tile)
    order.sort(key=lambda t: (abs(t[0] - hx) + abs(t[1] - hy), t[1], t[0]))
    for tile in order:
        if tile not in occupied:
            return tile
    return order[0]


def _ref_standing_spot(tmap, building, occupied):
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


def _ref_hall_candidates(tmap, hall):
    hx, hy = hall
    order = [hall]
    for dist in range(1, tmap.width + tmap.height):
        ring = []
        for dx in range(-dist, dist + 1):
            for dy in (-dist, dist):
                ring.append((hx + dx, hy + dy))
            for dy in range(-dist + 1, dist):
                ring.append((hx + dist, hy + dy))
                ring.append((hx - dist, hy + dy))
        for tile in ring:
            if tmap.walkable(*tile) and tile not in order:
                order.append(tile)
    order.sort(key=lambda t: (abs(t[0] - hx) + abs(t[1] - hy), t[1], t[0]))
    return order


def _ref_building_candidates(tmap, building):
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
    return order


def _monorepo_tmap(test):
    root = fixture.make_repo(test, MONOREPO_LIKE)
    model = survey.survey(root)
    rows = Rows().update(model)
    plat = Plat().update(model, rows)
    found = problems.find(model, rows)
    from townmap import TownMap
    return TownMap(model, plat, rows, found)


class StandingSpotEquivalenceTest(unittest.TestCase):
    def _towns(self):
        _, _, _, showcase = build_town()
        yield showcase
        yield _monorepo_tmap(self)

    def _occupied_sets(self, candidates):
        yield set()
        for k in range(1, min(13, len(candidates))):
            yield set(candidates[:k])
        yield set(candidates)

    def test_hall_standing_spot_matches_reference(self):
        for tmap in self._towns():
            hall = crowd.town_hall_tile(tmap)
            candidates = _ref_hall_candidates(tmap, hall)
            for occupied in self._occupied_sets(candidates):
                with self.subTest(town=tmap.model.repo, occupied=len(occupied)):
                    self.assertEqual(
                        crowd.hall_standing_spot(tmap, hall, occupied),
                        _ref_hall_standing_spot(tmap, hall, occupied))

    def test_standing_spot_matches_reference(self):
        for tmap in self._towns():
            for building in tmap.buildings.values():
                candidates = _ref_building_candidates(tmap, building)
                for occupied in self._occupied_sets(candidates):
                    with self.subTest(module=building.module, occupied=len(occupied)):
                        self.assertEqual(
                            crowd.standing_spot(tmap, building, occupied),
                            _ref_standing_spot(tmap, building, occupied))

    def test_free_hall_spot_nearby_uses_few_walkable_calls(self):
        _, _, _, tmap = build_town()
        hall = crowd.town_hall_tile(tmap)
        calls = []
        real = tmap.walkable

        def counting(x, y):
            calls.append((x, y))
            return real(x, y)

        with mock.patch.object(tmap, "walkable", side_effect=counting):
            crowd.hall_standing_spot(tmap, hall, set())
        self.assertLess(len(calls), 100)

    def test_free_standing_spot_nearby_uses_few_walkable_calls(self):
        _, _, _, tmap = build_town()
        building = next(iter(tmap.buildings.values()))
        calls = []
        real = tmap.walkable

        def counting(x, y):
            calls.append((x, y))
            return real(x, y)

        with mock.patch.object(tmap, "walkable", side_effect=counting):
            crowd.standing_spot(tmap, building, set())
        self.assertLess(len(calls), 100)


if __name__ == "__main__":
    unittest.main()
