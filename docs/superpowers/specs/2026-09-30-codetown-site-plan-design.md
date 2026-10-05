# CodeTown: a site plan for codebases (v2)

## Summary

One fixed set of rules, the **Town Code**, turns any codebase into a small
isometric town. Modules are buildings, dependencies are roads, and top-level
folders are districts. Problems show up as things anyone can read at a glance:
a crumbling hotspot, a boarded-up building nobody visits, a tower overshadowing
its street. You point at a building, send Clawd, and watch him walk the roads,
read, and rebuild. The first town is a large Python monorepo (`~/repos/big-monorepo`).

## Principles

1. **One visual property, one meaning.** Grass and trees only grow where there's no code.
2. **Structure is quiet, problems are loud.** A few bright colors are reserved for problems only.
3. **Nothing moves unless the code moves.** Placement is saved, so your mental map stays valid.
4. **Unknown isn't healthy.** Code the tool can't read yet gets its own "unsurveyed" look.
5. **Playful, never misleading.** Every symbol can be selected and explained by the fact behind it.
6. **Headed toward self-evident form.** Eventually a building's shape itself should show
   what's wrong with it, so no legend is needed.

## How it works

The Surveyor reads the repo and writes a model (JSON). A layout step decides where
everything goes, that becomes the scene, and the existing terminal renderer draws
it. Clawd's activity comes in from the Cursor SDK and is drawn into the same scene.

The first Surveyor is static only:

- **Python modules** are parsed, never imported or run: imports, exported names,
  lines of code, complexity, TODO/FIXME markers, and whether the file parses.
- **git history**, read-only: commits per file over the last 90 days, and renames.
- **Everything else** (JavaScript, shell scripts) is listed as unsurveyed plots.
- **Vendored folders** (any folder named `vendor`) are left out of the town entirely.

## Town Code: structure

| Code | Town |
| --- | --- |
| Repository | The town (an island) |
| Top-level folder | District, with its own roof color |
| Module (the unit other code imports) | Building. Footprint from lines of code (1×1 up to 4×4 tiles); height from complexity (up to 6 floors) |
| Exported names | Doors on street-facing walls |
| Import | Road; wider means more references |
| All imports between two districts | Highway |
| Module meant to be run directly | Gate at the town's front edge |
| Outside package | Warehouse in the harbor, behind the town |
| Tests that import a module | Annex attached to that building |
| Commits in the last 90 days | Worn paving around the building |

A deep module is a big building with few doors, without any extra rule.

## Town Code: layout

- **Rows by dependency layer.** Foundations at the back, entry points at the front,
  outside packages in a harbor behind everything. Imports should point backward, so a
  road running forward means something low-level reaching up into something high-level.
- **Order and streets.** Alphabetical within rows. One-tile streets between buildings,
  30% of plots left free for growth.
- **Saved placement, stored outside the repo.** New modules take the nearest free plot,
  deleted ones leave vacant lots, renamed ones keep their plot. Rearranging the whole
  town only happens when you ask for it.
- **Which roads are drawn.** Highways and problem roads always, plus every road into or
  out of the selected building. The rest stay hidden.

## Problems (the playful set)

| Problem | Detected when | What you see |
| --- | --- | --- |
| Won't parse | The file has a syntax error | Fire, with smoke above the skyline |
| Import cycle | Modules import each other in a loop | A red loop of road, with a roundabout |
| Backwards road | A foundation module imports something in front of it | A road running forward, with a no-entry sign |
| Hotspot | Top 5% by churn times complexity: busy and complicated | Cracked, shimmering paving |
| Tower | Far above the size or complexity cap | A tower casting a shadow on its neighbors |
| Abandoned | Imported by nothing, and not an entry point | Boarded windows, weeds, no road in |
| Untested | No test imports it | Dark windows, no annex |
| All doors | The interface is nearly as big as the code behind it | A front wall covered in doors |
| Notes left | TODO or FIXME markers | A small yellow sign |
| Unsurveyed | Not Python, so not readable yet | A gray outline on its plot |

Fire can be seen from anywhere: its smoke clears the skyline, and an arrow at the
screen edge points to it when it's off-screen. Everything else shows when you're
zoomed in. `n` and `p` jump between problems, worst first.

## Views and controls

Two zoom levels: the whole town, and a single district. You are the camera and a
cursor; Clawd is the agent. WASD or the arrow keys pan, `+` and `-` zoom, Enter opens
the inspector, `d` sends Clawd, `f` follows him, and `b` flips between before and after.

## Clawd (Cursor SDK)

Select a building or a problem, press `d`, and accept or edit a suggested one-line
task. This starts a local agent through the Python Cursor SDK, working in a scratch
copy at `~/codetown/.sandbox/<repo>`, never in the original.

| Agent does | Clawd does |
| --- | --- |
| Reads a file | Walks the roads there and peers in the windows |
| Searches | Stands in a plaza with a spyglass while matching buildings blink |
| Edits a file | Puts up scaffolding and hammers |
| Creates a file | Builds on a free plot |
| Deletes a file | Demolishes the building, leaving a vacant lot |
| Runs a command | Goes to Town Hall |
| Thinks | Stops, with a thought bubble |
| Finishes | Raises a flag |

Clawd sticks to roads when he can; cutting across grass means the agent jumped to code
the current file doesn't depend on. Buildings he changes that you didn't point him at
are marked. After the run, the scratch copy is surveyed again and before/after shows
what changed. What happens to the change next is your call. The API key comes from
`CURSOR_API_KEY` and is never printed or stored.

## The monorepo stays untouched

- Only tracked files are read (`git ls-files`); untracked and ignored files are never opened.
- Code is parsed, never imported, run or tested.
- git is only used for read commands, with optional locks off so it doesn't even refresh its index.
- Nothing is written inside the repo. The saved layout and caches live in `~/codetown/.survey/`.
- The town shows names and numbers, never file contents.
- Clawd's edits happen in a separate copy.
- A test proves it: surveying a test repo leaves every file, including git's internal
  ones, byte-for-byte identical with the same modification times. The same check runs
  against the monorepo after its first survey.

## Where this is headed: self-evident inefficiency

If you need the legend to see the problem, the form isn't doing its job yet. Later,
geometry generated from the code replaces the symbols: deep nesting as a maze of rooms,
copy-paste as identical house fronts, pass-through modules as bare corridors, long
dependency chains as roads that take the long way around, oversized modules that streets
bend around, unreachable code as rooms with no doors, and (with runtime traces) couriers
running back and forth between the same two buildings.

## Milestones

1. **Monorepo site plan:** Surveyor, layout, rendering, problems, inspector, read-only test.
   - Plan 1: the survey and its text report, calibrated against the monorepo.
   - Plan 2: the rendered town, controls and inspector.
2. **Clawd on the Cursor SDK:** dispatch, live walking, scratch copy, before/after.
3. **Self-evident forms:** floor plans, and generated forms replacing symbols.

## Success

- The same code always produces the same town, and adding one module never moves another.
- The read-only test passes on the monorepo.
- You look at the monorepo's town and, within a few minutes, agree the loud spots are real
  sore spots, and nothing is loud without reason.
