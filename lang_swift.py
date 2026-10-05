"""Swift: one file per building, SPM modules from Package.swift, symbol resolution.

`test_files` and `enrich` read target folders from `Package.swift` for tests, entry points
and library public API.
"""

import langkit

NAME = "swift"
LABEL = "Swift"
EXTENSIONS = (".swift",)
SHEBANGS = ("swift",)
GRAMMARS = {".swift": "swift"}
CONFIG = ("Package.swift",)
FIRE = False
SAMPLE = {
    "Package.swift": (
        "// swift-tools-version: 5.9\nimport PackageDescription\n\n"
        "let package = Package(\n"
        '    name: "Sample",\n'
        "    targets: [\n"
        '        .target(name: "Core"),\n'
        '        .executableTarget(name: "App", dependencies: ["Core"]),\n'
        "    ]\n)\n"
    ),
    "Sources/Core/Core.swift": "public struct CoreValue {}\n",
    "Sources/App/App.swift": "import Core\n\n@main struct App {\n    static func main() {}\n}\n",
    "Tests/CoreTests/CoreTests.swift": "import XCTest\n@testable import Core\n\nfinal class T: XCTestCase {}\n",
}

GRAMMAR = "swift"
COMMENT = {"comment", "multiline_comment"}
COMPLEXITY = (
    "if_statement", "guard_statement", "for_statement", "while_statement",
    "repeat_while_statement", "switch_entry", "catch_block", "ternary_expression",
    "conjunction_expression", "disjunction_expression", "nil_coalescing_expression",
)
FUNCTIONS = ("function_declaration", "init_declaration", "deinit_declaration")
UNNAMED_FUNCTIONS = {"init_declaration": "init", "deinit_declaration": "deinit"}
TARGET_KINDS = {
    "target": (False, False),
    "executableTarget": (False, True),
    "testTarget": (True, False),
    "macro": (False, False),
    "plugin": (False, False),
}
SYSTEM = frozenset({
    "Swift", "Foundation", "UIKit", "AppKit", "SwiftUI", "Combine", "CoreData",
    "CoreGraphics", "CoreFoundation", "CoreImage", "CoreLocation", "MapKit",
    "AVFoundation", "Dispatch", "os", "OSLog", "Darwin", "Glibc", "Musl", "WinSDK",
    "XCTest", "Testing", "Observation", "SwiftData", "StoreKit", "WebKit", "Security",
    "Network", "CryptoKit", "UniformTypeIdentifiers", "_Concurrency",
})
DECL_NODES = frozenset({
    "class_declaration", "protocol_declaration", "typealias_declaration",
    "function_declaration", "property_declaration",
})
SKIP_DIRS = frozenset({".build", "DerivedData", "Pods"})
_EXTRA = {}


def grammar_for(path, files):
    return GRAMMAR


def unit_of(path, files):
    return path


def is_excluded(path, text):
    if path.endswith("Package.swift") or path.split("/")[-1] == "Package.swift":
        return True
    if any(p in SKIP_DIRS for p in path.split("/")):
        return True
    if text and _generated(text):
        return True
    return False


def is_test(path, text=None):
    if "Tests" in path.split("/"):
        return True
    if text:
        for spec in _imports_from_text(text):
            if spec in ("XCTest", "Testing"):
                return True
    return False


def scan(path, text, tree):
    if tree is None:
        return langkit.Facts()
    try:
        declares = _declares(tree)
        exports = _exports(tree)
        references = _references(tree, declares)
        imports = _imports(tree) + tuple(
            langkit.Import(n, kind="reference") for n in references)
        module = _module_guess(path)
        _EXTRA[path] = {
            "toplevel_public": _has_toplevel_public_type(tree),
            "toplevel_statements": _has_toplevel_statements(tree),
            "main_attr": _has_main_attribute(tree),
        }
        return langkit.Facts(
            loc=langkit.loc(text, tree, COMMENT),
            complexity=1 + langkit.count_types(tree.root_node, COMPLEXITY),
            exports=tuple(exports),
            notes=langkit.notes(tree, COMMENT),
            is_entry=_is_entry(path, text, tree),
            public=_is_public(tree),
            parse_error=langkit.first_error(tree),
            imports=imports,
            scope=module,
            declares=tuple(declares),
            references=tuple(references),
            functions=langkit.functions(tree.root_node, FUNCTIONS,
                                        lambda n: 1 + langkit.count_types(n, COMPLEXITY),
                                        lambda n: UNNAMED_FUNCTIONS.get(n.type)),
        )
    except Exception:
        return langkit.Facts(parse_error=langkit.first_error(tree))


