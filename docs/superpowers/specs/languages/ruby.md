# Ruby adapter

Depends on: `../2026-10-01-universal-survey-design.md` (core). Core must be merged first.
You may touch: `lang_ruby.py` and `test_lang_ruby.py`. Nothing else.
Branch: `lang-ruby`, from `towncode-universal`, in its own worktree.

## Scope

| | |
| --- | --- |
| `NAME`, `LABEL` | `"ruby"`, `"Ruby"` |
| `EXTENSIONS` | `.rb .rake .ru` |
| `GRAMMARS` | all → `ruby` |
| `SHEBANGS` | `ruby`, `jruby` |
| `CONFIG` | `Gemfile`, `*.gemspec` |
| `FIRE` | `True` (calibrate) |

The node types below are expected. Print a snippet's subtree to confirm each one, and follow
the grammar where it differs.

`Rakefile` has no extension. Core finds it only through a shebang, so it stays at floor depth
unless it has one. That's accepted.

Read `Gemfile` and `*.gemspec` with regexes for the names in `gem "name"`, `add_dependency` and
`add_runtime_dependency` (and the `_development_` forms). Never run Ruby or Bundler.

## Building grain

One building per file.

## Two ways files reach each other

Ruby has explicit loading (`require`) and, in Rails and gems that use Zeitwerk, autoloading by
constant name. The adapter does both.

**Autoload mode is on** when either:

- `Gemfile` or a gemspec names `rails` or `zeitwerk`; or
- any file calls `Zeitwerk::Loader`.

**Autoload roots:**

- every folder directly under `app/` (`app/models`, `app/controllers`, `app/services` and so
  on), and `app/*/concerns`;
- `lib/`.

## Facts per file

- **Lines and notes:** from `comment` nodes, including `=begin`/`=end` blocks.
- **Complexity:** 1, plus:
  - `if`, `unless`, `while`, `until`, `for`, `when`, `rescue` and `conditional` (the ternary);
  - the modifier forms `if_modifier`, `unless_modifier`, `while_modifier`, `until_modifier`
    and `rescue_modifier`;
  - `binary` with `&&`, `||`, `and` or `or`.
- **Declares:** fully qualified names of every `class` and `module`, nesting joined with `::`
  (`module Admin; class User` → `Admin::User`; `class Admin::User` → `Admin::User`). The scope
  is `""`: Ruby names are global and fully qualified.
- **Exports:** public method names of the file's classes and modules:
  - a `def` after a bare `private` or `protected` line is not public;
  - `private :a, :b` and `private def x` hide those names;
  - `def self.x` and methods inside `class << self` are public unless hidden the same way;
  - `attr_reader`, `attr_writer` and `attr_accessor` symbols count as exports.
- **References:** `constant` and `scope_resolution` names used in the file, each with its
  lexical nesting (the list of enclosing `module`/`class` names).
- **Entry:** any of these:
  - a shebang;
  - the file is under `bin/` or `exe/`;
  - it ends in `.rake`, or is `config.ru`.
- **Public:** any of these:
  - the file is a gem's main file (`lib/<gemname>.rb`, where the gem name comes from the
    gemspec);
  - in autoload mode, files under `app/controllers`, `app/jobs`, `app/mailers`,
    `app/channels` or `app/helpers`, and anything under `db/migrate`, `config/initializers` or
    `config/environments`. Rails calls these by convention.
- **Fire:** `langkit.first_error`.

## Imports

- `require "x"` and `require 'x'` give `Import("x")`.
- `require_relative "x"` gives `Import("x", kind="relative")`. Core treats every kind alike;
  the label only tells this resolver which rule to use.
- `load "x.rb"` gives `Import("x.rb", kind="relative")` when it starts with `.`, otherwise
  `Import("x.rb")`.
- `autoload :Name, "x"` gives `Import("x")`.
- Each distinct reference gives `Import(name, kind="reference")`, with the nesting carried in
  `names`. `scan` can't see the `Gemfile`, so it always emits these. The resolver ignores them
  when autoload mode is off.

Only string literals count. Interpolated strings are skipped.

## Resolution

1. **`require_relative`:** against the importer's folder, adding `.rb` if it's missing.
2. **`require "x"`:** try `<root>/x.rb` for each load root. The load roots are every tracked
   `lib/` folder, then the repository root.
