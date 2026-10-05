# Towncode Survey (Milestone 1, Plan 1 of 2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Survey any git repository into a model of modules, imports and problems, and print the report the town will be drawn from, without ever changing the surveyed repository.

**Architecture:** A read-only `Repo` lists tracked files and git churn. `pyscan` parses each Python file into facts, and `resolve` maps imports to files or outside packages. `survey` assembles a `Model`, `layers` assigns saved rows (foundations at the back), and `problems` finds the ten problem kinds. `towncode.py survey` ties it together, saves `model.json` and `rows.json` outside the repo, and prints a names-and-numbers report. Plan 2 draws the town from these files.

**Tech Stack:** Python 3.10+ standard library only (`ast`, `subprocess`, `json`, `hashlib`, `unittest`), git CLI.

**Spec:** `docs/superpowers/specs/2026-09-30-codetown-site-plan-design.md`

## Global Constraints

- Python 3.10+ standard library only. No third-party packages.
- Flat modules in `~/codetown`, matching the existing files. Tests use `unittest`; run everything with `python3 -m unittest` from `~/codetown`.
- The surveyed repository is read-only:
  - The survey opens only files listed by `git ls-files`. Symlinks are never followed.
  - The `--check-untouched` fingerprint hashes tracked files and git's own files under `.git/`. Everything else gets only its size and modification time, so untracked files are never opened. Hashes stay in memory; only changed paths and counts are printed.
  - Code is parsed with `ast`, never imported, executed or tested.
  - git runs read-only commands only, with `GIT_OPTIONAL_LOCKS=0`.
  - Nothing is written inside it.
- Output goes to `~/codetown/.survey/<repo>-<hash>/` (or `$TOWNCODE_SURVEY_DIR`), never inside the surveyed repository. `.survey/` and `.sandbox/` are git-ignored in codetown.
- Reports and saved files contain names and numbers only, never file contents.
- Same input gives the same output: sort everything that is iterated.
- First real target: `~/repos/big-monorepo`. Never edit it, never run its code, never commit to it.
- Commits in this plan happen in `~/codetown` only.

## File Structure

| File | Responsibility |
| --- | --- |
| `fixture.py` | Test helper: throwaway git repos |
| `untouched.py` | Fingerprint a tree; diff two fingerprints |
| `repo.py` | Read-only git access: tracked files, text, churn |
| `pyscan.py` | Facts about one Python source text |
| `resolve.py` | Imports to repo files or outside package names |
| `model.py` | `Module` and `Model` dataclasses, JSON round trip |
| `survey.py` | Build a `Model` from a repo |
| `layers.py` | Import cycles, dependency layers, saved `Rows` |
| `problems.py` | The ten problem kinds, worst first |
| `towncode.py` | CLI: `survey PATH [--check-untouched]` |
| `test_*.py` | One test file per module above |

---

### Task 1: Read-only repository access

**Files:**
- Create: `fixture.py`, `untouched.py`, `repo.py`
- Modify: `.gitignore`
- Test: `test_repo.py`

**Interfaces:**
- Produces:
  - `fixture.make_repo(test, files: dict[str, str], untracked: dict | None = None) -> str` (repo root; removed on test cleanup)
  - `fixture.commit(root, files: dict, message="change", paths: list | None = None)`
  - `untouched.fingerprint(root, hashable=None) -> dict`: `hashable(rel) -> bool` picks the files whose contents may be read; the rest get size and modification time only, and `None` hashes everything
  - `untouched.differences(before, after) -> dict` (empty dict when identical)
  - `repo.Repo(root)` with `.root` (realpath), `.files() -> list[str]` (sorted tracked paths), `.read_text(rel) -> str | None`, and `.churn(days=90) -> dict[str, int]`
  - `repo.NotTracked` (exception)

- [ ] **Step 1: Write the test helper**

Create `fixture.py`:

```python
"""Test helper: throwaway git repositories for survey tests."""

import os
import shutil
import subprocess
import tempfile

GIT_ID = ["-c", "user.name=Fixture", "-c", "user.email=fixture@example.com",
          "-c", "commit.gpgsign=false", "-c", "core.hooksPath=/dev/null",
          "-c", "core.fsmonitor=false"]


def git(root, *args):
    subprocess.run(["git", "-C", root, *GIT_ID, *args], check=True, capture_output=True)


def write(root, files):
    for rel, text in files.items():
        path = os.path.join(root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)


def make_repo(test, files, untracked=None):
    """Create a committed repo; `untracked` files are written but never added."""
    root = tempfile.mkdtemp(prefix="towncode-fixture-")
    test.addCleanup(shutil.rmtree, root)
    subprocess.run(["git", "init", "-q", "-b", "main", root], check=True, capture_output=True)
    write(root, files)
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "fixture")
    if untracked:
        write(root, untracked)
    return root


def commit(root, files, message="change", paths=None):
    write(root, files)
    git(root, "add", "--", *(paths or list(files)))
    git(root, "commit", "-q", "-m", message)
```

- [ ] **Step 2: Write the failing test**

Create `test_repo.py`:

```python
import os
import unittest

import fixture
import untouched
from repo import NotTracked, Repo


class RepoTest(unittest.TestCase):
    def setUp(self):
        self.root = fixture.make_repo(
            self, {"a.py": "x = 1\n", "pkg/b.py": "y = 2\n"},
            untracked={"token.txt": "SECRET-TOKEN-123\n"})

    def test_files_lists_only_tracked_files(self):
        self.assertEqual(Repo(self.root).files(), ["a.py", "pkg/b.py"])

    def test_reading_an_untracked_file_is_refused(self):
        with self.assertRaises(NotTracked):
            Repo(self.root).read_text("token.txt")

    def test_reads_tracked_text(self):
        self.assertEqual(Repo(self.root).read_text("pkg/b.py"), "y = 2\n")

    def test_tracked_symlinks_are_not_followed(self):
        os.symlink(os.path.join(self.root, "token.txt"), os.path.join(self.root, "link.txt"))
        fixture.commit(self.root, {}, "add link", paths=["link.txt"])
        self.assertIsNone(Repo(self.root).read_text("link.txt"))

    def test_churn_counts_commits_per_file(self):
        fixture.commit(self.root, {"a.py": "x = 2\n"})
        fixture.commit(self.root, {"a.py": "x = 3\n"})
        churn = Repo(self.root).churn(days=90)
        self.assertEqual(churn["a.py"], 3)
        self.assertEqual(churn["pkg/b.py"], 1)

    def test_reading_leaves_the_repo_untouched(self):
        before = untouched.fingerprint(self.root)
        r = Repo(self.root)
        r.files()
        r.read_text("a.py")
        r.churn()
        self.assertEqual(untouched.differences(before, untouched.fingerprint(self.root)), {})

    def test_fingerprint_only_opens_files_it_is_allowed_to(self):
        prints = untouched.fingerprint(self.root, hashable=lambda rel: rel != "token.txt")
        self.assertIsNone(prints["token.txt"][3])
        self.assertIsNotNone(prints["a.py"][3])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `python3 -m unittest test_repo -v`
Expected: ERROR, `ModuleNotFoundError: No module named 'untouched'`.

- [ ] **Step 4: Write the fingerprinting module**

Create `untouched.py`:

```python
"""Fingerprint a directory tree to prove that reading it changed nothing."""

import hashlib
import os
import stat


def _digest(path):
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            for block in iter(lambda: f.read(1 << 20), b""):
                h.update(block)
    except OSError:
        return None
    return h.hexdigest()


def fingerprint(root, hashable=None):
    """Map each path to its type, size, mtime and (if `hashable` allows) content hash."""
    prints = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        prints[os.path.relpath(dirpath, root) + "/"] = ("dir", os.lstat(dirpath).st_mtime_ns)
        for name in dirnames:
            path = os.path.join(dirpath, name)
            if os.path.islink(path):
                prints[os.path.relpath(path, root)] = ("link", os.readlink(path))
        for name in sorted(filenames):
            path = os.path.join(dirpath, name)
            st = os.lstat(path)
            key = os.path.relpath(path, root)
            if stat.S_ISLNK(st.st_mode):
                prints[key] = ("link", os.readlink(path), st.st_mtime_ns)
            elif stat.S_ISREG(st.st_mode):
                digest = _digest(path) if hashable is None or hashable(key) else None
                prints[key] = ("file", st.st_size, st.st_mtime_ns, digest)
            else:
                prints[key] = ("other", st.st_mtime_ns)
    return prints


