# Swift adapter

Depends on: `../2026-10-01-universal-survey-design.md` (core). Core must be merged first.
You may touch: `lang_swift.py` and `test_lang_swift.py`. Nothing else.
Branch: `lang-swift`, from `towncode-universal`, in its own worktree.

## Scope

| | |
| --- | --- |
| `NAME`, `LABEL` | `"swift"`, `"Swift"` |
| `EXTENSIONS` | `.swift` |
| `GRAMMARS` | `.swift` → `swift` |
| `SHEBANGS` | `swift` |
| `CONFIG` | `Package.swift` |
| `FIRE` | `False`, until calibration proves the grammar (see "Fire") |

Confirm the grammar name with `available_languages()`. The grammar is the community
(alex-pinkus) one. Print a snippet's subtree to confirm every node type below, and follow the
grammar where it differs.

## Building grain

One building per file. `Package.swift` is a manifest, not a building: `is_excluded` returns True
for it.

## Swift modules

Swift files see every other file in their module without imports. So the adapter first decides
which module each file belongs to.

**With a `Package.swift`.** Parse it with the swift grammar, as text. Never run `swift`. Find
calls to `.target`, `.executableTarget`, `.testTarget`, `.macro` and `.plugin`, and read:

- the `name:` string literal;
- the `path:` string literal, if any.

A target's folder is its `path:`. Without one, it's `Sources/<name>`, or `Tests/<name>` for a
`.testTarget`, relative to `Package.swift`'s folder.

Each `.swift` file belongs to the target with the deepest folder containing it. A repository may
have several `Package.swift` files.

**Without one** (an Xcode project): each top-level folder holding `.swift` files is one module,
named after the folder. Files at the root form a module named `(root)`. This is an
approximation; the calibration note should say how it looks.

## Facts per file

- **Lines and notes:** from `comment` and `multiline_comment` nodes.
- **Complexity:** 1, plus:
  - `if_statement`, `guard_statement`, `for_statement`, `while_statement`,
    `repeat_while_statement`, `switch_entry`, `catch_block` and `ternary_expression`;
  - `conjunction_expression` (`&&`), `disjunction_expression` (`||`) and
    `nil_coalescing_expression` (`??`).
- **Scope:** the file's module name, from the section above.
- **Declares:** top-level type names (`class_declaration`, which in this grammar also covers
  `struct`, `enum`, `actor` and `extension`; check which keyword a node carries), plus
  `protocol_declaration`, `typealias_declaration`, and top-level `function_declaration` and
  `property_declaration`. An `extension` declares nothing.
- **Exports:** declarations not marked `private` or `fileprivate`, at the top level, plus the
  members of top-level types and extensions. Swift's default `internal` is visible to every file
  in the module, so it counts as a door.
- **References:** `type_identifier` and `simple_identifier` names used in type positions,
  inheritance clauses, call expressions and attributes. Not names the file declares itself.
  Deduplicate.
- **Entry:** any of these:
  - a type carrying the `@main` attribute;
  - a file named `main.swift`;
  - a file in an `.executableTarget` with top-level statements;
  - a shebang.
- **Public:** the file has any `public` or `open` declaration. Library products are used
  outside the repository.
- **Parse error:** `langkit.first_error`. `FIRE` decides whether it burns.

## Imports

- `import X`, `@testable import X`, and kind imports like `import struct X.Y` give `Import("X")`.
  These name a module, not a file.
- Each reference gives `Import(name, kind="reference")`.

## Resolution

Build a `SymbolIndex` of `(module, declared name, path)`.

1. **A reference:** `lookup(own module, name)` first, then `lookup(M, name)` for each module `M`
   the file imports that is a repository module. The first hit is the road. The file itself
   gives nothing.
2. **`import X` of a repository module** gives no road on its own. Roads come from references.
   Record nothing for it.
