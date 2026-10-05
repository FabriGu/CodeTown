"""Rust: one building per file, imports resolved from Cargo.toml and the module tree."""

import fnmatch
import os
import re
import tomllib

import langkit

NAME = "rust"
LABEL = "Rust"
EXTENSIONS = (".rs",)
SHEBANGS = ()
GRAMMARS = {".rs": "rust"}
CONFIG = ("Cargo.toml",)
FIRE = True
SAMPLE = {
    "Cargo.toml": ('[package]\nname = "sample"\nversion = "0.1.0"\n\n'
                   '[dependencies]\nserde = "1"\n'),
    "src/main.rs": "mod util;\nuse util::helper;\n\nfn main() { helper(); }\n",
    "src/util.rs": "pub fn helper() {}\n",
}

COMMENT = {"line_comment", "block_comment"}
COMPLEXITY = (
    "if_expression", "match_arm", "for_expression", "while_expression", "loop_expression",
    ("binary_expression", ("&&", "||")),
)
FUNCTIONS = ("function_item",)
EXPORT_ITEMS = (
    "function_item", "struct_item", "enum_item", "trait_item", "type_item",
    "const_item", "static_item", "mod_item",
)
STDLIB = frozenset({"std", "core", "alloc", "proc_macro", "test"})
GENERATED = re.compile(r"@generated|automatically generated", re.I)
PATH_ATTR = re.compile(r'\bpath\s*=\s*"([^"]+)"')


def unit_of(path, files):
    return path


def is_test(path, text=None):
    parts = path.split("/")
    if "tests" not in parts:
        return False
    idx = parts.index("tests")
    return idx + 1 < len(parts) and path.endswith(".rs")


def is_excluded(path, text):
    if "/target/" in f"/{path}/":
        return True
    for line in (text or "").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("//"):
            if GENERATED.search(line):
                return True
            continue
        break
    return False


def _dir(path):
    folder = os.path.dirname(path)
    return "./" if not folder else folder + "/"


def _join(base, rel):
    if rel.startswith("./"):
        rel = rel[2:]
    base = base.rstrip("/")
    if not base or base == ".":
        out = rel
    else:
        out = f"{base}/{rel}"
    return os.path.normpath(out).replace("\\", "/")


def _stem(path):
    return os.path.splitext(os.path.basename(path))[0]


def _plain_pub(node):
    for child in node.children:
        if child.type == "visibility_modifier":
            return langkit.node_text(child) == "pub"
    return False


def _item_name(node):
    for child in node.children:
        if child.type in ("identifier", "type_identifier"):
            return langkit.node_text(child)
    return None


def _path_from_segments(node):
    parts = []
    for child in node.children:
        if child.type in ("identifier", "type_identifier"):
            parts.append(langkit.node_text(child))
        elif child.type in ("self", "super", "crate"):
            parts.append(child.type)
    return "::".join(parts)


def _use_leaves(node, prefix=""):
    kind = node.type
    if kind in ("identifier", "scoped_identifier", "scoped_type_identifier"):
        path = _path_from_segments(node) if kind != "identifier" else langkit.node_text(node)
        return [f"{prefix}::{path}".lstrip(":")] if prefix else [path]
    if kind == "use_wildcard":
        base = _path_from_segments(node)
        return [f"{base}::*"]
    if kind == "use_as_clause":
        scoped = next(c for c in node.children if c.type in ("scoped_identifier", "identifier"))
        path = (_path_from_segments(scoped) if scoped.type != "identifier"
                else langkit.node_text(scoped))
        return [f"{prefix}::{path}".lstrip(":")] if prefix else [path]
    if kind == "scoped_use_list":
        base = langkit.node_text(node.children[0])
        rest = node.children[-1]
        return _use_list_leaves(rest, base)
    if kind == "use_list":
        return _use_list_leaves(node, prefix)
    return []


def _use_list_leaves(node, prefix):
    out = []
    for child in node.children:
        if child.type in ("identifier", "scoped_identifier", "scoped_type_identifier"):
            leaf = (_path_from_segments(child) if child.type != "identifier"
                    else langkit.node_text(child))
            out.append(f"{prefix}::{leaf}" if prefix else leaf)
    return out


def _use_imports(root):
    imports = []
    for node in langkit.walk(root):
        if node.type != "use_declaration":
            continue
        for child in node.children:
            if child.type in ("scoped_identifier", "identifier", "use_as_clause", "use_wildcard",
                              "scoped_use_list", "use_list"):
                for spec in _use_leaves(child):
                    imports.append(langkit.Import(spec))
                break
    return imports


