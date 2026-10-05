import unittest

import lang_rust
import langkit
import problems
from langtest import edges, needs_grammar, survey_files
from layers import Rows


def _tree(text, path="src/lib.rs"):
    return langkit.parse("rust", text)


class RustAdapterTest(unittest.TestCase):
    @needs_grammar("rust")
    def test_mod_in_lib_reaches_parser_file(self):
        model = survey_files(self, {
            "Cargo.toml": '[package]\nname = "app"\nversion = "0.1.0"\n',
            "src/lib.rs": "mod parser;\n",
            "src/parser.rs": "pub struct Token {}\n",
        })
        self.assertEqual(edges(model), {("src/lib.rs", "src/parser.rs")})

    @needs_grammar("rust")
    def test_mod_in_mod_rs_and_sibling_rs_reach_tcp(self):
        model = survey_files(self, {
            "Cargo.toml": '[package]\nname = "app"\nversion = "0.1.0"\n',
            "src/net/mod.rs": "mod tcp;\n",
            "src/net/tcp.rs": "use super::util;\n",
            "src/net/util.rs": "pub fn u() {}\n",
        })
        self.assertIn(("src/net/mod.rs", "src/net/tcp.rs"), edges(model))

    @needs_grammar("rust")
    def test_mod_in_net_rs_reaches_tcp(self):
        model = survey_files(self, {
            "Cargo.toml": '[package]\nname = "app"\nversion = "0.1.0"\n',
            "src/net.rs": "mod tcp;\n",
            "src/net/tcp.rs": "pub fn t() {}\n",
        })
        self.assertEqual(edges(model), {("src/net.rs", "src/net/tcp.rs")})

    @needs_grammar("rust")
    def test_path_attribute_reaches_override(self):
        model = survey_files(self, {
            "Cargo.toml": '[package]\nname = "app"\nversion = "0.1.0"\n',
            "src/lib.rs": '#[path = "imp/unix.rs"]\nmod sys;\n',
            "src/imp/unix.rs": "pub fn u() {}\n",
        })
        self.assertEqual(edges(model), {("src/lib.rs", "src/imp/unix.rs")})

    @needs_grammar("rust")
    def test_use_crate_reaches_parser(self):
        model = survey_files(self, {
            "Cargo.toml": '[package]\nname = "app"\nversion = "0.1.0"\n',
            "src/main.rs": "mod parser;\nuse crate::parser::Token;\nfn main() {}\n",
            "src/parser.rs": "pub struct Token {}\n",
        })
        self.assertIn(("src/main.rs", "src/parser.rs"), edges(model))

    @needs_grammar("rust")
    def test_use_super_reaches_util(self):
        model = survey_files(self, {
            "Cargo.toml": '[package]\nname = "app"\nversion = "0.1.0"\n',
            "src/net/mod.rs": "mod tcp;\nmod util;\n",
            "src/net/tcp.rs": "use super::util;\n",
            "src/net/util.rs": "pub fn u() {}\n",
        })
        self.assertIn(("src/net/tcp.rs", "src/net/util.rs"), edges(model))

    @needs_grammar("rust")
    def test_braced_use_gives_two_roads(self):
        model = survey_files(self, {
            "Cargo.toml": '[package]\nname = "app"\nversion = "0.1.0"\n',
            "src/lib.rs": "mod a;\nmod b;\nmod c;\n",
            "src/a.rs": "pub fn b() {}\n",
            "src/b.rs": "pub fn b() {}\n",
            "src/c.rs": "pub fn d() {}\n",
            "src/main.rs": "mod a; mod b; mod c;\nuse crate::a::{b, c::d};\nfn main() {}\n",
        })
        self.assertIn(("src/main.rs", "src/a.rs"), edges(model))
        self.assertIn(("src/main.rs", "src/c.rs"), edges(model))

    @needs_grammar("rust")
    def test_workspace_path_dependency(self):
        model = survey_files(self, {
            "Cargo.toml": ('[workspace]\nmembers = ["crates/*"]\n\n'
                           '[workspace.dependencies]\n'),
            "crates/app/Cargo.toml": ('[package]\nname = "app"\nversion = "0.1.0"\n\n'
                                      '[dependencies]\ncore-lib = { path = "../core-lib" }\n'),
            "crates/core-lib/Cargo.toml": '[package]\nname = "core-lib"\nversion = "0.1.0"\n',
            "crates/app/src/main.rs": "fn main() { core_lib::x(); }\n",
            "crates/core-lib/src/lib.rs": "pub fn x() {}\n",
        })
        self.assertIn(("crates/app/src/main.rs", "crates/core-lib/src/lib.rs"), edges(model))

    @needs_grammar("rust")
    def test_std_has_no_warehouse_and_serde_does(self):
        model = survey_files(self, {
            "Cargo.toml": ('[package]\nname = "app"\nversion = "0.1.0"\n\n'
                           '[dependencies]\nserde = "1"\n'),
            "src/main.rs": "use std::collections::HashMap;\nuse serde::Deserialize;\nfn main() {}\n",
        })
        self.assertEqual(model.externals, {"serde": ["src/main.rs"]})

    @needs_grammar("rust")
    def test_reference_in_code_gives_road(self):
        model = survey_files(self, {
            "Cargo.toml": '[package]\nname = "app"\nversion = "0.1.0"\n',
            "src/lib.rs": "mod config;\n",
            "src/config.rs": "pub fn load() {}\n",
            "src/main.rs": "mod config;\nfn main() { crate::config::load(); }\n",
        })
        self.assertIn(("src/main.rs", "src/config.rs"), edges(model))

    @needs_grammar("rust")
    def test_exports(self):
        text = """pub fn a() {}
pub(crate) fn b() {}
fn c() {}
pub struct S {}
pub use x::Y;
pub mod m;
"""
        fx = lang_rust.scan("src/lib.rs", text, _tree(text))
        self.assertEqual(set(fx.exports), {"a", "S", "Y", "m"})

    @needs_grammar("rust")
    def test_complexity_counts_each_construct(self):
        text = """fn f() {
    if true {}
    match x { _ => {} }
    for x in y {}
    while x {}
    loop {}
    let _ = true && false;
}
"""
        fx = lang_rust.scan("src/f.rs", text, _tree(text))
        self.assertEqual(fx.complexity, 7)

    @needs_grammar("rust")
    def test_entry_points(self):
        model = survey_files(self, {
            "Cargo.toml": '[package]\nname = "app"\nversion = "0.1.0"\n',
            "src/main.rs": "fn main() {}\n",
            "src/bin/tool.rs": "fn main() {}\n",
            "build.rs": "fn main() {}\n",
        })
        self.assertTrue(model.modules["src/main.rs"].is_entry)
        self.assertTrue(model.modules["src/bin/tool.rs"].is_entry)
        self.assertTrue(model.modules["build.rs"].is_entry)

    @needs_grammar("rust")
    def test_inline_tests(self):
        model = survey_files(self, {
            "Cargo.toml": '[package]\nname = "app"\nversion = "0.1.0"\n',
            "src/lib.rs": "#[cfg(test)]\nmod tests { #[test] fn t() {} }\n",
        })
        self.assertTrue(model.modules["src/lib.rs"].inline_tests)

    @needs_grammar("rust")
    def test_integration_test_links_source(self):
        model = survey_files(self, {
            "Cargo.toml": '[package]\nname = "mycrate"\nversion = "0.1.0"\n',
            "src/lib.rs": "pub mod api;\n",
            "src/api.rs": "pub fn f() {}\n",
            "tests/api.rs": "use mycrate::api;\n#[test] fn t() { api::f(); }\n",
        })
        self.assertEqual(model.modules["src/api.rs"].tested_by, ["tests/api.rs"])

    @needs_grammar("rust")
    def test_lib_with_only_mod_and_use_is_package(self):
        model = survey_files(self, {
            "Cargo.toml": '[package]\nname = "app"\nversion = "0.1.0"\n',
            "src/lib.rs": "mod a;\npub use a::f;\n",
            "src/a.rs": "pub fn f() {}\n",
        })
        self.assertTrue(model.modules["src/lib.rs"].is_package)

    @needs_grammar("rust")
    def test_syntax_error_is_fire_macro_weird_is_not(self):
        model = survey_files(self, {
            "Cargo.toml": '[package]\nname = "app"\nversion = "0.1.0"\n',
            "src/bad.rs": "fn (\n",
            "src/ok.rs": "macro_rules! m { ($x:expr) => { $x + } }\n",
        })
        self.assertTrue(model.modules["src/bad.rs"].parse_error)
        self.assertTrue(model.modules["src/bad.rs"].burns)
        self.assertFalse(model.modules["src/ok.rs"].parse_error)

    @needs_grammar("rust")
    def test_child_backrefs_to_parent_make_no_cycle(self):
        model = survey_files(self, {
            "Cargo.toml": '[package]\nname = "app"\nversion = "0.1.0"\n',
            "src/lib.rs": "mod child;\npub fn parent_fn() {}\n",
            "src/child.rs": "use super::parent_fn;\nfn x() { crate::parent_fn(); }\n",
        })
        self.assertEqual(edges(model), {("src/lib.rs", "src/child.rs")})
        rows = Rows().update(model)
        cycles = [p for p in problems.find(model, rows) if p.kind == problems.CYCLE]
        self.assertEqual(cycles, [])

    @needs_grammar("rust")
    def test_sibling_modules_using_each_other_cycle(self):
        model = survey_files(self, {
            "Cargo.toml": '[package]\nname = "app"\nversion = "0.1.0"\n',
            "src/lib.rs": "mod a;\nmod b;\n",
            "src/a.rs": "use crate::b;\n",
            "src/b.rs": "use crate::a;\n",
        })
        rows = Rows().update(model)
        cycles = {p.module for p in problems.find(model, rows) if p.kind == problems.CYCLE}
        self.assertIn("src/a.rs", cycles)
        self.assertIn("src/b.rs", cycles)

    @needs_grammar("rust")
    def test_super_super_reaches_grandparent_sibling(self):
        model = survey_files(self, {
            "Cargo.toml": '[package]\nname = "app"\nversion = "0.1.0"\n',
            "src/lib.rs": "mod net;\nmod other;\n",
            "src/other.rs": "pub fn grand_fn() {}\n",
            "src/net.rs": "mod tcp;\n",
            "src/net/tcp.rs": "use super::super::other::grand_fn;\n",
        })
        self.assertIn(("src/net/tcp.rs", "src/other.rs"), edges(model))

    @needs_grammar("rust")
    def test_functions_include_methods_but_not_inline_tests(self):
        model = survey_files(self, {
            "Cargo.toml": '[package]\nname = "app"\nversion = "0.1.0"\n',
            "src/lib.rs": "fn f(x: i32) -> i32 {\n    if x > 0 { 1 } else { 0 }\n}\n\n"
                          "impl S {\n    pub fn m(&self) {\n        let c = || 1;\n    }\n}\n\n"
                          "#[cfg(test)]\nmod tests {\n    fn t() {}\n}\n",
        })
        self.assertEqual(model.modules["src/lib.rs"].functions, [("f", 3, 2), ("m", 3, 1)])

    @needs_grammar("rust")
    def test_a_binary_declared_at_its_own_path_is_an_entry(self):
        model = survey_files(self, {
            "Cargo.toml": '[package]\nname = "app"\nversion = "0.1.0"\n\n'
                          '[[bin]]\nname = "app"\npath = "crates/core/main.rs"\n',
            "crates/core/main.rs": "fn main() {}\n",
        })
        self.assertTrue(model.modules["crates/core/main.rs"].is_entry)


if __name__ == "__main__":
    unittest.main()
