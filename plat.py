"""The plat: where every building stands, saved so placement survives each survey.

Districts sit in rows by dependency layer, alphabetical within a row. Inside a
district, lots sit in lines, back to front by module layer and alphabetical
within a layer. Every lot is bottom-aligned so its door faces the street in
front of its line. Each line is filled only to 70% of the district's width; the
rest is free plots for growth. ``by_roles`` lays out a role-based plat that is
never saved.
"""

import json
import math
import os
from dataclasses import asdict, dataclass, field

import roles
from layers import Rows
from townmap import AVENUE, PARK

FREE = 0.3
STREET = 1
SIZES = ((100, 1), (400, 2), (1000, 3))
MAX_SIZE = 4
PARK_SIDE = 7


def footprint(loc):
    """Lot size in tiles, from lines of code: 1x1 up to 4x4."""
    for limit, size in SIZES:
        if loc < limit:
            return size
    return MAX_SIZE


def placed(model):
    """Modules that stand on a lot: everything except tests."""
    return {m.id: m for m in model.modules.values() if m.kind != "test"}


def _overlaps(a, b):
    ax, ay, asize = a
    bx, by, bsize = b
    return ax < bx + bsize and bx < ax + asize and ay < by + bsize and by < ay + asize


@dataclass
class District:
    w: int = 0
    h: int = 0
    lines: list = field(default_factory=list)   # [top, height, layer]
    lots: dict = field(default_factory=dict)    # module -> [x, y, size]
    vacant: list = field(default_factory=list)  # [x, y, size] left by deleted modules

    @classmethod
    def pack(cls, entries, free=FREE, width=None):
        """A fresh district from (module, size, layer) entries sorted by (layer, module).

        free is the share of each line kept for growth; width, if given, replaces the square.
        """
        biggest = max(size for _, size, _ in entries)
        area = sum((size + STREET) ** 2 for _, size, _ in entries)
        width = max(biggest + STREET, width or math.ceil(math.sqrt(area / (1 - free))))
        fill = max(biggest, round(width * (1 - free)))
        d = cls(w=width)
        line = []
        for entry in entries:
            _, size, _ = entry
            if line and d._end(line) + size > fill:
                d._close(line)
                line = []
            line.append(entry)
        d._close(line)
        return d

    def _end(self, line):
        return sum(size + STREET for _, size, _ in line)

    def _close(self, line):
        top, height = self.h, max(size for _, size, _ in line)
        x = 0
        for module, size, _ in line:
            self.lots[module] = [x, top + height - size, size]
            x += size + STREET
        self.lines.append([top, height, line[0][2]])
        self.h = top + height + STREET

    def place(self, module, size, layer):
        """Put a new module on the nearest free plot: its own layer's lines first."""
        best = None
        for i, (top, height, line_layer) in enumerate(self.lines):
            if height < size:
                continue
            front = top + height
            taken = [(x, s) for x, y, s in self.lots.values() if y + s == front]
            for x in range(self.w - size + 1):
                if all(x + size + STREET <= tx or x >= tx + ts + STREET for tx, ts in taken):
                    key = (abs(line_layer - layer), i, x)
                    if best is None or key < best[0]:
                        best = (key, [x, front - size, size])
                    break
        if best is None:
            top = self.h
            self.lines.append([top, size, layer])
            self.h = top + size + STREET
            self.w = max(self.w, size)
            lot = [0, top, size]
        else:
            lot = best[1]
        self.lots[module] = lot
        self.vacant = [v for v in self.vacant if not _overlaps(v, lot)]

    def streets(self):
        """Tiles of this district's streets, relative to its corner."""
        tiles = set()
        every = list(self.lots.values()) + self.vacant
        for top, height, _ in self.lines:
            front = top + height
            tiles.update((x, front) for x in range(self.w))
            for x, y, s in every:
                if y + s == front and x + s < self.w:
                    tiles.update((x + s, row) for row in range(top, front))
        return tiles


