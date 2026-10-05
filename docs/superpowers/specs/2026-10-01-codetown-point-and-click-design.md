# CodeTown: point and click, labels and live work (v3)

## Summary

This brings what the showcase video shows into `towncode view`. The video is a separate,
locally rendered file (`~/codetown-video/out/codetown.mp4`) and is not in this
repository. The town drops into place when it opens. Buildings carry their names,
problems carry loud labels, and an arrow at the screen edge points to a fire you can't see.
You point and click: Clawd walks where you click, and clicking a problem's action sends him to
fix it. While he works, a badge above the building shows real numbers from his edits: the lines
of a broken file the parser can't reach, falling to zero; a tower's line count, shrinking;
`+added −removed` for everything he touched. Fires go out under a water spray. Towers vanish
into a cartoon dust cloud and come out as the smaller building the new survey says they are.

This updates the site-plan spec (`2026-09-30-codetown-site-plan-design.md`) and carries out
its milestone 2, Clawd on the Cursor SDK. Where the two disagree, this spec wins. The
differences are listed at the end.

## Scope

**In:** everything inside the terminal window in the video. That means the start-up lines and
the town dropping in, point and click, a camera that glides, name and problem labels, the edge
arrow, live badges, the janky tower, the upgraded fire, the water spray, the dust cloud, the
rebuilt building, Clawd's hops and confetti, and the status lines.

**Out:**
- **The recording itself:** the macOS desktop, dock, window dragging and zooms.
- **Presentation extras:** the panel of keys that light up, the caption card, the end card and
  sound.
- **Clawd's text reactions:** the "!", "!!", "?" and "Yippee!" bubbles, and the comic words.
  His body language stays: the startled jump, the slump, the celebration hops and confetti.
- **Applying Clawd's change to the real repository.** This is unchanged from the site plan.

## Principle added to the site plan's six

7. **Every number is a measurement.** Badges show only values computed from files on disk. A
   number may count from one measurement to the next over at most 0.6 s, and it always settles
   on the measured value.

## Where it lands in the code

| Module | New or changed | Responsibility |
| --- | --- | --- |
| `term.py` | changed | Mouse reporting on and off, click and wheel parsing, text overlays composed into rows |
| `render.py` | changed | `Framebuffer` keeps a pick map: which thing drew each pixel |
| `drawtown.py` | changed | Records pick owners, applies intro drop offsets, draws Clawd and effects in depth order, flower boxes |
| `tower.py` | new | The janky tower's geometry, generated from the module id |
| `effects.py` | new | Fire, smoke and steam, water spray, dust cloud, poof, sparkles, confetti |
| `labels.py` | new | Which labels show, their text and style, placement without overlaps, the edge arrow |
| `intro.py` | new | Start-up timing: when each tile, building and Clawd lands |
| `viewer.py` | changed | Clawd instead of the cursor, clicks, selection, actions, camera, runs, status lines |
| `measure.py` | new | Live metrics: unreadable lines, tower progress, diff stats |
| `agent.py` | new | Events, the run, the replay source, the sandbox, the file observer, the untouched guard |
| `cursor_agent.py` | new | The Cursor SDK source, imported only when a real run starts |
| `towncode.py` | changed | Start-up lines, `--no-intro`, `--replay FILE` |

The product stays dependency-free. The Cursor SDK is the one optional import, and it is needed
only to send Clawd for real.

## 1. Start-up

`towncode view PATH` prints these lines on the normal screen as the survey runs, so they stay
in the scrollback after you quit:

```
Surveying ~/code/shop (read-only) ...
shop: 16 modules, 9 tests, 2 unsurveyed files, 31 roads, 4 outside packages
2 problems, worst first: won't parse (payments/checkout.py), tower (utils/helpers.py)
Opening the town ...
```

The second line is the first line of today's `survey` report. The third line lists up to three
problems and then "and N more", or says "No problems found."

Then the alternate screen opens on an empty sea and the town drops in:

- **Clawd's start.** Clawd starts on the frontmost avenue, at the walkable tile nearest the
  town's centre column. The camera starts on him. The wave of drops spreads from his tile.
- **Tiles.** Each tile starts at `0.15 + d × 1.6` seconds, plus 0–0.18 s of jitter from
  `hash2(tx, ty, 5)`. Here `d` is the tile's screen distance from the origin, with the vertical
  axis weighted 1.6, divided by the largest such distance in the town. A tile falls from 26 px
  above over 0.42 s, easing out with a small overshoot. Its skirt falls with it.