def test_files(configs, files):
    layout = _layout(configs, files)
    return {f for f in files if f.endswith(".swift") and _in_folders(f, layout.test_folders)}


def enrich(facts, configs, files):
    layout = _layout(configs, files)
    has_pkg = bool(layout.test_folders or layout.executable_folders or layout.library_folders)
    try:
        for path, fx in facts.items():
            extra = _EXTRA.get(path, {})
            if has_pkg:
                if _in_folders(path, layout.executable_folders):
                    if extra.get("toplevel_statements") or extra.get("main_attr"):
                        fx.is_entry = True
                if _in_folders(path, layout.library_folders):
                    fx.public = extra.get("toplevel_public", False)
            elif extra.get("toplevel_statements"):
                parts = path.split("/")
                if len(parts) >= 2 and parts[0] == "Sources":
                    fx.is_entry = True
                elif len(parts) == 1:
                    fx.is_entry = True
    finally:
        _EXTRA.clear()


class _Layout:
    __slots__ = ("module_of", "repo_modules", "test_modules", "test_folders",
                 "executable_folders", "library_folders", "products")

    def __init__(self, module_of, repo_modules, test_modules, test_folders,
                 executable_folders, library_folders, products):
        self.module_of = module_of
        self.repo_modules = repo_modules
        self.test_modules = test_modules
        self.test_folders = test_folders
        self.executable_folders = executable_folders
        self.library_folders = library_folders
        self.products = products


class _Resolver:
    def __init__(self, layout, index, imports_by_path):
        self._layout = layout
        self._index = index
        self._imports = imports_by_path

    def resolve(self, path, imp):
        if imp.kind == "reference":
            return self._resolve_ref(path, imp.spec), None
        spec = imp.spec
        if spec in SYSTEM or spec in self._layout.repo_modules:
            return frozenset(), None
        return frozenset(), self._layout.products.get(spec, spec)

    def _resolve_ref(self, path, name):
        mod = self._layout.module_of.get(path)
        if mod is None:
            return frozenset()
        hit = self._index.lookup(mod, name)
        if hit and hit != path:
            return frozenset({hit})
        for imported in self._imports.get(path, ()):
            if imported not in self._layout.repo_modules:
                continue
            hit = self._index.lookup(imported, name)
            if hit and hit != path:
                return frozenset({hit})
        return frozenset()


def _generated(text):
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if not (stripped.startswith("//") or stripped.startswith("/*")):
            break
        low = stripped.lower()
        if "generated" in low and "do not edit" in low:
            return True
        if stripped.startswith("//"):
            continue
        if "*/" in stripped:
            break
    return False


def _join(base, *parts):
    bits = []
    for part in (base, *parts):
        if not part or part == ".":
            continue
        bits.append(part.strip("/"))
    return "/".join(bits)


def _pkg_dir(path):
    return path.rsplit("/", 1)[0] if "/" in path else ""


def _string_value(node):
    for c in langkit.walk(node):
        if c.type == "line_str_text":
            return langkit.node_text(c)
    raw = langkit.node_text(node)
    if len(raw) >= 2 and raw[0] == raw[-1] == '"':
        return raw[1:-1]
    return raw.strip('"')


def _call_kind(node):
    for c in node.children:
        if c.type != "prefix_expression":
            continue
        raw = langkit.node_text(c)
        if raw.startswith("."):
            return raw[1:]
    return None


def _call_args(node):
    args = {}
    for c in langkit.walk(node):
        if c.type != "value_argument":
            continue
        label = c.child_by_field_name("name")
        value = c.child_by_field_name("value")
        if label is not None and value is not None:
            args[langkit.node_text(label)] = _string_value(value)
    return args


