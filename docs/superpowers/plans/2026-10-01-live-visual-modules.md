# Live Visual Modules Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the designer's Plan 3 visuals live in `towncode view` and `towncode snapshot`: cake buildings, select and dim with blue/pink roads, `--session`, and `--layout roles` as an option.

**Architecture:** The designer's modules stay pure and untouched (`cake`, `focus`, `roles`); the renderer calls them. `townmap.Building` carries each building's cake tiers; `drawtown.TownScene` draws each building once from its front tile, glazes windows whole-or-nothing, and shades by a `dim` callable. `roads.Roads` routes a `focus.Focus`'s pairs in its own colours. `viewer.Viewer` puts the selected building, or the session, in focus. `plat.by_roles` builds an unsaved plat whose districts are roles.

**Tech Stack:** Python 3 standard library only (the renderer never imports Pillow); `unittest`; `.venv` with tree-sitter for the full suite.

**Spec:** `docs/superpowers/plans/2026-10-01-visual-modules.md` (Plan 3), section "Hooks for the engineer", plus the user's answers of 2026-10-01: cakes replace the old buildings; a cake taller than the frame's top room is squashed; selecting hides the district highways; with `--session` the session's focus stays on wherever the cursor is.

## Global Constraints

- Renderer stays stdlib only. No Pillow in `drawtown`, `viewer`, `towncode`, `townmap`, `roads`, `plat`.
- The designer's files are not edited, except `session.py`'s `import towncode`, which moves into the two functions that use it (Task 1). Say so in the PR so the designer knows.
- Colour meanings are the designer's: blue = uses, pink = used by, white roof = the focus, amber = a function of 100+ lines (`cake.LONG_FUNCTION`), orange = a construction site for a new uncommitted file.
- The window rule: "a window is painted only if every pixel is still its own wall after the scene is drawn."
- Cycle and backwards roads stay always on, focus or not.
- The district layout stays the default and stays saved. `--layout roles` is laid out afresh on every run and never saved.
- The surveyed repository is only read. Snapshots, the survey and transcripts are never written inside it. The monorepo (`~/repos/big-monorepo`) is only ever surveyed and snapshotted to `/tmp`.
- Every task ends with both `.venv/bin/python -m unittest` and `python3 -m unittest` passing (system python skips the tree-sitter tests).
- Work on a branch `live-visuals` off `main`. Commit after each task. Do not push. Pushing needs the user's go-ahead.

---

## File Structure

| File | Change |
| --- | --- |
| `session.py` | The designer's. Only `import towncode` moves into `_relative` and `main` (Task 1). |
| `townmap.py` | `Building.stack`, `Building.functions`, `floors` becomes `len(stack)`; `stack()`, `squash()`, `MAX_HEIGHT`; construction `sites` (Task 7). |
| `drawtown.py` | Cakes drawn once from the front tile; `tier`, `paint`, `glaze`, `shade_by_focus`; `dim` and `focused` arguments; focus road colours; sites; roofs keyed by folder. |
| `roads.py` | Focus road kinds `USES`/`USED_BY`; `Roads.focused(f)`, `Roads.outside(thing)`, `Roads.visible(selected, focus)`. |
| `viewer.py` | `Viewer(..., session=None)`, `in_focus`, `scene_args`, `session_line`; the inspector names the longest function, the session relation and sites. |
| `plat.py` | `by_roles(model, rows) -> (Plat, Rows)`. |
| `towncode.py` | `--session [TRANSCRIPT]` and `--layout {districts,roles}` on `view` and `snapshot`. |
| `README.md` | Towncode usage and what the new colours mean. |
| Tests | `test_townmap.py`, `test_drawtown.py`, `test_roads.py`, `test_viewer.py`, `test_plat.py`, `test_towncode.py`. |

---

### Task 1: Break the session → towncode import cycle

`focus` imports `session`, and `session` imports `towncode` at module level. `towncode` imports `roads`, so once `roads` imports `focus` (Task 5), `import roads` on its own fails: `towncode` runs `from roads import Roads` while `roads` is only half loaded.

**Files:**
- Modify: `session.py:20` (remove the top-level import), `session.py:60-62` (`_relative`), `session.py:200-212` (`main`)
- Test: `test_towncode.py`

**Interfaces:**
- Produces: `import focus` and `import session` no longer load `towncode`.

- [ ] **Step 1: Write the failing test**

Add to `test_towncode.py` (with `import subprocess`, `import sys` at the top, and `HERE = os.path.dirname(os.path.abspath(__file__))` below the imports):

```python
    def test_focus_and_session_load_without_the_command_line(self):
        code = "import sys, focus, session; sys.exit('towncode' in sys.modules)"
        done = subprocess.run([sys.executable, "-c", code], cwd=HERE, capture_output=True,
                              text=True)
        self.assertEqual(done.returncode, 0, done.stderr)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m unittest test_towncode.TowncodeTest.test_focus_and_session_load_without_the_command_line -v`
Expected: FAIL (`1 != 0`).

- [ ] **Step 3: Move the import**

In `session.py`, delete line 20 (`import towncode`). In `_relative`:

```python
def _relative(raw, root):
    import towncode  # towncode imports the renderer, which imports focus and so this module

    full = os.path.realpath(os.path.join(root, raw))
    return os.path.relpath(full, root) if towncode._inside(full, root) else full
```

And make `import towncode` the first line of `main`'s body, with the same comment.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m unittest test_towncode test_session -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add session.py test_towncode.py
git commit -m "Load towncode lazily in session so the renderer can import focus"
```

---

### Task 2: Cake geometry on Building

**Files:**
- Modify: `townmap.py:7-80` (imports, constants, `Building`, remove `floors()`), `townmap.py:170-180` (`_lot`)
- Test: `test_townmap.py` (showcase and the height test), `test_viewer.py:73`

**Interfaces:**
- Consumes: `cake.tiers(functions, size, module_complexity) -> [cake.Tier]`; `cake.Tier(half, z0, z1, amber)`.
- Produces: `townmap.MAX_HEIGHT = 90`; `townmap.stack(module, size) -> tuple[cake.Tier]`; `townmap.squash(tiers, limit) -> tuple[cake.Tier]`; `Building(module, district, x, y, size, stack, doors, tested, problems, churn, entry, functions=())`. `Building.floors` is a property, `len(stack)`. `doors` and `door_count` stay until Task 3.

- [ ] **Step 1: Write the failing tests**

In `test_townmap.py`, give the showcase functions. Replace the `core/base.py` and `core/broken.py` lines in `showcase()`:

```python
    add("core/base.py", loc=300, complexity=40, tested_by=TESTED, churn=2,
        functions=[("load", 120, 6), ("save", 30, 3), ("close", 8, 1)])
    add("core/broken.py", parse_error="line 3: invalid syntax", tested_by=TESTED,
        functions=[("half", 10, 2), ("way", 5, 1)])
