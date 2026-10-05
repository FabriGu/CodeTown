# Towncode Town (Milestone 1, Plan 2 of 2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Draw a surveyed repository as an isometric pixel town in the terminal, where every problem can be seen, and let the user move a cursor, zoom, inspect buildings and jump between problems worst first.

**Architecture:** A saved `Plat` (next to `rows.json`, outside the repo) records where every building stands, so placement survives each survey. `TownMap` turns the model, plat, rows and problems into tiles: ground, buildings, plots, warehouses and props. `Roads` routes imports along the streets and decides which are drawn. `drawtown.TownScene` paints the map back to front into the game's RGB framebuffer, reusing its projection, ground colours, wall technique and trees. `viewer.Viewer` adds the cursor, three zoom levels, the inspector and problem walking. `towncode view` and `towncode snapshot` tie it together.

**Tech Stack:** Python 3.10+ standard library only (`json`, `math`, `dataclasses`, `collections`, `unittest`), git CLI, ANSI truecolor or 256 colours.

**Spec:** `docs/superpowers/specs/2026-09-30-codetown-site-plan-design.md`

**Builds on:** Plan 1, `docs/superpowers/plans/2026-09-30-towncode-survey.md` (branch `towncode-survey`, 122 tests passing).

## Global Constraints

- Python 3.10+ standard library only. Flat modules in `~/codetown`, matching the existing files. Tests use `unittest`; run everything with `python3 -m unittest` from `~/codetown`.
- Work on a new branch `towncode-render` created from `towncode-survey`. The pushed `towncode-town` branch is the prototype this plan was checked against; leave it alone until the designer has looked at it.
- The surveyed repository stays read-only, with every Plan 1 guarantee unchanged:
  - The only new git command is `git log --reverse -M --diff-filter=R --name-status --format=`, run through the existing `Repo._git` (read-only flags, `GIT_OPTIONAL_LOCKS=0`).
  - `towncode snapshot` refuses an output path inside the repository. `towncode view` writes nothing but the saved survey files.
  - Code is never imported, executed or tested.
- `plat.json` is saved next to `model.json` and `rows.json` and holds names and numbers only.
- Same input gives the same picture: everything iterated is sorted, and randomness comes from `render.hash2` of tile coordinates. Tests compare frames pixel for pixel.
- First real target: `~/repos/big-monorepo`. Never edit it, never run its code, never commit to it. Snapshots of it go to `/tmp`, never into either repository.
- Commits in this plan happen in `~/codetown` only.

## Decisions this plan makes

These go beyond or against the spec. Each is small and easy to undo; tell the user about them when the plan is done.

1. **Three zoom levels, not two.** Street level (1:1, drawn live around the cursor), district (half size) and town (shrunk to fit). At half size and below, windows, doors and signs blur together, so the playful detail needs a 1:1 level.
2. **The gate stands in front of its building.** The spec puts gates for run-directly modules at the town's front edge. Here the gate stands on the street in front of the building's door, so you can tell which building it belongs to.
3. **`d` moves right.** WASD and the arrow keys move the cursor. The spec's `d` for "send Clawd" belongs to Milestone 2, which must pick another key or give up WASD.
4. **Rearranging the town means deleting `plat.json`.** There is no command for it yet. The error for a damaged plat says so.
5. **A lot's size is fixed when it is placed.** A module that grows keeps its footprint until the town is rearranged; its height (floors) still follows complexity.
6. **Lots never move inside their district.** A district that grows a new line can push the districts in front of it, and widening one pushes those to its right.
7. **The harbor is one line of warehouses.** The map widens to fit it.
8. **Plan 1's outline changed in four places, to match the spec.** Hotspots get cracked, shimmering paving, not scaffolding. Unsurveyed files get a gray outline, not fog. Tests get an annex per building, not a yard per district. Zoom shrinks the 1:1 drawing by averaging, so `iso.py` is unchanged.

Not in this plan: Clawd and `d`/`f`/`b` (Milestone 2), and drawing inefficient code so that its inefficiency is self-evident (later).

## File Structure

| File | Responsibility |
| --- | --- |
| `plat.py` | Saved placement: lots per district, free plots, vacant lots, harbor slots |
| `townmap.py` | The town as tiles: ground kinds, buildings, plots, warehouses, props, wear |
| `roads.py` | Imports routed along the streets, and which roads are drawn |
| `drawtown.py` | Paints a `TownMap` into a framebuffer, back to front |
| `viewer.py` | Cursor, zoom, inspector, problem walking, and the terminal loop |
| `repo.py`, `model.py`, `survey.py`, `layers.py` | Modified: renamed modules keep their row |
| `term.py` | Modified: `parse_keys` takes a keymap |
| `towncode.py` | Modified: saves the plat; adds `view` and `snapshot` |
| `README.md` | Modified: a Towncode section |
| `test_*.py` | `test_plat`, `test_townmap`, `test_roads`, `test_drawtown`, `test_viewer`; additions to `test_repo`, `test_survey`, `test_layers`, `test_towncode`, `test_smoke` |

---

### Task 1: Renamed modules keep their row

The spec says renamed modules keep their plot. The plot comes in Task 2; this task follows renames through git history so the saved row can move with the module.

**Files:**
- Modify: `repo.py`, `model.py`, `survey.py`, `layers.py`
- Test: `test_repo.py`, `test_survey.py`, `test_layers.py`