def _reference_imports(root):
    seen = set()
    imports = []
    for node in langkit.walk(root):
        if node.type not in ("scoped_identifier", "scoped_type_identifier"):
            continue
        segs = [c for c in node.children
                if c.type in ("identifier", "type_identifier", "self", "super", "crate")]
        if not segs:
            continue
        first = segs[0].type if segs[0].type in ("self", "super", "crate") else langkit.node_text(segs[0])
        if first not in ("crate", "self", "super") and not first.islower():
            continue
        spec = _path_from_segments(node)
        if spec not in seen:
            seen.add(spec)
            imports.append(langkit.Import(spec, kind="reference"))
    return imports


def _mod_imports(root):
    imports = []
    pending = []
    for child in root.children:
        if child.type == "attribute_item":
            pending.append(child)
            continue
        if child.type != "mod_item":
            pending = []
            continue
        if any(c.type == "declaration_list" for c in child.children):
            pending = []
            continue
        name = _item_name(child)
        if not name:
            pending = []
            continue
        path = None
        for attr in pending:
            match = PATH_ATTR.search(langkit.node_text(attr))
            if match:
                path = match.group(1)
                break
        imports.append(langkit.Import(name, names=((path,) if path else ()), kind="module"))
        pending = []
    return imports


def _exports(root):
    names = []
    pending = []
    for child in root.children:
        if child.type == "attribute_item":
            pending.append(child)
            continue
        if child.type not in EXPORT_ITEMS and child.type != "use_declaration":
            pending = []
            continue
        if child.type == "macro_definition":
            if any("macro_export" in langkit.node_text(a) for a in pending):
                name = _item_name(child)
                if name:
                    names.append(name)
            pending = []
            continue
        if child.type == "use_declaration":
            if not _plain_pub(child):
                pending = []
                continue
            for sub in child.children:
                if sub.type == "use_wildcard":
                    names.append("*")
                elif sub.type in ("scoped_identifier", "identifier"):
                    parts = [c for c in sub.children if c.type == "identifier"]
                    if parts:
                        names.append(langkit.node_text(parts[-1]))
                elif sub.type == "scoped_use_list":
                    base = langkit.node_text(sub.children[0])
                    for leaf in _use_list_leaves(sub.children[-1], base):
                        names.append(leaf.split("::")[-1])
            pending = []
            continue
        if _plain_pub(child):
            name = _item_name(child)
            if name:
                names.append(name)
        pending = []
    return tuple(sorted(set(names)))


def _is_package(root, path):
    base = os.path.basename(path)
    if base not in ("mod.rs", "lib.rs"):
        return False
    for child in root.children:
        if child.type in ("line_comment", "block_comment", "attribute_item"):
            continue
        if child.type == "mod_item":
            continue
        if child.type == "use_declaration":
            continue
        return False
    return True


def _is_entry(path):
    if path.endswith("/build.rs") or path == "build.rs":
        return True
    if path.endswith("src/main.rs"):
        return True
    if "src/bin/" in path and path.endswith(".rs"):
        return True
    if "examples/" in path and path.endswith(".rs"):
        return True
    return False


def _is_public(path):
    return path.endswith("/src/lib.rs") or path == "src/lib.rs"


def _is_test_mod(node):
    """A `mod` under `#[cfg(test)]`: its functions are tests, not the module's own."""
    if node.type != "mod_item":
        return False
    prev = node.prev_named_sibling
    while prev is not None and prev.type == "attribute_item":
        if "cfg(test)" in langkit.node_text(prev):
            return True
        prev = prev.prev_named_sibling
    return False


def _inline_tests(root):
    pending = []
    for child in root.children:
        if child.type == "attribute_item":
            pending.append(langkit.node_text(child))
            continue
        if child.type == "mod_item":
            if any("cfg(test)" in a for a in pending):
                return True
            if any(c.type == "declaration_list" for c in child.children):
                pending = []
                continue
        elif child.type == "function_item":
            if any("test" in a and "cfg" not in a for a in pending):
                return True
        pending = []
    return False


def scan(path, text, tree):
    if tree is None:
        return langkit.Facts()
    root = tree.root_node
    imports = _mod_imports(root) + _use_imports(root) + _reference_imports(root)
    return langkit.Facts(
        loc=langkit.loc(text, tree, COMMENT),
        complexity=1 + langkit.count_types(root, COMPLEXITY),
        exports=_exports(root),
        notes=langkit.notes(tree, COMMENT),
        is_entry=_is_entry(path),
        is_package=_is_package(root, path),
        public=_is_public(path),
        inline_tests=_inline_tests(root),
        parse_error=langkit.first_error(tree),
        imports=tuple(imports),
        functions=langkit.functions(root, FUNCTIONS,
                                    lambda n: 1 + langkit.count_types(n, COMPLEXITY),
                                    skip=_is_test_mod),
    )