```

Change the import to `from townmap import MAX_HEIGHT, TownMap, door_count, squash`, add `import cake`, and replace `test_height_comes_from_complexity_and_towers_break_the_cap` with:

```python
    def test_a_building_is_a_cake_with_a_floor_per_function(self):
        base = self.town.buildings["core/base.py"]
        self.assertEqual(base.functions, (("load", 120, 6), ("save", 30, 3), ("close", 8, 1)))
        self.assertEqual(base.floors, 3)
        self.assertEqual([t.amber for t in base.stack], [True, False, False])
        self.assertEqual(self.town.buildings["core/loop_a.py"].floors, 1)

    def test_a_module_that_will_not_parse_is_one_floor(self):
        self.assertEqual(self.town.buildings["core/broken.py"].floors, 1)

    def test_no_building_stands_taller_than_the_cap(self):
        self.assertEqual(self.town.buildings["core/tower.py"].stack[-1].z1, MAX_HEIGHT)
        self.assertTrue(all(b.stack[-1].z1 <= MAX_HEIGHT for b in self.town.buildings.values()))

    def test_squash_keeps_floors_touching_and_their_amber(self):
        tall = [cake.Tier(10, 0, 2, False), cake.Tier(10, 2, 4, True)] + \
               [cake.Tier(6, 4 + 2 * i, 6 + 2 * i, False) for i in range(98)]
        short = squash(tall, 50)
        self.assertEqual((short[0].z0, short[-1].z1), (0, 50))
        self.assertTrue(all(a.z1 == b.z0 for a, b in zip(short, short[1:])))
        self.assertTrue(all(t.z0 < t.z1 for t in short))
        self.assertTrue(short[0].amber)
        self.assertEqual(squash(tall[:3], 50), tuple(tall[:3]))
```

In `test_viewer.py:73` change `"9 floors"` to `"1 floor"`: the tower is now one squashed tier.

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m unittest test_townmap test_viewer -v`
Expected: FAIL with `ImportError: cannot import name 'MAX_HEIGHT'`.

- [ ] **Step 3: Implement**

In `townmap.py`, add `import cake` with the other imports. Delete `FLOOR_COMPLEXITY`, `MAX_FLOORS`, `TOWER_FLOORS` and `def floors(...)`. Add `MAX_HEIGHT = 90` after `TREE_CHANCE`. Replace the `Building` dataclass:

```python
@dataclass(frozen=True)
class Building:
    module: str
    district: str
    x: int
    y: int
    size: int
    stack: tuple
    doors: int
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
```

Below `Warehouse`, add:

```python
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
```

In `_lot`, build the building from the stack:

```python
        b = Building(m.id, m.district, x, y, size, stack(m, size), door_count(m, size),
                     bool(m.tested_by), kinds, m.churn, m.is_entry, tuple(m.functions))
```

`drawtown.height_px` still reads `b.floors`, so the old boxes keep drawing until Task 3.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m unittest -q` (then `python3 -m unittest -q`)
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add townmap.py test_townmap.py test_viewer.py
git commit -m "Give each building its cake: a tier per function, squashed under the frame's top room"
```

---

### Task 3: Draw cake buildings

Each building is drawn once, at its front tile's depth (`b.tiles()[-1]`), tier by tier as in `mock_roles.tier`. Every pixel records whose wall it is. Windows go on last, whole or not at all. Doors-per-export and the per-tile facade go away. Windows still mean what they did: lit = tested, dark = untested, boarded = abandoned, doors = everything exported (`ALL_DOORS`). Abandoned code keeps its weeds at the base, because a small building has no windows.

**Files:**
- Modify: `drawtown.py` (imports, constants, `height_px`, `TownScene.__init__`, `visible`, `render`, `draw_block` → `draw_warehouse`, remove `door_tiles` and `facade`, add `draw_cake`, `tier`, `paint`, `glass`, `glaze`, `_own`; `draw_annex` takes the module)
- Modify: `townmap.py` (remove `EXPORTS_PER_DOOR`, `door_count`, `Building.doors`)
- Test: `test_drawtown.py`, `test_townmap.py` (remove the doors test)

**Interfaces:**
- Consumes: `Building.stack`, `cake.wall_columns(half) -> (wall, column, t)`, `cake.windows(half, z0, z1) -> [(wall, [(dx, dy)])]`.
- Produces: `drawtown.AMBER = (236, 160, 40)`, `drawtown.ROOF = 2`, `drawtown.height_px(b) = b.stack[-1].z1 + ROOF`, `TownScene.owner: {(x, y): (key, face, colour)}` where `key = (module, tier index | "roof" | "annex")`, `TownScene.planned: [(key, face, pixels, glass)]`, `TownScene.tier(key, sx, sy, half, z0, z1, c, rim=False, weeds=False)`, `TownScene.paint(x, y, c, key, face)`. `Building(module, district, x, y, size, stack, tested, problems, churn, entry, functions=())`.

- [ ] **Step 1: Write the failing tests**

In `test_drawtown.py`, add `from unittest import mock`, `from render import Framebuffer, shade`, and import `AMBER, LIT, WEED` from `drawtown`. Then add:

```python
    def test_a_long_function_is_an_amber_floor(self):
        self.assertIn(shade(AMBER, 0.95), colours(self.plain))

    def test_windows_are_whole_or_not_drawn_at_all(self):
        scene = TownScene.whole(self.town)
        fb = scene.render()
        whole = 0
        for key, face, pixels, glass in scene.planned:
            pane = glass if face == "left" else shade(glass, 0.82)
            lit = [fb.get(*p) == pane for p in pixels]
            self.assertIn(sum(lit), (0, len(lit)), key)
            whole += all(lit)
        self.assertGreater(whole, 0)

    def test_tested_code_has_lit_windows_and_abandoned_code_grows_weeds(self):
        self.assertIn(LIT, colours(self.plain))
        self.assertIn(WEED, colours(self.plain))

    def test_each_building_is_drawn_once(self):
        scene = TownScene.whole(self.town)
        with mock.patch.object(scene, "draw_cake", wraps=scene.draw_cake) as draw:
            scene.render()
        self.assertEqual(sorted(c.args[0].module for c in draw.call_args_list),
                         sorted(self.town.buildings))
```

In `test_townmap.py`, delete `test_doors_from_exports_capped_by_frontage` and remove `door_count` from the import.

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m unittest test_drawtown -v`
Expected: FAIL with `ImportError: cannot import name 'AMBER'`.

- [ ] **Step 3: Implement in `townmap.py`**

Delete `EXPORTS_PER_DOOR`, `def door_count(...)` and the `doors: int` field of `Building`. In `_lot`:

```python
        b = Building(m.id, m.district, x, y, size, stack(m, size), bool(m.tested_by), kinds,
                     m.churn, m.is_entry, tuple(m.functions))
```

- [ ] **Step 4: Implement in `drawtown.py`**

Imports: add `import cake`; change the render import to drop `KNOB`; import `Building` too:

```python
import cake
import iso
import problems
import roads as R
import sprites
from render import (DIRT, DOOR, LOCAL, SKIRT, SKIRT_DEPTH, SKIRT_LIP, Framebuffer, ground_color,
                    hash2, mix, shade)
from townmap import Building, Warehouse
```

Constants: delete `GROUND_FLOOR`, `FLOOR` and `PARAPET`. Add these after `TOP_ROOM`:

```python
ROOF = 2
SIDE_ROOM = 28
AMBER = (236, 160, 40)
```

Replace `height_px`:

```python
def height_px(b):
    return b.stack[-1].z1 + ROOF
