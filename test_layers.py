import os
import shutil
import tempfile
import unittest

import layers
from layers import Rows
from model import Model, Module


def model_of(districts, edges):
    model = Model(repo="r")
    for id_, district in districts.items():
        model.modules[id_] = Module(id=id_, district=district, kind="source")
    model.edges = {e: 1 for e in edges}
    return model


class GraphTest(unittest.TestCase):
    def test_components_come_out_sinks_first(self):
        succ = {"a": {"b"}, "b": {"c"}, "c": {"b"}}
        self.assertEqual(layers.strongly_connected(["a", "b", "c"], succ), [["b", "c"], ["a"]])

    def test_foundations_are_layer_zero(self):
        succ = {"app": {"lib", "util"}, "lib": {"util"}}
        found, loops = layers.layer_of(["app", "lib", "util"], succ)
        self.assertEqual(found, {"app": 2, "lib": 1, "util": 0})
        self.assertEqual(loops, [])

    def test_a_cycle_shares_one_layer(self):
        succ = {"a": {"b"}, "b": {"a"}, "top": {"a"}}
        found, loops = layers.layer_of(["a", "b", "top"], succ)
        self.assertEqual((found["a"], found["b"], found["top"]), (0, 0, 1))
        self.assertEqual(loops, [["a", "b"]])

    def test_a_long_chain_does_not_hit_the_recursion_limit(self):
        nodes = [f"m{i:05d}" for i in range(5000)]
        succ = {a: {b} for a, b in zip(nodes, nodes[1:])}
        found, _ = layers.layer_of(nodes, succ)
        self.assertEqual((found[nodes[0]], found[nodes[-1]]), (4999, 0))

    def test_cycles_in_a_model(self):
        model = model_of({"a/x.py": "a", "a/y.py": "a", "a/z.py": "a"},
                         [("a/x.py", "a/y.py"), ("a/y.py", "a/x.py"), ("a/z.py", "a/x.py")])
        self.assertEqual(layers.cycles(model), [["a/x.py", "a/y.py"]])


class RowsTest(unittest.TestCase):
    def setUp(self):
        self.model = model_of(
            {"hub/app.py": "hub", "hub/records.py": "hub", "packages/sdk.py": "packages"},
            [("hub/app.py", "packages/sdk.py"), ("hub/app.py", "hub/records.py")])

    def test_district_and_module_rows(self):
        rows = Rows().update(self.model)
        self.assertEqual(rows.districts, {"packages": 0, "hub": 1})
        self.assertEqual(rows.modules,
                         {"hub/records.py": 0, "hub/app.py": 1, "packages/sdk.py": 0})

    def test_fresh_rows_have_no_backwards_roads(self):
        rows = Rows().update(self.model)
        self.assertFalse(any(rows.is_backwards(self.model, s, d) for s, d in self.model.edges))

    def test_saved_rows_hold_so_a_new_import_can_point_backwards(self):
        rows = Rows().update(self.model)
        self.model.edges[("packages/sdk.py", "hub/records.py")] = 1
        rows.update(self.model)
        self.assertEqual(rows.districts, {"packages": 0, "hub": 1})
        self.assertTrue(rows.is_backwards(self.model, "packages/sdk.py", "hub/records.py"))

    def test_a_renamed_module_keeps_its_row(self):
        rows = Rows({"hub": 1, "packages": 0}, {"hub/old.py": 3})
        self.model.renames = {"hub/old.py": "hub/records.py"}
        rows.update(self.model)
        self.assertEqual(rows.modules["hub/records.py"], 3)
        self.assertNotIn("hub/old.py", rows.modules)

    def test_rows_round_trip_and_a_missing_file_is_empty(self):
        folder = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, folder)
        path = os.path.join(folder, "rows.json")
        rows = Rows().update(self.model)
        rows.save(path)
        loaded = Rows.load(path)
        self.assertEqual((loaded.districts, loaded.modules), (rows.districts, rows.modules))
        self.assertEqual(Rows.load(path + ".missing").districts, {})


if __name__ == "__main__":
    unittest.main()