class Plat:
    def __init__(self, districts=None, harbor=None, ports=False, order=()):
        self.districts = dict(districts or {})
        self.harbor = list(harbor or [])
        self.ports = ports
        self.order = list(order)  # left to right within a band; unlisted ones follow by name

    def update(self, model, rows):
        here = placed(model)
        where = {m: name for name, d in self.districts.items() for m in d.lots}
        for old, new in sorted(model.renames.items()):
            if old in where and new not in where and new in here \
                    and here[new].district == where[old]:
                d = self.districts[where[old]]
                d.lots[new] = d.lots.pop(old)
                where[new] = where.pop(old)
        for name, d in self.districts.items():
            for module in sorted(d.lots):
                if module not in here or here[module].district != name:
                    d.vacant.append(d.lots.pop(module))
                    where.pop(module)
        new = {}
        for m in sorted(here.values(), key=lambda m: (rows.modules.get(m.id, 0), m.id)):
            if m.id not in where:
                new.setdefault(m.district, []).append(
                    (m.id, footprint(m.loc), rows.modules.get(m.id, 0)))
        for name, entries in sorted(new.items()):
            if name not in self.districts:
                self.districts[name] = District.pack(entries)
                continue
            for module, size, layer in entries:
                self.districts[name].place(module, size, layer)
        self.harbor = [p if p in model.externals else None for p in self.harbor]
        for package in sorted(model.externals):
            if package in self.harbor:
                continue
            if None in self.harbor:
                self.harbor[self.harbor.index(None)] = package
            else:
                self.harbor.append(package)
        return self

    def save(self, path):
        data = {"districts": {n: asdict(d) for n, d in sorted(self.districts.items())},
                "harbor": self.harbor}
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=1, sort_keys=True)

    @classmethod
    def load(cls, path):
        if not os.path.exists(path):
            return cls()
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return cls({n: District(**d) for n, d in data["districts"].items()}, data["harbor"])


def by_roles(model, rows):
    """A plat laid out by role instead of folder, and the band each district stands in.

    Town Hall stands in a park at the centre, the repository's own square. The code that runs
    flanks it: the front door with the first half of the main street on one side, the rest on
    the other, split by area so both sides weigh the same. Behind it are the foundations and
    what only scripts use; in front, scripts grouped by the helper they share; then what no
    import reaches, and unsurveyed files at the front edge.

    Laid out afresh on every run and never saved, so it keeps no room for growth, and every band
    runs the full width, the park or a band's last district taking up the slack, instead of
    leaving open land beside it.
    Names start with "/" so no folder can share one, and no district highway finds them.
    """
    found = roles.roles(model)
    _, importers = roles.graph(model, found)

    def of(*kinds):
        return sorted(m for m, role in found.items() if role in kinds)

    area = lambda m: (footprint(model.modules[m].loc) + STREET) ** 2
    door, rest = of(roles.DOOR), of(roles.STREET)
    left, right = list(door), []
    for m in sorted(rest, key=lambda m: (-area(m), m)):
        (left if sum(map(area, left)) <= sum(map(area, right)) else right).append(m)
    by_layer = lambda m: (m not in door, -rows.modules.get(m, 0), m)
    groups = [(2, "/standalone scripts" if key == roles.STANDALONE else f"/scripts/{key}",
               sorted(members, key=lambda m: (m != key, m)))
              for key, members in sorted(roles.script_groups(model, found).items())]
    order = [(0, "/foundations",
              sorted(of(roles.FOUNDATION), key=lambda m: (-len(importers[m]), m)) + of(roles.SIDE)),
             (1, "/front door", sorted(left, key=by_layer)),
             (1, PARK, []),
             (1, "/main street", sorted(right, key=by_layer)),
             *groups,
             (3, "/named", of(roles.NAMED)),
             (3, "/islands", of(roles.ISLAND)),
             (4, "/unsurveyed", sorted(m.id for m in model.of_kind("unsurveyed")))]
    entries = {name: [(m, footprint(model.modules[m].loc), 0) for m in members]
               for _, name, members in order if members}
    bands = {name: band for band, name, members in order if members or name == PARK}
    districts = {name: District.pack(e, free=0) for name, e in entries.items()}
    side = max([PARK_SIDE] + [districts[n].h for n, b in bands.items() if b == 1 and n != PARK])
    side += 1 - side % 2  # odd, so the plaza sits in the middle
    districts[PARK] = District(w=side, h=side)
    for name in ("/front door", "/main street"):
        if name in entries:
            districts[name] = District.pack(entries[name], free=0, width=math.ceil(
                sum((s + STREET) ** 2 for _, s, _ in entries[name]) / side))
    across = {}
    for name, band in bands.items():
        across.setdefault(band, []).append(name)
    span = lambda names: sum(districts[n].w for n in names) + AVENUE * (len(names) - 1)
    widest = max(map(span, across.values()))
    for names in across.values():
        slack = widest - span(names)
        if PARK in names:
            districts[PARK].w += slack
        elif slack:
            last = names[-1]
            districts[last] = District.pack(entries[last], free=0,
                                            width=districts[last].w + slack)
    return (Plat(districts, sorted(model.externals), ports=True,
                 order=[name for _, name, _ in order]), Rows(bands))
