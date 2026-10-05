"""The adapter registry, the contract every adapter keeps, and the survey around them."""

import builtins
import contextlib
import io
import os
import socket
import subprocess
import sys
import tempfile
import types
import unittest
from unittest import mock

import fixture
import langkit
import langs
import survey
import towncode
from langtest import edges, needs_grammar, survey_files
from model import Model

BAD_INPUTS = ["", "// only a comment\n# only a comment\n", "{{{ ((( ]]] <<< \n",
              "x" * 200_000, "a\0b\0c\n", "Ünïcødé ✓ 日本語 مرحبا\n"]


def _forbidden(*_, **__):
    raise AssertionError("adapters must not touch files, processes or the network")


@contextlib.contextmanager
def no_world():
    with mock.patch.object(builtins, "open", _forbidden), \
            mock.patch.object(os, "open", _forbidden), \
            mock.patch.object(os, "listdir", _forbidden), \
            mock.patch.object(os, "scandir", _forbidden), \
            mock.patch.object(subprocess, "Popen", _forbidden), \
            mock.patch.object(socket, "socket", _forbidden):
        yield


def _tree(adapter, path, text, files):
    return langkit.parse(langs.grammar_for(adapter, path, files), text)


class ContractTest(unittest.TestCase):
    """Every adapter that imports must keep these, whoever wrote it."""

    def adapters(self):
        found = langs.adapters()
        self.assertIn("python", found)
        return found

    def test_names_match_the_registry_and_constants_are_well_formed(self):
        for name, a in self.adapters().items():
            with self.subTest(adapter=name):
                self.assertEqual(a.NAME, name)
                self.assertTrue(a.LABEL)
                self.assertTrue(a.EXTENSIONS)
                self.assertTrue(all(e.startswith(".") for e in a.EXTENSIONS))
                self.assertTrue(set(a.GRAMMARS) <= set(a.EXTENSIONS))
                self.assertIsInstance(a.SHEBANGS, tuple)
                self.assertIsInstance(a.CONFIG, tuple)
                self.assertTrue(isinstance(a.FIRE, (bool, tuple)))
                self.assertTrue(a.SAMPLE and isinstance(a.SAMPLE, dict))

    def test_no_extension_has_two_owners(self):
        owners = {}
        for name, a in self.adapters().items():
            for ext in a.EXTENSIONS:
                self.assertNotIn(ext, owners, f"{ext} claimed by {owners.get(ext)} and {name}")
                owners[ext] = name

    def test_scan_never_raises_on_bad_input(self):
        for name, a in self.adapters().items():
            if langs.depth_reason(name):
                continue
            for ext in a.EXTENSIONS:
                path = f"src/bad{ext}"
                for text in BAD_INPUTS:
                    with self.subTest(adapter=name, ext=ext, text=text[:20]):
                        facts = a.scan(path, text, _tree(a, path, text, frozenset([path])))
                        self.assertIsInstance(facts, langkit.Facts)

    def test_adapters_only_compute_from_what_they_are_given(self):
        for name, a in self.adapters().items():
            if langs.depth_reason(name):
                continue
            with self.subTest(adapter=name):
                files = tuple(sorted(a.SAMPLE))
                code = [p for p in files if os.path.splitext(p)[1] in a.EXTENSIONS]
                trees = {p: _tree(a, p, a.SAMPLE[p], frozenset(files)) for p in code}
                configs = {p: a.SAMPLE[p] for p in langs.configs_of(a, files)}
                with no_world():
                    facts = {p: a.scan(p, a.SAMPLE[p], trees[p]) for p in code}
                    resolver = a.resolver(facts, configs, files)
                    for p, fx in facts.items():
                        for imp in fx.imports:
                            targets, outside = resolver.resolve(p, imp)
                            self.assertTrue(set(targets) <= set(files), (p, imp, targets))
                            self.assertTrue(outside is None or (isinstance(outside, str)
                                                                and outside))

    def test_functions_are_name_lines_and_complexity(self):
        for name, a in self.adapters().items():
            if langs.depth_reason(name):
                continue
            files = frozenset(a.SAMPLE)
            for p in sorted(f for f in files if os.path.splitext(f)[1] in a.EXTENSIONS):
                with self.subTest(adapter=name, path=p):
                    for fn_name, lines, complexity in a.scan(
                            p, a.SAMPLE[p], _tree(a, p, a.SAMPLE[p], files)).functions:
                        self.assertIsInstance(fn_name, str)
                        self.assertGreaterEqual(lines, 1)
                        self.assertGreaterEqual(complexity, 1)

    def test_functions_survive_a_saved_model_and_floor_buildings_have_none(self):
        model = survey_files(self, {"a.py": "def f():\n    return 1\n",
                                    "b.lua": "function g()\n  return 1\nend\n"})
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "model.json")
            model.save(path)
            loaded = Model.load(path)
        self.assertEqual(loaded.modules["a.py"].functions, [("f", 2, 1)])
        self.assertEqual(loaded.modules, model.modules)
        self.assertEqual(model.modules["b.lua"].depth, "floor")
        self.assertEqual(model.modules["b.lua"].functions, [])

    def test_the_same_sample_gives_the_same_town(self):
        for name, a in self.adapters().items():
            with self.subTest(adapter=name):
                first = survey_files(self, a.SAMPLE).to_dict()
                second = survey_files(self, a.SAMPLE).to_dict()
                first.pop("repo"), second.pop("repo")
                self.assertEqual(first, second)
                self.assertTrue(any(m["lang"] == name for m in first["modules"]))