- **Buildings.** A building uses its centre tile's start plus 0.12 s and falls from 48 px. A
  tower adds 0.15 s and falls from 60 px.
- **Clawd.** Clawd drops 0.1 s after the last tile lands. He falls for 0.45 s and squashes for
  0.1 s on landing. Labels and the status lines appear when he lands.
- **Length.** The intro lasts about 3 s whatever the town's size, because distance is
  normalized. Any click or key ends it at once.
- **Turning it off.** `--no-intro` skips it, and `snapshot` never plays it.

If the town has a fire, status line 1 announces it as soon as Clawd lands (see section 6).

## 2. Point and click

### Mouse input

On entering the viewer, `term.Terminal` turns on button reporting with SGR coordinates
(`ESC[?1000h ESC[?1006h`). It turns both off on exit, including after an error.
`term.parse_keys` also returns mouse events:

- `ESC[<0;COL;ROWM` is a left press. The viewer acts on presses and ignores releases.
- Wheel codes 64 and 65 zoom in and out.
- Other buttons and modified clicks are ignored.
- A sequence split across two reads is kept until it is complete.
- An `ESC` with nothing after it in the same read is the Esc key. Today's parser skips it as
  the start of a sequence.

Cell to pixel: column `c` and row `r`, both 1-based, become pixel `((c − 1) // 2, r − 1)`.
Rows below the framebuffer belong to the status lines.

A click is tested against the status-line items first, then the labels, then the pick map.

### Pick map

`Framebuffer` gains an `owner` grid parallel to `rows`. `TownScene` sets the current owner
before each drawable:

- **Blocks:** a `Building` or `Warehouse` owns its own pixels. Annexes, the tower's props and
  every effect belong to their building. A prop belongs to the building whose front it stands
  on.
- **Ground:** `("tile", tx, ty)`.
- **Clawd:** `"clawd"`.

Dithered ghost pixels don't change owners. At district and town zoom, the whole-town drawing's
pick map is cropped like its pixels and sampled at the centre pixel of each factor × factor
block, never averaged.

### What a click does

| Clicked | Result |
| --- | --- |
| Ground, street or water | Clawd walks to the walkable tile nearest the click |
| Building, warehouse, plot or vacant lot | Selected. Clawd walks to its front, its label expands, and status line 2 shows its facts |
| A label | Same as clicking its building |
| The action in a label | Starts that action. Clawd walks to the building first if he isn't there |
| The edge arrow | Selects the fire. The camera turns toward it and Clawd walks there |
| A status-line item | Cancel, Before, After or Quit |
| Clawd | Nothing |

During a run, clicks still select and inspect, but Clawd doesn't move. Clicking another action
shows "Clawd is busy. Cancel first."

### Clawd in the town

- **Movement.** Clawd is a `game.Actor`. He moves 0.16 s per tile along `roads.route` over
  street, avenue and quay, and faces the way he walks.
- **Clicking a building.** The target is the building's `front()`. If that tile isn't
  walkable, the target is the nearest walkable tile to the door.
- **Unreachable targets.** If the target can't be reached, Clawd goes to the reachable tile
  closest to it in a straight line. Ties break by `(y, x)`.
- **New clicks.** A new click replaces the path from the next tile on.
- **Behind buildings.** Clawd shows through as the dithered silhouette from the game's
  renderer.

### Keyboard fallback

| Key | Action |
| --- | --- |
| Arrows or WASD | Step Clawd one tile |
| Enter or space | Start the selected building's action if it has one. Otherwise select the building Clawd faces |
| `n` / `p` | Select the next or previous problem, worst first, and walk there |
| `+` / `-` | Zoom |
| Esc | Cancel the run |
| `b` | Flip between before and after |
| `q` | Quit |

### Camera

The camera keeps a focus point in whole-town pixels and eases toward its target every frame:
`focus += (target − focus) × (1 − e^(−6.5·dt))`. The target is:

- Clawd, while he walks.
- The selected building's roof centre, once he arrives.
- During a run, the target building, raised so its top and its badge are in view. This uses
  today's `lift` plus the badge's height.

