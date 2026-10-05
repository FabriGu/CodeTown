import json
import unittest

import drawtown
import focus
import fixture
import problems
import roads as R
import survey
import townjson
from layers import Rows
from plat import Plat
from roads import Roads
from test_townmap import build
from townmap import TownMap
from viewer import Viewer


class TownDocumentTest(unittest.TestCase):
    def setUp(self):
        self.model, self.rows, self.found, self.tmap = build()
        self.roads = Roads(self.tmap, self.model, self.found)
        self.viewer = Viewer(self.tmap, self.roads, self.model, self.found)
        self.doc = townjson.town(self.tmap, self.roads, self.viewer.describe,
                                 repo="showcase", version=3)

    def test_it_survives_a_round_trip_through_json(self):
        self.assertEqual(json.loads(json.dumps(self.doc)), self.doc)

    def test_it_names_its_repo_version_size_and_pixel_scale(self):
        self.assertEqual((self.doc["repo"], self.doc["version"]), ("showcase", 3))
        self.assertEqual(self.doc["size"], [self.tmap.width, self.tmap.height])
        self.assertEqual(self.doc["half_w"], 6)

    def test_tile_rows_spell_every_tile_kind(self):
        legend = self.doc["legend"]
        self.assertEqual(len(self.doc["tiles"]), self.tmap.height)
        for y, row in enumerate(self.doc["tiles"]):
            self.assertEqual(len(row), self.tmap.width)
            for x, letter in enumerate(row):
                self.assertEqual(legend[letter], self.tmap.kind(x, y), (x, y))

    def test_a_sessions_new_files_are_site_tiles(self):
        tmap = TownMap(self.model, Plat().update(self.model, self.rows), self.rows, self.found,
                       sites=["app/new.py"])
        roads = Roads(tmap, self.model, self.found)
        doc = townjson.town(tmap, roads, Viewer(tmap, roads, self.model, self.found).describe,
                            repo="showcase")
        x, y = tmap.sites["app/new.py"]
        self.assertEqual(doc["legend"][doc["tiles"][y][x]], "site")

    def test_trees_are_the_town_maps(self):
        self.assertEqual({tuple(t) for t in self.doc["trees"]}, self.tmap.trees)

    def test_each_building_carries_its_lot_cake_windows_and_problems(self):
        docs = {d["path"]: d for d in self.doc["buildings"]}
        self.assertEqual(set(docs), set(self.tmap.buildings))
        for module, b in self.tmap.buildings.items():
            d = docs[module]
            self.assertEqual(d["lot"], [b.x, b.y, b.size])
            self.assertEqual(d["district"], b.district)
            self.assertEqual([(t["half"], t["z0"], t["z1"], t["amber"]) for t in d["tiers"]],
                             [(t.half, t.z0, t.z1, t.amber) for t in b.stack])
            self.assertEqual(d["glass"], drawtown.window_kind(b))
            self.assertEqual(set(d["problems"]), set(b.problems))

    def test_roofs_are_the_pixel_towns(self):
        self.assertEqual({d["name"]: d["roof"] for d in self.doc["districts"]},
                         drawtown.roof_index(self.tmap))
        for d in self.doc["districts"]:
            box = self.tmap.boxes.get(d["name"])
            self.assertEqual(d["box"], list(box) if box else None)

    def test_inspect_is_the_terminal_inspector(self):
        for d in self.doc["buildings"]:
            title, facts, reasons = self.viewer.describe(self.tmap.buildings[d["path"]])
            self.assertEqual(d["inspect"], {"title": title, "facts": facts, "reasons": reasons})
        broken = next(d for d in self.doc["buildings"] if problems.FIRE in d["problems"])
        self.assertTrue(broken["inspect"]["reasons"])

    def test_warehouses_carry_their_lot_and_inspector(self):
        docs = {d["package"]: d for d in self.doc["warehouses"]}
        self.assertEqual(set(docs), set(self.tmap.warehouses))
        for package, w in self.tmap.warehouses.items():
            self.assertEqual(docs[package]["lot"], [w.x, w.y, w.size])
            self.assertEqual(docs[package]["inspect"]["title"], self.viewer.describe(w)[0])

    def test_every_import_and_package_use_is_a_road_always_drawn(self):
        net = self.roads.network()
        self.assertEqual(self.doc["roads"],
                         [{**townjson.road(r), "id": i,
                           "line": sorted({n.src for n in net}).index(r.src)}
                          for i, r in enumerate(net)])
        drawn = {(r["from"], r["to"]) for r in self.doc["roads"]}
        self.assertLessEqual({e for e in self.model.edges
                              if all(m in self.tmap.buildings for m in e)}, drawn)
        self.assertIn(("app/main.py", "flask"), drawn)
        self.assertIn("cycle", {r["kind"] for r in self.doc["roads"]})

    def test_the_roads_leaving_one_building_share_a_line(self):
        lines = {}
        for r in self.doc["roads"]:
            lines.setdefault(r["from"], set()).add(r["line"])
        self.assertTrue(all(len(v) == 1 for v in lines.values()))
        self.assertEqual(len({min(v) for v in lines.values()}), len(lines))

    def test_a_road_keeps_its_ends_tiles_width_and_layer(self):
        r = self.roads.visible()[0]
        d = townjson.road(r)
        self.assertEqual((d["from"], d["to"], d["kind"], d["weight"]),
                         (r.src, r.dst, r.kind, r.weight))
        self.assertEqual(d["tiles"], [list(t) for t in r.path])
        self.assertEqual(d["half"], R.half_width(r.kind, r.weight))
        self.assertEqual(d["layer"], R.ORDER.index(r.kind))