3. **System modules:** no road and no warehouse. That covers `Swift`, `Foundation`, `UIKit`,
   `AppKit`, `SwiftUI`, `Combine`, `CoreData`, `CoreGraphics`, `CoreFoundation`, `CoreImage`,
   `CoreLocation`, `MapKit`, `AVFoundation`, `Dispatch`, `os`, `OSLog`, `Darwin`, `Glibc`,
   `Musl`, `WinSDK`, `XCTest`, `Testing`, `Observation`, `SwiftData`, `StoreKit`, `WebKit`,
   `Security`, `Network`, `CryptoKit`, `UniformTypeIdentifiers` and `_Concurrency`.
4. **External:** any other imported module. The warehouse is named after the package that
   provides it, when `Package.swift` makes that clear: a `.product(name: "X", package: "P")`
   dependency gives `P`. Otherwise it's the module name.

## Tests

- A file is a test if:
  - it belongs to a `.testTarget`; or
  - it is under a `Tests` folder; or
  - it imports `XCTest` or `Testing`.
- Tests link through references, through core.

## Excluded (`is_excluded`)

- `Package.swift`.
- Anything under `.build/`, `DerivedData/` or `Pods/`.
- Files whose first comment contains `generated` and `DO NOT EDIT`.

## Fire

`FIRE` starts as `False`. Newer syntax (macros, `consume`, typed throws) is the risk.

If calibration shows the grammar parses swift-argument-parser with no false errors, set `FIRE`
to `True`, and say so in the calibration note. If it doesn't, leave it `False`, and list the
constructs that failed.

## Required tests

1. A `Package.swift` with `.target(name: "Core")` and
   `.executableTarget(name: "App", dependencies: ["Core"])` puts
   `Sources/Core/*.swift` in module `Core` and `Sources/App/*.swift` in `App`.
2. A target with `path: "Lib/Core"` uses that folder.
3. Two files in module `Core` reach each other through a type reference, with no import.
4. `Sources/App/main.swift` with `import Core`, using `Parser`, reaches `Sources/Core/Parser.swift`.
   Without `import Core`, it doesn't.
5. A struct, an enum, an actor and a protocol are all declared, but an `extension Parser` in
   another file is not. A reference to `Parser` reaches only the declaring file.
6. The same name declared in two files of one module reaches nothing.
7. `import Foundation` and `import SwiftUI` give no warehouse. With
   `.product(name: "ArgumentParser", package: "swift-argument-parser")`,
   `import ArgumentParser` gives warehouse `swift-argument-parser`.
8. Exports: `private` and `fileprivate` members are not exported. `internal`, `public` and `open`
   members are.
9. Complexity: exact for a fixture with one of each construct, `guard` included.
10. `@main struct App`, a `main.swift` and a shebang script are entries.
11. `Tests/CoreTests/ParserTests.swift` (a `.testTarget`, `@testable import Core`, references
    `Parser`) puts the test in `Parser.swift`'s `tested_by`.
12. Without a `Package.swift`, the top-level folders `App/` and `Shared/` become modules, and a
    reference from `App` to a type in `Shared` resolves only if `App` imports `Shared`. Within
    one folder, references always resolve.
13. `Package.swift` and `.build/x.swift` are not buildings.
14. A file with a syntax error shows its parse error in the inspector, and is on fire only if
    `FIRE` is `True`. The test asserts whichever `FIRE` says.

## Calibration

[apple/swift-argument-parser](https://github.com/apple/swift-argument-parser): several targets,
test targets, examples. Report the usual note, plus:

- the parse-error findings, and the `FIRE` value they led to;
- the share of references resolved.

## After calibration

- `FIRE` stays `False`. The grammar reports errors on nine valid files in
  swift-argument-parser: `for try await`, Swift Testing macros and `#_sourceLocation`.
- `Package.swift` is read as text through core's hooks. `.testTarget` files are tests
  (`test_files`). In `.executableTarget` folders, top-level code or `@main` makes an entry
  point. In library targets, top-level `public` or `open` types make a file `public`
  (`enrich`). `path:` arguments are honoured. Without a `Package.swift`, folder heuristics
  apply.

## Known limits

- Xcode project files (`project.pbxproj`) aren't read. Without `Package.swift`, folders
  approximate modules.
- Overloads, generics and protocol conformances aren't modelled.
- Calls to members defined in `extension`s resolve to the extended type's declaring file, by
  name only.
