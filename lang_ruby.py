"""Ruby: require roads, Zeitwerk-style reference roads when Rails/Zeitwerk is present."""

import os
import re

import langkit

NAME = "ruby"
LABEL = "Ruby"
EXTENSIONS = (".rb", ".rake", ".ru")
SHEBANGS = ("ruby", "jruby")
GRAMMARS = {".rb": "ruby", ".rake": "ruby", ".ru": "ruby"}
CONFIG = ("Gemfile", "*.gemspec")
FIRE = True
SAMPLE = {
    "lib/widget.rb": "require_relative \"engine\"\n\nclass Widget; end\n",
    "lib/engine.rb": "require \"json\"\nrequire \"httparty\"\n\nclass Engine; end\n",
    "spec/widget_spec.rb": "require_relative \"../lib/widget\"\n",
    "Gemfile": "source \"https://rubygems.org\"\ngem \"httparty\"\n",
}

COMMENT = {"comment"}
COMPLEXITY = (
    "if", "unless", "while", "until", "for", "when", "rescue", "conditional",
    "if_modifier", "unless_modifier", "while_modifier", "until_modifier", "rescue_modifier",
    ("binary", ("&&", "||", "and", "or")),
)
FUNCTIONS = ("method", "singleton_method")
LOAD = ("require", "require_relative", "load", "autoload")
VISIBILITY = frozenset(("private", "protected"))
ATTR = frozenset(("attr_reader", "attr_writer", "attr_accessor"))
GEM = re.compile(r"^\s*gem\s+[\"']([^\"']+)[\"']", re.M)
DEP = re.compile(r"add_(?:runtime_|development_)?dependency\s+[\"']([^\"']+)[\"']", re.M)
SPEC_NAME = re.compile(r"^\s*(?:spec\.)?name\s*=\s*[\"']([^\"']+)[\"']", re.M)
STDLIB = frozenset((
    "json", "set", "time", "date", "fileutils", "optparse", "yaml", "psych", "erb",
    "net/http", "uri", "securerandom", "open3", "tempfile", "tmpdir", "pathname", "logger",
    "csv", "digest", "base64", "stringio", "shellwords", "socket", "timeout", "benchmark",
    "pp", "English", "forwardable", "singleton", "observer", "ostruct", "open-uri", "zlib",
    "openssl",
))
PUBLIC_DIRS = (
    "app/controllers/", "app/jobs/", "app/mailers/", "app/channels/", "app/helpers/",
    "db/migrate/", "config/initializers/", "config/environments/",
)


def unit_of(path, files):
    return path


def is_test(path, text=None):
    if path.startswith("spec/support/") or "/spec/support/" in path:
        return True
    if path.startswith("test/support/") or "/test/support/" in path:
        return True
    if path.endswith("_spec.rb") and (path.startswith("spec/") or "/spec/" in path):
        return True
    return path.endswith("_test.rb") and (path.startswith("test/") or "/test/" in path)


def is_excluded(path, text):
    return path == "db/schema.rb" or path.startswith("tmp/")


def _shebang(text):
    line = (text or "").split("\n", 1)[0]
    return line.startswith("#!") and any(f"/{n}" in line or f" {n}" in line for n in SHEBANGS)


def _string_literal(node):
    if node is None or node.type != "string":
        return None
    if any(c.type == "interpolation" for c in node.children):
        return None
    for c in node.children:
        if c.type == "string_content":
            return langkit.node_text(c)
    return None


def _declare_name(name_node, stack):
    if name_node is None:
        return None
    if name_node.type == "scope_resolution":
        return langkit.node_text(name_node)
    if name_node.type == "constant":
        part = langkit.node_text(name_node)
        return "::".join(stack + [part]) if stack else part
    return None


def _stack_after(name_node, stack):
    if name_node is None:
        return stack
    if name_node.type == "scope_resolution":
        return langkit.node_text(name_node).split("::")
    if name_node.type == "constant":
        return stack + [langkit.node_text(name_node)]
    return stack


