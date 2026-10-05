# Shell adapter

Depends on: `../2026-10-01-universal-survey-design.md` (core). Core must be merged first.
You may touch: `lang_shell.py` and `test_lang_shell.py`. Nothing else.
Branch: `lang-shell`, from `towncode-universal`, in its own worktree.

## Scope

| | |
| --- | --- |
| `NAME`, `LABEL` | `"shell"`, `"Shell"` |
| `EXTENSIONS` | `.sh .bash .zsh .ksh .bats` |
| `GRAMMARS` | all → `bash` |
| `SHEBANGS` | `sh`, `bash`, `zsh`, `dash`, `ksh` (also as `env bash` and so on) |
| `CONFIG` | none |
| `FIRE` | `(".sh", ".bash", "")`: never `.zsh`, `.ksh` or `.bats`, whose extra syntax the bash grammar can't parse |

Confirm the grammar name with `available_languages()`. The node types below are expected. Print
a snippet's subtree to confirm each one, and follow the grammar where it differs.

## Building grain

One building per file.

## Facts per file

- **Lines and notes:** from `comment` nodes. The shebang line is not code.
- **Complexity:** 1, plus:
  - `if_statement`, `elif_clause`, `for_statement`, `c_style_for_statement`,
    `while_statement` (which covers `until` in this grammar; check) and `case_item`;
  - `list` nodes joined by `&&` or `||`.
- **Exports:** names from `function_definition`.
- **Entry:** the file starts with a shebang. Shell has no other way to say "run me", and git
  file modes aren't in the model.
- **Parse error:** `langkit.first_error`, for every file. `FIRE` decides which ones burn.

## Imports

- **Source:** `source X` and `. X` give `Import(X, kind="import")`.
- **Run:** a command whose name is a path to a repository script gives
  `Import(X, kind="runs")`. That covers `bash X`, `sh X`, `zsh X` and `exec X`, and also a
  command name that contains `/` or ends in `.sh`.
- **External tools:** any other command name gives `Import(name, kind="reference")`, once per
  distinct name per file. That includes commands inside pipelines, `$( … )` and backticks.
  `Resolution` decides whether it becomes a warehouse.

`X` must reduce to a literal path:

- Literal words and quoted strings are fine.
- A leading "this script's folder" expression is stripped and remembered as "relative to the
  script". That means `$(dirname "$0")`, `$(dirname "${BASH_SOURCE[0]}")`,
  `$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)`, or `${BASH_SOURCE%/*}`.
- So is a variable assigned exactly one of those expressions earlier in the same file (for
  example `DIR=…; source "$DIR/lib.sh"`).
- Any other expansion means the import is skipped.

## Resolution

1. **Relative to the script's folder**, and then relative to the repository root, for `source`
   and `runs` paths. The target must be a tracked file in this language.
2. **A bare file name** (`source lib.sh`) that matches exactly one tracked shell file anywhere
   reaches it. Several matches reach nothing.
3. **Command names**, in this order:
   - a function defined in this file or a sourced file: nothing;
   - a shell builtin or keyword (`cd`, `echo`, `printf`, `read`, `test`, `[`, `export`, `local`,
     `set`, `shift`, `trap`, `exit`, `return`, `true`, `false`, `eval`, `exec`, `source`, `.`,
     `wait` and so on): nothing;
   - a basic utility in the `COMMON` set (POSIX and coreutils: `ls`, `cat`, `grep`, `sed`, `awk`,
     `cut`, `sort`, `uniq`, `head`, `tail`, `tr`, `wc`, `find`, `xargs`, `mkdir`, `rm`, `cp`,
     `mv`, `chmod`, `ln`, `touch`, `date`, `sleep`, `tee`, `basename`, `dirname`, `readlink`,
     `realpath`, `env`, `mktemp`, `pwd`, `which`, `command`, `printf` and so on): nothing;
   - anything else (`git`, `docker`, `aws`, `kubectl`, `jq`, `curl`, `python3`, `npm` and so on):
     an outside name, so a warehouse.

## Tests

- A file is a test if it ends in `.bats`, or it is under a `test` or `tests` folder.
- Bats `load X` and `load "X.bash"` count as `source`.
- `run X` counts as `runs`.
- Tests link through those roads, then by name.

## Excluded

None beyond core.

## Required tests

1. `a.sh` with `source ./lib.sh` reaches `lib.sh`.
2. `bin/tool` (shebang `#!/usr/bin/env bash`, no extension) with
   `. "$(dirname "$0")/../lib/x.sh"` reaches `lib/x.sh`.
3. `DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; source "$DIR/y.sh"` reaches `y.sh`.
4. `source "$HOME/x.sh"` and `source "$1"` reach nothing.
5. `bash scripts/deploy.sh` and `./scripts/deploy.sh` both give a `runs` road.
6. `source lib.sh`, with `lib.sh` unique in the repo, reaches it; with two `lib.sh`, nothing.
7. Calls to `docker`, `aws` and `jq` give warehouses. `echo`, `grep`, `cd` and a locally defined
   function give none.
8. Commands inside `$( … )` and pipelines are found.
9. Exports are the function names; complexity is exact for a fixture with one of each construct.
10. A file with a shebang is an entry; a sourced library without one is not.
11. `test/x.bats` with `load ../lib/x` puts the test in `lib/x.sh`'s `tested_by`.
12. A `.sh` file with a syntax error is on fire. A `.zsh` file using zsh-only syntax is not, and
    neither is a `.bats` file with `@test`. Both still show the parse error in the inspector.

## Calibration

[bats-core/bats-core](https://github.com/bats-core/bats-core): many sourced libraries, scripts
without extensions under `libexec/`, and its own `.bats` tests. Report the usual note, and say
which tools ended up as warehouses.

## After calibration

- `FIRE = (".sh", ".bash")`. The bash grammar mis-parses valid extensionless `libexec/` scripts
  in bats-core, so those show their parse error without burning.
- A command named after a function declared in exactly one other repository file is a road to
  that file. If several files declare it, it gives nothing, and it's never a warehouse. This
  recovers libraries sourced through variables (bats-core: 1 road and 57 warehouses became 30
  roads and 10 warehouses).
- Tools every POSIX system ships (coreutils, findutils, procps, `tar`, `zip`, `sudo`, `sysctl`,
  the `sha*sum` tools) are standard library: no warehouse. Tools a fresh machine has to
  install, ones that call outside services, and platform tools (`launchctl`, `osascript`)
  stay warehouses.

## Known limits

- Sourcing through variables other than the "this folder" idioms is not followed.
- Aliases are not followed.
- Shell embedded in other files (Makefiles, CI YAML, Dockerfiles) is not read.
