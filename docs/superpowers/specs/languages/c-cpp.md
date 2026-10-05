# C / C++ adapter

Depends on: `../2026-10-01-universal-survey-design.md` (core). Core must be merged first.
You may touch: `lang_cfamily.py` and `test_lang_cfamily.py`. Nothing else.
Branch: `lang-cfamily`, from `towncode-universal`, in its own worktree.

## Scope

| | |
| --- | --- |
| `NAME`, `LABEL` | `"cfamily"`, `"C/C++"` |
| `EXTENSIONS` | `.c .h .cc .cpp .cxx .c++ .hh .hpp .hxx .h++ .ipp .tpp .inl` |
| `GRAMMARS` | `.c` → `c`; every other extension → `cpp`; `.h` is decided by `grammar_for` |
| `grammar_for` | `.h` → `cpp` if the repository has any `.cc`, `.cpp`, `.cxx`, `.c++`, `.hh`, `.hpp`, `.hxx` or `.h++` file, else `c` |
| `SHEBANGS` | none |
| `CONFIG` | `CMakeLists.txt`, `*.cmake`, `Makefile`, `*.mk`, `meson.build`, `compile_commands.json` |
| `FIRE` | `False`. Errors are kept in the inspector, but never become fire (see "Fire") |

Confirm grammar names with `available_languages()`. The node types below are expected. Print a
snippet's subtree to confirm each one, and follow the grammar where it differs.

## Building grain

**A header and its implementation are one building.** Other code includes the header, and the
code behind it lives in the source file.

`unit_of(path, files)`:

- A **header** is its own unit id.
- A **source file** (`.c`, `.cc`, `.cpp`, `.cxx`, `.c++`) joins the header it pairs with. A
  unique match wins, in this order:
  1. A header with the same stem in the same folder.
  2. A mirror under sibling `include/` and `src/` folders. With the header at `include/<h>`
     and the source at `src/<s>`, they pair when the stem of `<s>` equals the stem of `<h>`,
     either as written or without `<h>`'s first folder. For example, `include/fmt/format.h`
     pairs with `src/format.cc`, and `include/a/b.h` with `src/a/b.c`.
- A source file with no unique pair is its own unit.
- `.ipp`, `.tpp` and `.inl` files join the header with their stem in the same folder.
  Otherwise they're their own unit.

Core sums lines, complexity and notes over a unit's members. The source file's include of its
own header becomes a self-road, which core drops.

## Include folders

Read these from `CONFIG` text with regexes. Never run CMake, Make or Meson.

- **CMake:** `include_directories(…)` and `target_include_directories(<target> [SYSTEM]
  [PUBLIC|PRIVATE|INTERFACE] …)`.
  - Replace `${CMAKE_CURRENT_SOURCE_DIR}` and `${CMAKE_CURRENT_LIST_DIR}` with the
    `CMakeLists.txt`'s folder, and `${PROJECT_SOURCE_DIR}` and `${CMAKE_SOURCE_DIR}` with the
    repository root.
  - Paths are relative to the `CMakeLists.txt`'s folder.
  - Skip generator expressions (`$<…>`), and paths with other variables.
- **Make:** `-I<dir>` and `-I <dir>` tokens.
- **Meson:** `include_directories('a', 'b')`.
- **`compile_commands.json`:** `-I` flags.

Then add every tracked folder named `include`, plus `src` and the repository root. Keep only
folders that exist in `files`, in that order, deduplicated.

## Facts per file

- **Lines and notes:** from `comment` nodes.
- **Complexity:** 1, plus:
  - `if_statement`, `for_statement`, `while_statement`, `do_statement`, `case_statement` and
    `conditional_expression`;
  - `binary_expression` with `&&` or `||`;
  - for C++, also `for_range_loop` and `catch_clause`;
  - for both, the preprocessor branches `preproc_if`, `preproc_ifdef` and `preproc_elif`.
- **Exports:**
  - **Headers:** names declared at file scope or inside a `namespace_definition`, at any depth.
    That covers function declarators, the tags of struct, union, enum and class specifiers,
    typedef names, `alias_declaration` names, and macros (`preproc_def`,
    `preproc_function_def`). Not the include guard: a macro defined with no value, directly
    after an `#ifndef` of the same name.
  - **Source files:** names of `function_definition` without `static`, at file or namespace
    scope.
  - A paired unit is named after its header, so core takes only the header's exports. The
    source file's exports count only when it stands alone.
- **Entry:** a `function_definition` named `main`, or `wmain`, `WinMain` or `wWinMain`.
- **Parse error:** `langkit.first_error`, shown in the inspector, never as fire.

## Imports

`preproc_include` gives `Import(path, names=("quote",))` for `"x.h"`, or
`Import(path, names=("angle",))` for `<x.h>`. Includes inside `#if` branches count, because
branches aren't evaluated.

## Resolution

1. **Quoted includes:** the importer's folder first, then each include folder in order. The
   first tracked match wins.
2. **Angle includes:** the include folders in order. The first tracked match wins.
3. **Fallback**, for either form: a tracked header whose path ends with `/<path>` is the
   target, if it is the only one.