def _parse_package(text, pkg_dir):
    tree = langkit.parse(GRAMMAR, text)
    if tree is None:
        return [], {}
    targets = []
    products = {}
    for node in langkit.walk(tree.root_node):
        if node.type != "call_expression":
            continue
        kind = _call_kind(node)
        if kind is None:
            continue
        args = _call_args(node)
        if kind in TARGET_KINDS:
            name = args.get("name")
            if not name:
                continue
            is_test, is_exec = TARGET_KINDS[kind]
            folder = _join(pkg_dir, args["path"]) if "path" in args else _join(
                pkg_dir, "Tests" if is_test else "Sources", name)
            targets.append((folder, name, kind))
        elif kind == "product":
            prod = args.get("name")
            pkg = args.get("package")
            if prod and pkg:
                products[prod] = pkg
    return targets, products


def _deepest_target(path, targets):
    best = None
    best_len = -1
    for folder, name, kind in targets:
        if path == folder or path.startswith(folder + "/"):
            if len(folder) > best_len:
                best = (folder, name, kind)
                best_len = len(folder)
    return best


def _in_folders(path, folders):
    return any(path == folder or path.startswith(folder + "/") for folder in folders)


def _layout(configs, files):
    swift = sorted(f for f in files if f.endswith(".swift"))
    targets = []
    products = {}
    for pkg_path, text in sorted(configs.items()):
        if not pkg_path.endswith("Package.swift"):
            continue
        t, p = _parse_package(text or "", _pkg_dir(pkg_path))
        targets.extend(t)
        products.update(p)

    module_of = {}
    test_modules = set()
    test_folders = set()
    executable_folders = set()
    library_folders = set()
    if targets:
        for folder, name, kind in targets:
            if kind == "testTarget":
                test_modules.add(name)
                test_folders.add(folder)
            elif kind == "executableTarget":
                executable_folders.add(folder)
            elif kind == "target":
                library_folders.add(folder)
        for path in swift:
            hit = _deepest_target(path, targets)
            if hit is None:
                module_of[path] = _module_guess(path)
                continue
            module_of[path] = hit[1]
    else:
        for path in swift:
            module_of[path] = _module_guess(path)

    return _Layout(module_of, set(module_of.values()), test_modules, test_folders,
                   executable_folders, library_folders, products)


def _module_guess(path):
    parts = path.split("/")
    for i, part in enumerate(parts[:-1]):
        if part == "Sources" and i + 1 < len(parts) - 1:
            return parts[i + 1]
        if part == "Tests" and i + 1 < len(parts) - 1:
            return parts[i + 1]
    if len(parts) == 1:
        return "(root)"
    return parts[0]


def _index_entries(facts, layout):
    rows = []
    for path, fx in facts.items():
        mod = layout.module_of.get(path, fx.scope)
        for name in fx.declares:
            rows.append((mod, name, path))
    return rows


def resolver(facts, configs, files):
    layout = _layout(configs, files)
    imports = {
        p: tuple(i.spec for i in fx.imports if i.kind == "import")
        for p, fx in facts.items()
    }
    index = langkit.SymbolIndex(_index_entries(facts, layout))
    return _Resolver(layout, index, imports)


def _visibility(node):
    for c in node.children:
        if c.type != "modifiers":
            continue
        for m in c.children:
            if m.type == "visibility_modifier":
                return langkit.node_text(m)
    return None


def _is_exported(node):
    vis = _visibility(node)
    return vis not in ("private", "fileprivate")


def _is_extension(node):
    return node.type == "class_declaration" and any(
        c.type == "extension" for c in node.children)


def _type_name(node):
    for c in langkit.walk(node):
        if c.type == "type_identifier":
            return langkit.node_text(c)
    return None


def _decl_name(node):
    if node.type == "function_declaration":
        for c in node.children:
            if c.type == "simple_identifier":
                return langkit.node_text(c)
    if node.type == "property_declaration":
        for c in langkit.walk(node):
            if c.type == "simple_identifier" and c.parent and c.parent.type == "pattern":
                return langkit.node_text(c)
    if node.type == "typealias_declaration":
        for c in node.children:
            if c.type == "typealias":
                continue
            if c.type == "simple_identifier":
                return langkit.node_text(c)
    if node.type in ("class_declaration", "protocol_declaration"):
        return _type_name(node)
    return None


def _top_level_nodes(tree):
    for c in tree.root_node.children:
        if c.type in COMMENT:
            continue
        yield c


def _declares(tree):
    names = []
    for node in _top_level_nodes(tree):
        if node.type not in DECL_NODES or _is_extension(node):
            continue
        name = _decl_name(node)
        if name:
            names.append(name)
    return tuple(dict.fromkeys(names))