```

At the end of `TownScene.__init__`, add:

```python
        self.owner = {}
        self.planned = []
```

Replace `visible`. A building's walls reach `cake.half_width(4, 1.0) = 22` px either side of its front tile:

```python
    def visible(self, sx, sy):
        return -SIDE_ROOM < sx < self.fb.w + SIDE_ROOM and -8 < sy < self.fb.h + TOP_ROOM
```

In `render`, replace the block that appends `draw_block`, and the annex loop. Then glaze before the ghost:

```python
                thing = m.at.get((tx, ty))
                if isinstance(thing, Building):
                    if (tx, ty) == thing.tiles()[-1]:
                        drawables.append((tx + ty, 0, tx, partial(self.draw_cake, thing)))
                elif thing is not None:
                    draw = partial(self.draw_warehouse, thing, tx, ty, sx, sy)
                    drawables.append((tx + ty, 0, tx, draw))
                elif (tx, ty) in m.trees:
                    drawables.append((tx + ty, 0, tx, partial(self.draw_tree, tx, ty, sx, sy)))
```

```python
        for b in m.buildings.values():
            if b.tested:
                tx, ty = b.x + b.size, b.y
                sx, sy = self.screen(tx, ty)
                if self.visible(sx, sy):
                    drawables.append((tx + ty, 1, tx,
                                      partial(self.draw_annex, b.module, sx, sy)))
        drawables.sort(key=lambda d: d[:3])
        for *_, draw in drawables:
            draw()
        self.glaze()
        self.draw_ghost()
        return self.fb
```

Replace `draw_block`, `door_tiles` and `facade` with:

```python
    def draw_warehouse(self, w, tx, ty, sx, sy):
        self.draw_box(w, tx, ty, sx, sy, WAREHOUSE_H, WAREHOUSE_WALL, WAREHOUSE_ROOF,
                      self.warehouse_wall)

    def draw_cake(self, b):
        """A tier per function, biggest at the bottom, then the roof; windows wait for glaze."""
        sx, sy = self.centre_px(b)
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
        roof = self.roofs.get(b.district, ROOFS[-1])
        self.tier((b.module, "roof"), sx, sy, top.half, top.z1, top.z1 + ROOF,
                  shade(roof, shadow), rim=b is self.selected)
        if problems.FIRE in b.problems:
            self.draw_fire(b)

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
        if problems.ABANDONED in b.problems:
            return BOARD
        if problems.ALL_DOORS in b.problems:
            return DOOR
        return LIT if b.tested else DARK

    def glaze(self):
        """Paint each window only if every pixel of it is still its own wall: whole or not at all."""
        for key, face, pixels, glass in self.planned:
            if all(self._own(p, key, face) for p in pixels):
                pane = glass if face == "left" else shade(glass, 0.82)
                for x, y in pixels:
                    self.paint(x, y, pane, key, face)

    def _own(self, p, key, face):
        o = self.owner.get(p)
        return o is not None and o[:2] == (key, face) and self.fb.get(*p) == o[2]
```

Replace `draw_annex` so its pixels belong to the building:

```python
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
```

`draw_fire` already uses `height_px(b)`, and so does the viewer's street-view lift. Neither changes.

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/python -m unittest -q` (then `python3 -m unittest -q`)
Expected: PASS. If `test_loud_roads_and_the_selection_show_through_the_tower_in_front` fails, print where `core/tower.py` and `core/loop_a.py` stand. The tower must still stand in front of `loop_a`. Don't weaken the test.

- [ ] **Step 6: Look at it**

```bash
.venv/bin/python towncode.py snapshot . /tmp/towncode-live/cakes.png --zoom town --size 480x320 --scale 2
```

Open the PNG. Each building should be a stack of tiers, with windows only on whole tiers and nothing torn at tile seams.

- [ ] **Step 7: Commit**

```bash
git add drawtown.py townmap.py test_drawtown.py test_townmap.py
git commit -m "Draw each building as the designer's cake, once, with windows whole or not at all"
```

---

### Task 4: Dim by focus and a white roof

**Files:**
- Modify: `drawtown.py` (`TownScene.__init__` signature, `draw_cake` roof, `render`, new `shade_by_focus`)
- Test: `test_drawtown.py`

**Interfaces:**
- Consumes: `TownScene.owner` (Task 3).
- Produces: `TownScene(tmap, w, h, ox, oy, t=0.0, selected=None, visible=(), cursor=None, dim=None, focused=frozenset())`. `dim` is `module -> float`, `focused` is a set of modules. `drawtown.FOCUS_ROOF = (250, 250, 250)`.

- [ ] **Step 1: Write the failing test**

Import `FOCUS_ROOF` from `drawtown` in `test_drawtown.py`, then:

```python
    def test_a_focus_dims_the_rest_and_whitens_its_roof(self):
        plain = TownScene.whole(self.town)
        plain.render()
        level = {"app/main.py": 1.0, "core/base.py": 0.72}
        scene = TownScene.whole(self.town, dim=lambda m: level.get(m, 0.38),
                                focused={"app/main.py"})
        fb = scene.render()
        self.assertIn(shade(FOCUS_ROOF, 0.95), colours(fb))
        self.assertNotIn(shade(FOCUS_ROOF, 0.95), colours(plain.fb))
        showing = lambda module: [(p, c) for p, ((m, key), _, c) in plain.owner.items()
                                  if m == module and key != "roof" and plain.fb.get(*p) == c]
        self.assertTrue(showing("app/lonely.py"))
        self.assertTrue(all(fb.get(*p) == shade(c, 0.38) for p, c in showing("app/lonely.py")))
        self.assertTrue(all(fb.get(*p) == shade(c, 0.72) for p, c in showing("core/base.py")))
        self.assertTrue(all(fb.get(*p) == c for p, c in showing("app/main.py")))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m unittest test_drawtown -v`
Expected: FAIL with `ImportError: cannot import name 'FOCUS_ROOF'`.

- [ ] **Step 3: Implement**

Add `FOCUS_ROOF = (250, 250, 250)` after `AMBER`. Change the `TownScene.__init__` signature, and store both values:

```python
    def __init__(self, tmap, w, h, ox, oy, t=0.0, selected=None, visible=(), cursor=None,
                 dim=None, focused=frozenset()):
        ...
        self.dim = dim
        self.focused = focused
```

In `draw_cake`, choose the roof colour:

```python
        roof = FOCUS_ROOF if b.module in self.focused else self.roofs.get(b.district, ROOFS[-1])
```

In `render`, shade after glazing:

```python
        self.glaze()
        self.shade_by_focus()
        self.draw_ghost()
```

And add:

```python
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
            if levels[module] < 1 and self.fb.rows[y][x] == c:
                self.fb.rows[y][x] = shade(c, levels[module])
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m unittest -q` (then `python3 -m unittest -q`)
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add drawtown.py test_drawtown.py
git commit -m "Shade buildings by a focus and give the focus a white roof"
```

---

### Task 5: Focus roads in blue and pink

**Files:**
- Modify: `roads.py` (imports, `ORDER`, `half_width`, `Roads.__init__`, `_module_road`, `of`, `visible`; new `focused`, `outside`)
- Modify: `drawtown.py:47-48` (`ROAD_COLORS`)
- Test: `test_roads.py`, `test_drawtown.py`, `test_towncode.py`

**Interfaces:**
- Consumes: `focus.Focus.roads: ((kind, src, dst), ...)` with `kind` in `focus.USES`, `focus.USED_BY`; `focus.select(model, module) -> Focus`.
- Produces: `roads.USES`, `roads.USED_BY` (re-exported from `focus`); `Roads.problem_roads: [Road]`; `Roads.focused(f) -> [Road]`; `Roads.outside(thing) -> [Road]`; `Roads.visible(selected=None, focus=None) -> [Road]`. With a focus, it returns the problem roads, the focus's roads, and the selection's outside-package roads, and no highways. `drawtown.ROAD_COLORS[USES] = (80, 168, 255)` and `drawtown.ROAD_COLORS[USED_BY] = (236, 96, 196)`.

- [ ] **Step 1: Write the failing tests**

In `test_roads.py`, add `import focus` and `from roads import CYCLE, HIGHWAY, ROAD, USED_BY, USES`, then:

```python
    def test_a_focus_draws_its_roads_in_its_colours_instead_of_highways(self):
        base = self.town.buildings["core/base.py"]
        seen = keys(self.roads.visible(base, focus.select(self.model, "core/base.py")))
        self.assertIn((USED_BY, "app/main.py", "core/base.py"), seen)
        self.assertIn((USED_BY, "core/tower.py", "core/base.py"), seen)
        self.assertIn((ROAD, "core/base.py", "yaml"), seen)
        self.assertIn((CYCLE, "core/loop_a.py", "core/loop_b.py"), seen)
        self.assertNotIn(HIGHWAY, {kind for kind, _, _ in seen})

    def test_an_import_that_is_a_problem_keeps_its_own_road_in_a_focus(self):
        a = self.town.buildings["core/loop_a.py"]
        seen = keys(self.roads.visible(a, focus.select(self.model, "core/loop_a.py")))
        self.assertIn((CYCLE, "core/loop_a.py", "core/loop_b.py"), seen)
        self.assertNotIn((USES, "core/loop_a.py", "core/loop_b.py"), seen)
        self.assertIn((USED_BY, "app/main.py", "core/loop_a.py"), seen)

    def test_without_a_focus_the_roads_are_as_before(self):
        main = self.town.buildings["app/main.py"]
        kinds = {kind for kind, _, _ in keys(self.roads.visible(main))}
        self.assertIn(HIGHWAY, kinds)
        self.assertFalse({USES, USED_BY} & kinds)
```

In `test_drawtown.py`, add `import focus` and `from roads import USED_BY, USES`, then:

```python
    def test_focus_roads_are_blue_and_pink(self):
        b = self.town.buildings["core/base.py"]
        f = focus.select(self.model, "core/base.py")
        fb = TownScene.whole(self.town, selected=b, visible=self.roads.visible(b, f)).render()
        self.assertIn(ROAD_COLORS[USED_BY], colours(fb))
        main = self.town.buildings["app/main.py"]
        f = focus.select(self.model, "app/main.py")
        fb = TownScene.whole(self.town, selected=main, visible=self.roads.visible(main, f)).render()
        self.assertIn(ROAD_COLORS[USES], colours(fb))
```

In `test_towncode.py`:

```python
    def test_each_renderer_module_imports_on_its_own(self):
        for name in ("roads", "drawtown", "viewer", "towncode"):
            done = subprocess.run([sys.executable, "-c", f"import {name}"], cwd=HERE,
                                  capture_output=True, text=True)
            self.assertEqual(done.returncode, 0, f"{name}: {done.stderr}")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m unittest test_roads test_drawtown -v`
Expected: FAIL with `ImportError: cannot import name 'USED_BY' from 'roads'`.

- [ ] **Step 3: Implement in `roads.py`**

```python
import layers
import problems
from focus import USED_BY, USES
from townmap import Building, Warehouse

ROAD = "road"
HIGHWAY = "highway"
CYCLE = "cycle"
BACKWARDS = "backwards"
ORDER = [ROAD, HIGHWAY, USES, USED_BY, BACKWARDS, CYCLE]
```

In `half_width`:

```python
    base = {ROAD: 0.12, HIGHWAY: 0.16, USES: 0.12, USED_BY: 0.12, BACKWARDS: 0.17,
            CYCLE: 0.17}[kind]
```

At the end of `Roads.__init__`:

```python
        self._routes = {}
        self.problem_roads = self._problem_roads()
        self.always = self._highways() + self.problem_roads
```

`_module_road` takes the kind:

```python
    def _module_road(self, src, dst, avoid=frozenset(), kind=None):
        b = self.tmap.buildings
        if src not in b or dst not in b:
            return []
        n = self.model.edges[(src, dst)]
        return self._road(kind or self.kind_of(src, dst), src, dst, b[src].front(),
                          b[dst].front(), n, avoid=avoid)
