# CodeTown: function floors, a layout by role, and who owns what (proposal)

## Summary

From the designer, for the engineer and their agent. This is a proposal, not a decision: nothing here
changes a file listed in the point-and-click spec (v3,
`2026-10-01-codetown-point-and-click-design.md`, on `point-and-click-spec`).

The town today shows how many modules there are and which top-level folder each sits in.
At one look it doesn't show where the code starts, what the core is, what needs splitting or
what is stale. This proposes four changes to what a building *is* and *where it goes*, keeps
every drawing and animation decision with the engineer, and names the one place the two meet: the
`Building` record `townmap.py` hands to the renderer.

1. **Function floors.** Height stays complexity. Each floor is one function.
2. **A layout by role.** Front door, main street, foundations, scripts, islands, computed from
   the survey, instead of one district per top-level folder.
3. **Age as paint.** Modules fade by how long since their last commit, relative to the rest of
   the repository.
4. **Roads only when asked.** A selected building's imports both ways, and the blast radius of
   a file the agent changed. No always-on import roads.

A mock-up (`mock_roles.py`) renders all four from real survey data. It is a
throwaway exploration and changes none of the town's modules.

## The one-look test

The overview should answer five questions, and nothing more. Problems stay as alerts on top.

1. **Front door:** where does it start?
2. **Main street:** what is the main path from the front door?
3. **Foundations:** what does everything lean on?
4. **Scripts:** what hangs off the side?
5. **Alive or stale:** what is current, and what hasn't been touched?

## Evidence

Measured on `small-pipeline` (a small Python repository: 28 modules, 10 tests, 38 Python files)
and on this repository, on 2026-10-01.

- **One district per folder hides the structure.** `small-pipeline` renders as two equal
  neighbourhoods, `src` and `scripts`, of near-identical 1×1 and 2×2 houses. About half the
  frame is grass and trees. Nothing is labelled at town zoom.
- **The real front door isn't read.** `pyproject.toml` declares one command,
  `small-pipeline = "small_pipeline.pipeline:app"`. The survey doesn't read it, so 16 modules get
  the same entry gate.
- **An entry gate is wrong.** `scripts/common.py` is imported by 6 scripts but gets a
  gate, because `pyscan._is_top_level_call` treats any top-level call as "run directly".
- **The structure is in the graph.** `pipeline.py` imports 7 modules. `validate.py` has 17
  importers and imports nothing. 13 scripts are imported by nothing. Eight of them were last
  committed on 2026-09-08 and not since; `pipeline.py` on 2026-09-22.
- **The CLI never reaches four library modules.** Only scripts use them, and neither the town
  nor the text report shows this.
- **Functions separate code that needs splitting.** Biggest function per module: six are 100
  lines or more (`pipeline.generate` 147, four script `main()`s 104–138, `validate.check_all`
  123). The next is 90. Module complexity alone doesn't show this: `pipeline.py` has complexity
  57 spread over 15 functions; `scripts/report.py` has 36, with 138 of its 163 lines in `main`.

The mock (`uv run --with pillow python3 mock_roles.py PATH OUT.png`) is the source of these
role and function numbers. Snapshots are ignored by git, so the before and after images for
`small-pipeline` are attached to the PR rather than committed.

## 1. Function floors

Height stays complexity, as today. The building is split into floors, one per top-level
function and method, stacked like a wedding cake: the biggest function (by lines) at the bottom,
the smallest at the top, ties broken by complexity, then name. Each floor is never wider than
the one under it, so nothing overhangs.

| Property | Encodes | Rule in the mock |
| --- | --- | --- |
| Floor thickness | That function's complexity | `max(2, round(complexity × 0.7))` px |
| Floor width | Its size next to the module's biggest function | `0.35 + 0.65 × lines ÷ biggest` of the footprint, centred |
| Amber floor | A long function, the first thing to split | 100 lines or more |
| Floor line | Where one function ends | 1 px darker band under each floor |
| Roof | Top-level folder | District colour, as today |

