# Towncode watch in 3D: design

`towncode watch PATH --browser` opens the watch experience as a real-time 3D town in the browser.
It is the same town as the terminal view, with the same palette, built from boxes. Every agent
is a voxel Clawd. Implementers wear a scarf in their team's colour, reviewers wear glasses, and
the orchestrator stands at Town Hall in a pointed hat. A Clawd walks the streets to the file its
agent is editing. Scaffolding goes up around edited buildings, new files appear as orange sites,
and finished tasks plant flags. On a merge, the scaffolding comes down, the sites drop in as
buildings, and the implementer hops and leaves. You can orbit and zoom, let the camera follow
the activity, and click a building to see its facts and its import roads.

Python keeps doing the work: the survey, the town layout, watching the worktrees, and deciding
where each Clawd goes. The browser only draws and animates what Python tells it, so the terminal
and the browser never disagree about what is happening.

## Depends on

- **Watch phase 3** (branch `towncode-watch-3`, spec
  `docs/superpowers/specs/2026-10-01-towncode-watch-design.md` on `towncode-watch-spec`) merged
  into `main`. This design reuses `Watch.poll()`, `Crowd`, `CameraDirector` and `watch_ui`.
- **Live visuals** (PR #15) merged
  into `main`, for cake tiers on `Building`, focus roads and construction sites.

Plan 2 starts only when both are on `main`. Plan 1 (the static town) needs only live visuals, so
it is built now on a branch off `live-visuals`, and it is served by `towncode view PATH --browser`
because `towncode watch` exists only on `towncode-watch-3` until that merges. Plan 2 adds
`watch --browser` on the same server. Each plan starts by checking every name it uses on its base.

## Scope

In scope: the `--browser` mode of `towncode watch`; a local web server that streams live state;
a 3D scene of the town, the Clawds, scaffolding, sites and flags; the automatic camera and follow
keys; the building inspector with focus roads and dimming; rebuilding the town after a merge.

Out of scope:

- Replay in 3D (watch phase 4).
- Opening the view from another machine. It is served on `127.0.0.1` only.
- Changing anything in the repository or its worktrees. Like watch, it only looks.
- Worn streets, hot tiles, and the notes and signs props. They can follow once the core works.
- Sound, touch controls, recording and screenshots.

## How it runs

```
towncode watch PATH --browser [--port N] [--no-open]
```

- It surveys and lays out the town exactly as terminal watch does, and fails with the same
  errors.
- It serves `http://127.0.0.1:8765` (or `--port N`; `--port 0` picks a free port), prints the
  address, and opens it in the default browser unless `--no-open` is given.
- It doesn't need an interactive terminal. `Ctrl-C` stops the server and closes the watch.
- `--browser` can't be combined with `--events`.

## Parts

| File | Status | What it does |
|---|---|---|
| `livetown.py` | new, moved out of `viewer.py` | The live half of `WatchViewer`: the crowd, seeding, applying events, re-surveying on a merge, the merge status line. Also `WatchPoller`. No drawing. |
| `viewer.py` | changed | `WatchViewer` wraps a `LiveTown` and keeps only the pixel drawing. Terminal behaviour is unchanged. |
| `drawtown.py` | changed | `window_kind` and `roof_index` become module-level functions, so `townjson` uses the same window and roof rules. |
| `crowd.py` | changed | `CameraDirector.auto_agent`: a read-only property naming the Clawd the automatic camera has chosen. |
| `townjson.py` | new | Pure functions: the town, the live state, and the difference between two live states, as JSON-ready dictionaries. No I/O. |
| `webserve.py` | new | The local server, the simulation thread, and the event stream. Standard library only. |
| `towncode.py` | changed | `--browser`, `--port` and `--no-open` on `watch`. |
| `web/index.html` | new | The page: canvas, status bar, inspector panel. |
| `web/town3d.css` | new | Page layout and label styles. |
| `web/town3d.js` | new | Builds the scene, animates Clawds and poses, runs the camera, handles picking and keys. |
| `web/look.js` | new | The designer's file. Every colour, size, material and voxel model. |
| `web/vendor/` | new | One pinned Three.js release: `three.module.js` and the `three.core.js` it imports, `OrbitControls.js`, its MIT licence, and a `VERSION` file with each file's SHA-256. |
| `smoke_web.py` | new | A browser smoke check, run by hand. Its name keeps it out of `unittest` discovery. |
| `test_townjson.py`, `test_webserve.py`, `test_livetown.py` | new | Unit tests. |

`townjson.py` and `webserve.py` use only the standard library, so their tests run under both
`.venv/bin/python` and the system `python3`.

The browser side has no npm and no build step. The pinned Three.js version is the latest release
when the build starts, recorded in `web/vendor/VERSION`. Releases since r171 ship no minified
module build, so the vendored files are about 2.1 MB.

The inspector text comes from the terminal's own `Viewer.describe`, passed into `townjson`, so
the two inspectors can't disagree.

### Why `LiveTown`

On watch phase 3, `WatchViewer` holds both the live logic (seed the crowd, apply events, start a
re-survey when `main` moves, rebuild the town, write the merge line) and the terminal's pixel
scene. The browser needs the first half and none of the second. Moving the live half into
`livetown.py` lets both views drive the same code. It is the first task of the live work, with
every watch test still passing before anything live is added.

Each view keeps its own `CameraDirector`, because the camera belongs to whoever is looking. The
server's director stays in automatic mode, with a camera object that only records its target.
Follow keys are handled in each browser tab.

## What you see

**Scale.** A tile is one unit on the ground. A cake's pixel heights become world heights through
`PX_PER_UNIT` in `look.js`. Its default, `TILE_W / √2` (about 8.5), keeps towers in the same
proportion to their footprint as in the pixel town. The hop heights (15, 8 and 4 px) use the same
constant.

**Ground.** Each tile kind (`grass`, `water`, `quay`, `dock`, `avenue`, `street`, `lot`, `plot`,
`vacant`) is a flat tile in its own colour. Water sits slightly lower than land. Trees are small
voxel trees. Sites aren't ground tiles here: in watch they arrive live (see below).

**Buildings.** Each cake tier is a box `2 × half` wide, from `z0` to `z1`, in alternating shades
of its district's colour. Amber tiers are amber. The roof is the district's roof colour. Windows
are small quads on the walls, coloured by the same rule as the terminal: boarded for abandoned
buildings, door-coloured for "all doors", lit when tested, dark otherwise. The terminal's rule of
keeping a window only if it is still whole isn't needed, because depth hides what's behind.

**Problems** keep their meanings and colours:

- Code that won't parse burns: flickering flame cubes on the roof and rising smoke cubes.
- Import cycles are red roads, and backwards imports are orange roads.
- Abandoned buildings have boarded windows and weeds at their base.

**Roads** are flat strips just above the ground along their tile runs. The roads shown by
default are the ones `Roads.visible()` shows today.

**Harbor.** Warehouses for outside packages stand on the docks.

**Watch on top**, following the watch spec:

- **Clawds** are built from small cubes listed in `look.js`: body, eyes and legs, plus a scarf in
  the team's colour, glasses for reviewers, and a pointed hat for the orchestrator. Walking swaps
  between two leg frames with a small bob. Hammering is a quick bounce, peering is a lean toward
  the building, hopping is three hops of falling height, and leaving is a walk off the front of
  the town.
- **Town Hall** is a lectern prop on the hall tile with a "Town Hall" label.
- **Scaffolding** is poles at a building's corners, with rails every few units up to its height,
  in the team's colour.
- **Sites** are orange plots with a low frame, like the terminal's, on the tiles watch's site
  placement (`watch_sites`) chose.
- **Flags** are a pole with a flag in the team's colour by the building the task changed last.
- **Merges:** when the new town arrives, buildings that weren't there before drop in from above.

**Labels** are HTML elements placed over the canvas each frame. Every Clawd has its watch label
(for example `world · task 1  +212 −14`). Up to 8 scaffolded buildings nearest the camera's
target show their names. Labels fade out past a distance set in `look.js`.

**Status bar.** Lines 1 and 2 are the terminal's, from `watch_ui.line1` and `watch_ui.line2`.
Line 3 is the browser's own key legend, built from the follow numbers, for example
`0 auto  1 world  2 render  ·  drag orbit  scroll zoom  click inspect  Esc clear`.

## What you can do

- **Camera.** Drag to orbit, scroll to zoom, right-drag to pan, within the town's bounds. It
  starts at an isometric-style angle looking at Town Hall.
- **Automatic camera.** By default the camera eases toward the Clawd that `CameraDirector` chose,
  which already applies watch's event priority and 4 s minimum stay.
- **Keys** match terminal watch. `1`–`9` follow that Clawd until `0` or until it leaves, then the
  camera returns to automatic. Moving the camera yourself pauses automatic mode, and `0` resumes
  it. The status bar shows which mode is on.
- **Click a building** (or a warehouse) to open the inspector panel. It shows the terminal
  inspector's title, facts line and problem reasons. The building goes into focus at the same
  time: the roads it uses turn blue and the roads using it turn pink, its roof turns white, and
  other buildings dim by their distance from it (`focus.dim`'s levels). `Esc`, or clicking empty
  ground, clears the focus.

## Data and messages

Python sends meanings (kinds, indexes, paths), never colours. `look.js` turns each meaning into a
colour, so the designer can restyle the browser without touching Python. Its starting values are copied
from `drawtown` and watch's scarf colours.

### `GET /town.json`

The whole town, built once by the browser and fetched again after a merge.

```json
{
  "version": 3,
  "repo": "game-web",
  "size": [96, 120],
  "half_w": 6,
  "legend": {"g": "grass", "w": "water", "q": "quay", "d": "dock", "a": "avenue",
             "s": "street", "l": "lot", "p": "plot", "v": "vacant"},
  "tiles": ["ggggwwq…", "…"],
  "trees": [[4, 9], [5, 12]],
  "hall": [40, 7],
  "step_time": 0.16,
  "districts": [{"name": "world", "box": [4, 7, 20, 16], "roof": 2}],
  "buildings": [{"path": "src/world/map.ts", "district": "world", "lot": [6, 9, 3],
                 "tiers": [{"half": 1, "z0": 0, "z1": 24, "amber": false}],
                 "glass": "lit", "problems": ["import cycle"],
                 "inspect": {"title": "…", "facts": "…", "reasons": ["…"]}}],
  "warehouses": [{"package": "three", "lot": [60, 3, 2],
                  "inspect": {"title": "…", "facts": "…", "reasons": []}}],
  "roads": [{"from": "src/a.ts", "to": "src/b.ts", "kind": "cycle", "weight": 1,
             "half": 0.17, "layer": 5, "tiles": [[6, 12], [7, 12]]}]
}
```

- `half_w` is `iso.HALF_W`, the pixels in half a tile's width, which turns a tier's `half`
  (in pixels) into tiles.
- `tiles` is one string per row and one letter per tile, so a large town stays small.
- A road's `half` is `roads.half_width(kind, weight)` in tiles, and `layer` is its place in
  `roads.ORDER`, so louder roads sit on top.
- `glass` is `lit`, `dark`, `door` or `board`, from `drawtown.window_kind`.
- `roof` is the district's index into the roof colours, from `drawtown.roof_index`.
- `roads` are the ones `Roads.visible()` shows with nothing selected. `kind` is `road`,
  `highway`, `backwards` or `cycle`.
- `inspect` is the terminal's `Viewer.describe` for that building or warehouse.

### `GET /focus?module=PATH` and `GET /focus?package=NAME`

Returns `{"focused": ["PATH"], "dim": {"PATH": 1.0, …}, "roads": [road, …]}`, where each road
has the same shape as in `/town.json`. For a module, `dim` comes from `focus.select` and
`focus.dim`, and `roads` from `Roads.visible(building, focus)`, which adds the `uses` and
`used by` kinds. That is exactly what the terminal draws for a selection. For a warehouse,
`focused` and `dim` are empty and `roads` is `Roads.visible(warehouse)`. A name that isn't in the
town returns 404.

### `GET /events`

A Server-Sent Events stream (`text/event-stream`). Each message's `data` is one JSON object and
carries `t`, the server's monotonic clock.

- **`state`** is sent on connect and reconnect. It holds every Clawd, the scaffolding, sites,
  flags, the status lines, the automatic camera's Clawd, and the town `version`. A reconnecting
  browser always starts from the truth.
- **`tick`** is sent only when something changed. `clawds` lists only the Clawds whose record
  changed, `gone` lists the Clawds that left, and `scaffold`, `sites`, `flags`, `status` and
  `camera` appear only when they changed, each replaced whole.
- **`town`** is sent after a merge and re-survey, carrying the new `version`. The browser fetches
  `/town.json` again, rebuilds the scene, and keeps the Clawds where they are.
- A `:` comment is sent every 15 s as a heartbeat.

A Clawd's record:

```json
{"id": "w1-world-1", "role": "implementer", "team": "world", "scarf": 0,
 "label": "world · task 1  +212 −14", "follow": 1, "tile": [12, 30], "facing": [0, 1],
 "pose": "walk", "path": [[12, 30], [13, 30], [14, 30]], "path_i": 0, "walk_t": 0.25}
```

Other live fields:

- `scaffold`: `{"PATH": scarf_index}`;
- `sites`: `[{"path": "…", "tile": [x, y], "scarf": i}]`;
- `flags`: `[{"agent": "…", "building": "…", "scarf": i}]`;
- `status`: `["line 1", "line 2"]`;
- `camera`: a Clawd id or `null`.

### Movement contract

- A Clawd's record is sent again only when its path, pose, label, follow number or flag changes,
  not each time it steps to the next tile of the same path.
- The browser walks the path from `path_i` and `walk_t` at the message's time, one tile per
  `step_time`, moving smoothly between tiles. The next record snaps away any drift.
- The browser plays each pose when it arrives. `hammer`, `peer` and `hop` have fixed lengths in
  `look.js`.
- The browser keeps an offset between its clock and `t`, updated on every message.

### What never crosses the wire

File contents, transcript text, commands, and tool arguments. Only repository-relative paths,
roles, team names, labels, and the facts and counts the terminal already shows.

## The server

- **Polling.** A `WatchPoller` thread, the one terminal watch uses, calls `Watch.poll()` every 1 s
  and queues each snapshot, so a slow poll over many worktrees never stalls the animation.
- **Simulation thread.** Every 0.1 s it drains the poller's queue into `LiveTown.ingest`, then
  steps the crowd and the director. It then builds the live dictionary, diffs it against the last
  one sent, and puts any `tick` on every client's queue. 0.1 s is short enough that a 0.5 s hammer
  is never skipped.
- **Re-survey.** It is the same background survey `WatchViewer` runs now, moved into `LiveTown`.
  When it lands, the server rebuilds `/town.json`, bumps `version`, and sends `town`.
- **Clients.** Each `/events` connection gets its own queue. A client that falls more than 100
  messages behind is disconnected, and its browser reconnects and gets a fresh `state`.
- **Threads.** `ThreadingHTTPServer` with daemon threads. Shutting down stops the simulation
  thread and calls `Watch.close()`.

## Errors

| Case | What happens |
|---|---|
| Port in use | Says so and suggests `--port 0`. |
| Survey fails at start | The same error terminal watch gives, and no server starts. |
| Re-survey fails | The old town stays, and status line 1 says so, as in terminal watch. |
| Stream drops | The page shows "reconnecting…", `EventSource` retries, and the next `state` rebuilds the live layer. |
| No WebGL | The page says WebGL isn't available and shows the status lines as text. |
| No browser to open | Prints the address and keeps serving. |

## Safety

- It binds to `127.0.0.1` only. There is no host option.
- It rejects any request whose `Host` header isn't `127.0.0.1:PORT` or `localhost:PORT` with 403.
  This blocks DNS rebinding.
- It accepts GET only and answers anything else with 405.
- Static files come from a fixed table of names in `web/`. Any other path gets 404, so nothing
  outside `web/` can be served.
- It sends no CORS headers.
- Every response carries a strict `Content-Security-Policy`: `default-src 'self'`, with
  `script-src 'self'` plus the SHA-256 hash of the page's one inline import map, computed from
  `index.html` at startup. It also sets `base-uri 'none'` and `frame-ancestors 'none'`.
- The repository and its worktrees stay read-only, exactly as in watch. For the monorepo, its module
  names only ever reach a page on your own machine.

## Performance

- One instanced mesh per kind of thing (ground tiles by kind, trees, tier boxes, windows, flame
  cubes), with colour per instance. A town of a couple of hundred buildings costs a handful of
  draw calls, and dimming only rewrites instance colours.
- Clawds are small merged meshes, one per Clawd.
- One simulation thread per server, shared by every open tab.
- Targets, checked in the build: 60 fps for a town that size with 10 Clawds on a recent laptop, a
  `/town.json` under 1 MB, and the simulation thread under 5% of one core.

## Testing

Unit tests (`unittest`, both interpreters):

- **`townjson`:**
  - tile rows match `TownMap.kind` for every tile;
  - building, warehouse and road counts match the TownMap and `Roads`;
  - tiers match `Building` cake tiers;
  - roads match `Roads.visible()`, and `/focus` roads match `Roads.visible(selected, focus)`;
  - `inspect` equals `Viewer.describe`;
  - no file contents appear: a fixture file with a unique marker string, whose marker is absent
    from the JSON.
- **Diffs:**
  - a quiet step produces no `tick`;
  - a new path, pose or label sends that Clawd only;
  - advancing along the same path sends nothing;
  - a departure lands in `gone`;
  - `state` holds everything a fresh browser needs.
- **SSE framing:** `event:` and `data:` lines, the blank-line terminator, JSON with newlines kept
  on one `data` line, and the heartbeat comment.
- **Server,** run for real on port 0:
  - it binds to `127.0.0.1`;
  - a bad `Host` gets 403;
  - POST gets 405;
  - `/static/../towncode.py` and unknown names get 404;
  - `/focus` for an unknown module gets 404;
  - the CSP hash matches the import map in `index.html`;
  - `/events` sends `state` first;
  - a busy port stops with the `--port 0` hint.
- **Vendored files:** each one's SHA-256 matches `web/vendor/VERSION`.
- **`LiveTown`:** the watch tests that cover ingest, re-survey and merge lines pass against it
  unchanged, and terminal watch behaves the same.

Browser smoke check (`smoke_web.py`, run by hand with `playwright-cli`, not in `unittest`):

- serve a fixture repository with `--no-open --port 0`;
- load the page and wait for `window.town3d.ready`;
- check the scene's building count equals `/town.json`'s;
- check `window.town3d.missing` is empty. At startup, `town3d.js` lists any key it reads that
  `look.js` doesn't define, and the page names them, so a restyle that drops a key fails loudly;
- save a screenshot to `/tmp`.

## Build order

Two plans. Plan 1 is step 1, and plan 2 is steps 2 to 4. Plan 2 is written once plan 1 has
landed, so it's written against real code.

1. **Static 3D town.**
   - `townjson` for the town and focus;
   - `/town.json`, `/focus` and the static files;
   - ground, buildings, roads, problems, harbor;
   - orbit and zoom, the inspector and focus.

   It can be checked on any repository without agents. It is served by
   `towncode view PATH --browser`, which also takes `--layout` and `--session`; a session's new
   files are orange site tiles, as in the terminal view.
2. **Shared live core.**
   - `LiveTown` moved out of `WatchViewer`;
   - `CameraDirector.auto_agent`.

   Terminal watch stays unchanged and every test passes.
3. **Live.**
   - the simulation thread, `/events`, diffs;
   - Clawds and poses, scaffolding, sites, flags;
   - labels, status lines, the automatic camera and follow keys.
4. **Merges and polish.**
   - the `town` message and rebuilding;
   - dropping buildings;
   - reconnecting;
   - the error cases;
   - the smoke check;
   - the performance targets.

## Decisions

| Question | Choice |
|---|---|
| What the browser view is for | The watch experience in 3D. |
| When to build it | Design and plan now; build once watch phase 3 and PR #15 are on `main`. |
| Rendering | Three.js, one pinned release vendored into `web/vendor/`, no npm, no build step. |
| Look | A voxel version of today's town with the same palette, all of it in `look.js` for the designer. |
| Colours | Python sends meanings; `look.js` maps them to colours. |
| Architecture | Python simulates and streams over Server-Sent Events; the browser animates between the tiles Python chose. |
| Camera keys | The same as terminal watch: `0` automatic, `1`–`9` follow a Clawd. |
| Inspector and focus | The terminal's `Viewer.describe`, `focus` and `Roads.visible`, so the two views can't disagree. |