`n`, `p` and the edge arrow move the target, not the focus, so the view glides. District zoom
crops around the focus. Town zoom stays centred on the whole town.

## 3. Labels

### Text over pixels

Labels are real terminal characters with a background colour, laid over the pixel art:

- **Position.** A label at pixel `(x, y)` starts at column `2x + 1` on row `y + 1`. A
  half-pixel offset adds one column.
- **Half-pixel edges.** A label that ends halfway through a pixel fills that pixel's remaining
  column with a single block in the pixel's colour.
- **Redrawing.** `Screen.frame(fb, status, overlays)` diffs overlays along with pixels, so a
  row is redrawn when only its labels change.
- **No emoji.** Their width differs between terminals. Icons are single-width characters:
  `●` district, `▲` fire, `◆` warning, `✓` fixed, `▸` action, `■` diff squares, and the
  arrows `← ↑ → ↓ ↖ ↗ ↘ ↙`.

### Label kinds

| Label | Example | Style |
| --- | --- | --- |
| Name | `● api/routes.py` | Light text on dark grey. The dot is in the district's roof colour |
| Fire | `▲ payments/checkout.py  won't parse` | White on deep red |
| Loud problem | `◆ utils/helpers.py  tower: 3,412 lines` | Dark text on amber. Used for tower, import cycle, backwards road and hotspot |
| Selected | Its name or problem label, plus `  ▸ Put out fire` when it has an action | As its kind. The action is in bold |
| Edge arrow | `← ▲ checkout.py` | Fire style |
| District | `payments` | Roof colour on dark grey |
| Badge | See section 5 | |

Module paths longer than 28 characters are shortened from the left with `…`.

### Which labels show

- **Street zoom:**
  - The selected building's label.
  - Fire and loud-problem labels for buildings on screen.
  - Name labels for up to 8 buildings within 7 tiles of the camera focus, nearest first.
  - Quiet problems (abandoned, untested, all doors, notes left, unsurveyed) show only in the
    selected label, so loud stays meaningful.
- **District zoom:** fire and loud-problem labels, up to 6, plus district names.
- **Town zoom:** district names and fires.
- **During a run:** the badge, the selected label and any edge arrow to another fire. Name
  labels step aside.

### Placement

Each label is anchored one row above its building's roof, centred on it. Labels are placed in
this priority order: badge, selected, fire, loud problems, names (nearest first), districts.

A label that would overlap one already placed tries up to two rows higher, and is otherwise
dropped. Cells where Clawd is drawn count as taken. Labels are clamped inside the screen.

### Edge arrow

When a fire's roof centre is outside the view at street zoom, a fire chip sits on the screen
edge. It is placed where the line from the view centre to the fire crosses the edge, inset one
row and four columns. Its arrow is the closest of the eight directions. It replaces
`viewer._mark_fires` at street zoom. The flame marks drawn inside district and town views stay.

## 4. Buildings

### The janky tower (`tower.py`)

The tower replaces today's plain nine-floor box for buildings with the tower problem.

- **Segments.** The nine floors are drawn as 5–7 stacked segments of one or two floors each.
  Each segment has its own footprint, inset or shifted by up to 0.45 tile, and its own wall
  colour from a fixed palette of eight mismatched colours. A dark outline makes every segment
  read as a separate box.
- **Lean.** Segments shift sideways more the higher they are. The top's total lean is
  `6 + 12 × overage` pixels, where
  `overage = min(1, max(loc / TOWER_LOC, complexity / TOWER_COMPLEXITY) − 1)`. So a tower just
  over the limit leans a little, and one at twice the limit leans fully.
- **Props.** Props are chosen per segment, each used at most once: braces, a bay window on
  crooked props, a jogging drainpipe, cracks and scaffold planks. The top carries a bent
  antenna with a blinking light.
- **Stable shape.** Every choice comes from `zlib.crc32` of the module id, never Python's
  `hash()`, which changes between runs. The same module always gets the same tower.
- **Roof colour.** The top segment's roof keeps the district colour (one property, one
  meaning). The mismatch is in the walls.
- **Unchanged.** The shadow on the neighbours stays. Every tower pixel is owned by its
  building.

### Fire

`draw_fire`'s flame columns are replaced by the video's fire:

- Five swaying flame tongues on a bed of embers.
- Windows that glow and flicker.
- Smoke puffs that lighten as they rise.
- Embers drifting up.

