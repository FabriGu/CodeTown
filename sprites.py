"""Pixel art. Sprites are lists of strings; '.' is transparent.

Sprite coordinates are relative to an anchor on the ground: x=0 is the
column just right of centre, y=0 is the ground row, negative y is up.
"""

import random

CLAWD = {"O": (217, 119, 87), "o": (178, 92, 64), "E": (28, 24, 22)}

_CLAWD_BODY = [
    ".OOOOOOO.",
    ".OOOOOOO.",
    "OOOOOOOOO",
    ".ooooooo.",
]
_CLAWD_LEGS = {
    0: [".o.o.o.o."],
    1: [".o.o.o.o.", ".o...o..."],
    2: [".o.o.o.o.", "...o...o."],
}
# Eyes look the way Clawd walks; walking away (-x or -y) shows its back.
_CLAWD_EYES = {(0, 1): (2, 5), (1, 0): (3, 6)}


def parse(rows, palette):
    return [(x, y, palette[ch]) for y, row in enumerate(rows)
            for x, ch in enumerate(row) if ch != "."]


def clawd_rows(facing, frame):
    rows = list(_CLAWD_BODY)
    eyes = _CLAWD_EYES.get(tuple(facing))
    if eyes:
        r = list(rows[1])
        for c in eyes:
            r[c] = "E"
        rows[1] = "".join(r)
    return rows + _CLAWD_LEGS[frame]


def villager_rows(facing, frame):
    front = tuple(facing) in _CLAWD_EYES
    return [
        ".HHH.",
        "HHHHH",
        "HESEH" if front else "HHHHH",
        ".SSS." if front else ".HHH.",
        "CCCCC",
        "SCCCS",
        ".PPP.",
        {0: ".P.P.", 1: "P..P.", 2: ".P..P"}[frame],
    ]


def villager_palette(spec):
    return {"H": spec["hair"], "S": spec["skin"], "E": (30, 26, 24),
            "C": spec["shirt"], "P": spec["pants"]}


TRUNK = (110, 74, 48)
TRUNK_DARK = (84, 54, 36)
LEAF = [(40, 100, 52), (58, 138, 64), (96, 176, 80)]
PINE = [(28, 80, 58), (42, 110, 70), (70, 146, 86)]


def _blob(pixels, rnd, rx, ry, cy, palette):
    for py in range(int(cy - ry) - 1, int(cy + ry) + 2):
        for px in range(-int(rx) - 2, int(rx) + 2):
            nx = (px + 0.5) / rx
            ny = (py + 0.5 - cy) / ry
            if nx * nx + ny * ny > 1 + (rnd.random() - 0.5) * 0.3:
                continue
            light = -0.55 * nx - 0.8 * ny + (rnd.random() - 0.5) * 0.4
            tone = 0 if light < -0.3 else 1 if light < 0.4 else 2
            pixels.append((px, py, palette[tone]))


def _trunk(pixels, height):
    for k in range(height):
        pixels.append((-1, -k, TRUNK))
        pixels.append((0, -k, TRUNK_DARK))


def round_tree(seed):
    rnd = random.Random(seed)
    pixels = []
    _trunk(pixels, 5)
    rx, ry = 4.6 + rnd.random() * 0.9, 4.3 + rnd.random() * 0.7
    _blob(pixels, rnd, rx, ry, -(4 + ry), LEAF)
    return pixels


def pine_tree(seed):
    rnd = random.Random(seed)
    pixels = []
    _trunk(pixels, 4)
    for r in range(15):
        tier, j = min(2, r // 5), r % 5
        hw = 1 + j * 0.8 + tier * 1.2
        py = -18 + r
        for px in range(-6, 6):
            c = px + 0.5
            if abs(c) > hw:
                continue
            if j == 4 or c > hw * 0.35:
                tone = 0
            elif c < -hw * 0.3 or rnd.random() < 0.08:
                tone = 2
            else:
                tone = 1
            pixels.append((px, py, PINE[tone]))
    return pixels


def bush(seed):
    rnd = random.Random(seed)
    pixels = []
    _blob(pixels, rnd, 4.8, 2.8, -2.4, LEAF)
    return pixels


_cache = {}


def tree(kind, seed):
    key = (kind, seed)
    if key not in _cache:
        _cache[key] = {"round": round_tree, "pine": pine_tree, "bush": bush}[kind](seed)
    return _cache[key]
