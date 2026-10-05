"""Mock-up: the town laid out by role, each building split into its functions.

    uv run --with-requirements requirements.txt --with pillow python3 mock_roles.py PATH OUT.png [FOCUS] [flat] [watch]

No roads are drawn by default. FOCUS is one of:
  select:MODULE        what one module uses and what uses it
  changed:MODULE[,..]  everything that depends on the changed modules, directly or through others
  session[:TRANSCRIPT] the same for the modules an agent session changed; the newest Claude Code
                       or Cursor transcript for PATH unless one is named. New code files it wrote
                       that aren't committed yet show as orange sites along the front.
"flat" draws every building as a low block, the way a minimap would.
"watch" opens OUT.png and keeps it up to date with the session (the default FOCUS) until Ctrl-C.

A throwaway exploration to compare against the current town, not part of
towncode. It only reads the repository and changes none of the town's modules.
"""

import heapq
import json
import math
import os
import re
import shutil
import subprocess
import sys
import time
import tomllib

from PIL import Image, ImageDraw, ImageFont

import cake
import focus
import iso
import problems
import roads as R
import roles
import session
import survey
from drawtown import BOARD, DARK, LIT, _on_road
from layers import Rows
from plat import footprint
from render import LOCAL, Framebuffer, ground_color, mix, shade
from repo import Repo
from resolve import Resolver

SEA = (30, 66, 112)
GRAY = (150, 150, 156)
AMBER = (236, 160, 40)
WALL = (224, 222, 216)
ROOFS = [(70, 140, 120), (84, 108, 170), (132, 104, 156), (150, 92, 76)]
MAX_FADE = 0.65
GROUP_COLUMNS = 3
SCALE = 4
TOP_ROOM = 90
STREET_COST, GRASS_COST = 1, 4
FLAT_HEIGHT = 3
SITE = (232, 128, 48)
SITE_WIDTH = 0.7
SITE_HEIGHT = 3
SITE_COLUMNS = 6
WATCH_SECONDS = 2
MAX_PORTS = 8
PORT_GAP = 3
PORT_HEIGHT = 5
PORT_HALF = 6
PORT_WALL = (122, 136, 152)
PORT_ROOF = (86, 92, 104)
PIER = (150, 112, 74)
PORT_LABEL = (150, 200, 235)
MAX_ROW_TILES = 48
BUILD_DIRS = ("dist", "build", "out", "lib")
JS_SOURCE_EXTS = [".ts", ".tsx", ".mts", ".cts", ".js", ".jsx", ".mjs", ".cjs"]
SCRIPT_TAG = re.compile(r"<script\b[^>]*>")
SCRIPT_SRC = re.compile(r'\bsrc="([^"]+)"')
ROAD_COLORS = {focus.USES: (80, 168, 255), focus.USED_BY: (236, 96, 196)}
FOCUS_ROOF = (250, 250, 250)
MAX_NEIGHBOUR_LABELS = 8
LEGEND = [
    "height = complexity. Each floor is one function, biggest at the bottom:",
    "  thickness = that function's complexity, width = its size next to the module's biggest function.",
    f"amber floor = a function of {cake.LONG_FUNCTION}+ lines: the first thing to split.",
    "back row = foundations (3+ importers, import nothing). Main street = reached from the front door.",
    "across the street = scripts, grouped by the helper they import. Roof colour = top-level folder.",
    "across the water = nothing imports it. Named = its name appears in docs, config or code, so it is",
    "  probably loaded by name. Red label = its name appears nowhere: the first place to look for dead code.",
    "pier = an outside package, docked by the files that import it (<- how many).",
    "faded = last commit older than most of the repo (the oldest half fades, oldest most).",
    "windows = as many as fit each floor, centred: lit = tested, dark = untested, boarded = abandoned.",
]
ROAD_LEGEND = {
    "select": ["blue road = what the selected module uses. Pink road = what uses it. Everything else is dimmed."],
    "changed": ["pink road = what uses a changed module. Bright = uses it directly, half-dimmed = through another module."],
}