One level, from 0 to 1, scales the flame height, smoke density and window glow. Idle fires are
at level 1. As a fire dies down its smoke turns to white steam.

### Flower boxes

Buildings Clawd fixed in this session get flower boxes under their windows. That is their only
meaning, and the inspector says "fixed by Clawd this session". Roof colours never change,
because they mean district.

## 5. Clawd's work

### Actions

| Problem | Action | Task sent to the agent |
| --- | --- | --- |
| Won't parse | Put out fire | Make `{path}` parse again. Fix only the syntax error at line `{line}`. Change nothing else. |
| Tower | Refactor | Refactor `{path}` (`{loc}` lines, complexity `{complexity}`) into smaller modules with the same behaviour. Keep every name it exports importable from `{path}`. |

Other problem kinds have no action yet. A building with both problems offers Put out fire
first, because a file that doesn't parse can't be measured. The task is sent as written: in
this version it can't be edited.

### Events (`agent.py`)

Every animation and number reads from one stream of events:

| Event | Fields | Comes from |
| --- | --- | --- |
| `start` | action, target, task | The run |
| `read` | path | An agent message |
| `search` | query | An agent message |
| `edit`, `create`, `delete` | path | The file observer |
| `command` | text | An agent message |
| `finish` | summary | The agent's result |
| `fail` | reason | An agent error, Cancel, or the untouched guard |

Events carry no file contents: measurement reads the sandbox. File events come only from the
file observer, never from what the agent says it did. So the numbers stay true even if a
message is missing or wrong.

**File observer.** After every agent message, and every 0.5 s while a run is active, the
observer compares the sandbox's files (path, size, modification time) with the previous look.
It emits `edit`, `create` or `delete` for each change.

### Sources

**Replay (`--replay FILE`).** The file is JSON lines, for example
`{"at": 1.2, "type": "read", "path": "core/models.py"}`. Edit and create lines also carry the
new file content. The replay writes that content into the sandbox, and the file observer picks
it up like any other change.

Replays are hand-written fixtures for test repositories. Real runs are never recorded, because
a recording would hold file contents, and the site plan says the town shows names and numbers,
never file contents.

**Cursor SDK (`cursor_agent.py`).**
- **Starting.** It creates `Agent.create(local=LocalAgentOptions(cwd=sandbox))` and calls
  `agent.send(task)`.
- **Streaming.** It reads `run.messages()` on a worker thread into a queue the viewer drains
  every frame.
- **Ending.** `run.cancel()` serves Cancel, and `run.wait()` gives the result.
- **Mapping messages.** Phase 4 maps the SDK's message types to `read`, `search` and `command`
  against the SDK documentation. Unknown messages are ignored.
- **Missing SDK.** `cursor_sdk` is imported only when a real run starts. If it is missing, the
  action shows "Install cursor-sdk to send Clawd" and nothing else changes.
- **Key.** The API key comes from `CURSOR_API_KEY`. It is never printed or stored.

### Sandbox and guard

- **Location.** The sandbox lives at `.sandbox/<repo>-<tag>/` next to `towncode.py`, or under
  `$TOWNCODE_SANDBOX_DIR`. The tag is computed the same way as for `.survey`. A path inside the
  repository is refused.
- **Creation.** It is created at the first run of a viewer session by copying the repository's
  tracked files (`git ls-files`, read-only, as the survey does). Nothing that writes inside the
  original's `.git` is used, so no worktrees.
- **Reuse.** Later runs in the same session reuse it, so a refactor builds on a fire put out
  earlier. The next session replaces it.
- **Guard.** Before and after every run, `untouched.fingerprint` checks the original
  repository. Any difference fails the run loudly: "The original repository changed during the
  run: N paths." The agent works in the sandbox, and this is checked, not assumed.

### Live measurement (`measure.py`)

These values are recomputed after every file event:

- **Diff.** The sum, over the files touched in this run, of lines added and removed between the
  original file and the sandbox file, computed with `difflib`. A created file counts against
  empty, and a deleted file counts as all removed. It is shown as `+71 −1,142 ■■■■■`: five
  squares split green and red in proportion, like GitHub, and grey when both counts are 0.
- **Unreadable lines (fire).** The non-blank, non-comment lines from the syntax error's line to
  the end of the file, from `pyscan.scan` on the sandbox file. This is the same counting rule
  as `loc`. It is 0 once the file parses. Fire level = unreadable now ÷ unreadable at the
  start.