def _underscore(part):
    s = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", part)
    s = re.sub(r"([a-z\d])([A-Z])", r"\1_\2", s)
    return s.replace("-", "_").lower()


def _zeitwerk_path(name):
    return "/".join(_underscore(p) for p in name.split("::")) + ".rb"


def _norm(name):
    return name.lower().replace("-", "").replace("_", "")


def _stdlib(spec):
    if spec in STDLIB:
        return True
    head = spec.split("/")[0]
    return head in STDLIB


def _config_gems(configs):
    names = set()
    for text in configs.values():
        for pat in (GEM, DEP):
            names.update(m.group(1) for m in pat.finditer(text or ""))
    return names


def _gem_names(configs):
    return {_norm(n): n for n in _config_gems(configs)}


def _load_roots(files):
    roots = set()
    for f in files:
        parts = f.split("/")
        for i, part in enumerate(parts):
            if part == "lib":
                roots.add("/".join(parts[: i + 1]))
    if not roots and any(f == "lib" or f.startswith("lib/") for f in files):
        roots.add("lib")
    return sorted(roots) + ["."]


def _autoload_roots(files):
    roots = set()
    for f in files:
        parts = f.split("/")
        if len(parts) >= 2 and parts[0] == "app":
            roots.add(f"{parts[0]}/{parts[1]}")
        if len(parts) >= 3 and parts[0] == "app" and parts[2] == "concerns":
            roots.add(f"{parts[0]}/{parts[1]}/concerns")
    if any(f == "lib" or f.startswith("lib/") for f in files):
        roots.add("lib")
    return sorted(roots)


def _resolve_path(root, spec):
    path = spec if spec.endswith(".rb") else f"{spec}.rb"
    if root == ".":
        return path
    return f"{root}/{path}"


def _method_name(node):
    if node.type == "singleton_method":
        name_node = node.child_by_field_name("name")
        if name_node and name_node.type == "identifier":
            return langkit.node_text(name_node)
        return None
    name_node = node.child_by_field_name("name")
    return langkit.node_text(name_node) if name_node else None


def _collect_exports(body):
    exports, hidden, visibility = [], set(), "public"
    if body is None:
        return exports
    for child in body.children:
        if child.type == "identifier" and langkit.node_text(child) in VISIBILITY:
            visibility = langkit.node_text(child)
            continue
        if child.type == "call":
            method = child.child_by_field_name("method")
            mname = langkit.node_text(method) if method else ""
            if mname in VISIBILITY:
                args = child.child_by_field_name("arguments")
                if args and any(c.type in ("method", "singleton_method") for c in args.children):
                    visibility = mname
                elif args:
                    for c in args.children:
                        if c.type == "simple_symbol":
                            hidden.add(langkit.node_text(c)[1:])
                continue
            if mname in ATTR:
                args = child.child_by_field_name("arguments")
                if args:
                    for c in args.children:
                        if c.type == "simple_symbol":
                            exports.append(langkit.node_text(c)[1:])
            continue
        if child.type in ("method", "singleton_method"):
            name = _method_name(child)
            if name and visibility == "public" and name not in hidden:
                exports.append(name)
        elif child.type == "singleton_class":
            exports.extend(_collect_exports(child.child_by_field_name("body")))
    return exports


AUTOLOAD_BLOCK = frozenset(("eager_autoload", "autoload_under", "autoload_at"))


def _symbol(node):
    if node is not None and node.type == "simple_symbol":
        text = langkit.node_text(node)
        return text[1:] if text.startswith(":") else text
    return None


def _rails_autoload_spec(name, stack, under=None, at=None):
    if at:
        return at
    parts = [_underscore(p) for p in stack]
    if under:
        parts.append(under)
    parts.append(_underscore(name))
    return "/".join(parts)


