"""Draws the town into an RGB framebuffer, back to front."""

import math

import iso
import sprites
from world import WALL_H

SKY_TOP = (34, 40, 66)
SKY_BOTTOM = (14, 18, 32)
GHOST = (255, 214, 196)

GRASS = [(86, 156, 70), (92, 164, 74), (80, 148, 66), (98, 170, 78)]
DIRT = [(178, 142, 98), (170, 134, 92), (186, 150, 104), (164, 128, 88)]
STONE = [(164, 160, 166), (152, 148, 156), (174, 170, 174), (144, 140, 150)]
GROUT = (116, 112, 122)
WATER_DEEP = (44, 98, 168)
WATER = (60, 124, 196)
WATER_HI = (156, 210, 242)
FLOWERS = [(236, 80, 90), (250, 210, 70), (245, 245, 245), (232, 130, 200), (150, 128, 240)]
SKIRT_LIP = (66, 118, 56)
SKIRT = (122, 88, 60)
WOOD = (178, 128, 76)
WOOD_DARK = (122, 82, 50)
DOOR = (100, 62, 40)
KNOB = (232, 192, 84)
GLASS = (255, 222, 140)
POLE = (58, 58, 70)
POLE_DARK = (40, 40, 50)
LAMP = (255, 232, 150)
BRICK = (150, 72, 60)
SMOKE = (206, 206, 214)
SKIRT_DEPTH = 6

# Local world coordinates (0..1) of each pixel in a tile.
LOCAL = {}
for _dx, _dy in iso.TILE_MASK:
    _u, _v = (_dx + 0.5) / iso.HALF_W, (_dy + 0.5) / iso.HALF_H
    LOCAL[(_dx, _dy)] = ((_v + _u) / 2, (_v - _u) / 2)


def shade(c, f):
    return (min(255, int(c[0] * f)), min(255, int(c[1] * f)), min(255, int(c[2] * f)))


def mix(a, b, t):
    return (int(a[0] + (b[0] - a[0]) * t), int(a[1] + (b[1] - a[1]) * t),
            int(a[2] + (b[2] - a[2]) * t))


def hash2(*vals):
    h = 2166136261
    for v in vals:
        h = ((h ^ (v & 0xFFFFFFFF)) * 16777619) & 0xFFFFFFFF
    h ^= h >> 13
    h = (h * 0x5BD1E995) & 0xFFFFFFFF
    return h ^ (h >> 15)


class Framebuffer:
    def __init__(self, w, h, bg=(0, 0, 0)):
        self.w, self.h = w, h
        self.rows = [[bg] * w for _ in range(h)]

    def set(self, x, y, c):
        if 0 <= x < self.w and 0 <= y < self.h:
            self.rows[y][x] = c

    def get(self, x, y):
        if 0 <= x < self.w and 0 <= y < self.h:
            return self.rows[y][x]
        return None

    def darken(self, x, y, f):
        c = self.get(x, y)
        if c is not None:
            self.rows[y][x] = shade(c, f)


def ground_color(kind, tx, ty, dx, dy, gx, gy, t):
    h = hash2(tx, ty, dx, dy)
    if kind == "water":
        wave = math.sin(t * 2.2 + gx * 0.55 + gy * 1.1) + math.sin(t * 1.3 - gx * 0.3 + gy * 0.8)
        if wave > 1.55:
            return WATER_HI
        return WATER if wave > -0.3 else WATER_DEEP
    if kind == "path":
        return (140, 112, 80) if h % 13 == 0 else DIRT[h & 3]
    if kind == "plaza":
        wx, wy = LOCAL[(dx, dy)]
        ax, ay = wx * 2, wy * 2
        if ax % 1 < 0.16 or ay % 1 < 0.16:
            return GROUT
        return STONE[hash2(tx, ty, int(ax), int(ay)) & 3]
    c = GRASS[h & 3]
    if kind == "flowers" and hash2(tx, ty, dx, dy, 7) % 8 == 0:
        return FLOWERS[(h >> 3) % len(FLOWERS)]
    if (h >> 5) % 11 == 0:
        return shade(c, 0.84)
    return c


