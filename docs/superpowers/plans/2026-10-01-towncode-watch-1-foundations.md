# Towncode watch Phase 1: overlays, labels, camera and frame rate — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add text overlays, label placement, camera easing and adaptive frame rate to `towncode view`, shippable on its own before watch or v3 point-and-click.

**Architecture:** `term.py` gains an `Overlay` type and composes labels into terminal rows alongside pixels. Pure `labels.py` turns building facts into styled label requests and places them without overlaps. A small `camera.py` eases focus in whole-town pixels; `viewer.py` drives the camera from cursor and n/p, picks 24/12 FPS from movement and draw time, and at street zoom passes one selected-building overlay through `Screen.frame`. `snapshot` stays pixel-only.

**Tech Stack:** Python 3, standard library only (Pillow only in mocks). Tests are `unittest` files at the repo root (`test_*.py`).

**Spec:** [docs/superpowers/specs/2026-10-01-towncode-watch-design.md](docs/superpowers/specs/2026-10-01-towncode-watch-design.md) (Phase 1: Foundations). Label text, placement and overlay composition from [docs/superpowers/specs/2026-10-01-codetown-point-and-click-design.md](docs/superpowers/specs/2026-10-01-codetown-point-and-click-design.md) §3 Labels (Text over pixels, Label kinds, Placement — not edge arrow, not Which labels show), §2 Camera, §7 Frame rate.

## Global Constraints

- Standard library only in product code (Pillow only in mocks).
- One visual property, one meaning (roof colour = district; do not repurpose colours).
- No emoji; single-width icon characters only: `●` district, `▲` fire, `◆` warning, `✓` fixed, `▸` action, `■` diff squares, arrows `← ↑ → ↓ ↖ ↗ ↘ ↙`.
- Module paths longer than 28 characters shortened from the left with `…`.
- Camera easing: `focus += (target − focus) × (1 − e^(−6.5·dt))`.
- Frame rate: 24 FPS while anything moves (camera gliding counts), 12 FPS when still; drop to 12 FPS if a frame takes more than 35 ms until movement ends.
- Do not edit `focus.py`, `cake.py`, `roles.py`, or `mock_roles.py`.
- The full test suite (463 tests today) must still pass after every task.
- Match existing naming, sparse comments, short docstrings, and `unittest` style in sibling tests.
- Run a single test file: `.venv/bin/python -m unittest test_NAME -v` from the repo root. Full suite: `.venv/bin/python -m unittest`.

---

### Task 1: Text overlays in term.py

**Files:**
- Modify: `term.py`
- Test: `test_term.py`

**Interfaces:**
- Consumes: `render.Framebuffer`, existing `encode_row`, `color_code`, `PIXEL`, `RESET`.
- Produces:
  - `term.Overlay(x: float, y: int, text: str, fg: tuple[int, int, int], bg: tuple[int, int, int], bold: bool = False)` — frozen dataclass; `x` may be half-pixel (`.5`); `y` is a framebuffer row index.
  - `term.pixel_col(x: float) -> int` — 0-based terminal column for overlay start (`int(x * 2) + 1` minus 1 for 0-based).
  - `term.compose_row(fb_row, overlays, truecolor) -> str` — pixel row plus overlays on that `y`, including half-pixel tail fill.
  - `term.Screen.frame(fb, status, overlays=()) -> str` — optional third argument; existing two-argument callers unchanged.

- [ ] **Step 1: Write the failing test**

Add to `test_term.py`:

```python
import term

LIGHT, DARK, RED, BLUE = (230, 230, 230), (58, 58, 66), (255, 0, 0), (0, 0, 255)


class OverlayTest(unittest.TestCase):
    def test_pixel_col_whole_and_half(self):
        self.assertEqual(term.pixel_col(0), 0)
        self.assertEqual(term.pixel_col(5), 10)
        self.assertEqual(term.pixel_col(5.5), 11)

    def test_compose_row_places_text_over_pixels(self):
        row = [RED, RED]
        ov = term.Overlay(0, 0, "Hi", LIGHT, DARK)
        out = term.compose_row(row, [ov], truecolor=True)
        self.assertIn("Hi", out)
        self.assertIn("38;2;230;230;230", out)
        self.assertIn("48;2;58;58;66", out)

    def test_half_pixel_tail_fills_with_pixel_colour(self):
        row = [RED, BLUE]
        ov = term.Overlay(0, 0, "A", LIGHT, DARK)
        out = term.compose_row(row, [ov], truecolor=True)
        self.assertEqual(out.count(term.PIXEL), 3)

    def test_only_overlay_change_redraws_the_row(self):
        s = term.Screen(truecolor=True)
        fb = fb_of([RED])
        s.frame(fb, [], [term.Overlay(0, 0, "a", LIGHT, DARK)])
        out = s.frame(fb, [], [term.Overlay(0, 0, "b", LIGHT, DARK)])
        self.assertIn("\x1b[1;1H", out)
        self.assertIn("b", out)

    def test_frame_without_overlays_still_works(self):
        s = term.Screen(truecolor=True)
        out = s.frame(fb_of([RED], [BLUE]), ["hi"])
        self.assertIn("\x1b[1;1H", out)
        self.assertIn("\x1b[3;1H", out)
        self.assertIn("hi", out)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m unittest test_term.OverlayTest -v`

Expected: FAIL (`AttributeError: module 'term' has no attribute 'Overlay'` or similar).

- [ ] **Step 3: Write minimal implementation**

Add near the top of `term.py` (after imports):

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class Overlay:
    x: float
    y: int
    text: str
    fg: tuple[int, int, int]
    bg: tuple[int, int, int]
    bold: bool = False


def pixel_col(x):
    return int(x * 2)


def _bg_code(c, truecolor):
    if truecolor:
        r, g, b = c
        return f"\x1b[48;2;{r};{g};{b}m"
    return f"\x1b[48;5;{rgb_to_256(c)}m"


def _style(fg, bg, bold, truecolor):
    bold_code = "\x1b[1m" if bold else ""
    return f"{bold_code}{color_code(fg, truecolor)}{_bg_code(bg, truecolor)}"


