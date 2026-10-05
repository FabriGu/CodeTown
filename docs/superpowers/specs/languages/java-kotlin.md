# Java / Kotlin adapter

Depends on: `../2026-10-01-universal-survey-design.md` (core). Core must be merged first.
You may touch: `lang_jvm.py` and `test_lang_jvm.py`. Nothing else.
Branch: `lang-jvm`, from `towncode-universal`, in its own worktree.

Java and Kotlin share one adapter. Mixed projects reference each other's classes, so their
names must live in one symbol index.

## Scope

| | |
| --- | --- |
| `NAME`, `LABEL` | `"jvm"`, `"Java/Kotlin"` |
| `EXTENSIONS` | `.java .kt .kts` |
| `GRAMMARS` | `.java` → `java`; `.kt .kts` → `kotlin` |
| `SHEBANGS` | `kotlin`, `kotlinc` (rare `.main.kts`-style scripts without an extension) |
| `CONFIG` | none needed. Build files are not read: package names and paths carry the structure |
| `FIRE` | `(".java",)`. Kotlin is added only after calibration proves its grammar (see "Fire") |

Confirm grammar names with `available_languages()`. The Kotlin grammar is the community
(fwcd) one, and its node names differ from Java's. Print a snippet's subtree to confirm every
type below, and follow the grammar where it differs.

## Building grain

One building per file.

## Facts per file

**Scope** is the declared package:

- Java: `package_declaration`;
- Kotlin: `package_header`;
- `""` if absent.

**Declares**, for the symbol index:

- Java: names of top-level `class_declaration`, `interface_declaration`, `enum_declaration`,
  `record_declaration` and `annotation_type_declaration`.
- Kotlin: top-level `class_declaration` (classes, interfaces and enums), `object_declaration`,
  `type_alias`, and top-level `function_declaration` and `property_declaration` names.

**Exports:**

- Java: public top-level types, plus the public methods and fields of public top-level types.
- Kotlin: top-level declarations not marked `private` or `internal`, plus the non-private
  members of top-level classes and objects. Kotlin's default visibility is public.

**References:** type and simple identifiers used in the file that are not declared in the file.

- Java: `type_identifier`, plus the receivers of `identifier` in `method_invocation` and
  `field_access`.
- Kotlin: `user_type` identifiers, plus the `simple_identifier` callee and receiver
  expressions.

Deduplicate them, and keep them sorted.

**Complexity**, which is 1 plus:

- Java: `if_statement`, `for_statement`, `enhanced_for_statement`, `while_statement`,
  `do_statement`, `switch_label`, `catch_clause` and `ternary_expression`, and
  `binary_expression` with `&&` or `||`.
- Kotlin: `if_expression`, `for_statement`, `while_statement`, `do_while_statement`,
  `when_entry` and `catch_block`, and `conjunction_expression` and `disjunction_expression`.
  Confirm these names, and also `?:` elvis.

**Entry:**

- Java: a `public static void main(String[] …)` method.
- Kotlin: a top-level `fun main`, or a `.kts` script.

**Parse error:** `langkit.first_error`, for both languages. `FIRE` decides which ones burn.

## Imports

- **Java:**
  - `import a.b.C;` gives `Import("a.b.C")`;
  - `import static a.b.C.m;` gives `Import("a.b.C")`;
  - `import a.b.*;` gives `Import("a.b.*")`.
- **Kotlin:** `import a.b.C`, `import a.b.C as D` and `import a.b.*` take the same forms.
  Kotlin can import a top-level function or property (`import a.b.f`). That resolves like a
  type, through the index.
- **Same-package names:** `scan` can't see other files, so each distinct reference gives
  `Import(name, kind="reference")`. The resolver keeps the ones another file declares in the
  same package. Neither language imports these.

## Resolution

Build one `SymbolIndex` from every file's `(scope, declared name, path)`, Java and Kotlin
together.

1. **A single import `a.b.C`:** `lookup("a.b", "C")`. For a nested or static import whose last
   segment isn't found, drop segments from the right until a lookup hits
   (`a.b.Outer.Inner` → `a.b` / `Outer`).