```

Replace `of` and `visible`, and add `focused` and `outside`:

```python
    def focused(self, f):
        """A focus's roads in its own colours. An import that is a problem keeps its own road."""
        found = []
        for kind, src, dst in f.roads:
            if self.kind_of(src, dst) == ROAD:
                found += self._module_road(src, dst, kind=kind)
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
```

Update the module docstring's second paragraph:

```python
"""Roads: imports routed along the streets, and which of them are drawn.

Problem roads (cycles, backwards imports) are always drawn. Highways (all imports between two
districts) and the selection's own roads are drawn until something is in focus; then the
focus's roads are drawn instead, blue for what it uses and pink for what uses it.
"""
```

- [ ] **Step 4: Implement in `drawtown.py`**

Add `from focus import USED_BY, USES` to the imports, then:

```python
ROAD_COLORS = {R.ROAD: (82, 84, 96), R.HIGHWAY: (58, 60, 70), R.CYCLE: (214, 46, 46),
               R.BACKWARDS: (232, 112, 36), USES: (80, 168, 255), USED_BY: (236, 96, 196)}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/python -m unittest -q` (then `python3 -m unittest -q`)
Expected: PASS, including `test_each_renderer_module_imports_on_its_own`. That test only passes because Task 1 moved the import.

- [ ] **Step 6: Commit**

```bash
git add roads.py drawtown.py test_roads.py test_drawtown.py test_towncode.py
git commit -m "Route a focus's roads in blue and pink; problem roads keep their colours"
```

---

### Task 6: The viewer puts the selection, or the session, in focus

**Files:**
- Modify: `viewer.py` (imports, `Viewer.__init__`, `frame`, `_whole_town`, `status`, `describe`; new `in_focus`, `scene_args`, `session_line`)
- Test: `test_viewer.py`

**Interfaces:**
- Consumes: `focus.select`, `focus.dim`, `Roads.visible(selected, focus)`, `TownScene(..., dim=, focused=)`.
- Produces: `Viewer(tmap, roads, model, found, session=None)`, where `session` is a `focus.Focus` or `None`. Also `Viewer.in_focus(chosen) -> Focus | None`, `Viewer.scene_args(chosen) -> dict` and `Viewer.session_line() -> str`, which returns `"session: N changed, M use them directly, K through them"`.

- [ ] **Step 1: Write the failing tests**

In `test_viewer.py`, add `import focus`, `from drawtown import FLAMES, FOCUS_ROOF, ROAD_COLORS`, `from render import shade`, `from roads import Roads, USED_BY`, and a module-level `def colours(fb): return {c for row in fb.rows for c in row}`. Then:

```python
    def test_a_selected_building_is_in_focus(self):
        self.v.cursor = self.town.centre("core/base.py")
        f = self.v.in_focus(self.v.selected())
        self.assertEqual((f.kind, f.distance["core/base.py"]), ("select", 0))
        fb = self.v.frame(120, 90)
        self.assertIn(shade(FOCUS_ROOF, 0.95), colours(fb))
        self.assertIn(ROAD_COLORS[USED_BY], colours(fb))

    def test_nothing_is_in_focus_off_a_building(self):
        self.v.cursor = (0, self.town.height - 1)
        self.assertIsNone(self.v.in_focus(self.v.selected()))

    def test_a_session_stays_in_focus_wherever_the_cursor_is(self):
        changed = focus.changed(self.model, {"core/base.py"})
        v = Viewer(self.town, Roads(self.town, self.model, self.found), self.model, self.found,
                   session=changed)
        v.cursor = self.town.centre("app/lonely.py")
        self.assertIs(v.in_focus(v.selected()), changed)
        self.assertTrue(v.status(300)[0].startswith(
            " session: 1 changed, 2 use them directly, 0 through them"))
        _, facts, _ = v.describe(self.town.buildings["app/main.py"])
        self.assertIn("uses a changed module", facts)
        self.assertIn(shade(FOCUS_ROOF, 0.95), colours(v._whole_town(v.selected()).fb))

    def test_the_inspector_names_the_longest_function(self):
        _, facts, _ = self.v.describe(self.town.buildings["core/base.py"])
        self.assertIn("longest function load: 120 lines", facts)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m unittest test_viewer -v`
Expected: FAIL with `AttributeError: 'Viewer' object has no attribute 'in_focus'`.

- [ ] **Step 3: Implement**

Imports in `viewer.py`:

```python
import math
import signal
import time
from functools import partial

import focus
import iso
import problems
import term
from drawtown import FLAMES, SEA, SELECT, TownScene, height_px, shrink
```

Add a constant after `STYLES`:

```python
RELATION = {0: "changed this session", 1: "uses a changed module"}
```

Change `Viewer.__init__` to take the session, storing `self.session = session` after `self.found`:

```python
    def __init__(self, tmap, roads, model, found, session=None):
        self.m, self.roads, self.model, self.found = tmap, roads, model, found
        self.session = session
```

Add these methods under `selected`:

```python
    def in_focus(self, chosen):
        """The session's changes when there is a session, else the selected building."""
        if self.session is not None:
            return self.session
        if isinstance(chosen, Building):
            return focus.select(self.model, chosen.module)
        return None

    def scene_args(self, chosen):
        f = self.in_focus(chosen)
        if f is None:
            return {"selected": chosen, "visible": self.roads.visible(chosen)}
        return {"selected": chosen, "visible": self.roads.visible(chosen, f),
                "dim": partial(focus.dim, f),
                "focused": frozenset(m for m, d in f.distance.items() if d == 0)}

    def session_line(self):
        near = [self.session.distance[m] for m in self.m.buildings if m in self.session.distance]
        return (f"session: {near.count(0)} changed, {near.count(1)} use them directly, "
                f"{sum(d > 1 for d in near)} through them")
```

In `frame`, use the scene arguments for the street scene:

```python
            scene = TownScene.around(self.m, w, h, self.cursor, lift=lift, t=self.t,
                                     cursor=None if chosen else self.cursor,
                                     **self.scene_args(chosen))
```

In `_whole_town`, do the same for the whole-town scene:

```python
            scene = TownScene.whole(self.m, **self.scene_args(chosen))
```

In `status`, add this after the `problem` prefix:

```python
        if self.session is not None:
            title = f"{self.session_line()} · {title}"
```

In `describe`, add these facts for a `Building`, before `if m.is_entry:`:

```python
            longest = max(thing.functions, key=lambda f: (f[1], f[0]), default=None)
            if longest:
                facts.append(f"longest function {longest[0] or '(unnamed)'}: "
                             f"{_n(longest[1], 'line')}")
            d = self.session.distance.get(m.id) if self.session else None
            if d is not None:
                facts.append(RELATION.get(d, "uses a changed module through another"))
```

Update the module docstring. Add this sentence to its end: "Selecting a building puts it in focus: what it uses and what uses it stay bright, the rest dims. With a session, the session's changes stay in focus instead."

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m unittest -q` (then `python3 -m unittest -q`)
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add viewer.py test_viewer.py
git commit -m "Put the selected building, or the session, in focus in the viewer"
```

---

### Task 7: Construction sites for new files

`focus.unbuilt` lists the code files a session wrote that aren't committed yet. Each one becomes a one-tile orange site in rows along the island's front edge, in sorted path order, so a folder's files sit together.

**Files:**
- Modify: `townmap.py` (`TownMap.__init__` takes `sites`, new `_sites`, `thing_at`)
- Modify: `drawtown.py` (`SITE`, `SITE_WIDTH`, `SITE_HEIGHT`, `site_at`, `render`, `draw_site`)
- Modify: `viewer.py` (`describe` for a site)
- Test: `test_townmap.py`, `test_drawtown.py`, `test_viewer.py`

**Interfaces:**
- Produces: `TownMap(model, plat, rows, found, sites=())`, where `sites` is a sorted list of repository-relative paths. Also `TownMap.sites: {path: (x, y)}`, ground kind `"site"`, and `thing_at -> ("site", path)`. In `drawtown`: `SITE = (232, 128, 48)`, `SITE_WIDTH = 0.7`, `SITE_HEIGHT = 3`. Viewer: `describe(("site", path))`.

- [ ] **Step 1: Write the failing tests**

In `test_townmap.py` (import `MARGIN` from `townmap`):

```python
    def sited(self, paths):
        return TownMap(self.model, Plat().update(self.model, self.rows), self.rows, self.found,
                       sites=paths)

    def test_new_files_are_construction_sites_along_the_front(self):
        town = self.sited(["app/new.py", "app/newer.py"])
        (ax, ay), (bx, by) = town.sites["app/new.py"], town.sites["app/newer.py"]
        self.assertEqual(ay, by)
        self.assertGreater(bx, ax)
        self.assertGreaterEqual(ay, max(b.y + b.size for b in town.buildings.values()))
        self.assertEqual(town.kind(ax, ay), "site")
        self.assertEqual(town.thing_at(ax, ay), ("site", "app/new.py"))

    def test_many_sites_wrap_onto_more_rows_inside_the_island(self):
        town = self.sited([f"new/f{i:03}.py" for i in range(100)])
        rows = {y for _, y in town.sites.values()}
        self.assertGreater(len(rows), 1)
        self.assertTrue(all(x < town.right for x, _ in town.sites.values()))
        self.assertLess(max(rows) + MARGIN, town.height)
