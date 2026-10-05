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
    facts.is_entry = any(_is_main_guard(node) or _is_top_level_call(node) for node in tree.body)
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


def _is_top_level_call(node):
    return isinstance(node, ast.Expr) and isinstance(node.value, ast.Call)