def front_doors(repo, model):
    """Declared entry points, not guessed: pyproject's [project.scripts], package.json's main
    and bin, and the module scripts a tracked HTML page loads."""
    files = repo.files()
    doors = set()
    if "pyproject.toml" in files:
        scripts = tomllib.loads(repo.read_text("pyproject.toml") or "").get("project", {}) \
            .get("scripts", {})
        resolver = Resolver([m for m in model.modules if m.endswith(".py")])
        doors |= {found for target in scripts.values()
                  if (found := resolver._longest("", target.split(":")[0]))}
    if "package.json" in files:
        try:
            package = json.loads(repo.read_text("package.json") or "{}")
        except ValueError:
            package = {}
        bins = package.get("bin") or {}
        targets = [package.get("main")] + (list(bins.values()) if isinstance(bins, dict)
                                           else [bins])
        doors |= {found for t in targets if isinstance(t, str)
                  if (found := _source_of(t, model))}
    for page in (f for f in files if f.endswith(".html")):
        tags = SCRIPT_TAG.findall(repo.read_text(page) or "")
        for src in (found.group(1) for tag in tags if 'type="module"' in tag
                    if (found := SCRIPT_SRC.search(tag))):
            path = src.lstrip("/") if src.startswith("/") else \
                os.path.normpath(os.path.join(os.path.dirname(page), src))
            if path in model.modules:
                doors.add(path)
    return sorted(doors)


def _source_of(target, model):
    """The module a package.json path names, mapping a build folder back to src/."""
    path = os.path.normpath(target)
    stem, _ = os.path.splitext(path)
    first, _, rest = stem.partition("/")
    stems = [stem] + ([f"src/{rest}"] if first in BUILD_DIRS and rest else [])
    return next((s + ext for s in stems for ext in [os.path.splitext(path)[1]] + JS_SOURCE_EXTS
                 if s + ext in model.modules), None)


def town_roles(model, rows, doors):
    """roles.roles, gathered into the rows the layout lays out."""
    found = roles.roles(model, doors)
    src = roles.buildings(model)
    succ, importers = roles.graph(model, src)
    of = lambda role: sorted(m for m, r in found.items() if r == role)
    return dict(src=src, succ=succ, importers=importers, doors=of(roles.DOOR),
                spine=of(roles.DOOR) + sorted(of(roles.STREET),
                                              key=lambda m: (-rows.modules.get(m, 0), m)),
                foundations=sorted(of(roles.FOUNDATION), key=lambda m: (-len(importers[m]), m)),
                side=of(roles.SIDE), groups=roles.script_groups(model, found),
                named=of(roles.NAMED), unused=of(roles.ISLAND),
                islands=of(roles.NAMED) + of(roles.ISLAND))


def wrap(members, size):
    """Members split into rows of about equal width, none much over MAX_ROW_TILES, in order."""
    total = sum(size[m] + 1 for m in members)
    target = total / max(1, math.ceil(total / MAX_ROW_TILES))
    rows, width = [], 0
    for m in members:
        if not rows or width + size[m] + 1 > target and width:
            rows.append([])
            width = 0
        rows[-1].append(m)
        width += size[m] + 1
    return rows


def place_row(lots, row, size, y):
    """Lots along one row, their fronts lined up; returns the row's depth."""
    depth, x = max(size[m] for m in row), 0
    for m in row:
        lots[m] = (x, y + depth - size[m], size[m])
        x += size[m] + 1
    return depth


def layout(r):
    """Tile lots by role: back rows, main street blocks, then script groups across the street."""
    size = {m: footprint(r["src"][m].loc) for m in r["src"]}
    lots = {}
    y = 0
    for i, row in enumerate(wrap(r["foundations"] + r["side"], size)):
        y += (i > 0) + place_row(lots, row, size, y + (i > 0))
    lane = max(y, 1)
    y = spine_top = lane + 1
    streets = []
    for row in wrap(r["spine"], size):
        y += place_row(lots, row, size, y)
        streets.append(y)
        y += 2
    streets = streets or [spine_top + 1]
    street = streets[-1]

    def anchor(members):
        xs = [lots[d][0] for m in members for d in r["succ"].get(m, ()) if d in lots]
        return sum(xs) / len(xs) if xs else 0

    groups = sorted(r["groups"].items(), key=lambda kv: (kv[0] == "standalone", anchor(kv[1])))
    boxes, x, top = {}, 0, street + 3
    for key, members in groups:
        cell = max(size[m] for m in members) + 1
        for i, m in enumerate(sorted(members, key=lambda m: (m != key, m))):
            col, row = i % GROUP_COLUMNS, i // GROUP_COLUMNS
            lots[m] = (x + col * cell, top + row * cell, size[m])
        cols = min(GROUP_COLUMNS, len(members))
        boxes[key] = (x, top, cols * cell)
        x += cols * cell + 1
    width = max((x + w for x, _, w in lots.values()), default=0) + 1

    def reach(ty):
        """A street runs as far as the furthest lot along either side of it."""
        return max((x + s for x, y, s in lots.values() if y - 3 <= ty <= y + s + 1), default=0)

    paved = {(tx, ty) for ty in [lane] + [s + k for s in streets for k in (0, 1)]
             for tx in range(reach(ty) + 1)}
    for i, m in enumerate(r["islands"]):
        lots[m] = (width + 3 + i * 3, spine_top, size[m])
    return lots, boxes, paved, width


