"""JavaScript and TypeScript: one building per file, ESM and CommonJS imports.

TypeScript grammar gaps (callable-interface overloads, ``import()`` type args) produce
false fires on real code, so ``FIRE`` omits ``.ts``/``.mts``/``.cts``/``.tsx``.
"""

import json
import os
import posixpath
import re

import floor
import langkit

NAME = "javascript"
LABEL = "JavaScript/TypeScript"
EXTENSIONS = (".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".mts", ".cts")
SHEBANGS = ("node", "deno", "bun", "ts-node", "tsx")
GRAMMARS = {ext: "javascript" for ext in (".js", ".jsx", ".mjs", ".cjs")}
GRAMMARS.update({".ts": "typescript", ".mts": "typescript", ".cts": "typescript", ".tsx": "tsx"})
CONFIG = ("package.json", "tsconfig.json", "tsconfig.*.json", "jsconfig.json", "pnpm-workspace.yaml")
FIRE = (".js", ".jsx", ".mjs", ".cjs")
SAMPLE = {
    "src/a.ts": "import { b } from './b';\nexport function f() { return b; }\n",
    "src/b.ts": "export const b = 1;\nimport ky from 'ky';\n",
    "src/a.test.ts": "import './a';\n",
    "package.json": '{"name": "sample", "dependencies": {"ky": "^1.0.0"}}\n',
}

COMMENT = {"comment"}
COMPLEXITY = (
    "if_statement", "for_statement", "for_in_statement", "while_statement", "do_statement",
    "switch_case", "catch_clause", "ternary_expression",
    ("binary_expression", ("&&", "||", "??")),
)
FUNCTIONS = ("function_declaration", "generator_function_declaration", "function_expression",
             "function", "generator_function", "arrow_function", "method_definition")
CODE_EXTS = (".ts", ".tsx", ".mts", ".cts", ".js", ".jsx", ".mjs", ".cjs")
ASSET_EXTS = frozenset("""
.css .scss .sass .less .json .svg .png .jpg .jpeg .gif .webp .woff .woff2 .ttf .eot .ico
.bmp .mp3 .mp4 .wasm .map .md .txt .html .xml .yaml .yml .vue .svelte .graphql .gql
""".split())
EXCLUDED_DIRS = frozenset(
    {"dist", "coverage", ".next", ".nuxt", ".svelte-kit", "storybook-static"})
RUNNERS = frozenset({"node", "ts-node", "tsx", "bun", "deno"})
_node = """
assert buffer child_process cluster console constants crypto dgram diagnostics_channel dns
domain events fs http http2 https inspector module net os path perf_hooks process punycode
querystring readline repl stream string_decoder sys timers tls trace_events tty url util v8
vm wasi worker_threads zlib
""".split()
NODE_BUILTINS = frozenset(_node + [f"{m}/promises" for m in _node])
STRING = re.compile(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|`(?:\\.|[^`\\])*`')
LINE_COMMENT = re.compile(r"//[^\n]*")
BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
TRAILING_COMMA = re.compile(r",(\s*[}\]])")
PNPM_PACKAGES = re.compile(r"^\s*-\s*['\"]?([^'\"#\n]+)", re.MULTILINE)
GENERATED = re.compile(r"@generated|DO NOT EDIT", re.IGNORECASE)
INDEX = re.compile(r"^index\.(tsx?|jsx?|mjsx?|cjsx?|mts|cts)$", re.IGNORECASE)


def unit_of(path, files):
    return path


def is_test(path, text=None):
    name = path.rsplit("/", 1)[-1]
    if ".test." in name or ".spec." in name:
        return True
    return any(p in ("__tests__", "test", "tests", "e2e", "cypress")
               for p in path.split("/")[:-1])


def is_excluded(path, text):
    parts = path.split("/")
    if any(p in EXCLUDED_DIRS for p in parts[:-1]):
        return True
    base = parts[-1]
    if base.endswith(".min.js") or base.endswith(".bundle.js") or base.endswith(".chunk.js"):
        return True
    if path.endswith(".d.ts"):
        return True
    if text:
        head = text[:2000]
        if GENERATED.search(head):
            return True
        if tree := _parse(path, text):
            for node in langkit.walk(tree.root_node):
                if node.type == "comment" and node.start_byte < 400:
                    if GENERATED.search(langkit.node_text(node)):
                        return True
                    break
    return False


def scan(path, text, tree):
    if tree is None:
        return langkit.Facts()
    grammar = GRAMMARS.get(os.path.splitext(path)[1], "javascript")
    exports = _exports(tree.root_node, grammar)
    return langkit.Facts(
        loc=langkit.loc(text, tree, COMMENT),
        complexity=1 + langkit.count_types(tree.root_node, COMPLEXITY),
        exports=tuple(sorted(set(exports))),
        notes=langkit.notes(tree, COMMENT),
        is_entry=_shebang_entry(text),
        is_package=INDEX.match(os.path.basename(path)) and _is_package(tree.root_node),
        parse_error=langkit.first_error(tree),
        imports=tuple(_imports(tree.root_node)),
        functions=langkit.functions(tree.root_node, FUNCTIONS,
                                    lambda n: 1 + langkit.count_types(n, COMPLEXITY)),
    )


def enrich(facts, configs, files):
    """Apply package.json entry and public flags."""
    packages = _Packages(configs, files)
    for path, fx in facts.items():
        if packages.is_entry(path):
            fx.is_entry = True
        if packages.is_public(path):
            fx.public = True


def resolver(facts, configs, files):
    enrich(facts, configs, files)
    return _Resolver(_Packages(configs, files), _TsConfigs(configs, files), files)


class _Resolver:
    def __init__(self, packages, tsconfigs, files):
        self._packages = packages
        self._tsconfigs = tsconfigs
        self._files = frozenset(files)

    def resolve(self, path, imp):
        spec = imp.spec
        if not spec or "`" in spec:
            return frozenset(), None
        if spec.startswith("./") or spec.startswith("../"):
            return _resolve_relative(spec, path, self._files), None
        if spec.startswith("node:"):
            return frozenset(), None
        bare = spec[5:] if spec.startswith("node:") else spec
        root = bare.split("/")[0]
        if bare in NODE_BUILTINS or root in NODE_BUILTINS:
            return frozenset(), None
        found = self._packages.resolve(spec, self._files)
        if found:
            return found, None
        found = self._tsconfigs.resolve(spec, path, self._files)
        if found:
            return found, None
        if spec.startswith("@"):
            parts = spec.split("/")
            name = "/".join(parts[:2]) if len(parts) >= 2 else spec
        else:
            name = spec.split("/")[0]
        return frozenset(), name


