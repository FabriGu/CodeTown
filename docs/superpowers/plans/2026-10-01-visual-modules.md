# Plan 3 (designer): visual rules as modules the renderer calls

Status: proposed. From the designer, for the engineer and their agent. Builds on the proposal
`specs/2026-10-01-floors-roles-and-ownership-proposal.md` and on this branch,
`towncode-universal`, which supersedes `main`'s prototype.

## Goal

Turn what the mock-up (`mock_roles.py`) settled into small, tested modules: what a building
looks like, which buildings matter right now, and where each module belongs. The engineer's
renderer calls them. The designer never edits the engineer's files, and the engineer never has to re-derive
a rule from a picture.

## Global constraints

- **No edits to the engineer's files:** `drawtown`, `viewer`, `towncode`, `render`, `term`,
  `townmap`, `plat`, `roads`, `survey`, `model`, `langkit`, `langs` and every `lang_*`.
  Where a module needs a hook, this plan names it, and the engineer writes it.
- **Pure modules.** Each new module takes the model, a `Building`, or plain numbers, and
  returns plain data. None reads the repository, draws, or keeps state.
- **Dependency-free.** Standard library only. Pillow stays in the mock.
- **One meaning per property**, as in the site plan. New colours: blue = "uses", pink =
  "used by", white roof = the focus. Amber stays "a function of 100+ lines".
- **The mock imports the modules**, so what the designer approves in a picture is what the
  renderer gets.

## The modules

### 1. `focus.py`: what matters right now

```python
def neighbours(model, module) -> tuple[set, set]
    """(modules it imports, modules that import it), within the repository."""

def blast_radius(model, changed) -> dict[str, int]
    """Every module that imports any changed module, directly or through others, with its
    distance: 0 for the changed ones, 1 for direct users, and so on."""

def changed_by(session_steps, model) -> set[str]
    """Modules a session changed, from session.py's steps: successful edits, writes and
    deletes only, mapped to module ids. Unknown paths are ignored."""

def select(model, module) -> Focus
def changed(model, modules) -> Focus
    """Focus(kind, distance, roads): each module's distance from the focus, and the
    (colour, src, dst) roads to draw: "uses"/"used by" for a selection; for a blast
    radius, each road one step closer to a changed module."""

def dim(focus, module) -> float
    """1.0 for the focus and its direct neighbours, 0.72 further out, 0.38 for the rest."""
```

Tests: a fixture graph with a chain, a fan-in and a cycle; `blast_radius` stops at cycles;
`changed_by` drops failed edits and paths outside the model.

### 2. `cake.py`: function floors and their windows

```python
@dataclass(frozen=True)
class Tier:
    half: int        # half width in pixels, 2 more than a multiple of 4
    z0: int          # bottom, in pixels above the ground
    z1: int
    amber: bool      # a function of LONG_FUNCTION (100) lines or more

def tiers(functions, size, module_complexity) -> list[Tier]
    """Biggest function at the bottom, each tier never wider than the one under it."""

def windows(half, z0, z1) -> list[tuple[str, list[tuple[int, int]]]]
    """(wall, pixels) per window, relative to the building's centre column and ground row,
    centred with equal corner margins; none when a window doesn't fit."""

def wall_columns(half)
    """(wall, column, distance from the corner): paint walls on the columns windows use."""
```

The "whole or not at all" rule stays with the renderer: a window is painted only if every
pixel is still its own wall after the scene is drawn. Tests: the invariants already checked
for lots of 1–4 tiles, widths 0.35–1.0 and heights 2–59 px.

### 3. `roles.py`: where a module belongs

```python
def roles(model, declared_doors=()) -> dict[str, str]
    """door, street, foundation, side (scripts only), script, named or island, per building."""

def script_groups(model, roles) -> dict[str, list[str]]
    """Scripts grouped by the helper script they share; the rest under "standalone"."""
```

Language-neutral: front doors come from `declared_doors` (Python's `[project.scripts]`), else
the most tested entry point, then the one reaching most; the rest comes from `model.edges`.
What no import reaches is named (`mentioned` or `public`: probably loaded by name) or an
island (nothing uses it: the dead-code list). Tests on fixtures, then calibration on `small-pipeline`, `codetown`, and one
TypeScript repository once the grammars are installed.

## Hooks for the engineer

| Module | Where | What |
| --- | --- | --- |
| `focus` | `roads.Roads` | route `Focus.roads` pairs with the existing `_module_road`; keep cycle roads always on |
| `focus` | `drawtown.TownScene` | take a `dim` callable, shade each building's pixels by it; white roof for the focus |
| `focus` | `viewer` / `towncode` | `--session [TRANSCRIPT]` on `view` and `snapshot`, using `session.load` and `focus.changed_by` |
| `cake` | `townmap.Building` | a `functions` tuple of `(name, lines, complexity)`; `floors` stays the height count |
| `cake` | `drawtown` | draw a cake building once, at its front tile's depth, from `cake.tiers` and `cake.windows` |
| `roles` | `plat` / `townmap` | a `--layout roles` option, compared side by side before any default changes |

`Building.functions` needs `Module.functions`, filled by each adapter. Python can fill it from
`pyscan`'s tree; the other eight adapters each add a `functions` fact in their own file.
That's in the engineer's survey core, so it's their call when.

## Work order

1. **`focus.py`** with tests; the mock's selection and blast-radius views switch to it. The
   mock gains `--session`, so the designer can see a real agent session's blast radius.
2. **`cake.py`** with tests; the mock's floors and windows switch to it.
3. **`roles.py`** with tests; the mock's layout switches to it, and it's calibrated on more
   repositories.
4. **A watch mock.** A flat, whole-town minimap PNG re-rendered while an agent works, from
   its transcript. It informs a later `towncode watch`, which is the engineer's.

Each step is one PR into `towncode-universal`, touching only that step's new files, its
test file and `mock_roles.py`.

## Not in this plan

- Any change to the engineer's files (see the hooks table).
- v3's point-and-click, `tower.py`, effects and agent runs.
- Runtime probes on roads. A later, opt-in command for repositories you own.

## Questions for the engineer

1. Should PRs keep targeting `towncode-universal` until it merges to `main`?
2. Are the hook signatures above what the renderer wants?
3. When can `Module.functions` land, and should adapters fill it in parallel, like the
   language work?
4. The proposal's interface named the new field `Building.floors`, but `Building.floors` is
   already the height count. This plan calls it `functions` instead. OK?
