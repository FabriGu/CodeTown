# Towncode watch: Clawds in the town while agents build

## Summary

`towncode watch PATH` opens the town of a repository's `main` and keeps it live while agents
work on it. Every active agent is a Clawd. Implementers wear a scarf in their team's colour,
reviewers wear glasses, and the orchestrator stands at Town Hall in a pointed hat. A Clawd walks
to each file its agent creates, edits or deletes, a second or so after it happens. Edited
buildings put up scaffolding in the team's colour, and new files appear as construction sites.
When the orchestrator merges a branch, the town re-surveys `main`, the scaffolding comes down,
the sites drop in as buildings, and the implementer hops and leaves.

The first repository it is built for is `~/game-web`. There, one Cursor orchestrator runs up
to 8 Claude Opus implementers at once, each in its own worktree under `~/game-web-worktrees/`
on a `team/<team>/<slug>` branch. Watch must work for that, and for the simple case of one agent
working in one repository.

This builds on the site plan (`2026-09-30-codetown-site-plan-design.md`) and shares
foundations with point and click (`2026-10-01-codetown-point-and-click-design.md`, v3). It is
the `towncode watch` that Plan 3 (`plans/2026-10-01-visual-modules.md`) names as later work, and
it takes over from the designer's watch mock (`mock_roles.py ... watch`, PR #13). Changes to the earlier
specs are listed at the end.

## Scope

**In:** live Clawds for implementers, reviewers and the orchestrator; scaffolding, construction
sites and finish flags; re-surveying on merge; an automatic camera with follow keys; labels and
status lines; the state of a build already under way when watch opens.

**Out:**
- **Replay of past sessions.** Phase 4, later. It reuses this spec's event stream.
- **Mouse, the pick map and agent runs you start yourself.** Those stay in v3.
- **Anything that changes the repository or its worktrees.** Watch only looks.
- **Live reads by implementers and reviewers.** They can't be observed while they happen (see
  "What the probe found").

## What the probe found

On 2026-10-01, two throwaway Cursor subagents were started from a chat in this repository while
a recorder logged the transcript files once a second.

1. **A subagent's transcript is written when it returns.** A subagent that read three files with
   8 s pauses ran for about 30 s. No `subagents/` folder existed during the run. Its file
   appeared at the end, already holding all 8 lines.
2. **The parent writes a tool call when the call completes.** A marker in a second subagent's
   prompt reached the main transcript about 30 s after dispatch, when the subagent returned.
3. **Main transcripts are otherwise near-live.** Short tool calls appear within seconds.
4. **Cursor transcript lines carry no timestamps.** Only `role` and `message`. Time is when a
   line is first seen.

In the orchestrator's session, 160 subagent transcripts sit under the home-folder
workspace (the agent transcript), not under a `game-web` project.
Their paths point into worktrees. `session.transcripts(root)` finds none of them, and
`session.read_steps` would treat every worktree path as outside the repository.

So the live view is driven by the file system, and transcripts add what they can, when they can.

## Principles

The site plan's six, v3's seventh (every number is a measurement), and:

8. **A Clawd only goes where its agent was seen.** A Clawd walks to a building because a file
   event, a commit or a transcript line put its agent there. The one exception is the reviewer's
   tour, which shows the files under review and is labelled as such.

## What you see

### The town

The town is `main`, surveyed as `towncode view` surveys it, with its saved plat. Watch opens at
district zoom with the camera on Town Hall.

**Town Hall** is a one-tile lectern prop with a "Town Hall" label at street zoom. It stands on
the tile v3 gives Clawd at start-up: the frontmost avenue, at the walkable tile nearest the
town's centre column. It is not a building and has no survey facts.

### Clawds

| Agent | Looks like | Label |
| --- | --- | --- |
| Implementer | Clawd with a scarf in its team's colour | `world · task 1  +212 −14` |
| Reviewer | Clawd with glasses and a grey scarf | `review · world task 1 (6 files)` |
| Orchestrator | Clawd in a pointed hat | `orchestrator` |
| A single agent with no team | Plain Clawd | `agent` |

`+212 −14` is the worktree's diff against its merge base with `main`, from
`git diff --numstat <merge base>`, which includes uncommitted changes to tracked files.
Untracked files aren't counted until they're committed, because watch never opens them. It
refreshes at most every 2 s, after that worktree's file events. A reviewer's label is its team
and its ledger file name without `review-`, so `review-task-1.md` in `w2-world` reads
`review · world task 1` and `review-fix1.md` reads `review · world fix1`.

