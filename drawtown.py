"""Draws a TownMap into a framebuffer, back to front.

Cakes are drawn once; construction sites last; then glaze keeps a window only if
every pixel is still its own wall; then focus shading and the ghost.
"""

import math
from dataclasses import dataclass
from functools import partial

import cake
import iso
import problems
import roads as R
from focus import USED_BY, USES
import sprites
from render import (DIRT, DOOR, LOCAL, SKIRT, SKIRT_DEPTH, SKIRT_LIP, Framebuffer, ground_color,
                    hash2, mix, shade)
from townmap import Building, Warehouse

SEA = (30, 66, 112)
WAREHOUSE_H = 9
ANNEX_H = 5
TOP_ROOM = 96
ROOF = 2
SIDE_ROOM = 28
AMBER = (236, 160, 40)
FOCUS_ROOF = (250, 250, 250)
SITE = (232, 128, 48)
SITE_WIDTH = 0.7
SITE_HEIGHT = 3
WEAR_FULL = 10
WALLS = [(222, 208, 182), (210, 200, 186), (218, 196, 170), (200, 192, 180)]
ROOFS = [(84, 108, 150), (150, 92, 76), (88, 132, 102), (132, 104, 156), (160, 138, 84),
         (80, 132, 140), (152, 102, 124), (112, 112, 124)]
LIT = (240, 212, 140)
DARK = (46, 52, 70)
BOARD = (138, 98, 62)
WEED = (70, 120, 52)
NOTE = (250, 214, 60)
FLAMES = [(255, 72, 32), (255, 140, 40), (255, 214, 90)]
SMOKE = (92, 92, 100)
CRACK = (84, 76, 70)
SHIMMER = (255, 226, 150)
OUTLINE = (206, 206, 212)
UNKNOWN = (150, 150, 156)
RUBBLE = (132, 126, 122)
PLANK = (150, 112, 74)
STONE_GATE = (196, 186, 170)
NO_ENTRY = (220, 40, 40)
WHITE = (244, 244, 244)
POST = (60, 60, 70)
SELECT = (236, 246, 255)
ANNEX_WALL = (204, 208, 192)
ANNEX_ROOF = (118, 148, 108)
WAREHOUSE_WALL = (122, 136, 152)
WAREHOUSE_ROOF = (86, 92, 104)
ROAD_COLORS = {R.ROAD: (82, 84, 96), R.HIGHWAY: (58, 60, 70), R.CYCLE: (214, 46, 46),
               R.BACKWARDS: (232, 112, 36), USES: (80, 168, 255), USED_BY: (236, 96, 196)}
LOUD_ROADS = (R.CYCLE, R.BACKWARDS)

GLASS = {"board": BOARD, "door": DOOR, "lit": LIT, "dark": DARK}


def window_kind(b):
    """What a building's windows show: boards when abandoned, doors when it's all doors,
    else lit when tested and dark when not."""
    if problems.ABANDONED in b.problems:
        return "board"
    if problems.ALL_DOORS in b.problems:
        return "door"
    return "lit" if b.tested else "dark"


def roof_index(tmap):
    """Each district's roof as an index into ROOFS, in name order, the same in every view."""
    names = sorted(set(tmap.boxes) | {b.district for b in tmap.buildings.values()})
    return {name: i % len(ROOFS) for i, name in enumerate(names)}


DROP_HEIGHT = 48
DROP_TIME = 0.42
SCAFFOLD = (150, 112, 74)
SITE_ORANGE = SITE
HAT = (60, 60, 70)
LECTERN = (120, 90, 60)
GLASSES = (30, 26, 24)

# sprites.clawd_rows(facing, frame) = _CLAWD_BODY + _CLAWD_LEGS[frame]:
#   row 0 ".OOOOOOO."  row 1 ".OOOOOOO." (eyes on row 1 when facing south/east)
#   row 2 "OOOOOOOOO"  row 3 ".ooooooo."  <- scarf: recolour every 'o' here
#   then leg row(s) e.g. ".o.o.o.o."
_SCARF_ROW = 3
# Pointed hat rows appended above clawd_rows (relative to body, negative y in sprite space).
_HAT_ROWS = ["..PPP..", ".PPPPP."]
_HAT_PALETTE = {"P": HAT}


def drop_offset(t):
    """48 px at t=0, 0 at t>=0.42. Ease-out with slight overshoot (v3 intro building drop)."""
    if t <= 0:
        return float(DROP_HEIGHT)
    if t >= DROP_TIME:
        return 0.0
    u = t / DROP_TIME
    base = (1 - u) ** 2
    return DROP_HEIGHT * base * (1 + 0.12 * math.sin(u * math.pi))


