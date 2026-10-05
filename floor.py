"""Facts any source file gives without a parser: size, notes, rough complexity, tests by name."""

import os
import re

HASH = ("#",)
SLASH = ("//", "/*", "*")
DASH = ("--",)
SEMI = (";",)


def _table(*groups):
    table = {}
    for key, label, markers, extensions in groups:
        for ext in extensions.split():
            table[ext] = (key, label, markers)
    return table


FLOOR_LANGUAGES = _table(
    ("python", "Python", HASH, ".py"),
    ("javascript", "JavaScript/TypeScript", SLASH, ".js .jsx .mjs .cjs .ts .tsx .mts .cts"),
    ("shell", "Shell", HASH, ".sh .bash .zsh .ksh .bats"),
    ("go", "Go", SLASH, ".go"),
    ("jvm", "Java/Kotlin", SLASH, ".java .kt .kts"),
    ("csharp", "C#", SLASH, ".cs"),
    ("rust", "Rust", SLASH, ".rs"),
    ("ruby", "Ruby", HASH, ".rb .rake .ru"),
    ("cfamily", "C/C++", SLASH,
     ".c .h .cc .cpp .cxx .c++ .hh .hpp .hxx .h++ .ipp .tpp .inl"),
    ("swift", "Swift", SLASH, ".swift"),
    ("objc", "Objective-C", SLASH, ".m .mm"),
    ("scala", "Scala", SLASH, ".scala .sc"),
    ("groovy", "Groovy", SLASH, ".groovy"),
    ("php", "PHP", ("//", "#", "/*", "*"), ".php"),
    ("perl", "Perl", HASH, ".pl .pm"),
    ("lua", "Lua", DASH, ".lua"),
    ("r", "R", HASH, ".r .R"),
    ("julia", "Julia", HASH, ".jl"),
    ("dart", "Dart", SLASH, ".dart"),
    ("elixir", "Elixir", HASH, ".ex .exs"),
    ("erlang", "Erlang", ("%",), ".erl .hrl"),
    ("haskell", "Haskell", ("--", "{-"), ".hs"),
    ("ocaml", "OCaml", ("(*", "*"), ".ml .mli"),
    ("fsharp", "F#", ("//", "(*", "*"), ".fs .fsi .fsx"),
    ("clojure", "Clojure", SEMI, ".clj .cljs .cljc"),
    ("lisp", "Lisp", SEMI, ".lisp .lsp .el"),
    ("scheme", "Scheme/Racket", SEMI, ".scm .ss .rkt"),
    ("elm", "Elm", ("--", "{-"), ".elm"),
    ("zig", "Zig", ("//",), ".zig"),
    ("nim", "Nim", HASH, ".nim"),
    ("crystal", "Crystal", HASH, ".cr"),
    ("d", "D", SLASH, ".d"),
    ("solidity", "Solidity", SLASH, ".sol"),
    ("vue", "Vue", ("//", "/*", "*", "<!--"), ".vue"),
    ("svelte", "Svelte", ("//", "/*", "*", "<!--"), ".svelte"),
    ("powershell", "PowerShell", ("#", "<#"), ".ps1 .psm1"),
    ("batch", "Batch", ("REM ", "rem ", "::"), ".bat .cmd"),
    ("fish", "Fish", HASH, ".fish"),
    ("awk", "AWK", HASH, ".awk"),
    ("tcl", "Tcl", HASH, ".tcl"),
    ("fortran", "Fortran", ("!",), ".f90 .f95 .f03 .f08"),
    ("pascal", "Pascal", ("//", "{", "(*"), ".pas"),
    ("ada", "Ada", DASH, ".adb .ads"),
    ("cobol", "COBOL", ("*",), ".cob .cbl"),
    ("vbnet", "Visual Basic", ("'",), ".vb"),
    ("haxe", "Haxe", SLASH, ".hx"),
    ("gdscript", "GDScript", HASH, ".gd"),
    ("cuda", "CUDA", SLASH, ".cu .cuh"),
    ("terraform", "Terraform", ("#", "//", "/*", "*"), ".tf"),
    ("nix", "Nix", HASH, ".nix"),
    ("coffeescript", "CoffeeScript", HASH, ".coffee"),
    ("cython", "Cython", HASH, ".pyx .pxd"),
    ("arduino", "Arduino", SLASH, ".ino"),
    ("assembly", "Assembly", (";", "#", "//"), ".asm .s .S"),
    ("verilog", "Verilog", SLASH, ".sv .svh"),
    ("vhdl", "VHDL", DASH, ".vhd .vhdl"),
    ("apex", "Apex", SLASH, ".cls .trigger"),
    ("matlab", "MATLAB", ("%",), ".mlx"),
    ("vim", "Vim script", ('"',), ".vim"),
)