class SelectionTest(unittest.TestCase):
    def setUp(self):
        self.model, self.rows, self.found, self.tmap = build()
        self.roads = Roads(self.tmap, self.model, self.found)

    def select(self, **name):
        return townjson.selection(self.tmap, self.roads, self.model, **name)

    def test_a_module_dims_the_town_by_distance_and_lights_its_own_roads(self):
        module = "core/tower.py"
        answer = self.select(module=module)
        f = focus.select(self.model, module)
        self.assertEqual(answer["focused"], [module])
        self.assertEqual(answer["dim"], {m: focus.dim(f, m) for m in self.tmap.buildings})
        net = townjson.network(self.roads)
        self.assertEqual(answer["lit"], [r["id"] for r in net if module in (r["from"], r["to"])])
        lit = [net[i] for i in answer["lit"]]
        self.assertTrue(any(r["from"] == module for r in lit))
        self.assertTrue(any(r["to"] == module for r in lit))

    def test_a_warehouse_lights_its_users_roads_and_dims_nothing(self):
        answer = self.select(package="flask")
        self.assertEqual((answer["focused"], answer["dim"]), ([], {}))
        net = townjson.network(self.roads)
        self.assertTrue(answer["lit"])
        self.assertEqual({net[i]["to"] for i in answer["lit"]}, {"flask"})

    def test_a_name_not_in_the_town_has_no_answer(self):
        self.assertIsNone(self.select(module="nope.py"))
        self.assertIsNone(self.select(package="nope"))
        self.assertIsNone(self.select())

    def test_the_answer_survives_a_round_trip_through_json(self):
        answer = self.select(module="core/tower.py")
        self.assertEqual(json.loads(json.dumps(answer)), answer)


class NoFileContentsTest(unittest.TestCase):
    def test_file_contents_never_reach_the_document(self):
        marker = "zebra-quartz-7731"
        root = fixture.make_repo(self, {
            "pkg/__init__.py": "",
            "pkg/a.py": f"# {marker}\nimport pkg.b\nNOTE = '{marker}'\n\n\ndef run():\n"
                        f"    return '{marker}'\n",
            "pkg/b.py": f'"""{marker}"""\nimport pkg.a\n',
            "pkg/broken.py": f"def half(:\n    return '{marker}'\n",
        })
        model = survey.survey(root)
        rows = Rows({}).update(model)
        found = problems.find(model, rows)
        tmap = TownMap(model, Plat().update(model, rows), rows, found)
        roads = Roads(tmap, model, found)
        doc = townjson.town(tmap, roads, Viewer(tmap, roads, model, found).describe,
                            repo="fixture")
        text = json.dumps(doc) + json.dumps(townjson.selection(tmap, roads, model,
                                                               module="pkg/a.py"))
        self.assertIn("pkg/a.py", text)
        self.assertNotIn(marker, text)


if __name__ == "__main__":
    unittest.main()
