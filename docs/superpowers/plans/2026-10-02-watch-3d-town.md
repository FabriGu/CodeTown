# Watch in 3D, Plan 1: the Static 3D Town — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `towncode view PATH --browser` serves the town as a 3D scene on `127.0.0.1`. You can orbit it, zoom, and click a building to see the terminal inspector's facts, with its focus roads in blue and pink, a white roof, and the rest of the town dimmed.

**Architecture:** Python builds the town as today (survey, `TownMap`, `Roads`, `Viewer`) and turns it into plain JSON with `townjson.py`. `webserve.py` is a standard-library HTTP server that serves the page, the vendored Three.js, `/town.json` and `/focus`. In the browser, `web/town3d.js` builds instanced boxes from the JSON, and every colour and size comes from `web/look.js`. Python sends meanings, never colours. Live agents (`/events`, Clawds, `LiveTown`) and `towncode watch --browser` are Plan 2.

**Tech Stack:** Python 3 standard library (`http.server`, `json`, `hashlib`), `unittest`; Three.js 0.186.1 vendored as ES modules, with no npm and no build step; `playwright-cli` through `~/.codex/skills/playwright/scripts/playwright_cli.sh` for a browser smoke check run by hand.

**Spec:** `docs/superpowers/specs/2026-10-02-towncode-watch-3d-design.md`. This plan is its build-order step 1, "Static 3D town".

## Global Constraints

