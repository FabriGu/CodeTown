"""Where the work is: problems in a surveyed model, worst first."""

import os
from dataclasses import dataclass

import layers

FIRE = "won't parse"
CYCLE = "import cycle"
BACKWARDS = "backwards road"
HOTSPOT = "hotspot"
TOWER = "tower"
ABANDONED = "abandoned"
UNTESTED = "untested"
ALL_DOORS = "all doors"
NOTES = "notes left"
UNSURVEYED = "unsurveyed"
KINDS = [FIRE, CYCLE, BACKWARDS, HOTSPOT, TOWER, ABANDONED, UNTESTED, ALL_DOORS, NOTES,
         UNSURVEYED]

TOWER_LOC = 2000
TOWER_COMPLEXITY = 200
HOTSPOT_PERCENT = 5
HOTSPOT_MIN_CHURN = 3
ALL_DOORS_MIN_EXPORTS = 6
LINES_PER_DOOR = 10


@dataclass(frozen=True)
class Problem:
    kind: str
    module: str
    reason: str
    other: str | None = None


def find(model, rows):
    sources = model.of_kind("source")
    importers = model.importers()
    found = []
    for m in sources:
        if m.parse_error and m.burns:
            found.append(Problem(FIRE, m.id, m.parse_error))
    for loop in layers.cycles(model):
        for member in loop:
            found.append(Problem(CYCLE, member, f"in an import loop of {len(loop)} modules"))
    for src, dst in sorted(model.edges):
        if rows.is_backwards(model, src, dst):
            found.append(Problem(BACKWARDS, src, f"reaches forward to {dst}", other=dst))
    found += _hotspots([m for m in sources if m.depth == "full"])
    for m in sources:
        package = m.is_package or (m.lang == "python" and os.path.basename(m.id) == "__init__.py")
        if m.loc >= TOWER_LOC or m.complexity >= TOWER_COMPLEXITY:
            found.append(Problem(TOWER, m.id, f"{m.loc} lines, complexity {m.complexity}"))
        if (m.depth == "full" and not package and not importers.get(m.id) and not m.is_entry
                and not m.mentioned and not m.public):
            found.append(Problem(ABANDONED, m.id, "nothing imports it"))
        if not package and m.loc and not m.tested_by and not m.inline_tests:
            found.append(Problem(UNTESTED, m.id, _untested_reason(m)))
        doors = len(m.exports)
        if doors >= ALL_DOORS_MIN_EXPORTS and m.loc < doors * LINES_PER_DOOR:
            found.append(Problem(ALL_DOORS, m.id, f"{doors} exports over {m.loc} lines"))
        if m.notes:
            found.append(Problem(NOTES, m.id, f"{m.notes} TODO or FIXME note"
                                 + ("s" if m.notes > 1 else "")))
    for m in model.of_kind("unsurveyed"):
        found.append(Problem(UNSURVEYED, m.id, UNREADABLE))
    return sorted(found, key=lambda x: (KINDS.index(x.kind), x.module, x.other or ""))


UNREADABLE = "unreadable: symlink, binary, over 1 MB or not UTF-8"


def _untested_reason(m):
    if m.depth == "floor":
        return "no test found for it by name"
    return "no test imports it" if m.lang == "python" else "no test reaches it"


def _hotspots(sources):
    """The top few by churn times complexity: code that is both busy and complicated.

    Each language counts complexity its own way, so each is ranked against itself. The
    floor's complexity is only a keyword count, so floor buildings are never ranked. Only
    the repository's main language is promised a hotspot, or a lone script would get one.
    """
    by_lang = {}
    for m in sources:
        by_lang.setdefault(m.lang, []).append(m)
    main = min(by_lang, key=lambda lang: (-len(by_lang[lang]), lang), default=None)
    found = []
    for lang in sorted(by_lang):
        group = by_lang[lang]
        top = len(group) * HOTSPOT_PERCENT // 100
        if lang == main:
            top = max(1, top)
        eligible = [m for m in group if m.churn >= HOTSPOT_MIN_CHURN and m.complexity > 0]
        ranked = sorted(eligible, key=lambda m: (-m.churn * m.complexity, m.id))[:top]
        found += [Problem(HOTSPOT, m.id,
                          f"changed in {m.churn} commits in 90 days, complexity {m.complexity}")
                  for m in ranked]
    return found
