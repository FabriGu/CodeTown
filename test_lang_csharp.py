"""Required behaviour for the C# adapter."""

import unittest

import langkit
import lang_csharp as cs
import problems
from langtest import edges, needs_grammar, survey_files
from layers import Rows


def _scan(path, text):
    tree = langkit.parse("csharp", text)
    return cs.scan(path, text, tree)


def _resolve(files, configs=None):
    if configs is None:
        configs = {p: t for p, t in files.items() if not p.endswith(".cs")}
    facts = {p: _scan(p, t) for p, t in files.items() if p.endswith(".cs")}
    all_paths = tuple(sorted(set(files) | set(configs)))
    return cs.resolver(facts, configs, all_paths), facts


@needs_grammar("csharp")
class CSharpAdapterTest(unittest.TestCase):
    def test_using_reaches_declared_type(self):
        files = {
            "src/Core/Parser.cs": "namespace Acme.Core;\npublic class Parser {}\n",
            "src/App/Program.cs": (
                "using Acme.Core;\nnamespace Acme.App;\nclass Program { Parser p; }\n"
            ),
        }
        resolver, facts = _resolve(files)
        ref = next(i for i in facts["src/App/Program.cs"].imports if i.kind == "reference")
        self.assertEqual(resolver.resolve("src/App/Program.cs", ref),
                         (frozenset({"src/Core/Parser.cs"}), None))

    def test_parent_namespace_resolves_without_using(self):
        files = {
            "src/App/Settings.cs": "namespace Acme.App { public class Settings {} }\n",
            "src/App/Web/View.cs": "namespace Acme.App.Web;\nclass View { Settings s; }\n",
        }
        resolver, facts = _resolve(files)
        ref = next(i for i in facts["src/App/Web/View.cs"].imports if i.spec == "Settings")
        self.assertEqual(resolver.resolve("src/App/Web/View.cs", ref),
                         (frozenset({"src/App/Settings.cs"}), None))

    def test_global_using_is_project_scoped(self):
        files = {
            "src/Core/Core.csproj": "<Project Sdk=\"Microsoft.NET.Sdk\"></Project>\n",
            "src/Core/Parser.cs": "namespace Acme.Core;\npublic class Parser {}\n",
            "src/App/App.csproj": "<Project Sdk=\"Microsoft.NET.Sdk\"></Project>\n",
            "src/App/GlobalUsings.cs": "global using Acme.Core;\n",
            "src/App/Program.cs": "namespace Acme.App;\nclass Program { Parser p; }\n",
            "src/Other/Other.csproj": "<Project Sdk=\"Microsoft.NET.Sdk\"></Project>\n",
            "src/Other/Worker.cs": "namespace Acme.Other;\nclass Worker { Parser p; }\n",
        }
        resolver, facts = _resolve(files)
        ref = next(i for i in facts["src/App/Program.cs"].imports if i.spec == "Parser")
        self.assertEqual(resolver.resolve("src/App/Program.cs", ref),
                         (frozenset({"src/Core/Parser.cs"}), None))
        ref2 = next(i for i in facts["src/Other/Worker.cs"].imports if i.spec == "Parser")
        self.assertEqual(resolver.resolve("src/Other/Worker.cs", ref2), (frozenset(), None))

    def test_file_scoped_and_block_namespaces(self):
        scoped = _scan("a.cs", "namespace Acme.Core;\npublic class Parser {}\n")
        self.assertEqual(scoped.scope, "Acme.Core")
        self.assertEqual(scoped.declares, (("Acme.Core", "Parser"),))
        block = _scan("b.cs", "namespace A.B {\n  namespace C { class X {} }\n}\n")
        self.assertIsNone(block.scope)
        self.assertIn(("A.B.C", "X"), block.declares)

    def test_static_using_and_alias(self):
        files = {
            "src/Core/Guards.cs": "namespace Acme.Core;\npublic static class Guards {}\n",
            "src/Core/Parser.cs": "namespace Acme.Core;\npublic class Parser {}\n",
            "src/App/App.cs": (
                "using static Acme.Core.Guards;\nusing P = Acme.Core.Parser;\n"
                "namespace Acme.App;\nclass App {}\n"
            ),
        }
        resolver, facts = _resolve(files)
        static = next(i for i in facts["src/App/App.cs"].imports if i.spec == "Acme.Core.Guards")
        alias = next(i for i in facts["src/App/App.cs"].imports if i.spec == "Acme.Core.Parser")
        self.assertEqual(resolver.resolve("src/App/App.cs", static),
                         (frozenset({"src/Core/Guards.cs"}), None))
        self.assertEqual(resolver.resolve("src/App/App.cs", alias),
                         (frozenset({"src/Core/Parser.cs"}), None))

    def test_two_namespaces_in_one_file(self):
        text = "namespace A { class One {} }\nnamespace B { class Two {} }\n"
        fx = _scan("both.cs", text)
        self.assertIn(("A", "One"), fx.declares)
        self.assertIn(("B", "Two"), fx.declares)
        index = langkit.SymbolIndex((s, n, "both.cs") for s, n in fx.declares)
        self.assertEqual(index.lookup("A", "One"), "both.cs")
        self.assertEqual(index.lookup("B", "Two"), "both.cs")

    def test_partial_and_duplicate_types(self):
        files = {
            "src/Form.cs": "namespace UI;\npublic partial class Form {}\n",
            "src/Form.Layout.cs": "namespace UI;\npublic partial class Form {}\n",
            "src/UseForm.cs": "namespace UI;\nclass Page { Form f; }\n",
            "src/Dup1.cs": "namespace X;\nclass Dup {}\n",
            "src/Dup2.cs": "namespace X;\nclass Dup {}\n",
            "src/UseDup.cs": "namespace X;\nclass Holder { Dup d; }\n",
        }
        resolver, facts = _resolve(files)
        form = next(i for i in facts["src/UseForm.cs"].imports if i.spec == "Form")
        self.assertEqual(resolver.resolve("src/UseForm.cs", form)[0],
                         frozenset({"src/Form.cs", "src/Form.Layout.cs"}))
        dup = next(i for i in facts["src/UseDup.cs"].imports if i.spec == "Dup")
        self.assertEqual(resolver.resolve("src/UseDup.cs", dup)[0], frozenset())

    def test_framework_and_package_warehouses(self):
        files = {"App.cs": "using System.Linq;\nusing Newtonsoft.Json.Linq;\nnamespace A;\nclass App {}\n"}
        configs = {"App.csproj": (
            '<Project Sdk="Microsoft.NET.Sdk"><ItemGroup>'
            '<PackageReference Include="Newtonsoft.Json" />'
            "</ItemGroup></Project>\n"
        )}
        resolver, facts = _resolve({**files, "App.csproj": configs["App.csproj"]}, configs)
        sys = next(i for i in facts["App.cs"].imports if i.spec == "System.Linq")
        newton = next(i for i in facts["App.cs"].imports if i.spec == "Newtonsoft.Json.Linq")
        self.assertEqual(resolver.resolve("App.cs", sys), (frozenset(), None))
        self.assertEqual(resolver.resolve("App.cs", newton), (frozenset(), "Newtonsoft.Json"))

    def test_attribute_suffix(self):
        files = {
            "AuditAttribute.cs": "namespace Acme;\npublic class AuditAttribute : System.Attribute {}\n",
            "Worker.cs": "namespace Acme;\nclass Worker { [Audit] public void Run() {} }\n",
        }
        resolver, facts = _resolve(files)
        ref = next(i for i in facts["Worker.cs"].imports if i.spec == "Audit")
        self.assertEqual(resolver.resolve("Worker.cs", ref),
                         (frozenset({"AuditAttribute.cs"}), None))

    def test_exports(self):
        text = (
            "namespace Acme;\npublic class Widget {\n"
            "  public void A() {}\n  public void B() {}\n  public int P { get; set; }\n"
            "  private void Hidden() {}\n}\n"
        )
        fx = _scan("Widget.cs", text)
        self.assertEqual(set(fx.exports), {"Widget", "A", "B", "P"})

    def test_complexity(self):
        text = """
if (a) {}
for (;;) {}
foreach (var x in y) {}
while (true) {}
do {} while (true);
switch (x) { case 1: break; }
var t = a ? b : c;
var u = a && b || c ?? d;
try {} catch (Exception e) {}
var v = n switch { 1 => "a", _ => "b" };
"""
        fx = _scan("c.cs", text)
        self.assertEqual(fx.complexity, 12)

    def test_entry_points(self):
        main = _scan("Main.cs", "class P { static void Main() {} }\n")
        top = _scan("Top.cs", 'System.Console.WriteLine("hi");\n')
        self.assertTrue(main.is_entry)
        self.assertTrue(top.is_entry)

    def test_xunit_project_and_annex(self):
        files = {
            "src/Core/Parser.cs": "namespace Acme.Core;\npublic class Parser {}\n",
            "test/App.Tests/App.Tests.csproj": (
                '<Project Sdk="Microsoft.NET.Sdk"><ItemGroup>'
                '<PackageReference Include="xunit" />'
                "</ItemGroup></Project>\n"
            ),
            "test/App.Tests/ParserTests.cs": (
                "using Acme.Core;\nnamespace Acme.Tests;\npublic class ParserTests { Parser p; }\n"
            ),
        }
        model = survey_files(self, files)
        self.assertEqual(model.modules["test/App.Tests/ParserTests.cs"].kind, "test")
        self.assertIn("test/App.Tests/ParserTests.cs",
                      model.modules["src/Core/Parser.cs"].tested_by)

    def test_excluded_files(self):
        files = {
            "obj/Debug/X.g.cs": "namespace G;\nclass X {}\n",
            "Form1.Designer.cs": "namespace D;\nclass Form1 {}\n",
            "Gen.cs": "/* <auto-generated> */\nnamespace G;\nclass Gen {}\n",
            "Real.cs": "namespace R;\nclass Real {}\n",
        }
        model = survey_files(self, files)
        self.assertIn("Real.cs", model.modules)
        for path in ("obj/Debug/X.g.cs", "Form1.Designer.cs", "Gen.cs"):
            self.assertNotIn(path, model.modules)

    def test_syntax_error_fires(self):
        model = survey_files(self, {"Broken.cs": "class X { @@\n"})
        mod = model.modules["Broken.cs"]
        self.assertTrue(mod.parse_error)
        self.assertTrue(mod.burns)

    def test_xunit_helper_is_test_via_test_files(self):
        files = {
            "test/App.Tests/App.Tests.csproj": (
                '<Project Sdk="Microsoft.NET.Sdk"><ItemGroup>'
                '<PackageReference Include="xunit" />'
                "</ItemGroup></Project>\n"
            ),
            "test/App.Tests/Helpers.cs": "namespace Acme.Tests;\ninternal static class Helpers {}\n",
            "src/Lib/Lib.csproj": "<Project Sdk=\"Microsoft.NET.Sdk\"></Project>\n",
            "src/Lib/Foo.cs": "namespace Acme;\npublic class Foo {}\n",
        }
        configs = {p: t for p, t in files.items() if p.endswith(".csproj")}
        declared = cs.test_files(configs, tuple(files))
        self.assertIn("test/App.Tests/Helpers.cs", declared)
        self.assertNotIn("src/Lib/Foo.cs", declared)
        model = survey_files(self, files)
        self.assertEqual(model.modules["test/App.Tests/Helpers.cs"].kind, "test")

    def test_public_library_api_not_abandoned(self):
        model = survey_files(self, {
            "src/Lib/Lib.csproj": "<Project Sdk=\"Microsoft.NET.Sdk\"></Project>\n",
            "src/Lib/Api.cs": "namespace Acme;\npublic class Api { internal void Hidden() {} }\n",
        })
        mod = model.modules["src/Lib/Api.cs"]
        self.assertTrue(mod.public)
        abandoned = {p.module for p in problems.find(model, Rows()) if p.kind == "abandoned"}
        self.assertNotIn("src/Lib/Api.cs", abandoned)

    def test_internal_unreferenced_is_still_abandoned(self):
        model = survey_files(self, {
            "src/Lib/Lib.csproj": "<Project Sdk=\"Microsoft.NET.Sdk\"></Project>\n",
            "src/Lib/Hidden.cs": "namespace Acme;\ninternal class Hidden {}\n",
        })
        self.assertFalse(model.modules["src/Lib/Hidden.cs"].public)
        abandoned = {p.module for p in problems.find(model, Rows()) if p.kind == "abandoned"}
        self.assertIn("src/Lib/Hidden.cs", abandoned)

    def test_exe_public_class_is_not_public(self):
        model = survey_files(self, {
            "App/App.csproj": (
                '<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup>'
                "<OutputType>Exe</OutputType></PropertyGroup></Project>\n"
            ),
            "App/Program.cs": (
                "namespace App;\npublic class Program { static void Main() {} }\n"
            ),
        })
        mod = model.modules["App/Program.cs"]
        self.assertFalse(mod.public)
        self.assertTrue(mod.is_entry)

    @needs_grammar("csharp")
    def test_functions_are_methods_and_constructors_without_local_functions(self):
        model = survey_files(self, {
            "A.cs": "class A {\n  A() {}\n  int F(int x) {\n    if (x > 0 || x < 9) return 1;\n"
                    "    int Local() => 2;\n    return 0;\n  }\n}\n",
        })
        self.assertEqual(model.modules["A.cs"].functions, [("A", 1, 1), ("F", 5, 3)])


if __name__ == "__main__":
    unittest.main()