**Interfaces:**
- Consumes: `Repo._git(*args) -> str` (Plan 1's read-only git), `fixture.make_repo`, `fixture.git`, `Rows.modules`
- Produces:
  - `Repo.renames() -> dict[str, str]`: each old path to the path it has now, following chains (`a.py` to `b.py` to `pkg/c.py` maps both `a.py` and `b.py` to `pkg/c.py`)
  - `Model.renames: dict[str, str]`, saved in `model.json`; a `model.json` saved by Plan 1 loads with `{}`
  - `survey.survey(root)` keeps only renames that end at a current module and whose old path is gone
  - `Rows.update(model)` first moves a renamed module's saved row to its new path

- [ ] **Step 1: Write the failing tests**

In `test_repo.py`, replace:

```python
    def test_reading_leaves_the_repo_untouched(self):
```

with:

```python
    def test_renames_follow_a_chain_to_the_current_path(self):
        fixture.git(self.root, "mv", "a.py", "b.py")
        fixture.git(self.root, "commit", "-q", "-m", "rename")
        fixture.git(self.root, "mv", "b.py", "pkg/c.py")
        fixture.git(self.root, "commit", "-q", "-m", "move")
        self.assertEqual(Repo(self.root).renames(), {"a.py": "pkg/c.py", "b.py": "pkg/c.py"})

    def test_reading_leaves_the_repo_untouched(self):
```

In `test_survey.py`, replace:

```python
    def test_model_round_trips_through_json(self):
        self.assertEqual(Model.from_dict(self.model.to_dict()), self.model)
```

with:

```python
    def test_model_round_trips_through_json(self):
        self.assertEqual(Model.from_dict(self.model.to_dict()), self.model)

    def test_a_model_saved_before_renames_still_loads(self):
        data = self.model.to_dict()
        del data["renames"]
        self.assertEqual(Model.from_dict(data).renames, {})

    def test_renames_that_end_at_a_current_module_are_recorded(self):
        root = fixture.make_repo(self, {"hub/old.py": "x = 1\n", "hub/keep.py": "y = 2\n"})
        fixture.git(root, "mv", "hub/old.py", "hub/new.py")
        fixture.git(root, "commit", "-q", "-m", "rename")
        self.assertEqual(survey.survey(root).renames, {"hub/old.py": "hub/new.py"})
```

In `test_layers.py`, replace:

```python
    def test_rows_round_trip_and_a_missing_file_is_empty(self):
```

with:

```python
    def test_a_renamed_module_keeps_its_row(self):
        rows = Rows({"hub": 1, "packages": 0}, {"hub/old.py": 3})
        self.model.renames = {"hub/old.py": "hub/records.py"}
        rows.update(self.model)
        self.assertEqual(rows.modules["hub/records.py"], 3)
        self.assertNotIn("hub/old.py", rows.modules)

    def test_rows_round_trip_and_a_missing_file_is_empty(self):
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m unittest test_repo test_survey test_layers`
Expected: the 4 new tests fail (3 errors, 1 failure): `'Repo' object has no attribute 'renames'`, `KeyError: 'renames'`, `'Model' object has no attribute 'renames'`, and `AssertionError: 0 != 3` for the renamed module's row.

- [ ] **Step 3: Follow renames**

In `repo.py`, replace:

```python
            if line.strip():
                counts[line] = counts.get(line, 0) + 1
        return counts
```

with:

```python
            if line.strip():
                counts[line] = counts.get(line, 0) + 1
        return counts

    def renames(self):
        """Old path -> the path it has now, following chains of renames to the end."""
        out = self._git("log", "--reverse", "-M", "--diff-filter=R", "--name-status",
                        "--format=")
        found = {}
        for line in out.splitlines():
            parts = line.split("\t")
            if len(parts) != 3 or not parts[0].startswith("R"):
                continue
            old, new = parts[1], parts[2]
            for earlier, now in found.items():
                if now == old:
                    found[earlier] = new
            found[old] = new
        return {old: new for old, new in sorted(found.items()) if old != new}
```

In `model.py`, replace:

```python
    externals: dict = field(default_factory=dict)
```

with:

```python
    externals: dict = field(default_factory=dict)
    renames: dict = field(default_factory=dict)
```

In `model.py`, replace:

```python
            "externals": {k: sorted(v) for k, v in sorted(self.externals.items())},
```

with:

```python
            "externals": {k: sorted(v) for k, v in sorted(self.externals.items())},
            "renames": dict(sorted(self.renames.items())),
```

In `model.py`, replace:

```python
            externals={k: list(v) for k, v in data["externals"].items()},
```

with:

```python
            externals={k: list(v) for k, v in data["externals"].items()},
            renames=dict(data.get("renames", {})),
```

In `survey.py`, replace:

```python
    _connect(model, facts, resolver)
```

with:

```python
    model.renames = {old: new for old, new in repo.renames().items()
                     if new in model.modules and old not in model.modules}
    _connect(model, facts, resolver)
```

In `layers.py`, replace:

```python
    def update(self, model):
```

with:

```python
    def update(self, model):
        for old, new in sorted(model.renames.items()):
            if old in self.modules and new not in self.modules:
                self.modules[new] = self.modules.pop(old)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3 -m unittest test_repo test_survey test_layers`
Expected: 32 tests, all `ok`.

- [ ] **Step 5: Run the whole suite**

Run: `python3 -m unittest`
Expected: 126 tests pass.

- [ ] **Step 6: Commit**

```bash
git add repo.py model.py survey.py layers.py test_repo.py test_survey.py test_layers.py
git commit -m "Follow renames so a moved module keeps its row"
```


---

### Task 2: The plat

The plat is where every building stands, saved between surveys. The rules, from the spec:

- A module's footprint comes from its lines of code: 1×1 below 100 lines, 2×2 below 400, 3×3 below 1000, else 4×4. Tests get no lot (they become annexes in Task 5); unsurveyed files get a lot like any other module.
- Inside a district, lots stand in lines, back to front by module layer (foundations at the back), alphabetical within a layer. Lines are shared between layers so a district stays compact. Every lot is bottom-aligned in its line, so every door faces the street in front of the line. The gap column after each lot is a street too.
- A district is as wide as it needs for 30% of its area to stay free (`width = ceil(sqrt(sum((size + 1)^2) / 0.7))`, and at least the biggest lot plus a street). Each line is filled only to 70% of that width, so every line has room to grow.
- A new module takes the nearest free plot: lines of its own layer first, then the closest layer; among those, the line nearest the back, then the leftmost plot. If nothing fits, a new line opens at the district's front.
- A deleted module leaves a vacant lot, which a later lot may cover. A renamed module keeps its lot if it stays in the same district.
- The harbor is a list of slots, one per outside package. A package that disappears leaves an empty slot (`None`), and the next new package fills the first empty slot.

**Files:**
- Create: `plat.py`
- Test: `test_plat.py`

**Interfaces:**
- Consumes: `model.Model` (`modules`, `externals`, `renames`), `model.Module` (`id`, `district`, `kind`, `loc`), `layers.Rows.modules` (module to layer)
- Produces:
  - `plat.footprint(loc) -> int` (1 to 4) and `plat.placed(model) -> dict[str, Module]` (every module except tests)
  - `plat.District(w=0, h=0, lines=[], lots={}, vacant=[])`, in tiles local to the district: `lines` holds `[top, height, layer]` back to front, `lots` maps a module to `[x, y, size]`, and `vacant` holds `[x, y, size]`
  - `District.pack(entries) -> District`, where `entries` is `[(module, size, layer), ...]` in layer-then-name order
  - `District.place(module, size, layer)` and `District.streets() -> set[tuple[int, int]]`
  - `plat.Plat(districts=None, harbor=None)` with `.districts` (name to `District`) and `.harbor` (package names, `None` for an empty slot)
  - `Plat.update(model, rows) -> Plat`, `Plat.save(path)`, and `Plat.load(path) -> Plat` (a missing file gives an empty plat)

- [ ] **Step 1: Write the failing test**

Create `test_plat.py`:

```python
import copy
import os
import shutil
import tempfile
import unittest

import plat
from layers import Rows
from model import Model, Module
from plat import District, Plat


def town_model(locs):
    model = Model(repo="r")
    for id_, loc in locs.items():
        model.modules[id_] = Module(id=id_, district=id_.split("/")[0], kind="source", loc=loc)
    return model


def tiles(lot):
    x, y, size = lot
    return {(x + i, y + j) for i in range(size) for j in range(size)}


class FootprintTest(unittest.TestCase):
    def test_lines_of_code_set_the_lot_size(self):
        self.assertEqual([plat.footprint(n) for n in (0, 99, 100, 399, 400, 999, 1000, 9000)],
                         [1, 1, 2, 2, 3, 3, 4, 4])


class DistrictTest(unittest.TestCase):
    def setUp(self):
        self.d = District.pack([("a", 1, 0), ("b", 2, 0), ("c", 1, 0), ("d", 3, 1)])

    def assert_sound(self):
        streets = self.d.streets()
        seen = set()
        for x, y, size in self.d.lots.values():
            lot = tiles((x, y, size))
            self.assertFalse(lot & seen, "lots overlap")
            self.assertFalse(lot & streets, "a lot sits on a street")
            self.assertTrue(all((x + i, y + size) in streets for i in range(size)),
                            "no street in front")
            self.assertLessEqual(x + size, self.d.w)
            seen |= lot

    def test_lots_never_overlap_and_every_door_faces_a_street(self):
        self.assert_sound()

    def test_later_layers_never_stand_behind_earlier_ones(self):
        self.assertGreaterEqual(self.d.lots["d"][1], self.d.lots["b"][1])

    def test_lines_read_alphabetically_back_to_front_then_left_to_right(self):
        reading = sorted(self.d.lots, key=lambda m: (sum(self.d.lots[m][1:]), self.d.lots[m][0]))
        self.assertEqual(reading, ["a", "b", "c", "d"])

    def test_at_least_30_percent_of_each_line_is_free(self):
        for top, height, _ in self.d.lines:
            used = max(x + s for x, y, s in self.d.lots.values() if y + s == top + height)
            self.assertGreaterEqual(self.d.w - used, int(self.d.w * plat.FREE))

    def test_a_new_module_takes_a_free_plot_in_a_line_of_its_layer(self):
        self.d.place("e", 1, 0)
        x, y, size = self.d.lots["e"]
        top, height, _ = self.d.lines[0]
        self.assertEqual(y + size, top + height)
        self.assert_sound()

    def test_when_nothing_fits_a_new_line_opens_at_the_front(self):
        h = self.d.h
        self.d.place("big", 4, 0)
        self.assertEqual(self.d.lots["big"], [0, h, 4])
        self.assert_sound()


class PlatTest(unittest.TestCase):
    def setUp(self):
        self.model = town_model({"hub/app.py": 500, "hub/records.py": 50, "packages/sdk.py": 150})
        self.model.externals = {"flask": ["hub/app.py"], "yaml": ["packages/sdk.py"]}
        self.rows = Rows().update(self.model)
        self.plat = Plat().update(self.model, self.rows)

    def lots(self, p=None):
        return {m: lot for d in (p or self.plat).districts.values() for m, lot in d.lots.items()}

    def test_every_module_but_tests_gets_a_lot_sized_by_its_lines(self):
        self.model.modules["tests/test_app.py"] = Module("tests/test_app.py", "tests", "test")
        lots = self.lots(Plat().update(self.model, self.rows))
        self.assertEqual(sorted(lots), ["hub/app.py", "hub/records.py", "packages/sdk.py"])
        self.assertEqual(lots["hub/app.py"][2], 3)

    def test_existing_lots_stay_put_when_a_module_arrives(self):
        before = copy.deepcopy(self.lots())
        self.model.modules["hub/new.py"] = Module("hub/new.py", "hub", "source", loc=10)
        self.plat.update(self.model, self.rows)
        after = self.lots()
        self.assertEqual({m: after[m] for m in before}, before)
        self.assertIn("hub/new.py", after)

    def test_a_deleted_module_leaves_a_vacant_lot(self):
        lot = self.lots()["hub/records.py"]
        del self.model.modules["hub/records.py"]
        self.plat.update(self.model, self.rows)
        self.assertNotIn("hub/records.py", self.lots())
        self.assertIn(lot, self.plat.districts["hub"].vacant)

    def test_a_renamed_module_keeps_its_lot(self):
        lot = self.lots()["hub/records.py"]
        m = self.model.modules.pop("hub/records.py")
        m.id = "hub/store.py"
        self.model.modules[m.id] = m
        self.model.renames = {"hub/records.py": "hub/store.py"}
        self.plat.update(self.model, self.rows)
        self.assertEqual(self.lots()["hub/store.py"], lot)
        self.assertEqual(self.plat.districts["hub"].vacant, [])

    def test_outside_packages_keep_their_harbor_slot(self):
        self.assertEqual(self.plat.harbor, ["flask", "yaml"])
        self.model.externals = {"requests": ["hub/app.py"], "yaml": ["packages/sdk.py"]}
        self.plat.update(self.model, self.rows)
        self.assertEqual(self.plat.harbor, ["requests", "yaml"])

    def test_the_same_model_always_gives_the_same_plat(self):
        again = Plat().update(self.model, self.rows)
        self.assertEqual(self.lots(again), self.lots())

    def test_plat_round_trips_and_a_missing_file_is_empty(self):
        folder = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, folder)
        path = os.path.join(folder, "plat.json")
        self.plat.save(path)
        loaded = Plat.load(path)
        self.assertEqual((loaded.districts, loaded.harbor), (self.plat.districts, self.plat.harbor))
        self.assertEqual(Plat.load(path + ".missing").districts, {})
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python3 -m unittest test_plat`
Expected: `ModuleNotFoundError: No module named 'plat'`.

- [ ] **Step 3: Write the plat**

Create `plat.py`:

```python
"""The plat: where every building stands, saved so placement survives each survey.

Districts sit in rows by dependency layer, alphabetical within a row. Inside a
district, lots sit in lines, back to front by module layer and alphabetical
within a layer. Every lot is bottom-aligned so its door faces the street in
front of its line. Each line is filled only to 70% of the district's width; the
rest is free plots for growth.
"""

import json
import math
import os
from dataclasses import asdict, dataclass, field

FREE = 0.3
STREET = 1
SIZES = ((100, 1), (400, 2), (1000, 3))
MAX_SIZE = 4


def footprint(loc):
    """Lot size in tiles, from lines of code: 1x1 up to 4x4."""
    for limit, size in SIZES:
        if loc < limit:
            return size
    return MAX_SIZE


def placed(model):
    """Modules that stand on a lot: everything except tests."""
    return {m.id: m for m in model.modules.values() if m.kind != "test"}


def _overlaps(a, b):
    ax, ay, asize = a
    bx, by, bsize = b
    return ax < bx + bsize and bx < ax + asize and ay < by + bsize and by < ay + asize


@dataclass
class District:
    w: int = 0
    h: int = 0
    lines: list = field(default_factory=list)   # [top, height, layer]
    lots: dict = field(default_factory=dict)    # module -> [x, y, size]
    vacant: list = field(default_factory=list)  # [x, y, size] left by deleted modules

    @classmethod
    def pack(cls, entries):
        """A fresh district from (module, size, layer) entries sorted by (layer, module)."""
        biggest = max(size for _, size, _ in entries)
        area = sum((size + STREET) ** 2 for _, size, _ in entries)
        width = max(biggest + STREET, math.ceil(math.sqrt(area / (1 - FREE))))
        fill = max(biggest, round(width * (1 - FREE)))
        d = cls(w=width)
        line = []
        for entry in entries:
            _, size, _ = entry
            if line and d._end(line) + size > fill:
                d._close(line)
                line = []
            line.append(entry)
        d._close(line)
        return d

    def _end(self, line):
        return sum(size + STREET for _, size, _ in line)

    def _close(self, line):
        top, height = self.h, max(size for _, size, _ in line)
        x = 0
        for module, size, _ in line:
            self.lots[module] = [x, top + height - size, size]
            x += size + STREET
        self.lines.append([top, height, line[0][2]])
        self.h = top + height + STREET

    def place(self, module, size, layer):
        """Put a new module on the nearest free plot: its own layer's lines first."""
        best = None
        for i, (top, height, line_layer) in enumerate(self.lines):
            if height < size:
                continue
            front = top + height
            taken = [(x, s) for x, y, s in self.lots.values() if y + s == front]
            for x in range(self.w - size + 1):
                if all(x + size + STREET <= tx or x >= tx + ts + STREET for tx, ts in taken):
                    key = (abs(line_layer - layer), i, x)
                    if best is None or key < best[0]:
                        best = (key, [x, front - size, size])
                    break
        if best is None:
            top = self.h
            self.lines.append([top, size, layer])
            self.h = top + size + STREET
            self.w = max(self.w, size)
            lot = [0, top, size]
        else:
            lot = best[1]
        self.lots[module] = lot
        self.vacant = [v for v in self.vacant if not _overlaps(v, lot)]

    def streets(self):
        """Tiles of this district's streets, relative to its corner."""
        tiles = set()
        every = list(self.lots.values()) + self.vacant
        for top, height, _ in self.lines:
            front = top + height
            tiles.update((x, front) for x in range(self.w))
            for x, y, s in every:
                if y + s == front and x + s < self.w:
                    tiles.update((x + s, row) for row in range(top, front))
        return tiles


class Plat:
    def __init__(self, districts=None, harbor=None):
        self.districts = dict(districts or {})
        self.harbor = list(harbor or [])

    def update(self, model, rows):
        here = placed(model)
        where = {m: name for name, d in self.districts.items() for m in d.lots}
        for old, new in sorted(model.renames.items()):
            if old in where and new not in where and new in here \
                    and here[new].district == where[old]:
                d = self.districts[where[old]]
                d.lots[new] = d.lots.pop(old)
                where[new] = where.pop(old)
        for name, d in self.districts.items():
            for module in sorted(d.lots):
                if module not in here or here[module].district != name:
                    d.vacant.append(d.lots.pop(module))
                    where.pop(module)
        new = {}
        for m in sorted(here.values(), key=lambda m: (rows.modules.get(m.id, 0), m.id)):
            if m.id not in where:
                new.setdefault(m.district, []).append(
                    (m.id, footprint(m.loc), rows.modules.get(m.id, 0)))
        for name, entries in sorted(new.items()):
            if name not in self.districts:
                self.districts[name] = District.pack(entries)
                continue
            for module, size, layer in entries:
                self.districts[name].place(module, size, layer)
        self.harbor = [p if p in model.externals else None for p in self.harbor]
        for package in sorted(model.externals):
            if package in self.harbor:
                continue
            if None in self.harbor:
                self.harbor[self.harbor.index(None)] = package
            else:
                self.harbor.append(package)
        return self

    def save(self, path):
        data = {"districts": {n: asdict(d) for n, d in sorted(self.districts.items())},
                "harbor": self.harbor}
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=1, sort_keys=True)

    @classmethod
    def load(cls, path):
        if not os.path.exists(path):
            return cls()
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return cls({n: District(**d) for n, d in data["districts"].items()}, data["harbor"])
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python3 -m unittest test_plat`
Expected: 14 tests, all `ok`.

- [ ] **Step 5: Run the whole suite**

Run: `python3 -m unittest`
Expected: 140 tests pass.

- [ ] **Step 6: Commit**

```bash
git add plat.py test_plat.py
git commit -m "Lay out districts on a saved plat with room to grow"
```


---

### Task 3: The town as tiles

`TownMap` places the plat on one grid, back to front (small `y` is the back):

- Open water at `y` 0 and 1, and the harbor's warehouses on docks at `y` 2 and 3.
- The quay at `y` 4, then an avenue at `y` 5 and 6. Districts start at `y` 7.
- Each row of districts is one dependency layer, foundations at the back, alphabetical left to right. The rows are separated by two-tile avenues, which also run down both sides of the town and to the right of each district.
- A two-tile grass margin edges the island.

Each source module becomes a `Building`, and each unsurveyed file becomes a plot.

- **Height:** 1 floor plus 1 per 30 points of complexity, at most 6. A tower always gets 9 floors and casts a shadow 3 tiles to its right.
- **Doors:** none without exports, else 1 door per 6 exports, at most the building's width.
- **Props on the street tile in front of the door:**
  - a gate for a module meant to be run directly;
  - a no-entry sign for a backwards road;
  - a yellow sign for notes left.
- **Worn paving:** the street and avenue tiles around a building wear with its commits. A hotspot also marks them hot (cracked and shimmering).
- **Trees:** they grow only on grass, one tile in four outside districts. Inside a district, one tile in eight gets a bush.

**Files:**
- Create: `townmap.py`
- Test: `test_townmap.py`

**Interfaces:**
- Consumes: `Plat.districts`, `Plat.harbor`, `District.streets()`, `District.lots`, `District.vacant`, `District.w`, `District.h`, `Rows.districts`, `problems.find(model, rows) -> list[Problem]` (`kind`, `module`, `reason`, `other`; worst first), the kind names in `problems` (`TOWER`, `BACKWARDS`, `NOTES`, `HOTSPOT`), and `render.hash2`
- Produces:
  - `Building` (frozen): `module`, `district`, `x`, `y`, `size`, `floors`, `doors`, `tested`, `problems` (frozenset of kinds), `churn`, `entry`. Its methods are `door()` (middle tile of the front edge), `front()` (the street tile in front of the door) and `tiles()`.
  - `Warehouse` (frozen): `package`, `x`, `y`, `users` (tuple of modules), `size=2`. Its methods are `front()` (the quay tile in front) and `tiles()`.
  - `floors(module, kinds) -> int` and `door_count(module, size) -> int`
  - `TownMap(model, plat, rows, found)` attributes:
    - size: `.width`, `.height`;
    - ground: `.ground` maps a tile to `water`, `dock`, `quay`, `avenue`, `street`, `lot`, `plot` or `vacant`; everything else is grass;
    - contents: `.buildings`, `.plots` (module to `(x, y, size)`), `.vacant`, `.warehouses`;
    - layout: `.boxes` (district to `(x, y, w, h)`), `.bands` (`(top, bottom)` per row of districts);
    - problems and props: `.problems` (module to its problems), `.props` (tile to a sorted list of `gate`, `no entry`, `notes`);
    - paving and greenery: `.wear` (tile to commits), `.hot`, `.shadow`, `.trees`, `.bushes`;
    - lookup: `.at` (tile to `Building` or `Warehouse`).
  - `TownMap` methods: `kind(x, y)`, `walkable(x, y)` (street, avenue or quay), `thing_at(x, y)` (a `Building`, a `Warehouse`, `("plot", module)`, `("vacant", None)` or `None`), and `centre(module)`
  - `test_townmap.showcase() -> (model, rows)` and `test_townmap.build() -> (model, rows, found, tmap)`: a small town holding all ten problems, reused by Tasks 4 to 6

- [ ] **Step 1: Write the failing test**

Create `test_townmap.py`:

```python
import unittest

import problems
from layers import Rows
from model import Model, Module
from plat import Plat
from townmap import TownMap, door_count, floors

TESTED = ["tests/test_core.py"]


def showcase():
    """A small town with every problem in it, and the rows it was first laid out with."""
    model = Model(repo="showcase")

    def add(id_, loc=40, complexity=5, exports=("run",), kind="source", **facts):
        model.modules[id_] = Module(id=id_, district=id_.split("/")[0], kind=kind, loc=loc,
                                    complexity=complexity, exports=list(exports), **facts)

    add("core/base.py", loc=300, complexity=40, tested_by=TESTED, churn=2)
    add("core/broken.py", parse_error="line 3: invalid syntax", tested_by=TESTED)
    add("core/doors.py", loc=30, exports=[f"f{i}" for i in range(8)], tested_by=TESTED)
    add("core/loop_a.py", tested_by=TESTED)
    add("core/loop_b.py", tested_by=TESTED)
    add("core/notes.py", notes=2, tested_by=TESTED)
    add("core/tower.py", loc=2400, complexity=260, churn=9, tested_by=TESTED)
    add("app/main.py", loc=120, complexity=12, is_entry=True)
    add("app/helper.py")
    add("app/lonely.py")
    add("web/ui.js", kind="unsurveyed", loc=200, exports=())
    add("tests/test_core.py", kind="test")
    for src, dst in [("app/main.py", "core/base.py"), ("app/main.py", "core/tower.py"),
                     ("app/main.py", "core/doors.py"), ("app/main.py", "core/broken.py"),
                     ("app/main.py", "core/notes.py"), ("app/main.py", "core/loop_a.py"),
                     ("core/loop_a.py", "core/loop_b.py"), ("core/loop_b.py", "core/loop_a.py"),
                     ("core/tower.py", "core/base.py")]:
        model.edges[(src, dst)] = 2 if dst == "core/base.py" else 1
    model.externals = {"flask": ["app/main.py"], "yaml": ["core/base.py"]}
    rows = Rows({"app": 1, "core": 0}).update(model)
    model.edges[("core/notes.py", "app/helper.py")] = 1
    return model, rows


def build():
    model, rows = showcase()
    found = problems.find(model, rows)
    return model, rows, found, TownMap(model, Plat().update(model, rows), rows, found)


class ShowcaseTest(unittest.TestCase):
    def test_the_showcase_has_every_problem(self):
        _, _, found, _ = build()
        self.assertEqual({p.kind for p in found}, set(problems.KINDS))


class TownMapTest(unittest.TestCase):
    def setUp(self):
        self.model, self.rows, self.found, self.town = build()

    def test_every_source_module_is_a_building_and_others_are_plots(self):
        sources = sorted(m.id for m in self.model.of_kind("source"))
        self.assertEqual(sorted(self.town.buildings), sources)
        self.assertEqual(list(self.town.plots), ["web/ui.js"])

    def test_every_door_opens_onto_a_walkable_tile(self):
        for b in list(self.town.buildings.values()) + list(self.town.warehouses.values()):
            self.assertTrue(self.town.walkable(*b.front()), b)

    def test_buildings_never_share_a_tile(self):
        seen = set()
        for b in self.town.buildings.values():
            self.assertFalse(seen & set(b.tiles()))
            seen |= set(b.tiles())

    def test_height_comes_from_complexity_and_towers_break_the_cap(self):
        b = self.town.buildings
        self.assertEqual(b["core/loop_a.py"].floors, 1)
        self.assertEqual(b["core/base.py"].floors, 2)
        self.assertEqual(b["core/tower.py"].floors, 9)
        self.assertEqual(floors(Module("x", "d", "source", complexity=999), frozenset()), 6)

    def test_doors_from_exports_capped_by_frontage(self):
        b = self.town.buildings
        self.assertEqual(b["core/loop_a.py"].doors, 1)
        self.assertEqual(b["core/doors.py"].doors, 1)
        self.assertEqual(b["core/base.py"].doors, 1)
        no_exports = Module("x", "d", "source", loc=900)
        self.assertEqual(door_count(no_exports, 3), 0)
        no_exports.exports = [f"f{i}" for i in range(30)]
        self.assertEqual(door_count(no_exports, 3), 3)

    def test_back_rows_sit_behind_front_rows(self):
        self.assertLess(self.town.boxes["core"][1], self.town.boxes["app"][1])

    def test_the_harbor_is_behind_the_town(self):
        top = min(y for _, y, _, _ in self.town.boxes.values())
        self.assertEqual(sorted(self.town.warehouses), ["flask", "yaml"])
        self.assertTrue(all(w.y + w.size < top for w in self.town.warehouses.values()))

    def test_entry_points_get_a_gate_and_backwards_roads_a_no_entry_sign(self):
        b = self.town.buildings
        self.assertIn("gate", self.town.props[b["app/main.py"].front()])
        self.assertIn("no entry", self.town.props[b["core/notes.py"].front()])

    def test_paving_wears_around_busy_buildings_and_cracks_at_hotspots(self):
        tower = self.town.buildings["core/tower.py"]
        self.assertEqual(self.town.wear[tower.front()], 9)
        self.assertIn(tower.front(), self.town.hot)

    def test_towers_cast_a_shadow(self):
        tower = self.town.buildings["core/tower.py"]
        self.assertIn((tower.x + tower.size, tower.y), self.town.shadow)

    def test_trees_only_grow_where_there_is_no_code(self):
        self.assertTrue(self.town.trees)
        self.assertTrue(all(self.town.kind(*t) == "grass" for t in self.town.trees))

    def test_thing_at_finds_buildings_plots_and_warehouses(self):
        b = self.town.buildings["core/base.py"]
        self.assertIs(self.town.thing_at(b.x, b.y), b)
        x, y, _ = self.town.plots["web/ui.js"]
        self.assertEqual(self.town.thing_at(x, y), ("plot", "web/ui.js"))
        w = self.town.warehouses["flask"]
        self.assertIs(self.town.thing_at(w.x, w.y), w)
        self.assertIsNone(self.town.thing_at(0, self.town.height - 1))
```

The showcase adds `core/notes.py -> app/helper.py` after the rows are set, so the rows stay as given and that import runs forward: a backwards road.

- [ ] **Step 2: Run the test to verify it fails**

Run: `python3 -m unittest test_townmap`
Expected: `ModuleNotFoundError: No module named 'townmap'`.

- [ ] **Step 3: Write the tile map**

Create `townmap.py`:

```python
"""The town as tiles: ground, buildings, plots, warehouses and props.

Back to front: open water, a harbor of warehouses, the quay, then rows of
districts separated by avenues, then a grass margin at the island's front edge.
"""

from dataclasses import dataclass

import problems
from render import hash2

MARGIN = 2
AVENUE = 2
WATER_ROWS = 2
WAREHOUSE = 2
DOCK_STEP = WAREHOUSE + 1
QUAY = WATER_ROWS + WAREHOUSE
TOWN_TOP = QUAY + 1 + AVENUE
FLOOR_COMPLEXITY = 30
MAX_FLOORS = 6
TOWER_FLOORS = 9
EXPORTS_PER_DOOR = 6
SHADOW = 3
TREE_CHANCE = 4
WALKABLE = {"street", "avenue", "quay"}


@dataclass(frozen=True)
class Building:
    module: str
    district: str
    x: int
    y: int
    size: int
    floors: int
    doors: int
    tested: bool
    problems: frozenset
    churn: int
    entry: bool

    def door(self):
        return self.x + (self.size - 1) // 2, self.y + self.size - 1

    def front(self):
        x, y = self.door()
        return x, y + 1

    def tiles(self):
        return [(self.x + i, self.y + j) for j in range(self.size) for i in range(self.size)]


@dataclass(frozen=True)
class Warehouse:
    package: str
    x: int
    y: int
    users: tuple
    size: int = WAREHOUSE

    def front(self):
        return self.x + (self.size - 1) // 2, self.y + self.size

    def tiles(self):
        return [(self.x + i, self.y + j) for j in range(self.size) for i in range(self.size)]


def floors(module, kinds):
    if problems.TOWER in kinds:
        return TOWER_FLOORS
    return min(MAX_FLOORS, 1 + module.complexity // FLOOR_COMPLEXITY)


def door_count(module, size):
    if not module.exports:
        return 0
    return min(size, 1 + (len(module.exports) - 1) // EXPORTS_PER_DOOR)


class TownMap:
    def __init__(self, model, plat, rows, found):
        self.model = model
        self.problems = {}
        for p in found:
            self.problems.setdefault(p.module, []).append(p)
        self.ground = {}
        self.buildings = {}
        self.plots = {}
        self.vacant = []
        self.warehouses = {}
        self.boxes = {}
        self.props = {}
        self.wear = {}
        self.hot = set()
        self.shadow = set()
        self.trees = set()
        self._arrange(plat, rows)
        self._harbor(plat)
        self._avenues()
        self._districts(plat)
        self._surroundings()
        self.at = {}
        for b in list(self.buildings.values()) + list(self.warehouses.values()):
            for tile in b.tiles():
                self.at[tile] = b

    def _arrange(self, plat, rows):
        order = sorted(plat.districts, key=lambda n: (rows.districts.get(n, 0), n))
        self.bands = []
        y = TOWN_TOP
        for layer in sorted({rows.districts.get(n, 0) for n in order}):
            x, height = MARGIN + AVENUE, 0
            for name in (n for n in order if rows.districts.get(n, 0) == layer):
                d = plat.districts[name]
                self.boxes[name] = (x, y, d.w, d.h)
                x += d.w + AVENUE
                height = max(height, d.h)
            self.bands.append((y, y + height))
            y += height + AVENUE
        self.right = max([x + w for x, _, w, _ in self.boxes.values()] or [MARGIN + AVENUE])
        self.right = max(self.right, MARGIN + AVENUE + len(plat.harbor) * DOCK_STEP)
        self.bottom = y
        self.width = self.right + AVENUE + MARGIN
        self.height = self.bottom + MARGIN

    def _harbor(self, plat):
        for x in range(self.width):
            for y in range(QUAY):
                self.ground[(x, y)] = "water"
            self.ground[(x, QUAY)] = "quay"
        for i, package in enumerate(plat.harbor):
            if package is None:
                continue
            w = Warehouse(package, MARGIN + AVENUE + i * DOCK_STEP, WATER_ROWS,
                          tuple(self.model.externals.get(package, ())))
            self.warehouses[package] = w
            for tile in w.tiles():
                self.ground[tile] = "dock"

    def _avenues(self):
        left, top = MARGIN, TOWN_TOP - AVENUE
        rows = [range(top, TOWN_TOP)] + [range(end, end + AVENUE) for _, end in self.bands]
        for band in rows:
            for y in band:
                for x in range(left, self.right + AVENUE):
                    self.ground[(x, y)] = "avenue"
        sides = list(range(left, left + AVENUE)) + list(range(self.right, self.right + AVENUE))
        for y in range(top, self.bottom):
            for x in sides:
                self.ground[(x, y)] = "avenue"
        for bx, by, bw, _ in self.boxes.values():
            band_end = next(end for start, end in self.bands if start == by)
            for y in range(by, band_end):
                for x in range(bx + bw, bx + bw + AVENUE):
                    self.ground[(x, y)] = "avenue"

    def _districts(self, plat):
        for name, d in plat.districts.items():
            bx, by, _, _ = self.boxes[name]
            for x, y in d.streets():
                self.ground[(bx + x, by + y)] = "street"
            for x, y, size in d.vacant:
                self.vacant.append((bx + x, by + y, size))
                for i in range(size):
                    for j in range(size):
                        self.ground[(bx + x + i, by + y + j)] = "vacant"
            for module, (x, y, size) in d.lots.items():
                self._lot(self.model.modules[module], bx + x, by + y, size)

    def _lot(self, m, x, y, size):
        for i in range(size):
            for j in range(size):
                self.ground[(x + i, y + j)] = "lot" if m.kind == "source" else "plot"
        if m.kind != "source":
            self.plots[m.id] = (x, y, size)
            return
        kinds = frozenset(p.kind for p in self.problems.get(m.id, ()))
        b = Building(m.id, m.district, x, y, size, floors(m, kinds), door_count(m, size),
                     bool(m.tested_by), kinds, m.churn, m.is_entry)
        self.buildings[m.id] = b
        if m.is_entry:
            self.props.setdefault(b.front(), []).append("gate")
        if problems.TOWER in kinds:
            self.shadow.update((x + size + i, y + j) for i in range(SHADOW) for j in range(size))

    def _surroundings(self):
        for b in self.buildings.values():
            for p in self.problems.get(b.module, ()):
                if p.kind == problems.BACKWARDS:
                    self.props.setdefault(b.front(), []).append("no entry")
                if p.kind == problems.NOTES:
                    self.props.setdefault(b.front(), []).append("notes")
            for x in range(b.x - 1, b.x + b.size + 1):
                for y in range(b.y - 1, b.y + b.size + 1):
                    if self.ground.get((x, y)) in WALKABLE:
                        self.wear[(x, y)] = max(self.wear.get((x, y), 0), b.churn)
                        if problems.HOTSPOT in b.problems:
                            self.hot.add((x, y))
        for tile in self.props:
            self.props[tile] = sorted(set(self.props[tile]))
        inside = set()
        for bx, by, bw, bh in self.boxes.values():
            inside.update((x, y) for x in range(bx, bx + bw) for y in range(by, by + bh))
        for y in range(self.height):
            for x in range(self.width):
                chance = TREE_CHANCE * (2 if (x, y) in inside else 1)
                if self.kind(x, y) == "grass" and hash2(x, y, 11) % chance == 0:
                    self.trees.add((x, y))
        self.bushes = {t for t in self.trees if t in inside}

    def kind(self, x, y):
        return self.ground.get((x, y), "grass")

    def walkable(self, x, y):
        return self.kind(x, y) in WALKABLE

    def thing_at(self, x, y):
        """What the cursor is on: a Building, Warehouse, plot, vacant lot, or None."""
        if (x, y) in self.at:
            return self.at[(x, y)]
        for module, (px, py, size) in self.plots.items():
            if px <= x < px + size and py <= y < py + size:
                return ("plot", module)
        for vx, vy, size in self.vacant:
            if vx <= x < vx + size and vy <= y < vy + size:
                return ("vacant", None)
        return None

    def centre(self, module):
        if module in self.buildings:
            b = self.buildings[module]
            return b.x + b.size // 2, b.y + b.size // 2
        if module in self.plots:
            x, y, size = self.plots[module]
            return x + size // 2, y + size // 2
        return None
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python3 -m unittest test_townmap`
Expected: 13 tests, all `ok`.

- [ ] **Step 5: Run the whole suite**

Run: `python3 -m unittest`
Expected: 153 tests pass.

- [ ] **Step 6: Commit**

```bash
git add townmap.py test_townmap.py
git commit -m "Turn the plat into a tile map of the town"
```


---

### Task 4: Roads

An import is a road from the importer's front tile to the imported building's front tile, routed by breadth-first search over street, avenue and quay tiles.

- **Highways:** all imports between two districts make one highway, between the avenue tiles in front of the two districts' middles. Highways keep to avenues and the quay.
- **Problem roads:** cycle roads (both ends in one import cycle) and backwards roads are always drawn. The return leg of a two-way loop avoids the outbound leg's tiles, so it reads as a loop.
- **Other roads** are drawn only for the selected building (in and out, plus roads to its warehouses) or the selected warehouse (from each user).
- **Width** grows with the number of references. Non-highway roads end with a stub into the door.
- **Roundabouts:** each cycle road gets one, on its least hidden tile, nearest the road's middle. A ground tile is hidden by buildings on the tiles in front of it, to its right and front-right.

**Files:**
- Create: `roads.py`
- Test: `test_roads.py`

**Interfaces:**
- Consumes: `layers.cycles(model) -> list[list[str]]` (each import cycle's modules), `problems.BACKWARDS` with `Problem.other` (the module imported), `TownMap.kind`, `.buildings`, `.warehouses`, `.boxes`, `.bands`, `.at`, `Building.front()`, `Warehouse.front()`, `Warehouse.users`, `test_townmap.build`
- Produces:
  - road kinds `ROAD`, `HIGHWAY`, `CYCLE`, `BACKWARDS`, and `ORDER` (painting order, quietest first)
  - `Road(kind, src, dst, path, weight)` (frozen; `path` is a tuple of tiles)
  - `route(tmap, start, goal, ground=None, avoid=frozenset()) -> tuple | None` and `half_width(kind, weight) -> float` (in tiles)
  - `Roads(tmap, model, found)`:
    - attributes: `.always` (highways, then problem roads), `.cycle_edges`, `.backwards`;
    - methods: `.anchor(district)`, `.kind_of(src, dst)`, `.of(thing)`, `.visible(selected=None)` (always-drawn roads plus the selection's, without duplicates).
  - `segments(visible) -> dict[tile, list[(kind, weight, frozenset[direction])]]`, with `INTO_DOOR = (0, -1)` at road ends
  - `hidden(tmap, tile) -> int` (0 to 3) and `roundabouts(tmap, visible) -> set[tile]`

- [ ] **Step 1: Write the failing test**

Create `test_roads.py`:

```python
import unittest

import roads as R
from roads import Roads, half_width, hidden, roundabouts, route, segments
from test_townmap import build


def keys(found):
    return {(r.kind, r.src, r.dst) for r in found}


class RoadsTest(unittest.TestCase):
    def setUp(self):
        self.model, self.rows, self.found, self.town = build()
        self.roads = Roads(self.town, self.model, self.found)

    def test_routes_walk_the_streets_one_tile_at_a_time(self):
        a = self.town.buildings["app/main.py"].front()
        b = self.town.warehouses["yaml"].front()
        path = route(self.town, a, b)
        self.assertEqual((path[0], path[-1]), (a, b))
        self.assertTrue(all(self.town.walkable(*t) for t in path))
        steps = zip(path, path[1:])
        self.assertTrue(all(abs(p[0] - q[0]) + abs(p[1] - q[1]) == 1 for p, q in steps))

    def test_no_route_when_nothing_connects(self):
        corner = (0, self.town.height - 1)
        self.assertIsNone(route(self.town, corner, self.town.buildings["app/main.py"].front()))

    def test_highways_join_districts_along_avenues(self):
        highways = {(r.src, r.dst): r for r in self.roads.always if r.kind == R.HIGHWAY}
        self.assertEqual(sorted(highways), [("app", "core"), ("core", "app")])
        self.assertEqual(highways[("app", "core")].weight, 7)
        for road in highways.values():
            self.assertTrue(all(self.town.kind(*t) in R.HIGHWAY_GROUND for t in road.path))

    def test_problem_roads_always_show_and_plain_roads_wait_for_selection(self):
        always = keys(self.roads.visible())
        self.assertIn((R.CYCLE, "core/loop_a.py", "core/loop_b.py"), always)
        self.assertIn((R.BACKWARDS, "core/notes.py", "app/helper.py"), always)
        self.assertFalse(any(kind == R.ROAD for kind, _, _ in always))
        mine = keys(self.roads.visible(self.town.buildings["app/main.py"]))
        self.assertIn((R.ROAD, "app/main.py", "core/base.py"), mine)
        self.assertIn((R.ROAD, "app/main.py", "flask"), mine)

    def test_a_warehouse_shows_the_roads_of_its_users(self):
        self.assertEqual(keys(self.roads.of(self.town.warehouses["yaml"])),
                         {(R.ROAD, "core/base.py", "yaml")})

    def test_the_two_legs_of_a_loop_take_different_streets(self):
        legs = {(r.src, r.dst): r.path for r in self.roads.always if r.kind == R.CYCLE}
        there = legs[("core/loop_a.py", "core/loop_b.py")]
        back = legs[("core/loop_b.py", "core/loop_a.py")]
        self.assertFalse(set(there[1:-1]) & set(back[1:-1]))

    def test_roads_reach_into_doors_but_highways_end_on_the_avenue(self):
        segs = segments(self.roads.visible())
        loop = next(r for r in self.roads.always if r.kind == R.CYCLE)
        self.assertIn(R.INTO_DOOR, next(d for k, _, d in segs[loop.path[0]] if k == R.CYCLE))
        highway = next(r for r in self.roads.always if r.kind == R.HIGHWAY)
        self.assertEqual(len(next(d for k, _, d in segs[highway.path[0]] if k == R.HIGHWAY)), 1)

    def test_each_cycle_road_gets_a_roundabout_on_its_least_hidden_tile(self):
        spots = roundabouts(self.town, self.roads.always)
        for road in (r for r in self.roads.always if r.kind == R.CYCLE):
            on_road = [t for t in road.path if t in spots]
            self.assertTrue(on_road, road)
            least = min(hidden(self.town, t) for t in road.path)
            self.assertTrue(any(hidden(self.town, t) == least for t in on_road))
            self.assertLess(least, 3)

    def test_more_references_make_wider_roads(self):
        self.assertLess(half_width(R.ROAD, 1), half_width(R.ROAD, 3))
        self.assertLess(half_width(R.HIGHWAY, 1), half_width(R.HIGHWAY, 16))
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python3 -m unittest test_roads`
Expected: `ModuleNotFoundError: No module named 'roads'`.

- [ ] **Step 3: Write the roads**

Create `roads.py`:

```python
"""Roads: imports routed along the streets, and which of them are drawn.

Highways (all imports between two districts) and problem roads are always
drawn; ordinary roads only for the selected building or warehouse.
"""

import math
from collections import deque
from dataclasses import dataclass

import layers
import problems
from townmap import Building, Warehouse

ROAD = "road"
HIGHWAY = "highway"
CYCLE = "cycle"
BACKWARDS = "backwards"
ORDER = [ROAD, HIGHWAY, BACKWARDS, CYCLE]
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
    base = {ROAD: 0.12, HIGHWAY: 0.16, BACKWARDS: 0.17, CYCLE: 0.17}[kind]
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
        self.always = self._highways() + self._problem_roads()

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

    def _module_road(self, src, dst, avoid=frozenset()):
        b = self.tmap.buildings
        if src not in b or dst not in b:
            return []
        n = self.model.edges[(src, dst)]
        return self._road(self.kind_of(src, dst), src, dst, b[src].front(), b[dst].front(), n,
                          avoid=avoid)

    def _problem_roads(self):
        """Cycle and backwards roads. The return leg of a two-way loop goes round the other way."""
        found = {}
        for src, dst in sorted(self.cycle_edges | self.backwards):
            back = found.get((dst, src))
            avoid = frozenset(back.path[1:-1]) if back else frozenset()
            for road in self._module_road(src, dst, avoid):
                found[(src, dst)] = road
        return list(found.values())

    def of(self, thing):
        """Every road into or out of the selected building or warehouse."""
        found = []
        if isinstance(thing, Building):
            for src, dst in sorted(self.model.edges):
                if thing.module in (src, dst):
                    found += self._module_road(src, dst)
            for package, users in sorted(self.model.externals.items()):
                w = self.tmap.warehouses.get(package)
                if w and thing.module in users:
                    found += self._road(ROAD, thing.module, package, thing.front(), w.front(), 1)
        elif isinstance(thing, Warehouse):
            for user in thing.users:
                b = self.tmap.buildings.get(user)
                if b:
                    found += self._road(ROAD, user, thing.package, b.front(), thing.front(), 1)
        return found

    def visible(self, selected=None):
        seen, found = set(), []
        for road in self.always + self.of(selected):
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
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python3 -m unittest test_roads`
Expected: 9 tests, all `ok`.

- [ ] **Step 5: Run the whole suite**

Run: `python3 -m unittest`
Expected: 162 tests pass.

- [ ] **Step 6: Commit**

```bash
git add roads.py test_roads.py
git commit -m "Route imports along the streets and pick which roads to draw"
```


---

### Task 5: Drawing the town

`TownScene` paints a `TownMap` with the game's projection: 12×6-pixel diamonds and `render.LOCAL`, each pixel's position inside its tile. It draws in two passes:

1. Ground for every tile, including roads, roundabouts, wear, cracks, shadows and the island's skirt.
2. Buildings, warehouses, trees, props and annexes, sorted back to front by `(x + y, layer, x)`.

Buildings are flat-roofed boxes built with the game's wall-column technique:

- a 7-pixel ground floor, 4 pixels per upper floor, and a 1-pixel parapet;
- the district's roof colour.

How each problem shows:

| Problem | Drawn as |
| --- | --- |
| Won't parse | Flames on the roof, and smoke rising about 56 pixels above it |
| Import cycle | Red road with a roundabout (Task 4) |
| Backwards road | Orange road, and a red no-entry sign in front of the importer |
| Hotspot | Cracked, shimmering paving around the building |
| Tower | 9 floors, and a shadow over the 3 tiles to its right |
| Abandoned | Boarded windows and weeds; no road in, because nothing imports it |
| Untested | Dark windows and no annex (tested buildings get lit windows and an annex) |
| All doors | Doors across both faces, on every floor |
| Notes left | A small yellow sign in front of the door |
| Unsurveyed | A dashed gray outline around a grayed plot |

The selected building's roof rim turns white. With nothing selected, the cursor tile gets a white outline on the ground.

Tall buildings hide what stands behind them; the showcase's tower hides the whole import loop. The game already dithers Clawd's silhouette through whatever stands in front of him. The town does the same for loud things: cycle and backwards roads, roundabouts, the selected building's rim and the cursor outline. It records their pixels in `ghost`, and after everything is drawn, every other covered pixel gets its colour back.

**Files:**
- Create: `drawtown.py`
- Test: `test_drawtown.py`

**Interfaces:**
- Consumes:
  - from `iso`: `to_screen`, `TILE_MASK`, `COLUMN_BOTTOM`, `HALF_W`, `HALF_H`;
  - from `render`: `LOCAL`, `ground_color`, `shade`, `mix`, `hash2`, `DIRT`, `DOOR`, `KNOB`, `SKIRT`, `SKIRT_DEPTH`, `SKIRT_LIP`, `Framebuffer`;
  - from `sprites`: `tree(kind, seed)`;
  - from `roads`: `segments`, `roundabouts`, `half_width`;
  - from `townmap`: `TownMap`, `Building`, `Warehouse`.
- Produces:
  - colours `SEA`, `SELECT`, `OUTLINE`, `FLAMES`, and `ROAD_COLORS` (road kind to RGB)
  - `height_px(building) -> int`
  - `TownScene(tmap, w, h, ox, oy, t=0.0, selected=None, visible=(), cursor=None)`, where `visible` is the roads to draw and `t` is seconds, for animation
  - `TownScene.around(tmap, w, h, tile, lift=0, **kw)` (centred on a tile, raised by `lift` pixels) and `TownScene.whole(tmap, **kw)` (the whole island, with room above for smoke)
  - `.render() -> Framebuffer`, `.centre_px(building) -> (x, y)`, and `.ghost` (screen pixel to colour, for everything that shows through)
  - `shrink(fb, factor) -> Framebuffer` (each pixel the average of a `factor` × `factor` block)

- [ ] **Step 1: Write the failing test**

Create `test_drawtown.py`:

```python
import unittest

import problems
import roads as R
from drawtown import FLAMES, OUTLINE, ROAD_COLORS, SEA, SELECT, TownScene, shrink
from plat import Plat
from render import Framebuffer
from roads import Roads
from test_townmap import build
from townmap import TownMap


def colours(fb):
    return {c for row in fb.rows for c in row}


class DrawTownTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.model, cls.rows, cls.found, cls.town = build()
        cls.roads = Roads(cls.town, cls.model, cls.found)
        cls.plain = TownScene.whole(cls.town, visible=cls.roads.visible()).render()

    def test_the_whole_town_fits_inside_its_frame(self):
        fb = self.plain
        drawn = [y for y in range(fb.h) if any(c != SEA for c in fb.rows[y])]
        self.assertGreater(drawn[0], 0)
        self.assertLess(drawn[-1], fb.h - 1)
        self.assertTrue(all(fb.rows[y][0] == SEA and fb.rows[y][-1] == SEA for y in range(fb.h)))

    def test_fire_burns_only_where_a_module_will_not_parse(self):
        self.assertTrue({FLAMES[0], FLAMES[1]} <= colours(self.plain))
        self.model.modules["core/broken.py"].parse_error = None
        try:
            found = problems.find(self.model, self.rows)
            calm = TownMap(self.model, Plat().update(self.model, self.rows), self.rows, found)
            fb = TownScene.whole(calm).render()
        finally:
            self.model.modules["core/broken.py"].parse_error = "line 3: invalid syntax"
        self.assertFalse({FLAMES[0], FLAMES[1]} & colours(fb))

    def test_unsurveyed_plots_get_a_gray_outline(self):
        self.assertIn(OUTLINE, colours(self.plain))

    def test_problem_roads_always_show_and_plain_roads_wait_for_selection(self):
        self.assertIn(ROAD_COLORS[R.CYCLE], colours(self.plain))
        self.assertIn(ROAD_COLORS[R.BACKWARDS], colours(self.plain))
        self.assertNotIn(ROAD_COLORS[R.ROAD], colours(self.plain))
        self.assertNotIn(SELECT, colours(self.plain))
        b = self.town.buildings["app/main.py"]
        chosen = TownScene.whole(self.town, selected=b, visible=self.roads.visible(b)).render()
        self.assertIn(ROAD_COLORS[R.ROAD], colours(chosen))
        self.assertIn(SELECT, colours(chosen))

    def test_loud_roads_and_the_selection_show_through_the_tower_in_front(self):
        loop_a = self.town.buildings["core/loop_a.py"]
        scene = TownScene.whole(self.town, selected=loop_a, visible=self.roads.visible(loop_a))
        fb = scene.render()
        ghost = scene.ghost.items()
        covered = {c for (x, y), c in ghost if (x + y) % 2 and fb.get(x, y) != c}
        self.assertTrue({SELECT, ROAD_COLORS[R.CYCLE]} <= covered)
        self.assertTrue(all(fb.get(x, y) == c for (x, y), c in ghost if (x + y) % 2 == 0))

    def test_drawing_is_deterministic(self):
        again = TownScene.whole(self.town, visible=self.roads.visible()).render()
        self.assertEqual(again.rows, self.plain.rows)

    def test_a_street_view_is_the_size_asked_for(self):
        fb = TownScene.around(self.town, 50, 30, self.town.centre("core/base.py")).render()
        self.assertEqual((fb.w, fb.h, len(fb.rows), len(fb.rows[0])), (50, 30, 30, 50))

    def test_shrink_averages_each_block(self):
        fb = Framebuffer(4, 2, (0, 0, 0))
        fb.rows[0][0] = (40, 80, 120)
        small = shrink(fb, 2)
        self.assertEqual((small.w, small.h), (2, 1))
        self.assertEqual(small.rows[0], [(10, 20, 30), (0, 0, 0)])
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python3 -m unittest test_drawtown`
Expected: `ModuleNotFoundError: No module named 'drawtown'`.

- [ ] **Step 3: Write the renderer**

Create `drawtown.py`:

```python
"""Draws a TownMap into a framebuffer, back to front."""

import math
from functools import partial

import iso
import problems
import roads as R
import sprites
from render import (DIRT, DOOR, KNOB, LOCAL, SKIRT, SKIRT_DEPTH, SKIRT_LIP, Framebuffer,
                    ground_color, hash2, mix, shade)
from townmap import Warehouse

SEA = (30, 66, 112)
GROUND_FLOOR = 7
FLOOR = 4
PARAPET = 1
WAREHOUSE_H = 9
ANNEX_H = 5
TOP_ROOM = 96
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
               R.BACKWARDS: (232, 112, 36)}
LOUD_ROADS = (R.CYCLE, R.BACKWARDS)


def height_px(b):
    return GROUND_FLOOR + FLOOR * (b.floors - 1) + PARAPET


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
    def __init__(self, tmap, w, h, ox, oy, t=0.0, selected=None, visible=(), cursor=None):
        self.m = tmap
        self.t = t
        self.fb = Framebuffer(w, h, SEA)
        self.ox, self.oy = ox, oy
        self.selected = selected
        self.segments = R.segments(visible)
        self.roundabouts = R.roundabouts(tmap, visible)
        self.cursor = cursor
        self.ghost = {}
        self.roofs = {name: ROOFS[i % len(ROOFS)] for i, name in enumerate(sorted(tmap.boxes))}
        self.plot_of = {}
        for module, (x, y, size) in tmap.plots.items():
            for i in range(size):
                for j in range(size):
                    self.plot_of[(x + i, y + j)] = (x, y, size)

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
        return -16 < sx < self.fb.w + 16 and -8 < sy < self.fb.h + TOP_ROOM

    def render(self):
        m = self.m
        drawables = []
        for ty in range(m.height):
            for tx in range(m.width):
                sx, sy = self.screen(tx, ty)
                if not self.visible(sx, sy):
                    continue
                self.draw_ground(tx, ty, sx, sy)
                thing = m.at.get((tx, ty))
                if thing is not None:
                    draw = partial(self.draw_block, thing, tx, ty, sx, sy)
                    drawables.append((tx + ty, 0, tx, draw))
                elif (tx, ty) in m.trees:
                    drawables.append((tx + ty, 0, tx, partial(self.draw_tree, tx, ty, sx, sy)))
                for prop in m.props.get((tx, ty), ()):
                    drawables.append((tx + ty, 1, tx, partial(self.draw_prop, prop, sx, sy)))
        for b in m.buildings.values():
            if b.tested:
                tx, ty = b.x + b.size, b.y
                sx, sy = self.screen(tx, ty)
                if self.visible(sx, sy):
                    drawables.append((tx + ty, 1, tx, partial(self.draw_annex, sx, sy)))
        drawables.sort(key=lambda d: d[:3])
        for *_, draw in drawables:
            draw()
        self.draw_ghost()
        return self.fb

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

    def draw_block(self, thing, tx, ty, sx, sy):
        if isinstance(thing, Warehouse):
            self.draw_box(thing, tx, ty, sx, sy, WAREHOUSE_H, WAREHOUSE_WALL, WAREHOUSE_ROOF,
                          self.warehouse_wall)
            return
        wall = WALLS[hash2(thing.x, thing.y) & 3]
        self.draw_box(thing, tx, ty, sx, sy, height_px(thing), wall,
                      self.roofs.get(thing.district, ROOFS[-1]), self.facade)
        if problems.FIRE in thing.problems and (tx, ty) == (thing.x + thing.size - 1,
                                                            thing.y + thing.size - 1):
            self.draw_fire(thing)

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

    def door_tiles(self, b):
        door_x = b.door()[0]
        order = sorted(range(b.x, b.x + b.size), key=lambda x: (abs(x - door_x), x))
        return set(order[:b.doors])

    def facade(self, b, face, tx, ty, u, k, height, c):
        kinds = b.problems
        if k >= height - PARAPET:
            return shade(c, 0.86)
        if k < GROUND_FLOOR:
            floor, row = 0, k
        else:
            floor, row = 1 + (k - GROUND_FLOOR) // FLOOR, (k - GROUND_FLOOR) % FLOOR
        if problems.ALL_DOORS in kinds:
            if (floor == 0 and u in (0, 1, 3, 4) and 1 <= row <= 5) or \
                    (floor > 0 and 1 <= u <= 3 and row <= 2):
                return KNOB if (floor == 0 and u in (1, 4) and row == 3) else DOOR
            return c
        if face == "y" and floor == 0 and tx in self.door_tiles(b):
            if 1 <= u <= 3 and 1 <= row <= 5:
                return KNOB if (u == 3 and row == 3) else DOOR
            return c
        if 1 <= u <= 3 and row in ((3, 4) if floor == 0 else (1, 2)):
            if problems.ABANDONED in kinds:
                return BOARD if (u + row) % 2 else shade(BOARD, 0.75)
            glass = LIT if b.tested else DARK
            return shade(glass, 0.75) if u == 2 else glass
        if problems.ABANDONED in kinds and k <= 1 and hash2(tx, ty, u, k, face == "y") % 3 == 0:
            return WEED
        return c

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

    def draw_annex(self, sx, sy):
        pixels = [(dx, dy) for dx, dy in iso.TILE_MASK
                  if LOCAL[(dx, dy)][0] < 0.45 and LOCAL[(dx, dy)][1] < 0.5]
        bottoms = {}
        for dx, dy in pixels:
            bottoms[dx] = max(bottoms.get(dx, dy), dy)
        for dx, bottom in bottoms.items():
            wx, wy = LOCAL[(dx, bottom)]
            c = shade(ANNEX_WALL, 0.96 if 0.5 - wy < 0.45 - wx else 0.74)
            for k in range(ANNEX_H):
                self.fb.set(sx + dx, sy + bottom - k, shade(c, 0.7) if k == 0 else c)
        for dx, dy in pixels:
            self.fb.set(sx + dx, sy + dy - ANNEX_H, ANNEX_ROOF)

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
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python3 -m unittest test_drawtown`
Expected: 8 tests, all `ok`.

- [ ] **Step 5: Look at the showcase**

Run:

```bash
python3 -c "import snapshot, test_townmap as t; from roads import Roads; from drawtown import TownScene; m, r, f, town = t.build(); snapshot.write_png('/tmp/showcase.png', TownScene.whole(town, visible=Roads(town, m, f).visible()).render(), 3)"
```

Open `/tmp/showcase.png` and check that you can see each of these:

- **Water and harbor:** two warehouses on the dock in the water at the back.
- **Districts and roads:** `core` behind `app`, and a dark highway between them. The `web` plot has a dashed gray outline.
- **Problems in `core`:**
  - smoke and flames over `core/broken.py`;
  - a red loop with a roundabout between `core/loop_a.py` and `core/loop_b.py`, dithered through the tower that stands in front of it;
  - a tall tower with a shadow to its right;
  - doors across the front of `core/doors.py`;
  - a yellow sign in front of `core/notes.py`;
  - an orange road from `core/notes.py` forward to `app/helper.py`, with a red no-entry sign at its start.
- **In `app`:** a stone gate in front of `app/main.py`, dark windows on all three `app` buildings, and boards and weeds on `app/lonely.py`.

If something is missing or unreadable, fix it test first before moving on.

- [ ] **Step 6: Run the whole suite**

Run: `python3 -m unittest`
Expected: 170 tests pass.

- [ ] **Step 7: Commit**

```bash
git add drawtown.py test_drawtown.py
git commit -m "Draw the town: buildings, roads and every problem"
```


---

### Task 6: The viewer

The viewer has three zoom levels:

- **Street:** drawn live around the cursor at 1:1, raised by half the selected building's height so tall buildings stay in frame.
- **District and town:** cut from one drawing of the whole town and shrunk by averaging (by 2 for district, and enough to fit for town). The whole-town drawing is redone only when the selection changes, and the shrunk crop only when the view moves.

How the viewer behaves:

- **Moving:** WASD or the arrow keys move the cursor one tile at street level, two at district and four at town.
- **Starting point:** the viewer starts on the worst problem. `n` and `p` walk the problems worst first and wrap; moving the cursor leaves problem mode.
- **Inspector:** Enter or space toggles it. The second status line becomes the facts, and the third every problem's reason.
- **Fires:** at street level, an off-screen fire gets a flame marker at the screen edge. At district and town zoom, every fire gets a marker, since smoke is too small to see there.

**Files:**
- Create: `viewer.py`
- Modify: `term.py`
- Test: `test_viewer.py`

**Interfaces:**
- Consumes:
  - from `term`: `Screen(truecolor)` (`.frame(fb, status)`, `.invalidate()`), `Terminal()` (a context manager with `.size()`, `.read(timeout)`, `.write(s)`), `parse_keys`;
  - `Model.importers()`;
  - from `drawtown`: `TownScene`, `height_px`, `shrink`, `SEA`, `SELECT`, `FLAMES`;
  - `Roads.visible`;
  - from `TownMap`: `thing_at`, `centre`, `kind`, `problems`.
- Produces:
  - `term.parse_keys(data, keymap=KEYMAP)` (the game passes nothing and is unchanged)
  - `viewer.STREET`, `DISTRICT`, `TOWN`, `ZOOMS`, `KEYMAP`, `HINT`
  - `Viewer(tmap, roads, model, found)`:
    - state: `.cursor`, `.zoom`, `.inspecting`, `.problem` (an index into `found`, or `None`), `.t`;
    - methods: `.press(key)`, `.selected()`, `.frame(w, h) -> Framebuffer`, `.status(cols) -> list[str]` (3 lines), `.describe(thing) -> (title, facts, reasons)`.
  - `viewer.parse_keys(data) -> list[str]` and `viewer.run(viewer, truecolor)` (the terminal loop; returns on `q`)

- [ ] **Step 1: Write the failing test**

Create `test_viewer.py`:

```python
import unittest

import problems
from drawtown import FLAMES
from roads import Roads
from test_townmap import build
from viewer import DISTRICT, STREET, TOWN, Viewer, parse_keys


class ViewerTest(unittest.TestCase):
    def setUp(self):
        self.model, self.rows, self.found, self.town = build()
        self.v = Viewer(self.town, Roads(self.town, self.model, self.found), self.model, self.found)

    def press(self, data):
        for key in parse_keys(data):
            self.v.press(key)

    def test_keys(self):
        self.assertEqual(parse_keys("+-=_n p\r\x1b[Bq"),
                         ["zoom in", "zoom out", "zoom in", "zoom out", "next", "inspect",
                          "previous", "inspect", "down", "quit"])

    def test_starts_on_the_worst_problem(self):
        self.assertEqual(self.found[0].kind, problems.FIRE)
        self.assertEqual(self.v.selected().module, self.found[0].module)

    def test_keys_move_the_cursor_and_stop_at_the_edge(self):
        x, y = self.v.cursor
        self.press("d")
        self.assertEqual(self.v.cursor, (x + 1, y))
        self.press("\x1b[A")
        self.assertEqual(self.v.cursor, (x + 1, y - 1))
        self.press("w" * 200)
        self.assertEqual(self.v.cursor, (x + 1, 0))

    def test_zoom_steps_between_street_district_and_town(self):
        self.press("+")
        self.assertEqual(self.v.zoom, STREET)
        self.press("-")
        self.assertEqual(self.v.zoom, DISTRICT)
        self.press("--")
        self.assertEqual(self.v.zoom, TOWN)
        self.press("=")
        self.assertEqual(self.v.zoom, DISTRICT)

    def test_every_zoom_level_fills_the_frame(self):
        for zoom in (STREET, DISTRICT, TOWN):
            self.v.zoom = zoom
            fb = self.v.frame(60, 30)
            self.assertEqual((fb.w, fb.h, len(fb.rows), len(fb.rows[0])), (60, 30, 30, 60), zoom)

    def test_n_and_p_walk_the_problems_worst_first_and_wrap(self):
        self.press("n")
        self.assertEqual(self.v.problem, 0)
        self.press("n")
        self.assertEqual(self.v.problem, 1)
        self.press("pp")
        last = len(self.found) - 1
        self.assertEqual(self.v.problem, last)
        self.assertEqual(self.v.cursor, self.town.centre(self.found[last].module))
        self.assertIn(f"problem {last + 1} of {last + 1}", self.v.status(200)[0])

    def test_moving_away_clears_the_problem_count(self):
        self.press("nd")
        self.assertIsNone(self.v.problem)

    def test_the_inspector_shows_the_facts_behind_a_building(self):
        self.v.cursor = self.town.centre("core/tower.py")
        self.press("\r")
        title, facts, reasons = self.v.status(300)
        self.assertIn("core/tower.py", title)
        for fact in ("2400 lines", "complexity 260", "9 floors", "imported by 1", "1 test"):
            self.assertIn(fact, facts)
        self.assertIn("tower: 2400 lines, complexity 260", reasons)

    def test_the_hint_shows_while_the_inspector_is_closed(self):
        hint = self.v.status(300)[2]
        self.assertIn("q quit", hint)
        self.assertIn("[street]", hint)

    def test_warehouses_plots_and_streets_describe_themselves(self):
        w = self.town.warehouses["flask"]
        self.v.cursor = (w.x, w.y)
        self.assertIn("warehouse: flask", self.v.status(200)[0])
        x, y, _ = self.town.plots["web/ui.js"]
        self.v.cursor = (x, y)
        self.assertIn("unsurveyed", self.v.status(200)[0])
        self.v.cursor = self.town.buildings["core/base.py"].front()
        self.assertIn("street", self.v.status(200)[0])

    def test_an_off_screen_fire_gets_an_arrow_at_the_edge(self):
        self.v.cursor = (0, self.town.height - 1)
        fb = self.v.frame(40, 24)
        edge = {fb.rows[y][x] for y in range(fb.h) for x in range(fb.w)
                if min(x, y, fb.w - 1 - x, fb.h - 1 - y) <= 4}
        self.assertTrue(set(FLAMES[:2]) & edge)

    def test_fire_can_be_seen_from_the_whole_town_view(self):
        self.v.zoom = TOWN
        fb = self.v.frame(60, 30)
        self.assertTrue(any(c in FLAMES for row in fb.rows for c in row))
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python3 -m unittest test_viewer`
Expected: `ModuleNotFoundError: No module named 'viewer'`.

- [ ] **Step 3: Let the key parser take a keymap**

In `term.py`, replace:

```python
def parse_keys(data):
```

with:

```python
def parse_keys(data, keymap=KEYMAP):
```

In `term.py`, replace:

```python
        key = KEYMAP.get(ch.lower())
```

with:

```python
        key = keymap.get(ch.lower())
```

- [ ] **Step 4: Write the viewer**

Create `viewer.py`:

```python
"""The interactive town: a cursor, three zoom levels, the inspector, and n/p through problems.

Street level is drawn live around the cursor. District and town levels are cut
from one drawing of the whole town, shrunk; that drawing is redone only when the
selection changes.
"""

import math
import signal
import time

import iso
import problems
import term
from drawtown import FLAMES, SEA, SELECT, TownScene, height_px, shrink
from render import Framebuffer
from townmap import Building, Warehouse

STREET, DISTRICT, TOWN = "street", "district", "town"
ZOOMS = [STREET, DISTRICT, TOWN]
DISTRICT_FACTOR = 2
STEPS = {STREET: 1, DISTRICT: 2, TOWN: 4}
MOVES = {"up": (0, -1), "right": (1, 0), "down": (0, 1), "left": (-1, 0)}
KEYMAP = {"w": "up", "a": "left", "s": "down", "d": "right",
          "+": "zoom in", "=": "zoom in", "-": "zoom out", "_": "zoom out",
          "\r": "inspect", "\n": "inspect", " ": "inspect",
          "n": "next", "p": "previous", "q": "quit", "\x03": "quit"}
HINT = "WASD/arrows move   +/- zoom   Enter inspect   n/p next/previous problem   q quit"
FPS = 12
STATUS_LINES = 3
MIN_COLS, MIN_LINES = 40, 16
STYLES = ["\x1b[1;38;5;230m", "\x1b[38;5;250m", "\x1b[38;5;245m"]


def _n(count, word):
    return f"{count} {word}" if count == 1 else f"{count} {word}s"


class Viewer:
    def __init__(self, tmap, roads, model, found):
        self.m, self.roads, self.model, self.found = tmap, roads, model, found
        self.importers = model.importers()
        self.zoom = STREET
        self.inspecting = False
        self.problem = None
        self.t = 0.0
        self._whole = None
        self._whole_key = None
        self._shrunk = None
        start = next((tmap.centre(p.module) for p in found if tmap.centre(p.module)), None)
        self.cursor = start or (tmap.width // 2, tmap.height // 2)

    # --- input ------------------------------------------------------------

    def press(self, key):
        if key in MOVES:
            dx, dy = MOVES[key]
            step = STEPS[self.zoom]
            x = min(max(self.cursor[0] + dx * step, 0), self.m.width - 1)
            y = min(max(self.cursor[1] + dy * step, 0), self.m.height - 1)
            self.cursor = (x, y)
            self.problem = None
        elif key == "zoom in":
            self.zoom = ZOOMS[max(0, ZOOMS.index(self.zoom) - 1)]
        elif key == "zoom out":
            self.zoom = ZOOMS[min(len(ZOOMS) - 1, ZOOMS.index(self.zoom) + 1)]
        elif key == "inspect":
            self.inspecting = not self.inspecting
        elif key in ("next", "previous") and self.found:
            step = 1 if key == "next" else -1
            if self.problem is None:
                self.problem = 0 if step == 1 else len(self.found) - 1
            else:
                self.problem = (self.problem + step) % len(self.found)
            self.cursor = self.m.centre(self.found[self.problem].module) or self.cursor

    def selected(self):
        return self.m.thing_at(*self.cursor)

    # --- drawing ----------------------------------------------------------

    def frame(self, w, h):
        thing = self.selected()
        chosen = thing if isinstance(thing, (Building, Warehouse)) else None
        if self.zoom == STREET:
            lift = height_px(chosen) // 2 if isinstance(chosen, Building) else 0
            scene = TownScene.around(self.m, w, h, self.cursor, lift=lift, t=self.t,
                                     selected=chosen, visible=self.roads.visible(chosen),
                                     cursor=None if chosen else self.cursor)
            fb = scene.render()
            self._mark_fires(fb, lambda b: scene.centre_px(b), inside=False)
            return fb
        whole = self._whole_town(chosen)
        factor = DISTRICT_FACTOR if self.zoom == DISTRICT else self.town_factor(w, h)
        if self.zoom == TOWN:
            cx, cy = whole.fb.w // 2, whole.fb.h // 2
        else:
            cx, cy = self._point(whole, self.cursor[0] + 0.5, self.cursor[1] + 0.5)
        left, top = cx - w * factor // 2, cy - h * factor // 2

        def where(x, y):
            px, py = self._point(whole, x, y)
            return (px - left) // factor, (py - top) // factor

        key = (self._whole_key, left, top, w, h, factor)
        if self._shrunk is None or self._shrunk[0] != key:
            self._shrunk = (key, shrink(_crop(whole.fb, left, top, w * factor, h * factor), factor))
        fb = Framebuffer(w, h)
        fb.rows = [list(row) for row in self._shrunk[1].rows]
        _cross(fb, *where(self.cursor[0] + 0.5, self.cursor[1] + 0.5), self.t)
        self._mark_fires(fb, lambda b: where(b.x + b.size / 2, b.y + b.size / 2), inside=True)
        return fb

    def town_factor(self, w, h):
        whole = self._whole_town(None) if self._whole is None else self._whole
        return max(DISTRICT_FACTOR + 1, math.ceil(whole.fb.w / w), math.ceil(whole.fb.h / h))

    def _whole_town(self, chosen):
        key = chosen.module if isinstance(chosen, Building) else \
            (chosen.package if chosen else None)
        if self._whole is None or self._whole_key != key:
            scene = TownScene.whole(self.m, selected=chosen, visible=self.roads.visible(chosen))
            scene.render()
            self._whole, self._whole_key = scene, key
        return self._whole

    @staticmethod
    def _point(scene, x, y):
        sx, sy = iso.to_screen(x, y)
        return round(sx) + scene.ox, round(sy) + scene.oy

    def _mark_fires(self, fb, where, inside):
        frame = int(self.t * 6) % 2
        for b in self.m.buildings.values():
            if problems.FIRE not in b.problems:
                continue
            x, y = where(b)
            on_screen = 0 <= x < fb.w and 0 <= y < fb.h
            if on_screen and not inside:
                continue
            ex, ey = min(max(x, 2), fb.w - 3), min(max(y, 2), fb.h - 3)
            for i in range(-1, 2):
                for j in range(-1, 2):
                    fb.set(ex + i, ey + j, FLAMES[(i + j + frame) % 2])
            if not on_screen:
                ux, uy = (x > ex) - (x < ex), (y > ey) - (y < ey)
                fb.set(ex + 2 * ux, ey + 2 * uy, FLAMES[0])

    # --- words ------------------------------------------------------------

    def status(self, cols):
        thing = self.selected()
        title, facts, issues = self.describe(thing)
        if self.problem is not None:
            title = f"problem {self.problem + 1} of {len(self.found)} · {title}"
        lines = [title, facts if self.inspecting else "; ".join(issues[:2]),
                 "; ".join(issues) if self.inspecting else f"{HINT}   [{self.zoom}]"]
        width = max(10, cols - 2)
        return [f" {line[:width]}" for line in lines]

    def describe(self, thing):
        """A title, a line of facts, and the reasons behind each problem."""
        if isinstance(thing, Building):
            m = self.model.modules[thing.module]
            kinds = ", ".join(dict.fromkeys(p.kind for p in self.m.problems.get(m.id, ())))
            title = f"{m.id}  ({m.district})" + (f": {kinds}" if kinds else "")
            imports = sum(1 for src, _ in self.model.edges if src == m.id)
            facts = [_n(m.loc, "line"), f"complexity {m.complexity}", _n(thing.floors, "floor"),
                     _n(len(m.exports), "export"),
                     f"imported by {len(self.importers.get(m.id, ()))}",
                     f"imports {imports}", _n(len(m.tested_by), "test"),
                     f"{_n(m.churn, 'commit')} in 90 days"]
            if m.is_entry:
                facts.append("run directly")
            return title, ", ".join(facts), [f"{p.kind}: {p.reason}"
                                             for p in self.m.problems.get(m.id, ())]
        if isinstance(thing, Warehouse):
            return (f"warehouse: {thing.package}  (outside package)",
                    f"used by {_n(len(thing.users), 'module')}: {', '.join(thing.users)}", [])
        if thing and thing[0] == "plot":
            m = self.model.modules[thing[1]]
            reasons = [f"{p.kind}: {p.reason}" for p in self.m.problems.get(m.id, ())]
            return (f"{m.id}  ({m.district}): unsurveyed",
                    f"{_n(m.loc, 'line')}, {_n(m.churn, 'commit')} in 90 days", reasons)
        if thing and thing[0] == "vacant":
            return "vacant lot: a module that stood here was deleted", "", []
        kind = self.m.kind(*self.cursor)
        names = {"grass": "free land", "street": "street", "avenue": "avenue",
                 "quay": "quay", "water": "harbor", "dock": "dock"}
        return names.get(kind, kind), "", []


def _crop(fb, left, top, w, h):
    out = Framebuffer(w, h, SEA)
    for y in range(h):
        sy = top + y
        if 0 <= sy < fb.h:
            row = fb.rows[sy]
            x0, x1 = max(0, -left), min(w, fb.w - left)
            if x0 < x1:
                out.rows[y][x0:x1] = row[left + x0:left + x1]
    return out


def _cross(fb, x, y, t):
    if int(t * 4) % 2:
        return
    for d in (-2, -1, 1, 2):
        fb.set(x + d, y, SELECT)
        fb.set(x, y + d, SELECT)


def parse_keys(data):
    return term.parse_keys(data, KEYMAP)


def run(viewer, truecolor):
    """The terminal loop: read keys, draw a frame, repeat until q."""
    screen = term.Screen(truecolor)
    resized = [True]
    signal.signal(signal.SIGWINCH, lambda *_: resized.__setitem__(0, True))
    with term.Terminal() as t:
        t.write("\x1b]0;CodeTown\x07")
        start = time.monotonic()
        timeout = 0.0
        cols = lines = 0
        while True:
            if resized[0]:
                resized[0] = False
                cols, lines = t.size()
                screen.invalidate()
                t.write("\x1b[2J")
                if cols < MIN_COLS or lines < MIN_LINES:
                    msg = f"Make the window at least {MIN_COLS}x{MIN_LINES}"
                    t.write(f"\x1b[{max(1, lines // 2)};1H{msg[:cols]}")
            for key in parse_keys(t.read(timeout)):
                if key == "quit":
                    return
                viewer.press(key)
            now = time.monotonic()
            viewer.t = now - start
            if cols >= MIN_COLS and lines >= MIN_LINES:
                fb = viewer.frame(cols // 2, lines - STATUS_LINES)
                status = [style + line for style, line in zip(STYLES, viewer.status(cols))]
                t.write(screen.frame(fb, status))
            timeout = max(0.0, 1 / FPS - (time.monotonic() - now))
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python3 -m unittest test_viewer test_term`
Expected: 23 tests, all `ok` (the game's key tests unchanged).

- [ ] **Step 6: Run the whole suite**

Run: `python3 -m unittest`
Expected: 182 tests pass.

- [ ] **Step 7: Commit**

```bash
git add viewer.py term.py test_viewer.py
git commit -m "Add the town viewer: cursor, zoom, inspector and problem walking"
```


---

### Task 7: `towncode view` and `towncode snapshot`

The survey now saves `plat.json` too. A damaged `rows.json` or `plat.json` stops the run and is left as it is, with a message saying how to start over. `view` needs an interactive terminal. `snapshot` draws one frame to a PNG, which is how agents and tests look at the town; it refuses to write inside the surveyed repository.

The game's smoke test checked only once, right after the terminal closed, whether the game had exited. It failed once in about twenty full runs while this plan was being checked. `test_smoke.py` is rewritten so both smoke tests share one helper, `play`, which runs a program in a pseudo-terminal, presses its keys and then `q`, and waits up to 3 seconds for it to exit.

**Files:**
- Modify: `towncode.py` (whole file), `README.md`
- Test: `test_towncode.py`, `test_smoke.py`

**Interfaces:**
- Consumes: `Plat.load`, `Plat.update`, `Plat.save`, `TownMap`, `Roads`, `viewer.Viewer`, `viewer.run`, `viewer.ZOOMS`, `viewer.TOWN`, `snapshot.write_png(path, fb, scale)`, `term.supports_truecolor()`, `test_survey.MONOREPO_LIKE`
- Produces:
  - `towncode.run(repo_root) -> (model, rows, plat, out)`, which now also saves `plat.json`. It was a 3-tuple in Plan 1, and `towncode.py` is its only caller.
  - `towncode.town(model, rows, plat) -> Viewer`
  - `towncode view PATH [--256]`
  - `towncode snapshot PATH OUT.png [--zoom street|district|town] [--at MODULE] [--size WxH] [--scale N]`: it starts on the worst problem unless `--at` is given; the defaults are town zoom, `160x90` and scale 4

- [ ] **Step 1: Write the failing tests**

In `test_towncode.py`, replace:

```python
import shutil
import tempfile
```

with:

```python
import shutil
import struct
import tempfile
```

In `test_towncode.py`, replace:

```python
        saved = self.saved("model.json") + self.saved("rows.json")
```

with:

```python
        saved = self.saved("model.json") + self.saved("rows.json") + self.saved("plat.json")
```

In `test_towncode.py`, replace:

```python
        with open(rows_path, encoding="utf-8") as f:
            self.assertEqual(f.read(), corrupt)
```

with:

```python
        with open(rows_path, encoding="utf-8") as f:
            self.assertEqual(f.read(), corrupt)

    def test_survey_saves_the_plat_and_a_second_survey_keeps_every_lot(self):
        self.survey()
        first = self.saved("plat.json")
        self.assertIn('"hub/app.py"', first)
        self.survey()
        self.assertEqual(self.saved("plat.json"), first)

    def test_corrupt_saved_plat_exits_without_overwriting(self):
        self.survey()
        path = os.path.join(towncode.output_dir(self.root), "plat.json")
        with open(path, "w", encoding="utf-8") as f:
            f.write("[]")
        with self.assertRaises(SystemExit) as ctx:
            self.survey()
        self.assertIn("plat.json", str(ctx.exception))
        with open(path, encoding="utf-8") as f:
            self.assertEqual(f.read(), "[]")

    def snapshot(self, *args):
        with contextlib.redirect_stdout(io.StringIO()):
            return towncode.main(["snapshot", self.root, *args])

    def test_snapshot_draws_the_town_to_a_png_and_leaves_the_repo_untouched(self):
        before = untouched.fingerprint(self.root)
        png = os.path.join(self.out, "town.png")
        self.assertEqual(self.snapshot(png, "--size", "40x30", "--scale", "1"), 0)
        with open(png, "rb") as f:
            data = f.read()
        self.assertTrue(data.startswith(b"\x89PNG"))
        self.assertEqual(struct.unpack(">II", data[16:24]), (40, 30))
        self.assertEqual(untouched.differences(before, untouched.fingerprint(self.root)), {})

    def test_snapshot_can_centre_on_a_module_at_any_zoom(self):
        png = os.path.join(self.out, "town.png")
        for zoom in ("street", "district", "town"):
            self.assertEqual(self.snapshot(png, "--at", "hub/app.py", "--zoom", zoom,
                                           "--size", "30x20", "--scale", "1"), 0)
        with self.assertRaises(SystemExit) as ctx:
            self.snapshot(png, "--at", "nope.py")
        self.assertIn("nope.py", str(ctx.exception))

    def test_snapshot_refuses_to_write_inside_the_repo(self):
        inside = os.path.join(self.root, "town.png")
        with self.assertRaises(SystemExit) as ctx:
            self.snapshot(inside)
        self.assertIn("refusing to write inside", str(ctx.exception))
        self.assertFalse(os.path.exists(inside))

    def test_view_needs_an_interactive_terminal(self):
        with mock.patch("sys.stdin") as stdin:
            stdin.isatty.return_value = False
            with self.assertRaises(SystemExit) as ctx:
                towncode.main(["view", self.root])
        self.assertIn("interactive terminal", str(ctx.exception))
```

Replace the whole of `test_smoke.py` with:

```python
import fcntl
import os
import pty
import select
import shutil
import struct
import sys
import tempfile
import termios
import time
import unittest

import fixture
from test_survey import MONOREPO_LIKE

HERE = os.path.dirname(os.path.abspath(__file__))


def drain(fd, seconds):
    out = b""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        ready, _, _ = select.select([fd], [], [], 0.05)
        if ready:
            try:
                chunk = os.read(fd, 65536)
            except OSError:
                break
            if not chunk:
                break
            out += chunk
    return out


def wait_exit(pid, seconds):
    """The child's exit status, or None if it is still running after `seconds`."""
    deadline = time.monotonic() + seconds
    while True:
        done, status = os.waitpid(pid, os.WNOHANG)
        if done:
            return status
        if time.monotonic() >= deadline:
            return None
        time.sleep(0.02)


class SmokeTest(unittest.TestCase):
    def play(self, argv, keys, startup, per_key, env=None):
        """Run a program in a 120x40 terminal, press keys then q, and return what it drew."""
        pid, fd = pty.fork()
        if pid == 0:
            fcntl.ioctl(0, termios.TIOCSWINSZ, struct.pack("HHHH", 40, 120, 0, 0))
            os.environ["COLORTERM"] = "truecolor"
            os.environ.update(env or {})
            os.chdir(HERE)
            os.execv(sys.executable, [sys.executable, *argv])
        try:
            out = drain(fd, startup)
            for key in keys:
                os.write(fd, key)
                out += drain(fd, per_key)
            os.write(fd, b"q")
            out += drain(fd, 1.5)
            status = wait_exit(pid, 3.0)
            if status is None:
                os.kill(pid, 9)
                os.waitpid(pid, 0)
                self.fail(f"{argv[0]} did not exit after pressing q")
        finally:
            os.close(fd)
        text = out.decode("utf-8", errors="ignore")
        self.assertEqual(os.waitstatus_to_exitcode(status), 0, text[-500:])
        return text

    def test_game_draws_walks_talks_and_quits_cleanly(self):
        text = self.play(["town.py"], (b"d", b"d", b"\x1b[A", b"e"), startup=1.0, per_key=0.3)
        self.assertIn("\x1b[?1049h", text)
        self.assertIn("\u2588\u2588", text)
        self.assertIn("38;2;217;119;87", text)  # Clawd orange
        self.assertIn("\x1b[?1049l", text)
        self.assertIn("Thanks for visiting", text)

    def test_towncode_view_draws_jumps_inspects_zooms_and_quits_cleanly(self):
        root = fixture.make_repo(self, MONOREPO_LIKE)
        out_dir = tempfile.mkdtemp(prefix="towncode-out-")
        self.addCleanup(shutil.rmtree, out_dir)
        keys = (b"n", b"\r", b"d", b"\x1b[B", b"-", b"-", b"+")
        text = self.play(["towncode.py", "view", root], keys, startup=3.0, per_key=0.4,
                         env={"TOWNCODE_SURVEY_DIR": out_dir})
        self.assertIn("\x1b[?1049h", text)
        self.assertIn("\u2588\u2588", text)
        self.assertIn("problem 1 of", text)
        self.assertIn("\x1b[?1049l", text)
        self.assertIn("Saved to", text)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m unittest test_towncode test_smoke`
Expected: 8 tests fail (5 errors, 3 failures): the 7 new ones, and the leak test, which now reads `plat.json`. There is no `plat.json` yet, and argparse rejects `view` and `snapshot` with exit status 2, so the smoke test's `towncode.py view` quits before drawing anything.

- [ ] **Step 3: Add the commands**

Replace the whole of `towncode.py` with:

```python
"""Towncode: survey a repository into a model, and walk the town drawn from it.

    python3 towncode.py survey PATH [--check-untouched]
    python3 towncode.py view PATH [--256]
    python3 towncode.py snapshot PATH OUT.png [--zoom town] [--at MODULE] [--size WxH]

The surveyed repository is only read. Output goes to .survey/ next to this
file, or to $TOWNCODE_SURVEY_DIR, and never inside the repository.
"""

import argparse
import hashlib
import os
import subprocess
import sys

import problems
import snapshot
import survey
import term
import untouched
import viewer
from layers import Rows
from plat import Plat
from repo import Repo
from roads import Roads
from townmap import TownMap

HERE = os.path.dirname(os.path.abspath(__file__))
REPORT_LIMIT = 10


def _n(count, word):
    return f"{count} {word}" if count == 1 else f"{count} {word}s"


def survey_root():
    return os.environ.get("TOWNCODE_SURVEY_DIR") or os.path.join(HERE, ".survey")


def output_dir(repo_root):
    real = os.path.realpath(repo_root)
    tag = hashlib.sha256(real.encode("utf-8")).hexdigest()[:8]
    return os.path.join(survey_root(), f"{os.path.basename(real)}-{tag}")


def _inside(path, root):
    path, root = os.path.realpath(path), os.path.realpath(root)
    return path == root or path.startswith(root + os.sep)


def _require_repo(path):
    if not os.path.exists(os.path.join(path, ".git")):
        raise SystemExit(f"not a git repository: {path}")


def _fingerprint(repo_root, tracked):
    """Hash tracked files and git's own files; only stat the rest, never open them."""
    return untouched.fingerprint(
        repo_root, hashable=lambda rel: rel in tracked or rel.startswith(".git" + os.sep))


def _saved(path, load, what, remedy):
    """Load and update a saved file; a damaged one stops the run and is left as it is."""
    try:
        return load(path)
    except (ValueError, TypeError, KeyError, AttributeError) as e:
        raise SystemExit(f"cannot read saved {what} {path}: {e}. Delete it to {remedy}.") from e


def run(repo_root):
    _require_repo(repo_root)
    out = output_dir(repo_root)
    if _inside(out, repo_root):
        raise SystemExit(f"refusing to write inside the surveyed repository: {out}")
    model = survey.survey(repo_root)
    os.makedirs(out, exist_ok=True)
    rows_path = os.path.join(out, "rows.json")
    plat_path = os.path.join(out, "plat.json")
    rows = _saved(rows_path, lambda p: Rows.load(p).update(model), "rows", "rebuild the rows")
    plat = _saved(plat_path, lambda p: Plat.load(p).update(model, rows), "plat",
                  "lay the town out again")
    model.save(os.path.join(out, "model.json"))
    rows.save(rows_path)
    plat.save(plat_path)
    return model, rows, plat, out


def town(model, rows, plat):
    found = problems.find(model, rows)
    tmap = TownMap(model, plat, rows, found)
    return viewer.Viewer(tmap, Roads(tmap, model, found), model, found)


def report(model, rows, found):
    counts = {k: len(model.of_kind(k)) for k in ("source", "test", "unsurveyed")}
    lines = [f"{model.repo}: {_n(counts['source'], 'module')}, {_n(counts['test'], 'test')}, "
             f"{_n(counts['unsurveyed'], 'unsurveyed file')}, {_n(len(model.edges), 'road')}, "
             f"{_n(len(model.externals), 'outside package')}", "", "Districts, back row first:"]
    sizes = {}
    for m in model.of_kind("source"):
        sizes[m.district] = sizes.get(m.district, 0) + 1
    for name in sorted(sizes, key=lambda d: (rows.districts.get(d, 0), d)):
        lines.append(f"  row {rows.districts.get(name, 0)}  {name} ({_n(sizes[name], 'module')})")
    lines += ["", "Problems, worst first:" if found else "No problems found."]
    groups = {}
    for x in found:
        groups.setdefault(x.kind, []).append(x)
    for kind in problems.KINDS:
        group = groups.get(kind, [])
        if not group:
            continue
        lines.append(f"{kind} ({len(group)})")
        lines += [f"  {x.module}: {x.reason}" for x in group[:REPORT_LIMIT]]
        if len(group) > REPORT_LIMIT:
            lines.append(f"  ... and {len(group) - REPORT_LIMIT} more")
    return "\n".join(lines)


def _survey(args):
    tracked = set(Repo(args.path).files()) if args.check_untouched else None
    before = _fingerprint(args.path, tracked) if args.check_untouched else None
    model, rows, _, out = run(args.path)
    print(report(model, rows, problems.find(model, rows)))
    print(f"\nsaved to {out}")
    if before is None:
        return 0
    diff = untouched.differences(before, _fingerprint(args.path, tracked))
    if diff:
        print(f"untouched: NO, {sum(len(v) for v in diff.values())} paths differ")
        for change, paths in diff.items():
            print(f"  {change}: {', '.join(paths[:REPORT_LIMIT])}")
        return 1
    print(f"untouched: yes, {len(before)} paths identical before and after")
    return 0


def _view(args):
    if not sys.stdin.isatty():
        raise SystemExit("towncode view needs an interactive terminal.")
    model, rows, plat, out = run(args.path)
    v = town(model, rows, plat)
    truecolor = term.supports_truecolor() and not args.force256
    try:
        viewer.run(v, truecolor)
    except KeyboardInterrupt:
        pass
    print(f"{model.repo}: {_n(len(v.found), 'problem')}. Saved to {out}")
    return 0


def _snapshot(args):
    if _inside(args.out, args.path):
        raise SystemExit(f"refusing to write inside the surveyed repository: {args.out}")
    w, h = map(int, args.size.split("x"))
    model, rows, plat, _ = run(args.path)
    v = town(model, rows, plat)
    if args.at:
        tile = v.m.centre(args.at)
        if tile is None:
            raise SystemExit(f"no building or plot for {args.at}")
        v.cursor, v.problem = tile, None
    v.zoom = args.zoom
    snapshot.write_png(args.out, v.frame(w, h), args.scale)
    print(f"wrote {args.out}")
    return 0


def _parser():
    parser = argparse.ArgumentParser(prog="towncode")
    commands = parser.add_subparsers(dest="command", required=True)
    cmd = commands.add_parser("survey", help="survey a git repository without changing it")
    cmd.add_argument("path")
    cmd.add_argument("--check-untouched", action="store_true",
                     help="fingerprint the repository before and after; fail on any change")
    cmd = commands.add_parser("view", help="survey a repository, then walk its town")
    cmd.add_argument("path")
    cmd.add_argument("--256", dest="force256", action="store_true", help="force 256 colours")
    cmd = commands.add_parser("snapshot", help="survey a repository and draw its town to a PNG")
    cmd.add_argument("path")
    cmd.add_argument("out")
    cmd.add_argument("--zoom", choices=viewer.ZOOMS, default=viewer.TOWN)
    cmd.add_argument("--at", help="module to centre on (default: the worst problem)")
    cmd.add_argument("--size", default="160x90", help="frame in pixels, WxH")
    cmd.add_argument("--scale", type=int, default=4)
    return parser


COMMANDS = {"survey": _survey, "view": _view, "snapshot": _snapshot}


def main(argv=None):
    args = _parser().parse_args(argv)
    try:
        _require_repo(args.path)
        return COMMANDS[args.command](args)
    except subprocess.CalledProcessError as e:
        err = e.stderr.decode("utf-8", errors="replace")
        first_line = next((line for line in err.splitlines() if line.strip()), err.strip())
        if not first_line:
            first_line = "unknown error"
        raise SystemExit(f"git failed in {args.path}: {first_line}") from e


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3 -m unittest test_towncode test_smoke`
Expected: 20 tests, all `ok`.

- [ ] **Step 5: Document Towncode**

In `README.md`, replace:

```markdown
## Tests
```

with:

````markdown
## Towncode

Towncode draws any git repository as a town, so you can see where the work is.
It only ever reads the repository.

```bash
python3 towncode.py survey PATH [--check-untouched]   # print the problems
python3 towncode.py view PATH                          # walk the town
python3 towncode.py snapshot PATH out.png --zoom district --at MODULE
```

Folders are districts, modules are buildings, imports are roads and outside
packages are warehouses in the harbor. Problems show up in the town: fire for
code that won't parse, red loops for import cycles, towers, boarded-up
buildings and more (see `docs/superpowers/specs/`). The survey, rows and plat
are saved in `.survey/`, never inside the surveyed repository.

| Key | Action |
| --- | --- |
| `W` `A` `S` `D` / arrows | move the cursor |
| `+` / `-` | zoom: street, district, town |
| enter / space | inspector: facts and reasons |
| `N` / `P` | next or previous problem, worst first |
| `Q` | quit |

## Tests
````

- [ ] **Step 6: Run the whole suite**

Run: `python3 -m unittest`
Expected: 189 tests pass.

- [ ] **Step 7: Commit**

```bash
git add towncode.py README.md test_towncode.py test_smoke.py
git commit -m "Add towncode view and snapshot: walk the town in the terminal"
```


---

### Task 8: Walk the monorepo's town (read-only)

This task looks at the town drawn from the monorepo and tunes it with the user. It never edits, runs or commits anything in the monorepo, and snapshots go to `/tmp`.

- [ ] **Step 1: Survey the monorepo with the untouched check**

Run: `python3 towncode.py survey ~/repos/big-monorepo --check-untouched`
Expected: the report, then `untouched: yes, ... paths identical before and after`. If it says `untouched: NO`, stop and report the listed paths to the user before anything else.

- [ ] **Step 2: Draw it at every zoom**

```bash
for z in town district street; do
  python3 towncode.py snapshot ~/repos/big-monorepo /tmp/monorepo_$z.png --zoom $z --size 150x80 --scale 5
done
```

Expected: three PNGs.

- **Town:** the whole island, with the harbor at the back.
- **District:** readable roof colours per district, highways on the avenues, and lit or dark windows.
- **Street:** the worst problem (a hotspot, since the monorepo has no fires, cycles or backwards roads) with a white roof rim and cracked paving.

Unsurveyed files show as gray outlined plots.

- [ ] **Step 3: Walk it with the user**

`towncode view` needs a real terminal, so ask the user to run `python3 towncode.py view ~/repos/big-monorepo` in a large window. Show them the three PNGs. Ask whether the town reads at a glance, and whether the loud spots are the ones they know need work.

- [ ] **Step 4: Tune with agreement only**

Change sizes, colours or thresholds only with the user's agreement, each as a failing test first, in `~/codetown`.

- [ ] **Step 5: Check the monorepo is untouched and commit (codetown only)**

Run Step 1 again; it must end `untouched: yes`. Then:

```bash
git status --short
git add -u
git commit -m "Tune the town against a real repository"
```

`git status` must not list `.survey/` or any PNG. Skip the commit if Step 4 changed nothing.

---

## After this plan

- Milestone 2 (Clawd through the Cursor SDK) must settle the `d` key; see decision 3.
- A `towncode survey --rearrange` flag could replace deleting `plat.json` by hand, if rearranging turns out to be common.