- **Tower progress.** The target's lines and complexity from `pyscan.scan`. The tower is done
  when both are under `TOWER_LOC` and `TOWER_COMPLEXITY`.

### Badges

| Action | During the run | Fixed | Not fixed |
| --- | --- | --- | --- |
| Put out fire | `checkout.py  212 lines unreadable` (red, counting down) | `✓ checkout.py parses  +3 −1` (green) | `checkout.py  still won't parse` (red) |
| Refactor | `helpers.py  +71 −1,142 ■■■■■` | `✓ helpers.py  3,412 → 640 lines` (green) | `helpers.py  still a tower: 2,310 lines` (amber) |

- **Placement.** The badge sits above the target building. During a refactor it sits above the
  dust cloud, and it moves down onto the new roof after the poof.
- **Verdict.** On the verdict the badge shows in bright colours for 0.2 s.
- **Afterwards.** It stays for 6 s after the run ends, then the building's usual label returns.

### Animation (`effects.py`)

| Moment | What you see |
| --- | --- |
| `start` | Clawd walks to the target's front. The first time he reaches a burning building he does a startled jump: a hop with a squash, and no text |
| `read` or `search` of another file | Clawd walks the roads to that building, faces it and leans in. He cuts across grass when no road joins the two buildings, as in the site plan |
| File events on the target, Put out fire | Clawd faces the fire and sprays an arc of water. Steam puffs rise where it lands, embers fly, and the flames follow the fire level |
| File events on the target, Refactor | A dust cloud covers the building: spinning puffs with a dark outline, Clawd's arms and legs poking out, debris in the tower's wall colours, and small stars. It stays up while events keep coming and for 1.5 s after the last one |
| File events on other files | Counted in the diff. Clawd stays at the target |
| `command` | Clawd stands and taps his foot |
| No events for 2 s | Clawd idles, looking left and right |
| `finish`, fixed | Fire: the flames drop to nothing, a burst of sparkles, the steam clears. Refactor: the cloud bursts into fading puffs, the building is redrawn from the new survey, and new modules drop onto their plots with the intro's drop. Then Clawd hops three times (15, 8 and 4 px) and confetti pops from both sides |
| `finish` not fixed, or `fail` | Clawd slumps, squashed and looking down. The fire returns to its measured level, and the cloud clears to show the unchanged tower |
| Cancel (Esc or `[Cancel]`) | As not fixed. The status line says the sandbox keeps what was done so far |

The verdict comes from re-surveying the sandbox (next section), not from the live metrics.
"Fixed" means that survey no longer finds the action's problem on the target. A target that no
longer exists counts as not fixed.

### After a run

- **Re-survey.** The sandbox is surveyed with `survey.survey`. Its plat is the original plat
  updated with the sandbox model through `Plat.update`, so unchanged modules keep their plots
  and new modules take free ones. The result is saved as `after-model.json` and
  `after-plat.json` in the repository's survey folder. The original's `rows.json` and
  `plat.json` are not changed.
- **Before and after.** The town switches to "after", meaning buildings and problems from the
  sandbox survey. `b`, or clicking `[Before]` or `[After]` in status line 3, flips between the
  two.
- **The fix.** Status line 2 names the sandbox path, so you can diff it yourself. Applying the
  change to the repository is out of scope.

## 6. Status lines

The viewer keeps its three lines:

1. **Message.**
   - **Idle:** `shop: 16 modules, 31 roads, 2 problems. Click to walk, click a building to
     inspect.`
   - **A fire:** `FIRE! payments/checkout.py won't parse: line 212: invalid syntax`,
     highlighted for 6 s after Clawd lands.
   - **During runs:** `Clawd is putting out the fire in payments/checkout.py ...` or
     `Clawd is refactoring utils/helpers.py ...`, highlighted.
   - **After a run:** the result, for example `payments/checkout.py parses again. Fire's out.`
     or `utils/helpers.py: 3,412 → 640 lines, 3 new modules.`
2. **Facts.** The selected thing's facts, as today. During a run, the latest event, such as
   `reading core/models.py` or `edited 3 files`.
3. **Clickable items.** `[Cancel]` during a run, `[Before] [After]` after one, then
   `scroll to zoom   q quit   [street]`. They are plain text: nothing lights up on hover or
   press.