def _parse(path, text):
    grammar = GRAMMARS.get(os.path.splitext(path)[1])
    return langkit.parse(grammar, text) if grammar else None


def _shebang_entry(text):
    program = floor.interpreter(text or "")
    return program in SHEBANGS if program else False


def _string_spec(node):
    if node is None:
        return None
    if node.type == "string":
        for child in node.children:
            if child.type == "string_fragment":
                return langkit.node_text(child)
        return None
    if node.type == "template_string":
        return None
    return None


def _import_spec(node):
    for child in node.children:
        if child.type == "string":
            return _string_spec(child)
        if child.type == "import_require_clause":
            for sub in langkit.walk(child):
                if sub.type == "string":
                    return _string_spec(sub)
    return None


def _imports(root):
    specs = []
    seen = set()
    for node in langkit.walk(root):
        if node.type == "import_statement":
            spec = _import_spec(node)
        elif node.type == "export_statement" and any(c.type == "from" for c in node.children):
            spec = _import_spec(node)
        elif node.type == "call_expression":
            parts = [c for c in node.children if c.type not in ("(", ")")]
            if len(parts) < 2:
                continue
            fn, args = parts[0], parts[1]
            if fn.type == "identifier" and langkit.node_text(fn) == "require":
                spec = _first_string(args)
            elif fn.type == "import":
                spec = _first_string(args)
            else:
                continue
        else:
            continue
        if spec and spec not in seen:
            seen.add(spec)
            specs.append(langkit.Import(spec))
    return specs


def _first_string(args_node):
    for child in langkit.walk(args_node):
        if child.type == "string":
            return _string_spec(child)
    return None


def _exports(root, grammar):
    names = []
    for node in langkit.walk(root):
        if node.type == "export_statement":
            names.extend(_export_names(node, grammar))
        elif node.type == "assignment_expression":
            names.extend(_cjs_export_names(node))
    return names