FAKE_SAMPLE = {"pkg/a/one.fk": "import './../b/two.fk';\n", "pkg/b/two.fk": "export function g() {}\n"}


def _fake_adapter():
    """A small adapter over the javascript grammar that exercises every core path."""
    m = types.ModuleType("lang_fake")
    m.NAME, m.LABEL = "fake", "Fake"
    m.EXTENSIONS, m.SHEBANGS = (".fk",), ("fakerun",)
    m.GRAMMARS, m.CONFIG, m.FIRE = {".fk": "javascript"}, ("fake.json",), (".fk",)
    m.SAMPLE = FAKE_SAMPLE
    m.seen_configs = {}

    def unit_of(path, files):
        parts = path.split("/")
        return "/".join(parts[:2]) + "/" if parts[0] == "pkg" and len(parts) > 2 else path

    def is_test(path, text):
        return path.endswith("_test.fk")

    def scan(path, text, tree):
        root = tree.root_node
        imports = tuple(langkit.Import(langkit.node_text(n))
                        for n in langkit.captures("javascript",
                                                  "(import_statement source: (string "
                                                  "(string_fragment) @s))", root).get("s", []))
        exports = tuple(langkit.node_text(n)
                        for n in langkit.captures("javascript",
                                                  "(export_statement declaration: "
                                                  "(function_declaration name: (identifier) @n))",
                                                  root).get("n", []))
        return langkit.Facts(
            loc=langkit.loc(text, tree, {"comment"}), exports=exports,
            complexity=1 + langkit.count_types(root, ["if_statement"]),
            notes=langkit.notes(tree, {"comment"}), imports=imports,
            parse_error=langkit.first_error(tree), is_entry="// entry" in text,
            public="// public" in text, inline_tests="// inline-tests" in text)

    class Resolver:
        def __init__(self, files, configs):
            self.files, self.configs = set(files), configs

        def resolve(self, path, imp):
            if imp.spec.startswith("lib:"):
                return frozenset(), imp.spec[4:]
            if imp.spec.startswith("dir:"):
                folder = os.path.normpath(os.path.join(os.path.dirname(path), imp.spec[4:]))
                return frozenset(f for f in self.files if os.path.dirname(f) == folder), None
            target = os.path.normpath(os.path.join(os.path.dirname(path), imp.spec))
            return (frozenset([target]) if target in self.files else frozenset()), None

    def resolver(facts, configs, files):
        m.seen_configs = dict(configs)
        return Resolver(files, configs)

    def tests_for(path, facts, files):
        here = os.path.dirname(path)
        return {f for f in facts if os.path.dirname(f) == here and not is_test(f, "")}

    def is_excluded(path, text):
        return "// generated" in text

    def grammar_for(path, files):
        return "javascript"

    def enrich(facts, configs, files):
        if "fake.json" in configs:
            for path, fx in facts.items():
                fx.is_entry = fx.is_entry or path.endswith("/main.fk")

    def test_files(configs, files):
        return {f for f in files if f.startswith("checks/")}

    for fn in (unit_of, is_test, scan, resolver, tests_for, is_excluded, grammar_for, enrich,
               test_files):
        setattr(m, fn.__name__, fn)
    return m