4. **System headers:** no road and no warehouse. That means:
   - the C standard headers: `stdio.h`, `stdlib.h`, `string.h`, `stdint.h`, `stddef.h`,
     `stdbool.h`, `stdarg.h`, `limits.h`, `errno.h`, `assert.h`, `math.h`, `time.h`, `ctype.h`,
     `signal.h`, `setjmp.h`, `locale.h`, `float.h`, `inttypes.h`, `wchar.h`, `wctype.h`,
     `complex.h`, `fenv.h`, `iso646.h`, `stdalign.h`, `stdatomic.h`, `stdnoreturn.h`,
     `threads.h`, `uchar.h`, and their `c…` C++ forms;
   - any extensionless angle include (C++ standard: `vector`, `string`, `memory` and so on);
   - POSIX and platform headers: `unistd.h`, `fcntl.h`, `pthread.h`, `dlfcn.h`, `dirent.h`,
     `poll.h`, `netdb.h`, `termios.h`, `sys/*`, `netinet/*`, `arpa/*`, `windows.h`,
     `winsock2.h`, `ws2tcpip.h`, `mach/*` and `CoreFoundation/*`.
5. **External:** any other unresolved angle include. The warehouse is the first path segment,
   or the stem for a single file name (`openssl/ssl.h` → `openssl`, `zlib.h` → `zlib`,
   `boost/asio.hpp` → `boost`, `gtest/gtest.h` → `gtest`). An unresolved quoted include gives
   nothing; it's probably generated at build time.

## Tests

- A file is a test if:
  - it is under a `test`, `tests`, `unittest`, `unittests` or `testing` folder; or
  - its name matches `*_test.*`, `test_*.*`, `*_unittest.*`, `*Test.*` or `*_tests.*`.
- Tests link through their includes, which core resolves.

## Excluded (`is_excluded`)

- Anything under `build/`, `cmake-build-*/` or `out/`.
- `*.pb.h`, `*.pb.cc`, `*.generated.h` and `*_generated.h`.
- Files whose first comment contains `generated by` or `DO NOT EDIT`.

## Fire

`FIRE = False`. The preprocessor makes tree-sitter produce ERROR nodes on valid code: macros
that expand to syntax, or unbalanced `#if` branches. Calibration must report the share of files
with a parse error, per repository. Turning fire on is a later decision for the user, not for
this agent.

## Required tests

1. `src/net.c` with `#include "net.h"` and `src/net.h` form one building `src/net.h`, with
   members `[src/net.h, src/net.c]` and no self-road.
2. Mirror pairing: `include/fmt/format.h` and `src/format.cc` form one building.
3. With two candidate headers for one source file, nothing pairs.
4. `app.c` with `#include "util/str.h"`, `str.h` at `lib/util/str.h`, and
   `include_directories(lib)` in `CMakeLists.txt` reaches `lib/util/str.h`.
5. A `-Ithird/include` in a `Makefile` makes `#include <dep.h>` reach `third/include/dep.h`.
6. A quoted include found through the importer's folder wins over an include folder.
7. The suffix fallback reaches a unique `**/proto/msg.h`. With two matches, nothing.
8. `#include <stdio.h>`, `<vector>` and `<sys/socket.h>` give no warehouse.
   `#include <openssl/ssl.h>` gives warehouse `openssl`.
9. A `.h` file in a repository with a `.cpp` file is parsed with `cpp`; in a pure C repository,
   with `c`.
10. Header exports include functions, a struct, a typedef and a macro, but not the include
    guard. A standalone `.c` file's `static` function is not exported. A paired unit's doors
    are its header's names only.
11. Complexity: exact for one C fixture and one C++ fixture, including `#ifdef`.
12. `int main(void)` is an entry.
13. `tests/net_test.c` including `net.h` puts the test in `src/net.h`'s `tested_by`.
14. `build/gen.h` and `msg.pb.h` are not buildings.
15. A file with a syntax error has a parse error in the inspector, and no fire.

## Calibration

- [redis/hiredis](https://github.com/redis/hiredis): C, with headers beside their sources.
- [fmtlib/fmt](https://github.com/fmtlib/fmt): C++, with the `include/` and `src/` mirror.

Report the usual note, plus the parse-error share per repository.

## After calibration

- `FIRE` stays `False`: 36% of hiredis files and 51% of fmt files have grammar errors on valid
  code, mostly from unexpanded macros and `#if` branches.
- Before an include counts as outside, it tries, in order:
  1. the repository root;
  2. a unique tracked header whose path ends with `/<include>`;
  3. the include without a first segment that names no tracked folder, as in hiredis's
     `<hiredis/hiredis.h>`.

  Two or more matches give neither a road nor a warehouse (hiredis: 47 roads became 112).

## Known limits

- Objective-C (`.m`, `.mm`) stays at floor depth. Objective-C `.h` headers are claimed here
  and may show parse errors; with fire off, that's harmless.
- Macros aren't expanded, and `#if` branches aren't evaluated.
- Calls across units without an include, such as `extern` declarations, give no road.