## 7. Frame rate

A street-level frame takes 21–27 ms today at 100×45 to 120×57 pixels. That was measured on
this repository's own town (41 modules) on 2026-10-01.

- **Rates.** The viewer runs at 24 FPS while anything moves (intro, walking, effects, counting
  numbers, camera gliding) and at 12 FPS when still.
- **Fallback.** If a frame takes more than 35 ms to draw, the viewer drops to 12 FPS until the
  movement ends.
- **Effect budget.** Each effect should cost under 5 ms per frame at street zoom. A benchmark
  script checks this. The test suite doesn't time anything.
- **Zoomed out.** District and town zoom keep the cached whole-town drawing. While still, only
  labels and the badge are redrawn on top of it.

## 8. Testing

- **`term`:**
  - Overlay composition, including half-pixel edges.
  - A row is redrawn when only its overlay changes.
  - SGR parsing for press, release, wheel and sequences split across reads.
- **Pick map:**
  - Owners for a roof, a wall, an annex, a prop, the ground and Clawd.
  - Sampling at district and town zoom.
- **Walking:** the path to a building's front, an unreachable target, and a new click in the
  middle of a walk.
- **Labels:**
  - No overlaps, and priority order respected.
  - Never on top of Clawd.
  - Shortening long paths.
  - The edge arrow's direction in all eight sectors.
- **Intro:** only sea at time 0, every offset at 0 after the intro, and a key skips it.
- **Tower:**
  - The same id gives identical pixels.
  - Lean grows with overage.
  - Every tower pixel is owned by its building.
- **Measurement:** unreadable lines, tower progress, and diffs including created and deleted
  files.
- **Agent:**
  - Replay order.
  - The file observer emits `edit`, `create` and `delete`.
  - The guard fails a run that writes to the original.
  - The sandbox refuses a path inside the repository.
- **End to end, on replay:**
  - Setup: a fixture repository with one file that doesn't parse and one tower, and a replay
    that fixes both.
  - The badges settle on the measured values.
  - The after-town has no fire, and has a smaller building with flower boxes.
  - The original repository is byte-identical afterwards.
- **SDK source:**
  - A fake run that yields messages and raises errors.
  - A missing `cursor_sdk` shows the install hint.

## 9. Phases

Each phase gets its own implementation plan and ships on its own.

1. **Foundations:** text overlays, mouse input, pick map, camera, frame-rate rule.
2. **Point and click, and the look:**
   - Clawd in the town, clicks and the keyboard fallback.
   - Labels and the edge arrow.
   - Start-up lines and the intro.
   - The fire upgrade and the janky tower.
3. **Runs on replay:**
   - Events, the replay source, the sandbox and the guard.
   - Measurement and badges.
   - The spray and the dust cloud.
   - The verdict, the after-town, before and after, flower boxes, Cancel.
4. **Cursor SDK source:** message mapping, cancel, errors, the install hint.

## Changes to the site-plan spec

- **Views and controls.**
  - "You are the camera and a cursor; Clawd is the agent" becomes: you point and click, and
    Clawd walks where you click. The cursor is gone.
  - `d` (send Clawd) becomes clicking the action in the building's label, or Enter on the
    keyboard.
  - `f` (follow) goes away, because the camera follows Clawd during runs on its own.
  - `b` is unchanged, and the scroll wheel zooms.
- **Zoom levels.** Two zoom levels become three (street, district, town), as built.
- **Clawd.**
  - The one-line task is suggested and sent as written. Editing it comes later.
  - From the agent table, reading, editing the target and finishing are drawn as above.
  - Searching, commands and thinking get the simpler poses in section 5.
  - Scaffolding, Town Hall, building on free plots during the run, and the flag remain later
    work.
- **New symbol.** Flower boxes mean fixed by Clawd this session.
- **New principle.** Principle 7: every number is a measurement.

## Success

- Clicking any visible pixel of a building selects that building, at every zoom.
- Once its count settles, every number on screen equals what `measure.py` computes from the
  files at that moment.
- The end-to-end replay test passes, and the original repository is byte-identical afterwards.
- The intro finishes within about 3 s, and any input skips it.
- At street zoom in a 240×60 terminal (120×57 pixels), animations hold 24 FPS, or fall back to
  12 FPS as specified in section 7.