SHEBANG_LANGUAGES = {
    "sh": "shell", "bash": "shell", "zsh": "shell", "dash": "shell", "ksh": "shell",
    "node": "javascript", "deno": "javascript", "bun": "javascript", "ts-node": "javascript",
    "tsx": "javascript", "ruby": "ruby", "swift": "swift",
    "perl": "perl", "php": "php", "lua": "lua", "Rscript": "r", "julia": "julia",
    "elixir": "elixir", "tclsh": "tcl", "fish": "fish", "pwsh": "powershell",
    "awk": "awk", "gawk": "awk",
}

LABELS = {key: label for key, label, _ in FLOOR_LANGUAGES.values()}
DEFAULT_MARKERS = ("#", "//", "/*", "*")

NOT_CODE = frozenset("""
markdown markdown_inline json jsonc json5 yaml toml xml csv tsv ini html css scss sass less svg
dockerfile make cmake gitignore gitattributes properties sql graphql proto protobuf rst latex
tex bibtex diff regex comment requirements nginx ssh_config gomod gosum gowork dot mermaid po
jsdoc org asciidoc starlark meson ninja kconfig devicetree http query embedded_template
doxygen printf editorconfig gitcommit git_config git_rebase hcl text plaintext vimdoc luadoc
pem dotenv dtd embeddedtemplate jinja2 glimmer twig liquid
""".split())

TEST_DIRS = {"test", "tests", "spec", "specs", "__tests__", "testing"}
DECISIONS = re.compile(
    r"\b(?:if|elif|elsif|for|foreach|while|until|case|when|catch|except|rescue|guard)\b|&&|\|\|")
NOTE = re.compile(r"\b(?:TODO|FIXME)\b")
SHEBANG = re.compile(r"^#!\s*(\S+)(?:\s+(?:-\S+\s+)*(\S+))?")


def interpreter(text):
    """The program a shebang line names: 'bash' for both #!/bin/bash and #!/usr/bin/env bash."""
    if not text or not text.startswith("#!"):
        return None
    match = SHEBANG.match(text.splitlines()[0])
    if not match:
        return None
    program = os.path.basename(match.group(1))
    if program == "env" and match.group(2):
        program = os.path.basename(match.group(2))
    return program


def markers_for(path):
    entry = FLOOR_LANGUAGES.get(os.path.splitext(path)[1])
    return entry[2] if entry else DEFAULT_MARKERS


def _is_comment(line, markers):
    return line.startswith(markers)


def facts(path, text):
    """(loc, complexity, notes) for one file, from its lines alone."""
    markers = markers_for(path)
    loc = complexity = notes = 0
    for i, raw in enumerate(text.splitlines()):
        line = raw.strip()
        if not line or (i == 0 and line.startswith("#!")):
            continue
        if _is_comment(line, markers):
            if NOTE.search(line):
                notes += 1
            continue
        loc += 1
        complexity += len(DECISIONS.findall(line))
    return loc, 1 + complexity, notes


def is_test(path):
    parts = path.split("/")
    return any(p in TEST_DIRS for p in parts[:-1]) or test_stem(parts[-1]) is not None


def test_stem(name):
    """The stem a test file's name points at ('a' for a_test.go, a.test.ts, test_a.py,
    ATest.java), or None when the name carries no test marker."""
    root = os.path.splitext(name)[0]
    head, marker = os.path.splitext(root)
    if marker in (".test", ".spec") and head:
        return head
    if root.startswith("test_") and len(root) > 5:
        return root[5:]
    for suffix in ("_test", "_spec", "Tests", "Test"):
        if root.endswith(suffix) and len(root) > len(suffix):
            return root[:-len(suffix)]
    return None


def _stem(path):
    return os.path.splitext(os.path.basename(path))[0]


def _plain_folders(path):
    keep = TEST_DIRS | {"src", "lib", "main", "app"}
    return [p for p in path.split("/")[:-1] if p not in keep]


def pair_tests(tests, sources):
    """{test path: source path} for tests whose name points at exactly one source file.

    `tests` and `sources` are {path: language key}; only files in the same language pair.
    Prefer a source in the same folder, then one at the mirrored path, then the only one.
    """
    by_stem = {}
    for path, lang in sorted(sources.items()):
        by_stem.setdefault((lang, _stem(path)), []).append(path)
    found = {}
    for test, lang in sorted(tests.items()):
        name = os.path.basename(test)
        stem = test_stem(name) or _stem(test)
        candidates = by_stem.get((lang, stem), [])
        here = os.path.dirname(test)
        for pick in (
                [c for c in candidates if os.path.dirname(c) == here],
                [c for c in candidates if _plain_folders(c) == _plain_folders(test)],
                candidates):
            if len(pick) == 1:
                found[test] = pick[0]
                break
            if len(pick) > 1:
                break
    return found


def is_minified(text):
    lines = text.splitlines()
    if not lines:
        return False
    return max(len(line) for line in lines) > 1000 and len(text) / len(lines) > 200