- **Base:** the `live-visuals` branch (PR #15, not merged yet). `towncode watch` exists only on the unmerged `towncode-watch-3`, so this plan serves the town from `towncode view`; Plan 2 adds `watch --browser`. Task 0 checks every name this plan uses. If any check fails, stop and report; don't adapt the plan on the fly.
- **Standard library only:** `townjson.py`, `webserve.py` and `smoke_web.py` import nothing outside it. `townjson.py` does no I/O.
- **Tests:** every task ends with both `.venv/bin/python -m unittest -q` and `python3 -m unittest -q` passing. System Python skips the tree-sitter tests.
- **Browser files:** no npm and no build step. The vendored Three.js files are never edited. `web/vendor/VERSION` holds each file's SHA-256, and a test checks them.
- **Server safety:**
  - it binds to `127.0.0.1` only, with no host option;
  - it accepts GET only, and everything else gets 405 with `Allow: GET`;
  - a `Host` header other than `127.0.0.1:PORT` or `localhost:PORT` gets 403;
  - static files come from a fixed table, and anything else gets 404;
  - it sends no CORS headers;
  - every response carries `Content-Security-Policy: default-src 'self'; script-src 'self' '<sha256 of the import map>'; style-src 'self'; img-src 'self' data:; connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'`, plus `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer` and `Cache-Control: no-store`.
- **Page safety:** repository strings (paths, titles, reasons) reach the page only through `textContent`, never `innerHTML`. The page has exactly one inline script, the import map, and no inline styles or event handlers.
- **Meanings, not colours:** Python sends kinds and indexes. Colours and sizes live in `web/look.js`, which is the designer's file. Colour meanings are unchanged: blue is uses, pink is used by, a white roof is the focus, amber is a function of 100 or more lines, red roads are cycles, and orange roads are backwards imports.
- **Only what the terminal shows:** file contents, transcripts and commands never reach the page. The inspector text is the terminal's `Viewer.describe`, and focus is `focus.select`, `focus.dim` and `Roads.visible`, so the two views can't disagree.
- **Read-only:** the surveyed repository is only read, and the survey is never written inside it. This plan never runs anything against the monorepo (`~/repos/big-monorepo`).
- **The designer's files:** `cake.py`, `focus.py`, `roles.py`, `session.py` and `mock_roles.py` are not edited.
- **Git:** work in the worktree `~/codetown-3d`, on the branch `watch-3d` off `live-visuals`. Its `.venv` is a link to `~/codetown/.venv`. Commit after each task, in the repository's commit style (sentence case, saying what the change does). Do not push. Pushing needs the user's go-ahead.

---

## File Structure

| File | Change |
| --- | --- |
| `drawtown.py` | `GLASS`, `window_kind(b)`, `roof_index(tmap)` lifted out of `TownScene`, which now uses them (Task 1). |
| `townjson.py` | New. `road(r)`, `town(tmap, roads, describe, *, repo, version=1)`, `selection(tmap, roads, model, *, module=None, package=None)` (Tasks 1–2). |
| `web/vendor/` | New. `three.module.js`, `three.core.js`, `OrbitControls.js`, `LICENSE`, `VERSION` (Task 3). |
| `webserve.py` | New. `Site`, `STATIC`, `import_map_hash`, `policy`, `Handler`, `Server`, `make_server`, `serve`, `DEFAULT_PORT = 8765` (Task 4). |
| `web/index.html`, `web/town3d.css` | New. The page shell: status bar, inspector panel, message box, import map (Task 4). |
| `towncode.py` | `view --browser`, `--port`, `--no-open`; `_browser(args)` (Task 5). |
| `web/look.js` | New. Every colour, size and camera setting (Task 6). |
| `web/town3d.js` | New. Scene, camera, report (Task 6); picking, inspector, focus (Task 7). |
| `smoke_web.py` | New. Browser smoke check run by hand; the name keeps it out of `unittest` discovery (Tasks 6–7). |
| `README.md` | "In the browser" section (Task 8). |
| Tests | `test_drawtown.py`, `test_townjson.py` (new), `test_vendor.py` (new), `test_webserve.py` (new), `test_towncode.py`. |

---

### Task 0: Check the base

**Files:** none changed.

- [ ] **Step 1: Work in the `watch-3d` worktree**

```bash
cd ~/codetown-3d
git branch --show-current   # must print watch-3d
git status --porcelain      # must print nothing; if not, stop and ask
git merge-base --is-ancestor live-visuals HEAD && echo "on live-visuals"
```

- [ ] **Step 2: Check every name this plan uses**

Run from the repository root:

```bash
.venv/bin/python - <<'EOF'
import inspect, sys
import cake, drawtown, focus, iso, problems, roads, towncode, townmap, viewer
from test_townmap import build

fails = []
def need(ok, what):
    print(("ok   " if ok else "FAIL ") + what)
    if not ok:
        fails.append(what)

def params(f):
    return list(inspect.signature(f).parameters)

need(params(roads.Roads.visible) == ["self", "selected", "focus"], "Roads.visible(selected=None, focus=None)")
need(params(roads.half_width) == ["kind", "weight"], "roads.half_width(kind, weight)")
need(roads.ORDER == ["road", "highway", "uses", "used by", "backwards", "cycle"], "roads.ORDER")
need({"kind", "src", "dst", "path", "weight"} <= set(roads.Road.__dataclass_fields__), "Road fields")
need(params(focus.select) == ["model", "module"] and params(focus.dim) == ["focus", "module"], "focus.select, focus.dim")
need({"module", "district", "x", "y", "size", "stack", "tested", "problems"} <= set(townmap.Building.__dataclass_fields__), "Building fields")
need({"package", "x", "y", "users", "size"} <= set(townmap.Warehouse.__dataclass_fields__), "Warehouse fields")
need(set(cake.Tier.__dataclass_fields__) == {"half", "z0", "z1", "amber"}, "cake.Tier(half, z0, z1, amber)")
need(params(viewer.Viewer.__init__)[:5] == ["self", "tmap", "roads", "model", "found"], "Viewer(tmap, roads, model, found, ...)")
need(params(viewer.Viewer.describe) == ["self", "thing"], "Viewer.describe(thing)")
need(params(towncode.town) == ["model", "rows", "plat", "layout", "changed", "sites"], "towncode.town(model, rows, plat, layout, changed, sites)")
need(params(towncode.run) == ["repo_root"] and params(towncode._session) == ["args", "model"], "towncode.run(repo_root), towncode._session(args, model)")
need("isatty" in inspect.getsource(towncode._view), "towncode._view checks for a terminal")
view = towncode._parser().parse_args(["view", "."])
need(hasattr(view, "layout") and hasattr(view, "session"), "towncode view --layout, --session")
need(iso.HALF_W == 6 and drawtown.ROOF == 2 and len(drawtown.ROOFS) == 8, "iso.HALF_W 6, drawtown.ROOF 2, 8 ROOFS")
need(all(hasattr(drawtown, n) for n in ("LIT", "DARK", "BOARD", "DOOR")), "drawtown LIT, DARK, BOARD, DOOR")
need("ROOFS[i % len(ROOFS)]" in inspect.getsource(drawtown.TownScene.__init__), "TownScene roofs by name order")
need("problems.ABANDONED" in inspect.getsource(drawtown.TownScene.glass), "TownScene.glass rule")
need(problems.FIRE == "won't parse" and problems.ABANDONED == "abandoned", "problem kind names")
model, rows, found, tmap = build()
kinds = {tmap.kind(x, y) for x in range(tmap.width) for y in range(tmap.height)}
need(kinds <= {"grass", "water", "quay", "dock", "avenue", "street", "lot", "plot", "vacant"}, f"ground kinds {sorted(kinds)}")
need('self.ground[(x, y)] = "site"' in inspect.getsource(townmap.TownMap._sites), "a session's new files are \"site\" tiles")
need(isinstance(tmap.trees, set) and isinstance(tmap.boxes, dict), "TownMap.trees, TownMap.boxes")
sys.exit(1 if fails else 0)
EOF
```

Expected: every line starts with `ok`, and the exit code is 0. If any line says `FAIL`, stop and report which names changed. The plan must be updated before any task runs.

- [ ] **Step 3: Both test suites pass before anything changes**

Run: `.venv/bin/python -m unittest -q && python3 -m unittest -q`
Expected: both end with `OK` (the second with skips).

---

### Task 1: The town as JSON

**Files:**
- Modify: `drawtown.py`. Add `GLASS`, `window_kind` and `roof_index` after the colour constants, and make `TownScene.__init__`'s `self.roofs = …` line and `TownScene.glass` use them.
- Create: `townjson.py`
- Test: `test_drawtown.py`, and a new `test_townjson.py`

**Interfaces:**
- Produces:
  - `drawtown.GLASS: dict[str, tuple]`, with the keys `"board"`, `"door"`, `"lit"` and `"dark"`.
  - `drawtown.window_kind(b: Building) -> str`, one of those four keys.
  - `drawtown.roof_index(tmap) -> dict[str, int]`, each district's index into `ROOFS`.
  - `townjson.LETTERS: dict[str, str]`, mapping a ground kind to its letter.
  - `townjson.road(r: roads.Road) -> dict`, with the keys `from`, `to`, `kind`, `weight`, `half`, `layer` and `tiles`.
  - `townjson.town(tmap, roads, describe, *, repo: str, version: int = 1) -> dict`, with the keys `version`, `repo`, `size`, `half_w`, `legend`, `tiles`, `trees`, `districts`, `buildings`, `warehouses` and `roads`.
    - `describe` is a callable `thing -> (title, facts, reasons)`, in practice `Viewer.describe`.
    - Each building is `{"path", "district", "lot": [x, y, size], "tiers": [{"half", "z0", "z1", "amber"}], "glass", "problems": [kind, …], "inspect": {"title", "facts", "reasons"}}`.
    - Each warehouse is `{"package", "lot", "inspect"}`.
    - Each district is `{"name", "box": [x, y, w, h] or None, "roof": int}`.

- [ ] **Step 1: Write the failing drawtown tests**

Add to `test_drawtown.py`. Extend its imports with `from drawtown import GLASS, ROOFS, TownScene, roof_index, window_kind`, keeping any names it already imports, and `from test_townmap import build` if it isn't imported yet:

```python
class WindowAndRoofRulesTest(unittest.TestCase):
    def setUp(self):
        self.model, self.rows, self.found, self.town = build()
        self.scene = TownScene(self.town, 40, 30, 0, 0)

    def test_window_kind_names_the_glass_each_building_gets(self):
        seen = set()
        for b in self.town.buildings.values():
            kind = window_kind(b)
            seen.add(kind)
            self.assertEqual(self.scene.glass(b), GLASS[kind], b.module)
        self.assertEqual(seen, {"board", "door", "lit", "dark"})

    def test_roof_index_gives_each_district_the_roof_the_scene_paints(self):
        index = roof_index(self.town)
        self.assertEqual({name: ROOFS[i] for name, i in index.items()}, self.scene.roofs)
        self.assertEqual(set(index),
                         set(self.town.boxes) | {b.district for b in self.town.buildings.values()})
```

- [ ] **Step 2: Run them to see them fail**

Run: `.venv/bin/python -m unittest -q test_drawtown`
Expected: ERROR, `ImportError: cannot import name 'GLASS' from 'drawtown'`.

- [ ] **Step 3: Lift the two rules out of `TownScene`**

In `drawtown.py`, after the block of colour constants (after `ROAD_COLORS`/`LOUD_ROADS`), add:

```python
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
```

In `TownScene.__init__`, replace these two lines:

```python
        names = sorted(set(tmap.boxes) | {b.district for b in tmap.buildings.values()})
        self.roofs = {name: ROOFS[i % len(ROOFS)] for i, name in enumerate(names)}
```

with:

```python
        self.roofs = {name: ROOFS[i] for name, i in roof_index(tmap).items()}
```

Replace the body of `TownScene.glass` with:

```python
    def glass(self, b):
        return GLASS[window_kind(b)]
```

- [ ] **Step 4: Run the drawtown tests**

Run: `.venv/bin/python -m unittest -q test_drawtown test_viewer`
Expected: OK. The pixel town draws exactly as before.

- [ ] **Step 5: Write the failing townjson tests**

Create `test_townjson.py`:

```python
import json
import unittest

import drawtown
import fixture
import problems
import roads as R
import survey
import townjson
from layers import Rows
from plat import Plat
from roads import Roads
from test_townmap import build
from townmap import TownMap
from viewer import Viewer


class TownDocumentTest(unittest.TestCase):
    def setUp(self):
        self.model, self.rows, self.found, self.tmap = build()
        self.roads = Roads(self.tmap, self.model, self.found)
        self.viewer = Viewer(self.tmap, self.roads, self.model, self.found)
        self.doc = townjson.town(self.tmap, self.roads, self.viewer.describe,
                                 repo="showcase", version=3)

    def test_it_survives_a_round_trip_through_json(self):
        self.assertEqual(json.loads(json.dumps(self.doc)), self.doc)

    def test_it_names_its_repo_version_size_and_pixel_scale(self):
        self.assertEqual((self.doc["repo"], self.doc["version"]), ("showcase", 3))
        self.assertEqual(self.doc["size"], [self.tmap.width, self.tmap.height])
        self.assertEqual(self.doc["half_w"], 6)

    def test_tile_rows_spell_every_tile_kind(self):
        legend = self.doc["legend"]
        self.assertEqual(len(self.doc["tiles"]), self.tmap.height)
        for y, row in enumerate(self.doc["tiles"]):
            self.assertEqual(len(row), self.tmap.width)
            for x, letter in enumerate(row):
                self.assertEqual(legend[letter], self.tmap.kind(x, y), (x, y))

    def test_a_sessions_new_files_are_site_tiles(self):
        tmap = TownMap(self.model, Plat().update(self.model, self.rows), self.rows, self.found,
                       sites=["app/new.py"])
        roads = Roads(tmap, self.model, self.found)
        doc = townjson.town(tmap, roads, Viewer(tmap, roads, self.model, self.found).describe,
                            repo="showcase")
        x, y = tmap.sites["app/new.py"]
        self.assertEqual(doc["legend"][doc["tiles"][y][x]], "site")

    def test_trees_are_the_town_maps(self):
        self.assertEqual({tuple(t) for t in self.doc["trees"]}, self.tmap.trees)

    def test_each_building_carries_its_lot_cake_windows_and_problems(self):
        docs = {d["path"]: d for d in self.doc["buildings"]}
        self.assertEqual(set(docs), set(self.tmap.buildings))
        for module, b in self.tmap.buildings.items():
            d = docs[module]
            self.assertEqual(d["lot"], [b.x, b.y, b.size])
            self.assertEqual(d["district"], b.district)
            self.assertEqual([(t["half"], t["z0"], t["z1"], t["amber"]) for t in d["tiers"]],
                             [(t.half, t.z0, t.z1, t.amber) for t in b.stack])
            self.assertEqual(d["glass"], drawtown.window_kind(b))
            self.assertEqual(set(d["problems"]), set(b.problems))

    def test_roofs_are_the_pixel_towns(self):
        self.assertEqual({d["name"]: d["roof"] for d in self.doc["districts"]},
                         drawtown.roof_index(self.tmap))
        for d in self.doc["districts"]:
            box = self.tmap.boxes.get(d["name"])
            self.assertEqual(d["box"], list(box) if box else None)

    def test_inspect_is_the_terminal_inspector(self):
        for d in self.doc["buildings"]:
            title, facts, reasons = self.viewer.describe(self.tmap.buildings[d["path"]])
            self.assertEqual(d["inspect"], {"title": title, "facts": facts, "reasons": reasons})
        broken = next(d for d in self.doc["buildings"] if problems.FIRE in d["problems"])
        self.assertTrue(broken["inspect"]["reasons"])

    def test_warehouses_carry_their_lot_and_inspector(self):
        docs = {d["package"]: d for d in self.doc["warehouses"]}
        self.assertEqual(set(docs), set(self.tmap.warehouses))
        for package, w in self.tmap.warehouses.items():
            self.assertEqual(docs[package]["lot"], [w.x, w.y, w.size])
            self.assertEqual(docs[package]["inspect"]["title"], self.viewer.describe(w)[0])

    def test_roads_are_the_ones_the_terminal_shows_with_nothing_selected(self):
        self.assertEqual(self.doc["roads"], [townjson.road(r) for r in self.roads.visible()])
        self.assertIn("cycle", {r["kind"] for r in self.doc["roads"]})

    def test_a_road_keeps_its_ends_tiles_width_and_layer(self):
        r = self.roads.visible()[0]
        d = townjson.road(r)
        self.assertEqual((d["from"], d["to"], d["kind"], d["weight"]),
                         (r.src, r.dst, r.kind, r.weight))
        self.assertEqual(d["tiles"], [list(t) for t in r.path])
        self.assertEqual(d["half"], R.half_width(r.kind, r.weight))
        self.assertEqual(d["layer"], R.ORDER.index(r.kind))


class NoFileContentsTest(unittest.TestCase):
    def test_file_contents_never_reach_the_document(self):
        marker = "zebra-quartz-7731"
        root = fixture.make_repo(self, {
            "pkg/__init__.py": "",
            "pkg/a.py": f"# {marker}\nimport pkg.b\nNOTE = '{marker}'\n\n\ndef run():\n"
                        f"    return '{marker}'\n",
            "pkg/b.py": f'"""{marker}"""\nimport pkg.a\n',
            "pkg/broken.py": f"def half(:\n    return '{marker}'\n",
        })
        model = survey.survey(root)
        rows = Rows({}).update(model)
        found = problems.find(model, rows)
        tmap = TownMap(model, Plat().update(model, rows), rows, found)
        roads = Roads(tmap, model, found)
        doc = townjson.town(tmap, roads, Viewer(tmap, roads, model, found).describe,
                            repo="fixture")
        text = json.dumps(doc)
        self.assertIn("pkg/a.py", text)
        self.assertNotIn(marker, text)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 6: Run them to see them fail**

Run: `.venv/bin/python -m unittest -q test_townjson`
Expected: ERROR, `ModuleNotFoundError: No module named 'townjson'`.

- [ ] **Step 7: Write `townjson.py`**

```python
"""The town as JSON-ready dictionaries for the 3D view: plain data in, plain data out, no I/O.

Python sends meanings (tile kinds, problem kinds, roof indexes, paths), never colours; the
browser's web/look.js turns each meaning into a colour. Inspector text comes from the caller's
describe, the terminal Viewer's, so the two views say the same thing.
"""

import drawtown
import iso
import problems
import roads as R

LETTERS = {"grass": "g", "water": "w", "quay": "q", "dock": "d", "avenue": "a",
           "street": "s", "lot": "l", "plot": "p", "vacant": "v", "site": "c"}


def road(r):
    """One road: its ends, kind, width in tiles, draw layer and tile run."""
    return {"from": r.src, "to": r.dst, "kind": r.kind, "weight": r.weight,
            "half": R.half_width(r.kind, r.weight), "layer": R.ORDER.index(r.kind),
            "tiles": [list(t) for t in r.path]}


def _inspect(describe, thing):
    title, facts, reasons = describe(thing)
    return {"title": title, "facts": facts, "reasons": list(reasons)}


def _building(b, describe):
    return {"path": b.module, "district": b.district, "lot": [b.x, b.y, b.size],
            "tiers": [{"half": t.half, "z0": t.z0, "z1": t.z1, "amber": t.amber}
                      for t in b.stack],
            "glass": drawtown.window_kind(b),
            "problems": [k for k in problems.KINDS if k in b.problems],
            "inspect": _inspect(describe, b)}


def town(tmap, roads, describe, *, repo, version=1):
    """Everything the browser builds once: ground, trees, buildings, warehouses and roads."""
    return {
        "version": version,
        "repo": repo,
        "size": [tmap.width, tmap.height],
        "half_w": iso.HALF_W,
        "legend": {letter: kind for kind, letter in LETTERS.items()},
        "tiles": ["".join(LETTERS[tmap.kind(x, y)] for x in range(tmap.width))
                  for y in range(tmap.height)],
        "trees": [list(t) for t in sorted(tmap.trees)],
        "districts": [{"name": name,
                       "box": list(tmap.boxes[name]) if name in tmap.boxes else None,
                       "roof": i}
                      for name, i in sorted(drawtown.roof_index(tmap).items())],
        "buildings": [_building(b, describe) for _, b in sorted(tmap.buildings.items())],
        "warehouses": [{"package": w.package, "lot": [w.x, w.y, w.size],
                        "inspect": _inspect(describe, w)}
                       for _, w in sorted(tmap.warehouses.items())],
        "roads": [road(r) for r in roads.visible()],
    }
```

- [ ] **Step 8: Run the tests**

Run: `.venv/bin/python -m unittest -q test_townjson test_drawtown`
Expected: OK.

If the `problems` assertion fails, a building has a problem kind missing from `problems.KINDS`. Report it rather than dropping the check.

- [ ] **Step 9: Run both suites, then commit**

Run: `.venv/bin/python -m unittest -q && python3 -m unittest -q`
Expected: both OK.

```bash
git add drawtown.py townjson.py test_drawtown.py test_townjson.py
git commit -m "Describe the town as JSON for the 3D view, with drawtown's window and roof rules shared"
```

---

### Task 2: What a selection lights up

**Files:**
- Modify: `townjson.py`
- Test: `test_townjson.py`

**Interfaces:**
- Consumes: `townjson.road(r)` (Task 1).
- Produces: `townjson.selection(tmap, roads, model, *, module=None, package=None) -> dict | None`.
  - It returns `{"focused": [path], "dim": {path: float for every building}, "roads": [road, …]}` for a module.
  - It returns `{"focused": [], "dim": {}, "roads": [road, …]}` for a package.
  - It returns `None` when neither is given, or for a name that isn't in the town.
  - With both given, the module wins. The server never passes both.

- [ ] **Step 1: Write the failing tests**

Add `import focus` to the imports of `test_townjson.py`, and add this class:

```python
class SelectionTest(unittest.TestCase):
    def setUp(self):
        self.model, self.rows, self.found, self.tmap = build()
        self.roads = Roads(self.tmap, self.model, self.found)

    def select(self, **name):
        return townjson.selection(self.tmap, self.roads, self.model, **name)

    def test_a_module_dims_the_town_by_distance_and_shows_its_focus_roads(self):
        module = "core/tower.py"
        answer = self.select(module=module)
        f = focus.select(self.model, module)
        self.assertEqual(answer["focused"], [module])
        self.assertEqual(answer["dim"], {m: focus.dim(f, m) for m in self.tmap.buildings})
        b = self.tmap.buildings[module]
        self.assertEqual(answer["roads"], [townjson.road(r) for r in self.roads.visible(b, f)])
        self.assertLessEqual({"uses", "used by"}, {r["kind"] for r in answer["roads"]})

    def test_a_warehouse_shows_its_users_roads_and_dims_nothing(self):
        answer = self.select(package="flask")
        self.assertEqual((answer["focused"], answer["dim"]), ([], {}))
        w = self.tmap.warehouses["flask"]
        self.assertEqual(answer["roads"], [townjson.road(r) for r in self.roads.visible(w)])
        self.assertTrue(answer["roads"])

    def test_a_name_not_in_the_town_has_no_answer(self):
        self.assertIsNone(self.select(module="nope.py"))
        self.assertIsNone(self.select(package="nope"))
        self.assertIsNone(self.select())

    def test_the_answer_survives_a_round_trip_through_json(self):
        answer = self.select(module="core/tower.py")
        self.assertEqual(json.loads(json.dumps(answer)), answer)
```

In `NoFileContentsTest`, replace `text = json.dumps(doc)` with:

```python
        text = json.dumps(doc) + json.dumps(townjson.selection(tmap, roads, model,
                                                               module="pkg/a.py"))
```

- [ ] **Step 2: Run them to see them fail**

Run: `.venv/bin/python -m unittest -q test_townjson`
Expected: ERROR, `AttributeError: module 'townjson' has no attribute 'selection'`.

- [ ] **Step 3: Add `selection`**

In `townjson.py`, add `import focus` to the imports, and add at the end:

```python
def selection(tmap, roads, model, *, module=None, package=None):
    """What clicking a building or warehouse lights up, as the terminal draws a selection.

    For a building: its focus (focus.select), every building's brightness (focus.dim), and
    Roads.visible(building, focus). For a warehouse: Roads.visible(warehouse), nothing dimmed.
    None for a name that isn't in the town.
    """
    if module is not None:
        b = tmap.buildings.get(module)
        if b is None:
            return None
        f = focus.select(model, module)
        return {"focused": [module],
                "dim": {m: focus.dim(f, m) for m in sorted(tmap.buildings)},
                "roads": [road(r) for r in roads.visible(b, f)]}
    if package is not None:
        w = tmap.warehouses.get(package)
        if w is None:
            return None
        return {"focused": [], "dim": {}, "roads": [road(r) for r in roads.visible(w)]}
    return None
```

- [ ] **Step 4: Run the tests**

Run: `.venv/bin/python -m unittest -q test_townjson`
Expected: OK.

- [ ] **Step 5: Run both suites, then commit**

Run: `.venv/bin/python -m unittest -q && python3 -m unittest -q`
Expected: both OK.

```bash
git add townjson.py test_townjson.py
git commit -m "Answer what a 3D selection lights up, from the terminal's own focus and roads"
```

---

### Task 3: Vendor Three.js

**Files:**
- Create: `web/vendor/three.module.js`, `web/vendor/three.core.js`, `web/vendor/OrbitControls.js`, `web/vendor/LICENSE`, `web/vendor/VERSION`
- Test: a new `test_vendor.py`

**Interfaces:**
- Produces:
  - `web/vendor/VERSION`. Line 1 is `three X.Y.Z from https://registry.npmjs.org/three/-/three-X.Y.Z.tgz`. Each following line is `<sha256>  <file>`, as printed by `shasum -a 256`.
  - The import map in Task 4 maps `three` to `/static/vendor/three.module.js` and `three/addons/controls/OrbitControls.js` to `/static/vendor/OrbitControls.js`.

- [ ] **Step 1: Write the failing test**

Create `test_vendor.py`:

```python
import hashlib
import os
import re
import unittest

VENDOR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web", "vendor")
FILES = ["LICENSE", "OrbitControls.js", "three.core.js", "three.module.js"]
# Statements only: OrbitControls.js mentions an import path in a doc comment too.
SOURCES = re.compile(r"^(?:import|export)\b[^;]*?\bfrom '([^']+)'", re.M)


def read(name):
    with open(os.path.join(VENDOR, name), encoding="utf-8") as f:
        return f.read()


def digest(name):
    with open(os.path.join(VENDOR, name), "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def pinned():
    first, *rest = read("VERSION").splitlines()
    pairs = (line.split(maxsplit=1) for line in rest if line.strip())
    return first, {name: sha for sha, name in pairs}


class VendoredThreeTest(unittest.TestCase):
    def test_version_names_one_three_release_from_npm(self):
        first, _ = pinned()
        self.assertRegex(first, r"^three (\d+\.\d+\.\d+) from "
                                r"https://registry\.npmjs\.org/three/-/three-\1\.tgz$")

    def test_every_file_matches_its_pinned_sha256(self):
        _, sums = pinned()
        self.assertEqual(sorted(sums), FILES)
        for name in FILES:
            self.assertEqual(digest(name), sums[name], name)

    def test_the_module_imports_only_the_vendored_core(self):
        self.assertEqual(set(SOURCES.findall(read("three.module.js"))), {"./three.core.js"})

    def test_the_core_imports_nothing(self):
        self.assertEqual(SOURCES.findall(read("three.core.js")), [])

    def test_orbit_controls_imports_only_three(self):
        self.assertEqual(set(SOURCES.findall(read("OrbitControls.js"))), {"three"})

    def test_three_is_mit_licensed(self):
        self.assertTrue(read("LICENSE").startswith("The MIT License"))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run it to see it fail**

Run: `.venv/bin/python -m unittest -q test_vendor`
Expected: ERROR, `FileNotFoundError` for `web/vendor/VERSION`.

- [ ] **Step 3: Download the latest release and check the tarball against npm's integrity hash**

```bash
VERSION=$(curl -s https://registry.npmjs.org/three/latest | python3 -c 'import json,sys; print(json.load(sys.stdin)["version"])')
echo "three $VERSION"
rm -rf /tmp/three-vendor && mkdir -p /tmp/three-vendor
curl -sL "https://registry.npmjs.org/three/-/three-$VERSION.tgz" -o /tmp/three-vendor/three.tgz
INTEGRITY=$(curl -s "https://registry.npmjs.org/three/$VERSION" | python3 -c 'import json,sys; print(json.load(sys.stdin)["dist"]["integrity"])')
python3 - "$INTEGRITY" <<'EOF'
import base64, hashlib, sys
algo, digest = sys.argv[1].split("-", 1)
assert algo == "sha512", algo
with open("/tmp/three-vendor/three.tgz", "rb") as f:
    ok = base64.b64encode(hashlib.sha512(f.read()).digest()).decode() == digest
print("integrity ok" if ok else "INTEGRITY MISMATCH")
sys.exit(0 if ok else 1)
EOF
tar -xzf /tmp/three-vendor/three.tgz -C /tmp/three-vendor
```

Expected: `integrity ok`. On a mismatch, stop and report; don't vendor anything.

- [ ] **Step 4: Copy the four files and write `VERSION`**

```bash
mkdir -p web/vendor
cp /tmp/three-vendor/package/build/three.module.js /tmp/three-vendor/package/build/three.core.js web/vendor/
cp /tmp/three-vendor/package/examples/jsm/controls/OrbitControls.js web/vendor/
cp /tmp/three-vendor/package/LICENSE web/vendor/LICENSE
(cd web/vendor && { echo "three $VERSION from https://registry.npmjs.org/three/-/three-$VERSION.tgz"; shasum -a 256 LICENSE OrbitControls.js three.core.js three.module.js; } > VERSION)
cat web/vendor/VERSION
rm -rf /tmp/three-vendor
```

If `package/build/three.module.js` or `three.core.js` is missing, the release layout has changed. Stop and report.

- [ ] **Step 5: Run the test**

Run: `.venv/bin/python -m unittest -q test_vendor`
Expected: OK.

If `test_the_module_imports_only_the_vendored_core` fails, this release splits Three.js into more files than the import map serves. Stop and report rather than adding files the plan doesn't name.

- [ ] **Step 6: Run both suites, then commit**

Run: `.venv/bin/python -m unittest -q && python3 -m unittest -q`
Expected: both OK.

```bash
git add web/vendor test_vendor.py
git commit -m "Vendor one pinned Three.js release for the 3D town, with each file's SHA-256"
```

---

### Task 4: The local server and the page shell

**Files:**
- Create: `webserve.py`, `web/index.html`, `web/town3d.css`
- Test: a new `test_webserve.py`

**Interfaces:**
- Consumes: the vendored file names (Task 3).
- Produces:
  - `webserve.DEFAULT_PORT = 8765`.
  - `webserve.WEB`, the absolute path of `web/`.
  - `webserve.STATIC: dict[str, tuple[str, str]]`, mapping a URL path to a file under `web/` and its content type.
  - `webserve.Site(town: dict, select: Callable[..., dict | None])`. `select` is called with the keywords `module=` and `package=`, exactly one of them a string.
  - `webserve.import_map_hash(html) -> str` returns `"'sha256-…'"`.
  - `webserve.policy(html) -> str` returns the CSP header value.
  - `webserve.make_server(site, port=DEFAULT_PORT) -> Server`. A busy port raises `SystemExit` with a `--port 0` hint.
  - `webserve.serve(site, port=DEFAULT_PORT, *, open_browser=True, opener=webbrowser.open) -> int`. It blocks until Ctrl-C and returns 0.
  - Routes:
    - `GET /`;
    - `GET /town.json`;
    - `GET /focus?module=PATH`, or `GET /focus?package=NAME`;
    - `GET /static/…`, from the table only.

- [ ] **Step 1: Write the page shell**

Create `web/index.html`. The import map must stay on one line, because its exact text is what the CSP hash covers:

```html
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>CodeTown</title>
<link rel="stylesheet" href="/static/town3d.css">
<script type="importmap">{"imports": {"three": "/static/vendor/three.module.js", "three/addons/controls/OrbitControls.js": "/static/vendor/OrbitControls.js"}}</script>
<script type="module" src="/static/town3d.js"></script>
</head>
<body>
<header id="status">
<div id="line1">Loading the town…</div>
<div id="line2"></div>
<div id="line3"></div>
</header>
<aside id="inspector" hidden>
<h2 id="inspect-title"></h2>
<p id="inspect-facts"></p>
<ul id="inspect-reasons"></ul>
</aside>
<div id="message" hidden></div>
</body>
</html>
```

Create `web/town3d.css`:

```css
html, body { margin: 0; height: 100%; overflow: hidden; background: rgb(30, 66, 112);
  color: rgb(236, 236, 236); font: 13px/1.4 ui-monospace, Menlo, monospace; }
canvas { display: block; }
#status { position: fixed; top: 0; left: 0; right: 0; padding: 6px 10px; white-space: pre;
  background: rgba(14, 18, 32, 0.78); pointer-events: none; }
#line1 { color: rgb(255, 250, 215); font-weight: bold; }
#line2 { color: rgb(188, 188, 188); }
#line3 { color: rgb(138, 138, 138); }
#inspector { position: fixed; top: 76px; right: 12px; width: 360px; max-height: calc(100% - 100px);
  overflow: auto; padding: 10px 12px; background: rgba(14, 18, 32, 0.9);
  border: 1px solid rgba(236, 246, 255, 0.25); border-radius: 6px; }