**Team colours.** Eight scarf colours, given to teams in the order they're first seen and saved
in `watch.json` in the survey folder, so a team keeps its colour from one session to the next. A
ninth team reuses the least recently seen colour. None of the eight is within an RGB distance of
80 of the reserved colours: fire red, problem amber, uses blue, used-by pink, focus white, site
orange and the reviewer's grey. A test checks the distances.

### What each Clawd does

| Happens | The Clawd |
| --- | --- |
| A task brief appears in a worktree's ledger | Implementer arrives at Town Hall and waits |
| A file in its worktree is edited | Walks to that building, with scaffolding going up in the team colour |
| A new code file appears in its worktree | Walks to a construction site for it in its team colour |
| A file is deleted | Walks to it, and the building gets scaffolding like an edit. On merge it becomes a vacant lot, as in the site plan |
| A commit lands on its branch | A hammer bounce, and status line 2 says so |
| No events from its agent for 20 s | Idles where it stands, looking left and right |
| Its task report appears | Plants a flag in its team colour by the last building it changed, then walks to Town Hall and waits |
| File events after its report (a fix) | Takes the flag down and goes back to work |
| Its branch is merged into `main` | Hops three times (15, 8 and 4 px) and walks off the front of the town |
| A review package appears in its worktree | A reviewer arrives at Town Hall, then tours the branch's changed buildings, 4 s at each, in path order, repeating |
| The review's result file appears | The reviewer walks back to Town Hall and leaves |
| The orchestrator reads a file in `main` | The orchestrator walks there, peers in the windows, and goes back to Town Hall after 3 s with no further reads |
| The worktree is removed | Its Clawds leave, and its scaffolding and sites come down |

**Walking** uses `roads.route` at 0.16 s per tile, as in v3. A new target replaces the path from
the next tile on. When an agent touches many files at once, its Clawd heads for the most recent
one. Every touched building still gets its scaffolding straight away: the scaffolding is the
record, and the Clawd shows the latest step.

**Standing spots.** Several Clawds at one building stand on different tiles: the building's
front tile first, then the nearest free walkable tiles to its door, ties broken by `(y, x)`.
Walking Clawds may overlap one another; standing spots may not.

**Files with no building.** A changed file the survey makes no building for, such as a JSON
content file, gets no scaffolding and no site. Its Clawd walks to the building whose path shares
the longest folder prefix with the file, and status line 2 names the file itself.

### Scaffolding, sites and flags

- **Scaffolding** stands on a building while a worktree's diff against its merge base with
  `main` touches that file. Diffing against the merge base, not `main`'s tip, keeps other
  branches' merged work from showing as this branch's changes. It is in the colour of the team
  that changed it most recently. It comes down when that diff for the file is empty again,
  whether because the change merged or was undone.
- **Construction sites** are new code files in a worktree that `main` has no building for. They
  are chosen by `focus.unbuilt(steps, model, tracked)`, unchanged. Its `steps` are
  `session.Step`s made from the branch's added files (`git diff --name-status <merge base>`) and
  the worktree's untracked files, and its `tracked` is `main`'s tracked files. Sites are drawn as
  in the designer's mock: a 1-tile site per file, one yard per top folder, along the front of the town,
  in the team colour.
- **Why not a free plot.** The site plan has Clawd build new files on a free plot. In watch, two
  worktrees could claim the same free plot, and the plot a file really gets depends on merge
  order. A site on a provisional plot could move at merge, which breaks principle 3. So sites
  wait in a yard, and on merge each new building drops onto its real plot with v3's intro drop
  (48 px over 0.42 s).
- **Flags** stand by a building from a task's report until its branch merges or its agent goes
  back to work. A flag means "finished, waiting to merge", as in the site plan.

### Camera

- **Auto (`0`).** The camera glides, using v3's easing, to the Clawd with the most recent event.
  It stays on a Clawd for at least 4 s. Edits, creates, deletes, commits and merges take
  priority over finishes, which take priority over reads and arrivals.
- **Follow (`1`–`9`).** Each Clawd except the orchestrator gets the lowest free number on
  arrival, shown in status line 3. A tenth gets none until a number frees up. Pressing a number
  keeps the camera on that Clawd until `0` or until it leaves.
- **Zoom (`+` / `-`).** Street, district and town, as today. At town zoom the cached whole-town
  drawing is shown with each Clawd as a 3-pixel marker in its scarf colour on top.
- **Quit (`q`).**

### Labels and status lines

Labels are text overlays (v3 section 3). Watch places, in priority order: Clawd labels, the
Town Hall label, and name labels for scaffolded buildings at street zoom, up to 8, nearest the
camera first. It uses v3's anchoring, overlap avoidance, clamping and path shortening. There is
no edge arrow.