def _record_call(node, stack, imports, under=None, at=None):
    method = node.child_by_field_name("method")
    mname = langkit.node_text(method) if method else ""
    args = node.child_by_field_name("arguments")
    if mname == "autoload" and args:
        symbols = [c for c in args.children if c.type == "simple_symbol"]
        strings = [c for c in args.children if c.type == "string"]
        if strings:
            spec = _string_literal(strings[-1])
            if spec:
                imports.append(langkit.Import(spec))
            return
        if len(symbols) == 1:
            spec = _rails_autoload_spec(_symbol(symbols[0]), stack, under, at)
            if spec:
                imports.append(langkit.Import(spec, kind="import"))
        return
    if mname not in LOAD or not args:
        return
    strings = [c for c in args.children if c.type == "string"]
    if not strings:
        return
    spec = _string_literal(strings[0])
    if not spec:
        return
    kind = "relative" if mname == "require_relative" or (mname == "load" and spec.startswith(".")) else "import"
    imports.append(langkit.Import(spec, kind=kind))


def _is_declaration_name(node):
    parent = node.parent
    return bool(parent and parent.type in ("class", "module")
                and parent.child_by_field_name("name") == node)


def _visit(node, stack, declares, exports, imports, references, under=None, at=None):
    if node is None:
        return
    if node.type in ("class", "module"):
        name_node = node.child_by_field_name("name")
        qualified = _declare_name(name_node, stack)
        if qualified:
            declares.append(qualified)
        body = node.child_by_field_name("body")
        if node.type == "class":
            exports.extend(_collect_exports(body))
        next_stack = _stack_after(name_node, stack)
        for child in body.children if body else []:
            _visit(child, next_stack, declares, exports, imports, references, under, at)
        return
    if node.type == "call":
        method = node.child_by_field_name("method")
        mname = langkit.node_text(method) if method else ""
        if mname in AUTOLOAD_BLOCK:
            block = next((c for c in node.children if c.type == "do_block"), None)
            if block is not None:
                new_under, new_at = under, at
                args = node.child_by_field_name("arguments")
                strings = [c for c in args.children if c.type == "string"] if args else []
                if mname == "autoload_under" and strings:
                    new_under = _string_literal(strings[0])
                elif mname == "autoload_at" and strings:
                    new_at = _string_literal(strings[0])
                body = block.child_by_field_name("body")
                for child in body.children if body else []:
                    _visit(child, stack, declares, exports, imports, references, new_under, new_at)
                return
        _record_call(node, stack, imports, under, at)
    if node.type in ("constant", "scope_resolution") and not _is_declaration_name(node):
        references.add((langkit.node_text(node), tuple(stack)))
    for child in node.children:
        _visit(child, stack, declares, exports, imports, references, under, at)


_SKIP_PARENT = {
    "if": {"if", "if_modifier"},
    "unless": {"unless", "unless_modifier"},
    "while": {"while", "while_modifier"},
    "until": {"until", "until_modifier"},
    "rescue": {"rescue", "rescue_modifier"},
    "for": {"for"},
    "when": {"when"},
}


def _complexity(root):
    n = 0
    for node in langkit.walk(root):
        t = node.type
        parent = node.parent.type if node.parent else ""
        if t in _SKIP_PARENT and parent in _SKIP_PARENT[t]:
            continue
        if t in COMPLEXITY:
            n += 1
        elif t == "binary" and any(c.type in ("&&", "||", "and", "or") for c in node.children):
            n += 1
    return 1 + n


def _public(path, declares):
    if any(path.startswith(d) for d in PUBLIC_DIRS):
        return True
    if path.startswith("lib/") and path.endswith(".rb"):
        stem = os.path.basename(path)[:-3]
        for name in declares:
            if _underscore(name.split("::")[-1]) == stem:
                return True
    return False