```

In `test_drawtown.py` (import `SITE` from `drawtown`):

```python
    def test_new_files_are_orange_sites_that_never_dim(self):
        town = TownMap(self.model, Plat().update(self.model, self.rows), self.rows, self.found,
                       sites=["app/new.py"])
        fb = TownScene.whole(town, dim=lambda m: 0.38).render()
        self.assertIn(shade(SITE, 0.95), colours(fb))
```

In `test_viewer.py`:

```python
    def test_a_site_describes_itself(self):
        title, facts, _ = self.v.describe(("site", "app/new.py"))
        self.assertEqual(title, "new file: app/new.py")
        self.assertIn("not committed yet", facts)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m unittest test_townmap test_drawtown test_viewer -v`
Expected: FAIL with `TypeError: TownMap.__init__() got an unexpected keyword argument 'sites'`.

- [ ] **Step 3: Implement in `townmap.py`**

Add `SITE_STEP = 2` after `MAX_HEIGHT`. Change `__init__`:

```python
    def __init__(self, model, plat, rows, found, sites=()):
        ...
        self.trees = set()
        self.sites = {}
        self._arrange(plat, rows)
        self._sites(sites)
        self._harbor(plat)
```

Add the method after `_arrange`:

```python
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
```

In `thing_at`, before the vacant-lot loop:

```python
        for path, tile in self.sites.items():
            if tile == (x, y):
                return ("site", path)
```

Add `"site": the place a new file will stand` to the module docstring's list of what's on the tiles.

- [ ] **Step 4: Implement in `drawtown.py`**

Constants after `FOCUS_ROOF`:

```python
SITE = (232, 128, 48)
SITE_WIDTH = 0.7
SITE_HEIGHT = 3
```

At the end of `TownScene.__init__`:

```python
        self.site_at = {tile: path for path, tile in tmap.sites.items()}
```

In `render`, add a branch after the building and warehouse branches, before the trees:

```python
                elif (tx, ty) in self.site_at:
                    draw = partial(self.draw_site, self.site_at[(tx, ty)], tx, ty)
                    drawables.append((tx + ty, 0, tx, draw))
```

And the drawer, next to `draw_cake`:

```python
    def draw_site(self, path, tx, ty):
        sx, sy = iso.to_screen(tx + 0.5, ty + 0.5)
        self.tier((path, 0), round(sx) + self.ox, round(sy) + self.oy,
                  cake.half_width(1, SITE_WIDTH), 0, SITE_HEIGHT, SITE)
```

`shade_by_focus` already skips owners that aren't buildings, so sites never dim.

- [ ] **Step 5: Implement in `viewer.py`**

In `describe`, before the `vacant` branch:

```python
        if thing and thing[0] == "site":
            return f"new file: {thing[1]}", "not committed yet, so it has no building", []
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `.venv/bin/python -m unittest -q` (then `python3 -m unittest -q`)
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add townmap.py drawtown.py viewer.py test_townmap.py test_drawtown.py test_viewer.py
git commit -m "Show new uncommitted files as construction sites at the front of town"
```

---

### Task 8: `--session [TRANSCRIPT]` on view and snapshot

**Files:**
- Modify: `towncode.py` (docstring, imports, `town`, new `_session` and `_session_note`, `_view`, `_snapshot`, `_parser`)
- Test: `test_towncode.py`

**Interfaces:**
- Consumes: `session.transcripts(root) -> [path]` (oldest first), `session.load(transcript, root) -> [Step]`, `focus.changed_by(steps, model) -> set`, `focus.changed(model, modules) -> Focus`, `focus.unbuilt(steps, model, tracked) -> [path]`, `Viewer(..., session=)`, `TownMap(..., sites=)`.
- Produces: `towncode.town(model, rows, plat, layout=DISTRICTS, changed=None, sites=())`. `view` and `snapshot` accept `--session [TRANSCRIPT]` (`nargs="?"`, `const=""`); with no value it uses the newest transcript. `snapshot` prints `"<session_line>; N new files not committed yet"`.

- [ ] **Step 1: Write the failing tests**

In `test_towncode.py`, add `import json` and `import re`, then:

```python
    def transcript(self, *steps):
        """A Claude Code transcript of steps (tool, path) under a fake home, for this repo."""
        home = tempfile.mkdtemp(prefix="towncode-home-")
        self.addCleanup(shutil.rmtree, home)
        slug = re.sub(r"[^A-Za-z0-9]", "-", os.path.realpath(self.root))
        folder = os.path.join(home, ".claude", "projects", slug)
        os.makedirs(folder)
        path = os.path.join(folder, "session.jsonl")
        with open(path, "w", encoding="utf-8") as f:
            for i, (tool, rel) in enumerate(steps):
                block = {"type": "tool_use", "id": str(i), "name": tool,
                         "input": {"file_path": os.path.join(self.root, rel)}}
                f.write(json.dumps({"timestamp": f"2026-10-01T10:00:{i:02}Z",
                                    "message": {"content": [block]}}) + "\n")
        return home, path

    def test_snapshot_shows_what_a_session_changed_and_leaves_the_repo_untouched(self):
        home, _ = self.transcript(("Edit", "hub/records.py"), ("Write", "hub/new_tool.py"))
        png = os.path.join(self.out, "town.png")
        before = untouched.fingerprint(self.root)
        buf = io.StringIO()
        with mock.patch.dict(os.environ, {"HOME": home}), contextlib.redirect_stdout(buf):
            code = towncode.main(["snapshot", self.root, png, "--session", "--size", "40x30",
                                  "--scale", "1"])
        self.assertEqual(code, 0)
        self.assertIn("session: 1 changed", buf.getvalue())
        self.assertIn("1 new file not committed yet", buf.getvalue())
        self.assertEqual(untouched.differences(before, untouched.fingerprint(self.root)), {})

    def test_a_named_transcript_is_used_as_given(self):
        _, path = self.transcript(("Edit", "hub/app.py"))
        png = os.path.join(self.out, "town.png")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            towncode.main(["snapshot", self.root, png, "--session", path, "--size", "40x30"])
        self.assertIn("session: 1 changed", buf.getvalue())

    def test_session_without_a_transcript_says_so(self):
        home = tempfile.mkdtemp(prefix="towncode-home-")
        self.addCleanup(shutil.rmtree, home)
        png = os.path.join(self.out, "town.png")
        with mock.patch.dict(os.environ, {"HOME": home}), self.assertRaises(SystemExit) as ctx:
            self.snapshot(png, "--session")
        self.assertIn("no Claude Code or Cursor transcript", str(ctx.exception))
        with self.assertRaises(SystemExit) as ctx:
            self.snapshot(png, "--session", os.path.join(home, "missing.jsonl"))
        self.assertIn("no such transcript", str(ctx.exception))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m unittest test_towncode -v`
Expected: FAIL with `error: unrecognized arguments: --session`.

- [ ] **Step 3: Implement**

Docstring usage lines:

```
    python3 towncode.py survey PATH [--check-untouched]
    python3 towncode.py view PATH [--256] [--layout roles] [--session [TRANSCRIPT]]
    python3 towncode.py snapshot PATH OUT.png [--zoom town] [--at MODULE] [--size WxH]
                                 [--layout roles] [--session [TRANSCRIPT]]
