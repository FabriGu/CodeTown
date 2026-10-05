# JavaScript / TypeScript adapter

Depends on: `../2026-10-01-universal-survey-design.md` (core). Core must be merged first.
You may touch: `lang_javascript.py` and `test_lang_javascript.py`. Nothing else.
Branch: `lang-javascript`, from `towncode-universal`, in its own worktree.

## Scope

| | |
| --- | --- |
| `NAME`, `LABEL` | `"javascript"`, `"JavaScript/TypeScript"` |
| `EXTENSIONS` | `.js .jsx .mjs .cjs .ts .tsx .mts .cts` |
| `GRAMMARS` | `.js .jsx .mjs .cjs` → `javascript`; `.ts .mts .cts` → `typescript`; `.tsx` → `tsx` |
| `SHEBANGS` | `node`, `deno`, `bun`, `ts-node`, `tsx` (also as `env node` and so on) |
| `CONFIG` | `package.json`, `tsconfig.json`, `tsconfig.*.json`, `jsconfig.json`, `pnpm-workspace.yaml` |
| `FIRE` | `True` (calibrate) |

Confirm grammar names with `tree_sitter_language_pack.available_languages()`. The node types
below are what the grammars are expected to use. Before relying on one, parse a snippet and
print the subtree's `node.type` values. Where a grammar differs, follow the grammar and note it
in the module docstring.

Config files are JSON with comments. Parse them by stripping `//` and `/* */` comments outside
strings, plus trailing commas, then `json.loads`. If a file still doesn't parse, ignore it.
Read `pnpm-workspace.yaml` with a regex for the `packages:` list only; there is no YAML parser.

## Building grain

One building per file.

## Facts per file

- **Lines and notes:** from `comment` nodes, through `langkit.loc` and `langkit.notes`.
- **Complexity:** 1, plus:
  - `if_statement`, `for_statement`, `for_in_statement` (which also covers for-of),
    `while_statement`, `do_statement`, `switch_case`, `catch_clause` and `ternary_expression`;
  - `binary_expression` whose operator is `&&`, `||` or `??`.
- **Exports**, as names:
  - `export function f`, `export class C`, `export const a = …, b = …`, `export enum E`,
    `export interface I` and `export type T` each give their declared names;
  - `export { a, b as c }` gives `a` and `c`;
  - `export default …` gives `default`;
  - `export * from "x"` gives `*`, and `export * as ns from "x"` gives `ns`;
  - CommonJS: `module.exports = { a, b }` gives `a` and `b`; `exports.x = …` and
    `module.exports.x = …` give `x`; `module.exports = <anything else>` gives `default`.
- **Entry (`is_entry`):** any of these:
  - the file starts with a shebang;
  - a `package.json` `bin` value points at it;
  - a `package.json` `scripts` value names it after `node`, `ts-node`, `tsx`, `bun` or `deno`
    (a plain token match, never run).
- **Public (`public`):** any of these:
  - the file is a workspace package's entry: `main`, `module`, `types`, or a string value in
    `exports`;
  - the file has the same stem under `src/` when that entry points into an untracked `dist/`
    or `lib/`.
- **Package (`is_package`):** an `index.*` file whose top level holds only imports and
  re-exports.
- **Fire:** `langkit.first_error`.

## Imports

Every form below with a single string-literal specifier becomes an `Import(spec)`. Template
literals, variables and concatenations are skipped.

- `import … from "x"`, `import "x"`, `import type … from "x"`;
- `export … from "x"`;
- `require("x")`;
- TypeScript `import x = require("x")`;
- dynamic `import("x")`.

## Resolution

Try these in order. The first step that yields files wins.

1. **Relative** (`./` or `../`), against the importer's folder.
   - Try the exact path.
   - Then the path plus each of `.ts .tsx .mts .cts .js .jsx .mjs .cjs`.
   - Then `<path>/index.<ext>`, in that extension order.
   - TypeScript writes ESM imports as `./x.js` while the source is `./x.ts`. So for a `.js`,
     `.mjs` or `.cjs` specifier that doesn't exist, also try the same stem with `.ts`, `.tsx`,
     `.mts` or `.cts`.
   - A target that is not code (`.css`, `.json`, `.svg`, `.png` and so on) gives no road and no
     warehouse.
   - Only `.d.ts` matches: no road.
