import unittest

import lang_swift
import langkit
import layers
import problems
from langtest import edges, needs_grammar, survey_files


def _tree(text, path="x.swift"):
    return langkit.parse("swift", text)


PACKAGE = (
    "// swift-tools-version: 5.9\nimport PackageDescription\n\n"
    "let package = Package(\n"
    '    name: "Demo",\n'
    "    targets: [\n"
    '        .target(name: "Core"),\n'
    '        .executableTarget(name: "App", dependencies: ["Core"]),\n'
    '        .testTarget(name: "CoreTests", dependencies: ["Core"]),\n'
    "    ]\n)\n"
)


class SwiftAdapterTest(unittest.TestCase):
    @needs_grammar("swift")
    def test_package_targets_assign_modules(self):
        model = survey_files(self, {
            "Package.swift": PACKAGE,
            "Sources/Core/A.swift": "struct A {}\n",
            "Sources/App/B.swift": "struct B {}\n",
        })
        self.assertEqual(
            lang_swift._layout({"Package.swift": PACKAGE}, tuple(model.modules)).module_of,
            {
                "Sources/Core/A.swift": "Core",
                "Sources/App/B.swift": "App",
            },
        )

    @needs_grammar("swift")
    def test_target_custom_path(self):
        pkg = (
            "// swift-tools-version: 5.9\nimport PackageDescription\n\n"
            "let package = Package(\n"
            '    name: "Demo",\n'
            "    targets: [\n"
            '        .target(name: "Core", path: "Lib/Core"),\n'
            "    ]\n)\n"
        )
        layout = lang_swift._layout({"Package.swift": pkg}, ("Lib/Core/A.swift",))
        self.assertEqual(layout.module_of["Lib/Core/A.swift"], "Core")

    @needs_grammar("swift")
    def test_same_module_reaches_without_import(self):
        model = survey_files(self, {
            "Package.swift": PACKAGE,
            "Sources/Core/Parser.swift": "struct Parser {}\n",
            "Sources/Core/Use.swift": "let p = Parser()\n",
        })
        self.assertEqual(edges(model), {("Sources/Core/Use.swift", "Sources/Core/Parser.swift")})

    @needs_grammar("swift")
    def test_cross_module_needs_import(self):
        files = {
            "Package.swift": PACKAGE,
            "Sources/Core/Parser.swift": "struct Parser {}\n",
            "Sources/App/main.swift": "import Core\n\nlet p = Parser()\n",
        }
        with_import = survey_files(self, files)
        self.assertEqual(
            edges(with_import),
            {("Sources/App/main.swift", "Sources/Core/Parser.swift")},
        )
        without = dict(files)
        without["Sources/App/main.swift"] = "let p = Parser()\n"
        model = survey_files(self, without)
        self.assertEqual(edges(model), set())

    @needs_grammar("swift")
    def test_extension_does_not_declare_type(self):
        ext = "extension Parser { func run() {} }\n"
        types = "enum E {}\nactor A {}\nprotocol P {}\n"
        model = survey_files(self, {
            "Package.swift": PACKAGE,
            "Sources/Core/Parser.swift": "struct Parser {}\n",
            "Sources/Core/Types.swift": types,
            "Sources/Core/Ext.swift": ext,
            "Sources/Core/Use.swift": "let p = Parser()\n",
        })
        fx = lang_swift.scan("Sources/Core/Ext.swift", ext, _tree(ext))
        types_fx = lang_swift.scan("Sources/Core/Types.swift", types, _tree(types))
        self.assertNotIn("Parser", fx.declares)
        self.assertEqual(set(types_fx.declares), {"E", "A", "P"})
        self.assertEqual(edges(model), {("Sources/Core/Use.swift", "Sources/Core/Parser.swift")})

    @needs_grammar("swift")
    def test_ambiguous_same_name_in_one_module(self):
        model = survey_files(self, {
            "Package.swift": PACKAGE,
            "Sources/Core/A.swift": "struct Parser {}\n",
            "Sources/Core/B.swift": "struct Parser {}\n",
            "Sources/Core/Use.swift": "let p = Parser()\n",
        })
        self.assertEqual(edges(model), set())

    @needs_grammar("swift")
    def test_system_and_product_warehouses(self):
        pkg = (
            "// swift-tools-version: 5.9\nimport PackageDescription\n\n"
            "let package = Package(\n"
            '    name: "Demo",\n'
            "    dependencies: [\n"
            '        .product(name: "ArgumentParser", package: "swift-argument-parser"),\n'
            "    ],\n"
            "    targets: [\n"
            '        .target(name: "Core", dependencies: ["ArgumentParser"]),\n'
            "    ]\n)\n"
        )
        model = survey_files(self, {
            "Package.swift": pkg,
            "Sources/Core/A.swift": (
                "import Foundation\nimport SwiftUI\nimport ArgumentParser\n\nstruct A {}\n"
            ),
        })
        self.assertEqual(model.externals, {"swift-argument-parser": ["Sources/Core/A.swift"]})

    @needs_grammar("swift")
    def test_exports_respect_visibility(self):
        text = """
struct S {
    private func a() {}
    fileprivate var b: Int = 0
    internal func c() {}
    public let d = 1
    open func e() {}
    func f() {}
}
"""
        fx = lang_swift.scan("S.swift", text, _tree(text))
        self.assertEqual(set(fx.exports), {"S", "c", "d", "e", "f"})

    @needs_grammar("swift")
    def test_complexity_counts_each_construct(self):
        text = """
if x { }
guard y else { }
for i in 0..<10 { }
while z { }
repeat { } while w
switch x { case 1: break default: break }
do { try f() } catch { }
a ? b : c
x && y
x || y
x ?? y
"""
        fx = lang_swift.scan("c.swift", text, _tree(text))
        self.assertEqual(fx.complexity, 13)

    @needs_grammar("swift")
    def test_entry_points(self):
        model = survey_files(self, {
            "Package.swift": PACKAGE,
            "Sources/App/MainType.swift": "@main\nstruct App {\n  static func main() {}\n}\n",
            "Sources/Run/main.swift": "print(\"hi\")\n",
            "tools/run": "#!/usr/bin/env swift\nprint(1)\n",
        })
        self.assertTrue(model.modules["Sources/App/MainType.swift"].is_entry)
        self.assertTrue(model.modules["Sources/Run/main.swift"].is_entry)
        self.assertTrue(model.modules["tools/run"].is_entry)

    @needs_grammar("swift")
    def test_test_target_links_to_source(self):
        model = survey_files(self, {
            "Package.swift": PACKAGE,
            "Sources/Core/Parser.swift": "struct Parser {}\n",
            "Tests/CoreTests/ParserTests.swift": (
                "import XCTest\n@testable import Core\n\nfinal class T: XCTestCase {\n"
                "  func testP() { _ = Parser() }\n}\n"
            ),
        })
        self.assertIn(
            "Tests/CoreTests/ParserTests.swift",
            model.modules["Sources/Core/Parser.swift"].tested_by,
        )

    @needs_grammar("swift")
    def test_folder_modules_without_package(self):
        model = survey_files(self, {
            "App/App.swift": "import Shared\n\nlet x = SharedType()\n",
            "Shared/Shared.swift": "struct SharedType {}\n",
        })
        self.assertEqual(
            edges(model),
            {("App/App.swift", "Shared/Shared.swift")},
        )
        local = survey_files(self, {
            "App/A.swift": "struct T {}\n",
            "App/B.swift": "let t = T()\n",
        })
        self.assertEqual(edges(local), {("App/B.swift", "App/A.swift")})

    @needs_grammar("swift")
    def test_excluded_paths_are_not_buildings(self):
        model = survey_files(self, {
            "Package.swift": PACKAGE,
            ".build/x.swift": "struct X {}\n",
            "Sources/Core/A.swift": "struct A {}\n",
        })
        self.assertIn("Sources/Core/A.swift", model.modules)
        self.assertNotIn("Package.swift", model.modules)
        self.assertNotIn(".build/x.swift", model.modules)

    @needs_grammar("swift")
    def test_parse_error_and_fire(self):
        model = survey_files(self, {
            "Package.swift": PACKAGE,
            "Sources/Core/Broken.swift": "struct { }\n",
        })
        mod = model.modules["Sources/Core/Broken.swift"]
        self.assertTrue(mod.parse_error)
        if lang_swift.FIRE:
            self.assertTrue(mod.burns)
        else:
            self.assertFalse(mod.burns)

    @needs_grammar("swift")
    def test_custom_test_target_path_is_test(self):
        pkg = (
            "// swift-tools-version: 5.9\nimport PackageDescription\n\n"
            "let package = Package(\n"
            '    name: "Demo",\n'
            "    targets: [\n"
            '        .target(name: "Core"),\n'
            '        .testTarget(name: "CoreTests", path: "Spec/Tests", dependencies: ["Core"]),\n'
            "    ]\n)\n"
        )
        model = survey_files(self, {
            "Package.swift": pkg,
            "Sources/Core/A.swift": "struct A {}\n",
            "Spec/Tests/A.swift": "struct T {}\n",
        })
        self.assertEqual(model.modules["Spec/Tests/A.swift"].kind, "test")

    @needs_grammar("swift")
    def test_custom_executable_path_top_level_is_entry(self):
        pkg = (
            "// swift-tools-version: 5.9\nimport PackageDescription\n\n"
            "let package = Package(\n"
            '    name: "Demo",\n'
            "    targets: [\n"
            '        .executableTarget(name: "Run", path: "Cmd/Run"),\n'
            "    ]\n)\n"
        )
        model = survey_files(self, {
            "Package.swift": pkg,
            "Cmd/Run/Run.swift": 'print("go")\n',
        })
        self.assertTrue(model.modules["Cmd/Run/Run.swift"].is_entry)

    @needs_grammar("swift")
    def test_library_public_type_not_abandoned(self):
        model = survey_files(self, {
            "Package.swift": PACKAGE,
            "Sources/Core/Public.swift": "public struct Api {}\n",
            "Sources/Core/Hidden.swift": "internal struct Hidden {}\n",
        })
        self.assertTrue(model.modules["Sources/Core/Public.swift"].public)
        self.assertFalse(model.modules["Sources/Core/Hidden.swift"].public)
        rows = layers.Rows().update(model)
        abandoned = {p.module for p in problems.find(model, rows) if p.kind == problems.ABANDONED}
        self.assertNotIn("Sources/Core/Public.swift", abandoned)
        self.assertIn("Sources/Core/Hidden.swift", abandoned)

    @needs_grammar("swift")
    def test_functions_include_initialisers(self):
        model = survey_files(self, {
            "Package.swift": PACKAGE,
            "Sources/Core/a.swift": "struct S {\n  init() {}\n  func f(x: Int) -> Int {\n"
                                    "    if x > 0 { return 1 }\n    let c = { 1 }\n    return 0\n"
                                    "  }\n  deinit {}\n}\n\nfunc top() {}\n",
        })
        self.assertEqual(model.modules["Sources/Core/a.swift"].functions,
                         [("init", 1, 1), ("f", 5, 2), ("deinit", 1, 1), ("top", 1, 1)])
