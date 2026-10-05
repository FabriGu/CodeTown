"""Shared pieces for language adapters: facts, imports, tree helpers and a symbol index.

Nothing here reads a repository. Grammars load only if `towncode setup` already put
them on disk: the language pack downloads any other grammar it is asked for, so
`language()` refuses those instead of asking.
"""

import re
from dataclasses import dataclass

try:
    import tree_sitter
    import tree_sitter_language_pack as pack
except ImportError:
    tree_sitter = pack = None

NOTE = re.compile(r"\b(?:TODO|FIXME)\b")


@dataclass(frozen=True)
class Import:
    spec: str
    names: tuple = ()
    kind: str = "import"


@dataclass
class Facts:
    loc: int = 0
    complexity: int = 0
    exports: tuple = ()
    notes: int = 0
    is_entry: bool = False
    is_package: bool = False
    public: bool = False
    inline_tests: bool = False
    parse_error: str | None = None
    imports: tuple = ()
    scope: str | None = None
    declares: tuple = ()
    references: tuple = ()
    functions: tuple = ()


_ready = None
_languages = {}
_parsers = {}
_queries = {}


def available():
    return pack is not None


def ready_grammars():
    """Grammars already downloaded, read once per process."""
    global _ready
    if _ready is None:
        _ready = frozenset(pack.downloaded_languages()) if pack else frozenset()
    return _ready


def grammar_ready(name):
    return bool(name) and name in ready_grammars()


def language(name):
    if not grammar_ready(name):
        raise LookupError(f"grammar {name!r} is not installed: run towncode setup")
    if name not in _languages:
        _languages[name] = pack.get_language(name)
    return _languages[name]


def parse(grammar, text):
    """A tree for `text`, or None when the grammar isn't installed."""
    if not grammar_ready(grammar):
        return None
    parser = _parsers.get(grammar)
    if parser is None:
        parser = _parsers[grammar] = tree_sitter.Parser(language(grammar))
    return parser.parse(text.encode("utf-8"))


def query(grammar, pattern):
    key = (grammar, pattern)
    if key not in _queries:
        _queries[key] = tree_sitter.Query(language(grammar), pattern)
    return _queries[key]


def captures(grammar, pattern, node):
    """{capture name: [nodes]} for a query run over `node`."""
    return tree_sitter.QueryCursor(query(grammar, pattern)).captures(node)


def matches(grammar, pattern, node):
    """[(pattern index, {capture name: [nodes]})] for a query run over `node`."""
    return tree_sitter.QueryCursor(query(grammar, pattern)).matches(node)


def walk(node):
    """Every node under `node`, itself first, in source order."""
    cursor = node.walk()
    while True:
        yield cursor.node
        if cursor.goto_first_child():
            continue
        while not cursor.goto_next_sibling():
            if not cursor.goto_parent():
                return


def node_text(node):
    return node.text.decode("utf-8", errors="replace") if node is not None and node.text else ""


def count_types(node, types):
    """Nodes of the given types. An entry ("binary_expression", ("&&", "||")) counts
    that type only when one of its direct children is one of those operators."""
    plain = {t for t in types if isinstance(t, str)}
    ops = {t[0]: set(t[1]) for t in types if not isinstance(t, str)}
    n = 0
    for x in walk(node):
        if x.type in plain:
            n += 1
        elif x.type in ops and any(c.type in ops[x.type] for c in x.children):
            n += 1
    return n


def functions(root, types, complexity, name=None, skip=None):
    """(name, lines, complexity) for each function not inside another, in source order.

    Methods count, closures and nested functions belong to the function around them.
    `complexity(node)` scores one function the way the language scores a file; `name(node)`
    names those the grammar doesn't; nothing under a node `skip(node)` accepts is counted.
    """
    found, stack = [], list(reversed(root.children))
    while stack:
        node = stack.pop()
        if skip is not None and skip(node):
            continue
        if node.type in types:
            found.append(((name and name(node)) or function_name(node),
                          node.end_point[0] - node.start_point[0] + 1, complexity(node)))
        else:
            stack.extend(reversed(node.children))
    return tuple(found)


def function_name(node):
    """The grammar's name for a function, its declarator's (C, C++), or what it's assigned to."""
    named = node.child_by_field_name("name")
    if named is not None:
        return node_text(named)
    declarator = node.child_by_field_name("declarator")
    while declarator is not None:
        inner = declarator.child_by_field_name("declarator")
        if inner is None:
            return node_text(declarator)
        declarator = inner
    for i, child in enumerate(node.children):
        if child.type.endswith("identifier") and node.field_name_for_child(i) is None:
            return node_text(child)
    parent = node.parent
    for field in ("name", "key", "left"):
        owner = parent.child_by_field_name(field) if parent is not None else None
        if owner is not None and owner != node:
            return node_text(owner)
    return ""


def _comments(tree, comment_types):
    return [n for n in walk(tree.root_node) if n.type in comment_types]


def loc(text, tree, comment_types):
    """Non-blank lines holding something other than comments."""
    lines = text.splitlines()
    rows = set()
    stack = [tree.root_node]
    while stack:
        n = stack.pop()
        if n.type in comment_types:
            continue
        if n.child_count == 0:
            if n.end_byte > n.start_byte:
                rows.update(range(n.start_point[0], n.end_point[0] + 1))
        else:
            stack.extend(n.children)
    return sum(1 for r in rows if r < len(lines) and lines[r].strip())


def notes(tree, comment_types):
    """Comment lines containing TODO or FIXME."""
    return sum(1 for c in _comments(tree, comment_types)
               for line in node_text(c).splitlines() if NOTE.search(line))


def first_error(tree):
    """'line N: unexpected X' for the first ERROR or MISSING node, or None."""
    if tree is None or not tree.root_node.has_error:
        return None
    for n in walk(tree.root_node):
        if n.is_missing:
            return f"line {n.start_point[0] + 1}: missing {n.type}"
        if n.is_error:
            snippet = " ".join(node_text(n).split())[:24]
            return f"line {n.start_point[0] + 1}: unexpected {snippet or 'input'}"
    return None


class SymbolIndex:
    """Which file declares a name within a scope (a package, namespace or module)."""

    def __init__(self, declarations):
        self._by = {}
        self._scopes = {}
        for scope, name, path in declarations:
            self._by.setdefault((scope, name), set()).add(path)
            self._scopes.setdefault(scope, set()).add(path)

    def lookup(self, scope, name):
        found = self._by.get((scope, name))
        return next(iter(found)) if found and len(found) == 1 else None

    def lookup_all(self, scope, name):
        return tuple(sorted(self._by.get((scope, name), ())))

    def in_scope(self, scope):
        return tuple(sorted(self._scopes.get(scope, ())))