- **Function facts.** Per function: name, lines (`end_lineno − lineno + 1`), and complexity
  (1 + the same decision count `pyscan` uses, over that function's nodes). Nested functions
  count toward their parent. A module with no functions is one floor from its module
  complexity.
- **Shapes read without a legend.** A gentle taper of many floors reads as a well-factored
  module. A wide, thick base under a thin spire reads as one oversized function with small
  helpers. One block reads as a monolith.
- **The threshold.** 100 lines matched a natural break in `small-pipeline` (147, 138, 134, 132,
  123, 104, then 90). A share rule (one function of 60+ lines holding over half the module) made
  12 of 28 buildings amber, which is too many to be loud.
- **Principle 7 holds.** Every floor is a measurement from the parsed file.

### Windows on floors

The agreed look is the stepped, wedding-cake stack. Today's windows sit on a
fixed per-tile grid (`drawtown.facade`: columns 1–3 of each tile, rows by `FLOOR`), which can't
follow floors of any width or thickness. On floors, windows are laid out per floor, from that
floor's own walls, and keep the site plan's meaning: lit = tested, dark = untested, boarded =
abandoned. `mock_roles.py` implements the rules (`half_width`, `slots`, `windows`, `glaze`).

- **Whole pixels.** A floor's half width is snapped down to `4n + 2` px, never wider than the
  lot. Walls step one pixel every two columns, so each wall is laid out in two-column steps, and
  `4n + 2` gives an odd step count, which is what lets windows sit exactly centred.
- **Fit, then centre.** Windows are one step (2 px) wide and 2 px tall, with a one-step gap.
  As many as fit go in, with one step clear of each corner, centred. Rows work the same way:
  2 px clear of the floor line below, 1 px under the floor or roof above, a 2 px gap between rows.
  Both walls get the same layout, mirrored about the front corner.
- **None rather than a squeezed one.** A floor too thin or too narrow for one window gets none.
  The minimum floor (2 px) has none; a floor needs complexity ≥ 7 for a row of windows.
- **Whole or not at all.** Drawing records which floor and wall owns every pixel. Windows are
  painted last, and only when every pixel of the window still belongs to its own wall. A
  building in front hides a window entirely instead of cutting it.
- **Checked.** For lots of 1–4 tiles, floor widths 0.35–1.0 and thicknesses 2–59 px, every
  window is 4 pixels, inside its wall's margins, and has equal margins at both corners.

### Where it meets the janky tower

v3's `tower.py` generates the tower's geometry from the module id, so its blocks are
decoration. If the tower's blocks were the module's function floors, the tower would show which
functions make it a tower, and the refactor's dust cloud would end in a building whose floors
come from the new survey. Proposed: `tower.py` takes the floor list instead of a hash. This is
the engineer's call; it is the only change this proposal asks of a v3 file.

## 2. A layout by role

Districts by folder become a secondary property (roof colour). Placement comes from role:

| Role | Detected by | Confidence |
| --- | --- | --- |
| Front door | Modules named in `pyproject.toml` `[project.scripts]` | Declared |
| Main street | Modules reachable through imports from the front door | Inferred from imports |
| Foundations | 3+ importers, and import nothing in the repository | Inferred |
| Scripts only | Library modules reached from scripts but not from the front door | Inferred |
| Scripts | Entry modules not reached from the front door | Inferred |
| Script groups | Grouped by the script helper they import (a script other scripts import) | Inferred |
| Islands | Not reached from the front door or any script | Inferred, possibly dead |

When no front door is declared, the mock uses the entry module that reaches the most modules.

Placement in the mock, back to front: foundations and scripts-only modules in the back row; a
lane; the front door then the main street modules, ordered by dependency row, front door first;
a two-tile main street; script groups across the street, ordered by the main street modules
they use; islands on their own patch of land across the water.

- **Stability.** Role decides a module's plot only when it first gets one, as `Plat.update`
  does today. A module that changes role keeps its plot until a re-layout is asked for. Its
  change of role shows as paint or a label, not a move.
- **Inferred looks inferred.** The front door is declared; the other roles are guesses from
  imports. They need a visibly different treatment from verified facts. How is a drawing
  question for the engineer.
- **Import order is not run order.** The main street's order is the dependency order. A later
  runtime trace (opt-in, on repositories you own) could confirm or reorder it.

## 3. Age as paint

- **Rule.** Rank modules by last commit time. The newer half is untouched; the older half
  fades toward grey, the oldest most, up to 65%.
- **Relative, not absolute.** Fading after a fixed number of days greyed out most of
  `small-pipeline`, because nearly everything is one to three weeks old.
- **Problems stay loud.** Amber floors and problem effects never fade.
- **Stale is not dead.** The label is "untouched since …", never "unused".

## 4. Roads only when asked

The layout already shows the normal flow, from scripts at the front, through the main street,
to the foundations at the back. So with nothing selected, no import roads are drawn: the
streets are layout, not information. Roads appear in two moments, the ones where an engineer
needs connections.

| Moment | Roads | Everything else |
| --- | --- | --- |
| A building is selected | Blue to what it imports, pink from what imports it, door to door along the streets | Dimmed; the selected building gets a white roof |
| The agent changed a file | Pink from everything that imports it, directly or through others, each road one step closer to the changed file | Direct users bright, indirect ones half-dimmed, the rest dark |

- **Why not always-on.** In `small-pipeline`, 29 of 62 imports end at the foundations, so drawing
  every import buries the map. Two always-on variants were tried and dropped:
  - one road per pair of groups (8 roads), with or without roads into the foundations;
  - an orange "backwards" road for an import against the front-to-back flow.

  Both needed a legend, and the orange flagged a rule of the layout, not a problem in the code.
- **Dead code needs no road.** "Nothing imports it" belongs on the building itself: boarded
  windows, no annex.
- **The blast radius answers "what could this change break".** With `convert.py` changed,
  8 modules use it directly and 9 more through them; the other 9 of the town's 27 buildings
  can't be affected. That is the
  connection question behind the agent-change priority, and the same roads are where a later
  runtime probe would light up.
- **Import loops stay loud.** A cycle is a real problem, so cycle roads stay always on, as alerts.
  District highways go, because the role layout has no districts.
- **Flat is the minimap.** Tall buildings hide roads and the focused building behind them; with
  every building as a low block, both moments read at a glance. v3's show-through covers the
  tall view.

`mock_roles.py` implements both (`focus_of`, `plan_roads`, `walk`):
`mock_roles.py PATH OUT.png select:pipeline.py` or `changed:convert.py`, optionally `flat`.

## Who owns what

The split follows the v3 file table: the engineer owns how things are drawn and animated; the
designer owns what a building is made of and where it goes.

| Owner | Area | Files |
| --- | --- | --- |
| Engineer | Drawing, animation, input, labels, the viewer, agent runs | Everything in v3's "Where it lands in the code": `term`, `render`, `drawtown`, `viewer`, `towncode`, `tower`, `effects`, `labels`, `intro`, `measure`, `agent`, `cursor_agent` |
| Designer | Function facts, roles, plot placement, age, agent sessions run outside the town | `pyscan.py`, `model.py`, `plat.py`, `townmap.py`, `session.py` |

### The interface

`townmap.Building` gains three fields. Nothing else in `drawtown.py` has to change until
the engineer chooses to draw them.

| Field | Type | Meaning |
| --- | --- | --- |
| `floors` | tuple of `(name, lines, complexity)` | Top-level functions and methods, biggest first (bottom floor first) |
| `role` | str | `door`, `street`, `foundation`, `scripts-only`, `script`, `island` |
| `age_rank` | float, 0 to 1 | 0 is the most recently committed module, 1 the oldest |

`Module` gains `functions` (the same tuples) so they are saved in `model.json`. Reading the
front door needs `pyproject.toml`, which the survey already reads as text.

## Also in this PR: `session.py`

`python3 session.py PATH [TRANSCRIPT]` reports what an agent did in a repository: the files it
read and changed, edits made without reading the file first, and the commands it ran. It reads
the newest Claude Code (`~/.claude/projects/…`) or Cursor (`~/.cursor/projects/…/agent-transcripts`)
transcript for the repository, with its subagents, and saves `session.json` next to the survey.

- **Names only.** Paths and the first line of each command are kept, never file contents or
  edit text.
- **Checked, not assumed.** Claude Code transcripts have times and results: a failed edit is
  not counted, and tracked files changed on disk during the session without an edit tool are
  listed ("a command, you, or something else"). Cursor transcripts have neither; an edit to a
  file that doesn't exist afterwards counts as failed, and the report says commands can't be
  checked.
- **Tested** on fixtures (9 tests) and on real Claude Code and Cursor runs given the same
  four-step task.
- **How it relates to `agent.py`.** v3's `agent.py` is Clawd's own runs in the sandbox.
  `session.py` is for agents run outside the town, in a normal terminal. They are
  complementary. Its step kinds are `read`, `edit`, `write`, `delete` and `command`; if
  `agent.py`'s events can use the same names, the town can draw both the same way.

## Found along the way

Small things in the survey, for the engineer to take or leave:

- **A false "notes left".** `pyscan.NOTE` matches its own source line, so surveying this
  repository reports a TODO in `pyscan.py` that isn't one.
- **Python version.** The README says 3.8+; `str | None` in `model.py`, `pyscan.py` and
  `problems.py` needs 3.10.
- **Entry gates.** `_is_top_level_call` makes any module with a top-level call an entry point
  (see `scripts/common.py` above).
- **"Never run code."** The site plan's rule is about surveying the monorepo. A later runtime trace
  would be a separate, opt-in command on repositories you own, writing outside them, so the
  rule could say it applies to `survey` and `view`.

## Against the universal survey spec

Notes on `2026-10-01-universal-survey-design.md`, added after it merged:

- **Functions for every language.** `langkit.Facts` has no function list, so every
  non-Python building would be one block. Proposed: `functions: tuple = ()` of
  `(name, lines, complexity)` on `Facts`, filled by each adapter (tree-sitter gives function
  nodes and their line spans directly) and left empty at floor depth. It is cheap to add before
  nine language agents write adapters, and costly after.
- **`model.py` has two claimants.** Universal core changes `model.py`, `problems.py`,
  `survey.py` and `drawtown.py`, and isn't assigned. Whoever takes core should own `model.py`;
  the `functions` field above can ride along with core's other `Module` fields.
- **Plan 2 isn't pushed.** The designer's side (`plat.py`, `townmap.py`) waits for `towncode-render`
  on GitHub, so it isn't built on the prototype in `main`.

## Questions for the engineer

1. Should `tower.py` build its blocks from function floors?
2. Is the `Building` interface above enough, or does the renderer need more?
3. How should inferred roles look different from declared ones?
4. Should `agent.py` events share `session.py`'s step kinds?
5. Should the folder-by-district layout stay as an option, or go?
6. Can `towncode-render` be pushed, so work on placement starts from Plan 2?
7. Roads: can on-demand roads (section 4) replace always-on highways? Should `roads.py`, which
   decides which roads exist and where they run, move to the designer's side, with drawing staying in
   `drawtown`?

## In this PR

| File | What |
| --- | --- |
| `docs/superpowers/specs/2026-10-01-floors-roles-and-ownership-proposal.md` | This proposal |
| `mock_roles.py` | The mock-up. Needs Pillow for its labels only (`uv run --with pillow`). Not part of towncode |
| `session.py`, `test_session.py` | Agent session report, and its tests |

Not in this PR: any change to `pyscan.py`, `model.py`, `plat.py` or `townmap.py`. Those follow
once the interface is agreed.