def differences(before, after):
    found = {
        "added": sorted(after.keys() - before.keys()),
        "removed": sorted(before.keys() - after.keys()),
        "changed": sorted(k for k in before.keys() & after.keys() if before[k] != after[k]),
    }
    return {k: v for k, v in found.items() if v}
```

- [ ] **Step 5: Write the read-only repository module**

Create `repo.py`:

```python
"""Read-only access to a git repository.

Only files git tracks are ever opened, symlinks are never followed, and git
runs with optional locks off so it does not even refresh its own index.
"""

import os
import subprocess

GIT_ENV = {"GIT_OPTIONAL_LOCKS": "0", "GIT_TERMINAL_PROMPT": "0"}
GIT_FLAGS = ["--no-pager", "-c", "core.fsmonitor=false", "-c", "core.untrackedCache=false",
             "-c", "core.quotepath=false"]
MAX_TEXT_BYTES = 1_000_000


class NotTracked(Exception):
    """Raised when asked to read a file git does not track."""


class Repo:
    def __init__(self, root):
        self.root = os.path.realpath(root)
        self._files = None
        self._tracked = set()

    def _git(self, *args):
        result = subprocess.run(["git", "-C", self.root, *GIT_FLAGS, *args],
                                check=True, capture_output=True,
                                env=dict(os.environ, **GIT_ENV))
        return result.stdout.decode("utf-8", errors="replace")

    def files(self):
        if self._files is None:
            self._files = sorted(p for p in self._git("ls-files", "-z").split("\0") if p)
            self._tracked = set(self._files)
        return self._files

    def read_text(self, rel):
        """Tracked file contents as text, or None if binary, huge, missing or a symlink."""
        self.files()
        if rel not in self._tracked:
            raise NotTracked(rel)
        path = os.path.join(self.root, rel)
        try:
            if os.path.islink(path) or os.path.getsize(path) > MAX_TEXT_BYTES:
                return None
            with open(path, "rb") as f:
                return f.read().decode("utf-8")
        except (OSError, UnicodeDecodeError):
            return None

    def churn(self, days=90):
        counts = {}
        out = self._git("log", f"--since={days}.days", "--no-renames", "--name-only", "--format=")
        for line in out.splitlines():
            if line.strip():
                counts[line] = counts.get(line, 0) + 1
        return counts
```

- [ ] **Step 6: Keep survey output out of git**

Append to `.gitignore`:

```text
.survey/
.sandbox/
```

- [ ] **Step 7: Run the tests to verify they pass**

Run: `python3 -m unittest test_repo -v`
Expected: 7 tests, all `ok`.

- [ ] **Step 8: Commit**

```bash
git add fixture.py untouched.py repo.py test_repo.py .gitignore
git commit -m "Add read-only repository access for surveys"
```

---

### Task 2: Facts about one Python module

**Files:**
- Create: `pyscan.py`
- Test: `test_pyscan.py`

**Interfaces:**
- Produces:
  - `pyscan.Import(module: str, level: int, names: tuple)` (frozen dataclass). `module` is `""` for `from . import x`; `names` is `()` for plain `import`.
  - `pyscan.PyFacts` with `imports: list[Import]`, `exports: tuple[str, ...]`, `loc: int`, `complexity: int`, `notes: int`, `is_entry: bool`, `parse_error: str | None`
  - `pyscan.scan(source: str) -> PyFacts`

- [ ] **Step 1: Write the failing test**

Create `test_pyscan.py`:

```python
import unittest

import pyscan
from pyscan import Import

BRANCHY = """\
def f(a, b):
    if a and b:
        return [x for x in a if x]
    for i in b:
        pass
    try:
        pass
    except ValueError:
        pass
    return 1 if a else 2
"""


class ImportsTest(unittest.TestCase):
    def test_plain_from_and_relative_imports(self):
        facts = pyscan.scan("import os, a.b\nfrom c import d, e\nfrom . import f\nfrom ..g import h\n")
        self.assertEqual(facts.imports, [
            Import("os", 0, ()), Import("a.b", 0, ()), Import("c", 0, ("d", "e")),
            Import("", 1, ("f",)), Import("g", 2, ("h",)),
        ])

    def test_imports_inside_functions_count(self):
        self.assertEqual(pyscan.scan("def f():\n    import late\n").imports, [Import("late", 0, ())])


class ExportsTest(unittest.TestCase):
    def test_dunder_all_wins(self):
        self.assertEqual(pyscan.scan("__all__ = ['b', 'a']\ndef c(): pass\n").exports, ("b", "a"))

    def test_public_functions_and_classes_by_default(self):
        src = "def run(): pass\ndef _hidden(): pass\nclass Thing: pass\nLIMIT = 3\n"
        self.assertEqual(pyscan.scan(src).exports, ("run", "Thing"))


class SizeTest(unittest.TestCase):
    def test_loc_skips_blank_and_comment_lines(self):
        self.assertEqual(pyscan.scan("# c\n\nx = 1\n  # d\ny = 2\n").loc, 2)

    def test_complexity_counts_decisions(self):
        # if, and, comprehension, its if, for, except, conditional expression
        self.assertEqual(pyscan.scan(BRANCHY).complexity, 1 + 7)


class NotesAndEntryTest(unittest.TestCase):
    def test_counts_todo_and_fixme_comments(self):
        src = "x = 1  # TODO: tidy\n# FIXME later\ns = 'TODO in a string'\n"
        self.assertEqual(pyscan.scan(src).notes, 2)

    def test_main_block_marks_an_entry_point(self):
        self.assertTrue(pyscan.scan("if __name__ == '__main__':\n    main()\n").is_entry)
        self.assertFalse(pyscan.scan("def main(): pass\n").is_entry)


class ParseErrorTest(unittest.TestCase):
    def test_syntax_error_is_reported_not_raised(self):
        facts = pyscan.scan("def broken(:\n    pass\n")
        self.assertIn("line 1", facts.parse_error)
        self.assertEqual(facts.loc, 2)
        self.assertEqual(facts.imports, [])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python3 -m unittest test_pyscan -v`
Expected: ERROR, `ModuleNotFoundError: No module named 'pyscan'`.

- [ ] **Step 3: Write the implementation**

Create `pyscan.py`:

```python
"""Static facts about one Python module: parsed from text, never imported or run."""

import ast
import re
import warnings
from dataclasses import dataclass, field

NOTE = re.compile(r"#.*\b(?:TODO|FIXME)\b")
DECISIONS = (ast.If, ast.For, ast.AsyncFor, ast.While, ast.ExceptHandler, ast.IfExp,
             ast.match_case)


@dataclass(frozen=True)
class Import:
    module: str
    level: int
    names: tuple


@dataclass
class PyFacts:
    imports: list = field(default_factory=list)
    exports: tuple = ()
    loc: int = 0
    complexity: int = 0
    notes: int = 0
    is_entry: bool = False
    parse_error: str | None = None


def scan(source):
    lines = source.splitlines()
    facts = PyFacts(
        loc=sum(1 for line in lines if line.strip() and not line.lstrip().startswith("#")),
        notes=sum(1 for line in lines if NOTE.search(line)),
    )
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            tree = ast.parse(source)
    except (SyntaxError, ValueError) as e:
        line = getattr(e, "lineno", None) or "?"
        facts.parse_error = f"line {line}: {getattr(e, 'msg', None) or e}"
        return facts
    facts.imports = _imports(tree)
    facts.exports = _exports(tree)
    facts.complexity = 1 + sum(_decisions(node) for node in ast.walk(tree))
    facts.is_entry = any(_is_main_guard(node) for node in tree.body)
    return facts