def _norm_name(name):
    return name.replace("-", "_")


def _crate_folder(cargo_path):
    folder = os.path.dirname(cargo_path)
    return "./" if not folder else folder + "/"


def _glob_members(pattern, files):
    pat = pattern.rstrip("/")
    if pat.endswith("/*"):
        prefix = pat[:-1]
        return {f for f in files if f.startswith(prefix) and f.endswith("/Cargo.toml")}
    if any(c in pat for c in "*?[]"):
        return {f for f in files if fnmatch.fnmatchcase(f, pat + "/Cargo.toml")}
    target = pat + "/Cargo.toml" if pat else "Cargo.toml"
    return {target} if target in files else set()


def _dep_path(entry):
    if isinstance(entry, dict):
        return entry.get("path")
    return None


def _parse_cargo(text):
    try:
        data = tomllib.loads(text or "")
    except tomllib.TOMLDecodeError:
        return None
    package = data.get("package") or {}
    name = package.get("name")
    lib = data.get("lib") or {}
    lib_path = lib.get("path", "src/lib.rs")
    raw_bins = data.get("bin")
    if raw_bins is None:
        raw_bins = []
    elif not isinstance(raw_bins, list):
        raw_bins = [raw_bins]
    bins = []
    for entry in raw_bins:
        if isinstance(entry, dict):
            path = entry.get("path")
            if not path:
                bname = entry.get("name", "main")
                path = f"src/bin/{bname}.rs" if bname != "main" else "src/main.rs"
            bins.append(path)
    workspace = data.get("workspace") or {}
    members = workspace.get("members") or []
    deps = {}
    for section in ("dependencies", "dev-dependencies", "build-dependencies"):
        for key, val in (data.get(section) or {}).items():
            deps[key] = val
    for key, val in (workspace.get("dependencies") or {}).items():
        deps.setdefault(key, val)
    build = package.get("build")
    if build is True:
        build = "build.rs"
    return {
        "name": name,
        "lib_path": lib_path,
        "bins": bins,
        "build": build,
        "members": members,
        "deps": deps,
    }


def _crate_prefix(folder):
    return "" if folder == "./" else folder


def _roots_for_crate(folder, meta, files):
    """Root files and the folder each one anchors for submodule paths."""
    roots = []
    lib = _join(folder, meta["lib_path"])
    if lib in files:
        roots.append((lib, os.path.dirname(lib)))
    main = _join(folder, "src/main.rs")
    if main in files:
        roots.append((main, os.path.dirname(main)))
    for bp in meta["bins"]:
        candidate = _join(folder, bp)
        if candidate in files:
            roots.append((candidate, os.path.dirname(candidate)))
    if meta.get("build"):
        build = _join(folder, meta["build"])
        if build in files:
            roots.append((build, os.path.dirname(build)))
    prefix = _crate_prefix(folder)
    for path in sorted(files):
        if not path.endswith(".rs") or not path.startswith(prefix):
            continue
        rel = path[len(prefix):] if prefix else path
        if rel.startswith("src/bin/") and rel.endswith(".rs"):
            roots.append((path, os.path.dirname(path)))
        elif rel.startswith("examples/") and rel.endswith(".rs"):
            roots.append((path, os.path.dirname(path)))
        elif rel.startswith("benches/") and rel.endswith(".rs"):
            roots.append((path, os.path.dirname(path)))
        elif rel.startswith("tests/") and rel.endswith(".rs"):
            roots.append((path, os.path.dirname(path)))
    seen = set()
    out = []
    for root, base in roots:
        if root not in seen:
            seen.add(root)
            out.append((root, base))
    return out


def _mod_path_from_root(cname, root, base_dir, path):
    if path == root:
        return cname
    rel = os.path.relpath(path, base_dir).replace("\\", "/")
    if rel.endswith(".rs"):
        parts = rel[:-3].split("/")
        if parts and parts[-1] == "mod":
            parts = parts[:-1]
        return f"{cname}::{'::'.join(parts)}" if parts else cname
    return None


def _module_path_src_layout(folder, cname, path):
    """Fallback mapping for the usual src/ tree when no root claimed a file."""
    if folder != "./" and not path.startswith(folder):
        return None
    rel = path[len(folder):] if folder != "./" else path
    if rel == "build.rs":
        return cname
    for prefix in ("src/", "examples/", "benches/", "tests/"):
        if rel.startswith(prefix):
            rel = rel[len(prefix):]
            break
    else:
        return None
    if rel in ("lib.rs", "main.rs"):
        return cname
    if not rel.endswith(".rs"):
        return None
    parts = rel[:-3].split("/")
    if parts and parts[-1] == "mod":
        parts = parts[:-1]
    return f"{cname}::{'::'.join(parts)}" if parts else cname


