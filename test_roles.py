import unittest

import roles
from model import Model, Module


def model(modules, edges):
    found = {}
    for spec in modules:
        name, *flags = spec.split()
        found[name] = Module(name, "", "test" if "test" in flags else "source", loc=10,
                             is_entry="entry" in flags, mentioned="mentioned" in flags,
                             public="public" in flags,
                             tested_by=["t.py"] if "tested" in flags else [])
    return Model("r", found, {(s, d): 1 for s, d in edges})


TOWN = model(
    ["cli.py entry tested", "app.py", "core.py", "util.py", "log.py",
     "mock.py entry", "chart.py entry", "plot.py", "report.py entry", "common.py entry",
     "plugin.py mentioned", "api.py public", "dead.py", "test_cli.py test"],
    [("cli.py", "app.py"), ("app.py", "core.py"), ("cli.py", "util.py"), ("app.py", "util.py"),
     ("core.py", "util.py"), ("cli.py", "log.py"), ("mock.py", "app.py"), ("mock.py", "core.py"),
     ("mock.py", "plot.py"), ("mock.py", "log.py"), ("chart.py", "plot.py"),
     ("report.py", "common.py"), ("test_cli.py", "dead.py"), ("app.py", "app.py")])


class RolesTest(unittest.TestCase):
    def setUp(self):
        self.found = roles.roles(TOWN)

    def test_every_source_module_gets_one_role(self):
        self.assertEqual(set(self.found), {m for m in TOWN.modules if m != "test_cli.py"})

    def test_tested_entry_point_is_the_door_over_one_that_reaches_more(self):
        self.assertEqual(self.found["cli.py"], roles.DOOR)
        self.assertEqual(self.found["mock.py"], roles.SCRIPT)

    def test_most_tested_entry_point_wins_over_one_that_imports_it(self):
        m = model(["tool.py entry tested", "wrap.py entry tested", "lib.py"],
                  [("wrap.py", "tool.py"), ("tool.py", "lib.py")])
        m.modules["tool.py"].tested_by = ["test_a.py", "test_b.py"]
        found = roles.roles(m)
        self.assertEqual(found["tool.py"], roles.DOOR)
        self.assertEqual(found["wrap.py"], roles.SCRIPT)

    def test_declared_door_wins(self):
        found = roles.roles(TOWN, ["mock.py", "missing.py"])
        self.assertEqual(found["mock.py"], roles.DOOR)
        self.assertEqual(found["cli.py"], roles.SCRIPT)
        self.assertEqual(found["plot.py"], roles.STREET)

    def test_street_foundation_and_side(self):
        self.assertEqual(self.found["app.py"], roles.STREET)
        self.assertEqual(self.found["core.py"], roles.STREET)
        self.assertEqual(self.found["util.py"], roles.FOUNDATION)
        self.assertEqual(self.found["log.py"], roles.STREET)
        self.assertEqual(self.found["plot.py"], roles.SIDE)

    def test_unreached_modules_are_named_or_islands(self):
        self.assertEqual(self.found["plugin.py"], roles.NAMED)
        self.assertEqual(self.found["api.py"], roles.NAMED)
        self.assertEqual(self.found["dead.py"], roles.ISLAND)

    def test_without_entry_points_only_named_modules_keep_others_alive(self):
        quiet = model(["a.py", "b.py mentioned", "c.py", "d.py"], [("a.py", "b.py"), ("b.py", "c.py")])
        self.assertEqual(roles.roles(quiet), {"a.py": roles.ISLAND, "b.py": roles.NAMED,
                                              "c.py": roles.SIDE, "d.py": roles.ISLAND})

    def test_near_empty_packages_get_no_building(self):
        m = model(["pkg/__init__.py", "pkg/a.py entry"], [])
        m.modules["pkg/__init__.py"].loc = 2
        self.assertNotIn("pkg/__init__.py", roles.roles(m))
        m.modules["pkg/__init__.py"].loc = 40
        self.assertIn("pkg/__init__.py", roles.roles(m))

    def test_scripts_group_around_the_helper_they_share(self):
        self.assertEqual(roles.script_groups(TOWN, self.found),
                         {"common.py": ["common.py", "report.py"],
                          roles.STANDALONE: ["chart.py", "mock.py"]})


if __name__ == "__main__":
    unittest.main()