#inspector h2 { margin: 0 0 6px; font-size: 14px; color: rgb(255, 250, 215); overflow-wrap: anywhere; }
#inspector p { margin: 0 0 6px; color: rgb(200, 200, 200); }
#inspector ul { margin: 0; padding-left: 18px; color: rgb(255, 170, 150); }
#message { position: fixed; top: 76px; left: 12px; right: 12px; padding: 12px;
  background: rgba(14, 18, 32, 0.92); font-size: 15px; }
[hidden] { display: none !important; }
```

- [ ] **Step 2: Write the failing server tests**

Create `test_webserve.py`:

```python
import base64
import contextlib
import hashlib
import http.client
import io
import json
import os
import re
import socket
import threading
import unittest
from unittest import mock

import webserve

TOWN = {"version": 1, "repo": "fake", "buildings": []}


def select(module=None, package=None):
    if module == "a.py":
        return {"focused": ["a.py"], "dim": {"a.py": 1.0}, "roads": []}
    if package == "flask":
        return {"focused": [], "dim": {}, "roads": []}
    return None


SITE = webserve.Site(TOWN, select)


def page():
    with open(os.path.join(webserve.WEB, "index.html"), encoding="utf-8") as f:
        return f.read()


class ServerTest(unittest.TestCase):
    def setUp(self):
        self.server = webserve.make_server(SITE, 0)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)

    def request(self, path, method="GET", host="here"):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        self.addCleanup(conn.close)
        conn.putrequest(method, path, skip_host=True, skip_accept_encoding=True)
        if host == "here":
            host = f"127.0.0.1:{self.port}"
        if host is not None:
            conn.putheader("Host", host)
        conn.endheaders()
        response = conn.getresponse()
        return response, response.read()

    def test_it_listens_on_this_machine_only(self):
        self.assertEqual(self.server.server_address[0], "127.0.0.1")

    def test_the_page_comes_with_a_strict_policy_and_no_cors(self):
        r, body = self.request("/")
        self.assertEqual(r.status, 200)
        self.assertEqual(r.getheader("Content-Type"), "text/html; charset=utf-8")
        self.assertEqual(body.decode("utf-8"), page())
        self.assertEqual(r.getheader("Content-Security-Policy"), webserve.policy(page()))
        self.assertEqual(r.getheader("X-Content-Type-Options"), "nosniff")
        self.assertEqual(r.getheader("Referrer-Policy"), "no-referrer")
        self.assertEqual(r.getheader("Cache-Control"), "no-store")
        self.assertIsNone(r.getheader("Access-Control-Allow-Origin"))

    def test_the_policy_allows_the_import_map_and_nothing_else_inline(self):
        html = page()
        inline = re.search(r'<script type="importmap">(.*?)</script>', html, re.S).group(1)
        digest = base64.b64encode(hashlib.sha256(inline.encode("utf-8")).digest()).decode()
        self.assertEqual(webserve.policy(html),
                         "default-src 'self'; "
                         f"script-src 'self' 'sha256-{digest}'; "
                         "style-src 'self'; img-src 'self' data:; connect-src 'self'; "
                         "base-uri 'none'; form-action 'none'; frame-ancestors 'none'")
        self.assertEqual(len(re.findall(r"<script(?![^>]*\bsrc=)", html)), 1)
        self.assertNotIn("style=", html)
        self.assertNotRegex(html, r"\son[a-z]+=")

    def test_the_import_map_points_only_at_served_files(self):
        inline = re.search(r'<script type="importmap">(.*?)</script>', page(), re.S).group(1)
        for target in json.loads(inline)["imports"].values():
            self.assertIn(target, webserve.STATIC)

    def test_town_json_is_the_sites_town(self):
        r, body = self.request("/town.json")
        self.assertEqual((r.status, r.getheader("Content-Type")), (200, "application/json"))
        self.assertEqual(json.loads(body), TOWN)

    def test_focus_answers_one_known_module_or_package(self):
        r, body = self.request("/focus?module=a.py")
        self.assertEqual((r.status, json.loads(body)["focused"]), (200, ["a.py"]))
        r, body = self.request("/focus?package=flask")
        self.assertEqual((r.status, json.loads(body)["focused"]), (200, []))

    def test_focus_needs_exactly_one_known_name(self):
        for path in ("/focus", "/focus?module=nope.py", "/focus?package=nope",
                     "/focus?module=a.py&package=flask", "/focus?module="):
            self.assertEqual(self.request(path)[0].status, 404, path)

    def test_vendored_three_is_served_as_javascript(self):
        r, body = self.request("/static/vendor/three.module.js")
        self.assertEqual((r.status, r.getheader("Content-Type")),
                         (200, "text/javascript; charset=utf-8"))
        self.assertIn(b"three.core.js", body)

    def test_unknown_and_escaping_paths_are_not_found(self):
        for path in ("/static/../towncode.py", "/towncode.py", "/static/nope.js",
                     "//evil.example/town.json", "/web/index.html", "/static/vendor/VERSION"):
            self.assertEqual(self.request(path)[0].status, 404, path)

    def test_requests_for_another_host_are_refused(self):
        for host in ("evil.example", f"evil.example:{self.port}", "127.0.0.1", None):
            self.assertEqual(self.request("/town.json", host=host)[0].status, 403, host)
        self.assertEqual(self.request("/town.json", host=f"localhost:{self.port}")[0].status, 200)

    def test_only_get_is_allowed(self):
        for method in ("POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"):
            r, body = self.request("/town.json", method=method)
            self.assertEqual((r.status, r.getheader("Allow")), (405, "GET"), method)
        self.assertEqual(self.request("/", method="HEAD")[1], b"")


