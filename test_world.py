import unittest
from collections import deque

import world


def reachable_from(w, start):
    seen = {start}
    queue = deque([start])
    while queue:
        x, y = queue.popleft()
        for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if (nx, ny) not in seen and not w.blocked(nx, ny):
                seen.add((nx, ny))
                queue.append((nx, ny))
    return seen


class MapTest(unittest.TestCase):
    def setUp(self):
        self.w = world.load()

    def test_map_rows_are_rectangular(self):
        self.assertEqual({len(r) for r in world.MAP}, {self.w.width})
        self.assertEqual(len(world.MAP), self.w.height)

    def test_player_starts_on_walkable_path(self):
        x, y = self.w.start
        self.assertFalse(self.w.blocked(x, y))
        self.assertEqual(self.w.ground(x, y), "path")

    def test_trees_buildings_water_and_edges_block(self):
        self.assertTrue(self.w.blocked(0, 0))       # tree
        self.assertTrue(self.w.blocked(3, 3))       # building 1
        self.assertTrue(self.w.blocked(18, 11))     # pond
        self.assertTrue(self.w.blocked(-1, 5))
        self.assertTrue(self.w.blocked(self.w.width, 0))

    def test_grass_and_path_are_walkable(self):
        self.assertFalse(self.w.blocked(1, 1))
        self.assertFalse(self.w.blocked(3, 6))

    def test_flower_tiles_are_flowers_on_the_ground(self):
        self.assertEqual(self.w.ground(3, 1), "flowers")
        self.assertFalse(self.w.blocked(3, 1))


class BuildingTest(unittest.TestCase):
    def setUp(self):
        self.w = world.load()

    def test_building_footprint_comes_from_map_digits(self):
        b = self.w.buildings["1"]
        self.assertEqual((b.x0, b.y0, b.x1, b.y1), (2, 2, 5, 4))
        self.assertIs(self.w.building_at(4, 3), b)
        self.assertIsNone(self.w.building_at(6, 3))

    def test_every_door_opens_onto_a_tile_reachable_from_start(self):
        reach = reachable_from(self.w, self.w.start)
        for b in self.w.buildings.values():
            self.assertIs(self.w.building_at(*b.door), b, b.id)
            self.assertIn(b.door_outside(), reach, b.id)

    def test_roof_ridge_is_taller_than_roof_edge(self):
        b = self.w.buildings["1"]
        self.assertGreater(b.height_at(3, 3), b.height_at(3, 2))
        self.assertEqual(b.height_at(3, 2), b.height_at(3, 4))

    def test_door_tile_offers_building_line(self):
        b = self.w.buildings["1"]
        self.assertEqual(self.w.interaction_at(*b.door), b.line)


class FeatureTest(unittest.TestCase):
    def setUp(self):
        self.w = world.load()

    def test_sign_is_blocking_and_readable(self):
        self.assertEqual(self.w.feature(13, 5), "sign")
        self.assertTrue(self.w.blocked(13, 5))
        self.assertTrue(self.w.interaction_at(13, 5))

    def test_fountain_sits_in_the_plaza(self):
        self.assertEqual(self.w.feature(11, 11), "fountain")
        self.assertEqual(self.w.ground(10, 11), "plaza")

    def test_npcs_spawn_on_walkable_reachable_tiles(self):
        reach = reachable_from(self.w, self.w.start)
        self.assertGreaterEqual(len(world.NPCS), 3)
        for spec in world.NPCS:
            self.assertIn(spec["pos"], reach, spec["role"])


if __name__ == "__main__":
    unittest.main()
