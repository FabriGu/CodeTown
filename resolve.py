"""Map Python imports to files in the repository, or to outside packages."""

import sys

STDLIB = set(sys.stdlib_module_names) | {"__future__"}


def dotted_parts(path):
    parts = path[:-3].split("/")
    return parts[:-1] if parts[-1] == "__init__" else parts


def _shared(a, b):
    n = 0
    for x, y in zip(a, b):
        if x != y:
            break
        n += 1
    return n


class Resolver:
    def __init__(self, py_paths, known_external=()):
        self.known_external = set(known_external)
        self._full = {}
        self._by_suffix = {}
        for path in sorted(py_paths):
            parts = dotted_parts(path)
            if not parts:
                continue
            self._full.setdefault(".".join(parts), path)
            for k in range(1, len(parts) + 1):
                self._by_suffix.setdefault(".".join(parts[-k:]), []).append(path)

    def resolve(self, importer, imp):
        """Return (repo paths the import reaches, outside package name or None)."""
        if imp.level:
            return self._relative(importer, imp), None
        top = imp.module.split(".")[0]
        if top in STDLIB:
            return set(), None
        if top in self.known_external:
            return set(), top
        targets = set()
        if imp.names:
            package = None
            for name in imp.names:
                sub = self._pick(importer, f"{imp.module}.{name}") if name != "*" else None
                if sub:
                    targets.add(sub)
                elif package is None:
                    package = self._longest(importer, imp.module)
            if package:
                targets.add(package)
        else:
            found = self._longest(importer, imp.module)
            if found:
                targets.add(found)
        return (targets, None) if targets else (set(), top)

    def _longest(self, importer, dotted):
        parts = dotted.split(".")
        while parts:
            found = self._pick(importer, ".".join(parts))
            if found:
                return found
            parts.pop()
        return None

    def _pick(self, importer, dotted):
        candidates = self._by_suffix.get(dotted)
        if not candidates:
            return None
        here = importer.split("/")[:-1]

        def closeness(path):
            there = path.split("/")[:-1]
            return (there != here, -_shared(here, there), len(path), path)

        return min(candidates, key=closeness)

    def _relative(self, importer, imp):
        base = importer.split("/")[:-1]
        up = imp.level - 1
        if up > len(base):
            return set()
        base = base[:len(base) - up]
        prefix = base + (imp.module.split(".") if imp.module else [])
        targets = set()
        for name in imp.names:
            sub = self._full.get(".".join(prefix + [name]))
            package = self._full.get(".".join(prefix))
            if sub:
                targets.add(sub)
            elif package:
                targets.add(package)
        return targets
