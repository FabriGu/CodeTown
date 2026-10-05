# Universal survey: every language in the town (core)

Status: design, not yet assigned. Builds on the site-plan spec
(`2026-09-30-codetown-site-plan-design.md`) and on Plan 2, the finished rendered town.

Plan 2 is on the local branch `towncode-render`, which is not on GitHub yet. `main` has the
earlier prototype of the same modules (`plat`, `townmap`, `roads`, `drawtown`, `viewer`). Core
work starts from Plan 2's code, so `towncode-render` has to be pushed or merged before anyone
other than its author can start.

The language specs in `languages/` depend on this one, and cannot start until it is implemented
and merged.

## Summary

Today only Python files become buildings. Everything else is a gray outlined plot. This spec
makes the survey universal in two layers:

1. **A universal floor.** Every source file in any programming language becomes a real building
   from facts that need no parser: size, commits, notes, tests found by name, and a rough
   complexity. It uses only the standard library.
2. **Language adapters.** A small module per language adds the facts that need a real parser:
   roads (imports), doors (exports), fire (won't parse), gates (entry points) and exact
   complexity. Adapters other than Python use tree-sitter.

The drawing half (plat, tile map, roads, renderer, viewer) already reads only the model, so it
stays almost unchanged. The changes are a quiet look for half-read buildings, and a harbor that
fits large dependency lists.

## Why only Python today

Python's standard library ships an exact Python parser (`ast`), so the first surveyor got exact
facts with no dependencies and without running code. Two files are Python-specific:
`pyscan.py` (facts for one file) and `resolve.py` (an import to a file). `survey.py` hard-codes
them. Everything after the survey is already language-neutral.

## Principles (added to the site plan's six)

7. **Half-known looks half-known.** A building drawn from floor facts has no roads and no doors,
   and its lot carries the gray "unsurveyed" outline. The inspector says which facts are missing.
   It is never shown as abandoned, and never as all-doors.
8. **Adapters never touch the world.** An adapter gets file paths and text and returns facts. It
   never opens a file, lists a folder, runs a process or opens a socket. Core does every read,
   through `repo.Repo`, so the read-only guarantee holds by construction.
9. **Loud only when calibrated.** Fire comes from a parser, and parsers have gaps. An adapter
   only raises fire after its calibration repos show no false fires.

## Three depths

| Depth | Who sets it | Facts | Look |
| --- | --- | --- | --- |
| **full** | an adapter whose grammar is ready | everything: roads, doors, fire, gates, exact complexity, tests by import | a normal building |
| **floor** | core, for code with no adapter (or whose grammar is missing) | lines, commits, notes, tests by name, rough complexity | a building with the gray outline on its lot, no doors, no roads |
| **unsurveyed** | core, for code that can't be read | none | the existing gray outlined plot |

`unsurveyed` now means only unreadable code: a symlink, binary, over 1 MB, or not UTF-8. "Not
Python" stops being a reason.

## Which files are buildings

Core decides each tracked, non-vendored file's language, in this order:

1. Its extension is in an adapter's `EXTENSIONS`: that adapter.
2. It has no extension and its first line is a shebang whose interpreter is in an adapter's
   `SHEBANGS`: that adapter.
3. Its extension is in core's `FLOOR_LANGUAGES` table: floor depth, with that language's label.
   The table holds about 60 common programming languages, each with its comment markers (see
   "The floor" below). It includes every adapter language, so `.go`, `.rs` and the rest are
   floor buildings until their adapter lands.
4. tree-sitter-language-pack is installed and `detect_language_from_path` (or
   `detect_language_from_content` for extensionless files) names a language not in core's
   `NOT_CODE` set: floor depth.
5. Otherwise it is not a building. That covers docs, data and config, as today.

`NOT_CODE` holds markup, data and config languages: markdown, json, yaml, toml, xml, csv, ini,
html, css, scss, less, svg, dockerfile, make, gitignore, properties, sql. Their files are still
read for mentions and config, but never drawn.

Excluded entirely, like `vendor/` today:

- any folder named `vendor` or `node_modules`;
- minified files (a line over 1,000 characters, and an average line over 200), outside Python;
- anything an adapter's optional `is_excluded(path, text)` claims.

Python is unchanged. `.py` files still go through `pyscan` and `resolve`, behind the adapter
interface.

## The floor

The floor needs no parser and no dependency:

- **Lines of code:** non-blank lines that aren't comment-only. Comment markers come from
  `FLOOR_LANGUAGES` (for example `#` for shell-likes; `//`, `/*` and `*` for C-likes; `--` for
  Lua, Haskell and SQL-likes; `;` for Lisps).
- **Notes:** comment-only lines containing `TODO` or `FIXME`.
- **Complexity:** 1, plus a count of the words `if`, `elif`, `elsif`, `for`, `foreach`, `while`,
  `until`, `case`, `when`, `catch`, `except`, `rescue` and `guard`, and of `&&` and `||`, on
  non-comment lines. It is rough by design.
- **Commits:** from git, as today.
- **Tests by name.** A file is a test if a folder on its path is `test`, `tests`, `spec`,
  `specs`, `__tests__` or `testing`, or its name matches `test_*`, `*_test.*`, `*.test.*`,
  `*.spec.*`, `*Test.*`, `*Tests.*` or `*_spec.*`. A test is linked to the source file whose
  stem equals the test's stem with those markers removed. Only files in the same language
  count, and the match must be unique: prefer the same folder, then a mirrored path
  (`src/a/b.x` matches `test/a/b_test.x`). An ambiguous match links nothing.
- **Never set:** imports, exports, entry points, parse errors.

## The adapter contract

An adapter is a module `lang_<name>.py` with tests in `test_lang_<name>.py`. Core imports it
lazily by name from a fixed registry in `langs.py`:

```python
ADAPTERS = ("python", "javascript", "shell", "go", "jvm", "csharp", "rust", "ruby",
            "cfamily", "swift")
```

All names are listed up front, so a language agent only ever creates its own two files. If a
module is missing, or fails to import (tree-sitter not installed), its files fall back to floor
depth, and `towncode languages` reports why.

### Module constants

```python
NAME = "go"                   # registry key; stored as Module.lang
LABEL = "Go"                  # shown in the inspector and reports
EXTENSIONS = (".go",)         # owned exclusively: two adapters may not claim one extension
SHEBANGS = ()                 # interpreter names for extensionless scripts, e.g. ("bash", "sh")
GRAMMARS = {".go": "go"}      # extension -> tree-sitter-language-pack grammar name
CONFIG = ("go.mod", "go.work")  # tracked basenames (or "*.ext" globs) core reads as text for it
FIRE = True                   # parse errors become fire: True, False, or a tuple of the
                              # extensions that may ("" for extensionless scripts); see "Fire"
SAMPLE = {...}                # a tiny multi-file repo {path: text} used by the contract tests
```

### Functions

```python
def unit_of(path, files) -> str
    """The building a non-test source file belongs to: the path itself, a folder id ending
    in "/" for languages that import folders (Go; the repository root is "./"), or another
    file's path for languages that pair files (a C header and its source). `files` is the
    frozenset of every tracked path."""

def is_test(path, text) -> bool

def scan(path, text, tree) -> langkit.Facts
    """Facts for one file. `tree` is the tree-sitter tree for its grammar, or None when
    the adapter has no grammar (Python). Must never raise; garbage in gives empty facts."""

def resolver(facts, configs, files) -> Resolver
    """facts: {path: Facts} for every file of this language (tests included);
    configs: {path: text} for every tracked file matching CONFIG; files: every tracked path."""

class Resolver:
    def resolve(self, path, imp) -> tuple[frozenset[str], str | None]
        """Repository files this import reaches, and the outside package it names (or None).
        Both empty means a standard-library or unknown import: no road, no warehouse."""
```

Optional hooks:

- `tests_for(path, facts, files) -> set[str]`: source files a test covers without importing
  them (Go tests in the same folder).
- `is_excluded(path, text) -> bool`: not a building at all, for generated code, build output,
  or manifests written in the language (`Package.swift`).
- `grammar_for(path, files) -> str`: the grammar for one file, when the extension alone can't
  decide (a C `.h` in a C++ repository). Defaults to `GRAMMARS[extension]`.
- `mention_tokens(unit_id) -> set[str]`: tokens that count as another file mentioning this unit.
  Defaults to the path and the basename.
- `enrich(facts, configs, files) -> None`: adjusts `facts` in place with what only build files
  say, such as entry points and public API from `package.json` or `Package.swift`. Core calls it
  once per run, after every file of the language is scanned and before buildings are made.
- `test_files(configs, files) -> set[str]`: files that are tests because a build file says so
  (every file of a C# test project, a Swift `.testTarget`), on top of `is_test`.

### `langkit.Facts` and `langkit.Import`

```python
@dataclass(frozen=True)
class Import:
    spec: str            # what the code names: "./b", "net/http", "com.a.B", "Admin::User"
    names: tuple = ()    # imported names, when the syntax lists them
    kind: str = "import" # "import", "reference" (a name used without an import),
                         # "runs" (a script invoking another), "module" (a child module),
                         # or an adapter's own label; core treats every kind alike

@dataclass
class Facts:
    loc: int = 0
    complexity: int = 0
    exports: tuple = ()          # names other code can use: the building's doors
    notes: int = 0
    is_entry: bool = False       # run directly: a gate
    is_package: bool = False     # a package marker or barrel (Python __init__.py, JS index re-exports)
    public: bool = False         # used from outside the repo (a library's entry, a framework hook)
    inline_tests: bool = False   # carries its own tests (Rust #[cfg(test)])
    parse_error: str | None = None
    imports: tuple = ()          # Import, in source order; core resolves only these
    scope: str | None = None     # package, namespace or module this file declares into
    declares: tuple = ()         # top-level names it declares (for reference resolution)
    references: tuple = ()       # names it uses that might be declared elsewhere; resolvers
                                 # read these (Java wildcards), but a road needs an Import
```

### What core does with it

- **Units.** Core groups non-test source files by `unit_of`. A unit with several members sums
  `loc`, `complexity` and `notes`, and ORs `is_entry`, `public`, `is_package` and
  `inline_tests`. Its exports depend on its id:
  - a unit named after one of its members (a C header) takes that member's exports, because the
    header is the face other code sees;
  - a folder unit unions its members' exports, sorted.

  Its `parse_error` is the first member's by path, prefixed with that file's name
  (`"server.go: line 4: unexpected }"`). Its member list goes in `Module.members`. Test files
  are never grouped: each is its own test module.
- **Roads.** For each file's imports, core calls `resolve`, maps the targets to units with
  `unit_of`, and drops self-roads. Each resolved `Import` adds 1 to `Model.edges[(src, dst)]`.
  An import from a test adds the test to `tested_by` instead. `tests_for` adds more.
- **Tests by name.** The floor's name pairing also runs for adapter languages, adding to the
  links from imports. Python keeps its own filename rule.
- **Warehouses.** An outside name from a source file goes into `Model.externals`, as today.
- **Mentions.** Python keeps its current substring check, so the monorepo's town doesn't change. For
  other languages core tokenizes each text once into a set of `[A-Za-z0-9_./@-]+` tokens and
  checks membership, so mentions stay fast on large repos.
- **Renames** apply to file units only. A folder unit keeps its lot while its folder path is
  unchanged.

### Shared helpers in `langkit.py`

- `parse(grammar, text) -> Tree | None`: from the cached grammar, or None if it isn't ready.
- `walk(node)`, `node_text(node, source)` and `count_types(tree, types)`, where `types` can hold
  `("binary_expression", ("&&", "||"))` to count only those operators.
- `query(grammar, pattern)`: a cached `tree_sitter.Query`; run with `tree_sitter.QueryCursor`.
- `loc(text, tree, comment_types)` and `notes(tree, source, comment_types)`
- `first_error(tree) -> str | None`: `"line N: unexpected X"` from the first ERROR or MISSING node.
- `SymbolIndex(declarations)`, built from `(scope, name, path)` triples:
  - `lookup(scope, name)` returns the file declaring that name in that scope, or None when it is
    absent or ambiguous;
  - `lookup_all(scope, name)` returns every file declaring it, sorted, for languages where one
    name legitimately spans files (C# `partial`);
  - `in_scope(scope)` returns every file declaring into that scope, sorted.

  Java, Kotlin, C#, Swift and Ruby resolve references with it.

## Fire

`scan` always reports `parse_error` when the parser finds one. It becomes fire only when `FIRE`
allows it for that file: `True` for every file, `False` for none, or a tuple of extensions. One
adapter can cover a mature grammar and an immature one (Java and Kotlin). When fire isn't
allowed, core keeps the error in the inspector ("parser reports line N: ...") but raises no
problem.

Each language spec states its starting value. On the calibration repos, every fire must be a
real syntax error. A grammar gap means taking that extension out of `FIRE`, with the gap noted
in the module docstring.

## Model changes

`Module` gains fields with defaults, so old `model.json` files still load:

```python
lang: str = "python"
depth: str = "full"            # "full" or "floor"; ignored for kind "unsurveyed"
is_package: bool = False       # replaces the __init__.py check in problems.py
public: bool = False
inline_tests: bool = False
members: list = []             # files of a multi-file unit (Go folder, C header pair); else empty
```

Unit ids are repository-relative paths. A folder unit's id ends in `/`, and the root folder is
`./`. `district_of("cmd/server/")` is `cmd`, and `district_of("./")` is `(root)`.

## Problem changes

- **Abandoned** only for `depth == "full"`, and never for `is_package`, `is_entry`, `mentioned`
  or `public` modules.
- **Untested:** satisfied by `tested_by` or `inline_tests`, and never raised for `is_package`.
  Reasons:
  - Python keeps "no test imports it";
  - other full-depth languages get "no test reaches it";
  - floor buildings get "no test found for it by name".
- **All doors** can only happen at full depth, because the floor has no exports.
- **Hotspots** are ranked within each language: the top 5% of that language's full-depth
  sources by churn times complexity. Each language counts complexity its own way, and adding
  another language's buildings must not change which Python modules are hotspots. Only the
  repository's main language (the most full-depth sources) is promised at least one, so a lone
  script in another language isn't a hotspot. The floor's complexity is only a keyword count,
  so floor buildings are never hotspots.
- **Not code:** plain text, certificates, `.env` files and templates (ERB, Jinja, Handlebars,
  Twig, Liquid) are not buildings, whatever the language pack detects them as.
- **Fire** only where the adapter's `FIRE` allows it.
- **Unsurveyed** reasons: "unreadable: symlink, binary, over 1 MB or not UTF-8".
- Floor buildings are not problems. The survey report counts them by language instead.

## Drawing changes

- **Floor buildings** stand on `lot` ground like any source building. `drawtown` also draws the
  plot outline (the existing `OUTLINE` dashes) round the lot. They have no doors, because the
  floor finds no exports. Windows and annex keep their meaning, driven by tests found by name:
  an annex when a test pairs with the file, dark windows when none does.
- **The annex** is drawn for `tested_by` or `inline_tests`.
- **Inspector:**
  - the title gains the language label;
  - at floor depth the facts line reads "Go: size and history only, no roads yet (grammar not
    installed)" or "... (no Go adapter yet)", instead of import counts and exports;
  - multi-file units show "N files".
- **Harbor at scale.** The harbor line holds at most as many warehouses as fit the town's width.
  - Packages with the most users get their own warehouse, ties broken by name.
  - Once a package has a slot, it keeps it.
  - The rest share one last warehouse, `(more)`, whose inspector lists them.
  - This replaces Plan 2's decision 7, "the map widens to fit it", for large dependency lists.

## Commands

- **`towncode setup`:** the only command that uses the network. It downloads the grammars named
  in every importable adapter's `GRAMMARS` into the language pack's cache (outside every
  repository), then prints the cache folder and the package versions.
- **`towncode languages`:** one line per language. For example:

  ```
  Go          full   .go                  go (ready)
  Rust        floor  .rs                  rust (not installed: run towncode setup)
  Elixir      floor  .ex .exs             no adapter
  ```

- **`towncode survey`:** the report's second line is a languages summary, e.g. "Languages:
  Python 149 full, Shell 10 full, JavaScript/TypeScript 5 floor (no adapter yet)", followed by a
  "Parsers:" line with the tree-sitter versions. The district list counts floor buildings too.

## tree-sitter

- **Dependencies:** `tree-sitter` and `tree-sitter-language-pack`, pinned to the exact versions
  pip resolves when core is implemented, in a new `requirements.txt`. No version is chosen in
  this spec. The core implementer checks that wheels exist for the machine's Python (3.14 at the
  time of writing). If they don't, the README says which Python to make the venv with.
- **Install:** `python3 -m venv .venv`, then `.venv/bin/pip install -r requirements.txt`, then
  `.venv/bin/python towncode.py setup`. `.venv/` is git-ignored. With the system `python3` and no
  venv, everything still works: Python at full depth, the rest at floor.
- **API:** `tree_sitter_language_pack.get_language(name)` returns a real `tree_sitter.Language`.
  Parse with `tree_sitter.Parser(language)`. Query with `tree_sitter.Query(language, pattern)` and
  `tree_sitter.QueryCursor(query).captures(node)`.
- **No downloads during a survey.** `get_language` downloads missing grammars on its own.
  - Core only asks for grammars already in `downloaded_languages()` (or otherwise proven
    present without a fetch).
  - A missing grammar drops that language to floor depth for the run.
  - A test proves it: with `downloaded_languages()` reporting nothing and `get_language`
    patched to fail if called, a survey drops to floor depth without asking for any grammar.
    (Patching `socket.socket` proves nothing: the pack's downloader gets past it.)
- **Same code, same town.** Grammar output can change between versions, so versions are pinned.
  The survey report names the tree-sitter and language-pack versions it used.
- **Security.** Grammars are native libraries, fetched from the language pack's release
  downloads, at setup only. They parse text in-process and never run repository code. The
  release gate's Dependabot check covers `requirements.txt`.

## Read-only, unchanged

Every Plan 1 guarantee holds:

- only tracked files are read, through `Repo`;
- git runs read-only, with optional locks off;
- nothing is written inside the repository;
- saved files and the screen hold names and numbers only.

On top of that, no adapter may run a language's own tools (`npm`, `tsc`, `go`, `cargo`,
`gradle`, `mvn`, `dotnet`, `swift`, `bundle`, `make`, `cmake`). Build files are read as text and
never executed: `package.json`, `go.mod`, `Cargo.toml`, `*.csproj`, `Package.swift`, `Gemfile`,
`CMakeLists.txt`.

## Python behind the interface

`lang_python.py` wraps `pyscan` and `resolve` with no change in behaviour:

- `GRAMMARS = {}`, `FIRE = True`;
- `is_package` for `__init__.py`;
- its existing filename-test and mention rules.

Acceptance: for the `MONOREPO_LIKE` fixture, `model.json` from the new survey equals the old one,
ignoring the new fields' defaults. The controller then surveys the monorepo read-only and checks two
things: every Python building keeps its lot, and the same Python modules are flagged with the
same problem kinds. Python's untested reason keeps its old text, "no test imports it".

## Tests

Core ships:

- **`test_langs.py`, contract tests run against every importable adapter:**
  - Constants are well formed, `NAME` matches the registry, and no extension has two owners.
  - `scan` never raises on: an empty file, comments only, invalid syntax, a 200 KB single line,
    NUL bytes, and mixed scripts.
  - Determinism: surveying `SAMPLE` twice gives identical `model.json`.
  - Isolation: during `scan`, `resolver` and `resolve`, `builtins.open`, `os.open`,
    `os.listdir`, `os.scandir`, `subprocess.Popen` and `socket.socket` are patched to raise, and
    the survey still succeeds.
  - `resolve` only returns paths from `files`.
- **`langtest.py`, helpers for adapter tests:**
  - `survey_files(test, files) -> Model` builds a committed fixture repo and surveys it.
  - `edges(model)` returns `{(src, dst)}`.
  - `needs_grammar(name)` skips with "run towncode setup" when the grammar isn't cached. A
    language agent must finish with zero skips.
- **Floor tests:** each floor rule, including test pairing, ambiguity and comment markers.
- **Drawing tests:** a floor building has outline pixels and no doors; the harbor overflow merges
  into `(more)` and keeps existing slots.
- **Viewer tests:** floor facts text, and the folder-unit file count.
- **Command tests:** `towncode languages` output; `towncode setup` with the pack's download
  functions mocked (no network in tests).

## Work order, and rules for language agents

1. **Core** on branch `towncode-universal`, from `towncode-render` (pushed first; see "Status").
   It includes `lang_python.py`,
   `langs.py`, `langkit.py`, `langtest.py`, the floor, the model, problem, drawing and command
   changes, `requirements.txt`, README and `.gitignore`.
2. **Language agents, in parallel.** Each one works in its own worktree on branch
   `lang-<name>` from `towncode-universal`. Create it from `~/codetown` with
   `git worktree add ~/codetown-<name> -b lang-<name> towncode-universal`.
   Every agent follows these rules:
   - Create only `lang_<name>.py` and `test_lang_<name>.py`. If a core change looks necessary,
     stop and report it; don't edit core files.
   - Use the standard library plus tree-sitter only. Run tests with the main checkout's venv:
     `~/codetown/.venv/bin/python -m unittest`.
   - Never run the language's own tools, and never execute code from a surveyed repository.
   - Calibrate on the public repositories the language spec names, cloned into `/tmp`
     (`git clone --shallow-since="91 days ago" URL /tmp/towncode-cal/<name>`). Survey them with
     `--check-untouched`, and draw snapshots to `/tmp`. Never use `~/repos` or the monorepo.
   - **Done** means:
     - every required test in the language spec exists and passes, with zero skips;
     - the contract tests pass for this adapter;
     - the whole suite passes;
     - a calibration note is in the agent's report: modules, roads, warehouses, fires, the five
       loudest problems and whether each is plausible, false fires found, and survey time;
     - one commit on `lang-<name>`, not pushed.
3. **Merge.** Each `lang-*` branch merges into `towncode-universal`. The files don't overlap, so
   there are no conflicts. Then the whole suite runs, and the monorepo read-only check runs from
   the controller only.

## Out of scope

- Cross-language roads: Python running a shell script, TypeScript importing Rust through WASM.
  A later spec can add a `runs` pass over all languages.
- Running language servers or compilers for exact resolution.
- Performance work beyond the budget: a 5,000-file repository should survey in under 60
  seconds. If a calibration repo misses it, report it, don't optimise.
- Self-evident forms (Milestone 3).

## Decisions this spec makes

1. tree-sitter is the parser for every adapter except Python, which keeps `ast`.
2. The floor is standard-library only and covers every programming language.
3. Floor buildings reuse the unsurveyed gray outline, rather than a new colour.
4. Grammars are downloaded only by `towncode setup`, never during a survey.
5. Fire is opt-in per adapter, after calibration.
6. A building is "the unit other code imports". That's a file in most languages, a folder in
   Go, and a header/source pair in C and C++.
7. The harbor stops widening the map, and overflow shares one `(more)` warehouse.
8. Language agents touch only their own two files, and every core gap comes back as a report.