def _export_names(node, grammar):
    text = langkit.node_text(node)
    if " from " in text:
        if "* as " in text:
            for child in node.children:
                if child.type == "namespace_export":
                    for sub in child.children:
                        if sub.type == "identifier":
                            return [langkit.node_text(sub)]
        if any(c.type == "*" for c in node.children):
            return ["*"]
    if any(c.type == "default" for c in node.children):
        return ["default"]
    names = []
    for child in node.children:
        if child.type in ("function_declaration", "class_declaration", "enum_declaration",
                          "interface_declaration", "type_alias_declaration"):
            for sub in child.children:
                if sub.type in ("identifier", "type_identifier"):
                    names.append(langkit.node_text(sub))
                    break
        elif child.type == "lexical_declaration":
            for sub in langkit.walk(child):
                if sub.type == "variable_declarator":
                    ident = sub.child_by_field_name("name")
                    if ident is None:
                        for x in sub.children:
                            if x.type == "identifier":
                                ident = x
                                break
                    if ident is not None and ident.type == "identifier":
                        names.append(langkit.node_text(ident))
        elif child.type == "export_clause":
            for spec in child.children:
                if spec.type != "export_specifier":
                    continue
                ids = [c for c in spec.children if c.type == "identifier"]
                if not ids:
                    continue
                names.append(langkit.node_text(ids[-1]))
    return names


def _cjs_export_names(node):
    left = node.children[0] if node.children else None
    if left is None:
        return []
    chain = langkit.node_text(left)
    if left.type == "member_expression" and chain.startswith("exports."):
        return [chain.split(".", 1)[1]]
    if left.type == "member_expression" and chain.startswith("module.exports."):
        return [chain.rsplit(".", 1)[-1]]
    if chain == "module.exports":
        right = node.children[-1] if len(node.children) >= 3 else None
        if right is None:
            return []
        if right.type == "object":
            out = []
            for child in right.children:
                if child.type == "pair":
                    for sub in child.children:
                        if sub.type == "property_identifier":
                            out.append(langkit.node_text(sub))
                            break
            return out or ["default"]
        return ["default"]
    if chain == "exports" or chain.startswith("module.exports."):
        parts = chain.split(".")
        if len(parts) >= 2:
            return [parts[-1]]
    return []


def _is_package(root):
    for child in root.children:
        if child.type in ("import_statement", "export_statement"):
            continue
        if child.type == "comment" or not langkit.node_text(child).strip():
            continue
        return False
    return bool(root.children)


def _strip_jsonc(text):
    out = []
    i = 0
    while i < len(text):
        if text[i] in "\"'":
            quote = text[i]
            j = i + 1
            while j < len(text):
                if text[j] == "\\":
                    j += 2
                    continue
                if text[j] == quote:
                    j += 1
                    break
                j += 1
            out.append(text[i:j])
            i = j
            continue
        if text.startswith("//", i):
            j = text.find("\n", i)
            i = len(text) if j < 0 else j
            continue
        if text.startswith("/*", i):
            j = text.find("*/", i + 2)
            i = j + 2 if j >= 0 else len(text)
            continue
        out.append(text[i])
        i += 1
    cleaned = "".join(out)
    cleaned = TRAILING_COMMA.sub(r"\1", cleaned)
    return cleaned


def _parse_json(text):
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    try:
        return json.loads(_strip_jsonc(text))
    except json.JSONDecodeError:
        return None


def _resolve_relative(spec, from_path, files):
    base = posixpath.dirname(from_path)
    joined = posixpath.normpath(posixpath.join(base, spec))
    if joined.startswith("../"):
        return frozenset()
    if _ext_of(joined) in ASSET_EXTS:
        return frozenset()
    if joined.endswith(".d.ts"):
        return frozenset()
    found = set()
    stem, ext = posixpath.splitext(joined)
    candidates = [joined]
    if not ext:
        candidates.extend(joined + e for e in CODE_EXTS)
        candidates.extend(f"{joined}/index{e}" for e in CODE_EXTS)
    elif ext not in CODE_EXTS:
        return frozenset()
    else:
        candidates.extend(f"{stem}{alt}" for alt in CODE_EXTS if alt != ext)
        candidates.extend(f"{joined}/index{e}" for e in CODE_EXTS)
        if ext in (".js", ".mjs", ".cjs") and joined not in files:
            for alt in (".ts", ".tsx", ".mts", ".cts"):
                candidates.append(stem + alt)
                candidates.append(f"{stem}/index{alt}")
    for path in candidates:
        if path in files and not path.endswith(".d.ts") and _ext_of(path) not in ASSET_EXTS:
            found.add(path)
    return frozenset(found)