```

Add this to the docstring's paragraph: "`--session` reads an agent transcript under `~/.claude` or `~/.cursor` (the newest for the repository when none is named). It shows what that session changed, and what imports it."

Imports: add `import focus` and `import session`. Add the constants after `REPORT_LIMIT`:

```python
DISTRICTS, ROLES = "districts", "roles"
LAYOUTS = [DISTRICTS, ROLES]
```

Replace `town`:

```python
def town(model, rows, plat, layout=DISTRICTS, changed=None, sites=()):
    """The viewer for a surveyed town; changed is a session's focus, sites its new files."""
    found = problems.find(model, rows)
    tmap = TownMap(model, plat, rows, found, sites)
    return viewer.Viewer(tmap, Roads(tmap, model, found), model, found, changed)
```

`layout` is accepted here and used in Task 9. Add below `town`:

```python
def _session(args, model):
    """(focus, new files) for --session: the transcript named, or the newest for the repo."""
    if args.session is None:
        return None, ()
    found = session.transcripts(args.path)
    transcript = args.session or (found[-1] if found else None)
    if not transcript:
        raise SystemExit(f"no Claude Code or Cursor transcript found for {args.path}")
    if not os.path.isfile(transcript):
        raise SystemExit(f"no such transcript: {transcript}")
    steps = session.load(transcript, args.path)
    changed = focus.changed(model, focus.changed_by(steps, model))
    return changed, focus.unbuilt(steps, model, Repo(args.path).files())


def _session_note(v, sites):
    return f"{v.session_line()}; {_n(len(sites), 'new file')} not committed yet"
```

In `_view` and `_snapshot`, replace `v = town(model, rows, plat)` with:

```python
    changed, sites = _session(args, model)
    v = town(model, rows, plat, args.layout, changed, sites)
```

In `_snapshot`, before `print(f"wrote {args.out}")`:

```python
    if changed is not None:
        print(_session_note(v, sites))
```

In `_view`, change the final print to add the note when there is a session:

```python
    note = f" {_session_note(v, sites)}." if changed is not None else ""
    print(f"{model.repo}: {_n(len(v.found), 'problem')}.{note} Saved to {out}")
```

In `_parser`, add a helper and call it on both `view` and `snapshot` right after their other arguments:

```python
def _town_options(cmd):
    cmd.add_argument("--layout", choices=LAYOUTS, default=DISTRICTS,
                     help="districts by folder (default), or roles: front door, main street, "
                          "scripts, and what nothing imports")
    cmd.add_argument("--session", nargs="?", const="", metavar="TRANSCRIPT",
                     help="show what an agent session changed and what imports it "
                          "(default: the repository's newest transcript)")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m unittest -q` (then `python3 -m unittest -q`)
Expected: PASS.

- [ ] **Step 5: Try it on this repository**

```bash
.venv/bin/python towncode.py snapshot . /tmp/towncode-live/session.png --session <agent-transcript> --zoom town --size 480x320 --scale 2
```

Expected: a `session: N changed, ...` line. The PNG shows white roofs on the changed modules, pink roads to what imports them, and everything else dimmed.

- [ ] **Step 6: Commit**

```bash
git add towncode.py test_towncode.py
git commit -m "Add --session to view and snapshot: what an agent changed and what imports it"
```

---

### Task 9: `--layout roles`

The districts become roles, banded from back to front:

- band 0, `/foundations`: foundations, most imported first, then side modules (what only scripts use);
- band 1, `/main street`: the front door first, then the street;
- band 2: one district per script group, `/scripts/<helper>` or `/standalone scripts`;
- band 3: `/named` and `/islands`;
- band 4: `/unsurveyed`.

Names start with `/`, so no folder can share one, and no district highway ever finds one. Roof colours stay keyed by folder, as in the designer's mock-up.

**Files:**
- Modify: `plat.py` (imports, new `by_roles`)
- Modify: `drawtown.py:83` (roof colours keyed by folders as well as boxes)
- Modify: `towncode.py` (`town` uses `by_roles` for `ROLES`)
- Test: `test_plat.py`, `test_towncode.py`

**Interfaces:**
- Consumes: `roles.roles(model) -> {id: role}`, `roles.graph(model, ids) -> (imports, importers)`, `roles.script_groups(model, found) -> {helper: [scripts]}`, the role constants `DOOR`, `STREET`, `FOUNDATION`, `SIDE`, `SCRIPT`, `NAMED`, `ISLAND` and `STANDALONE`, and `District.pack(entries)`.
- Produces: `plat.by_roles(model, rows) -> (Plat, layers.Rows)`. Its `Rows.districts` maps each role district's name to its band.

- [ ] **Step 1: Write the failing tests**

In `test_plat.py`, add `import problems`, `from roads import Roads`, `from townmap import TownMap`, and:

```python
def role_model():
    model = Model(repo="roles")

    def add(id_, entry=False, kind="source"):
        model.modules[id_] = Module(id=id_, district=id_.split("/")[0], kind=kind, loc=40,
                                    is_entry=entry)

    add("app/main.py", entry=True)
    for id_ in ("core/a.py", "core/b.py", "core/util.py", "old/dead.py"):
        add(id_)
    add("tools/run.py", entry=True)
    add("web/ui.js", kind="unsurveyed")
    for edge in [("app/main.py", "core/a.py"), ("app/main.py", "core/b.py"),
                 ("app/main.py", "core/util.py"), ("core/a.py", "core/util.py"),
                 ("core/b.py", "core/util.py")]:
        model.edges[edge] = 1
    model.externals = {"yaml": ["core/a.py"]}
    return model


class RolesLayoutTest(unittest.TestCase):
    def test_districts_are_roles_from_back_to_front(self):
        layout, bands = plat.by_roles(role_model(), Rows())
        lots = {name: sorted(d.lots) for name, d in layout.districts.items()}
        self.assertEqual(lots, {"/foundations": ["core/util.py"],
                                "/main street": ["app/main.py", "core/a.py", "core/b.py"],
                                "/standalone scripts": ["tools/run.py"],
                                "/islands": ["old/dead.py"], "/unsurveyed": ["web/ui.js"]})
        order = ["/foundations", "/main street", "/standalone scripts", "/islands", "/unsurveyed"]
        self.assertEqual(sorted(order, key=bands.districts.get), order)
        self.assertEqual(layout.harbor, ["yaml"])

    def test_the_front_door_opens_the_main_street(self):
        layout, _ = plat.by_roles(role_model(), Rows())
        self.assertEqual(layout.districts["/main street"].lots["app/main.py"][:2], [0, 0])

    def test_a_town_laid_out_by_roles_has_every_building_and_no_highways(self):
        model = role_model()
        rows = Rows().update(model)
        layout, bands = plat.by_roles(model, rows)
        found = problems.find(model, rows)
        town = TownMap(model, layout, bands, found)
        self.assertEqual(sorted(town.buildings), sorted(m.id for m in model.of_kind("source")))
        self.assertEqual(Roads(town, model, found)._highways(), [])
