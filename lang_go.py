"""Go: one building per package folder, imports resolved from go.mod and go.work."""

import re

import langkit

NAME = "go"
LABEL = "Go"
EXTENSIONS = (".go",)
SHEBANGS = ()
GRAMMARS = {".go": "go"}
CONFIG = ("go.mod", "go.work")
FIRE = True
SAMPLE = {
    "go.mod": "module example.com/sample\n\nrequire github.com/lib/p v1.0.0\n",
    "cmd/main.go": 'package main\n\nimport "example.com/sample/pkg/a"\n\nfunc main() {}\n',
    "pkg/a/a.go": 'package a\n\nimport "fmt"\n\nfunc F() { fmt.Println() }\n',
    "pkg/a/a_test.go": 'package a\n\nfunc TestA(t *testing.T) {}\n',
}

COMMENT = {"comment"}
COMPLEXITY = (
    "if_statement", "for_statement", "expression_case", "type_case", "communication_case",
    ("binary_expression", ("&&", "||")),
)
FUNCTIONS = ("function_declaration", "method_declaration", "func_literal")
IMPORT_PATH = '(import_spec path: (interpreted_string_literal) @p)'
EXPORT_FUN = '(function_declaration name: (identifier) @n)'
EXPORT_TYPE = '(type_spec name: (type_identifier) @n)'
EXPORT_VAR = '(var_spec name: (identifier) @n)'
EXPORT_CONST = '(const_spec name: (identifier) @n)'
PACKAGE = '(package_clause (package_identifier) @p)'
MAIN = '(function_declaration name: (identifier) @n (#eq? @n "main"))'
GENERATED = re.compile(r"^// Code generated .* DO NOT EDIT\.$", re.MULTILINE)
MODULE = re.compile(r"^\s*module\s+(\S+)")
REQUIRE = re.compile(r"^\s*require\s+(?:\(\s*)?(\S+)")
REPLACE = re.compile(r"^\s*replace\s+(?:\(\s*)?(\S+)\s+=>\s+(\S+)")
USE = re.compile(r"^\s*use\s+(?:\(\s*)?(\S+)")


def _folder(path):
    if "/" not in path:
        return "./"
    return path.rsplit("/", 1)[0] + "/"


def _mod_folder(path):
    if path == "go.mod":
        return "./"
    return path.rsplit("/", 1)[0] + "/"


def _join(base, rel):
    if not rel or rel in (".", "./"):
        if base in ("", "./"):
            return "./"
        return base if base.endswith("/") else base + "/"
    if rel.startswith("./"):
        rel = rel[2:]
    if base in ("", "./"):
        return rel + ("/" if not rel.endswith("/") else "")
    return base.rstrip("/") + "/" + rel.lstrip("/")


def _leading_before_package(text):
    lines = text.splitlines()
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("package ") or stripped == "package":
            return [l.strip() for l in lines[:i]]
    return [line.strip() for line in lines]


def unit_of(path, files):
    return _folder(path)


def is_test(path, text=None):
    return path.endswith("_test.go")


def is_excluded(path, text):
    if "testdata" in path.split("/"):
        return True
    before = _leading_before_package(text)
    if any(line == "//go:build ignore" or line.startswith("//go:build ignore ") for line in before):
        return True
    return any(GENERATED.match(line) for line in before)


def _import_path(node):
    raw = langkit.node_text(node)
    return raw[1:-1] if len(raw) >= 2 and raw[0] == raw[-1] == '"' else raw


def _exports(root):
    names = []
    for pattern in (EXPORT_FUN, EXPORT_TYPE, EXPORT_VAR, EXPORT_CONST):
        for node in langkit.captures("go", pattern, root).get("n", []):
            name = langkit.node_text(node)
            if name[:1].isupper():
                names.append(name)
    return tuple(sorted(set(names)))


def scan(path, text, tree):
    if tree is None:
        return langkit.Facts()
    root = tree.root_node
    scope_nodes = langkit.captures("go", PACKAGE, root).get("p", [])
    scope = langkit.node_text(scope_nodes[0]) if scope_nodes else None
    mains = langkit.captures("go", MAIN, root).get("n", [])
    imports = []
    for node in langkit.captures("go", IMPORT_PATH, root).get("p", []):
        spec = _import_path(node)
        if spec != "C":
            imports.append(langkit.Import(spec))
    return langkit.Facts(
        loc=langkit.loc(text, tree, COMMENT),
        complexity=1 + langkit.count_types(root, COMPLEXITY),
        exports=_exports(root),
        notes=langkit.notes(tree, COMMENT),
        is_entry=scope == "main" and bool(mains),
        public=_is_public(path, scope),
        parse_error=langkit.first_error(tree),
        imports=tuple(imports),
        scope=scope,
        functions=langkit.functions(root, FUNCTIONS,
                                    lambda n: 1 + langkit.count_types(n, COMPLEXITY)),
    )


def _is_public(path, scope):
    return scope not in (None, "main") and "internal" not in path.split("/")


def tests_for(path, facts, files):
    folder = _folder(path)
    return {f for f in files if f.endswith(".go") and not f.endswith("_test.go")
            and _folder(f) == folder and f in facts}