def _ext_of(path):
    for ext in CODE_EXTS:
        if path.endswith(ext):
            return ext
    dot = path.rfind(".")
    return path[dot:] if dot >= 0 else ""


class _Packages:
    def __init__(self, configs, files):
        self._files = frozenset(files)
        self._by_name = {}
        self._entries = {}
        self._public = set()
        self._roots = {}
        for path, text in sorted(configs.items()):
            if not path.endswith("package.json"):
                continue
            data = _parse_json(text)
            if not isinstance(data, dict):
                continue
            root = posixpath.dirname(path) or "."
            name = data.get("name")
            if isinstance(name, str) and name:
                self._by_name[name] = root
            entries = _package_entries(root, data, files)
            self._roots[root] = data
            for entry in entries:
                self._entries[entry] = root
                if entry in files:
                    self._public.add(entry)
                else:
                    src = _src_fallback(entry, root, files)
                    if src:
                        self._public.add(src)
            self._mark_entries(root, data, files)

    def is_entry(self, path):
        return path in self._entries

    def is_public(self, path):
        return path in self._public

    def resolve(self, spec, files):
        if spec in self._by_name:
            root = self._by_name[spec]
            return _resolve_package_root(root, self._roots.get(root, {}), files)
        if spec.startswith("@"):
            parts = spec.split("/")
            if len(parts) >= 2:
                name = f"{parts[0]}/{parts[1]}"
                if name in self._by_name:
                    sub = "/".join(parts[2:])
                    return _resolve_package_sub(self._by_name[name], sub, files)
        elif "/" in spec:
            name = spec.split("/")[0]
            if name in self._by_name:
                sub = spec[len(name) + 1:]
                return _resolve_package_sub(self._by_name[name], sub, files)
        return frozenset()

    def _mark_entries(self, root, data, files):
        root_prefix = "" if root == "." else root + "/"
        for key in ("bin", "scripts"):
            val = data.get(key)
            if key == "bin":
                items = []
                if isinstance(val, str):
                    items.append(val)
                elif isinstance(val, dict):
                    items.extend(v for v in val.values() if isinstance(v, str))
                for rel in items:
                    self._entries[_join(root, rel)] = root
            elif isinstance(val, dict):
                for cmd in val.values():
                    if not isinstance(cmd, str):
                        continue
                    tokens = cmd.split()
                    for i, tok in enumerate(tokens):
                        if tok not in RUNNERS or i + 1 >= len(tokens):
                            continue
                        target = tokens[i + 1]
                        if target.startswith("-"):
                            continue
                        candidate = _join(root, target)
                        if candidate in files:
                            self._entries[candidate] = root


def _join(root, rel):
    if root in (".", ""):
        return posixpath.normpath(rel)
    return posixpath.normpath(posixpath.join(root, rel))


def _package_entries(root, data, files):
    entries = []
    for key in ("main", "module", "types"):
        val = data.get(key)
        if isinstance(val, str):
            entries.append(_join(root, val))
    exports = data.get("exports")
    if isinstance(exports, str):
        entries.append(_join(root, exports))
    elif isinstance(exports, dict):
        entries.extend(_join(root, v) for v in _flatten_exports(exports))
    return [e for e in entries if e]


def _flatten_exports(node):
    if isinstance(node, str):
        return [node]
    if isinstance(node, dict):
        out = []
        for val in node.values():
            out.extend(_flatten_exports(val))
        return out
    if isinstance(node, list):
        out = []
        for val in node:
            out.extend(_flatten_exports(val))
        return out
    return []


def _resolve_package_root(root, data, files):
    for entry in _package_entries(root, data, files):
        resolved = _resolve_relative(entry if entry.startswith(".") else f"./{posixpath.basename(entry)}",
                                      _join(root, "package.json"), files)
        if not resolved:
            resolved = _resolve_relative(f"./{entry}", _join(root, "package.json"), files)
        if resolved:
            return resolved
        src = _src_fallback(entry, root, files)
        if src:
            return frozenset([src])
    for name in ("index.ts", "index.tsx", "index.js", "index.mjs"):
        candidate = _join(root, name)
        if candidate in files:
            return frozenset([candidate])
        candidate = _join(root, f"src/{name}")
        if candidate in files:
            return frozenset([candidate])
    return frozenset()