1. **Who's working:** `game-web: 7 agents: world, render, gameplay ×2, qa, review, orchestrator. main at cab317f`.
   With nobody working: `game-web: no agents working. Watching main and 3 worktrees.`
2. **The latest event:** `world task 1 edited tools/blender/env/kit/bake.py`, or
   `merged team/world/w2-corridors: 4 new buildings, 9 changed`.
3. **Keys:** `0 auto  1 world  2 render  3 gameplay  4 gameplay  5 qa  6 review   +/- zoom   q quit   [district]`.

## Where the events come from

| Source | How it's read | Delay | Gives |
| --- | --- | --- | --- |
| Worktrees | `git worktree list --porcelain` from the main repository, every 5 s | 5 s | Which worktrees exist, their branches and teams |
| Files in each worktree | The file observer (below) | about 1 s | `edit`, `create`, `delete` |
| Each worktree's branch tip | `git rev-parse HEAD` in the worktree, every 1 s | about 1 s | `commit` |
| `main`'s tip | `git rev-parse HEAD` in the main repository, every 1 s | about 1 s | `merge` |
| Task ledgers | File names in `<worktree>/.superpowers/sdd/*/`, every 1 s | about 1 s | `start`, `finish`, `review_start`, `review_finish` |
| Main transcripts | New lines, tailed every 1 s | seconds | Orchestrator `read`s |
| Subagent transcripts | Noticed when they appear | after the agent returns | Read counts for the finish message, and replay later |

### Agents and teams

- **Team** comes from the worktree's branch, `team/<team>/<slug>`. A worktree on any other
  branch has its worktree folder's name as its team.
- **An implementer** is `<worktree>/task-<N>`, one per `task-<N>-brief.md`. File events in a
  worktree belong to its latest task's implementer. A worktree with changes and no ledger has a
  single implementer named after the worktree.
- **A reviewer** is `<worktree>/<stem>`, one per review package `<stem>.md` whose name starts
  with `review-` and doesn't end in `-result`. It finishes when `<stem>-result.md` appears. The
  files it tours are `git diff --name-only <merge base>..<branch tip>` at the moment the package
  appeared.
- **The orchestrator** is any main transcript, modified in the last 2 hours, whose tool calls
  touch the repository or one of its worktrees and which has dispatched a subagent. The window
  is long because an orchestrator writes nothing while it waits for subagents. A main transcript
  that touches them without dispatching is a single agent. Its team comes from the worktree it
  works in, or it has none if it works in the main repository. A new orchestrator shows as a
  single agent until its first dispatch returns and reaches its transcript.
- **Ledger files are never opened.** Watch uses their names only. The task number comes from the
  file name, so labels say `task 1` and not the task's title.

### Which worktrees are shown

A worktree is shown when its branch isn't merged into `main` and at least one of these holds:
it has a brief with no report, a review package with no result, or a file change or commit in
the last 2 hours. Others are checked every 10 s, so they can become active. For
`~/game-web` today, this hides the wave 1 worktrees that are already merged.

### The file observer (`observer.py`)

This is v3's file observer, moved out of `agent.py` so that v3's sandbox and watch's worktrees
share it.

- **What it looks at.** Every 1 s for a shown worktree, and every 10 s for the others, it lists
  `git ls-files -co --exclude-standard`: tracked files, and untracked files that aren't ignored.
  It compares each listed file's size and modification time with the previous look. The files
  are never opened.
- **What it emits.** `edit`, `create` or `delete` for each change. A rename is a delete and a
  create.
- **Git without side effects.** Every git command uses `repo.GIT_FLAGS` and
  `GIT_OPTIONAL_LOCKS=0`, so nothing refreshes an index or writes in `.git`. Watch never runs
  `git status`.

### Transcripts (`watch.py`)

- **Where it looks.** `~/.cursor/projects/*/agent-transcripts/*/*.jsonl` and
  `~/.claude/projects/*/*.jsonl` for main transcripts, and each one's `subagents/*.jsonl`.
  Only files modified in the last 2 hours are considered, and the folders are scanned again
  every 10 s for new ones.
- **What it keeps.** Only tool names, paths and the first line of each command, using
  `session.read_steps` with the main repository as root. That returns worktree paths as
  absolute paths. Watch then makes them relative to their worktree, so
  `~/game-web-worktrees/w2-world/tools/x.py` becomes `tools/x.py` in `w2-world`.
- **Tailing.** At start-up each transcript is read once in full, to decide whether it touches the
  repository and which role it has. After that it is read from a saved byte offset, so only new
  lines become events. A partial last line waits for its newline. A file that shrinks is read
  again from the start.