@dataclass
class WatchLayer:
    scaffolded: dict  # module -> team
    team_colours: dict  # team -> palette index
    sites: dict  # path -> (tx, ty, size, team)
    flags: dict  # worktree -> (building module, team)
    drops: dict  # module -> drop start time (scene.t)
    clawds: list
    town_hall: tuple


def clawd_extra_rows(clawd):
    if clawd.role == "orchestrator":
        return list(_HAT_ROWS)
    return []


def clawd_palette(clawd, team_colours):
    import watch
    base = dict(sprites.CLAWD)
    if clawd.role == "implementer":
        colour = watch.PALETTE[team_colours.get(clawd.team or "", clawd.colour)]
        return {**base, "o": colour}
    if clawd.role == "reviewer":
        return {**base, "o": watch.RESERVED["reviewer_grey"], "E": GLASSES}
    if clawd.role == "orchestrator":
        return {**base, **_HAT_PALETTE}
    return base


def clawd_marker_px(scene, clawd):
    sx, sy = scene.screen(clawd.tile[0] + 0.5, clawd.tile[1] + 0.5)
    return round(sx), round(sy)


def draw_town_markers(fb, scene, clawds, team_colours, *, origin=(0, 0), scale=1):
    """3×3 scarf-colour markers for town zoom (same as _append_watch_drawables town branch)."""
    import watch
    ox, oy = origin
    for c in clawds:
        if c.role == "orchestrator":
            continue
        mx, my = clawd_marker_px(scene, c)
        sx, sy = (mx - ox) // scale, (my - oy) // scale
        col = watch.PALETTE[team_colours.get(c.team or "", c.colour)]
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                x, y = sx + dx, sy + dy
                if 0 <= x < fb.w and 0 <= y < fb.h:
                    fb.set(x, y, col)


def _clawd_anchor(scene, clawd):
    fx, fy = iso.to_screen(clawd.tile[0] + 0.5, clawd.tile[1] + 0.5)
    ax = round(fx) + scene.ox
    ay = round(fy) + scene.oy + iso.HALF_H - int(clawd.hop_y)
    return ax, ay


def scarf_pixel_positions(scene, clawd, team_colours):
    ax, ay = _clawd_anchor(scene, clawd)
    rows = sprites.clawd_rows(clawd.facing, clawd.walk_frame)
    palette = clawd_palette(clawd, team_colours)
    y0 = ay - len(rows) + 1
    x0 = ax - 4
    out = []
    for x, y, c in sprites.parse(rows, palette):
        if rows[y].count("o") and c == palette.get("o"):
            out.append((x0 + x, y0 + y))
    return out


def hat_pixel_positions(scene, clawd):
    ax, ay = _clawd_anchor(scene, clawd)
    rows = clawd_extra_rows(clawd) + sprites.clawd_rows(clawd.facing, clawd.walk_frame)
    palette = clawd_palette(clawd, {})
    y0 = ay - len(rows) + 1
    x0 = ax - 4
    return [(x0 + x, y0 + y) for x, y, c in sprites.parse(rows, palette) if c == HAT]


def glasses_pixel_positions(scene, clawd):
    ax, ay = _clawd_anchor(scene, clawd)
    rows = sprites.clawd_rows(clawd.facing, clawd.walk_frame)
    palette = clawd_palette(clawd, {})
    y0 = ay - len(rows) + 1
    x0 = ax - 4
    return [(x0 + x, y0 + y) for x, y, c in sprites.parse(rows, palette) if c == GLASSES]


def flag_pixel_positions(scene, b):
    fx, fy = scene.screen(b.x + b.size, b.y)
    fx, fy = round(fx), round(fy)
    return [(fx + i, fy - i) for i in range(4)]


def scaffold_front_pixels(scene, b):
    """Front-wall pixels where team-coloured scaffolding is drawn."""
    height = height_px(b)
    pixels = []
    for tx in range(b.x, b.x + b.size):
        ty = b.y + b.size - 1
        sx, sy = scene.screen(tx, ty)
        right_same = tx + 1 < b.x + b.size
        hx = height if right_same else 0
        for dx, bottom in iso.COLUMN_BOTTOM.items():
            if dx < 0:
                continue
            for k in range(height):
                left = dx == 0 and k < hx
                if left or right_same:
                    continue
                pixels.append((sx + dx, sy + bottom - k))
    return pixels