3. **References, in autoload mode.** For a reference `Name` with nesting `A::B`, try
   `A::B::Name`, `A::Name`, then `Name`, in the `SymbolIndex` (scope `""`). The first hit is
   the road.
   - If no file declares the name, use Zeitwerk's file rule instead: `Admin::UserMailer`
     becomes `admin/user_mailer.rb` under any autoload root. A unique match is the road.
   - A reference to a constant the file itself declares gives nothing.
4. **Standard library** requires give no road and no warehouse. That covers `json`, `set`,
   `time`, `date`, `fileutils`, `optparse`, `yaml`, `psych`, `erb`, `net/http`, `uri`,
   `securerandom`, `open3`, `tempfile`, `tmpdir`, `pathname`, `logger`, `csv`, `digest`,
   `base64`, `stringio`, `shellwords`, `socket`, `timeout`, `benchmark`, `pp`, `English`,
   `forwardable`, `singleton`, `observer`, `ostruct`, `open-uri`, `zlib` and `openssl`, plus any
   `x/…` under them.
5. **External**, for other unresolved requires. The warehouse is the matching `Gemfile` or
   gemspec name when one equals the require's first segment, ignoring `-` versus `_`
   (`require "active_support/core_ext"` → `activesupport`). Otherwise the first segment as
   written.

## Tests

- A file is a test if it is `spec/**/*_spec.rb`, `test/**/*_test.rb`, or anything under
  `spec/support` or `test/support`.
- Tests link through `require`, `require_relative` and references, through core.
- Then by name, which the floor rule already covers (`user_spec.rb` → `user.rb`).

## Excluded (`is_excluded`)

- `db/schema.rb`.
- Anything under `vendor/`, which core already excludes, and `tmp/`.

## Required tests

1. `lib/a.rb` with `require_relative "b"` reaches `lib/b.rb`.
2. `require "acme/parser"` reaches `lib/acme/parser.rb`.
3. `require "json"` gives no warehouse. With `gem "httparty"` in the `Gemfile`,
   `require "httparty"` gives warehouse `httparty`. With `gem "activesupport"`,
   `require "active_support/core_ext"` gives warehouse `activesupport`.
4. Autoload mode is off without Rails or Zeitwerk: a bare constant reference gives no road.
5. Autoload mode on, `app/controllers/users_controller.rb` referencing `User` reaches
   `app/models/user.rb`.
6. Nesting: inside `module Admin`, a reference to `Report` reaches `app/models/admin/report.rb`
   when `Admin::Report` exists, else `app/models/report.rb`.
7. The Zeitwerk file rule: `Billing::InvoiceMailer`, with no declaration found, reaches
   `app/mailers/billing/invoice_mailer.rb`.
8. Exports:
   - two public `def`s, a bare `private`, then one `def` export 2;
   - `private def x` hides `x`;
   - `attr_reader :name` exports `name`.
9. Complexity: exact for a fixture with one of each construct, modifiers included.
10. These are entries: `bin/setup`, which has a `ruby` shebang and no extension; `exe/tool.rb`,
    which has no shebang; and `lib/tasks/x.rake`.
11. In Rails mode, a controller that nothing references is not abandoned (it's public). A
    model nothing references is abandoned.
12. `spec/models/user_spec.rb` referencing `User` puts the spec in `user.rb`'s `tested_by`.
13. `db/schema.rb` is not a building.
14. A file with a syntax error is on fire.

## Calibration

- [sinatra/sinatra](https://github.com/sinatra/sinatra): require-based, with specs.
- [basecamp/kamal](https://github.com/basecamp/kamal): a Zeitwerk gem.

Report the usual note, plus:

- the share of references resolved in kamal;
- whether autoload mode switched on correctly in each repository.

## After calibration

- ActiveSupport's one-argument forms are explicit loads, in autoload mode or not:
  `autoload :Name` (and `eager_autoload`) loads `<nesting>/<name>` underscored,
  `autoload_under "sub"` inserts `sub`, and `autoload_at "path"` loads that path for every name
  in its block. On rails/rails (5,017 files, 16 s) abandoned went from 769 to 457.
- Rails itself still shows a large import loop. That's real cross-requiring between its
  frameworks: dropping child-to-parent roads would only take 344 cycle members to 258.

## Known limits

- Metaprogramming (`define_method`, `method_missing`, `send`) isn't followed.
- Rails routes aren't parsed into controller roads. Controllers are `public` instead.
- `$LOAD_PATH` changes are ignored.