def _child_candidates(parent, name):
    folder = os.path.dirname(parent)
    base = os.path.basename(parent)
    stem = _stem(parent)
    if base in ("lib.rs", "main.rs") or base == "mod.rs" or any(
            x in parent for x in ("/src/bin/", "/examples/", "/benches/", "/tests/")):
        return [_join(folder, f"{name}.rs"), _join(folder, f"{name}/mod.rs")]
    if stem != "mod":
        return [_join(folder, f"{stem}/{name}.rs"), _join(folder, f"{stem}/{name}/mod.rs")]
    return [_join(folder, f"{name}.rs"), _join(folder, f"{name}/mod.rs")]


def _resolve_child(parent, name, path_override, files):
    folder = _dir(parent)
    if path_override:
        candidate = _join(folder, path_override)
        return candidate if candidate in files else None
    for candidate in _child_candidates(parent, name):
        if candidate in files:
            return candidate
    return None


class _ModuleTree:
    def __init__(self, crates, facts, files):
        self.crates = crates
        self.facts = facts
        self.files = files
        self.file_module = {}
        self.file_crate = {}
        self.root_modules = {}
        self.children = {}
        self._build()

    def _build(self):
        for folder, meta in self.crates.items():
            cname = _norm_name(meta["name"])
            prefix = _crate_prefix(folder)
            roots = _roots_for_crate(folder, meta, self.files)
            claimed = {}
            for path in sorted(self.files):
                if not path.endswith(".rs") or not path.startswith(prefix):
                    continue
                best = None
                for root, base in roots:
                    if path != root and not path.startswith(f"{base}/"):
                        continue
                    mod_path = _mod_path_from_root(cname, root, base, path)
                    if mod_path is None:
                        continue
                    if best is None or len(base) > best[0]:
                        best = (len(base), mod_path)
                if best:
                    claimed[path] = best[1]
                else:
                    fallback = _module_path_src_layout(folder, cname, path)
                    if fallback:
                        claimed[path] = fallback
            for path, mod_path in claimed.items():
                self.file_module[path] = mod_path
                self.file_crate[path] = folder
            self.root_modules[folder] = {cname}
            for path, fx in self.facts.items():
                if self.file_crate.get(path) != folder:
                    continue
                mod_path = self.file_module.get(path)
                if not mod_path:
                    continue
                for imp in fx.imports:
                    if imp.kind != "module":
                        continue
                    override = imp.names[0] if imp.names else None
                    child = _resolve_child(path, imp.spec, override, self.files)
                    if not child:
                        continue
                    child_mod = f"{mod_path}::{imp.spec}"
                    if child not in self.file_module:
                        self.file_module[child] = child_mod
                        self.file_crate[child] = folder
                    self.children.setdefault(path, {})[imp.spec] = child

    def crate_for(self, path):
        return self.file_crate.get(path)

    def module_of(self, path):
        return self.file_module.get(path)

    def parent_module(self, mod_path):
        if "::" not in mod_path:
            return None
        return mod_path.rsplit("::", 1)[0]

    def file_for_module(self, mod_path, crate_folder):
        matches = [p for p, m in self.file_module.items()
                   if m == mod_path and self.file_crate.get(p) == crate_folder]
        if len(matches) == 1:
            return matches[0]
        if len(matches) <= 1:
            return None
        for suffix in ("lib.rs", "main.rs", "mod.rs"):
            for path in matches:
                if path.endswith(suffix):
                    return path
        primary = [p for p in matches
                   if not any(x in p for x in ("/benches/", "/tests/", "/examples/", "/src/bin/"))]
        return primary[0] if len(primary) == 1 else None

    def root_module_names(self, crate_folder):
        return self.root_modules.get(crate_folder, set())

    def inline_mods(self, path):
        fx = self.facts.get(path)
        if not fx:
            return set()
        return {imp.spec for imp in fx.imports
                if imp.kind == "module" and not self.children.get(path, {}).get(imp.spec)}

    def ancestors(self, path):
        """Files that declare this one via `mod`, up to the crate root."""
        parents = {}
        for parent, kids in self.children.items():
            for child in kids.values():
                parents[child] = parent
        found = []
        current = path
        while current in parents:
            current = parents[current]
            found.append(current)
        return frozenset(found)