class StartTest(unittest.TestCase):
    def test_a_busy_port_says_how_to_pick_another(self):
        busy = socket.socket()
        self.addCleanup(busy.close)
        busy.bind(("127.0.0.1", 0))
        busy.listen()
        with self.assertRaises(SystemExit) as caught:
            webserve.make_server(SITE, busy.getsockname()[1])
        self.assertIn("--port 0", str(caught.exception))

    def serve(self, **options):
        opened = []
        out = io.StringIO()
        with mock.patch.object(webserve.Server, "serve_forever", side_effect=KeyboardInterrupt), \
                contextlib.redirect_stdout(out):
            code = webserve.serve(SITE, 0, opener=lambda url: opened.append(url) or True, **options)
        return code, out.getvalue(), opened

    def test_serve_prints_the_address_and_opens_it(self):
        code, out, opened = self.serve()
        url = re.search(r"http://127\.0\.0\.1:\d+/", out).group(0)
        self.assertEqual((code, opened), (0, [url]))

    def test_serve_can_leave_the_browser_closed(self):
        code, out, opened = self.serve(open_browser=False)
        self.assertEqual((code, opened), (0, []))
        self.assertIn("http://127.0.0.1:", out)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run them to see them fail**

Run: `.venv/bin/python -m unittest -q test_webserve`
Expected: ERROR, `ModuleNotFoundError: No module named 'webserve'`.

- [ ] **Step 4: Write `webserve.py`**

```python
"""The 3D town's web server: the page, its files, the town document and selection answers.

It listens on 127.0.0.1 only and answers GET only. A request naming any other Host is refused,
which blocks DNS rebinding. Static files come from a fixed table, so no request reaches a file
outside web/. Every response carries a strict Content-Security-Policy.
"""

import base64
import errno
import hashlib
import json
import os
import re
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
WEB = os.path.join(HERE, "web")
DEFAULT_PORT = 8765
JS = "text/javascript; charset=utf-8"
TEXT = "text/plain; charset=utf-8"
STATIC = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/static/town3d.css": ("town3d.css", "text/css; charset=utf-8"),
    "/static/town3d.js": ("town3d.js", JS),
    "/static/look.js": ("look.js", JS),
    "/static/vendor/three.module.js": ("vendor/three.module.js", JS),
    "/static/vendor/three.core.js": ("vendor/three.core.js", JS),
    "/static/vendor/OrbitControls.js": ("vendor/OrbitControls.js", JS),
}
IMPORT_MAP = re.compile(r'<script type="importmap">(.*?)</script>', re.S)


class Site:
    """What the server hands out: the town document, and what a selection lights up."""

    def __init__(self, town, select):
        self.town = town
        self.select = select


def import_map_hash(html):
    """The CSP source for the page's one inline script, its import map."""
    found = IMPORT_MAP.search(html)
    if not found:
        raise ValueError("web/index.html has no import map")
    digest = hashlib.sha256(found.group(1).encode("utf-8")).digest()
    return "'sha256-" + base64.b64encode(digest).decode("ascii") + "'"


def policy(html):
    return ("default-src 'self'; "
            f"script-src 'self' {import_map_hash(html)}; "
            "style-src 'self'; img-src 'self' data:; connect-src 'self'; "
            "base-uri 'none'; form-action 'none'; frame-ancestors 'none'")


class Handler(BaseHTTPRequestHandler):
    server_version = "towncode"
    sys_version = ""

    def log_message(self, format, *args):
        pass

    def _send(self, code, body, kind, allow=None):
        self.send_response(code)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Content-Security-Policy", self.server.policy)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cache-Control", "no-store")
        if allow:
            self.send_header("Allow", allow)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, value):
        self._send(200, json.dumps(value, separators=(",", ":")).encode("utf-8"),
                   "application/json")

    def _not_found(self):
        self._send(404, b"not found\n", TEXT)

    def do_GET(self):
        if self.headers.get("Host") not in self.server.hosts:
            return self._send(403, b"forbidden\n", TEXT)
        path, _, query = self.path.partition("?")
        if path == "/town.json":
            return self._json(self.server.site.town)
        if path == "/focus":
            return self._focus(urllib.parse.parse_qs(query))
        entry = STATIC.get(path)
        if entry is None:
            return self._not_found()
        name, kind = entry
        try:
            with open(os.path.join(WEB, name), "rb") as f:
                body = f.read()
        except FileNotFoundError:
            return self._not_found()
        self._send(200, body, kind)

    def _focus(self, query):
        module = query.get("module", [None])[0]
        package = query.get("package", [None])[0]
        answer = None
        if (module is None) != (package is None):
            answer = self.server.site.select(module=module, package=package)
        if answer is None:
            return self._not_found()
        self._json(answer)

    def _refuse(self):
        self._send(405, b"GET only\n", TEXT, allow="GET")

    do_POST = do_PUT = do_DELETE = do_PATCH = do_OPTIONS = do_HEAD = _refuse


class Server(ThreadingHTTPServer):
    daemon_threads = True
    # Two towncode servers must never share a port.
    allow_reuse_port = False

    def __init__(self, site, port):
        with open(os.path.join(WEB, "index.html"), encoding="utf-8") as f:
            self.policy = policy(f.read())
        super().__init__(("127.0.0.1", port), Handler)
        self.site = site
        bound = self.server_address[1]
        self.hosts = {f"127.0.0.1:{bound}", f"localhost:{bound}"}


def make_server(site, port=DEFAULT_PORT):
    try:
        return Server(site, port)
    except OSError as e:
        if e.errno == errno.EADDRINUSE:
            raise SystemExit(f"Port {port} is in use. Try --port 0 to pick any free port.")
        raise


def serve(site, port=DEFAULT_PORT, *, open_browser=True, opener=webbrowser.open):
    """Serve until Ctrl-C, after printing the address and opening it in a browser."""
    server = make_server(site, port)
    url = f"http://127.0.0.1:{server.server_address[1]}/"
    print(f"Town at {url}  (Ctrl-C to stop)", flush=True)
    if open_browser and not opener(url):
        print("Couldn't open a browser. Open the address above.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0
```