```

In `test_towncode.py`:

```python
    def test_snapshot_lays_out_by_roles_without_saving_it(self):
        png = os.path.join(self.out, "town.png")
        self.assertEqual(self.snapshot(png, "--size", "40x30"), 0)
        saved = self.saved("plat.json")
        self.assertEqual(self.snapshot(png, "--layout", "roles", "--size", "40x30"), 0)
        self.assertEqual(self.saved("plat.json"), saved)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m unittest test_plat test_towncode -v`
Expected: FAIL with `AttributeError: module 'plat' has no attribute 'by_roles'`. The towncode test passes or fails depending on whether `town` ignores the layout yet. It must pass after Step 4.

- [ ] **Step 3: Implement `plat.by_roles`**

Imports in `plat.py`: add `import roles` and `from layers import Rows`. At the end of the file:

```python
def by_roles(model, rows):
    """A plat laid out by role instead of folder, and the band each district stands in.

    Back to front: foundations and what only scripts use, the main street from the front door,
    scripts grouped by the helper they share, what no import reaches, then unsurveyed files.
    Laid out afresh on every run and never saved. Names start with "/" so no folder can share
    one, and no district highway finds them.
    """
    found = roles.roles(model)
    _, importers = roles.graph(model, found)

    def of(*kinds):
        return sorted(m for m, role in found.items() if role in kinds)

    groups = [(2, "/standalone scripts" if key == roles.STANDALONE else f"/scripts/{key}",
               sorted(members, key=lambda m: (m != key, m)))
              for key, members in sorted(roles.script_groups(model, found).items())]
    order = [(0, "/foundations",
              sorted(of(roles.FOUNDATION), key=lambda m: (-len(importers[m]), m)) + of(roles.SIDE)),
             (1, "/main street",
              of(roles.DOOR) + sorted(of(roles.STREET), key=lambda m: (-rows.modules.get(m, 0), m))),
             *groups,
             (3, "/named", of(roles.NAMED)),
             (3, "/islands", of(roles.ISLAND)),
             (4, "/unsurveyed", sorted(m.id for m in model.of_kind("unsurveyed")))]
    districts, bands = {}, {}
    for band, name, members in order:
        if members:
            districts[name] = District.pack([(m, footprint(model.modules[m].loc), 0)
                                             for m in members])
            bands[name] = band
    return Plat(districts, sorted(model.externals)), Rows(bands)
```

- [ ] **Step 4: Use it in towncode and colour roofs by folder**

In `towncode.py`, change the import to `from plat import Plat, by_roles`. Then in `town`, before building the `TownMap`:

```python
    found = problems.find(model, rows)
    if layout == ROLES:
        plat, rows = by_roles(model, rows)
    tmap = TownMap(model, plat, rows, found, sites)
```

`problems.find` runs on the real rows first. That's on purpose: the bands only place districts.

In `drawtown.py`, replace the `self.roofs = ...` line in `TownScene.__init__`. For the district layout this gives the same colours as before, because every building's folder is already a box:

```python
        names = sorted(set(tmap.boxes) | {b.district for b in tmap.buildings.values()})
        self.roofs = {name: ROOFS[i % len(ROOFS)] for i, name in enumerate(names)}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/python -m unittest -q` (then `python3 -m unittest -q`)
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add plat.py towncode.py drawtown.py test_plat.py test_towncode.py
git commit -m "Add --layout roles: districts by role, laid out afresh and never saved"
```

---

### Task 10: README and side-by-side check on real repositories

**Files:**
- Modify: `README.md:41-56`

- [ ] **Step 1: Update the README's Towncode section**

Replace the code block and paragraph at lines 46-56 with:

````markdown
```bash
python3 towncode.py survey PATH [--check-untouched]   # print the problems
python3 towncode.py view PATH                          # walk the town
python3 towncode.py view PATH --session                # what the newest agent session changed
python3 towncode.py snapshot PATH out.png --zoom district --at MODULE
python3 towncode.py snapshot PATH out.png --layout roles   # laid out by role, not folder
```

Folders are districts, modules are buildings, imports are roads and outside
packages are warehouses in the harbor. Each building is a cake: one floor per
function, the biggest at the bottom, and amber for a function of 100+ lines.
Select a building and what it uses turns blue, what uses it pink, and the rest
dims. `--session` keeps an agent session's changes in focus instead, with its
new uncommitted files as orange sites at the front of town. Problems show up in
the town: fire for code that won't parse, red loops for import cycles, towers,
boarded-up buildings and more (see `docs/superpowers/specs/`). The survey, rows
and plat are saved in `.survey/`, never inside the surveyed repository.
````

- [ ] **Step 2: Run the full suite both ways**

Run: `.venv/bin/python -m unittest -q && python3 -m unittest -q`
Expected: both OK (system python reports skips).

- [ ] **Step 3: Render both layouts side by side**

```bash
mkdir -p /tmp/towncode-live
for repo in ~/codetown /tmp/towncode-cal/cobra /tmp/towncode-cal/ripgrep /tmp/towncode-cal/zustand; do
  name=$(basename "$repo")
  for layout in districts roles; do
    .venv/bin/python towncode.py snapshot "$repo" "/tmp/towncode-live/$name-$layout.png" \
      --layout "$layout" --zoom town --size 640x400 --scale 2 || echo "FAILED $name $layout"
  done
done
```

Open each pair. Check:
- Cakes stand on their lots.
- No building is cut off at the top of the frame.
- `ripgrep`'s `crates/core/flags/defs.rs` is squashed to the cap.
- Roles towns put the front door on the main street.

Note any repository where the roles layout looks worse. Plan 3 says the two are compared before any default changes.

- [ ] **Step 4: The monorepo, read only**

```bash
.venv/bin/python towncode.py survey ~/repos/big-monorepo --check-untouched
.venv/bin/python towncode.py snapshot ~/repos/big-monorepo /tmp/towncode-live/monorepo-districts.png --zoom town --size 640x400 --scale 2
.venv/bin/python towncode.py snapshot ~/repos/big-monorepo /tmp/towncode-live/monorepo-roles.png --layout roles --zoom town --size 640x400 --scale 2
```

Expected: `untouched: yes`. Both PNGs are written to `/tmp`. Never import, run or test the monorepo's code.

- [ ] **Step 5: Time the whole-town drawing**

```bash
.venv/bin/python - <<'EOF'
import time, towncode
model, rows, plat, _ = towncode.run("~/repos/big-monorepo")
v = towncode.town(model, rows, plat)
v.zoom = "town"
start = time.monotonic(); v.frame(160, 45); print(f"town zoom: {time.monotonic() - start:.2f}s")
EOF
```

Compare this with the same timing on `main`, run from a temporary worktree. If it's more than twice as slow, report it before going on. Don't optimise inside this plan.

- [ ] **Step 6: Commit**

```bash
git add README.md
git commit -m "Document cakes, focus, --session and --layout roles in the README"
```

Then hand over with `superpowers:finishing-a-development-branch`. Pushing or opening a PR needs the user's go-ahead. The PR body must say that `session.py` (the designer's) had its `towncode` import moved, and why.
