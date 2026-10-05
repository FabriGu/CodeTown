"""The town as tiles: ground, buildings, plots, warehouses and props.

Back to front: open water, a harbor of warehouses, the quay, then rows of
districts separated by avenues, then a grass margin at the island's front edge.
Laid out by role, each warehouse instead docks on the edge nearest the files that import it.
"site": the place a new file will stand
"""

from dataclasses import dataclass

import cake
import problems
from render import hash2

MARGIN = 2
AVENUE = 2
WATER_ROWS = 2
WAREHOUSE = 2
DOCK_STEP = WAREHOUSE + 1
QUAY = WATER_ROWS + WAREHOUSE
TOWN_TOP = QUAY + 1 + AVENUE
SHADOW = 3
TREE_CHANCE = 4
MAX_HEIGHT = 90
SITE_STEP = 2
WALKABLE = {"street", "avenue", "quay"}
PARK = "/park"
PLAZA = 1


@dataclass(frozen=True)
class Building:
    module: str
    district: str
    x: int
    y: int
    size: int
    stack: tuple
    tested: bool
    problems: frozenset
    churn: int
    entry: bool
    functions: tuple = ()

    @property
    def floors(self):
        return len(self.stack)

    def door(self):
        return self.x + (self.size - 1) // 2, self.y + self.size - 1

    def front(self):
        x, y = self.door()
        return x, y + 1

    def tiles(self):
        return [(self.x + i, self.y + j) for j in range(self.size) for i in range(self.size)]


@dataclass(frozen=True)
class Warehouse:
    package: str
    x: int
    y: int
    users: tuple
    size: int = WAREHOUSE
    facing: tuple = (0, 1)

    def front(self):
        """The walkable tile its roads arrive at, on the side it faces."""
        dx, dy = self.facing
        mid = (self.size - 1) // 2
        if dx:
            return (self.x + self.size if dx > 0 else self.x - 1), self.y + mid
        return self.x + mid, (self.y + self.size if dy > 0 else self.y - 1)

    def tiles(self):
        return [(self.x + i, self.y + j) for j in range(self.size) for i in range(self.size)]


def stack(module, size):
    """The building's cake tiers, no taller than MAX_HEIGHT; code that won't parse is one tier."""
    functions = [] if module.parse_error else module.functions
    return squash(cake.tiers(functions, size, module.complexity), MAX_HEIGHT)


def squash(tiers, limit):
    """Tiers scaled to stand at most limit pixels tall. A tier squashed to nothing joins the
    one below it, and passes on its amber."""
    top = tiers[-1].z1
    if top <= limit:
        return tuple(tiers)
    found = []
    for t in tiers:
        z1 = t.z1 * limit // top
        if found and z1 <= found[-1].z1:
            last = found[-1]
            found[-1] = cake.Tier(last.half, last.z0, last.z1, last.amber or t.amber)
        else:
            found.append(cake.Tier(t.half, found[-1].z1 if found else 0, max(1, z1), t.amber))
    return tuple(found)


