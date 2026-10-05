"""Which language each file is in, and the adapters that read them.

Every adapter is listed here up front, so adding one means adding only its own
lang_<name>.py and test_lang_<name>.py. A missing or broken adapter leaves its
files at floor depth.
"""

import fnmatch
import importlib
import os
import re

import floor
import langkit

ADAPTERS = ("python", "javascript", "shell", "go", "jvm", "csharp", "rust", "ruby",
            "cfamily", "swift")
VERSIONED = re.compile(r"[\d.]+$")

_loaded = None
_failed = {}


def adapters():
    """{name: module} for every adapter that imports cleanly, in registry order."""
    global _loaded
    if _loaded is None:
        _loaded = {}
        for name in ADAPTERS:
            try:
                _loaded[name] = importlib.import_module(f"lang_{name}")
            except ModuleNotFoundError as e:
                if e.name == f"lang_{name}":
                    _failed[name] = "no adapter yet"
                elif e.name in ("tree_sitter", "tree_sitter_language_pack"):
                    _failed[name] = "tree-sitter not installed"
                else:
                    _failed[name] = f"adapter failed to load: {e}"
            except Exception as e:
                _failed[name] = f"adapter failed to load: {type(e).__name__}: {e}"
    return _loaded


def failure(name):
    adapters()
    return _failed.get(name)


def reset():
    """Forget loaded adapters and grammars; tests use this after patching the registry."""
    global _loaded
    _loaded = None
    _failed.clear()
    langkit._ready = None


def label(key):
    adapter = adapters().get(key)
    if adapter is not None:
        return adapter.LABEL
    return floor.LABELS.get(key) or key.replace("_", " ").title()


def missing_grammars(adapter):
    return sorted({g for g in getattr(adapter, "GRAMMARS", {}).values()
                   if not langkit.grammar_ready(g)})


def depth_reason(key):
    """None when files in this language are read in full, else why they stay at floor."""
    adapter = adapters().get(key)
    if adapter is None:
        return failure(key) or "no adapter yet"
    if getattr(adapter, "GRAMMARS", None) and not langkit.available():
        return "tree-sitter not installed"
    missing = missing_grammars(adapter)
    if missing:
        return f"grammar not installed: {', '.join(missing)} (run towncode setup)"
    return None


def fire_allowed(adapter, path):
    fire = getattr(adapter, "FIRE", True)
    if fire is True or fire is False:
        return fire
    return os.path.splitext(path)[1] in fire


def grammar_for(adapter, path, files):
    hook = getattr(adapter, "grammar_for", None)
    if hook is not None:
        return hook(path, files)
    return getattr(adapter, "GRAMMARS", {}).get(os.path.splitext(path)[1])


def is_config(path):
    base = os.path.basename(path)
    return any(fnmatch.fnmatchcase(base, pattern)
               for adapter in adapters().values() for pattern in getattr(adapter, "CONFIG", ()))


def configs_of(adapter, files):
    patterns = getattr(adapter, "CONFIG", ())
    return [f for f in files
            if any(fnmatch.fnmatchcase(os.path.basename(f), p) for p in patterns)]


def _shebang_names(text):
    program = floor.interpreter(text)
    if not program:
        return ()
    return (program, VERSIONED.sub("", program))


def classify(path, text):
    """The language key a file is in, or None when it isn't code.

    `text` is only needed for files without an extension, whose shebang decides.
    """
    ext = os.path.splitext(path)[1]
    loaded = adapters()
    for name, adapter in loaded.items():
        if ext and ext in adapter.EXTENSIONS:
            return name
    if not ext:
        names = _shebang_names(text)
        for name, adapter in loaded.items():
            if any(n in getattr(adapter, "SHEBANGS", ()) for n in names):
                return name
        for n in names:
            if n in floor.SHEBANG_LANGUAGES:
                return floor.SHEBANG_LANGUAGES[n]
    if ext in floor.FLOOR_LANGUAGES:
        return floor.FLOOR_LANGUAGES[ext][0]
    if langkit.pack is None:
        return None
    try:
        found = (langkit.pack.detect_language_from_path(path) if ext
                 else langkit.pack.detect_language_from_content(text or ""))
    except Exception:
        return None
    if not found or found in floor.NOT_CODE or found == "python":
        return None
    return found


def status():
    """Rows for `towncode languages`: (label, depth, extensions, grammar note)."""
    rows = []
    for name in ADAPTERS:
        adapter = adapters().get(name)
        if adapter is None:
            exts = sorted(e for e, entry in floor.FLOOR_LANGUAGES.items() if entry[0] == name)
            rows.append((label(name), "floor", " ".join(exts), failure(name) or "no adapter yet"))
            continue
        grammars = sorted(set(getattr(adapter, "GRAMMARS", {}).values()))
        missing = missing_grammars(adapter)
        if not grammars:
            note = "built in"
        elif not langkit.available():
            note = f"{', '.join(grammars)} (needs tree-sitter: see README)"
        elif missing:
            note = f"{', '.join(grammars)} (not installed: run towncode setup)"
        else:
            note = f"{', '.join(grammars)} (ready)"
        rows.append((adapter.LABEL, "floor" if missing else "full",
                     " ".join(adapter.EXTENSIONS), note))
    return rows


def floor_only():
    """Labels of languages drawn at floor depth because no adapter exists for them."""
    return sorted({lbl for key, lbl, _ in floor.FLOOR_LANGUAGES.values() if key not in ADAPTERS})


def setup_grammars():
    return sorted({g for adapter in adapters().values()
                   for g in getattr(adapter, "GRAMMARS", {}).values()})