2. **Path aliases.** Find the nearest `tsconfig.json` or `jsconfig.json` in the importer's
   folder or above it.
   - Follow `extends` chains that point at tracked files.
   - Apply `compilerOptions.paths` patterns, each with at most one `*`, relative to `baseUrl`
     (or to the config's folder if `baseUrl` is absent).
   - Then try `baseUrl` plus the bare specifier.
   - Each candidate goes through the relative rules above.
3. **Workspace packages.** Every tracked `package.json` with a `name` declares a package at its
   folder.
   - Specifier `name`: the package's entry, as under "Public".
   - Specifier `name/sub`: `sub` resolved under the package folder, then under its `src/`.
4. **Built-ins:** a `node:` prefix, or a Node core module name (`fs`, `path`, `http`, `url`,
   `crypto`, `child_process`, `os`, `stream`, `events`, `util`, `buffer`, `zlib`, `net`, `tls`,
   `dns`, `readline`, `assert`, `worker_threads`, `perf_hooks`, `timers`, and their
   `x/promises` forms). No road and no warehouse.
5. **External:** anything else. The package name is the first path segment, or the first two
   when it starts with `@` (`@scope/pkg`).

## Tests

- A file is a test if:
  - its name matches `*.test.*` or `*.spec.*`; or
  - it is under a folder named `__tests__`, `test`, `tests`, `e2e` or `cypress`.
- Tests link through their imports (core does this), then by name (the floor rule).

## Excluded (`is_excluded`)

- Files under `dist/`, `coverage/`, `.next/`, `.nuxt/`, `.svelte-kit/` or `storybook-static/`.
- Files matching `*.min.js`, `*.bundle.js` or `*.chunk.js`.
- Files whose first comment contains `@generated` or `DO NOT EDIT`.
- All `.d.ts` files. They are declarations, not buildings.

## Fire

Start with `FIRE = True` for all three grammars.

- JSX is valid in `.js` and `.jsx`, which the javascript grammar parses.
- `.ts` files must not contain JSX.
- `.tsx` must parse as tsx.

If calibration shows a grammar gap, such as a new decorator or `satisfies` form, make `FIRE` a
tuple without the affected extensions, and note the gap.

## Required tests

Each test is a fixture repo built with `langtest.survey_files`, plus the expected result.

1. `a.ts` with `import { b } from "./b"` reaches `b.ts`.
2. `a.ts` with `import "./b.js"` reaches `b.ts` when only `b.ts` exists.
3. `import x from "./lib"` reaches `lib/index.tsx`.
4. A `tsconfig.json` with `paths {"@/*": ["src/*"]}` makes `import "@/util/x"` reach
   `src/util/x.ts`.
5. A `tsconfig.json` that `extends` another tracked config, with `paths` only in the base, still
   resolves.
6. Workspaces: `packages/ui/package.json` names `@acme/ui` with `main: "dist/index.js"` (an
   untracked dist). `import "@acme/ui"` reaches `packages/ui/src/index.ts`, and that file is
   `public`.
7. `require("./c")` and `import("./d")` both reach their files. `require(name)` with a variable
   gives nothing.
8. `import fs from "node:fs"` and `import path from "path"` give no warehouse.
   `import React from "react"` and `import x from "@tanstack/query/core"` give warehouses `react`
   and `@tanstack/query`.
9. `import "./styles.css"` gives no road and no warehouse.
10. Exports are counted for every form in "Facts" (one test per group: ESM declarations, export
    lists, default, star, CommonJS).
11. Complexity: a fixture with one of each counted construct has the exact expected value.
12. A file with a shebang, and a file named by `package.json` `bin`, are both entries.
13. `src/a.test.ts` importing `src/a.ts` puts the test in `a.ts`'s `tested_by`.
14. An `index.ts` with only re-exports is `is_package`, and is neither abandoned nor untested.
15. `x.min.js`, `dist/y.js` and `types.d.ts` are not buildings.
16. A `.ts` file with a syntax error is on fire; a `.jsx` file with valid JSX is not.
17. A JSON-with-comments `tsconfig.json` (comments and trailing commas) still applies its paths.

## Calibration

- [sindresorhus/ky](https://github.com/sindresorhus/ky): small TypeScript library.
- [pmndrs/zustand](https://github.com/pmndrs/zustand): TypeScript with path aliases and tests.

Report the usual calibration note (core spec, "Work order"). In particular say:

- how many relative imports failed to resolve, and list up to ten;
- whether `react` and similar packages appear as warehouses.

## After calibration

- `FIRE = (".js", ".jsx", ".mjs", ".cjs")`. The TypeScript and TSX grammars report errors on
  valid zustand code (callable-interface overloads, `import()` type arguments), so `.ts` and
  `.tsx` files show their parse error without burning.
- `package.json` entry points and public exports are applied through core's `enrich` hook.
- Workspace packages are tried before `tsconfig` path aliases.

## Known limits

- Vue and Svelte single-file components stay at floor depth.
- Webpack and Vite aliases outside `tsconfig` aren't read.
- `exports` conditions (`import` and `require` maps) are flattened to their string values.
- Re-export chains don't forward roads to the original file. The road goes to the barrel.
