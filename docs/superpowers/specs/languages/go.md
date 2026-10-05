# Go adapter

Depends on: `../2026-10-01-universal-survey-design.md` (core). Core must be merged first.
You may touch: `lang_go.py` and `test_lang_go.py`. Nothing else.
Branch: `lang-go`, from `towncode-universal`, in its own worktree.

## Scope

| | |
| --- | --- |
| `NAME`, `LABEL` | `"go"`, `"Go"` |
| `EXTENSIONS` | `.go` |
| `GRAMMARS` | `.go` → `go` |
| `SHEBANGS` | none |
| `CONFIG` | `go.mod`, `go.work` |
| `FIRE` | `True` (calibrate) |

Confirm the grammar name with `available_languages()`. The node types below are expected. Print
a snippet's subtree to confirm each one, and follow the grammar where it differs.

Parse `go.mod` with regexes, never with the `go` tool:

- `module <path>`;
- `require <path> <version>` lines and `require ( … )` blocks;
- `replace <path> => ./local/dir` lines, where only local targets matter.

From `go.work`, read only the `use` lines (single and block form).

## Building grain

**A building is a package, which is a folder.** Go code imports folders, not files.

- `unit_of(path, files)` returns the folder plus `/`, and ignores `files`. A file at the
  repository root gives `./`.
- Core sums lines, complexity and notes over the folder's non-test `.go` files, and lists them in
  `Module.members`.
- Generated and `//go:build ignore` files are left out entirely (see "Excluded").
- Test files (`_test.go`) are never part of the unit. Each is its own test module.

## Facts per file

- **Lines and notes:** from `comment` nodes.
- **Complexity:** 1, plus:
  - `if_statement`, `for_statement`, `expression_case`, `type_case`, `communication_case`;
  - `binary_expression` with `&&` or `||`.
- **Exports:** top-level names that start with an upper-case letter. That covers
  `function_declaration` names, `type_spec` names, and `var_spec` and `const_spec` names.
  Methods are not counted.
- **Entry:** `package main` with a top-level `func main`.
- **Public:** the package is not `main`, and no path segment is `internal`. Other modules can
  import it, so it is never abandoned. In Go, abandoned only means an `internal/` package
  nothing imports.
- **Scope:** the `package` clause name. It is not used for resolution, which goes by folder.
- **Fire:** `langkit.first_error`.

## Imports

Every `import_spec` path string gives `Import(path)`. That includes aliased, dot (`.`) and blank
(`_`) imports, in both the single and the grouped form. Imports with the path `"C"` (cgo) are
skipped.

## Resolution

1. **Repository modules.** Every tracked `go.mod` declares a module, at its folder, with its
   `module` path. With a `go.work`, use only the folders its `use` lines list.
2. **Internal imports.** For import path `P`, find the module whose path `M` is the longest such
   that `P == M` or `P` starts with `M/`. The target folder is the module folder joined with
   the rest of `P`. If that folder holds non-test, non-ignored `.go` files, the import reaches
   them, and core maps them to the folder unit.
3. **Local replaces.** A `replace X => ./dir` in a repository `go.mod` makes `X` (and `X/…`)
   resolve into `dir` (and `dir/…`), when `dir` is a module in the repository.
4. **Standard library:** the first path element has no `.` (`fmt`, `net/http`,
   `encoding/json`). No road and no warehouse.
5. **External**, in this order:
   - the longest `require` path that prefixes `P`;
   - otherwise the first three segments for `github.com/…`, `gitlab.com/…` and
     `bitbucket.org/…`;
   - otherwise two segments for `golang.org/x/…` and `gopkg.in/…`;
   - otherwise the first segment.

## Tests

- A test is any `*_test.go` file.
- `tests_for(path, …)` returns the non-test `.go` files in the same folder. That covers both
  `package x` and `package x_test`. So a package with a test file in its folder gets an annex
  even when the test imports nothing.
- A test that imports other repository packages is linked to them too, through core.

## Excluded (`is_excluded`)

- Any folder named `testdata`.
- A file with a `//go:build ignore` line before `package`.
- A file whose leading comments (before `package`) contain a line matching
  `^// Code generated .* DO NOT EDIT\.$`. This includes protobuf `.pb.go` output.

## Required tests

1. Two files in `pkg/a/` form one building `pkg/a/` with summed lines, and both are in
   `members`.
2. With `go.mod` saying `module example.com/m`, `import "example.com/m/pkg/a"` from `cmd/x/` is
   a road from `cmd/x/` to `pkg/a/`.
3. A root-level `main.go` belongs to unit `./`.
4. A repository with `go.work` and two modules, where one imports the other, gets a road.
5. `replace example.com/lib => ./lib` resolves imports of `example.com/lib/sub` to `lib/sub/`.
6. `import "fmt"` and `import "net/http"` give no warehouse.
7. Warehouses:
   - `import "github.com/spf13/cobra/doc"` gives warehouse `github.com/spf13/cobra`;
   - with `require github.com/aws/aws-sdk-go-v2/service/s3 v1.0.0`, an import of
     `github.com/aws/aws-sdk-go-v2/service/s3/types` gives that module path.
8. Exports count upper-case top-level names only, and methods are not counted.
9. Complexity: a fixture with one of each construct has the exact value.
10. `package main` plus `func main` is an entry. A `main` package with no `main` function is not.
11. A package under `internal/` that nothing imports is abandoned. The same code outside
    `internal/` is public, and not abandoned.
12. `pkg/a/a_test.go` with no imports links to `pkg/a/` through `tests_for`, so `pkg/a/` is not
    untested.
13. A generated file is excluded from the unit's lines. So is a `//go:build ignore` file, and
    anything under `testdata/`.
14. A file with a syntax error sets fire on its folder unit, and the inspector names the file.

## Calibration

[spf13/cobra](https://github.com/spf13/cobra): one module, a `doc/` package, tests in every
folder. Report the usual note, and say whether any package came out abandoned.

## Known limits

- Build constraints other than `ignore` are not evaluated. Files for every OS and architecture
  join the unit.
- `vendor/` is already excluded by core.
- No package-level symbol references between folders. Imports are exact in Go, so none are
  needed.
