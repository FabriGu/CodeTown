import unittest

import lang_go
import langkit
import problems
from layers import Rows
from langtest import edges, needs_grammar, survey_files


def _tree(text, path="x.go"):
    return langkit.parse("go", text)


class GoAdapterTest(unittest.TestCase):
    @needs_grammar("go")
    def test_two_files_in_one_folder_form_one_building(self):
        model = survey_files(self, {
            "go.mod": "module example.com/m\n",
            "pkg/a/one.go": "package a\n",
            "pkg/a/two.go": "package a\n",
        })
        mod = model.modules["pkg/a/"]
        self.assertEqual(mod.loc, 2)
        self.assertEqual(sorted(mod.members), ["pkg/a/one.go", "pkg/a/two.go"])

    @needs_grammar("go")
    def test_internal_import_is_a_road(self):
        model = survey_files(self, {
            "go.mod": "module example.com/m\n",
            "cmd/x/main.go": 'package main\n\nimport "example.com/m/pkg/a"\n\nfunc main() {}\n',
            "pkg/a/a.go": "package a\n",
        })
        self.assertEqual(edges(model), {("cmd/x/", "pkg/a/")})

    @needs_grammar("go")
    def test_root_main_belongs_to_dot_slash(self):
        model = survey_files(self, {
            "go.mod": "module example.com/m\n",
            "main.go": "package main\n\nfunc main() {}\n",
        })
        self.assertIn("./", model.modules)

    @needs_grammar("go")
    def test_go_work_links_modules(self):
        model = survey_files(self, {
            "go.work": "go 1.21\n\nuse (\n\t./a\n\t./b\n)\n",
            "a/go.mod": "module example.com/a\n",
            "a/a.go": 'package a\n\nimport "example.com/b"\n',
            "b/go.mod": "module example.com/b\n",
            "b/b.go": "package b\n",
        })
        self.assertEqual(edges(model), {("a/", "b/")})

    @needs_grammar("go")
    def test_replace_resolves_local_modules(self):
        model = survey_files(self, {
            "go.mod": "module example.com/app\n\nreplace example.com/lib => ./lib\n",
            "main.go": 'package main\n\nimport "example.com/lib/sub"\n\nfunc main() {}\n',
            "lib/go.mod": "module example.com/lib\n",
            "lib/sub/sub.go": "package sub\n",
        })
        self.assertEqual(edges(model), {("./", "lib/sub/")})

    @needs_grammar("go")
    def test_stdlib_imports_have_no_warehouse(self):
        model = survey_files(self, {
            "go.mod": "module example.com/m\n",
            "main.go": 'package main\n\nimport (\n\t"fmt"\n\t"net/http"\n)\n\nfunc main() {}\n',
        })
        self.assertEqual(model.externals, {})

    @needs_grammar("go")
    def test_github_warehouse_is_three_segments(self):
        model = survey_files(self, {
            "go.mod": "module example.com/m\n",
            "main.go": 'package main\n\nimport "github.com/spf13/cobra/doc"\n\nfunc main() {}\n',
        })
        self.assertEqual(model.externals, {"github.com/spf13/cobra": ["./"]})

    @needs_grammar("go")
    def test_require_prefix_wins_for_warehouse(self):
        model = survey_files(self, {
            "go.mod": ("module example.com/m\n\n"
                       "require github.com/aws/aws-sdk-go-v2/service/s3 v1.0.0\n"),
            "main.go": ('package main\n\nimport '
                        '"github.com/aws/aws-sdk-go-v2/service/s3/types"\n\nfunc main() {}\n'),
        })
        self.assertEqual(
            model.externals,
            {"github.com/aws/aws-sdk-go-v2/service/s3": ["./"]},
        )

    @needs_grammar("go")
    def test_exports_are_uppercase_top_level_only(self):
        text = """package p

type Exported struct{}
type hidden int

func ExportedFunc() {}
func (Exported) Method() {}
func hiddenFunc() {}

var ExportedVar = 1
const ExportedConst = 1
"""
        fx = lang_go.scan("p.go", text, _tree(text))
        self.assertEqual(
            set(fx.exports),
            {"Exported", "ExportedFunc", "ExportedVar", "ExportedConst"},
        )

    @needs_grammar("go")
    def test_complexity_counts_each_construct(self):
        text = """package p

func f(x interface{}, ch chan int) {
    if true && false {}
    for {}
    switch x.(type) {
    case int:
    }
    switch x {
    case 1:
    }
    select {
    case <-ch:
    }
}
"""
        fx = lang_go.scan("p.go", text, _tree(text))
        self.assertEqual(fx.complexity, 7)

    @needs_grammar("go")
    def test_main_package_with_main_is_entry(self):
        model = survey_files(self, {
            "go.mod": "module example.com/m\n",
            "main.go": "package main\n\nfunc main() {}\n",
        })
        self.assertTrue(model.modules["./"].is_entry)

    @needs_grammar("go")
    def test_main_package_without_main_is_not_entry(self):
        model = survey_files(self, {
            "go.mod": "module example.com/m\n",
            "main.go": "package main\n\nfunc run() {}\n",
        })
        self.assertFalse(model.modules["./"].is_entry)

    @needs_grammar("go")
    def test_internal_unimported_is_abandoned_public_is_not(self):
        model = survey_files(self, {
            "go.mod": "module example.com/m\n",
            "internal/hidden/hidden.go": "package hidden\n",
            "pkg/open/open.go": "package open\n",
        })
        mods = model.modules
        self.assertFalse(mods["internal/hidden/"].public)
        self.assertTrue(mods["pkg/open/"].public)
        rows = Rows().update(model)
        found = problems.find(model, rows)
        abandoned = {p.module for p in found if p.kind == "abandoned"}
        self.assertIn("internal/hidden/", abandoned)
        self.assertNotIn("pkg/open/", abandoned)

    @needs_grammar("go")
    def test_same_folder_test_links_through_tests_for(self):
        model = survey_files(self, {
            "go.mod": "module example.com/m\n",
            "pkg/a/a.go": "package a\n",
            "pkg/a/a_test.go": "package a\n\nfunc TestA(t *testing.T) {}\n",
        })
        self.assertEqual(model.modules["pkg/a/"].tested_by, ["pkg/a/a_test.go"])

    @needs_grammar("go")
    def test_generated_build_ignore_and_testdata_are_excluded(self):
        model = survey_files(self, {
            "go.mod": "module example.com/m\n",
            "pkg/a/real.go": "package a\n",
            "pkg/a/gen.go": ("// Code generated by protoc-gen-go. DO NOT EDIT.\n\n"
                             "package a\n\nfunc Gen() {}\n"),
            "pkg/a/ignore.go": "//go:build ignore\n\npackage a\n",
            "pkg/a/testdata/x.go": "package x\n",
        })
        mod = model.modules["pkg/a/"]
        self.assertEqual(mod.loc, 1)
        self.assertEqual(mod.members, ["pkg/a/real.go"])

    @needs_grammar("go")
    def test_syntax_error_sets_fire_on_the_folder(self):
        model = survey_files(self, {
            "go.mod": "module example.com/m\n",
            "pkg/a/good.go": "package a\n",
            "pkg/a/bad.go": "package a\n\nfunc bad() {\n",
        })
        mod = model.modules["pkg/a/"]
        self.assertTrue(mod.parse_error)
        self.assertTrue(mod.parse_error.startswith("bad.go:"))
        rows = Rows().update(model)
        fires = [p for p in problems.find(model, rows) if p.kind == "won't parse"]
        self.assertEqual(len(fires), 1)
        self.assertEqual(fires[0].module, "pkg/a/")

    @needs_grammar("go")
    def test_a_package_building_has_every_file_s_functions_in_file_order(self):
        model = survey_files(self, {
            "go.mod": "module example.com/m\n",
            "pkg/a/one.go": "package a\n\nfunc A() {\n\tg := func() {}\n\t_ = g\n}\n",
            "pkg/a/two.go": "package a\n\nfunc (s S) B() {\n\tif true && false {}\n}\n",
        })
        self.assertEqual(model.modules["pkg/a/"].functions, [("A", 4, 1), ("B", 3, 3)])

    @needs_grammar("go")
    def test_the_sample_town(self):
        model = survey_files(self, lang_go.SAMPLE)
        self.assertEqual(edges(model), {("cmd/", "pkg/a/")})
        self.assertEqual(model.modules["pkg/a/"].tested_by, ["pkg/a/a_test.go"])


if __name__ == "__main__":
    unittest.main()