def coastline(lots, paved):
    """Land one tile around every lot and street, each row filled in from the left edge."""
    rows = {}
    for x, y, s in lots:
        for ty in range(y - 1, y + s + 1):
            rows[ty] = max(rows.get(ty, -1), x + s)
    for tx, ty in paved:
        rows[ty] = max(rows.get(ty, -1), tx)
    return {(tx, ty) for ty, right in rows.items() for tx in range(-1, right + 1)}


def harbour(model, lots, land):
    """{package: (pier tiles, files that import it)} for the outside packages the town imports.

    Each pier leaves the shore nearest the middle of the files that import it, most-imported
    first, with no two piers closer than PORT_GAP along the coast.
    """
    users = {p: [m for m in found if m in lots] for p, found in model.externals.items()}
    chosen = sorted((p for p in users if users[p]), key=lambda p: (-len(users[p]), p))[:MAX_PORTS]
    shore = sorted({((tx + dx, ty + dy), (dx, dy)) for tx, ty in land for dx, dy in R.STEPS
                    if (tx + dx, ty + dy) not in land
                    and (tx + 2 * dx, ty + 2 * dy) not in land})
    ports, taken = {}, []
    for p in chosen:
        mids = [(lots[m][0] + lots[m][2] / 2, lots[m][1] + lots[m][2] / 2) for m in users[p]]
        cx, cy = sum(x for x, _ in mids) / len(mids), sum(y for _, y in mids) / len(mids)
        free = [(c, d) for c, d in shore
                if all(max(abs(c[0] - t[0]), abs(c[1] - t[1])) >= PORT_GAP for t in taken)]
        if not free:
            break
        (x, y), (dx, dy) = min(free, key=lambda cd: (cd[0][0] - cx) ** 2 + (cd[0][1] - cy) ** 2)
        taken.append((x, y))
        ports[p] = ([(x, y), (x + dx, y + dy)], users[p])
    return ports


def walk(start, goals, blocked, land, paved):
    """Cheapest tile path from start to any goal: streets are cheap, grass dear, lots closed."""
    cost, prev, heap = {start: 0}, {start: None}, [(0, start)]
    while heap:
        d, tile = heapq.heappop(heap)
        if tile in goals:
            path = []
            while tile is not None:
                path.append(tile)
                tile = prev[tile]
            return path[::-1]
        if d > cost[tile]:
            continue
        for dx, dy in R.STEPS:
            nxt = (tile[0] + dx, tile[1] + dy)
            if nxt in blocked or nxt not in land:
                continue
            nd = d + (STREET_COST if nxt in paved else GRASS_COST)
            if nd < cost.get(nxt, float("inf")):
                cost[nxt], prev[nxt] = nd, tile
                heapq.heappush(heap, (nd, nxt))
    return None