def _parse_go_mod(text):
    module = None
    requires = []
    replaces = []
    block = None
    for line in (text or "").splitlines():
        stripped = line.split("//", 1)[0].strip()
        if not stripped:
            continue
        if stripped == "require (":
            block = "require"
            continue
        if stripped == "replace (":
            block = "replace"
            continue
        if stripped == ")":
            block = None
            continue
        if block == "require":
            parts = stripped.split()
            if parts:
                requires.append(parts[0])
            continue
        if block == "replace":
            match = re.match(r"(\S+)\s+=>\s+(\S+)", stripped)
            if match:
                replaces.append((match.group(1), match.group(2)))
            continue
        match = MODULE.match(stripped)
        if match:
            module = match.group(1)
            continue
        match = REQUIRE.match(stripped)
        if match:
            requires.append(match.group(1))
            continue
        match = REPLACE.match(stripped)
        if match:
            replaces.append((match.group(1), match.group(2)))
    return module, requires, replaces


def _parse_go_work(text):
    uses = []
    block = False
    for line in (text or "").splitlines():
        stripped = line.split("//", 1)[0].strip()
        if not stripped:
            continue
        if stripped == "use (":
            block = True
            continue
        if stripped == ")":
            block = False
            continue
        if block:
            uses.append(stripped)
            continue
        match = USE.match(stripped)
        if match:
            uses.append(match.group(1))
    return uses


def _norm_use(path):
    path = path.rstrip("/")
    if path.startswith("./"):
        path = path[2:]
    return "./" if not path else path + "/"


def _first_segment(path):
    return path.split("/")[0]


def _is_stdlib(path):
    return "." not in _first_segment(path)


def _external(path, requires):
    best = None
    for req in requires:
        if path == req or path.startswith(req + "/"):
            if best is None or len(req) > len(best):
                best = req
    if best:
        return best
    parts = path.split("/")
    if len(parts) >= 3 and parts[0] in ("github.com", "gitlab.com", "bitbucket.org"):
        return "/".join(parts[:3])
    if len(parts) >= 2 and parts[0] == "golang.org" and parts[1] == "x":
        return "golang.org/x"
    if len(parts) >= 2 and parts[0] == "gopkg.in":
        return "/".join(parts[:2])
    return parts[0]


def _module_for(path, modules):
    best = None
    best_len = -1
    for folder, mod_path in modules:
        prefix = "" if folder == "./" else folder
        if prefix and not path.startswith(prefix):
            continue
        if len(prefix) > best_len:
            best_len = len(prefix)
            best = (folder, mod_path)
    return best


class Resolver:
    def __init__(self, modules, requires, replaces, files, facts):
        self._modules = modules
        self._requires = requires
        self._replaces = replaces
        self._files = files
        self._facts = facts

    def resolve(self, path, imp):
        spec = imp.spec
        if spec == "C":
            return frozenset(), None
        mod_ctx = _module_for(path, self._modules)
        mod_folder = mod_ctx[0] if mod_ctx else "./"
        target = self._apply_replace(spec, mod_folder)
        local = self._local(target)
        if local:
            return local, None
        if _is_stdlib(target):
            return frozenset(), None
        return frozenset(), _external(target, self._requires)

    def _apply_replace(self, spec, mod_folder):
        for src, dst, base in self._replaces:
            if spec == src or spec.startswith(src + "/"):
                suffix = spec[len(src):].lstrip("/")
                local = dst if dst.startswith("./") else dst
                if local.startswith("./"):
                    local = _join(base, local[2:])
                else:
                    local = local + "/"
                return _join(local.rstrip("/"), suffix) if suffix else local
        return spec

    def _local(self, spec):
        best = None
        for folder, mod_path in self._modules:
            if spec == mod_path or spec.startswith(mod_path + "/"):
                rel = spec[len(mod_path):].lstrip("/")
                pkg = _join(folder, rel)
                if not pkg.endswith("/"):
                    pkg += "/"
                if best is None or len(mod_path) > len(best[0]):
                    best = (mod_path, pkg)
        if best is not None:
            return self._pkg_files(best[1])
        folder = spec if spec.endswith("/") else spec + "/"
        found = self._pkg_files(folder)
        return found if found else None

    def _pkg_files(self, folder):
        if folder == "./":
            folder = "./"
        return frozenset(
            f for f in self._files
            if f.endswith(".go") and not f.endswith("_test.go") and _folder(f) == folder
            and "testdata" not in f.split("/") and f in self._facts
        )


def resolver(facts, configs, files):
    workspace = None
    modules = []
    requires = []
    replaces = []
    for cfg_path, text in sorted(configs.items()):
        if cfg_path.endswith("go.work"):
            workspace = _parse_go_work(text)
            continue
        mod_path, reqs, reps = _parse_go_mod(text)
        if not mod_path:
            continue
        folder = _mod_folder(cfg_path)
        modules.append((folder, mod_path))
        requires.extend(reqs)
        for src, dst in reps:
            if dst.startswith("./") or dst.startswith("../"):
                replaces.append((src, dst, folder))
    if workspace is not None:
        allowed = {_norm_use(u) for u in workspace}
        modules = [(f, m) for f, m in modules if f in allowed]
    modules.sort(key=lambda x: (-len(x[0]), x[1]))
    return Resolver(modules, requires, replaces, files, facts)