def scan(path, text, tree):
    if tree is None:
        return langkit.Facts()
    declares, exports, imports, references = [], [], [], set()
    for child in tree.root_node.children:
        _visit(child, [], declares, exports, imports, references)
    ref_imports = [langkit.Import(name, names=nesting, kind="reference")
                   for name, nesting in sorted(references)]
    declares = tuple(sorted(set(declares)))
    return langkit.Facts(
        loc=langkit.loc(text, tree, COMMENT),
        complexity=_complexity(tree.root_node),
        exports=tuple(sorted(set(exports))),
        notes=langkit.notes(tree, COMMENT),
        is_entry=_shebang(text) or path.startswith(("bin/", "exe/")) or path.endswith(".rake")
        or os.path.basename(path) == "config.ru",
        public=_public(path, declares),
        parse_error=langkit.first_error(tree),
        imports=tuple(imports) + tuple(ref_imports),
        scope="",
        declares=declares,
        references=tuple(name for name, _ in sorted(references)),
        functions=langkit.functions(tree.root_node, FUNCTIONS, _complexity),
    )


def _autoload_mode(configs, facts):
    for name in _config_gems(configs):
        if _norm(name) in ("rails", "zeitwerk"):
            return True
    for fx in facts.values():
        if "Zeitwerk::Loader" in fx.references:
            return True
        for imp in fx.imports:
            if imp.kind == "reference" and imp.spec == "Zeitwerk::Loader":
                return True
    return False


def _candidate_names(nesting, name):
    if "::" in name:
        yield name
        return
    parts = list(nesting)
    for i in range(len(parts), -1, -1):
        yield "::".join(parts[:i] + [name]) if i else name


class Resolver:
    def __init__(self, facts, configs, files):
        self._files = frozenset(files)
        self._declares = {p: set(fx.declares) for p, fx in facts.items()}
        self._gems = _gem_names(configs)
        self._load_roots = _load_roots(files)
        self._autoload = _autoload_mode(configs, facts)
        self._autoload_roots = _autoload_roots(files) if self._autoload else []
        decls = [(fx.scope or "", name, p) for p, fx in facts.items() for name in fx.declares]
        self._index = langkit.SymbolIndex(decls)
        self._zeitwerk = {}
        for root in self._autoload_roots:
            for f in files:
                if f.startswith(root + "/") and f.endswith(".rb"):
                    rel = f[len(root) + 1:]
                    self._zeitwerk.setdefault(rel, set()).add(f)

    def resolve(self, path, imp):
        if imp.kind == "reference":
            return self._reference(path, imp) if self._autoload else (frozenset(), None)
        if imp.kind == "relative":
            return self._relative(path, imp.spec), None
        if _stdlib(imp.spec):
            return frozenset(), None
        hit = self._require(imp.spec)
        if hit:
            return frozenset([hit]), None
        return frozenset(), self._warehouse(imp.spec)

    def _self_declared(self, path, name):
        return name in self._declares.get(path, ())

    def _reference(self, path, imp):
        for candidate in _candidate_names(imp.names, imp.spec):
            if self._self_declared(path, candidate):
                continue
            hit = self._index.lookup("", candidate)
            if hit:
                return frozenset([hit]), None
        if self._self_declared(path, imp.spec):
            return frozenset(), None
        rel = _zeitwerk_path(imp.spec)
        matches = sorted(self._zeitwerk.get(rel, ()))
        if len(matches) == 1:
            return frozenset([matches[0]]), None
        return frozenset(), None

    def _relative(self, path, spec):
        base = os.path.dirname(path)
        target = os.path.normpath(os.path.join(base, spec))
        if target.startswith("../"):
            return frozenset()
        if not target.endswith(".rb"):
            target += ".rb"
        return frozenset([target]) if target in self._files else frozenset()

    def _require(self, spec):
        for root in self._load_roots:
            candidate = _resolve_path(root, spec)
            if candidate in self._files:
                return candidate
        return None

    def _warehouse(self, spec):
        head = spec.split("/")[0]
        key = _norm(head)
        if key in self._gems:
            return self._gems[key]
        return head


def resolver(facts, configs, files):
    return Resolver(facts, configs, files)