FAKE_REPO = {
    "pkg/a/one.fk": "import '../b/two.fk';\nimport 'lib:leftpad';\n// entry\n",
    "pkg/a/also.fk": "import '../b/two.fk';\nexport function a2() {}\n",
    "pkg/b/two.fk": "export function g() {}\nexport function h() {}\nfunction (\n",
    "pkg/b/two_test.fk": "",
    "tools/lone.fk": "export function z() {}\n",
    "tools/pub.fk": "// public\n",
    "tools/inl.fk": "// inline-tests\nif (x) {}\n",
    "tools/gen.fk": "// generated\n",
    "tools/runner": "#!/usr/bin/env fakerun\nimport '../pkg/b/two.fk';\nimport 'dir:../pkg/a';\n",
    "tools/broken": "#!/usr/bin/env fakerun\nfunction (\n",
    "fake.json": "{\"setting\": 1}\n",
    "app/main.fk": "import '../tools/lone.fk';\n",
    "checks/lone_check.fk": "import '../tools/lone.fk';\n",
    "README.md": "Run tools/lone.fk for the demo.\n",
    "lib/a.ex": "defmodule A do\n  def f(x), do: if x, do: 1\nend\n",
    "test/a_test.exs": "defmodule ATest do\nend\n",
    "bin/report": "#!/usr/bin/env perl\nprint 1;\n",
    "web/app.min.js": "var a=1;" * 200 + "\n",
    "node_modules/x/index.js": "module.exports = 1;\n",
    "docs/data.json": "{}\n",
    "src/util.py": "def f():\n    return 1\n",
}


