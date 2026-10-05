import copy
import os
import shutil
import tempfile
import unittest

import plat
import problems
from layers import Rows
from model import Model, Module
from plat import District, Plat
from roads import BACKWARDS, CYCLE, Roads
from townmap import TownMap


def town_model(locs):
    model = Model(repo="r")
    for id_, loc in locs.items():
        model.modules[id_] = Module(id=id_, district=id_.split("/")[0], kind="source", loc=loc)
    return model


def tiles(lot):
    x, y, size = lot
    return {(x + i, y + j) for i in range(size) for j in range(size)}


class FootprintTest(unittest.TestCase):
    def test_lines_of_code_set_the_lot_size(self):
        self.assertEqual([plat.footprint(n) for n in (0, 99, 100, 399, 400, 999, 1000, 9000)],
                         [1, 1, 2, 2, 3, 3, 4, 4])


class DistrictTest(unittest.TestCase):
    def setUp(self):
        self.d = District.pack([("a", 1, 0), ("b", 2, 0), ("c", 1, 0), ("d", 3, 1)])

    def assert_sound(self):
        streets = self.d.streets()
        seen = set()
        for x, y, size in self.d.lots.values():
            lot = tiles((x, y, size))
            self.assertFalse(lot & seen, "lots overlap")
            self.assertFalse(lot & streets, "a lot sits on a street")
            self.assertTrue(all((x + i, y + size) in streets for i in range(size)),
                            "no street in front")
            self.assertLessEqual(x + size, self.d.w)
            seen |= lot

    def test_lots_never_overlap_and_every_door_faces_a_street(self):
        self.assert_sound()

    def test_later_layers_never_stand_behind_earlier_ones(self):
        self.assertGreaterEqual(self.d.lots["d"][1], self.d.lots["b"][1])

    def test_lines_read_alphabetically_back_to_front_then_left_to_right(self):
        reading = sorted(self.d.lots, key=lambda m: (sum(self.d.lots[m][1:]), self.d.lots[m][0]))
        self.assertEqual(reading, ["a", "b", "c", "d"])

    def test_at_least_30_percent_of_each_line_is_free(self):
        for top, height, _ in self.d.lines:
            used = max(x + s for x, y, s in self.d.lots.values() if y + s == top + height)
            self.assertGreaterEqual(self.d.w - used, int(self.d.w * plat.FREE))

    def test_a_new_module_takes_a_free_plot_in_a_line_of_its_layer(self):
        self.d.place("e", 1, 0)
        x, y, size = self.d.lots["e"]
        top, height, _ = self.d.lines[0]
        self.assertEqual(y + size, top + height)
        self.assert_sound()

    def test_when_nothing_fits_a_new_line_opens_at_the_front(self):
        h = self.d.h
        self.d.place("big", 4, 0)
        self.assertEqual(self.d.lots["big"], [0, h, 4])
        self.assert_sound()


class PlatTest(unittest.TestCase):
    def setUp(self):
        self.model = town_model({"hub/app.py": 500, "hub/records.py": 50, "packages/sdk.py": 150})
        self.model.externals = {"flask": ["hub/app.py"], "yaml": ["packages/sdk.py"]}
        self.rows = Rows().update(self.model)
        self.plat = Plat().update(self.model, self.rows)

    def lots(self, p=None):
        return {m: lot for d in (p or self.plat).districts.values() for m, lot in d.lots.items()}

    def test_every_module_but_tests_gets_a_lot_sized_by_its_lines(self):
        self.model.modules["tests/test_app.py"] = Module("tests/test_app.py", "tests", "test")
        lots = self.lots(Plat().update(self.model, self.rows))
        self.assertEqual(sorted(lots), ["hub/app.py", "hub/records.py", "packages/sdk.py"])
        self.assertEqual(lots["hub/app.py"][2], 3)

    def test_existing_lots_stay_put_when_a_module_arrives(self):
        before = copy.deepcopy(self.lots())
        self.model.modules["hub/new.py"] = Module("hub/new.py", "hub", "source", loc=10)
        self.plat.update(self.model, self.rows)
        after = self.lots()
        self.assertEqual({m: after[m] for m in before}, before)
        self.assertIn("hub/new.py", after)

    def test_a_deleted_module_leaves_a_vacant_lot(self):
        lot = self.lots()["hub/records.py"]
        del self.model.modules["hub/records.py"]
        self.plat.update(self.model, self.rows)
        self.assertNotIn("hub/records.py", self.lots())
        self.assertIn(lot, self.plat.districts["hub"].vacant)

    def test_a_new_module_can_cover_a_vacant_lot(self):
        model = town_model({"hub/a.py": 10, "hub/b.py": 20, "packages/sdk.py": 150})
        rows = Rows().update(model)
        plat = Plat().update(model, rows)
        lot = plat.districts["hub"].lots["hub/b.py"]
        del model.modules["hub/b.py"]
        plat.update(model, rows)
        self.assertIn(lot, plat.districts["hub"].vacant)
        model.modules["hub/c.py"] = Module("hub/c.py", "hub", "source", loc=20)
        plat.update(model, rows)
        self.assertEqual(plat.districts["hub"].lots["hub/c.py"], lot)
        self.assertEqual(plat.districts["hub"].vacant, [])

    def test_a_renamed_module_keeps_its_lot(self):
        lot = self.lots()["hub/records.py"]
        m = self.model.modules.pop("hub/records.py")
        m.id = "hub/store.py"
        self.model.modules[m.id] = m
        self.model.renames = {"hub/records.py": "hub/store.py"}
        self.plat.update(self.model, self.rows)
        self.assertEqual(self.lots()["hub/store.py"], lot)
        self.assertEqual(self.plat.districts["hub"].vacant, [])

    def test_outside_packages_keep_their_harbor_slot(self):
        self.assertEqual(self.plat.harbor, ["flask", "yaml"])
        self.model.externals = {"requests": ["hub/app.py"], "yaml": ["packages/sdk.py"]}
        self.plat.update(self.model, self.rows)
        self.assertEqual(self.plat.harbor, ["requests", "yaml"])

    def test_the_same_model_always_gives_the_same_plat(self):
        again = Plat().update(self.model, self.rows)
        self.assertEqual(self.lots(again), self.lots())

    def test_plat_round_trips_and_a_missing_file_is_empty(self):
        folder = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, folder)
        path = os.path.join(folder, "plat.json")
        self.plat.save(path)
        loaded = Plat.load(path)
        self.assertEqual((loaded.districts, loaded.harbor), (self.plat.districts, self.plat.harbor))
        self.assertEqual(Plat.load(path + ".missing").districts, {})


