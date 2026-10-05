import unittest

import cake
import problems
from layers import Rows
from model import Model, Module
from plat import Plat
from townmap import MARGIN, MAX_HEIGHT, TownMap, squash

TESTED = ["tests/test_core.py"]


def showcase():
    """A small town with every problem in it, and the rows it was first laid out with."""
    model = Model(repo="showcase")

    def add(id_, loc=40, complexity=5, exports=("run",), kind="source", **facts):
        model.modules[id_] = Module(id=id_, district=id_.split("/")[0], kind=kind, loc=loc,
                                    complexity=complexity, exports=list(exports), **facts)

    add("core/base.py", loc=300, complexity=40, tested_by=TESTED, churn=2,
        functions=[("load", 120, 6), ("save", 30, 3), ("close", 8, 1)])
    add("core/broken.py", parse_error="line 3: invalid syntax", tested_by=TESTED,
        functions=[("half", 10, 2), ("way", 5, 1)])
    add("core/doors.py", loc=30, exports=[f"f{i}" for i in range(8)], tested_by=TESTED)
    add("core/loop_a.py", tested_by=TESTED)
    add("core/loop_b.py", tested_by=TESTED)
    add("core/notes.py", notes=2, tested_by=TESTED)
    add("core/tower.py", loc=2400, complexity=260, churn=9, tested_by=TESTED)
    add("app/main.py", loc=120, complexity=12, is_entry=True)
    add("app/helper.py")
    add("app/lonely.py")
    add("web/ui.js", kind="unsurveyed", loc=200, exports=())
    add("tests/test_core.py", kind="test")
    for src, dst in [("app/main.py", "core/base.py"), ("app/main.py", "core/tower.py"),
                     ("app/main.py", "core/doors.py"), ("app/main.py", "core/broken.py"),
                     ("app/main.py", "core/notes.py"), ("app/main.py", "core/loop_a.py"),
                     ("core/loop_a.py", "core/loop_b.py"), ("core/loop_b.py", "core/loop_a.py"),
                     ("core/tower.py", "core/base.py")]:
        model.edges[(src, dst)] = 2 if dst == "core/base.py" else 1
    model.externals = {"flask": ["app/main.py"], "yaml": ["core/base.py"]}
    rows = Rows({"app": 1, "core": 0}).update(model)
    model.edges[("core/notes.py", "app/helper.py")] = 1
    return model, rows


def build():
    model, rows = showcase()
    found = problems.find(model, rows)
    return model, rows, found, TownMap(model, Plat().update(model, rows), rows, found)


class ShowcaseTest(unittest.TestCase):
    def test_the_showcase_has_every_problem(self):
        _, _, found, _ = build()
        self.assertEqual({p.kind for p in found}, set(problems.KINDS))


