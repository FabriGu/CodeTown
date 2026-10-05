"""Shell scripts and Bats tests, read with the bash tree-sitter grammar."""

import posixpath
import re

import floor
import langkit

NAME = "shell"
LABEL = "Shell"
EXTENSIONS = (".sh", ".bash", ".zsh", ".ksh", ".bats")
SHEBANGS = ("sh", "bash", "zsh", "dash", "ksh")
GRAMMARS = {ext: "bash" for ext in EXTENSIONS}
CONFIG = ()
# Extensionless libexec scripts use parameter expansions the bash grammar mis-parses.
FIRE = (".sh", ".bash")
SAMPLE = {
    "lib.sh": "mylib() { echo 1; }\n",
    "a.sh": "#!/bin/bash\nsource ./lib.sh\ndocker ps\n",
    "test/t.bats": "load ../lib.sh\nrun echo hi\n",
}

GRAMMAR = "bash"
COMMENT = {"comment"}
COMPLEXITY = (
    "if_statement", "elif_clause", "for_statement", "c_style_for_statement",
    "while_statement", "case_item", ("list", ("&&", "||")),
)
FUNCTIONS = ("function_definition",)
SOURCE_CMDS = frozenset({"source", "."})
RUN_CMDS = frozenset({"bash", "sh", "zsh", "dash", "ksh", "exec"})
RUN_SUFFIX = ".sh"
BUILTINS = frozenset("""
. source cd echo printf read test [ export local set shift trap exit return true false
eval exec wait unset readonly declare typeset alias unalias hash type command builtin enable
shopt getopts let ulimit umask fg bg jobs disown suspend fc bind history caller pushd popd
dirs break continue times kill mapfile readarray compgen complete colon :
""".split())
COMMON = frozenset("""
ls cat grep sed awk cut sort uniq head tail tr wc find xargs mkdir rm cp mv chmod chown chgrp
ln touch rmdir date sleep tee basename dirname readlink realpath env mktemp pwd which command
printf id uname seq paste join split fmt fold nl od hexdump xxd file stat du df sync install
link nice nohup timeout watch groups whoami logname hostname pgrep pkill ps kill sudo sysctl
tar gzip gunzip zip unzip bzip2 bunzip2 xz shasum sha256sum sha1sum md5sum
""".split())
_DIRNAME_ZERO = re.compile(
    r'^dirname\s+("?\$0"?|\$0)\s*$')
_DIRNAME_BASH = re.compile(
    r'^dirname\s+"?\$\{BASH_SOURCE\[0\]\}"?\s*$')
REF_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]*$")


def grammar_for(path, files):
    return GRAMMAR


def unit_of(path, files):
    return path


def is_test(path, text=None):
    if path.endswith(".bats"):
        return True
    return any(p in ("test", "tests") for p in path.split("/")[:-1])


def scan(path, text, tree):
    if tree is None:
        return langkit.Facts()
    script_dir_vars = set()
    imports = []
    refs = set()
    for node in langkit.walk(tree.root_node):
        if node.type == "variable_assignment":
            var = _assignment_name(node)
            val = _assignment_value(node)
            if var and val is not None and _is_script_dir_value(val):
                script_dir_vars.add(var)
        elif node.type == "command":
            _scan_command(node, script_dir_vars, imports, refs)
    export_names = tuple(_function_names(tree.root_node))
    return langkit.Facts(
        loc=langkit.loc(text, tree, COMMENT),
        complexity=1 + langkit.count_types(tree.root_node, COMPLEXITY),
        exports=export_names,
        notes=langkit.notes(tree, COMMENT),
        is_entry=floor.interpreter(text) is not None,
        parse_error=langkit.first_error(tree),
        imports=tuple(imports) + tuple(
            langkit.Import(name, kind="reference") for name in sorted(refs)),
        functions=langkit.functions(tree.root_node, FUNCTIONS,
                                    lambda n: 1 + langkit.count_types(n, COMPLEXITY)),
    )


def _scan_command(node, script_dir_vars, imports, refs):
    parts = [c for c in node.children if c.type != "redirected_statement"]
    if not parts:
        return
    name_node = parts[0]
    if name_node.type != "command_name":
        return
    cmd = _plain_word(name_node)
    if not cmd:
        return
    args = parts[1:]
    if cmd in SOURCE_CMDS:
        spec = _path_arg(args, script_dir_vars)
        if spec:
            imports.append(langkit.Import(spec, kind="import"))
        return
    if cmd == "load":
        spec = _path_arg(args, script_dir_vars)
        if spec:
            imports.append(langkit.Import(spec, kind="import"))
        return
    if cmd in RUN_CMDS:
        spec = _path_arg(args, script_dir_vars)
        if spec:
            imports.append(langkit.Import(spec, kind="runs"))
        return
    if cmd == "run":
        spec = _path_arg(args, script_dir_vars)
        if spec:
            imports.append(langkit.Import(spec, kind="runs"))
        return
    if "/" in cmd or cmd.endswith(RUN_SUFFIX):
        imports.append(langkit.Import(cmd, kind="runs"))
        return
    if REF_NAME.match(cmd):
        refs.add(cmd)
    for arg in args:
        _scan_arg_commands(arg, refs)


def _scan_arg_commands(node, refs):
    for sub in langkit.walk(node):
        if sub.type != "command":
            continue
        parts = [c for c in sub.children if c.type != "redirected_statement"]
        if not parts or parts[0].type != "command_name":
            continue
        cmd = _plain_word(parts[0])
        if cmd and REF_NAME.match(cmd) and cmd not in SOURCE_CMDS and cmd not in RUN_CMDS:
            refs.add(cmd)