class Resolver:
    def __init__(self, tree, crates, externals, path_crates, files):
        self._tree = tree
        self._crates = crates
        self._externals = externals
        self._path_crates = path_crates
        self._files = files

    def resolve(self, path, imp):
        if imp.kind == "module":
            child = self._tree.children.get(path, {}).get(imp.spec)
            if child and child != path:
                return frozenset([child]), None
            return frozenset(), None
        spec = imp.spec
        module = self._tree.module_of(path)
        if not module:
            return frozenset(), None
        crate_folder = self._tree.crate_for(path)
        abs_path = self._absolute(spec, module, path, crate_folder)
        if not abs_path:
            return frozenset(), None
        first = abs_path.split("::")[0]
        if first in STDLIB:
            return frozenset(), None
        if first in self._externals:
            return frozenset(), self._externals[first]
        target_crate = self._repo_crate(first)
        if target_crate:
            return self._resolve_in_crate(abs_path, target_crate, path)
        return self._resolve_in_crate(abs_path, crate_folder, path)

    def _repo_crate(self, name):
        for folder, meta in self._crates.items():
            if _norm_name(meta["name"]) == name:
                return folder
        return self._path_crates.get(name)

    def _absolute(self, spec, module, path, crate_folder):
        parts = spec.split("::")
        if not parts:
            return None
        if parts[0] == "crate":
            cname = _norm_name(self._crates[crate_folder]["name"])
            base = [cname] + parts[1:]
        elif parts[0] == "self":
            base = module.split("::") + parts[1:]
        elif parts[0] == "super":
            current = module
            i = 0
            while i < len(parts) and parts[i] == "super":
                parent = self._tree.parent_module(current)
                if not parent:
                    return None
                current = parent
                i += 1
            base = current.split("::") + parts[i:]
        else:
            head = parts[0]
            tail = parts[1:]
            inline = self._tree.inline_mods(path)
            if head in inline:
                base = module.split("::") + [head] + tail
            elif head in self._tree.root_module_names(crate_folder):
                base = [head] + tail
            else:
                base = parts
        return "::".join(base)

    def _without_ancestors(self, path, targets):
        ancestors = self._tree.ancestors(path)
        return frozenset(t for t in targets if t not in ancestors)

    def _resolve_in_crate(self, abs_path, crate_folder, importer):
        parts = abs_path.split("::")
        cname = _norm_name(self._crates[crate_folder]["name"])
        if parts[0] == cname:
            parts = parts[1:]
        for n in range(len(parts), -1, -1):
            mod_path = cname if n == 0 else f"{cname}::{'::'.join(parts[:n])}"
            target = self._tree.file_for_module(mod_path, crate_folder)
            if target and target != importer:
                return self._without_ancestors(importer, frozenset([target])), None
        return frozenset(), None


def enrich(facts, configs, files):
    """A binary Cargo.toml declares at its own path is an entry point, like src/main.rs."""
    for path, text in configs.items():
        meta = _parse_cargo(text)
        for bin_path in meta["bins"] if meta else ():
            target = _join(_crate_folder(path), bin_path)
            if target in facts:
                facts[target].is_entry = True


def resolver(facts, configs, files):
    file_set = set(files)
    parsed = {p: _parse_cargo(t) for p, t in configs.items()}
    workspace_members = None
    for path, meta in sorted(parsed.items()):
        if meta and meta["members"]:
            folder = _crate_folder(path)
            workspace_members = set()
            for pattern in meta["members"]:
                base = pattern if folder == "./" else _join(folder, pattern)
                for member in _glob_members(base, file_set):
                    workspace_members.add(_crate_folder(member))
            break
    crates = {}
    for path, meta in parsed.items():
        if not meta or not meta["name"]:
            continue
        folder = _crate_folder(path)
        if workspace_members is not None and not meta["members"]:
            if folder not in workspace_members:
                continue
        crates[folder] = meta
    externals = {}
    path_crates = {}
    name_to_folder = {_norm_name(m["name"]): f for f, m in crates.items() if m["name"]}
    for folder, meta in crates.items():
        for key, val in meta["deps"].items():
            p = _dep_path(val)
            if p:
                dep_cargo = _join(_join(folder, p), "Cargo.toml")
                if dep_cargo in configs:
                    dm = parsed[dep_cargo]
                    if dm and dm["name"]:
                        dep_folder = _crate_folder(dep_cargo)
                        path_crates[_norm_name(key)] = dep_folder
                        path_crates[_norm_name(dm["name"])] = dep_folder
                        continue
            externals.setdefault(_norm_name(key), key)
    tree = _ModuleTree(crates, facts, file_set)
    return Resolver(tree, crates, externals, {**name_to_folder, **path_crates}, file_set)