@needs_grammar("javascript")
class UniversalSurveyTest(unittest.TestCase):
    def setUp(self):
        self.fake = _fake_adapter()
        modules = mock.patch.dict(sys.modules, {"lang_fake": self.fake})
        registry = mock.patch.object(langs, "ADAPTERS", ("python", "fake"))
        modules.start(), registry.start()
        self.addCleanup(langs.reset)
        self.addCleanup(registry.stop)
        self.addCleanup(modules.stop)
        langs.reset()
        self.model = survey_files(self, FAKE_REPO)
        self.mods = self.model.modules

    def test_folder_units_gather_their_files(self):
        unit = self.mods["pkg/a/"]
        self.assertEqual(unit.members, ["pkg/a/also.fk", "pkg/a/one.fk"])
        self.assertEqual((unit.kind, unit.lang, unit.depth, unit.district),
                         ("source", "fake", "full", "pkg"))
        self.assertEqual(unit.exports, ["a2"])
        self.assertTrue(unit.is_entry)
        self.assertNotIn("pkg/a/one.fk", self.mods)

    def test_each_import_adds_one_to_the_road_however_many_files_it_reaches(self):
        self.assertEqual(self.model.edges[("pkg/a/", "pkg/b/")], 2)
        self.assertEqual(self.model.edges[("tools/runner", "pkg/a/")], 1)
        self.assertIn(("tools/runner", "pkg/b/"), edges(self.model))

    def test_outside_packages_become_warehouses(self):
        self.assertEqual(self.model.externals, {"leftpad": ["pkg/a/"]})

    def test_a_folder_parse_error_names_the_file_and_burns_where_allowed(self):
        unit = self.mods["pkg/b/"]
        self.assertTrue(unit.parse_error.startswith("two.fk: line "), unit.parse_error)
        self.assertTrue(unit.burns)
        broken = self.mods["tools/broken"]
        self.assertTrue(broken.parse_error.startswith("line "), broken.parse_error)
        self.assertFalse(broken.burns)

    def test_tests_reach_what_they_cover(self):
        self.assertEqual(self.mods["pkg/b/two_test.fk"].kind, "test")
        self.assertEqual(self.mods["pkg/b/"].tested_by, ["pkg/b/two_test.fk"])

    def test_public_and_inline_facts_reach_the_module(self):
        self.assertTrue(self.mods["tools/pub.fk"].public)
        self.assertTrue(self.mods["tools/inl.fk"].inline_tests)

    def test_excluded_minified_vendored_and_data_files_are_not_buildings(self):
        for path in ["tools/gen.fk", "web/app.min.js", "node_modules/x/index.js",
                     "docs/data.json", "fake.json", "README.md"]:
            self.assertNotIn(path, self.mods)

    def test_the_resolver_gets_config_text(self):
        self.assertEqual(self.fake.seen_configs, {"fake.json": "{\"setting\": 1}\n"})

    def test_build_files_can_add_entry_points_and_tests(self):
        self.assertTrue(self.mods["app/main.fk"].is_entry)
        self.assertEqual(self.mods["checks/lone_check.fk"].kind, "test")
        self.assertEqual(self.mods["tools/lone.fk"].tested_by, ["checks/lone_check.fk"])

    def test_mentions_in_docs_keep_a_building_from_being_abandoned(self):
        self.assertTrue(self.mods["tools/lone.fk"].mentioned)
        self.assertFalse(self.mods["tools/pub.fk"].mentioned)

    def test_languages_without_an_adapter_stand_at_floor_depth(self):
        lib = self.mods["lib/a.ex"]
        self.assertEqual((lib.kind, lib.lang, lib.depth, lib.loc), ("source", "elixir", "floor", 3))
        self.assertEqual(lib.tested_by, ["test/a_test.exs"])
        self.assertEqual(self.mods["bin/report"].lang, "perl")

    def test_python_is_unchanged_beside_other_languages(self):
        py = self.mods["src/util.py"]
        self.assertEqual((py.lang, py.depth, py.exports), ("python", "full", ["f"]))

    def test_unreadable_code_is_unsurveyed(self):
        root = fixture.make_repo(self, {"pkg/a/x.fk": "export function a() {}\n"})
        with open(os.path.join(root, "pkg", "a", "bin.fk"), "wb") as f:
            f.write(b"\xff\xfe\x00bad")
        fixture.git(root, "add", "-A")
        fixture.git(root, "commit", "-q", "-m", "binary")
        mods = survey.survey(root).modules
        self.assertEqual((mods["pkg/a/bin.fk"].kind, mods["pkg/a/bin.fk"].lang),
                         ("unsurveyed", "fake"))
        self.assertEqual(mods["pkg/a/"].members, ["pkg/a/x.fk"])

    def test_a_missing_grammar_drops_to_floor_without_asking_for_it(self):
        langs.reset()
        with mock.patch.object(langkit, "_ready", frozenset()), \
                mock.patch.object(langkit, "_parsers", {}), \
                mock.patch.object(langkit, "_languages", {}), \
                mock.patch.object(langkit.pack, "get_language",
                                  side_effect=AssertionError("would download")):
            model = survey_files(self, {"pkg/a/one.fk": "import '../b/two.fk';\n",
                                        "pkg/b/two.fk": "export function g() {}\n"})
            line = towncode.languages_line(model)
        self.assertEqual(model.modules["pkg/a/one.fk"].depth, "floor")
        self.assertEqual(model.edges, {})
        self.assertIn("Fake 2 floor (grammar not installed", line)