class TownMapTest(unittest.TestCase):
    def setUp(self):
        self.model, self.rows, self.found, self.town = build()

    def sited(self, paths):
        return TownMap(self.model, Plat().update(self.model, self.rows), self.rows, self.found,
                       sites=paths)

    def test_every_source_module_is_a_building_and_others_are_plots(self):
        sources = sorted(m.id for m in self.model.of_kind("source"))
        self.assertEqual(sorted(self.town.buildings), sources)
        self.assertEqual(list(self.town.plots), ["web/ui.js"])

    def test_every_door_opens_onto_a_walkable_tile(self):
        for b in list(self.town.buildings.values()) + list(self.town.warehouses.values()):
            self.assertTrue(self.town.walkable(*b.front()), b)

    def test_buildings_never_share_a_tile(self):
        seen = set()
        for b in self.town.buildings.values():
            self.assertFalse(seen & set(b.tiles()))
            seen |= set(b.tiles())

    def test_a_building_is_a_cake_with_a_floor_per_function(self):
        base = self.town.buildings["core/base.py"]
        self.assertEqual(base.functions, (("load", 120, 6), ("save", 30, 3), ("close", 8, 1)))
        self.assertEqual(base.floors, 3)
        self.assertEqual([t.amber for t in base.stack], [True, False, False])
        self.assertEqual(self.town.buildings["core/loop_a.py"].floors, 1)

    def test_a_module_that_will_not_parse_is_one_floor(self):
        self.assertEqual(self.town.buildings["core/broken.py"].floors, 1)

    def test_no_building_stands_taller_than_the_cap(self):
        self.assertEqual(self.town.buildings["core/tower.py"].stack[-1].z1, MAX_HEIGHT)
        self.assertTrue(all(b.stack[-1].z1 <= MAX_HEIGHT for b in self.town.buildings.values()))

    def test_squash_keeps_floors_touching_and_their_amber(self):
        tall = [cake.Tier(10, 0, 2, False), cake.Tier(10, 2, 4, True)] + \
               [cake.Tier(6, 4 + 2 * i, 6 + 2 * i, False) for i in range(98)]
        short = squash(tall, 50)
        self.assertEqual((short[0].z0, short[-1].z1), (0, 50))
        self.assertTrue(all(a.z1 == b.z0 for a, b in zip(short, short[1:])))
        self.assertTrue(all(t.z0 < t.z1 for t in short))
        self.assertTrue(short[0].amber)
        self.assertEqual(squash(tall[:3], 50), tuple(tall[:3]))

    def test_back_rows_sit_behind_front_rows(self):
        self.assertLess(self.town.boxes["core"][1], self.town.boxes["app"][1])

    def test_the_harbor_is_behind_the_town(self):
        top = min(y for _, y, _, _ in self.town.boxes.values())
        self.assertEqual(sorted(self.town.warehouses), ["flask", "yaml"])
        self.assertTrue(all(w.y + w.size < top for w in self.town.warehouses.values()))

    def test_entry_points_get_a_gate_and_backwards_roads_a_no_entry_sign(self):
        b = self.town.buildings
        self.assertIn("gate", self.town.props[b["app/main.py"].front()])
        self.assertIn("no entry", self.town.props[b["core/notes.py"].front()])

    def test_paving_wears_around_busy_buildings_and_cracks_at_hotspots(self):
        tower = self.town.buildings["core/tower.py"]
        self.assertEqual(self.town.wear[tower.front()], 9)
        self.assertIn(tower.front(), self.town.hot)

    def test_towers_cast_a_shadow(self):
        tower = self.town.buildings["core/tower.py"]
        self.assertIn((tower.x + tower.size, tower.y), self.town.shadow)

    def test_trees_only_grow_where_there_is_no_code(self):
        self.assertTrue(self.town.trees)
        self.assertTrue(all(self.town.kind(*t) == "grass" for t in self.town.trees))

    def test_thing_at_finds_buildings_plots_and_warehouses(self):
        b = self.town.buildings["core/base.py"]
        self.assertIs(self.town.thing_at(b.x, b.y), b)
        x, y, _ = self.town.plots["web/ui.js"]
        self.assertEqual(self.town.thing_at(x, y), ("plot", "web/ui.js"))
        w = self.town.warehouses["flask"]
        self.assertIs(self.town.thing_at(w.x, w.y), w)
        self.assertIsNone(self.town.thing_at(0, self.town.height - 1))

    def test_new_files_are_construction_sites_along_the_front(self):
        town = self.sited(["app/new.py", "app/newer.py"])
        (ax, ay), (bx, by) = town.sites["app/new.py"], town.sites["app/newer.py"]
        self.assertEqual(ay, by)
        self.assertGreater(bx, ax)
        self.assertGreaterEqual(ay, max(b.y + b.size for b in town.buildings.values()))
        self.assertEqual(town.kind(ax, ay), "site")
        self.assertEqual(town.thing_at(ax, ay), ("site", "app/new.py"))

    def test_many_sites_wrap_onto_more_rows_inside_the_island(self):
        town = self.sited([f"new/f{i:03}.py" for i in range(100)])
        rows = {y for _, y in town.sites.values()}
        self.assertGreater(len(rows), 1)
        self.assertTrue(all(x < town.right for x, _ in town.sites.values()))
        self.assertLess(max(rows) + MARGIN, town.height)

    def test_sites_and_their_front_are_clear_of_trees(self):
        town = self.sited([f"new/f{i:03}.py" for i in range(100)])
        front = set()
        for x, y in town.sites.values():
            front.update(((x, y + 1), (x + 1, y), (x + 1, y + 1)))
        for tile in set(town.sites.values()) | front:
            self.assertNotIn(tile, town.trees, tile)
            self.assertNotIn(tile, town.bushes, tile)