def role_model():
    model = Model(repo="roles")

    def add(id_, entry=False, kind="source"):
        model.modules[id_] = Module(id=id_, district=id_.split("/")[0], kind=kind, loc=40,
                                    is_entry=entry)

    add("app/main.py", entry=True)
    for id_ in ("core/a.py", "core/b.py", "core/util.py", "old/dead.py"):
        add(id_)
    add("tools/run.py", entry=True)
    add("web/ui.js", kind="unsurveyed")
    for edge in [("app/main.py", "core/a.py"), ("app/main.py", "core/b.py"),
                 ("app/main.py", "core/util.py"), ("core/a.py", "core/util.py"),
                 ("core/b.py", "core/util.py")]:
        model.edges[edge] = 1
    model.externals = {"yaml": ["core/a.py"]}
    return model


class RolesLayoutTest(unittest.TestCase):
    def test_districts_are_roles_from_back_to_front(self):
        layout, bands = plat.by_roles(role_model(), Rows())
        lots = {name: sorted(d.lots) for name, d in layout.districts.items()}
        self.assertEqual(lots, {"/foundations": ["core/util.py"],
                                "/front door": ["app/main.py", "core/b.py"],
                                "/park": [], "/main street": ["core/a.py"],
                                "/standalone scripts": ["tools/run.py"],
                                "/islands": ["old/dead.py"], "/unsurveyed": ["web/ui.js"]})
        order = ["/foundations", "/front door", "/park", "/main street", "/standalone scripts",
                 "/islands", "/unsurveyed"]
        rank = lambda n: (bands.districts[n], layout.order.index(n))
        self.assertEqual(sorted(order, key=rank), order)
        self.assertEqual(layout.harbor, ["yaml"])

    def test_the_front_door_opens_its_side_of_the_main_street(self):
        layout, _ = plat.by_roles(role_model(), Rows())
        self.assertEqual(layout.districts["/front door"].lots["app/main.py"][:2], [0, 0])

    def test_town_hall_stands_in_the_park_and_ports_stand_in_water(self):
        model = role_model()
        rows = Rows().update(model)
        layout, bands = plat.by_roles(model, rows)
        town = TownMap(model, layout, bands, problems.find(model, rows))
        bx, by, w, h = town.boxes["/park"]
        self.assertEqual(town.hall, (bx + w // 2, by + h // 2))
        self.assertTrue(town.walkable(*town.hall))
        port = town.warehouses["yaml"]
        self.assertTrue(town.walkable(*port.front()))
        around = {(x + dx, y + dy) for x, y in port.tiles() for dx in (-1, 0, 1)
                  for dy in (-1, 0, 1)} - set(port.tiles()) - {port.front()}
        self.assertIn("water", {town.kind(*t) for t in around})

    def test_a_town_laid_out_by_roles_has_every_building_and_no_highways(self):
        model = role_model()
        rows = Rows().update(model)
        layout, bands = plat.by_roles(model, rows)
        found = problems.find(model, rows)
        town = TownMap(model, layout, bands, found)
        self.assertEqual(sorted(town.buildings), sorted(m.id for m in model.of_kind("source")))
        self.assertEqual(Roads(town, model, found)._highways(), [])

    def test_role_layout_pins_cycle_and_backwards_roads(self):
        model = role_model()
        model.edges[("core/a.py", "core/b.py")] = 1
        model.edges[("core/b.py", "core/a.py")] = 1
        model.modules["core/c.py"] = Module("core/c.py", "core", "source", loc=40)
        rows = Rows().update(model)
        model.edges[("core/c.py", "core/a.py")] = 1
        layout, bands = plat.by_roles(model, rows)
        found = problems.find(model, rows)
        town = TownMap(model, layout, bands, found)
        always = {(r.kind, r.src, r.dst) for r in Roads(town, model, found).always}
        self.assertIn((CYCLE, "core/a.py", "core/b.py"), always)
        self.assertIn((BACKWARDS, "core/c.py", "core/a.py"), always)