class RegistryTest(unittest.TestCase):
    def test_classify_by_extension_shebang_table_and_not_code(self):
        self.assertEqual(langs.classify("a/b.py", None), "python")
        self.assertEqual(langs.classify("a/b.go", None), "go")
        self.assertEqual(langs.classify("bin/tool", "#!/usr/bin/env bash\necho\n"), "shell")
        self.assertEqual(langs.classify("bin/py", "#!/usr/bin/env python3\n"), None)
        self.assertIsNone(langs.classify("README.md", None))
        self.assertIsNone(langs.classify("LICENSE", "MIT License\n"))
        for path in ("LICENSE.txt", "CMakeLists.txt", "certs/server.pem", "app/views/a.html.erb",
                     "templates/page.j2"):
            self.assertIsNone(langs.classify(path, None), path)

    def test_without_tree_sitter_the_reason_says_so(self):
        langs.reset()
        self.addCleanup(langs.reset)
        with mock.patch.object(langkit, "pack", None):
            self.assertEqual(langs.depth_reason("go"), "tree-sitter not installed")
            self.assertIsNone(langs.depth_reason("python"))
            row = next(r for r in langs.status() if r[0] == "Go")
            self.assertEqual(row[1], "floor")
            self.assertIn("needs tree-sitter", row[3])

    def test_every_registry_language_has_a_floor_entry(self):
        keys = {entry[0] for entry in langs.floor.FLOOR_LANGUAGES.values()}
        self.assertTrue(set(langs.ADAPTERS) <= keys)

    def test_fire_can_be_limited_to_extensions(self):
        a = types.SimpleNamespace(FIRE=(".java", ""))
        self.assertTrue(langs.fire_allowed(a, "A.java"))
        self.assertFalse(langs.fire_allowed(a, "A.kt"))
        self.assertTrue(langs.fire_allowed(a, "bin/run"))
        self.assertFalse(langs.fire_allowed(types.SimpleNamespace(FIRE=False), "x.c"))

    def test_folder_ids_have_districts(self):
        self.assertEqual(survey.district_of("cmd/server/"), "cmd")
        self.assertEqual(survey.district_of("pkg/"), "pkg")
        self.assertEqual(survey.district_of("./"), "(root)")
        self.assertEqual(survey.district_of("main.go"), "(root)")


class CommandsTest(unittest.TestCase):
    def run_cmd(self, *argv):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = towncode.main(list(argv))
        return code, buf.getvalue()

    def test_languages_lists_every_registry_language(self):
        code, text = self.run_cmd("languages")
        self.assertEqual(code, 0)
        for label in ("Python", "Go", "Rust", "C/C++", "Swift"):
            self.assertIn(label, text)
        self.assertIn("Floor only (no adapter):", text)

    def test_setup_downloads_only_what_adapters_name(self):
        if langkit.pack is None:
            self.skipTest("tree-sitter not installed")
        fake = types.SimpleNamespace(NAME="fake", GRAMMARS={".fk": "javascript"})
        with mock.patch.object(langs, "adapters", return_value={"fake": fake}), \
                mock.patch.object(langkit.pack, "download", return_value=1) as download, \
                mock.patch.object(langs, "reset"):
            code, text = self.run_cmd("setup")
        download.assert_called_once_with(["javascript"])
        self.assertIn("Grammars ready", text)
        self.assertEqual(code, 0 if langkit.grammar_ready("javascript") else 1)


if __name__ == "__main__":
    unittest.main()