- [ ] **Step 5: Run the tests**

Run: `.venv/bin/python -m unittest -q test_webserve`
Expected: OK.

- [ ] **Step 6: Run both suites, then commit**

Run: `.venv/bin/python -m unittest -q && python3 -m unittest -q`
Expected: both OK.

```bash
git add webserve.py web/index.html web/town3d.css test_webserve.py
git commit -m "Serve the 3D town's page on this machine only, GET only, with a strict policy"
```

---

### Task 5: `towncode view --browser`

**Files:**
- Modify: `towncode.py`. Add imports, `_browser(args)`, the start of `_view`, and three `view` arguments in `_parser`.
- Test: `test_towncode.py`

**Interfaces:**
- Consumes:
  - `townjson.town` and `townjson.selection` (Tasks 1–2);
  - `webserve.Site`, `webserve.serve` and `webserve.DEFAULT_PORT` (Task 4);
  - `towncode.run(path) -> (model, rows, plat, out)`;
  - `towncode._session(args, model) -> (changed, sites)`;
  - `towncode.town(model, rows, plat, layout, changed, sites) -> Viewer`.
- Produces:
  - `towncode view PATH --browser [--port N] [--no-open]`, which also takes `view`'s `--layout` and `--session`. It needs no terminal.
  - It calls `webserve.serve(site, port=args.port, open_browser=not args.no_open)`.

- [ ] **Step 1: Write the failing tests**

In `test_towncode.py`, add `import json` to the imports if it's missing. Then add these methods to `TowncodeTest`:

```python
    def browse(self, *flags):
        with mock.patch.object(towncode.webserve, "serve", return_value=0) as serve:
            self.assertEqual(towncode.main(["view", self.root, "--browser", *flags]), 0)
        (site,), options = serve.call_args
        return site, options

    def test_view_browser_serves_the_town_on_the_default_port(self):
        site, options = self.browse()
        self.assertEqual(options, {"port": 8765, "open_browser": True})
        self.assertEqual(site.town["repo"], os.path.basename(os.path.realpath(self.root)))
        self.assertTrue(site.town["buildings"])
        first = site.town["buildings"][0]["path"]
        self.assertEqual(site.select(module=first)["focused"], [first])

    def test_view_browser_takes_a_port_and_can_leave_the_browser_closed(self):
        _, options = self.browse("--port", "0", "--no-open")
        self.assertEqual(options, {"port": 0, "open_browser": False})

    def test_view_browser_needs_no_terminal(self):
        with mock.patch("sys.stdin") as stdin:
            stdin.isatty.return_value = False
            site, _ = self.browse()
        self.assertTrue(site.town["buildings"])

    def test_view_browser_lays_the_town_out_as_the_terminal_does(self):
        def lots(v):
            return {path: [b.x, b.y, b.size] for path, b in v.m.buildings.items()}
        site, _ = self.browse("--layout", "roles")
        model, rows, plat, _ = towncode.run(self.root)
        roles = towncode.town(model, rows, plat, "roles")
        self.assertEqual({b["path"]: b["lot"] for b in site.town["buildings"]}, lots(roles))
        self.assertNotEqual(lots(roles), lots(towncode.town(model, rows, plat)))

    def test_view_browser_sends_no_secrets_and_leaves_the_repo_untouched(self):
        before = untouched.fingerprint(self.root)
        site, _ = self.browse()
        self.assertNotIn("SECRET-TOKEN-123", json.dumps(site.town))
        self.assertEqual(untouched.differences(before, untouched.fingerprint(self.root)), {})
```

- [ ] **Step 2: Run them to see them fail**

Run: `.venv/bin/python -m unittest -q test_towncode`
Expected: the new tests fail with `AttributeError: module 'towncode' has no attribute 'webserve'`, or with argparse rejecting `--browser` (`SystemExit: 2`).

- [ ] **Step 3: Add `--browser`**

In `towncode.py`:

- Add `import townjson` and `import webserve` to the module imports, in alphabetical order with the others.
- Add `from functools import partial` if it isn't imported yet.

Add this function just above `def _view(`:

```python
def _browser(args):
    """Serve the town in 3D on this machine, and open it in the browser."""
    model, rows, plat, _ = run(args.path)
    changed, sites = _session(args, model)
    v = town(model, rows, plat, args.layout, changed, sites)
    name = os.path.basename(os.path.realpath(args.path))
    site = webserve.Site(townjson.town(v.m, v.roads, v.describe, repo=name),
                         partial(townjson.selection, v.m, v.roads, v.model))
    return webserve.serve(site, port=args.port, open_browser=not args.no_open)
```

Make these the first two lines of `_view`'s body, before its terminal check:

```python
    if args.browser:
        return _browser(args)
```

In `_parser`, after `cmd.add_argument("--256", …)` on the `view` command, add:

```python
    cmd.add_argument("--browser", action="store_true",
                     help="show the town in 3D in a browser tab on this machine")
    cmd.add_argument("--port", type=int, default=webserve.DEFAULT_PORT,
                     help=f"port for --browser (default {webserve.DEFAULT_PORT}; 0 picks any free port)")
    cmd.add_argument("--no-open", action="store_true",
                     help="with --browser, print the address without opening a browser")
```

- [ ] **Step 4: Run the tests**

Run: `.venv/bin/python -m unittest -q test_towncode`
Expected: OK.

- [ ] **Step 5: Check it serves for real**

```bash
TOWNCODE_SURVEY_DIR=/tmp/towncode-live/survey .venv/bin/python towncode.py view . --browser --no-open --port 0 > /tmp/towncode-serve.log &
SERVER=$!; sleep 8; cat /tmp/towncode-serve.log
URL=$(grep -o 'http://127.0.0.1:[0-9]*/' /tmp/towncode-serve.log)
curl -s -o /dev/null -w "%{http_code} %{content_type}\n" "${URL}town.json"
curl -s -o /dev/null -w "%{http_code}\n" -H "Host: evil.example" "${URL}town.json"
kill $SERVER; rm -f /tmp/towncode-serve.log
```

Expected: the log line `Town at http://127.0.0.1:…/  (Ctrl-C to stop)`, then `200 application/json`, then `403`.

- [ ] **Step 6: Run both suites, then commit**

Run: `.venv/bin/python -m unittest -q && python3 -m unittest -q`
Expected: both OK.

```bash
git add towncode.py test_towncode.py
git commit -m "Add towncode view --browser: the town served in 3D on this machine"
```

---

### Task 6: The 3D scene

**Files:**
- Create: `web/look.js`, `web/town3d.js`, `smoke_web.py`
- Test: `test_webserve.py`, by adding a check that every static file exists; `smoke_web.py`, run by hand

