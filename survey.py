"""Survey a repository into a Model. Every read goes through repo.Repo.

A file is read in full by its language's adapter when that adapter and its grammars
are installed, and from its lines alone (floor depth) when they aren't. Adapters
only ever see paths and text.
"""

import os
import re

import floor
import langkit
import langs
from model import Model, Module
from repo import Repo

TEXT = {".py", ".md", ".txt", ".toml", ".yml", ".yaml", ".json", ".cfg", ".ini", ".sh",
        ".html", ".js", ".mjs", ".rst", ".xml", ".gradle", ".properties", ".mk", ".cmake"}
TEXT_NAMES = {"Dockerfile", "Makefile", "Procfile", "Justfile", "Rakefile", "Gemfile"}
SKIP_DIRS = {"vendor", "node_modules"}
TOKEN = re.compile(r"[A-Za-z0-9_./@-]+")
MENTION_CAP = 64


def district_of(unit):
    if unit == "./":
        return "(root)"
    parts = unit.split("/")
    return parts[0] if len(parts) > 1 else "(root)"


def is_vendored(path):
    return any(p in SKIP_DIRS for p in path.split("/")[:-1])


class _Survey:
    def __init__(self, root):
        self.repo = Repo(root)
        self.files = [f for f in self.repo.files() if not is_vendored(f)]
        self.file_set = frozenset(self.files)
        self.texts = {}
        self.adapters = langs.adapters()
        self.model = Model(repo=os.path.basename(self.repo.root))
        self.lang_of = {}
        self.facts = {}
        self.floor = {}
        self.unread = []
        self.tests = set()
        self.unit_of = {}
        self.members = {}
        self.configs = {}

    def text(self, path):
        if path not in self.texts:
            self.texts[path] = self.repo.read_text(path)
        return self.texts[path]

    def run(self):
        for f in self.files:
            if (os.path.splitext(f)[1] in TEXT or os.path.basename(f) in TEXT_NAMES
                    or langs.is_config(f)):
                self.text(f)
        self._classify()
        self.full = {key for key in set(self.lang_of.values())
                     if key in self.adapters and langs.depth_reason(key) is None}
        self._read()
        churn = self.repo.churn()
        self._full_modules(churn)
        self._floor_modules(churn)
        for f in self.unread:
            self.model.modules[f] = Module(id=f, district=district_of(f), kind="unsurveyed",
                                           lang=self.lang_of[f], churn=churn.get(f, 0))
        self.model.renames = {old: new for old, new in self.repo.renames().items()
                              if new in self.model.modules and old not in self.model.modules}
        self._connect()
        self._named_tests()
        self._mentions()
        for m in self.model.modules.values():
            m.tested_by.sort()
        return self.model

    def _classify(self):
        for f in self.files:
            if langs.is_config(f):
                continue
            ext = os.path.splitext(f)[1]
            key = langs.classify(f, None if ext else self.text(f))
            if key:
                self.lang_of[f] = key

    def _read(self):
        for f, key in sorted(self.lang_of.items()):
            text = self.text(f)
            if text is None:
                self.unread.append(f)
                continue
            adapter = self.adapters.get(key)
            if key != "python" and floor.is_minified(text):
                continue
            excluded = getattr(adapter, "is_excluded", None)
            if excluded is not None and excluded(f, text):
                continue
            if key not in self.full:
                self.floor[f] = key
                continue
            grammar = langs.grammar_for(adapter, f, self.file_set)
            tree = langkit.parse(grammar, text) if grammar else None
            self.facts[f] = adapter.scan(f, text, tree)
        files = tuple(self.files)
        for key in sorted(self.full):
            adapter = self.adapters[key]
            facts = {p: fx for p, fx in self.facts.items() if self.lang_of[p] == key}
            configs = self.configs[key] = {p: self.text(p)
                                           for p in langs.configs_of(adapter, self.files)}
            if not facts:
                continue
            enrich = getattr(adapter, "enrich", None)
            if enrich is not None:
                enrich(facts, configs, files)
            test_files = getattr(adapter, "test_files", None)
            declared = set(test_files(configs, files)) if test_files is not None else set()
            for f in sorted(facts):
                if f in declared or adapter.is_test(f, self.text(f)):
                    self.tests.add(f)
                    self.unit_of[f] = f
                else:
                    unit = adapter.unit_of(f, self.file_set)
                    self.unit_of[f] = unit
                    self.members.setdefault(unit, []).append(f)

    def _full_modules(self, churn):
        for f in sorted(self.tests):
            fx, key = self.facts[f], self.lang_of[f]
            self.model.modules[f] = Module(
                id=f, district=district_of(f), kind="test", loc=fx.loc,
                complexity=fx.complexity, exports=list(fx.exports), notes=fx.notes,
                is_entry=fx.is_entry, parse_error=fx.parse_error, churn=churn.get(f, 0),
                lang=key, burns=langs.fire_allowed(self.adapters[key], f),
                functions=list(fx.functions))
        for unit, paths in sorted(self.members.items()):
            paths = sorted(paths)
            fxs = [self.facts[p] for p in paths]
            key = self.lang_of[paths[0]]
            multi = unit not in paths or len(paths) > 1
            if unit in paths:
                exports = list(self.facts[unit].exports)
            else:
                exports = sorted({name for fx in fxs for name in fx.exports})
            broken = next((p for p in paths if self.facts[p].parse_error), None)
            error = self.facts[broken].parse_error if broken else None
            if broken and multi:
                error = f"{os.path.basename(broken)}: {error}"
            self.model.modules[unit] = Module(
                id=unit, district=district_of(unit), kind="source",
                loc=sum(fx.loc for fx in fxs), complexity=sum(fx.complexity for fx in fxs),
                exports=exports, notes=sum(fx.notes for fx in fxs),
                is_entry=any(fx.is_entry for fx in fxs), parse_error=error,
                churn=sum(churn.get(p, 0) for p in paths), lang=key,
                is_package=any(fx.is_package for fx in fxs),
                public=any(fx.public for fx in fxs),
                inline_tests=any(fx.inline_tests for fx in fxs),
                burns=langs.fire_allowed(self.adapters[key], broken) if broken else True,
                members=paths if multi else [],
                functions=[f for fx in fxs for f in fx.functions])

    def _floor_modules(self, churn):
        for f, key in sorted(self.floor.items()):
            text = self.text(f)
            loc, complexity, notes = floor.facts(f, text)
            adapter = self.adapters.get(key)
            test = adapter.is_test(f, text) if adapter is not None else floor.is_test(f)
            self.model.modules[f] = Module(
                id=f, district=district_of(f), kind="test" if test else "source", loc=loc,
                complexity=complexity, notes=notes, churn=churn.get(f, 0), lang=key,
                depth="floor")

    def _connect(self):
        externals = {}
        for key in sorted(self.full):
            adapter = self.adapters[key]
            facts = {p: fx for p, fx in self.facts.items() if self.lang_of[p] == key}
            if not facts:
                continue
            resolver = adapter.resolver(facts, self.configs[key], tuple(self.files))
            tests_for = getattr(adapter, "tests_for", None)
            for f, fx in sorted(facts.items()):
                here = self.unit_of[f]
                is_test = f in self.tests
                for imp in fx.imports:
                    targets, outside = resolver.resolve(f, imp)
                    for unit in self._source_units(targets, here):
                        if is_test:
                            self._tested(unit, f)
                        else:
                            self.model.edges[(here, unit)] = self.model.edges.get(
                                (here, unit), 0) + 1
                    if outside and not is_test:
                        externals.setdefault(outside, set()).add(here)
                if is_test and tests_for is not None:
                    for unit in self._source_units(tests_for(f, facts, tuple(self.files)), here):
                        self._tested(unit, f)
        self.model.externals = {k: sorted(v) for k, v in sorted(externals.items())}

    def _source_units(self, paths, here):
        units = set()
        for p in paths:
            unit = self.unit_of.get(p)
            target = self.model.modules.get(unit) if unit else None
            if target is not None and target.kind == "source" and unit != here:
                units.add(unit)
        return sorted(units)

    def _tested(self, unit, test):
        tested_by = self.model.modules[unit].tested_by
        if test not in tested_by:
            tested_by.append(test)

    def _named_tests(self):
        modules = self.model.modules
        python = self.adapters["python"]
        py_sources = [m.id for m in self.model.of_kind("source") if m.lang == "python"]
        py_tests = [m.id for m in self.model.of_kind("test") if m.lang == "python"]
        for unit, tests in python.named_tests(py_sources, py_tests, self.texts).items():
            for t in tests:
                self._tested(unit, t)
        sources, tests = {}, {}
        for f, key in self.lang_of.items():
            if key == "python":
                continue
            unit = self.unit_of.get(f, f if f in self.floor else None)
            module = modules.get(unit) if unit else None
            if module is None:
                continue
            if module.kind == "source":
                sources[f] = key
            elif module.kind == "test":
                tests[f] = key
        for test, source in floor.pair_tests(tests, sources).items():
            self._tested(self.unit_of.get(source, source), test)

    def _mentions(self):
        python = self.adapters["python"]
        units = [m for m in self.model.of_kind("source") if m.depth == "full"]
        found = python.mentioned([m.id for m in units if m.lang == "python"], self.texts)
        others = [m for m in units if m.lang != "python"]
        if others:
            index = self._token_index()
            for m in others:
                adapter = self.adapters[m.lang]
                hook = getattr(adapter, "mention_tokens", None)
                tokens = hook(m.id) if hook is not None else _default_tokens(m.id)
                own = set(m.members) | {m.id}
                for token in tokens:
                    paths = index.get(token, ())
                    if len(paths) >= MENTION_CAP or any(p not in own for p in paths):
                        found.add(m.id)
                        break
        for m in units:
            m.mentioned = m.id in found

    def _token_index(self):
        index = {}
        for path, text in sorted(self.texts.items()):
            if not text:
                continue
            seen = set()
            for raw in TOKEN.findall(text):
                for token in _variants(raw):
                    if token in seen:
                        continue
                    seen.add(token)
                    paths = index.setdefault(token, [])
                    if len(paths) < MENTION_CAP:
                        paths.append(path)
        return index


def _variants(token):
    bare = token.strip(".-/")
    found = {token, bare}
    if "/" in bare:
        found.add(bare.rsplit("/", 1)[1])
    if bare.startswith("./"):
        found.add(bare[2:])
    found.discard("")
    return found


def _default_tokens(unit):
    if unit.endswith("/"):
        bare = unit.rstrip("/")
        return {bare} if bare and bare != "." else set()
    return {unit, os.path.basename(unit)}


def survey(root):
    return _Survey(root).run()
