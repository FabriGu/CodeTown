import unittest

import lang_jvm
import langkit
import langs
from langtest import edges, needs_grammar, survey_files


def _facts(files):
    out = {}
    file_set = frozenset(files)
    for path, text in files.items():
        tree = langkit.parse(langs.grammar_for(lang_jvm, path, file_set), text)
        out[path] = lang_jvm.scan(path, text, tree)
    resolver = lang_jvm.resolver(out, {}, tuple(files))
    return out, resolver


@needs_grammar("java", "kotlin")
class JvmAdapterTest(unittest.TestCase):
    def test_the_sample_town(self):
        model = survey_files(self, lang_jvm.SAMPLE)
        mods = model.modules
        self.assertIn(("src/main/java/com/a/App.java", "lib/com/b/Util.java"), edges(model))
        self.assertEqual(model.externals, {})
        self.assertEqual(mods["src/test/java/com/a/AppTest.java"].kind, "test")
        self.assertEqual(mods["src/main/java/com/a/App.java"].tested_by,
                         ["src/test/java/com/a/AppTest.java"])
        self.assertTrue(mods["src/main/java/com/a/App.java"].is_entry)

    def test_package_import_reaches_util_anywhere(self):
        files = {
            "com/a/App.java": "package com.a;\nimport com.b.Util;\nclass App { Util u; }\n",
            "lib/com/b/Util.java": "package com.b;\npublic class Util {}\n",
        }
        _, resolver = _facts(files)
        hit, outside = resolver.resolve("com/a/App.java", langkit.Import("com.b.Util"))
        self.assertEqual(hit, frozenset(["lib/com/b/Util.java"]))
        self.assertIsNone(outside)

    def test_static_import_reaches_util(self):
        files = {
            "com/a/App.java": "package com.a;\nimport static com.b.Util.helper;\nclass App {}\n",
            "com/b/Util.java": "package com.b;\npublic class Util { static void helper() {} }\n",
        }
        _, resolver = _facts(files)
        hit, _ = resolver.resolve("com/a/App.java", langkit.Import("com.b.Util"))
        self.assertEqual(hit, frozenset(["com/b/Util.java"]))

    def test_wildcard_reaches_only_used_types(self):
        files = {
            "com/a/App.java": "package com.a;\nimport com.b.*;\nclass App { Util u; Other o; }\n",
            "com/b/Util.java": "package com.b;\nclass Util {}\n",
            "com/b/Unused.java": "package com.b;\nclass Unused {}\n",
            "com/b/Other.java": "package com.b;\nclass Other {}\n",
        }
        _, resolver = _facts(files)
        model = survey_files(self, files)
        self.assertEqual(edges(model), {
            ("com/a/App.java", "com/b/Util.java"),
            ("com/a/App.java", "com/b/Other.java"),
        })
        self.assertNotIn(("com/a/App.java", "com/b/Unused.java"), edges(model))

    def test_same_package_references(self):
        files = {
            "com/a/A.java": "package com.a;\nclass A { B b; }\n",
            "com/a/B.java": "package com.a;\nclass B { A a; }\n",
        }
        model = survey_files(self, files)
        self.assertEqual(edges(model), {
            ("com/a/A.java", "com/a/B.java"),
            ("com/a/B.java", "com/a/A.java"),
        })

    def test_nested_import_reaches_outer(self):
        files = {
            "com/a/App.java": "package com.a;\nimport com.b.Outer.Inner;\nclass App { Inner i; }\n",
            "com/b/Outer.java": "package com.b;\npublic class Outer { static class Inner {} }\n",
        }
        _, resolver = _facts(files)
        hit, _ = resolver.resolve("com/a/App.java", langkit.Import("com.b.Outer.Inner"))
        self.assertEqual(hit, frozenset(["com/b/Outer.java"]))

    def test_kotlin_java_cross_reach(self):
        files = {
            "com/a/App.kt": "package com.a\nimport com.b.Util\nfun f() { Util() }\n",
            "com/b/Util.java": "package com.b;\npublic class Util {}\n",
            "com/a/Helper.java": "package com.a;\nclass Helper { Kt k; }\n",
            "com/a/Kt.kt": "package com.a\nclass Kt\n",
        }
        model = survey_files(self, files)
        self.assertIn(("com/a/App.kt", "com/b/Util.java"), edges(model))
        self.assertIn(("com/a/Helper.java", "com/a/Kt.kt"), edges(model))

    def test_kotlin_top_level_function_import(self):
        files = {
            "com/a/App.kt": "package com.a\nimport com.b.formatName\nfun f() = formatName()\n",
            "com/b/Util.kt": "package com.b\nfun formatName() = \"x\"\n",
        }
        _, resolver = _facts(files)
        hit, _ = resolver.resolve("com/a/App.kt", langkit.Import("com.b.formatName"))
        self.assertEqual(hit, frozenset(["com/b/Util.kt"]))

    def test_stdlib_and_external_warehouses(self):
        files = {
            "com/a/App.java": (
                "package com.a;\nimport java.util.List;\nimport kotlin.collections.List;\n"
                "import org.junit.jupiter.api.Test;\nclass App {}\n"
            ),
        }
        _, resolver = _facts(files)
        for spec in ("java.util.List", "kotlin.collections.List"):
            hit, outside = resolver.resolve("com/a/App.java", langkit.Import(spec))
            self.assertEqual(hit, frozenset())
            self.assertIsNone(outside)
        hit, outside = resolver.resolve("com/a/App.java",
                                        langkit.Import("org.junit.jupiter.api.Test"))
        self.assertEqual(hit, frozenset())
        self.assertEqual(outside, "org.junit")

    def test_ambiguous_duplicate_declarations(self):
        files = {
            "com/a/A.java": "package com.a;\nclass A { Dup d; }\n",
            "com/a/Dup1.java": "package com.a;\nclass Dup {}\n",
            "com/a/Dup2.java": "package com.a;\nclass Dup {}\n",
        }
        _, resolver = _facts(files)
        hit, _ = resolver.resolve("com/a/A.java", langkit.Import("Dup", kind="reference"))
        self.assertEqual(hit, frozenset())

    def test_java_exports(self):
        java = (
            "public class Pub {\n"
            "    public void a() {}\n"
            "    public void b() {}\n"
            "    private void c() {}\n"
            "    public int field;\n"
            "}\n"
        )
        tree = langkit.parse("java", java)
        fx = lang_jvm.scan("Pub.java", java, tree)
        self.assertEqual(set(fx.exports), {"Pub", "a", "b", "field"})

    def test_kotlin_private_top_level_not_exported(self):
        kt = "private fun hidden() {}\nfun visible() {}\n"
        tree = langkit.parse("kotlin", kt)
        fx = lang_jvm.scan("H.kt", kt, tree)
        self.assertEqual(fx.exports, ("visible",))

    def test_java_complexity(self):
        java = (
            "class X {\n"
            "    void f() {\n"
            "        if (a) {}\n"
            "        for (int i=0;;) {}\n"
            "        for (T x : xs) {}\n"
            "        while (true) {}\n"
            "        do {} while (true);\n"
            "        switch (x) { case 1: break; }\n"
            "        try {} catch (E e) {}\n"
            "        int y = a ? b : c;\n"
            "        if (a && b) {}\n"
            "        if (a || b) {}\n"
            "    }\n"
            "}\n"
        )
        tree = langkit.parse("java", java)
        fx = lang_jvm.scan("X.java", java, tree)
        self.assertEqual(fx.complexity, 13)

    def test_kotlin_complexity(self):
        kt = (
            "fun f() {\n"
            "    if (a) {}\n"
            "    for (x in xs) {}\n"
            "    while (true) {}\n"
            "    do {} while (true)\n"
            "    when (x) { 1 -> {} }\n"
            "    try {} catch (e: E) {}\n"
            "    x ?: y\n"
            "    a && b\n"
            "    a || b\n"
            "}\n"
        )
        tree = langkit.parse("kotlin", kt)
        fx = lang_jvm.scan("X.kt", kt, tree)
        self.assertEqual(fx.complexity, 10)

    def test_java_main_entry(self):
        java = "public static void main(String[] args) {}\n"
        tree = langkit.parse("java", java)
        fx = lang_jvm.scan("Main.java", java, tree)
        self.assertTrue(fx.is_entry)

    def test_java_non_static_main_not_entry(self):
        java = "public void main(String[] args) {}\n"
        tree = langkit.parse("java", java)
        fx = lang_jvm.scan("Main.java", java, tree)
        self.assertFalse(fx.is_entry)

    def test_kotlin_main_entry(self):
        kt = "fun main() {}\n"
        tree = langkit.parse("kotlin", kt)
        fx = lang_jvm.scan("Main.kt", kt, tree)
        self.assertTrue(fx.is_entry)

    def test_test_file_links_to_source(self):
        files = {
            "src/test/java/com/a/AppTest.java": "package com.a;\nclass AppTest { App a; }\n",
            "src/main/java/com/a/App.java": "package com.a;\nclass App {}\n",
        }
        model = survey_files(self, files)
        self.assertEqual(model.modules["src/main/java/com/a/App.java"].tested_by,
                         ["src/test/java/com/a/AppTest.java"])

    def test_generated_java_excluded(self):
        files = {
            "build/generated/X.java": "// Generated by tool\npackage x;\nclass X {}\n",
            "src/X.java": "class X {}\n",
        }
        model = survey_files(self, files)
        self.assertNotIn("build/generated/X.java", model.modules)
        self.assertIn("src/X.java", model.modules)

    def test_java_syntax_error_on_fire(self):
        files = {"Bad.java": "class Bad { }\n}\n"}
        model = survey_files(self, files)
        self.assertTrue(model.modules["Bad.java"].parse_error)
        self.assertTrue(model.modules["Bad.java"].burns)

    def test_kotlin_syntax_error_fire_follows_setting(self):
        files = {"Bad.kt": "fun bad( }\n"}
        model = survey_files(self, files)
        self.assertTrue(model.modules["Bad.kt"].parse_error)
        self.assertEqual(model.modules["Bad.kt"].burns, ".kt" in lang_jvm.FIRE)

    @needs_grammar("java", "kotlin")
    def test_functions_are_methods_and_constructors(self):
        model = survey_files(self, {
            "A.java": "class A {\n  A() {}\n  int f(int x) {\n    if (x > 0 && x < 9) return 1;\n"
                      "    Runnable r = () -> {};\n    return 0;\n  }\n}\n",
            "B.kt": "class B {\n  constructor(x: Int) {}\n  fun f(x: Int): Int {\n"
                    "    if (x > 0 && x < 9) return 1\n    val l = { 1 }\n    return 0\n  }\n}\n"
                    "fun String.ext() = 1\n",
        })
        self.assertEqual(model.modules["A.java"].functions, [("A", 1, 1), ("f", 5, 3)])
        self.assertEqual(model.modules["B.kt"].functions,
                         [("constructor", 1, 1), ("f", 5, 3), ("ext", 1, 1)])


if __name__ == "__main__":
    unittest.main()