**Interfaces:**
- Consumes:
  - `/town.json` (Task 1's shape);
  - `/static/look.js` and `/static/town3d.js` from `webserve.STATIC` (Task 4);
  - `towncode view --browser --no-open --port 0` prints `Town at http://127.0.0.1:PORT/` (Tasks 4–5).
- Produces:
  - **`window.town3d`**:
    - `ready: bool`, true after the first frame is drawn;
    - `error: string | null`;
    - `missing: string[]`, the `look.js` keys it needs that aren't defined;
    - `buildings`, `warehouses` and `roads`, the counts drawn;
    - `focused: string[]`;
    - `dimmed: number`;
    - `build_ms`;
    - `fps`;
    - `report() -> object`, a plain copy of the fields above plus `inspector`, the inspector's title or `null`.
  - **In `town3d.js`, for Task 7:**
    - the `view` object, with `doc`, `scene`, `box`, `walls`, `windows`, `fire`, `warehouses` and `roadMesh`;
    - `colour(rgb, k)`;
    - `setRoads(roads)`;
    - `Boxes`, whose items carry an `owner`: `{kind: "building", index, part: "tier"|"roof"|"window"|"weed"}`, or `{kind: "warehouse", index, part: "warehouse"}`;
    - a `wire(renderer, camera)` function that Task 7 fills in.
  - **`smoke_web.py`:** `main(argv) -> int`, `smoke(url, shot, headed) -> (doc, raw, report)`, `report()`, `wait_for(condition, timeout_ms)`, `pw(*args)`, `SmokeFailed`.

- [ ] **Step 1: Check that every static file exists, and see it fail**

Add to `ServerTest` in `test_webserve.py`:

```python
    def test_every_static_file_exists(self):
        for path, (name, _) in webserve.STATIC.items():
            self.assertTrue(os.path.isfile(os.path.join(webserve.WEB, name)), path)
```

Run: `.venv/bin/python -m unittest -q test_webserve`
Expected: FAIL for `/static/town3d.js`.

- [ ] **Step 2: Write the smoke check**

Create `smoke_web.py`:

```python
"""Browser smoke check for the 3D town. Run it by hand, not with unittest:

    python3 smoke_web.py [REPO] [--headed]

It serves REPO (by default a small throwaway repository) with `towncode view --browser`,
loads the page in Playwright through playwright-cli, and checks the scene against /town.json:
every building and road drawn, and no key look.js should define missing. It needs npx, and
leaves a screenshot in /tmp.
"""

import argparse
import base64
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request

import fixture

HERE = os.path.dirname(os.path.abspath(__file__))
PWCLI = os.environ.get("PWCLI") or os.path.expanduser(
    "~/.codex/skills/playwright/scripts/playwright_cli.sh")
SESSION = "towncode-3d-smoke"
FILES = {
    "app/main.py": "import app.loop_a\nimport core.base\n\n\ndef run():\n"
                   "    return core.base.load()\n",
    "app/loop_a.py": "import app.loop_b\n",
    "app/loop_b.py": "import app.loop_a\n",
    "core/base.py": "import yaml\n\n\ndef load():\n    return yaml.safe_load('1')\n",
    "core/broken.py": "def half(:\n",
    "tests/test_base.py": "import core.base\n\n\ndef test_load():\n"
                          "    assert core.base.load() == 1\n",
}


class SmokeFailed(Exception):
    pass


def check(ok, what):
    if not ok:
        raise SmokeFailed(what)


# playwright-cli writes snapshot files into its working folder, so it runs in a scratch one.
WORK = tempfile.mkdtemp(prefix="towncode-smoke-pw-")


def pw(*args, timeout=180):
    done = subprocess.run([PWCLI, "--session", SESSION, *args], capture_output=True, text=True,
                          timeout=timeout, cwd=WORK)
    if done.returncode != 0 or "### Error" in done.stdout:
        raise SmokeFailed(f"playwright-cli {args[0]}: {(done.stdout + done.stderr).strip()[-600:]}")
    return done.stdout


def wait_for(condition, timeout_ms):
    pw("run-code", f"async page => {{ await page.waitForFunction(() => {condition}, null, "
                   f"{{timeout: {timeout_ms}}}); }}")


def report():
    out = pw("eval", "'SMOKE ' + btoa(unescape(encodeURIComponent("
                     "JSON.stringify(window.town3d.report()))))")
    found = re.search(r"SMOKE ([A-Za-z0-9+/=]+)", out)
    check(found, f"no report in: {out.strip()[:300]}")
    return json.loads(base64.b64decode(found.group(1)).decode("utf-8"))


def make_repo():
    root = tempfile.mkdtemp(prefix="towncode-smoke-repo-")
    subprocess.run(["git", "init", "-q", "-b", "main", root], check=True, capture_output=True)
    fixture.write(root, FILES)
    fixture.git(root, "add", "-A")
    fixture.git(root, "commit", "-q", "-m", "smoke")
    return root


def start_server(root, scratch):
    env = dict(os.environ, TOWNCODE_SURVEY_DIR=scratch)
    server = subprocess.Popen(
        [sys.executable, os.path.join(HERE, "towncode.py"), "view", root, "--browser",
         "--no-open", "--port", "0"], stdout=subprocess.PIPE, text=True, env=env)
    for line in server.stdout:
        found = re.search(r"http://127\.0\.0\.1:\d+/", line)
        if found:
            return server, found.group(0)
    server.wait()
    raise SmokeFailed(f"the server stopped before serving (exit {server.returncode})")


def smoke(url, shot, headed):
    raw = urllib.request.urlopen(url + "town.json", timeout=60).read()
    doc = json.loads(raw)
    pw("open", url, *(["--headed"] if headed else []))
    wait_for("window.town3d && (window.town3d.ready || window.town3d.error)", 120000)
    r = report()
    check(r["error"] is None, f"the page failed: {r['error']}")
    check(r["missing"] == [], f"look.js doesn't define {r['missing']}")
    check(r["buildings"] == len(doc["buildings"]),
          f"{r['buildings']} buildings drawn, {len(doc['buildings'])} in town.json")
    check(r["warehouses"] == len(doc["warehouses"]),
          f"{r['warehouses']} warehouses drawn, {len(doc['warehouses'])} in town.json")
    check(r["roads"] == len(doc["roads"]),
          f"{r['roads']} roads drawn, {len(doc['roads'])} in town.json")
    pw("run-code", "async page => { await page.waitForTimeout(2000); "
                   f"await page.screenshot({{path: {json.dumps(shot)}}}); }}")
    return doc, raw, report()


def main(argv=None):
    parser = argparse.ArgumentParser(description="Browser smoke check for the 3D town.")
    parser.add_argument("repo", nargs="?", help="repository to serve (default: a throwaway one)")
    parser.add_argument("--headed", action="store_true", help="show the browser window")
    args = parser.parse_args(argv)
    scratch = tempfile.mkdtemp(prefix="towncode-smoke-survey-")
    root = os.path.abspath(args.repo) if args.repo else make_repo()
    name = os.path.basename(root) if args.repo else "fixture"
    shot = f"/tmp/towncode-3d-smoke-{name}.png"
    server = None
    try:
        server, url = start_server(root, scratch)
        doc, raw, r = smoke(url, shot, args.headed)
        print(f"ok: {r['buildings']} buildings, {r['warehouses']} warehouses, {r['roads']} roads; "
              f"town.json {len(raw) // 1024} KB; built in {r['build_ms']} ms; {r['fps']} fps; {shot}")
        return 0
    except SmokeFailed as e:
        print(f"FAILED: {e}", file=sys.stderr)
        return 1
    finally:
        subprocess.run([PWCLI, "--session", SESSION, "close"], capture_output=True, cwd=WORK,
                       timeout=60)
        if server:
            server.terminate()
            server.wait(timeout=10)
        for path in (scratch, WORK) + (() if args.repo else (root,)):
            shutil.rmtree(path, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 3: Run the smoke check and see it fail**

Run: `python3 smoke_web.py`
Expected: `FAILED: playwright-cli run-code: … TimeoutError …`, because `/static/town3d.js` is a 404, so `window.town3d` never appears. The first run may take a minute while npx fetches `@playwright/cli`.

- [ ] **Step 4: Write `web/look.js`**

```js
// How the 3D town looks: every colour, size and camera setting. This is the designer's file.
// Colours are [r, g, b] from 0 to 255, starting from drawtown's palette. Heights in px are the
// pixel town's; PX_PER_UNIT turns them into tiles. town3d.js names any key it needs that's
// missing here, so a restyle that drops one fails loudly.

// iso.TILE_W / √2: a tower is as tall, for its footprint, as in the pixel town.
export const PX_PER_UNIT = 12 / Math.SQRT2;
export const BACKGROUND = [30, 66, 112];
// How bright each face of every box is, like drawtown's tier walls. +Z is the pixel town's
// left wall and +X its right; the other two only show when you orbit round.
export const FACES = { top: 1.08, bottom: 0.5, pz: 0.95, px: 0.74, nz: 0.86, nx: 0.66 };

export const GROUND = {
  grass: [86, 156, 70], water: [60, 124, 196], quay: [150, 112, 74], dock: [150, 112, 74],
  street: [164, 160, 166], avenue: [148, 144, 149], lot: [178, 142, 98],
  plot: [124, 152, 122], vacant: [170, 134, 92], site: [232, 128, 48],
};
export const TILE_THICKNESS = 0.2;
export const WATER_DROP = 0.12;
export const TREE = {
  trunk: [122, 82, 50], leaves: [[60, 128, 58], [70, 140, 62], [52, 116, 52]],
  trunk_width: 0.14, trunk_height: 0.35, crown: 0.55,
};

export const WALLS = [[222, 208, 182], [210, 200, 186], [218, 196, 170], [200, 192, 180]];
export const ALTERNATE_SHADE = 0.84;
export const AMBER = [236, 160, 40];
export const ROOFS = [[84, 108, 150], [150, 92, 76], [88, 132, 102], [132, 104, 156],
  [160, 138, 84], [80, 132, 140], [152, 102, 124], [112, 112, 124]];
export const ROOF_PX = 2;
export const FOCUS_ROOF = [250, 250, 250];
export const GLASS = { lit: [240, 212, 140], dark: [46, 52, 70], door: [100, 62, 40], board: [138, 98, 62] };
export const WINDOW = {
  width: 0.16, depth: 0.03, spacing: 0.32, margin: 0.12,
  height_px: 2, row_gap_px: 2, bottom_px: 2, top_px: 1,
};
export const WEED = { colour: [70, 120, 52], size: 0.08, count: 14 };
export const FIRE = {
  flames: [[255, 214, 90], [255, 140, 40], [255, 72, 32]], smoke: [92, 92, 100],
  cubes: 12, size: 0.16, speed: 0.6, flame_rise: 0.9, smoke_rise: 2.2,
};

export const WAREHOUSE = { wall: [122, 136, 152], roof: [86, 92, 104], height_px: 9, footprint: 0.9 };

export const ROADS = {
  road: [82, 84, 96], highway: [58, 60, 70], uses: [80, 168, 255], "used by": [236, 96, 196],
  backwards: [232, 112, 36], cycle: [214, 46, 46],
};
export const ROAD_LIFT = 0.012;

// Distances are in tiles; start and max are multiples of the town's longer side.
export const CAMERA = {
  fov: 35, elevation_deg: 35, azimuth_deg: 45, start_distance: 1.2,
  min_distance: 3, max_distance: 3, max_polar_deg: 85,
};
```

- [ ] **Step 5: Write `web/town3d.js`**

```js
// The 3D town: built once from /town.json and orbited with the mouse. Every colour and size
// comes from look.js; Python sends only meanings.

import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import * as LOOK from "./look.js";

const NEEDED = ["PX_PER_UNIT", "BACKGROUND", "FACES", "GROUND", "TILE_THICKNESS", "WATER_DROP",
  "TREE", "WALLS", "ALTERNATE_SHADE", "AMBER", "ROOFS", "ROOF_PX", "FOCUS_ROOF", "GLASS",
  "WINDOW", "WEED", "FIRE", "WAREHOUSE", "ROADS", "ROAD_LIFT", "CAMERA"];
const FIRE = "won't parse";
const ABANDONED = "abandoned";
const HINT = "drag orbit   right-drag pan   scroll zoom";

const $ = (id) => document.getElementById(id);
const px = (p) => p / LOOK.PX_PER_UNIT;
const view = { doc: null, scene: null, box: null, walls: null, windows: null, fire: null,
  warehouses: null, roadMesh: null, selected: null };

const town3d = {
  ready: false, error: null, missing: NEEDED.filter((key) => !(key in LOOK)),
  buildings: 0, warehouses: 0, roads: 0, focused: [], dimmed: 0, build_ms: 0, fps: 0,
};
town3d.report = () => ({
  ready: town3d.ready, error: town3d.error, missing: [...town3d.missing],
  buildings: town3d.buildings, warehouses: town3d.warehouses, roads: town3d.roads,
  focused: [...town3d.focused], dimmed: town3d.dimmed,
  inspector: $("inspector").hidden ? null : $("inspect-title").textContent,
  build_ms: town3d.build_ms, fps: Math.round(town3d.fps),
});
window.town3d = town3d;

// k darkens or brightens as drawtown's shade() does on sRGB values.
function colour(rgb, k = 1) {
  return new THREE.Color().setRGB(rgb[0] / 255, rgb[1] / 255, rgb[2] / 255, THREE.SRGBColorSpace)
    .multiplyScalar(Math.pow(k, 2.2));
}

function pick(list, x, y) {
  return list[(((x * 73856093) ^ (y * 19349663)) >>> 0) % list.length];
}

function show(text) {
  const box = $("message");
  box.textContent = text;
  box.hidden = false;
}

// One unit box whose faces are shaded like the pixel town's walls, so the scene needs no lights.
function shadedBox() {
  const box = new THREE.BoxGeometry(1, 1, 1);
  const F = LOOK.FACES;
  const faces = [F.px, F.nx, F.top, F.bottom, F.pz, F.nz];
  const shades = new Float32Array(24 * 3);
  for (let v = 0; v < 24; v++) shades.fill(Math.pow(faces[Math.floor(v / 4)], 2.2), v * 3, v * 3 + 3);
  box.setAttribute("color", new THREE.BufferAttribute(shades, 3));
  return box;
}

// Boxes drawn as one instanced mesh; each keeps its colour and the thing it belongs to.
class Boxes {
  constructor() {
    this.items = [];
  }

  add(x, y, z, sx, sy, sz, c, owner = null) {
    this.items.push({ x, y, z, sx, sy, sz, c, owner });
  }

  mesh(box) {
    const n = this.items.length;
    const mesh = new THREE.InstancedMesh(box, new THREE.MeshBasicMaterial({ vertexColors: true }),
      Math.max(1, n));
    mesh.count = n;
    const m = new THREE.Matrix4(), q = new THREE.Quaternion();
    const p = new THREE.Vector3(), s = new THREE.Vector3();
    this.items.forEach((b, i) => {
      mesh.setMatrixAt(i, m.compose(p.set(b.x, b.y, b.z), q, s.set(b.sx, b.sy, b.sz)));
      mesh.setColorAt(i, b.c);
    });
    if (n === 0) mesh.setColorAt(0, new THREE.Color());
    mesh.userData.boxes = this;
    return mesh;
  }
}

function ground(doc) {
  const boxes = new Boxes();
  const t = LOOK.TILE_THICKNESS;
  doc.tiles.forEach((row, z) => {
    for (let x = 0; x < row.length; x++) {
      const kind = doc.legend[row[x]];
      const top = kind === "water" ? -LOOK.WATER_DROP : 0;
      const k = 1 - 0.03 * ((x * 7 + z * 13) % 3);
      boxes.add(x + 0.5, top - t / 2, z + 0.5, 1, t, 1, colour(LOOK.GROUND[kind], k));
    }
  });
  return boxes;
}

function trees(doc) {
  const T = LOOK.TREE, trunks = new Boxes(), crowns = new Boxes();
  for (const [x, z] of doc.trees) {
    trunks.add(x + 0.5, T.trunk_height / 2, z + 0.5, T.trunk_width, T.trunk_height,
      T.trunk_width, colour(T.trunk));
    crowns.add(x + 0.5, T.trunk_height + T.crown / 2, z + 0.5, T.crown, T.crown, T.crown,
      colour(pick(T.leaves, x, z)));
  }
  return [trunks, crowns];
}

function addWindows(boxes, cx, cz, side, tier, glass, owner) {
  const W = LOOK.WINDOW;
  const usable = side - 2 * W.margin;
  if (usable < W.width) return;
  const cols = 1 + Math.floor((usable - W.width) / W.spacing);
  const h = px(W.height_px), out = side / 2 + W.depth / 2;
  for (let k = tier.z0 + W.bottom_px; k + W.height_px <= tier.z1 - W.top_px;
    k += W.height_px + W.row_gap_px) {
    const y = px(k + W.height_px / 2);
    for (let i = 0; i < cols; i++) {
      const along = (i - (cols - 1) / 2) * W.spacing;
      boxes.add(cx + out, y, cz + along, W.depth, h, W.width, glass, owner);
      boxes.add(cx - out, y, cz + along, W.depth, h, W.width, glass, owner);
      boxes.add(cx + along, y, cz + out, W.width, h, W.depth, glass, owner);
      boxes.add(cx + along, y, cz - out, W.width, h, W.depth, glass, owner);
    }
  }
}

function addWeeds(boxes, cx, cz, side, owner) {
  const W = LOOK.WEED, r = side / 2 + W.size / 2;
  for (let i = 0; i < W.count; i++) {
    const a = (i / W.count) * Math.PI * 2;
    const dx = Math.cos(a), dz = Math.sin(a), edge = Math.max(Math.abs(dx), Math.abs(dz));
    const h = W.size * (1 + (i % 3));
    boxes.add(cx + (dx / edge) * r, h / 2, cz + (dz / edge) * r, W.size, h, W.size,
      colour(W.colour), owner);
  }
}

function buildings(doc) {
  const walls = new Boxes(), windows = new Boxes(), fires = [];
  const roofs = Object.fromEntries(doc.districts.map((d) => [d.name, d.roof]));
  doc.buildings.forEach((b, index) => {
    const [x, z, size] = b.lot;
    const cx = x + size / 2, cz = z + size / 2;
    const wall = pick(LOOK.WALLS, x, z), glass = colour(LOOK.GLASS[b.glass]);
    b.tiers.forEach((t, i) => {
      const side = t.half / doc.half_w;
      const c = t.amber ? colour(LOOK.AMBER) : colour(wall, i % 2 ? LOOK.ALTERNATE_SHADE : 1);
      walls.add(cx, px(t.z0 + t.z1) / 2, cz, side, px(t.z1 - t.z0), side, c,
        { kind: "building", index, part: "tier" });
      addWindows(windows, cx, cz, side, t, glass, { kind: "building", index, part: "window" });
    });
    const top = b.tiers[b.tiers.length - 1], side = top.half / doc.half_w;
    const roof = LOOK.ROOFS[(roofs[b.district] ?? 0) % LOOK.ROOFS.length];
    walls.add(cx, px(top.z1 + LOOK.ROOF_PX / 2), cz, side, px(LOOK.ROOF_PX), side, colour(roof),
      { kind: "building", index, part: "roof" });
    if (b.problems.includes(FIRE)) fires.push({ x: cx, y: px(top.z1 + LOOK.ROOF_PX), z: cz, side });
    if (b.problems.includes(ABANDONED)) {
      addWeeds(walls, cx, cz, b.tiers[0].half / doc.half_w, { kind: "building", index, part: "weed" });
    }
  });
  return { walls, windows, fires };
}

function warehouses(doc) {
  const W = LOOK.WAREHOUSE, boxes = new Boxes();
  doc.warehouses.forEach((w, index) => {
    const [x, z, size] = w.lot;
    const side = size * W.footprint, h = px(W.height_px);
    const owner = { kind: "warehouse", index, part: "warehouse" };
    boxes.add(x + size / 2, h / 2, z + size / 2, side, h, side, colour(W.wall), owner);
    boxes.add(x + size / 2, h + px(LOOK.ROOF_PX) / 2, z + size / 2, side, px(LOOK.ROOF_PX), side,
      colour(W.roof), owner);
  });
  return boxes;
}

function roadBoxes(roads) {
  const boxes = new Boxes();
  for (const r of roads) {
    const c = colour(LOOK.ROADS[r.kind]);
    const w = 2 * r.half, h = LOOK.ROAD_LIFT, y = LOOK.ROAD_LIFT * (r.layer + 1);
    r.tiles.forEach(([x, z], i) => {
      boxes.add(x + 0.5, y, z + 0.5, w, h, w, c);
      const next = r.tiles[i + 1];
      if (!next) return;
      const dx = next[0] - x, dz = next[1] - z;
      boxes.add(x + 0.5 + dx / 2, y, z + 0.5 + dz / 2, dx ? 1 : w, h, dz ? 1 : w, c);
    });
  }
  return boxes;
}

function setRoads(roads) {
  if (view.roadMesh) {
    view.scene.remove(view.roadMesh);
    view.roadMesh.material.dispose();
    view.roadMesh.dispose();
  }
  view.roadMesh = roadBoxes(roads).mesh(view.box);
  view.scene.add(view.roadMesh);
  town3d.roads = roads.length;
}

function fireMesh(fires, box) {
  const boxes = new Boxes();
  for (const f of fires) {
    for (let k = 0; k < LOOK.FIRE.cubes; k++) boxes.add(f.x, f.y, f.z, 0, 0, 0, colour(LOOK.FIRE.smoke));
  }
  const mesh = boxes.mesh(box);
  mesh.frustumCulled = false;
  mesh.userData.fires = fires;
  return mesh;
}

function burn(mesh, t) {
  const F = LOOK.FIRE, fires = mesh.userData.fires;
  if (!fires.length) return;
  const m = new THREE.Matrix4(), q = new THREE.Quaternion();
  const p = new THREE.Vector3(), s = new THREE.Vector3();
  fires.forEach((f, j) => {
    for (let k = 0; k < F.cubes; k++) {
      const phase = (t * F.speed + k / F.cubes) % 1;
      const smoke = k % 3 === 2, turn = k * 2.4 + t;
      const r = f.side * 0.35 * (1 - phase * 0.5);
      const size = F.size * (smoke ? 1 + phase : 1 - phase * 0.6);
      const rise = phase * (smoke ? F.smoke_rise : F.flame_rise);
      const i = j * F.cubes + k;
      mesh.setMatrixAt(i, m.compose(p.set(f.x + Math.cos(turn) * r, f.y + rise + size / 2,
        f.z + Math.sin(turn) * r), q, s.set(size, size, size)));
      const flame = F.flames[Math.min(F.flames.length - 1, Math.floor(phase * F.flames.length))];
      mesh.setColorAt(i, colour(smoke ? F.smoke : flame));
    }
  });
  mesh.instanceMatrix.needsUpdate = true;
  mesh.instanceColor.needsUpdate = true;
}

function build(doc) {
  view.scene = new THREE.Scene();
  view.scene.background = colour(LOOK.BACKGROUND);
  view.box = shadedBox();
  view.scene.add(ground(doc).mesh(view.box));
  for (const part of trees(doc)) view.scene.add(part.mesh(view.box));
  const town = buildings(doc);
  view.walls = town.walls.mesh(view.box);
  view.windows = town.windows.mesh(view.box);
  view.fire = fireMesh(town.fires, view.box);
  view.warehouses = warehouses(doc).mesh(view.box);
  view.scene.add(view.walls, view.windows, view.fire, view.warehouses);
  setRoads(doc.roads);
}

function makeCamera(doc, canvas) {
  const C = LOOK.CAMERA, [w, h] = doc.size, span = Math.max(w, h);
  const camera = new THREE.PerspectiveCamera(C.fov, window.innerWidth / window.innerHeight, 0.1,
    span * 10);
  const elevation = THREE.MathUtils.degToRad(C.elevation_deg);
  const azimuth = THREE.MathUtils.degToRad(C.azimuth_deg);
  const d = span * C.start_distance;
  camera.position.set(w / 2 + d * Math.cos(elevation) * Math.sin(azimuth), d * Math.sin(elevation),
    h / 2 + d * Math.cos(elevation) * Math.cos(azimuth));
  const controls = new OrbitControls(camera, canvas);
  controls.target.set(w / 2, 0, h / 2);
  controls.enableDamping = true;
  controls.screenSpacePanning = false;
  controls.minDistance = C.min_distance;
  controls.maxDistance = span * C.max_distance;
  controls.maxPolarAngle = THREE.MathUtils.degToRad(C.max_polar_deg);
  controls.addEventListener("change", () => {
    const t = controls.target;
    t.set(THREE.MathUtils.clamp(t.x, 0, w), 0, THREE.MathUtils.clamp(t.z, 0, h));
  });
  controls.update();
  return { camera, controls };
}

function checkKinds(doc) {
  const wanted = [...Object.values(doc.legend).map((k) => ["GROUND", k]),
    ...doc.buildings.map((b) => ["GLASS", b.glass]),
    ...["road", "highway", "uses", "used by", "backwards", "cycle"].map((k) => ["ROADS", k])];
  for (const [table, key] of wanted) {
    const name = `${table}.${key}`;
    if (!(key in LOOK[table]) && !town3d.missing.includes(name)) town3d.missing.push(name);
  }
}

// Clicking, the inspector and focus are wired here (Task 7).
function wire(renderer, camera) {}

function run(renderer, camera, controls) {
  let frames = 0, since = performance.now();
  renderer.setAnimationLoop((now) => {
    controls.update();
    burn(view.fire, now / 1000);
    renderer.render(view.scene, camera);
    town3d.ready = true;
    frames += 1;
    if (now - since >= 1000) {
      town3d.fps = (frames * 1000) / (now - since);
      frames = 0;
      since = now;
    }
  });
}

async function start() {
  const began = performance.now();
  if (town3d.missing.length) throw new Error(`look.js doesn't define ${town3d.missing.join(", ")}`);
  const res = await fetch("/town.json");
  if (!res.ok) throw new Error(`Couldn't load the town (${res.status}).`);
  const doc = await res.json();
  view.doc = doc;
  checkKinds(doc);
  if (town3d.missing.length) throw new Error(`look.js doesn't define ${town3d.missing.join(", ")}`);
  $("line1").textContent = `${doc.repo}: ${doc.buildings.length} buildings, ` +
    `${doc.warehouses.length} warehouses`;
  $("line3").textContent = HINT;
  let renderer;
  try {
    renderer = new THREE.WebGLRenderer({ antialias: true });
  } catch {
    town3d.error = "no webgl";
    show("WebGL isn't available in this browser, so the 3D town can't be drawn.");
    return;
  }
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.setSize(window.innerWidth, window.innerHeight);
  document.body.appendChild(renderer.domElement);
  build(doc);
  town3d.buildings = doc.buildings.length;
  town3d.warehouses = doc.warehouses.length;
  const { camera, controls } = makeCamera(doc, renderer.domElement);
  window.addEventListener("resize", () => {
    camera.aspect = window.innerWidth / window.innerHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(window.innerWidth, window.innerHeight);
  });
  wire(renderer, camera);
  town3d.build_ms = Math.round(performance.now() - began);
  run(renderer, camera, controls);
}

start().catch((e) => {
  town3d.error = e.message || String(e);
  show(town3d.error);
});
```

- [ ] **Step 6: Syntax-check both files**

Run: `node --check web/look.js && node --check web/town3d.js && echo syntax ok`
Expected: `syntax ok`.

- [ ] **Step 7: Run the unit tests and the smoke check**

Run: `.venv/bin/python -m unittest -q test_webserve && python3 smoke_web.py`
Expected: OK, then a line like `ok: 4 buildings, 1 warehouses, 2 roads; town.json 3 KB; built in … ms; … fps; /tmp/towncode-3d-smoke-fixture.png`. The counts depend on the fixture's layout.

Look at the screenshot with the Read tool. It should show:
- a green island with a harbor;
- cake buildings with roofs and windows;
- a red cycle road;
- flames on the building that won't parse.

A blank or single-colour image means the scene didn't draw. Fix that before going on.

- [ ] **Step 8: Run both suites, then commit**

Run: `.venv/bin/python -m unittest -q && python3 -m unittest -q`
Expected: both OK.

```bash
git add web/look.js web/town3d.js smoke_web.py test_webserve.py
git commit -m "Build the 3D town in the browser from town.json, with every colour in look.js"
```

---

### Task 7: Click to inspect and focus

**Files:**
- Modify: `web/town3d.js`. Replace the empty `wire`, add `recolour`, `inspect`, `select`, `clear` and `pickable`, and change `HINT`.
- Modify: `smoke_web.py`, by adding the selection checks to `smoke`.

**Interfaces:**
- Consumes:
  - `view`, `colour`, `setRoads` and the `Boxes` owners (Task 6);
  - `GET /focus?module=…` or `GET /focus?package=…` returns `{"focused", "dim", "roads"}` (Tasks 2 and 4).
- Produces:
  - `window.town3d.select(path) -> Promise`, the same path as clicking that building;
  - Escape and clicking empty ground clear the selection;
  - `report().focused`, `report().dimmed` and `report().inspector` follow the selection.

- [ ] **Step 1: Add the selection checks to the smoke test, and see them fail**

In `smoke_web.py`'s `smoke()`, replace this line:

```python
    pw("run-code", "async page => { await page.waitForTimeout(2000); "
```

and the line after it with:

```python
    target = next((b for b in doc["buildings"] if b["path"] in
                   {p for r in doc["roads"] for p in (r["from"], r["to"])}), doc["buildings"][0])
    pw("eval", f"window.town3d.select({json.dumps(target['path'])}).then(() => 'selected')")
    wait_for("window.town3d.report().focused.length === 1", 15000)
    r = report()
    check(r["focused"] == [target["path"]], f"focused {r['focused']}, wanted {target['path']}")
    check(r["inspector"] == target["inspect"]["title"],
          f"the inspector says {r['inspector']!r}, wanted {target['inspect']['title']!r}")
    check(r["dimmed"] > 0 or len(doc["buildings"]) == 1, "nothing dimmed around the focus")
    pw("run-code", "async page => { await page.waitForTimeout(1500); await page.screenshot("
                   f"{{path: {json.dumps(shot.replace('.png', '-focus.png'))}}}); }}")
    pw("press", "Escape")
    wait_for("window.town3d.report().focused.length === 0", 15000)
    r = report()
    check(r["inspector"] is None and r["dimmed"] == 0, "Escape left the focus on")
    check(r["roads"] == len(doc["roads"]), "Escape didn't bring the town's roads back")
    pw("run-code", "async page => { await page.waitForTimeout(2000); "
                   f"await page.screenshot({{path: {json.dumps(shot)}}}); }}")
```

Run: `python3 smoke_web.py`
Expected: `FAILED: playwright-cli eval: … town3d.select is not a function`.

- [ ] **Step 2: Wire picking, the inspector and focus**

In `web/town3d.js`, change `HINT` to:

```js
const HINT = "drag orbit   right-drag pan   scroll zoom   click inspect   Esc clear";
```

Replace these two lines:

```js
// Clicking, the inspector and focus are wired here (Task 7).
function wire(renderer, camera) {}
```

with:

```js
// A building's boxes take its brightness from the focus; the focused building gets the white roof.
function recolour(dim, focused) {
  const c = new THREE.Color();
  for (const mesh of [view.walls, view.windows]) {
    mesh.userData.boxes.items.forEach((b, i) => {
      const path = view.doc.buildings[b.owner.index].path;
      if (b.owner.part === "roof" && focused.has(path)) {
        mesh.setColorAt(i, colour(LOOK.FOCUS_ROOF));
        return;
      }
      const k = dim && path in dim ? dim[path] : 1;
      mesh.setColorAt(i, c.copy(b.c).multiplyScalar(Math.pow(k, 2.2)));
    });
    if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
  }
  town3d.dimmed = dim ? Object.values(dim).filter((k) => k < 1).length : 0;
}

// Repository text only ever reaches the page as textContent.
function inspect(info) {
  $("inspect-title").textContent = info.title;
  $("inspect-facts").textContent = info.facts;
  $("inspect-reasons").replaceChildren(...info.reasons.map((reason) => {
    const item = document.createElement("li");
    item.textContent = reason;
    return item;
  }));
  $("inspector").hidden = false;
}

function clear() {
  view.selected = null;
  $("inspector").hidden = true;
  recolour(null, new Set());
  setRoads(view.doc.roads);
  town3d.focused = [];
}

async function select(owner) {
  if (!owner) return clear();
  const building = owner.kind === "building";
  const thing = building ? view.doc.buildings[owner.index] : view.doc.warehouses[owner.index];
  view.selected = thing;
  inspect(thing.inspect);
  const query = building ? `module=${encodeURIComponent(thing.path)}`
    : `package=${encodeURIComponent(thing.package)}`;
  const res = await fetch(`/focus?${query}`);
  if (!res.ok || view.selected !== thing) return;
  const answer = await res.json();
  if (view.selected !== thing) return;
  recolour(building ? answer.dim : null, new Set(answer.focused));
  setRoads(answer.roads);
  town3d.focused = answer.focused;
}

// A click is a press and release that barely moved; a drag belongs to the camera.
function pickable(canvas, camera, meshes) {
  const ray = new THREE.Raycaster(), at = new THREE.Vector2();
  let down = null;
  canvas.addEventListener("pointerdown", (e) => {
    down = e.button === 0 ? [e.clientX, e.clientY] : null;
  });
  canvas.addEventListener("pointerup", (e) => {
    if (!down || Math.hypot(e.clientX - down[0], e.clientY - down[1]) > 5) return;
    down = null;
    const r = canvas.getBoundingClientRect();
    at.set(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
    ray.setFromCamera(at, camera);
    const hit = ray.intersectObjects(meshes, false).find((h) => h.instanceId !== undefined);
    select(hit ? hit.object.userData.boxes.items[hit.instanceId].owner : null);
  });
}

function wire(renderer, camera) {
  pickable(renderer.domElement, camera, [view.walls, view.windows, view.warehouses]);
  window.addEventListener("keydown", (e) => {
    if (e.key === "Escape") clear();
  });
  town3d.select = (path) => {
    const index = view.doc.buildings.findIndex((b) => b.path === path);
    return select(index < 0 ? null : { kind: "building", index });
  };
}
```

- [ ] **Step 3: Syntax-check, then run the smoke check**

Run: `node --check web/town3d.js && python3 smoke_web.py`
Expected: an `ok: …` line.

Look at both screenshots:
- `/tmp/towncode-3d-smoke-fixture-focus.png` should show the target building with a white roof and blue or pink roads, with everything else darker;
- `/tmp/towncode-3d-smoke-fixture.png` should show the town back to normal.

- [ ] **Step 4: Run both suites, then commit**

Run: `.venv/bin/python -m unittest -q && python3 -m unittest -q`
Expected: both OK.

```bash
git add web/town3d.js smoke_web.py
git commit -m "Click a 3D building to see the terminal inspector and its focus roads"
```

---

### Task 8: README, and a look at real towns

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Document it**

In `README.md`, add this subsection directly after the section documenting `towncode view`:

````markdown
### In the browser

```
towncode view PATH --browser [--port N] [--no-open] [--layout roles] [--session [TRANSCRIPT]]
```

This serves the town in 3D at <http://127.0.0.1:8765> and opens it in your browser. `--port 0`
picks any free port, and `--no-open` prints the address instead of opening it. `--layout` and
`--session` work as they do in the terminal view; a session's new files are orange site tiles. Drag to orbit,
right-drag to pan, and scroll to zoom.

Click a building to see what the terminal inspector says about it. The roads it uses turn blue,
the roads that use it turn pink, its roof turns white, and the rest of the town dims. `Esc`
clears the selection.

The server answers this machine only and never changes the repository. Every colour and size is
in `web/look.js`. `python3 smoke_web.py [REPO]` is a browser check you run by hand; it needs
`npx`.
````

- [ ] **Step 2: Smoke-check two real towns**

```bash
python3 smoke_web.py ~/game-web
python3 smoke_web.py .
```

Expected: an `ok: …` line for each. Then:
- Record each one's building and road counts, `town.json` size, build time and fps in the task report. Headless fps is only indicative.
- `game-web`'s `town.json` should be under 1 MB. If it isn't, report the size; don't change the format.
- Look at `/tmp/towncode-3d-smoke-game-web.png` and its `-focus` partner. Check that the districts, roads and harbor read clearly.

- [ ] **Step 3: Run both suites, then commit**

Run: `.venv/bin/python -m unittest -q && python3 -m unittest -q`
Expected: both OK.

```bash
git add README.md
git commit -m "Document towncode view --browser and the 3D smoke check"
```

- [ ] **Step 4: Hand back for review**

Report to the user:
- the commits on `watch-3d`;
- both test-suite results;
- the smoke numbers from Step 2;
- the screenshot paths.

Don't push. Pushing and opening a PR need the user's go-ahead. Plan 2 (`LiveTown`, `/events`, Clawds, merges) is written next, against this code.