def compose_row(fb_row, overlays, truecolor):
    width = len(fb_row) * 2
    chars = [" "] * width
    for i, c in enumerate(fb_row):
        chars[i * 2:i * 2 + 2] = [PIXEL[0], PIXEL[1]]
    for ov in overlays:
        col = pixel_col(ov.x)
        style = _style(ov.fg, ov.bg, ov.bold, truecolor)
        for j, ch in enumerate(ov.text):
            if col + j < width:
                chars[col + j] = f"{style}{ch}"
    end = 0
    for ov in overlays:
        end = max(end, pixel_col(ov.x) + len(ov.text))
    if end % 2 == 1 and end // 2 < len(fb_row):
        px = fb_row[end // 2]
        fill = f"{color_code(px, truecolor)}{PIXEL[0]}"
        if end < width:
            chars[end] = fill
    parts = []
    i = 0
    while i < width:
        if isinstance(chars[i], str) and len(chars[i]) > 1:
            parts.append(chars[i])
            i += 1
        else:
            run = []
            c = fb_row[i // 2]
            while i < width and not (isinstance(chars[i], str) and len(chars[i]) > 1):
                run.append(c)
                i += 1
            if run:
                parts.append(encode_row(run, truecolor))
    parts.append(RESET)
    return "".join(parts)
```

Replace `Screen.frame` with:

```python
    def frame(self, fb, status, overlays=()):
        by_row = {}
        for ov in overlays:
            by_row.setdefault(ov.y, []).append(ov)
        out = [SYNC_BEGIN]
        composed = []
        for y, row in enumerate(fb.rows):
            line = compose_row(row, by_row.get(y, ()), self.truecolor)
            composed.append(line)
            if y < len(self.prev_rows) and self.prev_rows[y] == line:
                continue
            out.append(f"\x1b[{y + 1};1H{line}")
        for i, line in enumerate(status):
            if i < len(self.prev_status) and self.prev_status[i] == line:
                continue
            out.append(f"\x1b[{fb.h + i + 1};1H{RESET}{line}{RESET}\x1b[K")
        self.prev_rows = composed
        self.prev_status = list(status)
        out.append(SYNC_END)
        return "".join(out)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m unittest test_term -v`

Expected: PASS (all `test_term` cases, including new overlay tests).

- [ ] **Step 5: Commit**

```bash
git add term.py test_term.py
git commit -m "Compose text overlays into the terminal rows"
```

---

### Task 2: Label placement and styles in labels.py

**Files:**
- Create: `labels.py`
- Create: `test_labels.py`

**Interfaces:**
- Consumes: `problems.FIRE`, `problems.TOWER`, `problems.CYCLE`, `problems.BACKWARDS`, `problems.HOTSPOT`, `problems.Problem`; `term.Overlay`.
- Produces:
  - `labels.SHORT = 28`
  - `labels.shorten(path: str) -> str`
  - `labels.LIGHT`, `labels.DARK_GREY`, `labels.FIRE_FG`, `labels.FIRE_BG`, `labels.LOUD_FG`, `labels.LOUD_BG`, `labels.AGENT` (a `(fg, bg)` pair for generic agent labels in later phases)
  - `labels.style_name(roof) -> tuple[tuple, tuple]`, `labels.style_fire()`, `labels.style_loud()`, `labels.style_district(roof)`, `labels.style_agent(fg, bg)`
  - `labels.LOUD_KINDS: frozenset[str]`
  - `labels.LabelRequest(text: str, anchor_x: float, anchor_y: int, fg, bg, bold=False, priority: int)` — frozen dataclass; `anchor_x` is a **viewport pixel** x (v3: label at pixel `(x, y)` starts at terminal column `2x + 1`; half-pixel `.5` adds one column). `anchor_y` is the pixel row **above** the roof.
  - `labels.selected_building(building, problem_rows: tuple[problems.Problem, ...], roof: tuple[int, int, int]) -> list[LabelRequest]` — one request (possibly two for the district-coloured dot on name labels: dot overlay + path overlay). Anchors are placeholders (`0.0`, `0`); the viewer sets real pixel anchors before `place`.
  - `labels.place(requests, width, height, taken: set[tuple[int, int]] = frozenset()) -> list[term.Overlay]` — `width`/`height` are framebuffer pixels; overlap tries up to two rows higher; returns `[]` if dropped. `taken` holds **terminal column** indices `(col, row)` where `col = term.pixel_col(overlay.x) + j`.

Centre column for a group: `term.pixel_col(anchor_x) - total_chars // 2`.

- [ ] **Step 1: Write the failing test**

Create `test_labels.py`:

```python
import unittest

import problems
import term
from labels import LOUD_KINDS, place, selected_building, shorten
from test_townmap import build


class ShortenTest(unittest.TestCase):
    def test_short_paths_unchanged(self):
        self.assertEqual(shorten("core/base.py"), "core/base.py")

    def test_long_paths_shorten_from_the_left(self):
        path = "packages/deep/nested/module/file.py"
        self.assertTrue(shorten(path).startswith("…"))
        self.assertLessEqual(len(shorten(path)), 28)


class SelectedLabelTest(unittest.TestCase):
    def setUp(self):
        self.model, _, _, self.town = build()
        self.roof = (84, 108, 150)

    def test_fire_beats_name(self):
        b = self.town.buildings["core/broken.py"]
        rows = self.town.problems.get(b.module, ())
        reqs = selected_building(b, rows, self.roof)
        self.assertEqual(len(reqs), 1)
        self.assertIn("▲", reqs[0].text)
        self.assertIn("broken.py", reqs[0].text)

    def test_loud_problem_beats_name(self):
        b = self.town.buildings["core/tower.py"]
        rows = self.town.problems.get(b.module, ())
        reqs = selected_building(b, rows, self.roof)
        self.assertIn("◆", reqs[0].text)
        self.assertIn("tower", reqs[0].text)

    def test_name_label_has_two_parts_for_the_dot(self):
        b = self.town.buildings["core/base.py"]
        rows = self.town.problems.get(b.module, ())
        reqs = selected_building(b, rows, self.roof)
        self.assertEqual(len(reqs), 2)
        self.assertEqual(reqs[0].text, "●")
        self.assertIn("base.py", reqs[1].text)
        ovs = place(reqs, 40, 20)
        self.assertEqual(len(ovs), 2)
        self.assertEqual(ovs[0].text, "●")
        self.assertEqual(term.pixel_col(ovs[1].x), term.pixel_col(ovs[0].x) + 1)


class PlaceTest(unittest.TestCase):
    def test_centres_on_the_roof(self):
        from labels import LabelRequest, DARK_GREY, LIGHT
        r = LabelRequest("hello", 5.0, 5, LIGHT, DARK_GREY, priority=0)
        ovs = place([r], 40, 20)
        self.assertEqual(len(ovs), 1)
        self.assertEqual(ovs[0].y, 5)
        self.assertEqual(term.pixel_col(ovs[0].x), term.pixel_col(5.0) - len("hello") // 2)

    def test_moves_up_when_overlapping(self):
        from labels import LabelRequest, DARK_GREY, LIGHT
        first = LabelRequest("first", 5.0, 5, LIGHT, DARK_GREY, priority=0)
        second = LabelRequest("second", 5.0, 5, LIGHT, DARK_GREY, priority=1)
        taken = set()
        for ov in place([first], 40, 20, taken):
            for j in range(len(ov.text)):
                taken.add((term.pixel_col(ov.x) + j, ov.y))
        ovs = place([second], 40, 20, taken)
        self.assertEqual(ovs[0].y, 4)

    def test_drops_after_two_rows_up(self):
        from labels import LabelRequest, DARK_GREY, LIGHT
        centre = term.pixel_col(5.0)
        col = centre - len("blocked") // 2
        taken = ({(col + i, 5) for i in range(7)} | {(col + i, 4) for i in range(7)}
                 | {(col + i, 3) for i in range(7)})
        r = LabelRequest("blocked", 5.0, 5, LIGHT, DARK_GREY, priority=0)
        self.assertEqual(place([r], 40, 20, taken), [])

    def test_respects_taken_cells(self):
        from labels import LabelRequest, DARK_GREY, LIGHT
        centre = term.pixel_col(5.0)
        taken = {(centre, 5), (centre + 1, 5)}
        r = LabelRequest("x", 5.0, 5, LIGHT, DARK_GREY, priority=0)
        ovs = place([r], 40, 20, taken)
        self.assertEqual(ovs[0].y, 4)

    def test_clamps_inside_the_screen(self):
        from labels import LabelRequest, DARK_GREY, LIGHT
        r = LabelRequest("edge", 1.0, 5, LIGHT, DARK_GREY, priority=0)
        ovs = place([r], 8, 20)
        term_w = 8 * 2
        self.assertGreaterEqual(term.pixel_col(ovs[0].x), 0)
        self.assertLess(term.pixel_col(ovs[0].x) + len(ovs[0].text), term_w)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m unittest test_labels -v`

Expected: FAIL (`ModuleNotFoundError: No module named 'labels'`).

- [ ] **Step 3: Write minimal implementation**

Create `labels.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m unittest test_labels -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add labels.py test_labels.py
git commit -m "Add label styles and overlap-aware placement"
```

---

### Task 3: Camera easing

**Files:**
- Create: `camera.py`
- Create: `test_camera.py`

**Interfaces:**
- Produces:
  - `camera.EASE = 6.5`
  - `camera.Camera(focus=(0.0, 0.0))` with `.focus: list[float, float]`, `.target: list[float, float]`, `.set_target(x, y)`, `.jump(x, y)` (sets focus and target to the same point — not gliding), `.gliding() -> bool`, `.step(dt: float) -> bool` (applies easing then returns `.gliding()`).

**Decision:** `camera.py` is a separate module (not inside `viewer.py`) because v3 and watch both need the same easing object, it is testable without a town fixture, and `viewer.py` is already doing zoom, drawing and status lines.

- [ ] **Step 1: Write the failing test**

Create `test_camera.py`:

```python
import math
import unittest

import camera


class CameraTest(unittest.TestCase):
    def test_step_moves_toward_the_target(self):
        c = camera.Camera((0.0, 0.0))
        c.set_target(100.0, 50.0)
        moved = c.step(0.1)
        self.assertTrue(moved)
        self.assertGreater(c.focus[0], 0.0)
        self.assertLess(c.focus[0], 100.0)

    def test_step_reaches_the_target_over_many_frames(self):
        c = camera.Camera((0.0, 0.0))
        c.set_target(40.0, 20.0)
        for _ in range(200):
            c.step(1 / 24)
        self.assertAlmostEqual(c.focus[0], 40.0, places=1)
        self.assertAlmostEqual(c.focus[1], 20.0, places=1)
        self.assertFalse(c.step(1 / 24))

    def test_ease_constant_matches_the_spec(self):
        self.assertEqual(camera.EASE, 6.5)
        c = camera.Camera((0.0, 0.0))
        c.set_target(10.0, 0.0)
        c.step(1.0)
        expected = 10.0 * (1 - math.exp(-6.5))
        self.assertAlmostEqual(c.focus[0], expected, places=5)

    def test_jump_snaps_focus_and_target(self):
        c = camera.Camera((0.0, 0.0))
        c.set_target(100.0, 50.0)
        c.step(0.1)
        c.jump(40.0, 20.0)
        self.assertEqual(c.focus, [40.0, 20.0])
        self.assertEqual(c.target, [40.0, 20.0])
        self.assertFalse(c.gliding())

    def test_gliding_is_public(self):
        c = camera.Camera((0.0, 0.0))
        c.set_target(10.0, 0.0)
        self.assertTrue(c.gliding())
        c.jump(10.0, 0.0)
        self.assertFalse(c.gliding())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m unittest test_camera -v`

Expected: FAIL (`ModuleNotFoundError: No module named 'camera'`).

- [ ] **Step 3: Write minimal implementation**

Create `camera.py`:

```python
"""Camera focus easing (v3 section 2)."""

import math

EASE = 6.5
EPS = 0.05


class Camera:
    def __init__(self, focus=(0.0, 0.0)):
        self.focus = [float(focus[0]), float(focus[1])]
        self.target = [float(focus[0]), float(focus[1])]

    def set_target(self, x, y):
        self.target[0], self.target[1] = float(x), float(y)

    def jump(self, x, y):
        self.focus[0] = self.target[0] = float(x)
        self.focus[1] = self.target[1] = float(y)

    def gliding(self):
        return (abs(self.focus[0] - self.target[0]) > EPS
                or abs(self.focus[1] - self.target[1]) > EPS)

    def step(self, dt):
        if dt <= 0:
            return self.gliding()
        t = 1 - math.exp(-EASE * dt)
        for i in range(2):
            self.focus[i] += (self.target[i] - self.focus[i]) * t
        return self.gliding()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m unittest test_camera -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add camera.py test_camera.py
git commit -m "Add camera focus easing toward a target"
```

---

### Task 4: Wire camera, frame rate and selected label into the viewer

**Files:**
- Modify: `viewer.py`
- Modify: `test_viewer.py`

**Interfaces:**
- Consumes: `camera.Camera` (`.jump`, `.gliding`, `.set_target`, `.step`), `labels.selected_building`, `labels.place`, `term.Overlay`, `drawtown.height_px`, existing `TownScene`, `_whole_town`.
- Produces:
  - `viewer.FramePace(clock=time.monotonic)` with `.after_frame(frame_seconds: float, moving: bool) -> float` and read-only `.fps: int` (last chosen rate: 24 or 12).
  - `Viewer.__init__` creates `self.camera` and `camera.jump`s to the starting focus in whole-town pixels (roof centre for the initial building, else tile centre).
  - `Viewer.sync_camera()` — `camera.jump(*_target_for_cursor())`; call after setting `cursor` directly in tests.
  - `Viewer.press` updates `camera.set_target` (does not jump — view glides).
  - `Viewer.moving() -> bool` — delegates to `camera.gliding()`.
  - `Viewer.overlays(w, h) -> list[term.Overlay]` — street zoom, selected `Building` only; `anchor_x`/`anchor_y` are viewport pixel coords from `scene.centre_px` minus `height_px`.
  - `viewer.run(viewer, truecolor, clock=time.monotonic)` — `FramePace`, camera step, overlays in `screen.frame`.
  - `Viewer.frame` — street and district crop around `camera.focus`; town stays whole-town centred.

**Existing tests this task changes** (all in `test_viewer.py`):

| Test | Change | Why |
| --- | --- | --- |
| `test_an_off_screen_fire_gets_an_arrow_at_the_edge` | after `self.v.cursor = …`, call `self.v.sync_camera()` before `frame()` | street view follows `camera.focus`, not cursor alone |
| `test_street_zoom_selected_building_gets_an_overlay` (new) | call `sync_camera()` after moving cursor | same |
| `test_the_inspector_shows_the_facts_behind_a_building` | none | only reads `status()`, not `frame()` |
| `test_warehouses_plots_and_streets_describe_themselves` | none | only reads `status()` |
| `test_every_zoom_level_fills_the_frame` | none | checks dimensions only; camera position irrelevant |
| All other existing tests | none | use `press()` (which updates target) or do not call `frame()` at street zoom with a mismatched cursor |

- [ ] **Step 1: Write the failing test**

In `test_viewer.py`, change `test_an_off_screen_fire_gets_an_arrow_at_the_edge`:

```python
    def test_an_off_screen_fire_gets_an_arrow_at_the_edge(self):
        self.v.cursor = (0, self.town.height - 1)
        self.v.sync_camera()
        fb = self.v.frame(40, 24)
        edge = {fb.rows[y][x] for y in range(fb.h) for x in range(fb.w)
                if min(x, y, fb.w - 1 - x, fb.h - 1 - y) <= 4}
        self.assertTrue(set(FLAMES[:2]) & edge)
```

Extend imports at the top of `test_viewer.py` (keep existing `build`, `Roads`, `FLAMES`, etc.):

```python
import term
from viewer import DISTRICT, STREET, TOWN, FramePace, Viewer, parse_keys, run
```

Append new test classes:

```python
class FramePaceTest(unittest.TestCase):
    def test_still_is_twelve_fps(self):
        p = FramePace(clock=lambda: 0.0)
        self.assertEqual(p.after_frame(0.01, moving=False), 1 / 12 - 0.01)
        self.assertEqual(p.fps, 12)

    def test_moving_is_twenty_four_fps(self):
        p = FramePace(clock=lambda: 0.0)
        self.assertEqual(p.after_frame(0.01, moving=True), 1 / 24 - 0.01)
        self.assertEqual(p.fps, 24)

    def test_slow_frame_drops_to_twelve_until_movement_ends(self):
        p = FramePace(clock=lambda: 0.0)
        p.after_frame(0.04, moving=True)
        self.assertEqual(p.fps, 12)
        self.assertEqual(p.after_frame(0.01, moving=True), 1 / 12 - 0.01)
        p.after_frame(0.01, moving=False)
        self.assertEqual(p.fps, 12)


class CameraViewerTest(unittest.TestCase):
    def setUp(self):
        self.model, self.rows, self.found, self.town = build()
        self.v = Viewer(self.town, Roads(self.town, self.model, self.found), self.model, self.found)

    def test_camera_glides_after_n(self):
        self.v.press("n")
        t0 = self.v.camera.focus[0]
        self.v.camera.step(1 / 24)
        self.assertNotEqual(self.v.camera.focus[0], t0)
        self.assertTrue(self.v.moving())

    def test_sync_camera_jumps_to_the_cursor(self):
        self.v.cursor = (0, self.town.height - 1)
        self.v.sync_camera()
        self.assertFalse(self.v.moving())
        tx, ty = self.v._target_for_cursor()
        self.assertEqual(self.v.camera.focus, [tx, ty])

    def test_street_zoom_selected_building_gets_an_overlay(self):
        self.v.zoom = STREET
        b = self.v.selected()
        self.v.cursor = self.town.centre(b.module)
        self.v.sync_camera()
        self.v.frame(60, 30)
        ovs = self.v.overlays(60, 30)
        self.assertTrue(ovs)
        joined = "".join(o.text for o in ovs)
        self.assertIn("broken", joined)


class RunLoopTest(unittest.TestCase):
    def test_run_writes_frames_and_picks_pace_with_injected_clock(self):
        tick = [0.0]

        def clock():
            return tick[0]

        class FakeTerm:
            last = None

            def __init__(self):
                self.writes = []
                self.timeouts = []
                FakeTerm.last = self

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                pass

            def size(self):
                return 80, 24

            def read(self, timeout):
                self.timeouts.append(timeout)
                tick[0] += timeout
                if tick[0] > 0.05:
                    return "q"
                return ""

            def write(self, s):
                self.writes.append(s)

        model, rows, found, town = build()
        v = Viewer(town, Roads(town, model, found), model, found)
        import viewer as viewer_mod
        old_term = viewer_mod.term.Terminal
        viewer_mod.term.Terminal = FakeTerm
        try:
            run(v, True, clock=clock)
        finally:
            viewer_mod.term.Terminal = old_term
        fake = FakeTerm.last
        self.assertGreaterEqual(len(fake.writes), 2)
        self.assertTrue(any(term.SYNC_BEGIN in w for w in fake.writes))
        self.assertTrue(fake.timeouts)
        self.assertAlmostEqual(fake.timeouts[0], 1 / 12, places=2)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m unittest test_viewer.FramePaceTest test_viewer.CameraViewerTest test_viewer.RunLoopTest -v`

Expected: FAIL (`ImportError` / `AttributeError` for `FramePace`, `moving`, or `overlays`).

- [ ] **Step 3: Write minimal implementation**

Add to `viewer.py` (imports: `camera`, `labels`, `term.Overlay`, keep `math`, `time`):

```python
import camera
import labels

FPS_MOVE = 24
FPS_STILL = 12
FRAME_BUDGET = 0.035


class FramePace:
    def __init__(self, clock=time.monotonic):
        self._clock = clock
        self._slow = False
        self._fps = FPS_STILL

    @property
    def fps(self):
        return self._fps

    def after_frame(self, frame_seconds, moving):
        if frame_seconds > FRAME_BUDGET:
            self._slow = True
        if not moving:
            self._slow = False
        if moving and not self._slow:
            self._fps = FPS_MOVE
        else:
            self._fps = FPS_STILL
        return max(0.0, 1 / self._fps - frame_seconds)
```

In `Viewer.__init__`, after setting `self.cursor` and `self._last_street_scene = None`:

```python
        self.camera = camera.Camera((0.0, 0.0))
        self.sync_camera()
```

Add import `from townmap import Building, Warehouse` (Warehouse already imported).

Add methods:

```python
    def _whole_px(self, tile):
        whole = self._whole_town(None)
        sx, sy = iso.to_screen(tile[0] + 0.5, tile[1] + 0.5)
        return round(sx) + whole.ox, round(sy) + whole.oy

    def _target_for_cursor(self):
        thing = self.selected()
        whole = self._whole_town(None)
        if isinstance(thing, Building):
            fx, fy = whole.centre_px(thing)
            return fx, fy - height_px(thing)
        return self._whole_px(self.cursor)

    def sync_camera(self):
        self.camera.jump(*self._target_for_cursor())

    def moving(self):
        return self.camera.gliding()

    def overlays(self, w, h):
        if self.zoom != STREET or self._last_street_scene is None:
            return []
        thing = self.selected()
        if not isinstance(thing, Building):
            return []
        scene = self._last_street_scene
        roof_x, roof_y = scene.centre_px(thing)
        roof_y -= height_px(thing)
        roof = scene.roofs.get(thing.district, (112, 112, 124))
        raw = labels.selected_building(thing, self.m.problems.get(thing.module, ()), roof)
        anchored = [labels.LabelRequest(r.text, float(roof_x), roof_y - 1, r.fg, r.bg, r.bold, r.priority)
                    for r in raw]
        return labels.place(anchored, w, h)
```

In `press`, after cursor changes:

```python
        self.camera.set_target(*self._target_for_cursor())
```

In `frame`, street branch — replace `TownScene.around(..., self.cursor, ...)` with focus-based origin:

```python
        if self.zoom == STREET:
            whole = self._whole_town(chosen)
            fx, fy = self.camera.focus[0], self.camera.focus[1]
            sx = fx - whole.ox
            sy = fy - whole.oy
            lift = height_px(chosen) // 2 if isinstance(chosen, Building) else 0
            scene = TownScene(self.m, w, h, w // 2 - round(sx), h // 2 - round(sy) + lift,
                              t=self.t, selected=chosen, visible=self.roads.visible(chosen),
                              cursor=None if chosen else self.cursor)
            fb = scene.render()
            self._last_street_scene = scene
            self._mark_fires(fb, lambda b: scene.centre_px(b), inside=False)
            return fb
        self._last_street_scene = None
```

District branch — replace `_point(whole, cursor…)` with camera focus; town unchanged:

```python
        if self.zoom == TOWN:
            cx, cy = whole.fb.w // 2, whole.fb.h // 2
        else:
            cx, cy = round(self.camera.focus[0]), round(self.camera.focus[1])
```

Update `run`:

```python
def run(viewer, truecolor, clock=time.monotonic):
    screen = term.Screen(truecolor)
    pace = FramePace(clock)
    ...
        while True:
            frame_start = clock()
            ...
            if cols >= MIN_COLS and lines >= MIN_LINES:
                fb = viewer.frame(cols // 2, lines - STATUS_LINES)
                status = [style + line for style, line in zip(STYLES, viewer.status(cols))]
                t.write(screen.frame(fb, status, viewer.overlays(fb.w, fb.h)))
            frame_seconds = clock() - frame_start
            moving = viewer.camera.step(frame_seconds)
            timeout = pace.after_frame(frame_seconds, moving)
```

Call `camera.step(frame_seconds)` once per loop iteration, after drawing; its return value is the glide flag for `FramePace`.

Remove module-level `FPS = 12` or keep unused — delete and use `FramePace` only.

Initialize `self._last_street_scene = None` in `__init__`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m unittest test_viewer -v`

Expected: PASS (all prior viewer tests plus new ones; `sync_camera()` in the fire-edge test keeps the view on the corner tile).

- [ ] **Step 5: Commit**

```bash
git add viewer.py test_viewer.py
git commit -m "Glide the camera, adapt frame rate and show the selected label"
```

---

### Task 5: Full suite verification

**Files:**
- None (verification only).

- [ ] **Step 1: Run the full test suite**

Run: `.venv/bin/python -m unittest`

Expected: 463+ tests PASS (five new test modules add cases; total count rises slightly).

- [ ] **Step 2: Smoke-check view wiring manually (optional)**

Run: `.venv/bin/python towncode.py view . --256` in a real terminal; confirm WASD and n/p glide the view, street zoom shows a text label on the selected building, status lines and keys still work, `q` quits. `snapshot` unchanged (no overlays in PNG).

- [ ] **Step 3: Commit (only if Step 3 fixes were needed)**

If fixes were required, commit each fix separately with an imperative message describing the fix. If the suite passed with no code changes, skip this commit.

---

## Self-Review

**Spec coverage**

| Requirement | Task |
| --- | --- |
| Text overlays with fg/bg/bold at pixel positions | Task 1 |
| Column `2x+1`, half-pixel +1 column, tail fill | Task 1 |
| `Screen.frame(fb, status, overlays)` row diff | Task 1 |
| Single-width characters; no emoji | Tasks 1–2 |
| Label kinds (name, fire, loud, district, agent style) | Task 2 |
| Path shorten at 28 with `…` | Task 2 |
| Placement: anchor, priority, overlap, taken, clamp | Task 2 |
| Camera easing constant 6.5 | Task 3 |
| 24/12 FPS and 35 ms fallback | Task 4 |
| Street selected-building label visible in `towncode view` | Task 4 |
| Camera glides on cursor / n/p | Task 4 |
| snapshot unaffected | Task 4 (no overlay call in `towncode._snapshot`) |
| Do not touch focus/cake/roles/mock_roles | All tasks |
| Full suite passes | Task 5 |

**Placeholder scan:** No TBD/TODO steps; every code block is complete.

**Type consistency:** `term.Overlay.x` is viewport pixel x; `labels.place` and `Viewer.overlays` both use pixel anchors from `scene.centre_px`. `Camera.jump`/`gliding` are public; `Viewer.moving()` and `FramePace.fps` match their tests. `sync_camera()` is the single entry for snapping focus after direct cursor writes.

**Scan fixes applied:** pixel anchor tests (Task 2), `BLUE` in Task 1, `Camera.jump`/`gliding()`, `FramePace.fps`, `RunLoopTest` assertions, Task 4 imports, fire-edge `sync_camera()`, existing-test change table.

**Rulings on spec ambiguity**

1. **Label RGB values** — fixed tuples aligned with the existing terminal palette.
2. **District/agent label kinds** — styles defined in Task 2; only selected-building label shown in Phase 1.
3. **Camera at district/town zoom** — district crops around eased focus; town stays whole-town centred.
4. **Name label dot** — two `LabelRequest` parts placed as one anchored group.
5. **Anchors** — pixel coordinates everywhere (v3 §3 Text over pixels); `taken` cells use terminal columns.