def _member_exports(node):
    names = []
    body = None
    for c in node.children:
        if c.type in ("class_body", "protocol_body", "enum_class_body"):
            body = c
            break
    if body is None:
        return names
    for child in body.children:
        if child.type not in ("function_declaration", "property_declaration"):
            continue
        if not _is_exported(child):
            continue
        name = _decl_name(child)
        if name:
            names.append(name)
    return names


def _exports(tree):
    names = []
    for node in _top_level_nodes(tree):
        if node.type not in DECL_NODES:
            continue
        if _is_extension(node):
            names.extend(_member_exports(node))
            continue
        if not _is_exported(node):
            continue
        name = _decl_name(node)
        if name:
            names.append(name)
        if node.type in ("class_declaration", "protocol_declaration"):
            names.extend(_member_exports(node))
    return tuple(dict.fromkeys(names))


def _is_public(tree):
    for node in langkit.walk(tree.root_node):
        if node.type not in DECL_NODES:
            continue
        vis = _visibility(node)
        if vis in ("public", "open"):
            return True
        if node.type in ("class_declaration", "protocol_declaration"):
            body = next((c for c in node.children
                         if c.type in ("class_body", "protocol_body", "enum_class_body")), None)
            if body is None:
                continue
            for child in body.children:
                if child.type not in ("function_declaration", "property_declaration"):
                    continue
                if _visibility(child) in ("public", "open"):
                    return True
    return False


def _imports(tree):
    specs = []
    for node in langkit.walk(tree.root_node):
        if node.type != "import_declaration":
            continue
        spec = _import_spec(node)
        if spec:
            specs.append(spec)
    return tuple(langkit.Import(s) for s in dict.fromkeys(specs))


def _import_spec(node):
    for c in langkit.walk(node):
        if c.type != "identifier":
            continue
        raw = langkit.node_text(c)
        return raw.split(".")[0]
    return None


def _imports_from_text(text):
    tree = langkit.parse(GRAMMAR, text)
    if tree is None:
        return ()
    return tuple(i.spec for i in _imports(tree))


def _extended_type_name(node):
    if not _is_extension(node):
        return None
    for c in node.children:
        if c.type != "user_type":
            continue
        for d in c.children:
            if d.type == "type_identifier":
                return langkit.node_text(d)
    return None


def _references(tree, declares):
    declared = set(declares)
    found = []
    seen = set()

    def add(name):
        if not name or name in declared or name in seen:
            return
        seen.add(name)
        found.append(name)

    for node in langkit.walk(tree.root_node):
        if node.type == "type_identifier":
            parent = node.parent
            if parent and parent.type == "user_type":
                gp = parent.parent
                if gp and gp.type == "class_declaration" and _is_extension(gp):
                    if langkit.node_text(node) == _extended_type_name(gp):
                        continue
            add(langkit.node_text(node))
        elif node.type == "inheritance_specifier":
            for c in langkit.walk(node):
                if c.type == "type_identifier":
                    add(langkit.node_text(c))
        elif node.type == "call_expression":
            for c in node.children:
                if c.type == "simple_identifier":
                    add(langkit.node_text(c))
                    break
                if c.type == "navigation_expression":
                    for d in c.children:
                        if d.type == "simple_identifier":
                            add(langkit.node_text(d))
                            break
                    break
        elif node.type == "attribute":
            for c in langkit.walk(node):
                if c.type == "type_identifier":
                    add(langkit.node_text(c))

    return tuple(found)


def _has_toplevel_public_type(tree):
    for node in _top_level_nodes(tree):
        if node.type not in ("class_declaration", "protocol_declaration") or _is_extension(node):
            continue
        if _visibility(node) in ("public", "open"):
            return True
    return False


def _has_main_attribute(tree):
    for node in langkit.walk(tree.root_node):
        if node.type != "class_declaration" or _is_extension(node):
            continue
        for c in langkit.walk(node):
            if c.type == "attribute" and langkit.node_text(c).lstrip().startswith("@main"):
                return True
    return False


def _has_toplevel_statements(tree):
    for node in _top_level_nodes(tree):
        if node.type in DECL_NODES or node.type == "import_declaration":
            continue
        return True
    return False


def _is_entry(path, text, tree):
    if text.lstrip().startswith("#!"):
        return True
    if path.rsplit("/", 1)[-1] == "main.swift":
        return True
    return _has_main_attribute(tree)
