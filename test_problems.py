import unittest

import problems as p
from layers import Rows
from model import Model, Module

HEALTHY = {"is_entry": True, "tested_by": ["tests/test_it.py"], "loc": 10}


def build(specs, edges=()):
    model = Model(repo="r")
    for id_, fields in specs.items():
        fields = dict(fields)
        kind = fields.pop("kind", "source")
        model.modules[id_] = Module(id=id_, district=id_.split("/")[0], kind=kind, **fields)
    model.edges = {e: 1 for e in edges}
    return model


def found(model, rows=None):
    rows = rows if rows is not None else Rows().update(model)
    return [(x.kind, x.module) for x in p.find(model, rows)]


class ProblemsTest(unittest.TestCase):
    def test_a_healthy_module_has_no_problems(self):
        self.assertEqual(found(build({"a/x.py": HEALTHY})), [])

    def test_wont_parse_carries_the_error(self):
        model = build({"a/x.py": dict(HEALTHY, parse_error="line 3: invalid syntax")})
        self.assertEqual(p.find(model, Rows()),
                         [p.Problem(p.FIRE, "a/x.py", "line 3: invalid syntax")])

    def test_every_member_of_a_cycle_is_reported(self):
        model = build({"a/x.py": HEALTHY, "a/y.py": HEALTHY},
                      edges=[("a/x.py", "a/y.py"), ("a/y.py", "a/x.py")])
        self.assertEqual(found(model), [(p.CYCLE, "a/x.py"), (p.CYCLE, "a/y.py")])

    def test_backwards_road_is_reported_even_inside_a_cycle(self):
        model = build({"app/x.py": HEALTHY, "lib/y.py": HEALTHY}, edges=[("app/x.py", "lib/y.py")])
        rows = Rows().update(model)
        model.edges[("lib/y.py", "app/x.py")] = 1
        self.assertEqual(found(model, rows),
                         [(p.CYCLE, "app/x.py"), (p.CYCLE, "lib/y.py"), (p.BACKWARDS, "lib/y.py")])

    def test_hotspot_filters_before_slicing(self):
        specs = {f"a/m{i:02d}.py": dict(HEALTHY, churn=1, complexity=5) for i in range(82)}
        for i in range(4):
            specs[f"a/stable{i}.py"] = dict(HEALTHY, churn=1, complexity=10000)
        specs["a/real_hotspot.py"] = dict(HEALTHY, churn=10, complexity=50)
        hotspots = [(x.kind, x.module) for x in p.find(build(specs), Rows()) if x.kind == p.HOTSPOT]
        self.assertEqual(hotspots, [(p.HOTSPOT, "a/real_hotspot.py")])

    def test_hotspot_is_both_busy_and_complicated(self):
        specs = {f"a/m{i:02d}.py": dict(HEALTHY, churn=1, complexity=5) for i in range(20)}
        specs["a/busy.py"] = dict(HEALTHY, churn=9, complexity=5)
        specs["a/knotty.py"] = dict(HEALTHY, churn=1, complexity=150)
        specs["a/both.py"] = dict(HEALTHY, churn=6, complexity=40)
        self.assertEqual(found(build(specs)), [(p.HOTSPOT, "a/both.py")])

    def test_hotspots_are_ranked_within_each_language(self):
        specs = {f"a/m{i:02d}.py": dict(HEALTHY, churn=1, complexity=5) for i in range(20)}
        specs["a/hot.py"] = dict(HEALTHY, churn=4, complexity=20)
        for i in range(20):
            specs[f"b/s{i:02d}.sh"] = dict(HEALTHY, churn=1, complexity=5, lang="shell")
        specs["b/hotter.sh"] = dict(HEALTHY, churn=9, complexity=90, lang="shell")
        specs["b/warm.sh"] = dict(HEALTHY, churn=5, complexity=50, lang="shell")
        specs["c/rough.lua"] = dict(HEALTHY, churn=9, complexity=90, lang="lua", depth="floor")
        specs["d/lone.rb"] = dict(HEALTHY, churn=9, complexity=90, lang="ruby")
        self.assertEqual(found(build(specs)), [(p.HOTSPOT, "a/hot.py"), (p.HOTSPOT, "b/hotter.sh")])

    def test_little_churn_is_never_a_hotspot(self):
        self.assertEqual(found(build({"a/x.py": dict(HEALTHY, churn=2, complexity=150)})), [])

    def test_tower_by_size_or_by_complexity(self):
        model = build({"a/big.py": dict(HEALTHY, loc=2400, complexity=90),
                       "a/knot.py": dict(HEALTHY, complexity=250)})
        self.assertEqual(found(model), [(p.TOWER, "a/big.py"), (p.TOWER, "a/knot.py")])

    def test_abandoned_unless_imported_run_or_mentioned(self):
        model = build({
            "a/lost.py": dict(HEALTHY, is_entry=False),
            "a/used.py": dict(HEALTHY, is_entry=False),
            "a/named.py": dict(HEALTHY, is_entry=False, mentioned=True),
            "a/__init__.py": dict(HEALTHY, is_entry=False),
            "a/main.py": HEALTHY,
        }, edges=[("a/main.py", "a/used.py")])
        self.assertEqual(found(model), [(p.ABANDONED, "a/lost.py")])

    def test_untested_skips_packages_and_empty_files(self):
        model = build({"a/x.py": dict(HEALTHY, tested_by=[]),
                       "a/__init__.py": dict(HEALTHY, tested_by=[]),
                       "a/empty.py": dict(HEALTHY, tested_by=[], loc=0)})
        self.assertEqual(found(model), [(p.UNTESTED, "a/x.py")])

    def test_all_doors_means_many_exports_over_little_code(self):
        doors = list("abcdef")
        model = build({"a/thin.py": dict(HEALTHY, exports=doors, loc=40),
                       "a/deep.py": dict(HEALTHY, exports=doors, loc=600)})
        self.assertEqual(found(model), [(p.ALL_DOORS, "a/thin.py")])

    def test_unsurveyed_now_only_means_unreadable(self):
        model = build({"a/big.py": {"kind": "unsurveyed"},
                       "a/tool.sh": {"kind": "unsurveyed", "lang": "shell"}})
        self.assertEqual(
            p.find(model, Rows()),
            [p.Problem(p.UNSURVEYED, "a/big.py", p.UNREADABLE),
             p.Problem(p.UNSURVEYED, "a/tool.sh", p.UNREADABLE)])

    def test_floor_buildings_are_never_abandoned_and_say_how_tests_were_sought(self):
        model = build({"a/tool.sh": dict(loc=10, lang="shell", depth="floor")})
        self.assertEqual(p.find(model, Rows()),
                         [p.Problem(p.UNTESTED, "a/tool.sh", "no test found for it by name")])

    def test_other_full_languages_say_no_test_reaches_it(self):
        model = build({"cmd/x/": dict(HEALTHY, tested_by=[], lang="go")})
        self.assertEqual(p.find(model, Rows()),
                         [p.Problem(p.UNTESTED, "cmd/x/", "no test reaches it")])

    def test_packages_public_and_inline_tested_modules_are_exempt(self):
        model = build({
            "a/index.ts": dict(HEALTHY, is_entry=False, tested_by=[], is_package=True,
                               lang="javascript"),
            "a/lib.rs": dict(HEALTHY, is_entry=False, public=True, lang="rust"),
            "a/x.rs": dict(HEALTHY, tested_by=[], inline_tests=True, lang="rust"),
        })
        self.assertEqual(found(model), [])

    def test_a_parse_error_burns_only_where_the_adapter_allows(self):
        model = build({"a/X.kt": dict(HEALTHY, parse_error="line 2: unexpected }",
                                      burns=False, lang="jvm")})
        self.assertEqual(found(model), [])

    def test_notes_and_unsurveyed(self):
        model = build({"a/x.py": dict(HEALTHY, notes=2), "a/tool.sh": {"kind": "unsurveyed"}})
        self.assertEqual(found(model), [(p.NOTES, "a/x.py"), (p.UNSURVEYED, "a/tool.sh")])

    def test_worst_first(self):
        model = build({"a/x.py": dict(HEALTHY, notes=1, parse_error="line 1: bad")})
        self.assertEqual([x.kind for x in p.find(model, Rows())], [p.FIRE, p.NOTES])


if __name__ == "__main__":
    unittest.main()