- **Subagent transcripts** are matched, when they appear, to the worktree most of their paths
  fall in. The implementer's finish message then reads `world task 1 finished: read 41 files,
  changed 12`.

### Events (`events.py`)

Shared with v3, which today plans to define them in `agent.py`.

```python
@dataclass(frozen=True)
class Agent:
    id: str            # "w2-world/task-1", "w2-world/review-task-1", "orchestrator"
    role: str          # "implementer", "reviewer", "orchestrator" or "agent"
    team: str | None
    worktree: str | None

@dataclass(frozen=True)
class Event:
    kind: str          # start, read, edit, create, delete, commit, finish,
                       # review_start, review_finish, merge, leave
    agent: Agent | None
    path: str | None = None   # relative to the worktree, or to the repository for main
    seen: float = 0.0         # time.monotonic() when watch first saw it
```

v3 adds `search`, `command` and `fail` for its own runs. Watch never emits them.

### When watch opens mid-build

Watch shows the build as it stands, without replaying history:

- **Scaffolding and sites** come from each shown worktree's diff against its merge base with
  `main`, and its untracked files.
- **Implementers** whose brief has no report stand at the building of their most recently
  modified changed file. Finished ones wait at Town Hall, with their flags planted.
- **Reviewers** whose package has no result are already on their tour.
- **The orchestrator** stands at Town Hall.

### Merges

When `main`'s tip moves:

1. **Wait for a clean main.** If `git ls-files -u` lists unmerged paths, watch waits and says
   `main is mid-merge`, so conflict markers never become fires.
2. **Re-survey.** It runs `survey.survey` on `main` with the saved plat, through
   `Plat.update`, on a worker thread, so frames keep coming. `~/game-web` surveys in 1.3 s
   (134 modules, 351 roads, measured 2026-10-01).
3. **Swap the town.** New buildings drop onto their plots. Scaffolding and sites whose files no
   longer differ from `main` come down.
4. **Say goodbye.** An implementer whose branch tip is now an ancestor of `main`
   (`git merge-base --is-ancestor`) hops and leaves.
5. **If the survey fails,** the old town stays, status line 1 says
   `couldn't re-survey main: <reason>`, and watch tries again at the next move of `main`.

## Read-only

- **Never writes in the repository or its worktrees.** Watch writes only `watch.json` in the
  survey folder outside the repository, which `towncode.output_dir` already guarantees.
- **Untracked and ignored files.** The site plan reads only tracked files. Watch also lists the
  names and sizes of untracked files that aren't ignored, and the names of files in
  `.superpowers/sdd/`. It opens neither.
- **Never shows file contents.** The town shows names and numbers only, as in the site plan.
- **Never runs code,** and runs git read commands only.

## Where it lands in the code

| Module | New or changed | Responsibility |
| --- | --- | --- |
| `events.py` | new | `Agent` and `Event`, shared with v3 |
| `observer.py` | new | The file observer for a folder, shared with v3's sandbox |
| `watch.py` | new | Finds worktrees, ledgers and transcripts, tails them, and merges them into one event stream. Holds who is working where. No drawing |
| `crowd.py` | new | Many Clawds: routes, standing spots, poses, flags, arrivals and departures, the auto camera's target |
| `labels.py` | new | v3's label placement, without the edge arrow, which comes with v3's phase 2 |
| `term.py` | changed | Text overlays composed into rows (v3 section 3) |
| `drawtown.py` | changed | Clawds, scarves, hats and glasses in depth order, scaffolding, sites, flags, the Town Hall lectern, dropping buildings |
| `viewer.py` | changed | Watch mode: the event loop, camera easing, follow keys, status lines, the frame-rate rule |
| `towncode.py` | changed | `towncode watch PATH [--zoom street\|district\|town]`, and `snapshot PATH OUT --watch` for one frame of the current state |

Standard library only. Ownership is as in Plan 3: these are the engineer's files. The designer's
`focus.py` is used as it is.

## Frame rate

v3 section 7 applies: 24 FPS while anything moves, 12 FPS when still, and 12 FPS if a frame
takes more than 35 ms. Watch adds about 10 Clawds and their labels: 8 subagents, the
orchestrator and one spare. A benchmark script checks
that a street frame with 10 Clawds stays under 35 ms at 120×57 pixels.

Polling stays cheap. For `~/game-web`, 8 active worktrees of about 300 files each is about
2,400 `stat` calls a second.

## Testing