def _resolve_package_sub(root, sub, files):
    if not sub:
        return _resolve_package_root(root, {}, files)
    for base in (root, _join(root, "src")):
        rel = f"./{sub}"
        from_path = _join(base, "package.json")
        found = _resolve_relative(rel, from_path, files)
        if found:
            return found
    return frozenset()


def _src_fallback(entry, root, files):
    target = _join(root, entry)
    if target in files or not any(part in ("dist", "lib") for part in target.split("/")):
        return None
    base = posixpath.basename(entry)
    stem, _ = posixpath.splitext(base)
    if not stem:
        return None
    for ext in CODE_EXTS:
        src_path = _join(root, f"src/{stem}{ext}")
        if src_path in files:
            return src_path
    return None


class _TsConfigs:
    def __init__(self, configs, files):
        self._files = frozenset(files)
        self._texts = dict(configs)
        self._configs = {}
        for path, text in sorted(configs.items()):
            if not _is_tsconfig_path(path):
                continue
            data = _parse_json(text)
            if isinstance(data, dict):
                self._configs[path] = data

    def resolve(self, spec, from_path, files):
        cfg_path = self._nearest(from_path)
        if not cfg_path:
            return frozenset()
        merged = self._merged(cfg_path)
        opts = merged.get("compilerOptions") or {}
        base_url = opts.get("baseUrl", ".")
        cfg_dir = posixpath.dirname(cfg_path) or "."
        paths = opts.get("paths") or {}
        for pattern, targets in sorted(paths.items()):
            if pattern.count("*") > 1:
                continue
            matched = _match_pattern(spec, pattern)
            if matched is None:
                continue
            target_list = targets if isinstance(targets, list) else [targets]
            for target in target_list:
                if not isinstance(target, str):
                    continue
                mapped = target.replace("*", matched) if "*" in target else target
                rel = _join(cfg_dir, base_url) if not mapped.startswith(".") else mapped
                if not mapped.startswith("."):
                    rel = posixpath.normpath(posixpath.join(_join(cfg_dir, base_url), mapped))
                else:
                    rel = posixpath.normpath(posixpath.join(cfg_dir, mapped))
                found = _resolve_relative(f"./{rel}", from_path, files)
                if found:
                    return found
        rel = posixpath.normpath(posixpath.join(_join(cfg_dir, base_url), spec))
        return _resolve_relative(f"./{rel}", from_path, files)

    def _nearest(self, from_path):
        folder = posixpath.dirname(from_path) or "."
        parts = [] if folder == "." else folder.split("/")
        for i in range(len(parts), -1, -1):
            prefix = "." if i == 0 else "/".join(parts[:i])
            for name in ("tsconfig.json", "jsconfig.json"):
                candidate = f"{prefix}/{name}" if prefix != "." else name
                if candidate in self._configs:
                    return candidate
            for path in self._configs:
                base = os.path.basename(path)
                if base.startswith("tsconfig.") and base.endswith(".json"):
                    parent = posixpath.dirname(path) or "."
                    if parent == (prefix if prefix != "." else "."):
                        return path
        return None

    def _merged(self, path):
        data = dict(self._configs.get(path) or {})
        ext = data.get("extends")
        if isinstance(ext, str):
            base_path = posixpath.normpath(posixpath.join(posixpath.dirname(path) or ".", ext))
            base_data = self._configs.get(base_path)
            if base_data is None and base_path in self._texts:
                base_data = _parse_json(self._texts[base_path])
                if isinstance(base_data, dict):
                    self._configs[base_path] = base_data
            if base_data is not None:
                base = self._merged(base_path)
                opts = dict(base.get("compilerOptions") or {})
                opts.update(data.get("compilerOptions") or {})
                merged = dict(base)
                merged.update(data)
                merged["compilerOptions"] = opts
                return merged
        return data


def _is_tsconfig_path(path):
    base = os.path.basename(path)
    return (base == "tsconfig.json" or base == "jsconfig.json"
            or (base.startswith("tsconfig.") and base.endswith(".json")))


def _match_pattern(spec, pattern):
    if "*" not in pattern:
        return spec if spec == pattern else None
    pre, post = pattern.split("*", 1)
    if not spec.startswith(pre) or not spec.endswith(post):
        return None
    return spec[len(pre):len(spec) - len(post) if post else len(spec)]