class Scene:
    def __init__(self, game, w, h):
        self.game = game
        self.world = game.world
        self.t = game.time
        self.fb = Framebuffer(w, h)
        for y in range(h):
            row_color = mix(SKY_TOP, SKY_BOTTOM, y / max(1, h - 1))
            self.fb.rows[y] = [row_color] * w
        px, py = game.player.pos()
        psx, psy = iso.to_screen(px, py)
        self.ox = w // 2 - round(psx)
        self.oy = int(h * 0.62) - round(psy) - iso.HALF_H
        self.ghost = []

    def screen(self, tx, ty):
        sx, sy = iso.to_screen(tx, ty)
        return sx + self.ox, sy + self.oy

    def visible(self, sx, sy):
        return -16 < sx < self.fb.w + 16 and -8 < sy < self.fb.h + 26

    def render(self):
        w = self.world
        tiles = [(tx, ty) for ty in range(w.height) for tx in range(w.width)]
        drawables = []
        for tx, ty in tiles:
            sx, sy = self.screen(tx, ty)
            if not self.visible(sx, sy):
                continue
            self.draw_ground(tx, ty, sx, sy)
            if w.building_at(tx, ty) or w.feature(tx, ty):
                drawables.append((tx + ty, 0, tx, lambda a=tx, b=ty, c=sx, d=sy: self.draw_object(a, b, c, d)))
        for actor in self.game.actors():
            depth = max(actor.x + actor.y, actor.from_x + actor.from_y)
            drawables.append((depth, 1, actor.x, lambda a=actor: self.draw_actor(a)))
        drawables.sort(key=lambda d: d[:3])
        for *_, draw in drawables:
            draw()
        self.draw_ghost()
        return self.fb

    # --- ground -----------------------------------------------------------

    def draw_ground(self, tx, ty, sx, sy):
        fb, w = self.fb, self.world
        kind = w.ground(tx, ty)
        bx, by = sx - self.ox, sy - self.oy
        shadowed = w.feature(tx, ty) == "tree"
        for dx, dy in iso.TILE_MASK:
            c = ground_color(kind, tx, ty, dx, dy, bx + dx, by + dy, self.t)
            if shadowed and ((dx + 0.5) / 4.6) ** 2 + ((dy - 2.6) / 2.1) ** 2 < 1:
                c = shade(c, 0.74)
            fb.set(sx + dx, sy + dy, c)
        right_edge = tx == w.width - 1
        front_edge = ty == w.height - 1
        if right_edge or front_edge:
            for dx, bottom in iso.COLUMN_BOTTOM.items():
                # The two bottom-vertex columns bridge into the next edge tile.
                if (dx >= -1 and right_edge) or (dx <= 0 and front_edge):
                    right_face = dx >= 0 if (right_edge and front_edge) else right_edge
                    f = 0.78 if right_face else 1.0
                    for i in range(1, SKIRT_DEPTH + 1):
                        c = SKIRT_LIP if i == 1 else shade(SKIRT, 1.0 - i * 0.05)
                        fb.set(sx + dx, sy + bottom + i, shade(c, f))

    # --- objects ----------------------------------------------------------

    def draw_object(self, tx, ty, sx, sy):
        b = self.world.building_at(tx, ty)
        if b:
            self.draw_building_tile(b, tx, ty, sx, sy)
            return
        feature = self.world.feature(tx, ty)
        ax, ay = sx, sy + iso.HALF_H
        if feature == "tree":
            w = self.world
            seed = tx * 31 + ty * 17
            edge = tx == w.width - 1 or ty == w.height - 1
            kind = "bush" if edge else ("pine" if seed % 3 == 0 else "round")
            self.blit(sprites.tree(kind, seed), ax, ay)
        elif feature == "fence":
            self.draw_fence(tx, ty, ax, ay)
        elif feature == "lamp":
            self.draw_lamp(tx, ty, ax, ay)
        elif feature == "sign":
            self.draw_sign(ax, ay)
        elif feature == "fountain":
            self.draw_fountain(sx, sy)

    def blit(self, pixels, ax, ay):
        for dx, dy, c in pixels:
            self.fb.set(ax + dx, ay + dy, c)

    def draw_building_tile(self, b, tx, ty, sx, sy):
        fb, w = self.fb, self.world
        h = b.height_at(tx, ty)
        right_same = w.building_at(tx + 1, ty) is b
        front_same = w.building_at(tx, ty + 1) is b
        hx = b.height_at(tx + 1, ty) if right_same else 0
        hy = b.height_at(tx, ty + 1) if front_same else 0
        wall_l, wall_r = shade(b.wall, 0.96), shade(b.wall, 0.74)
        roof_l, roof_r = shade(b.roof, 0.8), shade(b.roof, 0.6)
        door_face = b.door_face if b.door == (tx, ty) else None
        for dx, bottom in iso.COLUMN_BOTTOM.items():
            for k in range(h):
                # Columns at the bottom vertex continue the neighbouring tile's wall.
                if dx < 0:
                    left = not (dx == -1 and k < hy)
                else:
                    left = dx == 0 and k < hx
                if k >= WALL_H:
                    c = roof_l if left else roof_r
                else:
                    c = wall_l if left else wall_r
                    if k == 0:
                        c = shade(c, 0.68)
                    elif k == WALL_H - 1:
                        c = shade(c, 0.8)
                    if left and dx < 0 and not front_same:
                        c = self.wall_detail(c, dx + 5, k, door_face == "y")
                    elif not left and dx >= 0 and not right_same:
                        c = self.wall_detail(c, dx, k, door_face == "x")
                fb.set(sx + dx, sy + bottom - k, c)
        ridge_x = (b.x1 - b.x0) >= (b.y1 - b.y0)
        for dx, dy in iso.TILE_MASK:
            wx, wy = LOCAL[(dx, dy)]
            stripe = int((wy if ridge_x else wx) * 4) % 2
            fb.set(sx + dx, sy + dy - h, shade(b.roof, 0.9) if stripe else b.roof)
        if b.chimney == (tx, ty):
            self.draw_chimney(sx, sy + iso.HALF_H - h)

    def wall_detail(self, c, u, k, door):
        if door:
            if 1 <= u <= 3 and 1 <= k <= 5:
                return KNOB if (u == 3 and k == 3) else DOOR
            return c
        if 1 <= u <= 3 and 3 <= k <= 4:
            return shade(c, 0.7) if u == 2 else GLASS
        return c

    def draw_chimney(self, cx, cy):
        fb = self.fb
        for k in range(5):
            fb.set(cx + 1, cy - k, BRICK)
            fb.set(cx + 2, cy - k, shade(BRICK, 0.72))
        fb.set(cx + 1, cy - 5, (60, 50, 50))
        fb.set(cx + 2, cy - 5, (60, 50, 50))
        for i in range(3):
            phase = (self.t * 0.35 + i / 3) % 1.0
            px = cx + 1 + int(math.sin(phase * 5 + i) * 1.5 + phase * 4)
            py = cy - 7 - int(phase * 12)
            size = 2 if phase > 0.3 else 1
            col = mix(SMOKE, SKY_TOP, phase * 0.8)
            for sx in range(size):
                for sy in range(size):
                    fb.set(px + sx, py - sy, col)

    def draw_fence(self, tx, ty, ax, ay):
        fb, w = self.fb, self.world
        for (nx, ny), (sx, sy) in (((1, 0), (1, 0.5)), ((0, 1), (-1, 0.5))):
            if w.feature(tx + nx, ty + ny) != "fence":
                continue
            for i in range(iso.TILE_W // 2 + 1):
                x = ax - 1 + int(i * sx) if sx > 0 else ax + int(i * sx)
                y = ay + int(i * sy)
                fb.set(x, y - 2, WOOD)
                fb.set(x, y - 4, WOOD)
        for k in range(6):
            fb.set(ax - 1, ay - k, WOOD)
            fb.set(ax, ay - k, WOOD_DARK)

    def draw_lamp(self, tx, ty, ax, ay):
        fb = self.fb
        for k in range(9):
            fb.set(ax - 1, ay - k, POLE)
            fb.set(ax, ay - k, POLE_DARK)
        flicker = hash2(int(self.t * 8), tx, ty) % 17 == 0
        glow = shade(LAMP, 0.75) if flicker else LAMP
        for dx in (-2, -1, 0, 1):
            fb.set(ax + dx, ay - 9, glow)
            fb.set(ax + dx, ay - 10, glow)
            fb.set(ax + dx, ay - 11, POLE_DARK)
        fb.set(ax - 1, ay - 12, POLE_DARK)
        fb.set(ax, ay - 12, POLE_DARK)

    def draw_sign(self, ax, ay):
        fb = self.fb
        for k in range(4):
            fb.set(ax - 1, ay - k, WOOD_DARK)
            fb.set(ax, ay - k, WOOD_DARK)
        for dx in range(-3, 3):
            for k in range(4, 8):
                fb.set(ax + dx, ay - k, (214, 174, 112) if k < 7 else WOOD)
        for dx in (-2, 0, 1):
            fb.set(ax + dx, ay - 5, WOOD_DARK)
        for dx in (-2, -1, 1):
            fb.set(ax + dx, ay - 6, WOOD_DARK)

    def draw_fountain(self, sx, sy):
        fb = self.fb
        h = 3
        for dx, bottom in iso.COLUMN_BOTTOM.items():
            for k in range(h):
                fb.set(sx + dx, sy + bottom - k, shade(STONE[0], 0.85 if dx < 0 else 0.66))
        for dx, dy in iso.TILE_MASK:
            wx, wy = LOCAL[(dx, dy)]
            inner = 0.2 < wx < 0.8 and 0.2 < wy < 0.8
            if inner:
                c = ground_color("water", 0, 0, dx, dy, sx + dx, sy + dy, self.t * 1.6)
            else:
                c = STONE[2]
            fb.set(sx + dx, sy + dy - h, c)
        cx, cy = sx, sy + iso.HALF_H - h
        for k in range(1, 4):
            fb.set(cx - 1, cy - k, STONE[1])
            fb.set(cx, cy - k, STONE[3])
        for k in range(4, 9):
            on = (int(self.t * 10) + k) % 3
            fb.set(cx - 1, cy - k, WATER_HI if on else WATER)
            fb.set(cx, cy - k, WATER if on else WATER_HI)
        for side in (-1, 1):
            phase = (self.t * 1.8 + (0.5 if side > 0 else 0)) % 1.0
            px = cx - 1 + side * (1 + int(phase * 3)) + (1 if side > 0 else 0)
            py = cy - 8 + int(phase * phase * 8)
            fb.set(px, py, WATER_HI)

    # --- actors -----------------------------------------------------------

    def draw_actor(self, actor):
        fx, fy = actor.pos()
        sx, sy = iso.to_screen(fx, fy)
        ax, ay = round(sx) + self.ox, round(sy) + self.oy + iso.HALF_H
        for dx in range(-4, 4):
            for dy in (0, 1):
                if ((dx + 0.5) / 4.5) ** 2 + ((dy - 0.3) / 1.3) ** 2 <= 1:
                    self.fb.darken(ax + dx, ay + dy, 0.72)
        frame = actor.walk_frame()
        if actor is self.game.player:
            rows = sprites.clawd_rows(actor.facing, frame)
            pixels = sprites.parse(rows, sprites.CLAWD)
            x0 = ax - 4
        else:
            rows = sprites.villager_rows(actor.facing, frame)
            pixels = sprites.parse(rows, sprites.villager_palette(actor.spec))
            x0 = ax - 2
        y0 = ay - len(rows) + 1
        for x, y, c in pixels:
            self.fb.set(x0 + x, y0 + y, c)
            if actor is self.game.player:
                self.ghost.append((x0 + x, y0 + y, c))

    def draw_ghost(self):
        """Dither Clawd's silhouette through anything drawn in front of it."""
        for x, y, c in self.ghost:
            if self.fb.get(x, y) != c and (x + y) % 2 == 0:
                self.fb.set(x, y, GHOST)


def render_scene(game, w, h):
    return Scene(game, w, h).render()