def _imports(tree):
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend(Import(alias.name, 0, ()) for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            found.append(Import(node.module or "", node.level,
                                tuple(alias.name for alias in node.names)))
    return found


def _exports(tree):
    for node in tree.body:
        if (isinstance(node, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == "__all__" for t in node.targets)
                and isinstance(node.value, (ast.List, ast.Tuple))):
            return tuple(e.value for e in node.value.elts
                         if isinstance(e, ast.Constant) and isinstance(e.value, str))
    return tuple(node.name for node in tree.body
                 if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
                 and not node.name.startswith("_"))


def _decisions(node):
    if isinstance(node, DECISIONS):
        return 1
    if isinstance(node, ast.BoolOp):
        return len(node.values) - 1
    if isinstance(node, ast.comprehension):
        return 1 + len(node.ifs)
    return 0


def _is_main_guard(node):
    if not isinstance(node, ast.If) or not isinstance(node.test, ast.Compare):
        return False
    test = node.test
    sides = [test.left, *test.comparators]
    names_it = any(isinstance(s, ast.Name) and s.id == "__name__" for s in sides)
    main = any(isinstance(s, ast.Constant) and s.value == "__main__" for s in sides)
    return names_it and main and len(test.ops) == 1 and isinstance(test.ops[0], ast.Eq)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3 -m unittest test_pyscan -v`
Expected: 9 tests, all `ok`.

- [ ] **Step 5: Commit**

```bash
git add pyscan.py test_pyscan.py
git commit -m "Parse Python modules into imports, exports, size and complexity"
```

---

### Task 3: Resolve imports to files or outside packages

The monorepo imports its SDK as `core_sdk` although it lives in `packages/core_sdk/`. Hub modules import siblings by bare name (`import records`), and `app` is ambiguous between `hub/app.py` and each `apps/*/app.py`. So resolution matches on path suffixes, preferring the closest file.

**Files:**
- Create: `resolve.py`
- Test: `test_resolve.py`

**Interfaces:**
- Consumes: `pyscan.Import`
- Produces:
  - `resolve.Resolver(py_paths: list[str], known_external: set[str] = ())`
  - `.resolve(importer: str, imp: Import) -> tuple[set[str], str | None]`: the repo paths the import reaches, plus the outside package's top-level name (or `None` when the import resolved in the repo, or is standard library)
  - `resolve.STDLIB` (set of names)

- [ ] **Step 1: Write the failing test**

Create `test_resolve.py`:

```python
import unittest

from pyscan import Import
from resolve import Resolver

FILES = [
    "desktop/__init__.py", "desktop/main.py", "desktop/launcher.py",
    "hub/app.py", "hub/records.py",
    "apps/sample-app/app.py",
    "packages/core_sdk/__init__.py", "packages/core_sdk/manifest.py",
    "tests/test_hub.py",
]


class ResolveTest(unittest.TestCase):
    def setUp(self):
        self.r = Resolver(FILES, known_external={"flask"})

    def resolve(self, importer, module, level=0, names=()):
        return self.r.resolve(importer, Import(module, level, tuple(names)))

    def test_package_import(self):
        self.assertEqual(self.resolve("desktop/main.py", "desktop.launcher"),
                         ({"desktop/launcher.py"}, None))

    def test_from_import_of_a_submodule_skips_the_package(self):
        self.assertEqual(self.resolve("desktop/main.py", "core_sdk", names=["manifest"]),
                         ({"packages/core_sdk/manifest.py"}, None))

    def test_from_import_of_a_name_lands_on_the_package(self):
        self.assertEqual(self.resolve("hub/app.py", "core_sdk", names=["check_app"]),
                         ({"packages/core_sdk/__init__.py"}, None))

    def test_sibling_script_import(self):
        self.assertEqual(self.resolve("hub/app.py", "records"), ({"hub/records.py"}, None))

    def test_ambiguous_name_prefers_the_same_folder(self):
        self.assertEqual(self.resolve("apps/sample-app/views.py", "app"),
                         ({"apps/sample-app/app.py"}, None))

    def test_ambiguous_name_then_prefers_the_shortest_path(self):
        self.assertEqual(self.resolve("tests/test_hub.py", "app"), ({"hub/app.py"}, None))

    def test_relative_import(self):
        self.assertEqual(self.resolve("desktop/main.py", "", level=1, names=["launcher"]),
                         ({"desktop/launcher.py"}, None))

    def test_stdlib_is_ignored_and_third_party_is_external(self):
        self.assertEqual(self.resolve("hub/app.py", "json"), (set(), None))
        self.assertEqual(self.resolve("hub/app.py", "flask"), (set(), "flask"))
        self.assertEqual(self.resolve("hub/app.py", "boto3.session"), (set(), "boto3"))

    def test_declared_requirement_beats_a_same_named_repo_file(self):
        r = Resolver(FILES + ["tools/flask.py"], known_external={"flask"})
        self.assertEqual(r.resolve("hub/app.py", Import("flask", 0, ())), (set(), "flask"))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python3 -m unittest test_resolve -v`
Expected: ERROR, `ModuleNotFoundError: No module named 'resolve'`.

- [ ] **Step 3: Write the implementation**

Create `resolve.py`:

```python
"""Map Python imports to files in the repository, or to outside packages."""

import sys

STDLIB = set(sys.stdlib_module_names) | {"__future__"}


def dotted_parts(path):
    parts = path[:-3].split("/")
    return parts[:-1] if parts[-1] == "__init__" else parts


def _shared(a, b):
    n = 0
    for x, y in zip(a, b):
        if x != y:
            break
        n += 1
    return n


class Resolver:
    def __init__(self, py_paths, known_external=()):
        self.known_external = set(known_external)
        self._full = {}
        self._by_suffix = {}
        for path in sorted(py_paths):
            parts = dotted_parts(path)
            if not parts:
                continue
            self._full.setdefault(".".join(parts), path)
            for k in range(1, len(parts) + 1):
                self._by_suffix.setdefault(".".join(parts[-k:]), []).append(path)

    def resolve(self, importer, imp):
        """Return (repo paths the import reaches, outside package name or None)."""
        if imp.level:
            return self._relative(importer, imp), None
        top = imp.module.split(".")[0]
        if top in STDLIB:
            return set(), None
        if top in self.known_external:
            return set(), top
        targets = set()
        if imp.names:
            package = None
            for name in imp.names:
                sub = self._pick(importer, f"{imp.module}.{name}") if name != "*" else None
                if sub:
                    targets.add(sub)
                elif package is None:
                    package = self._longest(importer, imp.module)
            if package:
                targets.add(package)
        else:
            found = self._longest(importer, imp.module)
            if found:
                targets.add(found)
        return (targets, None) if targets else (set(), top)

    def _longest(self, importer, dotted):
        parts = dotted.split(".")
        while parts:
            found = self._pick(importer, ".".join(parts))
            if found:
                return found
            parts.pop()
        return None

    def _pick(self, importer, dotted):
        candidates = self._by_suffix.get(dotted)
        if not candidates:
            return None
        here = importer.split("/")[:-1]

        def closeness(path):
            there = path.split("/")[:-1]
            return (there != here, -_shared(here, there), len(path), path)

        return min(candidates, key=closeness)

    def _relative(self, importer, imp):
        base = importer.split("/")[:-1]
        up = imp.level - 1
        if up > len(base):
            return set()
        base = base[:len(base) - up]
        prefix = base + (imp.module.split(".") if imp.module else [])
        targets = set()
        for name in imp.names:
            sub = self._full.get(".".join(prefix + [name]))
            package = self._full.get(".".join(prefix))
            if sub:
                targets.add(sub)
            elif package:
                targets.add(package)
        return targets
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3 -m unittest test_resolve -v`
Expected: 9 tests, all `ok`.

- [ ] **Step 5: Commit**

```bash
git add resolve.py test_resolve.py
git commit -m "Resolve imports by path suffix, preferring the closest file"
```

---

### Task 4: The model and the survey

**Files:**
- Create: `model.py`, `survey.py`
- Test: `test_survey.py`

**Interfaces:**
- Consumes: `repo.Repo`, `pyscan.scan`, `resolve.Resolver`, `fixture.make_repo`
- Produces:
  - `model.Module` dataclass: `id: str`, `district: str`, `kind: str` (`"source" | "test" | "unsurveyed"`), `loc: int`, `complexity: int`, `exports: list[str]`, `notes: int`, `is_entry: bool`, `parse_error: str | None`, `churn: int`, `mentioned: bool`, `tested_by: list[str]`
  - `model.Model` dataclass, with fields:
    - `repo: str`
    - `modules: dict[str, Module]`
    - `edges: dict[tuple[str, str], int]` (importer to imported, source modules only)
    - `externals: dict[str, list[str]]`
  - `Model` methods: `.of_kind(kind) -> list[Module]` (sorted by id), `.importers() -> dict[str, list[str]]` (imported id to sorted importer ids), `.to_dict()`, `Model.from_dict(d)`, `.save(path)`, `Model.load(path)`
  - `survey.survey(root) -> Model`
  - `test_survey.MONOREPO_LIKE` (fixture files, reused by Task 7)

- [ ] **Step 1: Write the failing test**

Create `test_survey.py`:

```python
import unittest

import fixture
import survey
from model import Model

MONOREPO_LIKE = {
    "packages/core_sdk/__init__.py": "",
    "packages/core_sdk/manifest.py": "def load(path):\n    return path\n",
    "packages/core_sdk/dev.py": "def run():\n    pass\n",
    "hub/app.py": ("from core_sdk import manifest\nimport records\nimport flask\nimport json\n\n"
                   "if __name__ == '__main__':\n    manifest.load('x')\n"),
    "hub/records.py": "import app\n# TODO: split this up\ndef save():\n    pass\n",
    "hub/unused.py": "def nobody():\n    pass\n",
    "desktop/broken.py": "def broken(:\n",
    "scripts/tool.sh": "echo hi\n",
    "tests/test_manifest.py": "from core_sdk import manifest\nMARKER = 'CANARY_SOURCE_TEXT'\n",
    "requirements.txt": "flask==3.0\n# a comment\n",
    "README.md": "Run `python -m core_sdk.dev` to preview an app.\n",
}


class SurveyTest(unittest.TestCase):
    def setUp(self):
        root = fixture.make_repo(self, MONOREPO_LIKE, untracked={
            "token.txt": "SECRET-TOKEN-123\n", "leftover.py": "x = 1\n"})
        self.model = survey.survey(root)

    def test_modules_tests_and_unsurveyed_files_are_classified(self):
        kinds = {m.id: m.kind for m in self.model.modules.values()}
        self.assertEqual(kinds["hub/app.py"], "source")
        self.assertEqual(kinds["tests/test_manifest.py"], "test")
        self.assertEqual(kinds["scripts/tool.sh"], "unsurveyed")
        self.assertNotIn("token.txt", kinds)
        self.assertNotIn("leftover.py", kinds)
        self.assertNotIn("README.md", kinds)

    def test_districts_are_top_level_folders(self):
        self.assertEqual(self.model.modules["packages/core_sdk/manifest.py"].district, "packages")

    def test_imports_become_edges(self):
        self.assertEqual(self.model.edges, {
            ("hub/app.py", "packages/core_sdk/manifest.py"): 1,
            ("hub/app.py", "hub/records.py"): 1,
            ("hub/records.py", "hub/app.py"): 1,
        })

    def test_outside_packages_skip_the_standard_library(self):
        self.assertEqual(self.model.externals, {"flask": ["hub/app.py"]})

    def test_tests_mark_what_they_import(self):
        self.assertEqual(self.model.modules["packages/core_sdk/manifest.py"].tested_by,
                         ["tests/test_manifest.py"])

    def test_facts_from_the_parser(self):
        mods = self.model.modules
        self.assertTrue(mods["hub/app.py"].is_entry)
        self.assertEqual(mods["hub/records.py"].notes, 1)
        self.assertIn("line 1", mods["desktop/broken.py"].parse_error)
        self.assertEqual(mods["hub/records.py"].churn, 1)

    def test_mentions_in_docs_and_config_count(self):
        self.assertTrue(self.model.modules["packages/core_sdk/dev.py"].mentioned)
        self.assertFalse(self.model.modules["hub/unused.py"].mentioned)

    def test_importers_lists_who_imports_each_module(self):
        self.assertEqual(self.model.importers()["hub/app.py"], ["hub/records.py"])

    def test_model_round_trips_through_json(self):
        self.assertEqual(Model.from_dict(self.model.to_dict()), self.model)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python3 -m unittest test_survey -v`
Expected: ERROR, `ModuleNotFoundError: No module named 'survey'`.

- [ ] **Step 3: Write the model**

Create `model.py`:

```python
"""The codebase model: plain data the town is built from."""

import json
from dataclasses import asdict, dataclass, field


@dataclass
class Module:
    id: str
    district: str
    kind: str
    loc: int = 0
    complexity: int = 0
    exports: list = field(default_factory=list)
    notes: int = 0
    is_entry: bool = False
    parse_error: str | None = None
    churn: int = 0
    mentioned: bool = False
    tested_by: list = field(default_factory=list)


@dataclass
class Model:
    repo: str
    modules: dict = field(default_factory=dict)
    edges: dict = field(default_factory=dict)
    externals: dict = field(default_factory=dict)

    def of_kind(self, kind):
        return [m for _, m in sorted(self.modules.items()) if m.kind == kind]

    def importers(self):
        found = {}
        for src, dst in sorted(self.edges):
            found.setdefault(dst, []).append(src)
        return found

    def to_dict(self):
        return {
            "repo": self.repo,
            "modules": [asdict(m) for _, m in sorted(self.modules.items())],
            "edges": [[s, d, n] for (s, d), n in sorted(self.edges.items())],
            "externals": {k: sorted(v) for k, v in sorted(self.externals.items())},
        }

    @classmethod
    def from_dict(cls, data):
        return cls(
            repo=data["repo"],
            modules={m["id"]: Module(**m) for m in data["modules"]},
            edges={(s, d): n for s, d, n in data["edges"]},
            externals={k: list(v) for k, v in data["externals"].items()},
        )

    def save(self, path):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=1, sort_keys=True)

    @classmethod
    def load(cls, path):
        with open(path, encoding="utf-8") as f:
            return cls.from_dict(json.load(f))
```

- [ ] **Step 4: Write the survey**

Create `survey.py`:

```python
"""Survey a repository into a Model. Every read goes through repo.Repo."""

import os
import re

import pyscan
from model import Model, Module
from repo import Repo
from resolve import Resolver

UNSURVEYED = {".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".sh", ".go", ".rb", ".java",
              ".kt", ".swift", ".rs", ".c", ".cc", ".cpp", ".h", ".m"}
TEXT = {".py", ".md", ".txt", ".toml", ".yml", ".yaml", ".json", ".cfg", ".ini", ".sh",
        ".html", ".js", ".mjs"}
TEXT_NAMES = {"Dockerfile", "Makefile", "Procfile"}
REQUIREMENT = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)")


def district_of(path):
    parts = path.split("/")
    return parts[0] if len(parts) > 1 else "(root)"


def is_test(path):
    parts = path.split("/")
    name = parts[-1]
    return (any(p in ("tests", "test") for p in parts[:-1]) or name.startswith("test_")
            or name.endswith("_test.py") or name == "conftest.py")


def requirement_names(texts):
    names = set()
    for path, text in texts.items():
        base = os.path.basename(path)
        if text is None or not (base.startswith("requirements") and base.endswith(".txt")):
            continue
        for line in text.splitlines():
            match = REQUIREMENT.match(line)
            if match and not line.lstrip().startswith(("#", "-")):
                names.add(match.group(1).lower().replace("-", "_"))
    return names


def mention_tokens(path):
    """Strings that, found in another file, mean something refers to this module."""
    parts = path[:-3].split("/")
    tokens = {path, f'"{parts[-1]}.py"', f"'{parts[-1]}.py'"}
    for k in range(2, len(parts) + 1):
        tokens.add(".".join(parts[-k:]))
    return tokens


def survey(root):
    repo = Repo(root)
    files = repo.files()
    texts = {f: repo.read_text(f) for f in files
             if os.path.splitext(f)[1] in TEXT or os.path.basename(f) in TEXT_NAMES}
    churn = repo.churn()
    py = [f for f in files if f.endswith(".py")]
    resolver = Resolver(py, known_external=requirement_names(texts))
    model = Model(repo=os.path.basename(repo.root))
    facts = {}
    for f in py:
        if texts.get(f) is None:
            model.modules[f] = Module(id=f, district=district_of(f), kind="unsurveyed",
                                      churn=churn.get(f, 0))
            continue
        fx = facts[f] = pyscan.scan(texts[f])
        model.modules[f] = Module(
            id=f, district=district_of(f), kind="test" if is_test(f) else "source",
            loc=fx.loc, complexity=fx.complexity, exports=list(fx.exports), notes=fx.notes,
            is_entry=fx.is_entry, parse_error=fx.parse_error, churn=churn.get(f, 0))
    for f in files:
        if os.path.splitext(f)[1] in UNSURVEYED:
            text = texts.get(f)
            model.modules[f] = Module(id=f, district=district_of(f), kind="unsurveyed",
                                      loc=len(text.splitlines()) if text else 0,
                                      churn=churn.get(f, 0))
    _connect(model, facts, resolver)
    _mark_mentions(model, texts)
    return model


def _connect(model, facts, resolver):
    externals = {}
    for f, fx in sorted(facts.items()):
        importer = model.modules[f]
        for imp in fx.imports:
            targets, outside = resolver.resolve(f, imp)
            for t in sorted(targets):
                target = model.modules.get(t)
                if t == f or target is None or target.kind != "source":
                    continue
                if importer.kind == "test":
                    if f not in target.tested_by:
                        target.tested_by.append(f)
                else:
                    model.edges[(f, t)] = model.edges.get((f, t), 0) + 1
            if outside and importer.kind == "source":
                externals.setdefault(outside, set()).add(f)
    model.externals = {k: sorted(v) for k, v in sorted(externals.items())}
    for m in model.modules.values():
        m.tested_by.sort()


def _mark_mentions(model, texts):
    for m in model.of_kind("source"):
        tokens = mention_tokens(m.id)
        m.mentioned = any(text and any(t in text for t in tokens)
                          for path, text in texts.items() if path != m.id)
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python3 -m unittest test_survey -v`
Expected: 9 tests, all `ok`.

- [ ] **Step 6: Commit**

```bash
git add model.py survey.py test_survey.py
git commit -m "Survey a repository into a model of modules, imports and tests"
```

---

### Task 5: Import cycles and saved rows

Rows put foundations at the back (row 0) and what is built on them further forward. Districts get rows from imports between districts, and modules get rows from imports inside their own district. Once something has a row it keeps it, so a new import that points the wrong way shows up as a backwards road instead of quietly reshuffling the town.

**Files:**
- Create: `layers.py`
- Test: `test_layers.py`

**Interfaces:**
- Consumes: `model.Model`, `model.Module`
- Produces:
  - `layers.strongly_connected(nodes, succ) -> list[list[str]]` (sinks first, each sorted)
  - `layers.layer_of(nodes, succ) -> tuple[dict[str, int], list[list[str]]]` (layers, cycles with more than one member)
  - `layers.cycles(model) -> list[list[str]]` (module import cycles among source modules)
  - `layers.Rows(districts=None, modules=None)`, with:
    - `.districts: dict[str, int]` and `.modules: dict[str, int]`
    - `.update(model) -> Rows`
    - `.is_backwards(model, src, dst) -> bool`
    - `.save(path)` and `Rows.load(path)` (a missing file gives empty rows)

- [ ] **Step 1: Write the failing test**

Create `test_layers.py`:

```python
import os
import shutil
import tempfile
import unittest

import layers
from layers import Rows
from model import Model, Module


def model_of(districts, edges):
    model = Model(repo="r")
    for id_, district in districts.items():
        model.modules[id_] = Module(id=id_, district=district, kind="source")
    model.edges = {e: 1 for e in edges}
    return model


class GraphTest(unittest.TestCase):
    def test_components_come_out_sinks_first(self):
        succ = {"a": {"b"}, "b": {"c"}, "c": {"b"}}
        self.assertEqual(layers.strongly_connected(["a", "b", "c"], succ), [["b", "c"], ["a"]])

    def test_foundations_are_layer_zero(self):
        succ = {"app": {"lib", "util"}, "lib": {"util"}}
        found, loops = layers.layer_of(["app", "lib", "util"], succ)
        self.assertEqual(found, {"app": 2, "lib": 1, "util": 0})
        self.assertEqual(loops, [])

    def test_a_cycle_shares_one_layer(self):
        succ = {"a": {"b"}, "b": {"a"}, "top": {"a"}}
        found, loops = layers.layer_of(["a", "b", "top"], succ)
        self.assertEqual((found["a"], found["b"], found["top"]), (0, 0, 1))
        self.assertEqual(loops, [["a", "b"]])

    def test_a_long_chain_does_not_hit_the_recursion_limit(self):
        nodes = [f"m{i:05d}" for i in range(5000)]
        succ = {a: {b} for a, b in zip(nodes, nodes[1:])}
        found, _ = layers.layer_of(nodes, succ)
        self.assertEqual((found[nodes[0]], found[nodes[-1]]), (4999, 0))

    def test_cycles_in_a_model(self):
        model = model_of({"a/x.py": "a", "a/y.py": "a", "a/z.py": "a"},
                         [("a/x.py", "a/y.py"), ("a/y.py", "a/x.py"), ("a/z.py", "a/x.py")])
        self.assertEqual(layers.cycles(model), [["a/x.py", "a/y.py"]])


class RowsTest(unittest.TestCase):
    def setUp(self):
        self.model = model_of(
            {"hub/app.py": "hub", "hub/records.py": "hub", "packages/sdk.py": "packages"},
            [("hub/app.py", "packages/sdk.py"), ("hub/app.py", "hub/records.py")])

    def test_district_and_module_rows(self):
        rows = Rows().update(self.model)
        self.assertEqual(rows.districts, {"packages": 0, "hub": 1})
        self.assertEqual(rows.modules,
                         {"hub/records.py": 0, "hub/app.py": 1, "packages/sdk.py": 0})

    def test_fresh_rows_have_no_backwards_roads(self):
        rows = Rows().update(self.model)
        self.assertFalse(any(rows.is_backwards(self.model, s, d) for s, d in self.model.edges))

    def test_saved_rows_hold_so_a_new_import_can_point_backwards(self):
        rows = Rows().update(self.model)
        self.model.edges[("packages/sdk.py", "hub/records.py")] = 1
        rows.update(self.model)
        self.assertEqual(rows.districts, {"packages": 0, "hub": 1})
        self.assertTrue(rows.is_backwards(self.model, "packages/sdk.py", "hub/records.py"))

    def test_rows_round_trip_and_a_missing_file_is_empty(self):
        folder = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, folder)
        path = os.path.join(folder, "rows.json")
        rows = Rows().update(self.model)
        rows.save(path)
        loaded = Rows.load(path)
        self.assertEqual((loaded.districts, loaded.modules), (rows.districts, rows.modules))
        self.assertEqual(Rows.load(path + ".missing").districts, {})


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python3 -m unittest test_layers -v`
Expected: ERROR, `ModuleNotFoundError: No module named 'layers'`.

- [ ] **Step 3: Write the implementation**

Create `layers.py`:

```python
"""Dependency layers: foundations at the back (row 0), what builds on them in front."""

import json
import os


def strongly_connected(nodes, succ):
    """Tarjan's algorithm without recursion. Components come out sinks first."""
    index, low, on_stack, stack, components = {}, {}, set(), [], []

    def visit(node):
        index[node] = low[node] = len(index)
        stack.append(node)
        on_stack.add(node)
        return node, iter(sorted(succ.get(node, ())))

    for start in sorted(nodes):
        if start in index:
            continue
        work = [visit(start)]
        while work:
            node, children = work[-1]
            for child in children:
                if child not in index:
                    work.append(visit(child))
                    break
                if child in on_stack:
                    low[node] = min(low[node], index[child])
            else:
                work.pop()
                if work:
                    parent = work[-1][0]
                    low[parent] = min(low[parent], low[node])
                if low[node] == index[node]:
                    component = []
                    while True:
                        member = stack.pop()
                        on_stack.discard(member)
                        component.append(member)
                        if member == node:
                            break
                    components.append(sorted(component))
    return components


def layer_of(nodes, succ):
    """Layer = longest import path down to a module that imports nothing here."""
    keep = set(nodes)
    succ = {n: {c for c in succ.get(n, ()) if c in keep} for n in keep}
    components = strongly_connected(keep, succ)
    component_of = {n: i for i, comp in enumerate(components) for n in comp}
    component_layer = []
    for i, comp in enumerate(components):
        below = [component_layer[component_of[c]]
                 for n in comp for c in succ[n] if component_of[c] != i]
        component_layer.append(1 + max(below) if below else 0)
    found = {n: component_layer[component_of[n]] for n in keep}
    return found, sorted(c for c in components if len(c) > 1)


def module_graph(model, district=None):
    nodes = [m.id for m in model.of_kind("source") if district in (None, m.district)]
    keep = set(nodes)
    succ = {}
    for src, dst in model.edges:
        if src in keep and dst in keep:
            succ.setdefault(src, set()).add(dst)
    return nodes, succ


def district_graph(model):
    sources = model.of_kind("source")
    nodes = sorted({m.district for m in sources})
    succ = {}
    for src, dst in model.edges:
        a, b = model.modules[src].district, model.modules[dst].district
        if a != b:
            succ.setdefault(a, set()).add(b)
    return nodes, succ


def cycles(model):
    return layer_of(*module_graph(model))[1]


class Rows:
    def __init__(self, districts=None, modules=None):
        self.districts = dict(districts or {})
        self.modules = dict(modules or {})

    def update(self, model):
        for name, row in sorted(layer_of(*district_graph(model))[0].items()):
            self.districts.setdefault(name, row)
        for district in sorted({m.district for m in model.of_kind("source")}):
            for name, row in sorted(layer_of(*module_graph(model, district))[0].items()):
                self.modules.setdefault(name, row)
        return self

    def is_backwards(self, model, src, dst):
        """True when an import reaches forward, from a foundation to what sits in front."""
        a, b = model.modules[src], model.modules[dst]
        if a.district != b.district:
            here, there = self.districts.get(a.district), self.districts.get(b.district)
        else:
            here, there = self.modules.get(src), self.modules.get(dst)
        return here is not None and there is not None and there > here

    def save(self, path):
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"districts": self.districts, "modules": self.modules}, f,
                      indent=1, sort_keys=True)

    @classmethod
    def load(cls, path):
        if not os.path.exists(path):
            return cls()
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return cls(data.get("districts"), data.get("modules"))
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3 -m unittest test_layers -v`
Expected: 9 tests, all `ok`.

- [ ] **Step 5: Commit**

```bash
git add layers.py test_layers.py
git commit -m "Find import cycles and give districts and modules saved rows"
```

---

### Task 6: The ten problems

Thresholds are named constants so Task 8 can tune them against the monorepo. A hotspot ranks by churn times complexity, so it needs to be both busy and complicated. Requiring the top 5% of each list separately would likely flag nothing on a repo of the monorepo's size.

**Files:**
- Create: `problems.py`
- Test: `test_problems.py`

**Interfaces:**
- Consumes: `model.Model`, `layers.Rows`, `layers.cycles`
- Produces:
  - `problems.Problem(kind, module, reason, other=None)` (frozen dataclass)
  - `problems.find(model, rows) -> list[Problem]`, sorted worst kind first, then module, then other
  - Kind constants: `FIRE`, `CYCLE`, `BACKWARDS`, `HOTSPOT`, `TOWER`, `ABANDONED`, `UNTESTED`, `ALL_DOORS`, `NOTES` and `UNSURVEYED`, with `problems.KINDS` listing them worst first. Their values are the report labels: `"won't parse"`, `"import cycle"`, `"backwards road"`, `"hotspot"`, `"tower"`, `"abandoned"`, `"untested"`, `"all doors"`, `"notes left"` and `"unsurveyed"`.

- [ ] **Step 1: Write the failing test**

Create `test_problems.py`:

```python
import unittest

import problems as p
from layers import Rows
from model import Model, Module

HEALTHY = {"is_entry": True, "tested_by": ["tests/test_it.py"], "loc": 10}


def build(specs, edges=()):
    model = Model(repo="r")
    for id_, fields in specs.items():
        fields = dict(fields)
        kind = fields.pop("kind", "source")
        model.modules[id_] = Module(id=id_, district=id_.split("/")[0], kind=kind, **fields)
    model.edges = {e: 1 for e in edges}
    return model


def found(model, rows=None):
    rows = rows if rows is not None else Rows().update(model)
    return [(x.kind, x.module) for x in p.find(model, rows)]


class ProblemsTest(unittest.TestCase):
    def test_a_healthy_module_has_no_problems(self):
        self.assertEqual(found(build({"a/x.py": HEALTHY})), [])

    def test_wont_parse_carries_the_error(self):
        model = build({"a/x.py": dict(HEALTHY, parse_error="line 3: invalid syntax")})
        self.assertEqual(p.find(model, Rows()),
                         [p.Problem(p.FIRE, "a/x.py", "line 3: invalid syntax")])

    def test_every_member_of_a_cycle_is_reported(self):
        model = build({"a/x.py": HEALTHY, "a/y.py": HEALTHY},
                      edges=[("a/x.py", "a/y.py"), ("a/y.py", "a/x.py")])
        self.assertEqual(found(model), [(p.CYCLE, "a/x.py"), (p.CYCLE, "a/y.py")])

    def test_backwards_road_is_reported_even_inside_a_cycle(self):
        model = build({"app/x.py": HEALTHY, "lib/y.py": HEALTHY}, edges=[("app/x.py", "lib/y.py")])
        rows = Rows().update(model)
        model.edges[("lib/y.py", "app/x.py")] = 1
        self.assertEqual(found(model, rows),
                         [(p.CYCLE, "app/x.py"), (p.CYCLE, "lib/y.py"), (p.BACKWARDS, "lib/y.py")])

    def test_hotspot_is_both_busy_and_complicated(self):
        specs = {f"a/m{i:02d}.py": dict(HEALTHY, churn=1, complexity=5) for i in range(20)}
        specs["a/busy.py"] = dict(HEALTHY, churn=9, complexity=5)
        specs["a/knotty.py"] = dict(HEALTHY, churn=1, complexity=150)
        specs["a/both.py"] = dict(HEALTHY, churn=6, complexity=40)
        self.assertEqual(found(build(specs)), [(p.HOTSPOT, "a/both.py")])

    def test_little_churn_is_never_a_hotspot(self):
        self.assertEqual(found(build({"a/x.py": dict(HEALTHY, churn=2, complexity=150)})), [])

    def test_tower_by_size_or_by_complexity(self):
        model = build({"a/big.py": dict(HEALTHY, loc=2400, complexity=90),
                       "a/knot.py": dict(HEALTHY, complexity=250)})
        self.assertEqual(found(model), [(p.TOWER, "a/big.py"), (p.TOWER, "a/knot.py")])

    def test_abandoned_unless_imported_run_or_mentioned(self):
        model = build({
            "a/lost.py": dict(HEALTHY, is_entry=False),
            "a/used.py": dict(HEALTHY, is_entry=False),
            "a/named.py": dict(HEALTHY, is_entry=False, mentioned=True),
            "a/__init__.py": dict(HEALTHY, is_entry=False),
            "a/main.py": HEALTHY,
        }, edges=[("a/main.py", "a/used.py")])
        self.assertEqual(found(model), [(p.ABANDONED, "a/lost.py")])

    def test_untested_skips_packages_and_empty_files(self):
        model = build({"a/x.py": dict(HEALTHY, tested_by=[]),
                       "a/__init__.py": dict(HEALTHY, tested_by=[]),
                       "a/empty.py": dict(HEALTHY, tested_by=[], loc=0)})
        self.assertEqual(found(model), [(p.UNTESTED, "a/x.py")])

    def test_all_doors_means_many_exports_over_little_code(self):
        doors = list("abcdef")
        model = build({"a/thin.py": dict(HEALTHY, exports=doors, loc=40),
                       "a/deep.py": dict(HEALTHY, exports=doors, loc=600)})
        self.assertEqual(found(model), [(p.ALL_DOORS, "a/thin.py")])

    def test_notes_and_unsurveyed(self):
        model = build({"a/x.py": dict(HEALTHY, notes=2), "a/tool.sh": {"kind": "unsurveyed"}})
        self.assertEqual(found(model), [(p.NOTES, "a/x.py"), (p.UNSURVEYED, "a/tool.sh")])

    def test_worst_first(self):
        model = build({"a/x.py": dict(HEALTHY, notes=1, parse_error="line 1: bad")})
        self.assertEqual([x.kind for x in p.find(model, Rows())], [p.FIRE, p.NOTES])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python3 -m unittest test_problems -v`
Expected: ERROR, `ModuleNotFoundError: No module named 'problems'`.

- [ ] **Step 3: Write the implementation**

Create `problems.py`:

```python
"""Where the work is: problems in a surveyed model, worst first."""

import os
from dataclasses import dataclass

import layers

FIRE = "won't parse"
CYCLE = "import cycle"
BACKWARDS = "backwards road"
HOTSPOT = "hotspot"
TOWER = "tower"
ABANDONED = "abandoned"
UNTESTED = "untested"
ALL_DOORS = "all doors"
NOTES = "notes left"
UNSURVEYED = "unsurveyed"
KINDS = [FIRE, CYCLE, BACKWARDS, HOTSPOT, TOWER, ABANDONED, UNTESTED, ALL_DOORS, NOTES,
         UNSURVEYED]

TOWER_LOC = 2000
TOWER_COMPLEXITY = 200
HOTSPOT_PERCENT = 5
HOTSPOT_MIN_CHURN = 3
ALL_DOORS_MIN_EXPORTS = 6
LINES_PER_DOOR = 10


@dataclass(frozen=True)
class Problem:
    kind: str
    module: str
    reason: str
    other: str | None = None


def find(model, rows):
    sources = model.of_kind("source")
    importers = model.importers()
    found = []
    for m in sources:
        if m.parse_error:
            found.append(Problem(FIRE, m.id, m.parse_error))
    for loop in layers.cycles(model):
        for member in loop:
            found.append(Problem(CYCLE, member, f"in an import loop of {len(loop)} modules"))
    for src, dst in sorted(model.edges):
        if rows.is_backwards(model, src, dst):
            found.append(Problem(BACKWARDS, src, f"reaches forward to {dst}", other=dst))
    found += _hotspots(sources)
    for m in sources:
        package = os.path.basename(m.id) == "__init__.py"
        if m.loc >= TOWER_LOC or m.complexity >= TOWER_COMPLEXITY:
            found.append(Problem(TOWER, m.id, f"{m.loc} lines, complexity {m.complexity}"))
        if not package and not importers.get(m.id) and not m.is_entry and not m.mentioned:
            found.append(Problem(ABANDONED, m.id, "nothing imports it"))
        if not package and m.loc and not m.tested_by:
            found.append(Problem(UNTESTED, m.id, "no test imports it"))
        doors = len(m.exports)
        if doors >= ALL_DOORS_MIN_EXPORTS and m.loc < doors * LINES_PER_DOOR:
            found.append(Problem(ALL_DOORS, m.id, f"{doors} exports over {m.loc} lines"))
        if m.notes:
            found.append(Problem(NOTES, m.id, f"{m.notes} TODO or FIXME note"
                                 + ("s" if m.notes > 1 else "")))
    for m in model.of_kind("unsurveyed"):
        found.append(Problem(UNSURVEYED, m.id, "not surveyed yet"))
    return sorted(found, key=lambda x: (KINDS.index(x.kind), x.module, x.other or ""))


def _hotspots(sources):
    """The top few by churn times complexity: code that is both busy and complicated."""
    top = max(1, len(sources) * HOTSPOT_PERCENT // 100)
    ranked = sorted(sources, key=lambda m: (-m.churn * m.complexity, m.id))[:top]
    return [Problem(HOTSPOT, m.id,
                    f"changed in {m.churn} commits in 90 days, complexity {m.complexity}")
            for m in ranked if m.churn >= HOTSPOT_MIN_CHURN and m.complexity]
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3 -m unittest test_problems -v`
Expected: 12 tests, all `ok`.

- [ ] **Step 5: Commit**

```bash
git add problems.py test_problems.py
git commit -m "Find the ten problem kinds, worst first"
```

---

### Task 7: The `towncode survey` command

**Files:**
- Create: `towncode.py`
- Test: `test_towncode.py`

**Interfaces:**
- Consumes: `survey.survey`, `repo.Repo`, `layers.Rows`, `problems.find`, `problems.KINDS`, `untouched.fingerprint`, `untouched.differences`, `test_survey.MONOREPO_LIKE`
- Produces:
  - `towncode.survey_root() -> str` (`$TOWNCODE_SURVEY_DIR`, else `~/codetown/.survey`)
  - `towncode.output_dir(repo_root) -> str` (`<survey_root>/<repo name>-<first 8 of sha256(realpath)>`)
  - `towncode.run(repo_root) -> tuple[Model, Rows, str]` (saves `model.json` and `rows.json`; raises `SystemExit` for a non-repo or an output path inside the repo)
  - `towncode.report(model, rows, found) -> str`
  - `towncode.main(argv) -> int` (exit code: 0, or 1 when `--check-untouched` finds a change)

- [ ] **Step 1: Write the failing test**

Create `test_towncode.py`:

```python
import contextlib
import io
import os
import shutil
import tempfile
import unittest
from unittest import mock

import fixture
import towncode
import untouched
from test_survey import MONOREPO_LIKE


class TowncodeTest(unittest.TestCase):
    def setUp(self):
        self.root = fixture.make_repo(self, MONOREPO_LIKE,
                                      untracked={"token.txt": "SECRET-TOKEN-123\n"})
        self.out = tempfile.mkdtemp(prefix="towncode-out-")
        self.addCleanup(shutil.rmtree, self.out)
        env = mock.patch.dict(os.environ, {"TOWNCODE_SURVEY_DIR": self.out})
        env.start()
        self.addCleanup(env.stop)

    def survey(self, *flags):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = towncode.main(["survey", self.root, *flags])
        return code, buf.getvalue()

    def saved(self, name):
        with open(os.path.join(towncode.output_dir(self.root), name), encoding="utf-8") as f:
            return f.read()

    def test_report_lists_districts_back_row_first_and_problems(self):
        code, text = self.survey()
        self.assertEqual(code, 0)
        for expected in ["row 0  packages", "row 1  hub", "won't parse (1)", "import cycle (2)",
                         "hub/unused.py: nothing imports it", "unsurveyed (1)"]:
            self.assertIn(expected, text)
        self.assertLess(text.index("row 0  packages"), text.index("row 1  hub"))

    def test_model_and_rows_are_saved_outside_the_repo(self):
        self.survey()
        self.assertEqual(os.path.dirname(towncode.output_dir(self.root)), self.out)
        self.assertIn('"hub/app.py"', self.saved("model.json"))
        self.assertIn('"packages": 0', self.saved("rows.json"))

    def test_the_repo_is_untouched(self):
        before = untouched.fingerprint(self.root)
        self.survey()
        self.assertEqual(untouched.differences(before, untouched.fingerprint(self.root)), {})

    def test_check_untouched_confirms(self):
        code, text = self.survey("--check-untouched")
        self.assertEqual(code, 0)
        self.assertIn("untouched: yes", text)

    def test_check_untouched_fails_when_something_changes(self):
        real = towncode.survey.survey

        def meddling(root):
            with open(os.path.join(root, "hub", "records.py"), "a", encoding="utf-8") as f:
                f.write("# meddled\n")
            return real(root)

        with mock.patch.object(towncode.survey, "survey", meddling):
            code, text = self.survey("--check-untouched")
        self.assertEqual(code, 1)
        self.assertIn("untouched: NO", text)
        self.assertIn("hub/records.py", text)

    def test_check_untouched_never_opens_untracked_files(self):
        opened = []
        real = untouched._digest

        def spy(path):
            opened.append(os.path.relpath(path, self.root))
            return real(path)

        with mock.patch.object(untouched, "_digest", spy):
            self.survey("--check-untouched")
        self.assertIn("hub/app.py", opened)
        self.assertTrue(any(p.startswith(".git" + os.sep) for p in opened))
        self.assertNotIn("token.txt", opened)

    def test_no_file_contents_or_untracked_names_leak(self):
        _, text = self.survey()
        saved = self.saved("model.json") + self.saved("rows.json")
        for secret in ["CANARY_SOURCE_TEXT", "SECRET-TOKEN-123", "token.txt"]:
            self.assertNotIn(secret, text)
            self.assertNotIn(secret, saved)

    def test_surveys_are_repeatable(self):
        self.survey()
        first = self.saved("model.json"), self.saved("rows.json")
        self.survey()
        self.assertEqual((self.saved("model.json"), self.saved("rows.json")), first)

    def test_refuses_to_write_inside_the_repo(self):
        inside = os.path.join(self.root, ".survey")
        with mock.patch.dict(os.environ, {"TOWNCODE_SURVEY_DIR": inside}):
            with self.assertRaises(SystemExit):
                self.survey()
        self.assertFalse(os.path.exists(inside))

    def test_refuses_a_folder_that_is_not_a_repo(self):
        with self.assertRaises(SystemExit):
            towncode.main(["survey", self.out])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python3 -m unittest test_towncode -v`
Expected: ERROR, `ModuleNotFoundError: No module named 'towncode'`.

- [ ] **Step 3: Write the implementation**

Create `towncode.py`:

```python
"""Towncode: survey a repository into the model its town is drawn from.

    python3 towncode.py survey PATH [--check-untouched]

The surveyed repository is only read. Output goes to .survey/ next to this
file, or to $TOWNCODE_SURVEY_DIR, and never inside the repository.
"""

import argparse
import hashlib
import os
import sys

import problems
import survey
import untouched
from layers import Rows
from repo import Repo

HERE = os.path.dirname(os.path.abspath(__file__))
REPORT_LIMIT = 10


def _n(count, word):
    return f"{count} {word}" if count == 1 else f"{count} {word}s"


def survey_root():
    return os.environ.get("TOWNCODE_SURVEY_DIR") or os.path.join(HERE, ".survey")


def output_dir(repo_root):
    real = os.path.realpath(repo_root)
    tag = hashlib.sha256(real.encode("utf-8")).hexdigest()[:8]
    return os.path.join(survey_root(), f"{os.path.basename(real)}-{tag}")


def _inside(path, root):
    path, root = os.path.realpath(path), os.path.realpath(root)
    return path == root or path.startswith(root + os.sep)


def _require_repo(path):
    if not os.path.exists(os.path.join(path, ".git")):
        raise SystemExit(f"not a git repository: {path}")


def _fingerprint(repo_root, tracked):
    """Hash tracked files and git's own files; only stat the rest, never open them."""
    return untouched.fingerprint(
        repo_root, hashable=lambda rel: rel in tracked or rel.startswith(".git" + os.sep))


def run(repo_root):
    _require_repo(repo_root)
    out = output_dir(repo_root)
    if _inside(out, repo_root):
        raise SystemExit(f"refusing to write inside the surveyed repository: {out}")
    model = survey.survey(repo_root)
    os.makedirs(out, exist_ok=True)
    rows_path = os.path.join(out, "rows.json")
    rows = Rows.load(rows_path).update(model)
    model.save(os.path.join(out, "model.json"))
    rows.save(rows_path)
    return model, rows, out


def report(model, rows, found):
    counts = {k: len(model.of_kind(k)) for k in ("source", "test", "unsurveyed")}
    lines = [f"{model.repo}: {_n(counts['source'], 'module')}, {_n(counts['test'], 'test')}, "
             f"{_n(counts['unsurveyed'], 'unsurveyed file')}, {_n(len(model.edges), 'road')}, "
             f"{_n(len(model.externals), 'outside package')}", "", "Districts, back row first:"]
    sizes = {}
    for m in model.of_kind("source"):
        sizes[m.district] = sizes.get(m.district, 0) + 1
    for name in sorted(sizes, key=lambda d: (rows.districts.get(d, 0), d)):
        lines.append(f"  row {rows.districts.get(name, 0)}  {name} ({_n(sizes[name], 'module')})")
    lines += ["", "Problems, worst first:" if found else "No problems found."]
    groups = {}
    for x in found:
        groups.setdefault(x.kind, []).append(x)
    for kind in problems.KINDS:
        group = groups.get(kind, [])
        if not group:
            continue
        lines.append(f"{kind} ({len(group)})")
        lines += [f"  {x.module}: {x.reason}" for x in group[:REPORT_LIMIT]]
        if len(group) > REPORT_LIMIT:
            lines.append(f"  ... and {len(group) - REPORT_LIMIT} more")
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(prog="towncode")
    commands = parser.add_subparsers(dest="command", required=True)
    cmd = commands.add_parser("survey", help="survey a git repository without changing it")
    cmd.add_argument("path")
    cmd.add_argument("--check-untouched", action="store_true",
                     help="fingerprint the repository before and after; fail on any change")
    args = parser.parse_args(argv)
    _require_repo(args.path)
    tracked = set(Repo(args.path).files()) if args.check_untouched else None
    before = _fingerprint(args.path, tracked) if args.check_untouched else None
    model, rows, out = run(args.path)
    print(report(model, rows, problems.find(model, rows)))
    print(f"\nsaved to {out}")
    if before is None:
        return 0
    diff = untouched.differences(before, _fingerprint(args.path, tracked))
    if diff:
        print(f"untouched: NO, {sum(len(v) for v in diff.values())} paths differ")
        for change, paths in diff.items():
            print(f"  {change}: {', '.join(paths[:REPORT_LIMIT])}")
        return 1
    print(f"untouched: yes, {len(before)} paths identical before and after")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3 -m unittest test_towncode -v`
Expected: 10 tests, all `ok`.

- [ ] **Step 5: Run the whole suite**

Run: `python3 -m unittest`
Expected: all tests pass, the game's 49 plus this plan's 65.

- [ ] **Step 6: Commit**

```bash
git add towncode.py test_towncode.py
git commit -m "Add towncode survey: report, saved model and untouched check"
```

---

### Task 8: Calibrate on the monorepo (read-only)

This task runs the tool on the monorepo and tunes it. It never edits, runs, or commits anything in the monorepo. Every fix happens in `~/codetown`, test first.

- [ ] **Step 1: Survey the monorepo with the untouched check**

Run: `python3 towncode.py survey ~/repos/big-monorepo --check-untouched`
Expected: a report, `saved to .../.survey/big-monorepo-<hash>`, and a final line starting `untouched: yes`. If it says `untouched: NO`, stop, report the listed paths to the user, and fix the cause before anything else.

- [ ] **Step 2: Sanity-check the shape**

Compare the header against the module and test counts found earlier. `packages` should be on row 0. Then check who has the most importers:

Run: `python3 -c "from model import Model; import glob; m = Model.load(glob.glob('.survey/big-monorepo-*/model.json')[0]); print(sorted(((len(v), k) for k, v in m.importers().items()), reverse=True)[:5])"`
Expected: `packages/core_sdk/manifest.py` at or near the top, since most of the repo imports it.

- [ ] **Step 3: Spot-check the loud problems by reading, never running**

For each `won't parse`, `import cycle`, `backwards road` and `abandoned` entry, open the file read-only and confirm the claim. A dynamically loaded app that the report calls abandoned is a false alarm. For each false alarm:

1. Add a failing case to the matching test file, reproducing the pattern with a made-up fixture. Never copy the monorepo code into the test.
2. Fix the survey or the threshold until the test passes.
3. Run `python3 -m unittest` and re-run Step 1.

- [ ] **Step 4: Agree the loud spots with the user**

Show the user the problem counts and the top entries of each kind. Ask whether the loudest spots match where they know the work is. Tune thresholds in `problems.py` only with their agreement.

- [ ] **Step 5: Commit calibration fixes (codetown only)**

```bash
git status --short
git add -u
git commit -m "Calibrate the survey against a real repository"
```

`git status` must not list `.survey/`; it is ignored so the monorepo's module names never reach GitHub.

---

## Plan 2 outline: the rendered town (written after Task 8)

1. **Projection and zoom:** lift the tile size out of `iso.py` constants so the town can be drawn at 1 or 2 pixels per unit.
2. **Lots and plat:** pack each district's modules into lots by row, alphabetical within a row, with the lot size set by lines of code. Save the plat next to `rows.json` so new modules do not reshuffle the town. Add `Repo.renames()` (read-only `git log -M --name-status`) so a renamed module keeps its plot and its row.
3. **Code-town scene:** buildings with height from complexity, the harbor for outside packages behind the town, and a test yard per district.
4. **Problem visuals:** fire, looping roads, red backwards roads, scaffolding for hotspots, towers, boarded-up abandoned buildings, a missing inspection sign for untested, a wall of doors, notes pinned to doors, and fog over unsurveyed files.
5. **Roads:** route imports along streets, collapse parallel roads, and hide roads that are not selected when the town is busy.
6. **Camera, cursor and inspector:** move around, jump between problems with `n` and `p`, and show a building's facts.
7. **`towncode view PATH`:** a survey followed by the town, in the terminal.

