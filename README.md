# CodeTown

You're the architect of your repo, but once your agents start building, it can be hard to feel at
home in it. Any piece of software can now be made in 90 minutes, so the bottleneck is how fast you
can keep up with your agents, and we've come to depend on them for everything. We missed being able
to find our way around our own repos. So we made a map.

CodeTown turns a codebase into a place you can walk around: a city built from symbols you already
know. Every part of it means something. Ports are dependencies, and roads connect them to the parts
of the city that use them. Towers are scripts: their height is their size and their footprint is
their complexity. There are neighborhoods, abandoned buildings and unused land. You can watch Claude
move around the city in real time, putting up scaffolding for changes, putting out fires and
slimming down buildings that overshadow their neighbors. When Claude is done working, it returns to
Town Hall.

A map like this lets you keep up with how fast a repo changes and still see the paths between its
parts.

## Why now?

Swarms of agents can make fundamental changes to a codebase before the whole team has pulled the
last ones. Teams need a way to stay on the same page while agents build out their designs. When
everyone shares the same picture, they can work together much more closely and focus on design
and systems instead of the details. Higher-level thinking is becoming where people who build
software do their most meaningful work, and that thinking needs a place to live.

Prompting for changes and delegating tasks makes us think like middle managers. We want to be the
architects.

We want the future of work to be fun, approachable and rewarding. CodeTown runs in the terminal, as
a playful nod to early TUIs and video games, and in 3D in the browser. Wouldn't it be cool to play
SimCity for your job instead of staring at a grey screen with an orange spinner?

## Usage

CodeTown draws any git repository as a town. It only reads the repository and never changes it.
Python 3.8+ with no dependencies is enough to start (see [Languages](#languages) for full
multi-language support).

```bash
python3 towncode.py survey PATH [--check-untouched]   # print the problems
python3 towncode.py view PATH                          # walk the town
python3 towncode.py view PATH --session                # what the newest agent session changed
python3 towncode.py watch PATH [--zoom district]       # watch agents work in the repo and its worktrees
python3 towncode.py watch PATH --browser [--port N] [--no-open]  # 3D town in the browser, live
python3 towncode.py watch PATH --events                # print the event stream
python3 towncode.py snapshot PATH out.png --zoom district --at MODULE
python3 towncode.py snapshot PATH out.png --layout roles   # laid out by role, not folder
python3 towncode.py snapshot PATH out.png --watch      # one frame of the current watch state
```

Watch only reads the repository and its worktrees; it writes only
`watch.json` in `.survey/`.

Folders are districts, modules are buildings, imports are roads and outside
packages are warehouses in the harbor. Each building is a cake: one floor per
function, the biggest at the bottom, and amber for a function of 100+ lines.
Select a building in the viewer (or name one with `--at` in a snapshot) and what
it uses turns blue, what uses it pink, and the rest dims. `--session` keeps an agent session's changes in focus instead, with its
new uncommitted files as orange sites at the front of town. Problems show up in
the town: fire for code that won't parse, red loops for import cycles, towers,
boarded-up buildings and more (see `docs/superpowers/specs/`). The survey, rows
and plat are saved in `.survey/`, never inside the surveyed repository.

### In the browser

```
python3 towncode.py view PATH --browser [--port N] [--no-open] [--layout roles] [--session [TRANSCRIPT]]
python3 towncode.py watch PATH --browser [--port N] [--no-open]
```

`watch --browser` watches PATH's agents in the 3D town: each agent is a Clawd walking to the file
it's editing, with scaffolding on edited buildings, orange sites for new files, flags for finished
tasks, and the town rebuilt after a merge. The camera follows the newest activity; `1`–`9` follow
one Clawd, `0` goes back to automatic, and moving the camera yourself pauses it. It serves this
machine only and never changes the repository.

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

### Languages

Towncode reads Python with the standard library. JavaScript/TypeScript,
Shell, Go, Java/Kotlin, C#, Rust, Ruby, C/C++ and Swift are read with
tree-sitter, installed once into a local venv:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python towncode.py setup        # download grammars (the only network use)
.venv/bin/python towncode.py languages    # what is read in full, and what isn't
```

Use `.venv/bin/python` in place of `python3` for the other commands too.
Without the venv, everything still works: Python is read in full and other
code is read at floor depth, from its lines alone (size, notes, rough
complexity, tests found by name). Floor buildings have no roads and never
burn, and languages with no adapter at all, like Elixir or Lua, stay at
floor depth.

| Key | Action |
| --- | --- |
| `W` `A` `S` `D` / arrows | move the cursor |
| `+` / `-` | zoom: street, district, town |
| enter / space | inspector: facts and reasons |
| `N` / `P` | next or previous problem, worst first |
| `Q` | quit |

## Tests

```bash
python3 -m unittest
```

## Bonus: Tokenville

The project started as a small isometric pixel-art game: you play Clawd, the orange Claude Code
mascot, wandering around the town of Tokenville.

```bash
python3 town.py
```

Python 3.8+ only. There are no dependencies. Use a big terminal window, or shrink the font
(Cmd − on macOS): each pixel is two columns wide, so more columns means more town.
Truecolor is detected from `$COLORTERM`. Use `--256` to force 256-color mode, or
`--truecolor` to force truecolor.

| Key | Action |
| --- | --- |
| `W` / `↑` | move up-right |
| `D` / `→` | move down-right |
| `S` / `↓` | move down-left |
| `A` / `←` | move up-left |
| `E` / space / enter | talk to villagers, read signs, knock on doors |
| `Q` | quit |

Walk behind a building or tree and Clawd shows through as a dithered silhouette.

### Files

- `iso.py`: isometric projection and the 12×6 diamond tile mask
- `world.py`: the map, buildings, signs, villagers and collision
- `game.py`: grid movement with tweening, wandering villagers, dialogue
- `sprites.py`: Clawd, the villagers, and generated trees and bushes
- `render.py`: draws the scene back to front into an RGB framebuffer
- `term.py`: ANSI output that redraws only changed rows, raw keyboard input
- `town.py`: the game loop
- `snapshot.py`: renders a frame to PNG without a terminal
  (`python3 snapshot.py out.png --at 11,15`)

## Credits

- [Michael Culleton](https://github.com/glaseagle)