2. **A wildcard `a.b.*`:** for each of the file's references, `lookup("a.b", name)`. Each hit
   is a road. A wildcard that matches no references gives no road and no warehouse.
3. **A reference in the same package:** `lookup(own scope, name)`, excluding the file itself.
4. **Standard library:** specs under `java.`, `javax.`, `jdk.`, `sun.`, `kotlin.` (but not
   `kotlinx.`) and `org.w3c.`, that no repository file declares. No road and no warehouse.
5. **External:** any other unresolved import. The package name is its first two segments
   (`org.junit.jupiter.api.Test` → `org.junit`, `com.google.gson.Gson` → `com.google`).
   `android.` and `androidx.` imports become `android` and `androidx`.

## Tests

- A file is a test if any of these holds:
  - it is under a `src/test/`, `src/androidTest/`, `src/testFixtures/` or `src/integrationTest/`
    folder;
  - its name ends in `Test`, `Tests`, `IT` or `Spec` before the extension.
- Tests in the same package reference classes directly. Core treats those `reference` roads like
  imports, so the class gets an annex.

## Excluded (`is_excluded`)

- Files under any `build/`, `generated/` or `generated-sources/` folder.
- Files whose leading comment contains `@generated` or `Generated by`.

## Fire

- `FIRE` starts as `(".java",)`.
- If calibration shows the Kotlin grammar parses moshi's Kotlin with no false errors, make it
  `(".java", ".kt", ".kts")`, and say so in the calibration note. If it doesn't, leave Kotlin
  out, and list the constructs that failed.

## Required tests

1. `com/a/App.java` (`package com.a; import com.b.Util;`) reaches `com/b/Util.java`. Folder
   layout doesn't matter: put `Util.java` under `lib/`, and it still resolves by package.
2. `import static com.b.Util.helper;` reaches `Util.java`.
3. `import com.b.*;`, when the file uses `Util`, reaches only `Util.java`. It doesn't reach the
   other `com.b` files that the file doesn't use.
4. Two files in package `com.a` reach each other through same-package references, with no
   import.
5. A nested import `com.b.Outer.Inner` reaches `Outer.java`.
6. A Kotlin file `import com.b.Util` reaches the Java file `Util.java`, and a Java file
   referencing a Kotlin class in its own package reaches the `.kt` file.
7. A Kotlin top-level function import, `import com.b.formatName`, reaches the `.kt` file that
   declares it.
8. `import java.util.List` and `import kotlin.collections.List` give no warehouse.
   `import org.junit.jupiter.api.Test` gives warehouse `org.junit`.
9. Two files declaring `com.a.Dup`: lookups for `Dup` reach nothing, because the match is
   ambiguous.
10. Exports:
    - a Java public class with 2 public methods, 1 private method and 1 public field exports
      the class plus 3;
    - a Kotlin file with a private top-level function exports it not at all.
11. Complexity: exact for one Java fixture and one Kotlin fixture.
12. Entries:
    - Java `public static void main(String[] args)` is an entry;
    - a Java non-static `main` is not;
    - Kotlin `fun main()` is an entry.
13. `src/test/java/com/a/AppTest.java` referencing `App` puts the test in `App.java`'s
    `tested_by`.
14. `build/generated/X.java` is not a building.
15. A Java file with a syntax error is on fire. A Kotlin file with a syntax error shows its
    parse error in the inspector, and is on fire only if calibration added Kotlin to `FIRE`.
    The test asserts whichever `FIRE` says.

## Calibration

- [google/gson](https://github.com/google/gson): Java, Maven layout, wildcard imports in tests.
- [square/moshi](https://github.com/square/moshi): mixed Kotlin and Java.

Report the usual note, plus:

- the Kotlin false-error findings, and the `FIRE` value they led to;
- the share of references that resolved.

## After calibration

- `FIRE = (".java", ".kt", ".kts")`. The Kotlin grammar parsed all 156 JVM files in moshi
  without an error, so Kotlin earned fire.

## Known limits

- Overloads, generics and inner-class scoping are not modelled. Resolution stops at the
  top-level type.
- Kotlin extension functions and `typealias` chains are resolved by name only.
- Gradle and Maven module boundaries aren't read. The packages carry the structure.
