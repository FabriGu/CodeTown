"""Label text, styles and placement for text overlays (v3 section 3, no edge arrow)."""

from dataclasses import dataclass

import problems
import term

SHORT = 28
LIGHT = (236, 236, 240)
DARK_GREY = (58, 58, 66)
FIRE_FG = (255, 255, 255)
FIRE_BG = (140, 28, 28)
LOUD_FG = (40, 40, 48)
LOUD_BG = (255, 180, 60)
AGENT = (236, 236, 240), (58, 58, 66)
LOUD_KINDS = frozenset({problems.TOWER, problems.CYCLE, problems.BACKWARDS, problems.HOTSPOT})


def shorten(path):
    if len(path) <= SHORT:
        return path
    return "…" + path[-(SHORT - 1):]


def style_name(roof):
    return LIGHT, DARK_GREY


def style_fire():
    return FIRE_FG, FIRE_BG


def style_loud():
    return LOUD_FG, LOUD_BG


def style_district(roof):
    return roof, DARK_GREY


def style_agent(fg, bg):
    return fg, bg


@dataclass(frozen=True)
class LabelRequest:
    text: str
    anchor_x: float
    anchor_y: int
    fg: tuple[int, int, int]
    bg: tuple[int, int, int]
    bold: bool = False
    priority: int = 0


def _reason(rows, kind):
    for p in rows:
        if p.kind == kind:
            return p.reason
    return kind


def selected_building(building, problem_rows, roof):
    path = shorten(building.module)
    kinds = building.problems
    if problems.FIRE in kinds:
        fg, bg = style_fire()
        text = f"▲ {path}  {_reason(problem_rows, problems.FIRE)}"
        return [LabelRequest(text, 0.0, 0, fg, bg, priority=0)]
    for kind in (problems.TOWER, problems.CYCLE, problems.BACKWARDS, problems.HOTSPOT):
        if kind in kinds:
            fg, bg = style_loud()
            text = f"◆ {path}  {kind}: {_reason(problem_rows, kind)}"
            return [LabelRequest(text, 0.0, 0, fg, bg, priority=0)]
    fg, bg = style_name(roof)
    dot = LabelRequest("●", 0.0, 0, roof, bg, priority=0)
    name = LabelRequest(f" {path}", 0.0, 0, fg, bg, priority=0)
    return [dot, name]


def _cells(text, col, row):
    for i, _ in enumerate(text):
        yield col + i, row


def _fits(text, col, row, width, height, taken):
    if row < 0 or row >= height:
        return False
    end = col + len(text)
    if col < 0 or end > width:
        return False
    return not any(c in taken for c in _cells(text, col, row))


def _clamp_col(text, col, width):
    end = col + len(text)
    if col < 0:
        col = 0
    if end > width:
        col = max(0, width - len(text))
    return col


def _groups(requests):
    """Requests sharing anchor and priority are one label (e.g. coloured dot + path)."""
    if not requests:
        return
    group = [requests[0]]
    for req in requests[1:]:
        if req.anchor_x == group[0].anchor_x and req.anchor_y == group[0].anchor_y and req.priority == group[0].priority:
            group.append(req)
        else:
            yield group
            group = [req]
    yield group


def place(requests, width, height, taken=frozenset()):
    taken = set(taken)
    out = []
    term_w = width * 2
    for group in _groups(requests):
        total = sum(len(r.text) for r in group)
        col = int(round(group[0].anchor_x * 2)) - total // 2
        row = group[0].anchor_y
        placed = None
        for lift in (0, 1, 2):
            try_row = row - lift
            try_col = _clamp_col(" " * total, col, term_w)
            if _fits(" " * total, try_col, try_row, term_w, height, taken):
                placed = (try_col, try_row)
                break
        if placed is None:
            continue
        try_col, try_row = placed
        at = try_col
        for req in group:
            taken |= set(_cells(req.text, at, try_row))
            out.append(term.Overlay(at / 2, try_row, req.text, req.fg, req.bg, req.bold))
            at += len(req.text)
    return out