def scaffold_shade(colour, i, n):
    factors = (0.6, 0.74, 0.95, 1.08)
    return shade(colour, factors[(i * len(factors)) // max(1, n)])


def site_accent_pixel(scene, tx, ty, size):
    sx, sy = scene.screen(tx + 0.5, ty + 0.5)
    half = cake.half_width(size, SITE_WIDTH)
    top_y = round(sy) - half // 2 - SITE_HEIGHT
    return round(sx), top_y


def site_wall_pixel(scene, tx, ty, size):
    """One orange wall pixel from a construction-site tier block and its colour."""
    sx, sy = scene.screen(tx + 0.5, ty + 0.5)
    sx, sy = round(sx), round(sy)
    half = cake.half_width(size, SITE_WIDTH)
    walls = {"left": shade(SITE_ORANGE, 0.95), "right": shade(SITE_ORANGE, 0.74)}
    face, dx, t = next(iter(cake.wall_columns(half)))
    return sx + dx, sy + t // 2 - 1, walls[face]


def lectern_pixel_positions(scene, hall):
    sx, sy = scene.screen(hall[0], hall[1])
    px, py = local_to_screen(0.5, 0.5)
    ax, ay = sx + px, sy + py
    out = [(ax, ay - k) for k in range(5)]
    for i in range(-2, 3):
        out.append((ax + i, ay - 5))
        out.append((ax + i, ay - 6))
    return out


def roof_corner_pixel(scene, b):
    tx, ty = b.x + b.size - 1, b.y
    sx, sy = scene.screen(tx, ty)
    return sx, sy - height_px(b)


def tree_sprite_pixels(scene, tx, ty):
    sx, sy = scene.screen(tx, ty)
    seed = tx * 31 + ty * 17
    kind = "bush" if (tx, ty) in scene.m.bushes else ("pine", "round")[seed % 2]
    return [(sx + dx, sy + iso.HALF_H + dy) for dx, dy, _ in sprites.tree(kind, seed)]


def hall_tile_pixels(scene, hall, tmap):
    import crowd
    tiles = {hall}
    occupied = set()
    for _ in range(12):
        spot = crowd.hall_standing_spot(tmap, hall, occupied)
        tiles.add(spot)
        occupied.add(spot)
    pixels = set()
    for tile in tiles:
        tsx, tsy = scene.screen(*tile)
        for dx, dy in iso.TILE_MASK:
            pixels.add((tsx + dx, tsy + dy))
    return pixels


def _draw_sprite(fb, ax, ay, rows, palette, ghost, y_offset=0):
    y0 = ay - len(rows) + 1 - y_offset
    x0 = ax - 4
    for x, y, c in sprites.parse(rows, palette):
        fb.set(x0 + x, y0 + y, c)
        ghost[(x0 + x, y0 + y)] = c


def _tier_block(fb, sx, sy, half, z0, z1, c):
    """One building tier block (copied from mock_roles.tier — no Pillow)."""
    walls = {"left": shade(c, 0.95), "right": shade(c, 0.74)}
    for face, dx, t in cake.wall_columns(half):
        col = sx + dx
        for k in range(z0, z1):
            y = sy + t // 2 - k
            fb.set(col, y, shade(walls[face], 0.6) if k == z0 else walls[face])
        for y in range(sy - t // 2 - z1, sy + t // 2 - z1 + 1):
            fb.set(col, y, shade(c, 1.08))


def _append_watch_drawables(scene, drawables):
    import watch
    layer = scene._watch
    if layer is None:
        return
    zoom = scene._watch_zoom
    m = scene.m
    t = scene.t

    def add(depth_tx, depth_ty, layer_i, draw_fn):
        drawables.append((depth_tx + depth_ty, layer_i, depth_tx, draw_fn))

    for mod, team in layer.scaffolded.items():
        if mod not in m.buildings:
            continue
        b = m.buildings[mod]
        colour = watch.PALETTE[layer.team_colours[team]]

        def draw_scaffold(b=b, colour=colour):
            pixels = scaffold_front_pixels(scene, b)
            n = len(pixels)
            for i, (x, y) in enumerate(pixels):
                scene.fb.set(x, y, scaffold_shade(colour, i, n))

        add(b.x + b.size, b.y + b.size, 2, draw_scaffold)

    for path, site in layer.sites.items():
        tx, ty, size, team = site
        team_colour = watch.PALETTE[layer.team_colours[team]]
        ax, ay = site_accent_pixel(scene, tx, ty, size)

        def draw_site(tx=tx, ty=ty, size=size, team_colour=team_colour, ax=ax, ay=ay):
            sx, sy = scene.screen(tx + 0.5, ty + 0.5)
            _tier_block(scene.fb, round(sx), round(sy), cake.half_width(size, SITE_WIDTH),
                        0, SITE_HEIGHT, SITE_ORANGE)
            scene.fb.set(ax, ay, team_colour)

        add(tx, ty, 2, draw_site)

    for wt, flag in layer.flags.items():
        mod, team = flag
        if mod not in m.buildings:
            continue
        b = m.buildings[mod]
        colour = watch.PALETTE[layer.team_colours[team]]

        def draw_flag(b=b, colour=colour):
            for x, y in flag_pixel_positions(scene, b):
                scene.fb.set(x, y, colour)

        add(b.x + b.size, b.y, 2, draw_flag)

    def draw_lectern():
        positions = lectern_pixel_positions(scene, layer.town_hall)
        for x, y in positions[:5]:
            scene.fb.set(x, y, POST)
        for x, y in positions[5:10]:
            scene.fb.set(x, y, LECTERN)
        for x, y in positions[10:]:
            scene.fb.set(x, y, shade(LECTERN, 1.1))

    add(layer.town_hall[0], layer.town_hall[1], 2, draw_lectern)

    if zoom == "town":
        for c in layer.clawds:
            if c.role == "orchestrator":
                continue
            mx, my = clawd_marker_px(scene, c)
            col = watch.PALETTE[c.colour]

            def draw_marker(mx=mx, my=my, col=col):
                for dx in (-1, 0, 1):
                    for dy in (-1, 0, 1):
                        scene.fb.set(mx + dx, my + dy, col)

            add(c.tile[0], c.tile[1], 3, draw_marker)
        return

    for c in layer.clawds:
        def draw_clawd(c=c):
            ax, ay = _clawd_anchor(scene, c)
            rows = clawd_extra_rows(c) + sprites.clawd_rows(c.facing, c.walk_frame)
            _draw_sprite(scene.fb, ax, ay, rows, clawd_palette(c, layer.team_colours), scene.ghost)

        add(c.tile[0], c.tile[1], 2, draw_clawd)


def height_px(b):
    return b.stack[-1].z1 + ROOF


def local_to_screen(wx, wy):
    return round((wx - wy) * iso.HALF_W), round((wx + wy) * iso.HALF_H)


def _on_road(dirs, wx, wy, hw):
    ux, uy = wx - 0.5, wy - 0.5
    if abs(ux) <= hw and abs(uy) <= hw:
        return True
    for dx, dy in dirs:
        if dx and abs(uy) <= hw and ux * dx >= 0:
            return True
        if dy and abs(ux) <= hw and uy * dy >= 0:
            return True
    return False


class TownScene:
    def __init__(self, tmap, w, h, ox, oy, t=0.0, selected=None, visible=(), cursor=None,
                 dim=None, focused=frozenset()):
        self.m = tmap
        self.t = t
        self.fb = Framebuffer(w, h, SEA)
        self.ox, self.oy = ox, oy
        self.selected = selected
        self.segments = R.segments(visible)
        self.roundabouts = R.roundabouts(tmap, visible)
        self.cursor = cursor
        self.ghost = {}
        self._watch = None
        self._watch_zoom = "street"
        self._watch_hall_pixels = None
        self._watch_reserved_pixels = None
        self._drop_off = {}
        self.roofs = {name: ROOFS[i] for name, i in roof_index(tmap).items()}
        self.plot_of = {}
        for module, (x, y, size) in tmap.plots.items():
            for i in range(size):
                for j in range(size):
                    self.plot_of[(x + i, y + j)] = (x, y, size)
        self.owner = {}
        self.planned = []
        self.dim = dim
        self.focused = focused
        self.site_at = {tile: path for path, tile in tmap.sites.items()}

    @classmethod
    def around(cls, tmap, w, h, tile, lift=0, **kw):
        """A w x h view centred on a tile, raised by `lift` pixels to frame tall buildings."""
        sx, sy = iso.to_screen(tile[0] + 0.5, tile[1] + 0.5)
        return cls(tmap, w, h, w // 2 - round(sx), h // 2 - round(sy) + lift, **kw)

    @classmethod
    def whole(cls, tmap, **kw):
        left = -tmap.height * iso.HALF_W - iso.HALF_W
        right = tmap.width * iso.HALF_W + iso.HALF_W
        bottom = (tmap.width + tmap.height) * iso.HALF_H + SKIRT_DEPTH + 2
        return cls(tmap, right - left, bottom + TOP_ROOM, -left, TOP_ROOM, **kw)

    def screen(self, tx, ty):
        sx, sy = iso.to_screen(tx, ty)
        return sx + self.ox, sy + self.oy

    def centre_px(self, b):
        sx, sy = iso.to_screen(b.x + b.size / 2, b.y + b.size / 2)
        return round(sx) + self.ox, round(sy) + self.oy

    def visible(self, sx, sy):
        return -SIDE_ROOM < sx < self.fb.w + SIDE_ROOM and -8 < sy < self.fb.h + TOP_ROOM

    def render(self):
        self.owner.clear()
        self.planned.clear()
        m = self.m
        self._drop_off = {}
        if self._watch:
            for mod, start in self._watch.drops.items():
                off = int(drop_offset(self.t - start))
                if off > 0:
                    self._drop_off[mod] = off
        drawables = []
        for ty in range(m.height):
            for tx in range(m.width):
                sx, sy = self.screen(tx, ty)
                if not self.visible(sx, sy):
                    continue
                self.draw_ground(tx, ty, sx, sy)
                thing = m.at.get((tx, ty))
                if isinstance(thing, Building):
                    if (tx, ty) == thing.tiles()[-1]:
                        drawables.append((tx + ty, 0, tx, partial(self.draw_cake, thing)))
                elif thing is not None:
                    draw = partial(self.draw_warehouse, thing, tx, ty, sx, sy)
                    drawables.append((tx + ty, 0, tx, draw))
                elif (tx, ty) in m.trees and not self._watch_tree_overlaps_reserved(tx, ty):
                    drawables.append((tx + ty, 0, tx, partial(self.draw_tree, tx, ty, sx, sy)))
                for prop in m.props.get((tx, ty), ()):
                    drawables.append((tx + ty, 1, tx, partial(self.draw_prop, prop, sx, sy)))
        for b in m.buildings.values():
            if b.tested:
                tx, ty = b.x + b.size, b.y
                sx, sy = self.screen(tx, ty)
                if self.visible(sx, sy):
                    drawables.append((tx + ty, 1, tx,
                                      partial(self.draw_annex, b.module, sx, sy)))
        if getattr(self, "_watch", None):
            _append_watch_drawables(self, drawables)
        drawables.sort(key=lambda d: d[:3])
        for *_, draw in drawables:
            draw()
        for tx, ty in sorted(self.site_at, key=lambda t: (t[0] + t[1], t[0])):
            sx, sy = self.screen(tx, ty)
            if self.visible(sx, sy):
                self.draw_site(self.site_at[(tx, ty)], tx, ty)
        self.glaze()
        self.shade_by_focus()
        self.draw_ghost()
        return self.fb

    def set_watch(self, layer: WatchLayer, zoom: str, *, reserved_pixels=None):
        self._watch = layer
        self._watch_zoom = zoom
        self._watch_hall_pixels = None
        self._watch_reserved_pixels = reserved_pixels

    def _reserved_pixels(self):
        if self._watch_reserved_pixels is not None:
            return self._watch_reserved_pixels
        if self._watch:
            pixels = hall_tile_pixels(self, self._watch.town_hall, self.m)
            for tx, ty, size, _team in self._watch.sites.values():
                for dx in range(size):
                    for dy in range(size):
                        tsx, tsy = self.screen(tx + dx, ty + dy)
                        for mask_dx, mask_dy in iso.TILE_MASK:
                            pixels.add((tsx + mask_dx, tsy + mask_dy))
            self._watch_reserved_pixels = pixels
        return self._watch_reserved_pixels or set()

    def _watch_tree_overlaps_reserved(self, tx, ty):
        if not self._watch:
            return False
        return bool(set(tree_sprite_pixels(self, tx, ty)) & self._reserved_pixels())

    def draw_ghost(self):
        """Dither loud roads and the selection through anything drawn in front of them."""
        for (x, y), c in self.ghost.items():
            if self.fb.get(x, y) != c and (x + y) % 2 == 0:
                self.fb.set(x, y, c)

    # --- ground -----------------------------------------------------------

    def draw_ground(self, tx, ty, sx, sy):
        m, fb = self.m, self.fb
        kind = m.kind(tx, ty)
        bx, by = sx - self.ox, sy - self.oy
        wear = min(1.0, m.wear.get((tx, ty), 0) / WEAR_FULL)
        hot = (tx, ty) in m.hot
        segs = self.segments.get((tx, ty))
        tree = (tx, ty) in m.trees
        shadow = (tx, ty) in m.shadow
        plot = self.plot_of.get((tx, ty))
        for dx, dy in iso.TILE_MASK:
            wx, wy = LOCAL[(dx, dy)]
            gx, gy = bx + dx, by + dy
            c = self.ground_pixel(kind, tx, ty, dx, dy, gx, gy, wx, wy)
            if plot:
                c = self.plot_pixel(plot, tx, ty, wx, wy, gx, gy, c)
            if wear and hash2(tx, ty, dx, dy, 3) % 100 < wear * 45:
                c = shade(c, 0.8)
            if hot:
                if hash2(tx, ty, dx, dy, 9) % 6 == 0:
                    c = CRACK
                else:
                    glow = 0.5 + 0.5 * math.sin(self.t * 5 + gx * 0.6 + gy * 0.9)
                    c = mix(c, SHIMMER, 0.15 + 0.3 * glow)
            loud = False
            if segs:
                c, loud = self.road_pixel(segs, wx, wy, c)
            if (tx, ty) in self.roundabouts:
                r = math.hypot(wx - 0.5, wy - 0.5)
                if r < 0.2:
                    c, loud = ground_color("grass", tx, ty, dx, dy, gx, gy, self.t), False
                elif r < 0.36:
                    c, loud = ROAD_COLORS[R.CYCLE], True
            if tree and ((dx + 0.5) / 4.6) ** 2 + ((dy - 2.6) / 2.1) ** 2 < 1:
                c = shade(c, 0.74)
            if shadow:
                c = shade(c, 0.62)
            if self.cursor == (tx, ty) and min(wx, wy, 1 - wx, 1 - wy) < 0.09:
                c, loud = SELECT, True
            fb.set(sx + dx, sy + dy, c)
            if loud:
                self.ghost[(sx + dx, sy + dy)] = c
        self.draw_skirt(tx, ty, sx, sy)

    def ground_pixel(self, kind, tx, ty, dx, dy, gx, gy, wx, wy):
        if kind in ("grass", "water"):
            return ground_color(kind, tx, ty, dx, dy, gx, gy, self.t)
        if kind in ("street", "avenue"):
            c = ground_color("plaza", tx, ty, dx, dy, gx, gy, self.t)
            return shade(c, 0.9) if kind == "avenue" else c
        if kind in ("quay", "dock"):
            return shade(PLANK, 0.7) if int(wy * 4 % 1 * 10) == 0 else PLANK
        if kind == "vacant":
            return RUBBLE if hash2(tx, ty, dx, dy, 5) % 5 == 0 else DIRT[hash2(tx, ty, dx, dy) & 3]
        if kind == "plot":
            return mix(ground_color("grass", tx, ty, dx, dy, gx, gy, self.t), UNKNOWN, 0.6)
        return DIRT[hash2(tx, ty, dx, dy) & 3]

    def plot_pixel(self, plot, tx, ty, wx, wy, gx, gy, c):
        x, y, size = plot
        edge = ((tx == x and wx < 0.17) or (tx == x + size - 1 and wx > 0.83)
                or (ty == y and wy < 0.17) or (ty == y + size - 1 and wy > 0.83))
        return OUTLINE if edge and (gx + gy) // 2 % 2 == 0 else c

    def road_pixel(self, segs, wx, wy, c):
        """The pixel's colour, and whether a loud road drew it."""
        loud = False
        for kind, weight, dirs in segs:
            hw = R.half_width(kind, weight)
            if _on_road(dirs, wx, wy, hw):
                edge = hw >= 0.2 and not _on_road(dirs, wx, wy, hw - 0.07)
                c = shade(ROAD_COLORS[kind], 0.82) if edge else ROAD_COLORS[kind]
                loud = kind in LOUD_ROADS
        return c, loud

    def draw_skirt(self, tx, ty, sx, sy):
        right_edge = tx == self.m.width - 1
        front_edge = ty == self.m.height - 1
        if not (right_edge or front_edge):
            return
        for dx, bottom in iso.COLUMN_BOTTOM.items():
            if (dx >= -1 and right_edge) or (dx <= 0 and front_edge):
                right_face = dx >= 0 if (right_edge and front_edge) else right_edge
                f = 0.78 if right_face else 1.0
                for i in range(1, SKIRT_DEPTH + 1):
                    c = SKIRT_LIP if i == 1 else shade(SKIRT, 1.0 - i * 0.05)
                    self.fb.set(sx + dx, sy + bottom + i, shade(c, f))

    # --- buildings --------------------------------------------------------

    def draw_warehouse(self, w, tx, ty, sx, sy):
        self.draw_box(w, tx, ty, sx, sy, WAREHOUSE_H, WAREHOUSE_WALL, WAREHOUSE_ROOF,
                      self.warehouse_wall)

    def draw_cake(self, b):
        """A tier per function, biggest at the bottom, then the roof; windows wait for glaze."""
        sx, sy = self.centre_px(b)
        sy -= self._drop_off.get(b.module, 0)
        shadow = 0.66 if any(t in self.m.shadow for t in b.tiles()) else 1.0
        wall = WALLS[hash2(b.x, b.y) & 3]
        glass = self.glass(b)
        for i, t in enumerate(b.stack):
            c = AMBER if t.amber else shade(wall, 1.0 if i % 2 == 0 else 0.84)
            weeds = i == 0 and problems.ABANDONED in b.problems
            self.tier((b.module, i), sx, sy, t.half, t.z0, t.z1, shade(c, shadow), weeds=weeds)
            self.planned += [((b.module, i), face, [(sx + dx, sy + dy) for dx, dy in pixels], glass)
                             for face, pixels in cake.windows(t.half, t.z0, t.z1)]
        top = b.stack[-1]
        roof = FOCUS_ROOF if b.module in self.focused else self.roofs.get(b.district, ROOFS[-1])
        self.tier((b.module, "roof"), sx, sy, top.half, top.z1, top.z1 + ROOF,
                  shade(roof, shadow), rim=b is self.selected)
        if problems.FIRE in b.problems:
            self.draw_fire(b)

    def draw_site(self, path, tx, ty):
        sx, sy = iso.to_screen(tx + 0.5, ty + 0.5)
        self.tier((path, 0), round(sx) + self.ox, round(sy) + self.oy,
                  cake.half_width(1, SITE_WIDTH), 0, SITE_HEIGHT, SITE)

    def tier(self, key, sx, sy, half, z0, z1, c, rim=False, weeds=False):
        """One block in whole pixels, each recorded as its wall's for glaze and focus shading."""
        walls = {"left": shade(c, 0.95), "right": shade(c, 0.74)}
        top = shade(c, 1.08)
        for face, dx, t in cake.wall_columns(half):
            x = sx + dx
            for k in range(z0, z1):
                wc = shade(walls[face], 0.6) if k == z0 else walls[face]
                if weeds and k <= z0 + 1 and hash2(x, k, 7) % 3 == 0:
                    wc = WEED
                self.paint(x, sy + t // 2 - k, wc, key, face)
            low, high = sy - t // 2 - z1, sy + t // 2 - z1
            for y in range(low, high + 1):
                edge = rim and (t == 0 or y in (low, high))
                self.paint(x, y, SELECT if edge else top, key, "top")
                if edge:
                    self.ghost[(x, y)] = SELECT

    def paint(self, x, y, c, key, face):
        if 0 <= x < self.fb.w and 0 <= y < self.fb.h:
            self.fb.rows[y][x] = c
            self.owner[(x, y)] = (key, face, c)

    def glass(self, b):
        return GLASS[window_kind(b)]

    def glaze(self):
        """Paint each window only if every pixel of it is still its own wall: whole or not at all."""
        for key, face, pixels, glass in self.planned:
            if all(self._own(p, key, face) for p in pixels):
                pane = glass if face == "left" else shade(glass, 0.82)
                for x, y in pixels:
                    self.paint(x, y, pane, key, face)

    def shade_by_focus(self):
        """Darken every building pixel still showing by how far its module is from the focus."""
        if self.dim is None:
            return
        levels = {}
        for (x, y), ((module, _), _, c) in self.owner.items():
            if module not in self.m.buildings:
                continue
            if module not in levels:
                levels[module] = self.dim(module)
            if levels[module] < 1 and c != SELECT and self.fb.rows[y][x] == c:
                self.fb.rows[y][x] = shade(c, levels[module])

    def _own(self, p, key, face):
        o = self.owner.get(p)
        return o is not None and o[:2] == (key, face) and self.fb.get(*p) == o[2]

    def draw_box(self, b, tx, ty, sx, sy, height, wall, roof, facade):
        right_same = tx + 1 < b.x + b.size
        front_same = ty + 1 < b.y + b.size
        hx = height if right_same else 0
        hy = height if front_same else 0
        dim = 0.66 if (tx, ty) in self.m.shadow else 1.0
        wall_l, wall_r = shade(wall, 0.96 * dim), shade(wall, 0.74 * dim)
        for dx, bottom in iso.COLUMN_BOTTOM.items():
            for k in range(height):
                if dx < 0:
                    left = not (dx == -1 and k < hy)
                else:
                    left = dx == 0 and k < hx
                c = wall_l if left else wall_r
                if k == 0:
                    c = shade(c, 0.7)
                if left and dx < 0 and not front_same:
                    c = facade(b, "y", tx, ty, dx + 5, k, height, c)
                elif not left and dx >= 0 and not right_same:
                    c = facade(b, "x", tx, ty, dx, k, height, c)
                self.fb.set(sx + dx, sy + bottom - k, c)
        rim = SELECT if b is self.selected else shade(roof, 1.15)
        for dx, dy in iso.TILE_MASK:
            wx, wy = LOCAL[(dx, dy)]
            edge = ((tx == b.x and wx < 0.12) or (tx == b.x + b.size - 1 and wx > 0.88)
                    or (ty == b.y and wy < 0.12) or (ty == b.y + b.size - 1 and wy > 0.88))
            self.fb.set(sx + dx, sy + dy - height, rim if edge else shade(roof, dim))
            if edge and b is self.selected:
                self.ghost[(sx + dx, sy + dy - height)] = SELECT

    def warehouse_wall(self, w, face, tx, ty, u, k, height, c):
        if face == "y" and 1 <= u <= 4 and 1 <= k <= 6:
            return (70, 76, 88)
        return shade(c, 0.9) if u % 2 else c

    def draw_fire(self, b):
        cx, cy = self.centre_px(b)
        cy -= height_px(b)
        frame = int(self.t * 10)
        for i in range(-b.size * 3, b.size * 3):
            flame = 2 + hash2(i, frame, b.x) % (3 + b.size)
            for k in range(flame):
                self.fb.set(cx + i, cy - k, FLAMES[min(2, k * 3 // flame)])
        for i in range(10):
            phase = (self.t * 0.25 + i / 10) % 1.0
            px = cx + round(math.sin(phase * 6 + i) * 2 + phase * 10)
            py = cy - 6 - round(phase * 56)
            size = 2 if phase < 0.4 else 3
            col = mix(SMOKE, (168, 168, 176), phase)
            for ax in range(size):
                for ay in range(size):
                    self.fb.set(px + ax, py - ay, col)

    def draw_annex(self, module, sx, sy):
        pixels = [(dx, dy) for dx, dy in iso.TILE_MASK
                  if LOCAL[(dx, dy)][0] < 0.45 and LOCAL[(dx, dy)][1] < 0.5]
        bottoms = {}
        for dx, dy in pixels:
            bottoms[dx] = max(bottoms.get(dx, dy), dy)
        key = (module, "annex")
        for dx, bottom in bottoms.items():
            wx, wy = LOCAL[(dx, bottom)]
            c = shade(ANNEX_WALL, 0.96 if 0.5 - wy < 0.45 - wx else 0.74)
            for k in range(ANNEX_H):
                self.paint(sx + dx, sy + bottom - k, shade(c, 0.7) if k == 0 else c, key, "annex")
        for dx, dy in pixels:
            self.paint(sx + dx, sy + dy - ANNEX_H, ANNEX_ROOF, key, "annex")

    # --- props and trees --------------------------------------------------

    def draw_tree(self, tx, ty, sx, sy):
        seed = tx * 31 + ty * 17
        kind = "bush" if (tx, ty) in self.m.bushes else ("pine", "round")[seed % 2]
        for dx, dy, c in sprites.tree(kind, seed):
            self.fb.set(sx + dx, sy + iso.HALF_H + dy, c)

    def draw_prop(self, prop, sx, sy):
        fb = self.fb
        if prop == "gate":
            ends = [local_to_screen(0.12, 0.5), local_to_screen(0.88, 0.5)]
            for ex, ey in ends:
                for k in range(9):
                    fb.set(sx + ex, sy + ey - k, STONE_GATE)
            (ax, ay), (bx, by) = ends
            for i in range(bx - ax + 1):
                y = ay + round((by - ay) * i / max(1, bx - ax))
                fb.set(sx + ax + i, sy + y - 9, shade(STONE_GATE, 0.8))
                fb.set(sx + ax + i, sy + y - 10, STONE_GATE)
        elif prop in ("no entry", "notes"):
            px, py = local_to_screen(*((0.85, 0.2) if prop == "no entry" else (0.15, 0.2)))
            for k in range(5):
                fb.set(sx + px, sy + py - k, POST)
            face, mark = (NOTE, shade(NOTE, 0.6)) if prop == "notes" else (NO_ENTRY, WHITE)
            for i in range(-1, 3):
                for k in range(5, 8):
                    fb.set(sx + px + i, sy + py - k, mark if k == 6 and 0 <= i <= 1 else face)


def shrink(fb, factor):
    """The whole town at 1/factor size, each pixel the average of a factor x factor block."""
    w, h = fb.w // factor, fb.h // factor
    out = Framebuffer(w, h, SEA)
    n = factor * factor
    for y in range(h):
        rows = fb.rows[y * factor:(y + 1) * factor]
        for x in range(w):
            r = g = b = 0
            for row in rows:
                for c in row[x * factor:(x + 1) * factor]:
                    r += c[0]
                    g += c[1]
                    b += c[2]
            out.rows[y][x] = (r // n, g // n, b // n)
    return out
