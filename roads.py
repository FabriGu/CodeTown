"""Roads: imports routed along the streets, and which of them are drawn.

Problem roads (cycles, backwards imports) are always drawn. Highways (all imports between two
districts) and the selection's own roads are drawn until something is in focus; then the
focus's roads are drawn instead, blue for what it uses and pink for what uses it.
"""

import math
from collections import deque
from dataclasses import dataclass

import layers
import problems
from focus import USED_BY, USES
from townmap import Building, Warehouse

ROAD = "road"
HIGHWAY = "highway"
CYCLE = "cycle"
BACKWARDS = "backwards"
ORDER = [ROAD, HIGHWAY, USES, USED_BY, BACKWARDS, CYCLE]
STEPS = ((1, 0), (0, 1), (-1, 0), (0, -1))
HIGHWAY_GROUND = {"avenue", "quay"}
INTO_DOOR = (0, -1)


@dataclass(frozen=True)
class Road:
    kind: str
    src: str
    dst: str
    path: tuple
    weight: int


def route(tmap, start, goal, ground=None, avoid=frozenset()):
    """Shortest path over walkable tiles; ties break the same way every time."""
    ground = ground or {"street", "avenue", "quay"}
    prev = {tile: tile for tile in avoid if tile not in (start, goal)}
    prev[start] = None
    queue = deque([start])
    while queue:
        tile = queue.popleft()
        if tile == goal:
            path = []
            while tile is not None:
                path.append(tile)
                tile = prev[tile]
            return tuple(reversed(path))
        for dx, dy in STEPS:
            nxt = (tile[0] + dx, tile[1] + dy)
            if nxt not in prev and tmap.kind(*nxt) in ground:
                prev[nxt] = tile
                queue.append(nxt)
    return None


def half_width(kind, weight):
    steps = min(weight - 1, 3) if kind != HIGHWAY else min(int(math.log2(weight)), 4)
    base = {ROAD: 0.12, HIGHWAY: 0.16, USES: 0.12, USED_BY: 0.12, BACKWARDS: 0.17,
            CYCLE: 0.17}[kind]
    return base + 0.05 * steps


