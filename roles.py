"""Where each source module belongs in town, from what imports what.

The front door is where a run starts; the street is everything it reaches. Scripts are other
entry points. Foundations are imported widely and import nothing. A module no import reaches
from a door or script is named when its name appears in docs, config or code, or it's a
package's public surface, so it is probably loaded by name. Side is what only scripts and named
modules use. An island is reached from none of these: the first place to look for dead code.

Language-neutral: it reads only the survey's facts and model.edges. Plain data in and out.
"""

import os

DOOR = "door"
STREET = "street"
FOUNDATION = "foundation"
SIDE = "side"
SCRIPT = "script"
NAMED = "named"
ISLAND = "island"
STANDALONE = "standalone"
FOUNDATION_MIN_IMPORTERS = 3
TINY_PACKAGE = 5


def buildings(model):
    """{id: Module} for every source module that gets a building: near-empty packages don't."""
    return {m.id: m for m in model.of_kind("source")
            if not (_package(m) and m.loc < TINY_PACKAGE)}


def graph(model, ids):
    """(imports, importers) among ids, each {id: set of ids}, self-imports left out."""
    imports = {m: set() for m in ids}
    importers = {m: set() for m in ids}
    for s, d in model.edges:
        if s != d and s in imports and d in imports:
            imports[s].add(d)
            importers[d].add(s)
    return imports, importers


def roles(model, declared_doors=()):
    """{id: role} for every building; declared doors win over the guess from entry points."""
    src = buildings(model)
    imports, importers = graph(model, src)
    doors = [m for m in declared_doors if m in src] or _guess_door(src, imports)
    street = _reach(imports, doors)
    scripts = {m for m in src if src[m].is_entry and m not in street}
    used = street | _reach(imports, scripts)
    named = {m for m in src if m not in used and (src[m].mentioned or src[m].public)}
    used |= _reach(imports, named)
    found = {}
    for m in src:
        if m in doors:
            found[m] = DOOR
        elif m in scripts:
            found[m] = SCRIPT
        elif len(importers[m]) >= FOUNDATION_MIN_IMPORTERS and not imports[m]:
            found[m] = FOUNDATION
        elif m in street:
            found[m] = STREET
        elif m in named:
            found[m] = NAMED
        elif m in used:
            found[m] = SIDE
        else:
            found[m] = ISLAND
    return found


def script_groups(model, found):
    """{helper: scripts} for scripts that share a helper script; the rest under STANDALONE.

    A helper is a script other scripts import. Each script joins its own group if it is one,
    else the first helper it imports.
    """
    scripts = sorted(m for m, role in found.items() if role == SCRIPT)
    imports, importers = graph(model, scripts)
    helpers = {m for m in scripts if importers[m]}
    groups = {}
    for m in scripts:
        key = m if m in helpers else min(imports[m] & helpers, default=STANDALONE)
        groups.setdefault(key, []).append(m)
    return groups


def _guess_door(src, imports):
    """The most tested entry point, then the one reaching most.

    Reach alone favours whatever imports the tool, such as a helper script or a mock-up.
    """
    entries = sorted(m for m in src if src[m].is_entry)
    if not entries:
        return []
    return [max(entries, key=lambda m: (len(src[m].tested_by), len(_reach(imports, [m]))))]


def _reach(imports, starts):
    seen, todo = set(starts), list(starts)
    while todo:
        for n in imports[todo.pop()]:
            if n not in seen:
                seen.add(n)
                todo.append(n)
    return seen


def _package(m):
    return m.is_package or (m.lang == "python" and os.path.basename(m.id) == "__init__.py")
