# Rust adapter

Depends on: `../2026-10-01-universal-survey-design.md` (core). Core must be merged first.
You may touch: `lang_rust.py` and `test_lang_rust.py`. Nothing else.
Branch: `lang-rust`, from `towncode-universal`, in its own worktree.

## Scope

| | |
| --- | --- |
| `NAME`, `LABEL` | `"rust"`, `"Rust"` |
| `EXTENSIONS` | `.rs` |
| `GRAMMARS` | `.rs` → `rust` |
| `SHEBANGS` | none |
| `CONFIG` | `Cargo.toml` |
| `FIRE` | `True` (calibrate) |

The node types below are expected. Print a snippet's subtree to confirm each one, and follow
the grammar where it differs.

Read `Cargo.toml` with the standard library's `tomllib`, never with `cargo`:

- `[package] name`;
- `[lib] path`;
- `[[bin]] name/path`;
- `[workspace] members`, with globs matched against tracked folders;
- the keys of `[dependencies]`, `[dev-dependencies]`, `[build-dependencies]` and
  `[workspace.dependencies]`, plus `package = "…"` renames and `path = "…"` local crates.

If a file doesn't parse, ignore it.

## Building grain

One building per file. A Rust file is a module.

## The module tree

Each crate in the repository has a folder (where its `Cargo.toml` is), a name (`[package] name`,
with `-` → `_`), and roots:

- `src/lib.rs`, or `[lib] path`: the library root;
- `src/main.rs`, `src/bin/*.rs`, `src/bin/*/main.rs` and `[[bin]] path`: binary roots;
- `examples/*.rs`, `benches/*.rs` and `tests/*.rs`: each is its own root;
- `build.rs`: a build script root.

From each root, follow `mod name;` declarations (a `mod_item` with no body) to child files:

- In a crate root (any root listed above) or a `mod.rs`: `name.rs` or `name/mod.rs` in the same
  folder.
- In any other file `a.rs`: `a/name.rs` or `a/name/mod.rs`, next to `a.rs`.
- A `#[path = "x.rs"]` attribute on the `mod` overrides the location, relative to the declaring
  file's folder.
- Inline `mod name { … }` creates a module path inside the same file. It doesn't create a file.

The result maps each file to `crate_name::a::b`, and each module path to its file.
`resolver()` builds it from `facts`, from the `mod` declarations `scan` records as
`Import(name, kind="module")`, and from `files`.

## Facts per file

- **Lines and notes:** `line_comment` and `block_comment` nodes. Doc comments count as
  comments.
- **Complexity:** 1, plus:
  - `if_expression`, `match_arm`, `for_expression`, `while_expression` and `loop_expression`;
  - `binary_expression` with `&&` or `||`.

  The `?` operator does not count.
- **Exports:** names of top-level items with a plain `pub` (not `pub(crate)` or `pub(super)`):
  `function_item`, `struct_item`, `enum_item`, `trait_item`, `type_item`, `const_item`,
  `static_item`, `mod_item` and `macro_definition` with `#[macro_export]`. Also `pub use`
  re-exports, as their final names, with a glob counted as `*`.
- **Entry:** binary roots, example roots and `build.rs`.
- **Public:** every library root. A library may be used outside the repository, and the town
  can't tell.
- **Package:** a `mod.rs` or `lib.rs` whose top level holds only `mod` declarations and `use`
  or `pub use` items.
- **Inline tests:** the file has a `mod` item carrying `#[cfg(test)]`, or any function carrying
  `#[test]`.
- **Fire:** `langkit.first_error`. Macro bodies are token trees, so macros don't trigger false
  errors.

## Imports

- `mod name;` gives `Import(name, kind="module")`, a road from parent to child module.
- **`use` declarations:** each leaf of a `use_declaration` tree gives `Import(path)`, as a full
  path. `use a::{b, c::d}` gives `a::b` and `a::c::d`, `use a::*` gives `a::*`, and
  `use a::b as c` gives `a::b`.
- **Paths in code:** a `scoped_identifier` or `scoped_type_identifier` whose first segment is
  `crate`, `self`, `super`, or any lower-case name gives `Import(path, kind="reference")`.
  Types like `Vec::new` and `Self::x` are skipped. Deduplicate per file. `scan` can't see
  `Cargo.toml`, so the resolver decides which first segments are crates.

