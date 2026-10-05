import unittest

import lang_cfamily
import langkit
import langs
import problems
from layers import Rows
from langtest import edges, needs_grammar, survey_files


def _tree(text, path="x.c", files=frozenset()):
    grammar = langs.grammar_for(lang_cfamily, path, files)
    return langkit.parse(grammar, text)


class CfamilyAdapterTest(unittest.TestCase):
    @needs_grammar("c", "cpp")
    def test_header_and_source_in_same_folder_form_one_building(self):
        files = {
            "src/net.h": "void net_init(void);\n",
            "src/net.c": '#include "net.h"\nvoid net_init(void) {}\n',
        }
        model = survey_files(self, files)
        mod = model.modules["src/net.h"]
        self.assertEqual(sorted(mod.members), ["src/net.c", "src/net.h"])
        self.assertNotIn(("src/net.h", "src/net.h"), edges(model))

    @needs_grammar("cpp")
    def test_mirror_pairing_include_and_src(self):
        files = {
            "include/fmt/format.h": "namespace fmt {}\n",
            "src/format.cc": '#include "fmt/format.h"\n',
        }
        model = survey_files(self, files)
        self.assertIn("include/fmt/format.h", model.modules)
        self.assertEqual(sorted(model.modules["include/fmt/format.h"].members),
                         ["include/fmt/format.h", "src/format.cc"])

    @needs_grammar("c")
    def test_ambiguous_header_candidates_do_not_pair(self):
        files = {
            "src/a.h": "void a(void);\n",
            "src/a.hpp": "void a_cpp(void);\n",
            "src/a.c": "void a(void) {}\n",
        }
        model = survey_files(self, files)
        self.assertNotIn("src/a.c", model.modules.get("src/a.h", type("", (), {"members": []})()).members
                         if "src/a.h" in model.modules else [])
        mod = model.modules["src/a.c"]
        self.assertEqual(mod.id, "src/a.c")

    @needs_grammar("c")
    def test_cmake_include_directories_reaches_nested_header(self):
        files = {
            "CMakeLists.txt": "include_directories(lib)\n",
            "app.c": '#include "util/str.h"\n',
            "lib/util/str.h": "void str(void);\n",
        }
        model = survey_files(self, files)
        self.assertEqual(edges(model), {("app.c", "lib/util/str.h")})

    @needs_grammar("c")
    def test_makefile_i_flag_reaches_angle_include(self):
        files = {
            "Makefile": "CFLAGS = -Ithird/include\n",
            "main.c": "#include <dep.h>\n",
            "third/include/dep.h": "void dep(void);\n",
        }
        model = survey_files(self, files)
        self.assertEqual(edges(model), {("main.c", "third/include/dep.h")})

    @needs_grammar("c")
    def test_importer_folder_wins_over_include_directory(self):
        files = {
            "CMakeLists.txt": "include_directories(other)\n",
            "src/main.c": '#include "local.h"\n',
            "src/local.h": "void local(void);\n",
            "other/local.h": "void other(void);\n",
        }
        model = survey_files(self, files)
        self.assertEqual(edges(model), {("src/main.c", "src/local.h")})

    @needs_grammar("c")
    def test_suffix_fallback_unique_match(self):
        files = {
            "a/main.c": '#include "msg.h"\n',
            "lib/proto/msg.h": "void msg(void);\n",
        }
        model = survey_files(self, files)
        self.assertEqual(edges(model), {("a/main.c", "lib/proto/msg.h")})

    @needs_grammar("c")
    def test_suffix_fallback_ambiguous_reaches_nothing(self):
        files = {
            "main.c": '#include "msg.h"\n',
            "x/proto/msg.h": "void x(void);\n",
            "y/proto/msg.h": "void y(void);\n",
        }
        model = survey_files(self, files)
        self.assertEqual(edges(model), set())

    @needs_grammar("c", "cpp")
    def test_system_headers_have_no_warehouse(self):
        files = {
            "main.c": '#include <stdio.h>\n',
            "main.cpp": "#include <vector>\n#include <sys/socket.h>\n",
        }
        model = survey_files(self, files)
        self.assertEqual(model.externals, {})

    @needs_grammar("c")
    def test_external_angle_include_gets_warehouse(self):
        model = survey_files(self, {"main.c": "#include <openssl/ssl.h>\n"})
        self.assertEqual(model.externals, {"openssl": ["main.c"]})

    @needs_grammar("c")
    def test_angle_include_reaches_tracked_header_by_suffix(self):
        files = {
            "main.c": "#include <lib/util.h>\n",
            "include/lib/util.h": "void util(void);\n",
        }
        model = survey_files(self, files)
        self.assertEqual(edges(model), {("main.c", "include/lib/util.h")})
        self.assertEqual(model.externals, {})

    @needs_grammar("c")
    def test_ambiguous_angle_suffix_gives_no_road_or_warehouse(self):
        files = {
            "main.c": "#include <lib/util.h>\n",
            "a/lib/util.h": "void a(void);\n",
            "b/lib/util.h": "void b(void);\n",
        }
        model = survey_files(self, files)
        self.assertEqual(edges(model), set())
        self.assertEqual(model.externals, {})

    @needs_grammar("c")
    def test_quote_include_reaches_unique_suffix_after_relative_miss(self):
        files = {
            "src/main.c": '#include "lib/util.h"\n',
            "include/lib/util.h": "void util(void);\n",
        }
        model = survey_files(self, files)
        self.assertEqual(edges(model), {("src/main.c", "include/lib/util.h")})
        self.assertEqual(model.externals, {})

    @needs_grammar("c", "cpp")
    def test_h_grammar_follows_repository_dialect(self):
        pure_c = frozenset(["a.h", "a.c"])
        mixed = frozenset(["a.h", "a.cpp"])
        self.assertEqual(langs.grammar_for(lang_cfamily, "a.h", pure_c), "c")
        self.assertEqual(langs.grammar_for(lang_cfamily, "a.h", mixed), "cpp")

    @needs_grammar("c", "cpp")
    def test_exports_and_paired_unit_doors(self):
        header = """
#ifndef FOO_H
#define FOO_H
struct Point { int x; };
typedef int MyInt;
void foo(void);
#define BAR 42
#endif
"""
        source = "static void hidden(void) {}\nvoid visible(void) {}\n"
        files = {"src/foo.h": header, "src/foo.c": source}
        model = survey_files(self, files)
        mod = model.modules["src/foo.h"]
        self.assertEqual(set(mod.exports), {"BAR", "Point", "MyInt", "foo"})
        self.assertNotIn("hidden", mod.exports)
        self.assertNotIn("visible", mod.exports)
        alone = survey_files(self, {"alone.c": source})
        self.assertIn("visible", alone.modules["alone.c"].exports)
        self.assertNotIn("hidden", alone.modules["alone.c"].exports)

    @needs_grammar("c", "cpp")
    def test_complexity_counts_control_flow_and_preprocessor(self):
        c_text = """
#ifdef F
if (1) {}
#endif
while (1) {}
for (;;) {}
do {} while(0);
switch (x) { case 1: break; }
int y = a ? b : c;
if (p && q || r) {}
"""
        c_tree = _tree(c_text, "x.c")
        c_facts = lang_cfamily.scan("x.c", c_text, c_tree)
        self.assertEqual(c_facts.complexity, 11)
        cpp_text = c_text + """
for (auto x : v) {}
try {} catch (int e) {}
"""
        cpp_tree = _tree(cpp_text, "x.cpp")
        cpp_facts = lang_cfamily.scan("x.cpp", cpp_text, cpp_tree)
        self.assertEqual(cpp_facts.complexity, 13)

    @needs_grammar("c")
    def test_main_is_entry(self):
        model = survey_files(self, {"main.c": "int main(void) { return 0; }\n"})
        self.assertTrue(model.modules["main.c"].is_entry)

    @needs_grammar("c")
    def test_test_includes_link_tested_by(self):
        files = {
            "src/net.h": "void net_init(void);\n",
            "src/net.c": "void net_init(void) {}\n",
            "tests/net_test.c": '#include "net.h"\n',
        }
        model = survey_files(self, files)
        self.assertEqual(model.modules["src/net.h"].tested_by, ["tests/net_test.c"])

    @needs_grammar("c")
    def test_generated_and_build_paths_are_excluded(self):
        model = survey_files(self, {
            "build/gen.h": "void gen(void);\n",
            "msg.pb.h": "void pb(void);\n",
            "src/ok.c": "void ok(void) {}\n",
        })
        self.assertNotIn("build/gen.h", model.modules)
        self.assertNotIn("msg.pb.h", model.modules)
        self.assertIn("src/ok.c", model.modules)

    @needs_grammar("c")
    def test_parse_error_without_fire(self):
        model = survey_files(self, {"bad.c": "int main( { return 0; }\n"})
        mod = model.modules["bad.c"]
        self.assertTrue(mod.parse_error)
        self.assertFalse(mod.burns)
        found = problems.find(model, Rows().update(model))
        self.assertFalse(any(p.kind == problems.FIRE for p in found))

    @needs_grammar("c", "cpp")
    def test_functions_are_named_by_their_declarator(self):
        model = survey_files(self, {
            "a.c": "static int f(int x) {\n  if (x > 0 && x < 9) return 1;\n  return 0;\n}\n\n"
                   "int *g(void) { return 0; }\n",
            "b.cpp": "namespace n {\nint A::f(int x) {\n  for (auto y : v) {}\n"
                     "  auto l = [](){ return 1; };\n  return 0;\n}\n"
                     "template <class T> T g(T t) { return t; }\n}\n",
        })
        self.assertEqual(model.modules["a.c"].functions, [("f", 4, 3), ("g", 1, 1)])
        self.assertEqual(model.modules["b.cpp"].functions, [("A::f", 5, 2), ("g", 1, 1)])
