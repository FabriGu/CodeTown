import unittest

import lang_javascript
import langs
from langtest import edges, needs_grammar, survey_files


@needs_grammar("javascript", "typescript", "tsx")
class JavaScriptAdapterTest(unittest.TestCase):
    def test_relative_import(self):
        model = survey_files(self, {
            "a.ts": "import { b } from './b';\n",
            "b.ts": "export const b = 1;\n",
        })
        self.assertIn(("a.ts", "b.ts"), edges(model))

    def test_js_specifier_reaches_ts_source(self):
        model = survey_files(self, {
            "a.ts": "import { b } from './b.js';\n",
            "b.ts": "export const b = 1;\n",
        })
        self.assertIn(("a.ts", "b.ts"), edges(model))

    def test_directory_import_reaches_index(self):
        model = survey_files(self, {
            "a.ts": "import x from './lib';\n",
            "lib/index.tsx": "export default 1;\n",
        })
        self.assertIn(("a.ts", "lib/index.tsx"), edges(model))

    def test_tsconfig_paths(self):
        model = survey_files(self, {
            "tsconfig.json": '{"compilerOptions": {"baseUrl": ".", "paths": {"@/*": ["src/*"]}}}\n',
            "src/util/x.ts": "export const x = 1;\n",
            "a.ts": 'import { x } from "@/util/x";\n',
        })
        self.assertIn(("a.ts", "src/util/x.ts"), edges(model))

    def test_tsconfig_extends(self):
        model = survey_files(self, {
            "tsconfig.base.json": (
                '{"compilerOptions": {"baseUrl": ".", "paths": {"@/*": ["src/*"]}}}\n'),
            "tsconfig.json": '{"extends": "./tsconfig.base.json"}\n',
            "src/util/x.ts": "export const x = 1;\n",
            "a.ts": 'import { x } from "@/util/x";\n',
        })
        self.assertIn(("a.ts", "src/util/x.ts"), edges(model))

    def test_workspace_package(self):
        model = survey_files(self, {
            "packages/ui/package.json": (
                '{"name": "@acme/ui", "main": "dist/index.js"}\n'),
            "packages/ui/src/index.ts": "export const ui = 1;\n",
            "app.ts": 'import ui from "@acme/ui";\n',
        })
        self.assertIn(("app.ts", "packages/ui/src/index.ts"), edges(model))
        self.assertTrue(model.modules["packages/ui/src/index.ts"].public)

    def test_commonjs_and_dynamic_import(self):
        model = survey_files(self, {
            "a.js": 'const c = require("./c");\nimport("./d");\n',
            "c.js": "module.exports = 1;\n",
            "d.js": "export default 1;\n",
            "b.js": 'const name = "x"; require(name);\n',
        })
        self.assertIn(("a.js", "c.js"), edges(model))
        self.assertIn(("a.js", "d.js"), edges(model))
        self.assertEqual(len(edges(model)), 2)

    def test_builtins_and_externals(self):
        model = survey_files(self, {
            "a.ts": 'import fs from "node:fs";\nimport path from "path";\n'
                    'import React from "react";\n'
                    'import x from "@tanstack/query/core";\n',
        })
        self.assertEqual(edges(model), set())
        self.assertEqual(set(model.externals), {"@tanstack/query", "react"})

    def test_asset_import_has_no_road(self):
        model = survey_files(self, {
            "a.ts": 'import "./styles.css";\n',
            "styles.css": "body {}\n",
        })
        self.assertEqual(edges(model), set())
        self.assertEqual(model.externals, {})

    def test_esm_exports(self):
        model = survey_files(self, {
            "esm.ts": (
                "export function f() {}\n"
                "export class C {}\n"
                "export const a = 1, b = 2;\n"
                "export enum E { A }\n"
                "export interface I {}\n"
                "export type T = string;\n"
            ),
        })
        self.assertEqual(set(model.modules["esm.ts"].exports),
                         {"a", "b", "C", "E", "f", "I", "T"})

    def test_export_list_and_star(self):
        model = survey_files(self, {
            "list.ts": 'export { a, b as c } from "./x";\nexport * from "./y";\n'
                        'export * as ns from "./z";\nexport default 1;\n',
        })
        self.assertEqual(set(model.modules["list.ts"].exports),
                         {"*", "a", "c", "default", "ns"})

    def test_commonjs_exports(self):
        model = survey_files(self, {
            "cjs.js": (
                "module.exports = { a: 1, b: 2 };\n"
                "exports.x = 1;\n"
                "module.exports.y = 2;\n"
                "module.exports = other;\n"
            ),
        })
        self.assertEqual(set(model.modules["cjs.js"].exports), {"a", "b", "default", "x", "y"})

    def test_complexity(self):
        model = survey_files(self, {
            "x.ts": """
if (a) {}
for (;;) {}
for (x in y) {}
while (1) {}
do {} while (0);
switch (x) { case 1: break; }
try {} catch (e) {}
const t = a ? b : c;
const u = a && b || c;
""",
        })
        self.assertEqual(model.modules["x.ts"].complexity, 11)

    def test_entries(self):
        model = survey_files(self, {
            "package.json": '{"bin": {"cli": "bin/cli.js"}}\n',
            "bin/cli.js": "console.log(1);\n",
            "run.ts": "#!/usr/bin/env node\nconsole.log(1);\n",
        })
        self.assertTrue(model.modules["bin/cli.js"].is_entry)
        self.assertTrue(model.modules["run.ts"].is_entry)

    def test_test_import_links_tested_by(self):
        model = survey_files(self, {
            "src/a.ts": "export const a = 1;\n",
            "src/a.test.ts": "import './a';\n",
        })
        self.assertEqual(model.modules["src/a.ts"].tested_by, ["src/a.test.ts"])

    def test_index_reexport_is_package(self):
        model = survey_files(self, {
            "src/index.ts": 'export { a } from "./a";\nexport * from "./b";\nimport "./side";\n',
            "src/a.ts": "export const a = 1;\n",
            "src/b.ts": "export const b = 1;\n",
            "src/side.ts": "export {};\n",
        })
        self.assertTrue(model.modules["src/index.ts"].is_package)

    def test_excluded_files(self):
        model = survey_files(self, {
            "x.min.js": "var a=1;\n",
            "dist/y.js": "export const y = 1;\n",
            "types.d.ts": "export declare const x: number;\n",
            "src/ok.ts": "export const ok = 1;\n",
        })
        self.assertNotIn("x.min.js", model.modules)
        self.assertNotIn("dist/y.js", model.modules)
        self.assertNotIn("types.d.ts", model.modules)
        self.assertIn("src/ok.ts", model.modules)

    def test_fire(self):
        model = survey_files(self, {
            "bad.ts": "const x = ;\n",
            "ok.jsx": "export const App = () => <div/>;\n",
        })
        self.assertIsNotNone(model.modules["bad.ts"].parse_error)
        self.assertEqual(model.modules["bad.ts"].burns,
                         langs.fire_allowed(lang_javascript, "bad.ts"))
        self.assertIsNone(model.modules["ok.jsx"].parse_error)

    def test_jsonc_tsconfig(self):
        model = survey_files(self, {
            "tsconfig.json": (
                "// comment\n"
                '{"compilerOptions": {"baseUrl": ".", "paths": {"@/*": ["src/*"]},},}\n'
            ),
            "src/util/x.ts": "export const x = 1;\n",
            "a.ts": 'import { x } from "@/util/x";\n',
        })
        self.assertIn(("a.ts", "src/util/x.ts"), edges(model))

    @needs_grammar("javascript", "typescript")
    def test_functions_take_the_name_they_are_assigned_to(self):
        model = survey_files(self, {
            "a.js": "function f(x) {\n  if (x) return 1;\n  const inner = () => 2;\n}\n"
                    "const g = (y) => y ?? 0;\nclass C {\n  m() { return 1; }\n}\n"
                    "module.exports = { h: function () {} };\n",
            "b.ts": "const g = async (y: string) => y;\n",
        })
        self.assertEqual(model.modules["a.js"].functions,
                         [("f", 4, 2), ("g", 1, 2), ("m", 1, 1), ("h", 1, 1)])
        self.assertEqual(model.modules["b.ts"].functions, [("g", 1, 1)])

    def test_sample_town(self):
        model = survey_files(self, lang_javascript.SAMPLE)
        self.assertIn(("src/a.ts", "src/b.ts"), edges(model))
        self.assertEqual(model.externals, {"ky": ["src/b.ts"]})
        self.assertEqual(model.modules["src/a.ts"].tested_by, ["src/a.test.ts"])


if __name__ == "__main__":
    unittest.main()
