"""Python, read with the standard library's own parser: pyscan for facts, resolve for imports."""

import ast
import os
import re
import warnings

import langkit
import pyscan
import resolve

NAME = "python"
LABEL = "Python"
EXTENSIONS = (".py",)
SHEBANGS = ()
GRAMMARS = {}
CONFIG = ("requirements*.txt",)
FIRE = True
SAMPLE = {
    "pkg/__init__.py": "",
    "pkg/a.py": "from pkg import b\n\n\ndef f():\n    return b.g()\n",
    "pkg/b.py": "import json\nimport requests\n\n\ndef g():\n    return json.dumps(1)\n",
    "tests/test_a.py": "from pkg import a\n",
    "requirements.txt": "requests==2.0\n",
}

MENTION_TEXT = {".py", ".md", ".txt", ".toml", ".yml", ".yaml", ".json", ".cfg", ".ini", ".sh",
                ".html", ".js", ".mjs"}
MENTION_NAMES = {"Dockerfile", "Makefile", "Procfile"}
REQUIREMENT = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)")


def unit_of(path, files):
    return path


def is_test(path, text=None):
    parts = path.split("/")
    name = parts[-1]
    return (any(p in ("tests", "test") for p in parts[:-1]) or name.startswith("test_")
            or name.endswith("_test.py") or name == "conftest.py")


def scan(path, text, tree):
    fx = pyscan.scan(text)
    return langkit.Facts(
        loc=fx.loc, complexity=fx.complexity, exports=tuple(fx.exports), notes=fx.notes,
        is_entry=fx.is_entry, is_package=os.path.basename(path) == "__init__.py",
        parse_error=fx.parse_error,
        imports=tuple(langkit.Import("." * i.level + i.module, i.names) for i in fx.imports),
        functions=() if fx.parse_error else _functions(text))


def _functions(text):
    """Top-level functions and the methods of top-level classes, in file order."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        tree = ast.parse(text)
    found = []
    for node in tree.body:
        for f in node.body if isinstance(node, ast.ClassDef) else [node]:
            if isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef)):
                found.append((f.name, f.end_lineno - f.lineno + 1,
                              1 + sum(pyscan._decisions(n) for n in ast.walk(f))))
    return tuple(found)


def requirement_names(configs):
    names = set()
    for text in configs.values():
        for line in (text or "").splitlines():
            match = REQUIREMENT.match(line)
            if match and not line.lstrip().startswith(("#", "-")):
                names.add(match.group(1).lower().replace("-", "_"))
    return names


class Resolver:
    def __init__(self, paths, known_external):
        self._resolver = resolve.Resolver(paths, known_external=known_external)

    def resolve(self, path, imp):
        level = len(imp.spec) - len(imp.spec.lstrip("."))
        targets, outside = self._resolver.resolve(
            path, pyscan.Import(imp.spec[level:], level, imp.names))
        return frozenset(targets), outside


def resolver(facts, configs, files):
    return Resolver([f for f in files if f.endswith(".py")], requirement_names(configs))


def _mention_texts(texts):
    return {path: text for path, text in texts.items()
            if os.path.splitext(path)[1] in MENTION_TEXT
            or os.path.basename(path) in MENTION_NAMES}


def mention_tokens(unit_id):
    """Strings that, found in another file, mean something refers to this module."""
    parts = unit_id[:-3].split("/")
    tokens = {unit_id, f'"{parts[-1]}.py"', f"'{parts[-1]}.py'"}
    for k in range(2, len(parts) + 1):
        tokens.add(".".join(parts[-k:]))
    return tokens


def mentioned(unit_ids, texts):
    """Python keeps its substring rule over docs, config and code text."""
    texts = _mention_texts(texts)
    found = set()
    for unit in unit_ids:
        tokens = mention_tokens(unit)
        if any(text and any(t in text for t in tokens)
               for path, text in texts.items() if path != unit):
            found.add(unit)
    return found


def named_tests(sources, tests, texts):
    """{source: [tests]}: a test that quotes a source's unique file name tests it."""
    by_name = {}
    for unit in sorted(sources):
        by_name.setdefault(os.path.basename(unit), []).append(unit)
    found = {}
    for base, units in by_name.items():
        if len(units) != 1:
            continue
        for test in sorted(tests):
            text = texts.get(test)
            if text and (f'"{base}"' in text or f"'{base}'" in text):
                found.setdefault(units[0], []).append(test)
    return found
