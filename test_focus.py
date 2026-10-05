import unittest

import focus
from model import Model, Module
from session import COMMAND, DELETE, EDIT, READ, WRITE, Step


def model(edges, members=None):
    """app -> lib -> core, tool -> core, a <-> b, and a lone module."""
    ids = {m for edge in edges for m in edge} | {"lone.py"} | set(members or ())
    modules = {m: Module(m, "(root)", "source", members=(members or {}).get(m, []))
               for m in sorted(ids)}
    return Model("repo", modules, {edge: 1 for edge in edges})


EDGES = [("app.py", "lib.py"), ("lib.py", "core.py"), ("tool.py", "core.py"),
         ("a.py", "b.py"), ("b.py", "a.py"), ("lib.py", "lib.py")]


class NeighboursTest(unittest.TestCase):
    def test_both_ways_without_self_imports(self):
        self.assertEqual(focus.neighbours(model(EDGES), "lib.py"), ({"core.py"}, {"app.py"}))

    def test_select_draws_both_ways_and_keeps_the_rest_out(self):
        f = focus.select(model(EDGES), "lib.py")
        self.assertEqual(f.distance, {"lib.py": 0, "core.py": 1, "app.py": 1})
        self.assertEqual(f.roads, ((focus.USES, "lib.py", "core.py"),
                                   (focus.USED_BY, "app.py", "lib.py")))
        self.assertEqual(focus.dim(f, "app.py"), focus.BRIGHT)
        self.assertEqual(focus.dim(f, "tool.py"), focus.REST)


class BlastRadiusTest(unittest.TestCase):
    def test_follows_importers_outwards_by_distance(self):
        self.assertEqual(focus.blast_radius(model(EDGES), {"core.py"}),
                         {"core.py": 0, "lib.py": 1, "tool.py": 1, "app.py": 2})

    def test_stops_at_a_cycle(self):
        self.assertEqual(focus.blast_radius(model(EDGES), {"a.py"}), {"a.py": 0, "b.py": 1})

    def test_ignores_modules_not_in_the_model(self):
        self.assertEqual(focus.blast_radius(model(EDGES), {"gone.py"}), {})

    def test_roads_each_lead_one_step_closer(self):
        f = focus.changed(model(EDGES), {"core.py"})
        self.assertEqual(set(f.roads), {(focus.USED_BY, "app.py", "lib.py"),
                                        (focus.USED_BY, "lib.py", "core.py"),
                                        (focus.USED_BY, "tool.py", "core.py")})
        self.assertEqual(focus.dim(f, "lib.py"), focus.BRIGHT)
        self.assertEqual(focus.dim(f, "app.py"), focus.FAR)
        self.assertEqual(focus.dim(f, "lone.py"), focus.REST)


class ChangedByTest(unittest.TestCase):
    def test_successful_changes_to_modules_only(self):
        steps = [Step(EDIT, "Edit", "lib.py"), Step(WRITE, "Write", "core.py", failed=True),
                 Step(READ, "Read", "app.py"), Step(COMMAND, "Bash", command="make"),
                 Step(DELETE, "Delete", "notes.md"), Step(EDIT, "Edit", "/outside/x.py")]
        self.assertEqual(focus.changed_by(steps, model(EDGES)), {"lib.py"})

    def test_a_member_file_maps_to_its_module(self):
        m = model(EDGES, members={"cmd/": ["cmd/main.go", "cmd/flags.go"]})
        self.assertEqual(focus.changed_by([Step(EDIT, "Edit", "cmd/flags.go")], m), {"cmd/"})


class UnbuiltTest(unittest.TestCase):
    def test_new_code_the_town_has_no_building_for(self):
        steps = [Step(WRITE, "Write", "src/new.py"), Step(EDIT, "Edit", "web/panel.js"),
                 Step(WRITE, "Write", "lib.py"), Step(WRITE, "Write", "kept.py"),
                 Step(WRITE, "Write", "notes.md"), Step(WRITE, "Write", "tests/test_new.py"),
                 Step(WRITE, "Write", "/tmp/scratch.py"), Step(WRITE, "Write", "bad.py", failed=True),
                 Step(WRITE, "Write", "gone.py"), Step(DELETE, "Delete", "gone.py"),
                 Step(READ, "Read", "read.py")]
        self.assertEqual(focus.unbuilt(steps, model(EDGES), ["kept.py"]),
                         ["src/new.py", "web/panel.js"])

    def test_rewritten_after_a_delete_counts_again(self):
        steps = [Step(DELETE, "Delete", "x.py"), Step(WRITE, "Write", "x.py")]
        self.assertEqual(focus.unbuilt(steps, model(EDGES), []), ["x.py"])


if __name__ == "__main__":
    unittest.main()