class Roads:
    def __init__(self, tmap, model, found):
        self.tmap = tmap
        self.model = model
        loops = layers.cycles(model)
        self.cycle_edges = {(s, d) for s, d in model.edges
                            if any(s in loop and d in loop for loop in loops)}
        self.backwards = {(p.module, p.other) for p in found if p.kind == problems.BACKWARDS}
        self._routes = {}
        self.problem_roads = self._problem_roads()
        self.always = self._highways() + self.problem_roads

    def _route(self, start, goal, ground=None, avoid=frozenset()):
        key = (start, goal, ground is None, avoid)
        if key not in self._routes:
            path = route(self.tmap, start, goal, ground, avoid)
            self._routes[key] = path or (route(self.tmap, start, goal, ground) if avoid else None)
        return self._routes[key]

    def _road(self, kind, src, dst, start, goal, weight, ground=None, avoid=frozenset()):
        path = self._route(start, goal, ground, avoid)
        return [Road(kind, src, dst, path, weight)] if path else []

    def kind_of(self, src, dst):
        if (src, dst) in self.cycle_edges:
            return CYCLE
        if (src, dst) in self.backwards:
            return BACKWARDS
        return ROAD

    def _highways(self):
        totals = {}
        for (src, dst), n in self.model.edges.items():
            a, b = self.model.modules[src].district, self.model.modules[dst].district
            if a != b and a in self.tmap.boxes and b in self.tmap.boxes:
                totals[(a, b)] = totals.get((a, b), 0) + n
        found = []
        for (a, b), n in sorted(totals.items()):
            found += self._road(HIGHWAY, a, b, self.anchor(a), self.anchor(b), n, HIGHWAY_GROUND)
        return found

    def anchor(self, district):
        """The avenue tile in front of the middle of a district."""
        x, y, w, _ = self.tmap.boxes[district]
        end = next(end for start, end in self.tmap.bands if start == y)
        return x + w // 2, end

    def _module_road(self, src, dst, avoid=frozenset(), kind=None):
        b = self.tmap.buildings
        if src not in b or dst not in b:
            return []
        n = self.model.edges[(src, dst)]
        return self._road(kind or self.kind_of(src, dst), src, dst, b[src].front(),
                          b[dst].front(), n, avoid=avoid)

    def _problem_roads(self):
        """Cycle and backwards roads. The return leg of a two-way loop goes round the other way."""
        found = {}
        for src, dst in sorted(self.cycle_edges | self.backwards):
            back = found.get((dst, src))
            avoid = frozenset(back.path[1:-1]) if back else frozenset()
            for road in self._module_road(src, dst, avoid):
                found[(src, dst)] = road
        return list(found.values())

    def focused(self, f):
        """A focus's roads in its own colours. An import that is a problem keeps its own road."""
        found = []
        for kind, src, dst in f.roads:
            if self.kind_of(src, dst) == ROAD:
                found += self._module_road(src, dst, kind=kind)
        return found

    def network(self):
        """Every import as its own road, in its problem kind if it has one, then every road from
        a building to an outside package it uses."""
        found = []
        for src, dst in sorted(self.model.edges):
            found += self._module_road(src, dst)
        for b in sorted(self.tmap.buildings.values(), key=lambda b: b.module):
            found += self.outside(b)
        return found

    def outside(self, thing):
        """Roads from the selected building to the outside packages it uses."""
        found = []
        if isinstance(thing, Building):
            for package, users in sorted(self.model.externals.items()):
                w = self.tmap.warehouses.get(package)
                if w and thing.module in users:
                    found += self._road(ROAD, thing.module, package, thing.front(), w.front(), 1)
        return found

    def of(self, thing):
        """Every road into or out of the selected building or warehouse."""
        found = []
        if isinstance(thing, Building):
            for src, dst in sorted(self.model.edges):
                if thing.module in (src, dst):
                    found += self._module_road(src, dst)
            found += self.outside(thing)
        elif isinstance(thing, Warehouse):
            for user in thing.users:
                b = self.tmap.buildings.get(user)
                if b:
                    found += self._road(ROAD, user, thing.package, b.front(), thing.front(), 1)
        return found

    def visible(self, selected=None, focus=None):
        """Highways, problem roads and the selection's roads; with a focus, the focus's roads
        replace the highways and the selection's own imports."""
        if focus is None:
            roads = self.always + self.of(selected)
        else:
            extra = self.of(selected) if isinstance(selected, Warehouse) else self.outside(selected)
            roads = self.problem_roads + self.focused(focus) + extra
        seen, found = set(), []
        for road in roads:
            key = (road.kind, road.src, road.dst)
            if key not in seen:
                seen.add(key)
                found.append(road)
        return found


def segments(visible):
    """Per tile, what to paint: (kind, weight, directions), quiet roads first."""
    tiles = {}
    for road in sorted(visible, key=lambda r: ORDER.index(r.kind)):
        path = road.path
        for i, tile in enumerate(path):
            dirs = set()
            if i > 0:
                dirs.add((path[i - 1][0] - tile[0], path[i - 1][1] - tile[1]))
            if i + 1 < len(path):
                dirs.add((path[i + 1][0] - tile[0], path[i + 1][1] - tile[1]))
            if road.kind != HIGHWAY and i in (0, len(path) - 1):
                dirs.add(INTO_DOOR)
            tiles.setdefault(tile, []).append((road.kind, road.weight, frozenset(dirs)))
    return tiles


def hidden(tmap, tile):
    """How many of the tiles drawn over this one (front, right, front-right) are built on."""
    x, y = tile
    return sum((x + dx, y + dy) in tmap.at for dx, dy in ((0, 1), (1, 0), (1, 1)))


def roundabouts(tmap, visible):
    """One roundabout per cycle road: the least hidden tile, nearest the road's middle."""
    found = set()
    for road in visible:
        if road.kind == CYCLE:
            middle = len(road.path) // 2
            best = min(range(len(road.path)),
                       key=lambda i: (hidden(tmap, road.path[i]), abs(i - middle), i))
            found.add(road.path[best])
    return found
