"""A building as a wedding cake: one floor per function, biggest at the bottom, and its windows.

Pure geometry in whole pixels, relative to the building's centre column and ground row, so any
renderer can place it. Nothing here reads the repository or draws.
"""

from dataclasses import dataclass

import iso

LONG_FUNCTION = 100
PX_PER_COMPLEXITY = 0.7
MIN_THICKNESS = 2
MIN_WIDTH = 0.35
WINDOW_H = 2
WINDOW_ROW_GAP = 2
# In two-column steps from each corner, not pixels.
WINDOW_SIDE = 1
WINDOW_BOTTOM = 2
WINDOW_TOP = 1


@dataclass(frozen=True)
class Tier:
    half: int
    z0: int
    z1: int
    amber: bool


def half_width(size, w):
    """A tier's half width in pixels: at most the lot's, and 2 more than a multiple of 4.

    Walls step one pixel every two columns, so a wall is laid out in two-column steps. An odd
    number of steps is what lets windows sit exactly centred, with equal margins at both corners.
    """
    return max(2, (int(size * iso.HALF_W * w) - 2) // 4 * 4 + 2)


def thickness(complexity):
    return max(MIN_THICKNESS, round(complexity * PX_PER_COMPLEXITY))


def tiers(functions, size, module_complexity):
    """Biggest function at the bottom, each tier never wider than the one under it.

    functions is (name, lines, complexity) per function; with none, the module is one tier.
    """
    if not functions:
        return [Tier(half_width(size, 1.0), 0, thickness(module_complexity), False)]
    ordered = sorted(functions, key=lambda f: (-f[1], -f[2], f[0]))
    biggest = ordered[0][1]
    found, z = [], 0
    for _, lines, complexity in ordered:
        w = MIN_WIDTH + (1 - MIN_WIDTH) * lines / biggest
        top = z + thickness(complexity)
        found.append(Tier(half_width(size, w), z, top, lines >= LONG_FUNCTION))
        z = top
    return found


def wall_columns(half):
    """(wall, column, distance from the outer corner) for every wall column of a tier."""
    for t in range(half):
        yield "left", t - half, t
        yield "right", half - 1 - t, t


def slots(length, low, high, size, gap):
    """Starts of as many size-long openings as fit in length, centred between the two margins."""
    room = length - low - high
    n = max(0, (room + gap) // (size + gap))
    used = n * size + (n - 1) * gap if n else 0
    first = low + (room - used) // 2
    return [first + i * (size + gap) for i in range(n)]


def windows(half, z0, z1):
    """(wall, pixels) per window, the same on both walls; none when a window doesn't fit.

    Pixels are (column, row) from the building's centre column and ground row, rows growing
    downwards as on screen.
    """
    steps = slots(half // 2, WINDOW_SIDE, WINDOW_SIDE, 1, 1)
    rows = slots(z1 - z0, WINDOW_BOTTOM, WINDOW_TOP, WINDOW_H, WINDOW_ROW_GAP)
    return [(wall, [(col, t // 2 - k)
                    for w, col, t in wall_columns(half) if w == wall and t // 2 == step
                    for k in range(z0 + row, z0 + row + WINDOW_H)])
            for step in steps for row in rows for wall in ("left", "right")]