- **Observer:** create, edit, delete and rename in a temporary folder; ignored files are never
  reported; files are never opened (a test makes them unreadable and still gets events).
- **Worktrees and teams:** a temporary repository with two worktrees on `team/a/x` and
  `team/b/y`; a merged branch isn't shown; a removed worktree emits `leave`.
- **Ledger:** brief, report, review package and result names give `start`, `finish`,
  `review_start` and `review_finish`, and work with the files unreadable.
- **Transcripts:** Cursor and Claude Code lines; a partial last line; a file that shrinks;
  worktree paths made relative; a main transcript with a dispatch is the orchestrator and one
  without is a single agent; a subagent transcript is matched to its worktree.
- **Mapping:** a path to its module, to a site through `focus.unbuilt`, and to the building
  with the longest shared folder prefix.
- **Crowd:** standing spots never shared; a new target replaces the path; departure after a
  merge; a flag goes up on finish and comes down on a fix.
- **Camera:** the 4 s minimum stay, event priority, and follow until `0` or departure.
- **Colours:** the eight scarf colours keep their distance from the reserved ones, and a team
  keeps its colour across sessions through `watch.json`.
- **Drawing:** a snapshot with three Clawds, scaffolding, a site and a flag has scarf pixels in
  the right colours, and the scaffolding is drawn in front of its building.
- **End to end:**
  - A script builds a fake run in a temporary repository: it makes a worktree on
    `team/world/demo`, writes a brief, edits a file, adds a new one, commits, writes a report,
    writes a review package and its result, and merges into `main`.
  - Watch's event stream for that script is, in order: `start`, `edit`, `create`, `commit`,
    `finish`, `review_start`, `review_finish`, `merge`, `leave`.
  - At the end the town has the new building, no scaffolding, no sites and only the
    orchestrator.
  - The repository and worktree fingerprints from `untouched.fingerprint` are the same before
    and after watch runs over the finished script.

## Phases

Each phase gets its own implementation plan and ships on its own.

1. **Foundations, shared with v3.** Text overlays in `term.py`, label placement in `labels.py`,
   camera easing, and the frame-rate rule. v3's phase 1 then only needs mouse input and the pick
   map.
2. **The event stream.** `events.py`, `observer.py` and `watch.py`, tested on fixture folders
   and repositories, with no drawing. It includes a `towncode watch PATH --events` mode that
   prints events as lines, so the stream can be checked against a real build before anything is
   drawn.
3. **The watch view.** `crowd.py`, the drawing, the camera, status lines, merges and
   `snapshot --watch`.
4. **Later: replay.** Past sessions from transcripts, including subagent transcripts, at a
   chosen speed. This phase also checks whether Claude Code transcripts are written as the agent
   works, which this spec hasn't tested.

## Changes to earlier specs

- **Site plan.**
  - "Creates a file: builds on a free plot." In watch, a new file waits as a site in a yard at
    the front until it merges, then drops onto its real plot. Agent runs in v3 are unchanged.
  - The read-only rule gains the two listings described under "Read-only". Neither opens a
    file.
- **Point and click (v3).**
  - `agent.py`'s events move to `events.py`, and its file observer to `observer.py`. The run,
    the replay source, the sandbox and the guard stay in `agent.py`.
  - Its phase 1 loses text overlays, the camera and the frame-rate rule, which this spec's
    phase 1 builds. It keeps mouse input and the pick map.
- **Plan 3.** Its hook `--session [TRANSCRIPT]` on `view` and `snapshot` is covered for live
  work by `watch`. A `--session` view of a finished session can come with phase 4's replay.

## Open questions

- **One big district.** In `~/game-web`, `packages` is one district of about a hundred modules, so team
  areas don't look separate. A deeper district split, or the designer's layout by role, is a survey and
  plat decision, not part of watch.
- **Content files.** Some teams mostly change JSON content and
  asset files, which aren't buildings yet. Their Clawds will stand at the nearest building by folder.
  Giving data files floor buildings is a universal-survey decision.

## Success

- Within 2 s of a file being saved in a shown worktree, its scaffolding or site is up and its
  team's Clawd is walking there.
- Opening watch in the middle of a wave shows every task in progress and every unmerged change,
  without replaying anything.
- Within 3 s of `main` moving on `~/game-web`, the town matches a fresh
  `towncode survey` of `main`.
- No Clawd walks to a building its agent wasn't seen at, apart from the labelled reviewer tour.
- The end-to-end test passes, and the repository and worktrees are byte-identical after watch.
- At street zoom in a 240×60 terminal, frames hold 24 FPS with 10 Clawds, or fall back to 12 FPS
  as v3 section 7 specifies.
