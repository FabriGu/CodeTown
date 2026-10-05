import unittest

import focus
import roads as R
from roads import CYCLE, HIGHWAY, ROAD, USED_BY, USES, Roads, half_width, hidden, roundabouts, route, segments
from test_townmap import build


def keys(found):
    return {(r.kind, r.src, r.dst) for r in found}


class RoadsTest(unittest.TestCase):
    def setUp(self):
        self.model, self.rows, self.found, self.town = build()
        self.roads = Roads(self.town, self.model, self.found)

    def test_routes_walk_the_streets_one_tile_at_a_time(self):
        a = self.town.buildings["app/main.py"].front()
        b = self.town.warehouses["yaml"].front()
        path = route(self.town, a, b)
        self.assertEqual((path[0], path[-1]), (a, b))
        self.assertTrue(all(self.town.walkable(*t) for t in path))
        steps = zip(path, path[1:])
        self.assertTrue(all(abs(p[0] - q[0]) + abs(p[1] - q[1]) == 1 for p, q in steps))

    def test_no_route_when_nothing_connects(self):
        corner = (0, self.town.height - 1)
        self.assertIsNone(route(self.town, corner, self.town.buildings["app/main.py"].front()))

    def test_highways_join_districts_along_avenues(self):
        highways = {(r.src, r.dst): r for r in self.roads.always if r.kind == R.HIGHWAY}
        self.assertEqual(sorted(highways), [("app", "core"), ("core", "app")])
        self.assertEqual(highways[("app", "core")].weight, 7)
        for road in highways.values():
            self.assertTrue(all(self.town.kind(*t) in R.HIGHWAY_GROUND for t in road.path))

    def test_problem_roads_always_show_and_plain_roads_wait_for_selection(self):
        always = keys(self.roads.visible())
        self.assertIn((R.CYCLE, "core/loop_a.py", "core/loop_b.py"), always)
        self.assertIn((R.BACKWARDS, "core/notes.py", "app/helper.py"), always)
        self.assertFalse(any(kind == R.ROAD for kind, _, _ in always))
        mine = keys(self.roads.visible(self.town.buildings["app/main.py"]))
        self.assertIn((R.ROAD, "app/main.py", "core/base.py"), mine)
        self.assertIn((R.ROAD, "app/main.py", "flask"), mine)

    def test_a_warehouse_shows_the_roads_of_its_users(self):
        self.assertEqual(keys(self.roads.of(self.town.warehouses["yaml"])),
                         {(R.ROAD, "core/base.py", "yaml")})

    def test_the_two_legs_of_a_loop_take_different_streets(self):
        legs = {(r.src, r.dst): r.path for r in self.roads.always if r.kind == R.CYCLE}
        there = legs[("core/loop_a.py", "core/loop_b.py")]
        back = legs[("core/loop_b.py", "core/loop_a.py")]
        self.assertFalse(set(there[1:-1]) & set(back[1:-1]))

    def test_roads_reach_into_doors_but_highways_end_on_the_avenue(self):
        segs = segments(self.roads.visible())
        loop = next(r for r in self.roads.always if r.kind == R.CYCLE)
        self.assertIn(R.INTO_DOOR, next(d for k, _, d in segs[loop.path[0]] if k == R.CYCLE))
        highway = next(r for r in self.roads.always if r.kind == R.HIGHWAY)
        self.assertEqual(len(next(d for k, _, d in segs[highway.path[0]] if k == R.HIGHWAY)), 1)

    def test_each_cycle_road_gets_a_roundabout_on_its_least_hidden_tile(self):
        spots = roundabouts(self.town, self.roads.always)
        for road in (r for r in self.roads.always if r.kind == R.CYCLE):
            on_road = [t for t in road.path if t in spots]
            self.assertTrue(on_road, road)
            least = min(hidden(self.town, t) for t in road.path)
            self.assertTrue(any(hidden(self.town, t) == least for t in on_road))
            self.assertLess(least, 3)

    def test_more_references_make_wider_roads(self):
        self.assertLess(half_width(R.ROAD, 1), half_width(R.ROAD, 3))
        self.assertLess(half_width(R.HIGHWAY, 1), half_width(R.HIGHWAY, 16))

    def test_a_focus_draws_its_roads_in_its_colours_instead_of_highways(self):
        base = self.town.buildings["core/base.py"]
        seen = keys(self.roads.visible(base, focus.select(self.model, "core/base.py")))
        self.assertIn((USED_BY, "app/main.py", "core/base.py"), seen)
        self.assertIn((USED_BY, "core/tower.py", "core/base.py"), seen)
        self.assertIn((ROAD, "core/base.py", "yaml"), seen)
        self.assertIn((CYCLE, "core/loop_a.py", "core/loop_b.py"), seen)
        self.assertNotIn(HIGHWAY, {kind for kind, _, _ in seen})

    def test_an_import_that_is_a_problem_keeps_its_own_road_in_a_focus(self):
        a = self.town.buildings["core/loop_a.py"]
        seen = keys(self.roads.visible(a, focus.select(self.model, "core/loop_a.py")))
        self.assertIn((CYCLE, "core/loop_a.py", "core/loop_b.py"), seen)
        self.assertNotIn((USES, "core/loop_a.py", "core/loop_b.py"), seen)
        self.assertIn((USED_BY, "app/main.py", "core/loop_a.py"), seen)

    def test_without_a_focus_the_roads_are_as_before(self):
        main = self.town.buildings["app/main.py"]
        kinds = {kind for kind, _, _ in keys(self.roads.visible(main))}
        self.assertIn(HIGHWAY, kinds)
        self.assertFalse({USES, USED_BY} & kinds)