## Resolution

To resolve a path, make it absolute, then find its file.

**Making it absolute:**

- `crate::x` becomes `<this crate>::x`.
- `self::x` becomes `<this module>::x`.
- `super::x` becomes `<parent module>::x`. Repeated `super` climbs once each.
- A bare first segment is either a module declared in this file, or a module in the crate root
  (2018 edition paths). Otherwise it's a crate name.

**Finding the file:** walk the segments down the module tree. The deepest module path that maps
to a file is the target. Segments after it are items (`crate::a::b::Thing` → the file of
`crate::a::b`). A target equal to the importer gives no road.

**Repository crates.** A crate name that matches another crate in the repository resolves into
that crate's library root and down its tree. A `path =` dependency maps to that folder's crate.

**Standard library:** `std`, `core`, `alloc`, `proc_macro` and `test`. No road and no warehouse.

**External:** a first segment that matches a dependency key (with `-` → `_`, and following
`package =` renames). The warehouse is named after the Cargo dependency key as written.
Anything else unresolved gives nothing; it's probably a local item or a macro.

## Tests

- Integration tests: files under a crate's `tests/` folder are tests. Their `use <crate>::…`
  paths link them to library files, through core.
- `inline_tests` covers unit tests.

## Excluded (`is_excluded`)

- Anything under `target/`.
- Files whose leading comment contains `@generated` or `automatically generated`.

## Required tests

1. `src/lib.rs` with `mod parser;` gives a road from `lib.rs` to `src/parser.rs`.
2. `src/net/mod.rs` with `mod tcp;` reaches `src/net/tcp.rs`. `src/net.rs` with `mod tcp;`
   reaches `src/net/tcp.rs`.
3. `#[path = "imp/unix.rs"] mod sys;` reaches `src/imp/unix.rs`.
4. `use crate::parser::Token;` in `src/main.rs` reaches `src/parser.rs`.
5. `use super::util;` in `src/net/tcp.rs` reaches `src/net/util.rs`, or `src/net.rs` if `util`
   is an inline module there.
6. `use crate::a::{b, c::d};` gives two roads.
7. A two-crate workspace: `crates/app` uses `core_lib::x` and reaches
   `crates/core-lib/src/x.rs`. The package name is `core-lib`, so this tests the `-` → `_` rule.
8. `use std::collections::HashMap;` gives no warehouse. `use serde::Deserialize;`, with `serde` in
   `[dependencies]`, gives warehouse `serde`.
9. A path in code (`crate::config::load()`) gives a road with no `use`.
10. Exports: `pub fn`, `pub struct`, `pub use x::Y` and `pub mod m` count; `pub(crate) fn` and a
    private `fn` don't.
11. Complexity: exact for a fixture with one of each construct.
12. `src/main.rs`, `src/bin/tool.rs` and `build.rs` are entries.
13. A file with `#[cfg(test)] mod tests` has `inline_tests`. It's not untested, and it has an
    annex.
14. `tests/api.rs` using `mycrate::api` puts the test in `src/api.rs`'s `tested_by`.
15. A `lib.rs` with only `mod` and `pub use` lines is `is_package`.
16. A file with a syntax error is on fire. A file whose macro invocation contains odd tokens is
    not.

## Calibration

[BurntSushi/ripgrep](https://github.com/BurntSushi/ripgrep): a workspace with several crates,
inline tests, binaries. Report the usual note, plus how many `use` paths failed to resolve,
with up to ten examples.

## After calibration

- A reference from a module to one of its own ancestors in the `mod` tree is not a road: the
  child is already connected by the `mod` road. References between siblings and cousins stay
  roads (ripgrep: import cycle members went from 78 to 6, all genuine sibling loops).
- `public` covers `src/lib.rs` roots only. A custom `[lib] path` isn't read yet.

## Known limits

- Re-exports aren't followed. A road goes to the module that re-exports a name, not to where
  it's defined.
- `cfg` attributes aren't evaluated. Every platform's modules are in the tree.
- Macro-generated modules and `include!` aren't followed.