def plan_roads(r, model, lots, paved, land, pairs):
    """[(colour, weight, path, the way into the door at each end)], door to door along streets."""
    scripts = {m for members in r["groups"].values() for m in members}
    blocked = {(x + i, y + j) for x, y, s in lots.values() for i in range(s) for j in range(s)}

    def door(m):
        """The tile in front of a lot's middle, facing its street, and the way in."""
        x, y, s = lots[m]
        return ((x + s // 2, y - 1), (0, 1)) if m in scripts else ((x + s // 2, y + s), (0, -1))

    found = []
    for colour, s, d in pairs:
        (start, into_s), (goal, into_d) = door(s), door(d)
        path = walk(start, {goal}, blocked, land, paved)
        if path:
            found.append((colour, model.edges[(s, d)], path, (into_s, into_d)))
    return found


def road_tiles(found):
    """Per tile and kind: the heaviest road's weight, and the directions roads leave it in."""
    tiles = {}
    for kind, weight, path, (into_start, into_end) in found:
        for i, tile in enumerate(path):
            entry = tiles.setdefault(tile, {}).setdefault(kind, [0, set()])
            entry[0] = max(entry[0], weight)
            for j in (i - 1, i + 1):
                if 0 <= j < len(path):
                    entry[1].add((path[j][0] - tile[0], path[j][1] - tile[1]))
            if i == 0 and into_start:
                entry[1].add(into_start)
            if i == len(path) - 1 and into_end:
                entry[1].add(into_end)
    return tiles


def road_pixel(kinds, wx, wy, c):
    for kind in (focus.USED_BY, focus.USES):
        if kind in kinds:
            weight, dirs = kinds[kind]
            hw = R.half_width(R.ROAD, weight)
            if _on_road(dirs, wx, wy, hw):
                edge = not _on_road(dirs, wx, wy, hw - 0.08)
                c = shade(ROAD_COLORS[kind], 0.82) if edge else ROAD_COLORS[kind]
    return c


def project(x, y, z, ox, oy):
    sx, sy = iso.to_screen(x, y)
    return sx + ox, sy - z + oy


def tier(fb, owner, key, sx, sy, half, z0, z1, c):
    """One block of a building, in whole pixels; owner records which wall each pixel is."""
    walls = {"left": shade(c, 0.95), "right": shade(c, 0.74)}
    for face, dx, t in cake.wall_columns(half):
        col = sx + dx
        for k in range(z0, z1):
            y = sy + t // 2 - k
            fb.set(col, y, shade(walls[face], 0.6) if k == z0 else walls[face])
            owner[col, y] = key, face
        for y in range(sy - t // 2 - z1, sy + t // 2 - z1 + 1):
            fb.set(col, y, shade(c, 1.08))
            owner[col, y] = key, "top"


def glaze(fb, owner, planned):
    """Paint each window only if every pixel of it is still its own wall: whole or not at all."""
    for key, face, pixels, glass in planned:
        if all(owner.get(p) == (key, face) for p in pixels):
            for x, y in pixels:
                fb.set(x, y, glass if face == "left" else shade(glass, 0.82))


def floors(m, size, flat):
    """The building's cake.Tiers; flat squashes them into one low block that keeps any amber."""
    stack = cake.tiers([] if m.parse_error else m.functions, size, m.complexity)
    if flat:
        return [cake.Tier(stack[0].half, 0, FLAT_HEIGHT, any(t.amber for t in stack))]
    return stack


def draw_building(fb, owner, planned, m, lot, stack, roof, fade, glass, ox, oy):
    x, y, size = lot
    sx, sy = map(round, project(x + size / 2, y + size / 2, 0, ox, oy))
    for i, t in enumerate(stack):
        c = AMBER if t.amber else mix(shade(WALL, 1.0 if i % 2 == 0 else 0.84), GRAY, fade)
        tier(fb, owner, (m, i), sx, sy, t.half, t.z0, t.z1, c)
        planned += [((m, i), face, [(sx + dx, sy + dy) for dx, dy in px], glass)
                    for face, px in cake.windows(t.half, t.z0, t.z1)]
    top = stack[-1]
    tier(fb, owner, (m, "roof"), sx, sy, top.half, top.z1, top.z1 + 2, mix(roof, GRAY, fade))
    return top.z1 + 2


def find_focus(root, model, lots, kind, arg, tracked=()):
    """A focus.Focus for "select", "changed" or "session", and where the changes came from."""
    def one(name):
        matches = [m for m in lots if m == name or m.endswith("/" + name)]
        if len(matches) != 1:
            raise SystemExit(f"{name}: matches {len(matches)} modules in the town")
        return matches[0]

    if kind == "select":
        return focus.select(model, one(arg)), None
    if kind == "changed":
        return focus.changed(model, {one(name) for name in arg.split(",")}), None
    found = session.transcripts(root)
    transcript = arg or (found[-1] if found else None)
    if not transcript:
        raise SystemExit(f"no Claude Code or Cursor transcript found for {root}")
    steps = session.load(transcript, root)
    changed = focus.changed_by(steps, model)
    new = focus.unbuilt(steps, model, tracked)
    paths = {s.path for s in steps if s.kind in session.CHANGES and not s.failed}
    return focus.changed(model, changed), (transcript, new, len(paths - set(lots) - set(new)))


def construction(new, lots, width):
    """A 1-tile site per new file along the front of the town: a yard per top folder."""
    folders = {}
    for p in new:
        folders.setdefault(_top_folder(p), []).append(p)
    top = max(y + s for _, y, s in lots.values()) + 1
    sites, x, y, deepest = {}, 0, top, 0
    for members in folders.values():
        cols = min(SITE_COLUMNS, len(members))
        if x and x + cols > width:
            x, y = 0, y + deepest + 1
        for i, p in enumerate(members):
            sites[p] = (x + i % cols, y + i // cols, 1)
        deepest = max(deepest, -(-len(members) // cols))
        x += cols + 1
    return sites


def _top_folder(path):
    return path.split("/")[0] + "/" if "/" in path else path


def summary(f, lots, source):
    """The legend lines saying what is in focus, counted over the buildings in the town."""
    count = lambda test: sum(1 for m, d in f.distance.items() if m in lots and test(d))
    if f.kind == "select":
        return []
    line = (f"{count(lambda d: d == 0)} changed, {count(lambda d: d == 1)} use them directly, "
            f"{count(lambda d: d > 1)} more through them, "
            f"{len(lots) - count(lambda d: True)} can't be affected.")
    if not source:
        return [line]
    transcript, new, missing = source
    return [f"session {os.path.basename(transcript)}: {line}",
            f"  orange site at the front = {len(new)} new code files, not committed yet. "
            f"{missing} other changed files aren't buildings: docs, tests or outside the repo."]


def render(root, out, focus_arg=None, flat=False):
    """focus_arg is None, or ("select", MODULE), ("changed", "A,B") or ("session", TRANSCRIPT)."""
    repo = Repo(root)
    model = survey.survey(root)
    rows = Rows().update(model)
    r = town_roles(model, rows, front_doors(repo, model))
    lots, boxes, paved, width = layout(r)
    f, source = (find_focus(root, model, lots, *focus_arg, tracked=repo.files()) if focus_arg
                 else (None, None))
    sites = construction(source[1], lots, width) if source else {}
    pairs = [p for p in f.roads if p[1] in lots and p[2] in lots] if f else []
    when = {m: int(repo._git("log", "-1", "--format=%ct", "--", m) or time.time()) for m in lots}
    order = sorted(set(when.values()), reverse=True)
    rank = {m: order.index(t) / max(1, len(order) - 1) for m, t in when.items()}
    fades = {m: MAX_FADE * max(0.0, rank[m] - 0.5) * 2 for m in lots}
    districts = sorted({r["src"][m].district for m in lots})
    land = coastline([lot for m, lot in lots.items() if m not in r["islands"]]
                     + list(sites.values()), paved)
    for m in r["islands"]:
        x, y, s = lots[m]
        land |= {(tx, ty) for tx in range(x - 1, x + s + 1) for ty in range(y - 1, y + s + 1)}
    ports = harbour(model, lots, land)
    piers = {t for tiles, _ in ports.values() for t in tiles}
    sheds = {p: tiles[-1] for p, (tiles, _) in ports.items()}
    stacks = {m: floors(r["src"][m], lot[2], flat) for m, lot in lots.items()}
    corners = [iso.to_screen(tx, ty) for tx, ty in land | piers]
    top_room = max([TOP_ROOM - min(sy for _, sy in corners)]
                   + [stacks[m][-1].z1 + TOP_ROOM // 3
                      - round(project(x + s / 2, y + s / 2, 0, 0, 0)[1])
                      for m, (x, y, s) in lots.items()])
    left = min(sx for sx, _ in corners) - iso.TILE_W
    w = max(sx for sx, _ in corners) + iso.TILE_W - left
    h = max(sy for _, sy in corners) + iso.TILE_H + top_room + 10
    ox, oy = -left, top_room
    fb = Framebuffer(w, h, SEA)
    tiles = road_tiles(plan_roads(r, model, lots, paved, land, pairs))
    for tx, ty in sorted(land, key=lambda t: (t[1], t[0])):
        sx, sy = project(tx, ty, 0, ox, oy)
        kind = "plaza" if (tx, ty) in paved else "grass"
        kinds = tiles.get((tx, ty))
        for dx, dy in iso.TILE_MASK:
            c = ground_color(kind, tx, ty, dx, dy, sx + dx, sy + dy, 0)
            fb.set(sx + dx, sy + dy, road_pixel(kinds, *LOCAL[(dx, dy)], c) if kinds else c)
    for tx, ty in piers:
        sx, sy = project(tx, ty, 0, ox, oy)
        for dx, dy in iso.TILE_MASK:
            fb.set(sx + dx, sy + dy, shade(PIER, 0.86 if dy % 2 else 1.0))
    abandoned = {p.module for p in problems.find(model, rows) if p.kind == problems.ABANDONED}
    labels, owner, planned = [], {}, []
    for _, m in sorted([(x + y + s, m) for m, (x, y, s) in lots.items()]
                       + [(x + y + 1, p) for p, (x, y) in sheds.items()]):
        if m in sheds:
            x, y = sheds[m]
            users = ports[m][1]
            z = PORT_HEIGHT + round(PORT_HEIGHT * len(users) / max(len(u) for _, u in ports.values()))
            sx, sy = map(round, project(x + 0.5, y + 0.5, 0, ox, oy))
            tier(fb, owner, (m, 0), sx, sy, PORT_HALF, 0, z, PORT_WALL)
            tier(fb, owner, (m, "roof"), sx, sy, PORT_HALF, z, z + 2, PORT_ROOF)
            if not f or any(f.distance.get(u) == 0 for u in users):
                labels.append((f"{m}  <- {len(users)}",
                               project(x + 0.5, y + 0.5, z + 2, ox, oy), PORT_LABEL))
            continue
        lot = lots[m]
        mod = r["src"][m]
        d = districts.index(mod.district)
        glass = BOARD if m in abandoned else LIT if mod.tested_by else DARK
        stack = stacks[m]
        roof = FOCUS_ROOF if f and f.distance.get(m) == 0 else ROOFS[d % len(ROOFS)]
        top = draw_building(fb, owner, planned, m, lot, stack, roof, fades[m], glass, ox, oy)
        x, y, s = lot
        anchor = project(x + s / 2, y + s / 2, top, ox, oy)
        name = os.path.basename(m)
        if f:
            labels += focus_label(m, name, anchor, f, lots)
        elif m in r["doors"]:
            labels.append((f"> {name}  front door", anchor, (250, 214, 60)))
        elif m in r["foundations"]:
            labels.append((f"{name}  <- {len(r['importers'][m])}", anchor, (200, 220, 255)))
        elif m in r["side"]:
            labels.append((f"{name}  (not from the door)", anchor, (230, 230, 230)))
        elif m in r["named"]:
            labels.append((f"{name}  (named, not imported)", anchor, (190, 190, 200)))
        elif m in r["unused"]:
            labels.append((f"{name}  nothing uses it", anchor, (255, 150, 120)))
        elif m in r["spine"]:
            labels.append((name, anchor, (230, 230, 230)))
    for key, (gx, gy, gw) in boxes.items() if not f else ():
        title = "standalone scripts" if key == "standalone" else \
            f"{os.path.basename(key)} + {len(r['groups'][key]) - 1} scripts"
        labels.append((title, project(gx + gw / 2, gy + gw / 2, -14, ox, oy), (180, 230, 170)))
    folders = {}
    for p in sites:
        folders.setdefault(_top_folder(p), []).append(p)
    for folder, members in folders.items():
        for p in members:
            x, y, s = sites[p]
            sx, sy = map(round, project(x + s / 2, y + s / 2, 0, ox, oy))
            tier(fb, owner, (p, 0), sx, sy, cake.half_width(1, SITE_WIDTH), 0, SITE_HEIGHT, SITE)
        x, y, s = sites[members[0]]
        labels.append((f"new: {folder} ({len(members)})" if len(members) > 1
                       else f"new: {os.path.basename(members[0])}",
                       project(x + s / 2, y + s / 2, SITE_HEIGHT, ox, oy), SITE))
    glaze(fb, owner, planned)
    extra = []
    if f:
        for (x, y), (key, _) in owner.items():
            level = max(focus.dim(f, u) for u in ports[key[0]][1]) if key[0] in sheds \
                else focus.dim(f, key[0])
            if level < 1 and key[0] not in sites:
                fb.set(x, y, shade(fb.rows[y][x], level))
        extra = ROAD_LEGEND[f.kind] + summary(f, lots, source)
    _save(fb, labels, LEGEND + extra, out)
    return r, extra


def focus_label(m, name, anchor, f, lots):
    d = f.distance.get(m)
    if d == 0 and f.kind == "select":
        uses = sum(c == focus.USES for c, *_ in f.roads)
        return [(f"{name}: uses {uses}, used by {len(f.roads) - uses}", anchor, (255, 255, 255))]
    if d == 0:
        return [(f"changed: {name}", anchor, (255, 255, 255))]
    if d is not None and sum(1 for n in f.distance if n in lots) - 1 <= MAX_NEIGHBOUR_LABELS:
        used = any(c == focus.USES and dst == m for c, _, dst in f.roads)
        return [(name, anchor, ROAD_COLORS[focus.USES if used else focus.USED_BY])]
    return []


def _save(fb, labels, legend, out):
    img = Image.new("RGB", (fb.w, fb.h))
    img.putdata([c for row in fb.rows for c in row])
    img = img.resize((fb.w * SCALE, fb.h * SCALE), Image.NEAREST)
    legend_h = 16 * len(legend) + 16
    canvas = Image.new("RGB", (img.width, img.height + legend_h), (16, 20, 30))
    canvas.paste(img, (0, 0))
    draw = ImageDraw.Draw(canvas)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Menlo.ttc", 13)
    except OSError:
        font = ImageFont.load_default()
    placed = []
    for text, (ax, ay), color in labels:
        tw, th = draw.textbbox((0, 0), text, font=font)[2:]
        x, y = ax * SCALE - tw // 2, ay * SCALE - th - 14
        while any(x < px2 and px1 < x + tw + 8 and y < py2 and py1 < y + th + 6
                  for px1, py1, px2, py2 in placed):
            y -= th + 6
        placed.append((x - 4, y - 3, x + tw + 4, y + th + 3))
        draw.line([(ax * SCALE, ay * SCALE), (ax * SCALE, y + th + 3)], fill=(20, 20, 24))
        draw.rectangle(placed[-1], fill=(24, 26, 34))
        draw.text((x, y), text, font=font, fill=color)
    for i, line in enumerate(legend):
        draw.text((12, img.height + 8 + 16 * i), line, font=font, fill=(200, 200, 210))
    canvas.save(out)


def watch(root, out, transcript, flat):
    """Re-render whenever the session's transcript grows, a new session starts, or HEAD moves.

    Opens OUT.png once, in Cursor when its command is installed, since its image tab reloads
    when the file changes.
    """
    print(f"watching {root}: {out} is redrawn after each agent step. Ctrl-C to stop.", flush=True)
    last = None
    try:
        while True:
            found = session.transcripts(root)
            current = transcript or (found[-1] if found else None)
            head = Repo(root)._git("rev-parse", "HEAD")
            seen = (current, current and os.path.getmtime(current), head)
            if not current and last is None:
                print("no Claude Code or Cursor session for it yet; waiting for one.", flush=True)
                last = seen
            if current and seen != last:
                _, extra = render(root, out, ("session", current), flat)
                print(time.strftime("%H:%M:%S"), *(line.strip() for line in extra[1:]), flush=True)
                if last is None or last[0] is None:
                    _show(out)
                last = seen
            time.sleep(WATCH_SECONDS)
    except KeyboardInterrupt:
        pass


def _show(path):
    opener = shutil.which("cursor") or ("open" if sys.platform == "darwin" else "xdg-open")
    try:
        subprocess.Popen([opener, path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        print(f"open {path} to see it.")


def main(argv):
    flat, watching = "flat" in argv[3:], "watch" in argv[3:]
    rest = [a for a in argv[3:] if a not in ("flat", "watch")]
    kind, _, arg = rest[0].partition(":") if rest else ("session" if watching else None, "", "")
    if len(argv) < 3 or len(rest) > 1 or kind not in (None, "select", "changed", "session") \
            or kind in ("select", "changed") and not arg or watching and kind != "session":
        raise SystemExit(__doc__)
    if watching:
        return watch(argv[1], argv[2], arg, flat)
    r, _ = render(argv[1], argv[2], (kind, arg) if kind else None, flat)
    for role in ("doors", "spine", "foundations", "side", "named", "unused"):
        print(f"{role}: {', '.join(r[role]) or '-'}")
    for key, members in r["groups"].items():
        print(f"group {key}: {', '.join(members)}")
    print(f"wrote {argv[2]}")


if __name__ == "__main__":
    main(sys.argv)
