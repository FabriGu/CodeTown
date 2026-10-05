"""Which modules matter right now: one module's neighbours, or what a change could break.

Plain data in, plain data out: the renderer decides how to draw it. A focus holds each
module's distance from what's in focus (0 for the module itself) and the import roads to
draw, as (colour, src, dst). Modules missing from the distances are out of focus.
"""

from collections import deque
from dataclasses import dataclass, field

import floor
import langs
from session import CHANGES, DELETE, EDIT, WRITE

USES = "uses"
USED_BY = "used by"
# Brightness by distance from the focus; anything further than NEAR is FAR, unlisted is REST.
NEAR = 1
BRIGHT = 1.0
FAR = 0.72
REST = 0.38


@dataclass(frozen=True)
class Focus:
    kind: str
    distance: dict = field(default_factory=dict)
    roads: tuple = ()


def _imports(model):
    """Repository imports between two different modules, sorted."""
    return sorted((s, d) for s, d in model.edges
                  if s != d and s in model.modules and d in model.modules)


def neighbours(model, module):
    """(modules it imports, modules that import it)."""
    edges = _imports(model)
    return {d for s, d in edges if s == module}, {s for s, d in edges if d == module}


def blast_radius(model, changed):
    """Every module that imports a changed module, directly or through others, by distance:
    0 for the changed modules themselves, 1 for their direct importers, and so on."""
    importers = {}
    for s, d in _imports(model):
        importers.setdefault(d, []).append(s)
    distance = {m: 0 for m in changed if m in model.modules}
    todo = deque(sorted(distance))
    while todo:
        m = todo.popleft()
        for s in importers.get(m, ()):
            if s not in distance:
                distance[s] = distance[m] + 1
                todo.append(s)
    return distance


def changed_by(steps, model):
    """Modules a session changed: successful edits, writes and deletes of a module's file, or
    of a member of a multi-file module. Paths that are no module are ignored."""
    owner = {m.id: m.id for m in model.modules.values()}
    owner.update({path: m.id for m in model.modules.values() for path in m.members})
    return {owner[s.path] for s in steps
            if s.kind in CHANGES and not s.failed and s.path in owner}


def unbuilt(steps, model, tracked):
    """Code files a session wrote that the town has no building for yet, because they aren't
    committed: still there, inside the repository, not tests. Decided from paths alone."""
    owned = set(model.modules) | {p for m in model.modules.values() for p in m.members}
    written, deleted = set(), set()
    for s in steps:
        if s.kind in (EDIT, WRITE) and not s.failed:
            written.add(s.path)
            deleted.discard(s.path)
        elif s.kind == DELETE and not s.failed:
            deleted.add(s.path)
    return sorted(p for p in written - deleted - owned - set(tracked)
                  if not p.startswith(("/", "../")) and not floor.is_test(p)
                  and langs.classify(p, None))


def select(model, module):
    uses, users = neighbours(model, module)
    distance = {m: 1 for m in uses | users}
    distance[module] = 0
    roads = [(USES, module, d) for d in sorted(uses)] + [(USED_BY, s, module) for s in sorted(users)]
    return Focus("select", distance, tuple(roads))


def changed(model, modules):
    distance = blast_radius(model, modules)
    roads = [(USED_BY, s, d) for s, d in _imports(model)
             if s in distance and d in distance and distance[s] == distance[d] + 1]
    return Focus("changed", distance, tuple(roads))


def dim(focus, module):
    """How bright to draw a module: 1 near the focus, less further out, least out of it."""
    d = focus.distance.get(module)
    if d is None:
        return REST
    return BRIGHT if d <= NEAR else FAR