class TownMap:
    def __init__(self, model, plat, rows, found, sites=()):
        self.model = model
        self.problems = {}
        for p in found:
            self.problems.setdefault(p.module, []).append(p)
        self.ground = {}
        self.buildings = {}
        self.plots = {}
        self.vacant = []
        self.warehouses = {}
        self.boxes = {}
        self.props = {}
        self.wear = {}
        self.hot = set()
        self.shadow = set()
        self.trees = set()
        self.sites = {}
        self.hall = None
        self._arrange(plat, rows)
        self._sites(sites)
        self._harbor(plat)
        self._avenues()
        self._districts(plat)
        if PARK in self.boxes:
            self._park()
        if plat.ports:
            self._shore()
            self._ports(plat)
        self._surroundings()
        self.at = {}
        for b in list(self.buildings.values()) + list(self.warehouses.values()):
            for tile in b.tiles():
                self.at[tile] = b

    def _arrange(self, plat, rows):
        rank = {n: i for i, n in enumerate(plat.order)}
        order = sorted(plat.districts,
                       key=lambda n: (rows.districts.get(n, 0), rank.get(n, len(rank)), n))
        self.bands = []
        y = TOWN_TOP
        for layer in sorted({rows.districts.get(n, 0) for n in order}):
            x, height = MARGIN + AVENUE, 0
            for name in (n for n in order if rows.districts.get(n, 0) == layer):
                d = plat.districts[name]
                self.boxes[name] = (x, y, d.w, d.h)
                x += d.w + AVENUE
                height = max(height, d.h)
            self.bands.append((y, y + height))
            y += height + AVENUE
        self.right = max([x + w for x, _, w, _ in self.boxes.values()] or [MARGIN + AVENUE])
        if not plat.ports:
            self.right = max(self.right, MARGIN + AVENUE + len(plat.harbor) * DOCK_STEP)
        self.bottom = y
        self.width = self.right + AVENUE + MARGIN
        self.height = self.bottom + MARGIN

    def _sites(self, paths):
        """A one-tile construction site per new file, in rows along the island's front edge."""
        x0 = MARGIN + AVENUE
        per_row = max(1, (self.right - x0) // SITE_STEP)
        for i, path in enumerate(paths):
            x, y = x0 + i % per_row * SITE_STEP, self.bottom + i // per_row * SITE_STEP
            self.sites[path] = (x, y)
            self.ground[(x, y)] = "site"
        if paths:
            self.height = self.bottom + (len(paths) - 1) // per_row * SITE_STEP + 1 + MARGIN

    def _harbor(self, plat):
        for x in range(self.width):
            for y in range(QUAY):
                self.ground[(x, y)] = "water"
            self.ground[(x, QUAY)] = "quay"
        for i, package in enumerate([] if plat.ports else plat.harbor):
            if package is None:
                continue
            w = Warehouse(package, MARGIN + AVENUE + i * DOCK_STEP, WATER_ROWS,
                          tuple(self.model.externals.get(package, ())))
            self.warehouses[package] = w
            for tile in w.tiles():
                self.ground[tile] = "dock"

    def _park(self):
        """Paths cross the park from each avenue to a plaza in its middle, where Town Hall stands."""
        bx, by, w, h = self.boxes[PARK]
        cx, cy = bx + w // 2, by + h // 2
        for x in range(bx, bx + w):
            self.ground[(x, cy)] = "street"
        for y in range(by, by + h):
            self.ground[(cx, y)] = "street"
        for x in range(cx - PLAZA, cx + PLAZA + 1):
            for y in range(cy - PLAZA, cy + PLAZA + 1):
                self.ground[(x, y)] = "street"
        self.hall = (cx, cy)

    def _shore(self):
        """The margin outside the avenues is sea, so the ports stand in water off the waterfront.
        Construction sites past the front keep their grass."""
        xs = range(MARGIN, self.right + AVENUE)
        ys = range(TOWN_TOP - AVENUE, self.height - MARGIN if self.sites else self.bottom)
        for x in range(self.width):
            for y in range(QUAY + 1, self.height):
                if (x, y) not in self.ground and not (x in xs and y in ys):
                    self.ground[(x, y)] = "water"

    def _ports(self, plat):
        """Each outside package docks on the island's edge nearest the files that import it,
        most-imported first, a tile apart, facing the avenue or quay its roads arrive by."""
        span = range(self.width - WAREHOUSE + 1)
        sides = range(QUAY + 1, self.height - WAREHOUSE + 1)
        slots = ([(x, WATER_ROWS, (0, 1)) for x in span]
                 + [(0, y, (1, 0)) for y in sides]
                 + [(self.width - WAREHOUSE, y, (-1, 0)) for y in sides]
                 + [(x, self.height - WAREHOUSE, (0, -1)) for x in span])
        slots = [Warehouse("", x, y, (), facing=f) for x, y, f in slots]
        slots = [w for w in slots if self.walkable(*w.front())
                 and all(self.kind(*t) in ("grass", "water") for t in w.tiles())]
        users = {p: tuple(self.model.externals.get(p, ())) for p in plat.harbor if p}
        for package in sorted(users, key=lambda p: (-len(users[p]), p)):
            mids = [c for c in map(self.centre, users[package]) if c]
            cx = sum(x for x, _ in mids) / len(mids) if mids else self.width / 2
            cy = sum(y for _, y in mids) / len(mids) if mids else 0
            free = [w for w in slots if all(max(abs(w.x - o.x), abs(w.y - o.y)) >= DOCK_STEP
                                            for o in self.warehouses.values())]
            if not free:
                break
            w = min(free, key=lambda w: (w.x + 1 - cx) ** 2 + (w.y + 1 - cy) ** 2)
            self.warehouses[package] = Warehouse(package, w.x, w.y, users[package],
                                                 facing=w.facing)
            for tile in w.tiles():
                self.ground[tile] = "dock"

    def _avenues(self):
        left, top = MARGIN, TOWN_TOP - AVENUE
        rows = [range(top, TOWN_TOP)] + [range(end, end + AVENUE) for _, end in self.bands]
        for band in rows:
            for y in band:
                for x in range(left, self.right + AVENUE):
                    self.ground[(x, y)] = "avenue"
        sides = list(range(left, left + AVENUE)) + list(range(self.right, self.right + AVENUE))
        for y in range(top, self.bottom):
            for x in sides:
                self.ground[(x, y)] = "avenue"
        for bx, by, bw, _ in self.boxes.values():
            band_end = next(end for start, end in self.bands if start == by)
            for y in range(by, band_end):
                for x in range(bx + bw, bx + bw + AVENUE):
                    self.ground[(x, y)] = "avenue"

    def _districts(self, plat):
        for name, d in plat.districts.items():
            bx, by, _, _ = self.boxes[name]
            for x, y in d.streets():
                self.ground[(bx + x, by + y)] = "street"
            for x, y, size in d.vacant:
                self.vacant.append((bx + x, by + y, size))
                for i in range(size):
                    for j in range(size):
                        self.ground[(bx + x + i, by + y + j)] = "vacant"
            for module, (x, y, size) in d.lots.items():
                self._lot(self.model.modules[module], bx + x, by + y, size)

    def _lot(self, m, x, y, size):
        for i in range(size):
            for j in range(size):
                self.ground[(x + i, y + j)] = "lot" if m.kind == "source" else "plot"
        if m.kind != "source":
            self.plots[m.id] = (x, y, size)
            return
        kinds = frozenset(p.kind for p in self.problems.get(m.id, ()))
        b = Building(m.id, m.district, x, y, size, stack(m, size), bool(m.tested_by), kinds,
                     m.churn, m.is_entry, tuple(m.functions))
        self.buildings[m.id] = b
        if m.is_entry:
            self.props.setdefault(b.front(), []).append("gate")
        if problems.TOWER in kinds:
            self.shadow.update((x + size + i, y + j) for i in range(SHADOW) for j in range(size))

    def _surroundings(self):
        for b in self.buildings.values():
            for p in self.problems.get(b.module, ()):
                if p.kind == problems.BACKWARDS:
                    self.props.setdefault(b.front(), []).append("no entry")
                if p.kind == problems.NOTES:
                    self.props.setdefault(b.front(), []).append("notes")
            for x in range(b.x - 1, b.x + b.size + 1):
                for y in range(b.y - 1, b.y + b.size + 1):
                    if self.ground.get((x, y)) in WALKABLE:
                        self.wear[(x, y)] = max(self.wear.get((x, y), 0), b.churn)
                        if problems.HOTSPOT in b.problems:
                            self.hot.add((x, y))
        for tile in self.props:
            self.props[tile] = sorted(set(self.props[tile]))
        inside = set()
        for bx, by, bw, bh in self.boxes.values():
            inside.update((x, y) for x in range(bx, bx + bw) for y in range(by, by + bh))
        cleared = set()  # no trees in front of a construction site
        for x, y in self.sites.values():
            cleared.update(((x, y + 1), (x + 1, y), (x + 1, y + 1)))
        for y in range(self.height):
            for x in range(self.width):
                if (x, y) in cleared:
                    continue
                chance = TREE_CHANCE * (2 if (x, y) in inside else 1)
                if self.kind(x, y) == "grass" and hash2(x, y, 11) % chance == 0:
                    self.trees.add((x, y))
        self.bushes = {t for t in self.trees if t in inside}

    def kind(self, x, y):
        return self.ground.get((x, y), "grass")

    def walkable(self, x, y):
        return self.kind(x, y) in WALKABLE

    def thing_at(self, x, y):
        """What the cursor is on: a Building, Warehouse, plot, site, vacant lot, or None."""
        if (x, y) in self.at:
            return self.at[(x, y)]
        for module, (px, py, size) in self.plots.items():
            if px <= x < px + size and py <= y < py + size:
                return ("plot", module)
        for path, tile in self.sites.items():
            if tile == (x, y):
                return ("site", path)
        for vx, vy, size in self.vacant:
            if vx <= x < vx + size and vy <= y < vy + size:
                return ("vacant", None)
        return None

    def centre(self, module):
        if module in self.buildings:
            b = self.buildings[module]
            return b.x + b.size // 2, b.y + b.size // 2
        if module in self.plots:
            x, y, size = self.plots[module]
            return x + size // 2, y + size // 2
        return None