def _path_arg(args, script_dir_vars):
    for arg in args:
        if arg.type in ("word", "string", "raw_string", "concatenation"):
            return _literal_path(arg, script_dir_vars)
    return None


def _literal_path(node, script_dir_vars):
    if node.type == "word":
        text = langkit.node_text(node)
        if not text or "$" in text or "`" in text:
            return None
        return _normalize_spec(text)
    if node.type in ("string", "raw_string"):
        return _string_path(node, script_dir_vars)
    if node.type == "concatenation":
        parts = []
        for child in node.children:
            piece = _literal_path(child, script_dir_vars)
            if piece is None:
                return None
            parts.append(piece)
        return _normalize_spec("".join(parts))
    return None


def _string_path(node, script_dir_vars):
    parts = []
    for child in node.children:
        if child.type == "string_content":
            parts.append(langkit.node_text(child))
        elif child.type == "simple_expansion":
            var = langkit.node_text(child)[1:]
            if var not in script_dir_vars:
                return None
        elif child.type == "expansion":
            if not _is_bash_source_dir(child):
                return None
        elif child.type == "command_substitution":
            if not _is_script_dir_substitution(child):
                return None
        elif child.type in ('"', "'"):
            continue
        else:
            return None
    path = _normalize_spec("".join(parts))
    return path or None


def _assignment_name(node):
    for child in node.children:
        if child.type == "variable_name":
            return langkit.node_text(child)
    return None


def _assignment_value(node):
    for child in node.children:
        if child.type in ("command_substitution", "expansion", "string", "raw_string", "word",
                          "concatenation"):
            return child
    return None


def _is_script_dir_value(node):
    if node.type == "expansion":
        return _is_bash_source_dir(node)
    if node.type == "command_substitution":
        return _is_script_dir_substitution(node)
    if node.type == "string":
        inner = langkit.node_text(node)
        if "$" in inner:
            for child in node.children:
                if child.type == "command_substitution":
                    return _is_script_dir_substitution(child)
            return False
    return False


def _is_bash_source_dir(node):
    text = langkit.node_text(node)
    return "BASH_SOURCE" in text and "%" in text


def _is_script_dir_substitution(node):
    inner = langkit.node_text(node)[2:-1].strip()
    if _DIRNAME_ZERO.match(inner) or _DIRNAME_BASH.match(inner):
        return True
    if "dirname" in inner and "BASH_SOURCE" in inner and "pwd" in inner:
        return True
    if _DIRNAME_ZERO.match(inner.split("&&")[0].strip()):
        return True
    return False


def _normalize_spec(path):
    path = path.strip()
    if path.startswith("/") and not path.startswith("//"):
        path = path[1:]
    return path


def _plain_word(node):
    for child in node.children:
        if child.type == "word":
            return langkit.node_text(child)
    text = langkit.node_text(node)
    return text if text and "/" not in text else None


def _function_names(root):
    for node in langkit.walk(root):
        if node.type != "function_definition":
            continue
        for child in node.children:
            if child.type == "word":
                name = langkit.node_text(child)
                if name:
                    yield name
                break


class Resolver:
    def __init__(self, facts, files):
        self._facts = facts
        self._files = frozenset(files)
        self._shell = frozenset(facts)
        self._by_base = {}
        for path in self._shell:
            self._by_base.setdefault(posixpath.basename(path), []).append(path)
        self._functions = {path: set(fx.exports) for path, fx in facts.items()}
        self._declares = {}
        for path, fx in facts.items():
            for name in fx.exports:
                self._declares.setdefault(name, []).append(path)
        self._sourced = self._source_closure()

    def _source_closure(self):
        sourced = {path: set() for path in self._shell}
        changed = True
        while changed:
            changed = False
            for path, fx in self._facts.items():
                before = len(sourced[path])
                for imp in fx.imports:
                    if imp.kind not in ("import", "runs"):
                        continue
                    for target in self._resolve_path(path, imp.spec):
                        sourced[path].add(target)
                        sourced[path].update(sourced.get(target, ()))
                if len(sourced[path]) != before:
                    changed = True
        return sourced

    def resolve(self, path, imp):
        if imp.kind in ("import", "runs"):
            targets = self._resolve_path(path, imp.spec)
            return frozenset(t for t in targets if t in self._shell), None
        if imp.kind == "reference":
            if imp.spec in BUILTINS or imp.spec in COMMON:
                return frozenset(), None
            if imp.spec in self._functions.get(path, ()):
                return frozenset(), None
            for src in self._sourced.get(path, ()):
                if imp.spec in self._functions.get(src, ()):
                    return frozenset(), None
            owners = self._declares.get(imp.spec, [])
            if len(owners) == 1:
                if owners[0] != path:
                    return frozenset({owners[0]}), None
                return frozenset(), None
            if len(owners) > 1:
                return frozenset(), None
            return frozenset(), imp.spec
        return frozenset(), None

    def _resolve_path(self, here, spec):
        if not spec or "$" in spec:
            return frozenset()
        if "/" not in spec:
            matches = self._by_base.get(spec, [])
            return {matches[0]} if len(matches) == 1 else set()
        found = set()
        here_dir = posixpath.dirname(here) or "."
        for base in (here_dir, "."):
            candidate = posixpath.normpath(posixpath.join(base, spec))
            if candidate in self._shell:
                found.add(candidate)
        return found


def resolver(facts, configs, files):
    return Resolver(facts, files)
