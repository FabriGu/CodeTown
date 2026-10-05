"""Isometric projection. World +x runs down-right on screen, +y runs down-left.

Screen units are "pixels"; the terminal draws each pixel as two full blocks.
"""

HALF_W = 6
HALF_H = 3
TILE_W = HALF_W * 2
TILE_H = HALF_H * 2


def to_screen(x, y):
    """Screen position of a tile's top vertex."""
    return (x - y) * HALF_W, (x + y) * HALF_H


def _build_mask():
    mask = []
    for dy in range(TILE_H):
        for dx in range(-HALF_W, HALF_W):
            # Sample pixel centres; the +0.5 keeps samples off tile edges.
            u = (dx + 0.5) / HALF_W
            v = (dy + 0.5) / HALF_H
            wx, wy = (v + u) / 2, (v - u) / 2
            if 0 <= wx < 1 and 0 <= wy < 1:
                mask.append((dx, dy))
    return mask


TILE_MASK = _build_mask()

COLUMN_TOP = {}
COLUMN_BOTTOM = {}
for _dx, _dy in TILE_MASK:
    COLUMN_TOP[_dx] = min(COLUMN_TOP.get(_dx, _dy), _dy)
    COLUMN_BOTTOM[_dx] = max(COLUMN_BOTTOM.get(_dx, _dy), _dy)
