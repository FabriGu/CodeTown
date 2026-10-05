"""Towncode: survey a repository into a model, and walk the town drawn from it.

    python3 towncode.py survey PATH [--check-untouched]
    python3 towncode.py view PATH [--256] [--layout roles] [--session [TRANSCRIPT]]
    python3 towncode.py watch PATH [--zoom district]
    python3 towncode.py watch PATH --events
    python3 towncode.py snapshot PATH OUT.png [--zoom town] [--at MODULE] [--size WxH]
                                 [--layout roles] [--session [TRANSCRIPT]]
    python3 towncode.py snapshot PATH OUT.png --watch
    python3 towncode.py languages
    python3 towncode.py setup

The surveyed repository is only read. Output goes to .survey/ next to this
file, or to $TOWNCODE_SURVEY_DIR, and never inside the repository. Watch
also reads the repository's worktrees and writes only watch.json in the
survey folder. Only `setup` uses the network: it downloads the parser
grammars the adapters need. `--session` reads an agent transcript under
`~/.claude` or `~/.cursor` (the newest for the repository when none is
named). It shows what that session changed, and what imports it.
"""

import argparse
import hashlib
import os
import queue
import subprocess
import sys
import time
import types
from functools import partial
from importlib import metadata

import crowd
import focus
import livetown
import langkit
import langs
import problems
import session
import snapshot
import survey
import term
import townjson
import untouched
import viewer
import webserve
from layers import Rows
from plat import Plat, by_roles
from repo import Repo
from roads import Roads
from townmap import TownMap

HERE = os.path.dirname(os.path.abspath(__file__))
REPORT_LIMIT = 10
DISTRICTS, ROLES = "districts", "roles"
LAYOUTS = [DISTRICTS, ROLES]


def _n(count, word):
    return f"{count} {word}" if count == 1 else f"{count} {word}s"


def survey_root():
    return os.environ.get("TOWNCODE_SURVEY_DIR") or os.path.join(HERE, ".survey")


def output_dir(repo_root):
    real = os.path.realpath(repo_root)
    tag = hashlib.sha256(real.encode("utf-8")).hexdigest()[:8]
    return os.path.join(survey_root(), f"{os.path.basename(real)}-{tag}")


def _inside(path, root):
    path, root = os.path.realpath(path), os.path.realpath(root)
    return path == root or path.startswith(root + os.sep)


def _require_repo(path):
    if not os.path.exists(os.path.join(path, ".git")):
        raise SystemExit(f"not a git repository: {path}")


def _fingerprint(repo_root, tracked):
    """Hash tracked files and git's own files; only stat the rest, never open them."""
    return untouched.fingerprint(
        repo_root, hashable=lambda rel: rel in tracked or rel.startswith(".git" + os.sep))


def _saved(path, load, what, remedy):
    """Load and update a saved file; a damaged one stops the run and is left as it is."""
    try:
        return load(path)
    except (ValueError, TypeError, KeyError, AttributeError) as e:
        raise SystemExit(f"cannot read saved {what} {path}: {e}. Delete it to {remedy}.") from e


def _watch_town(repo_root):
    _require_repo(repo_root)
    out = output_dir(repo_root)
    if _inside(out, repo_root):
        raise SystemExit(f"refusing to write inside the surveyed repository: {out}")
    model = survey.survey(repo_root)
    rows_path = os.path.join(out, "rows.json")
    plat_path = os.path.join(out, "plat.json")
    rows = _saved(rows_path, lambda p: Rows.load(p).update(model), "rows", "rebuild the rows")
    plat = _saved(plat_path, lambda p: Plat.load(p).update(model, rows), "plat",
                  "lay the town out again")
    return model, rows, plat, out


def run(repo_root):
    model, rows, plat, out = _watch_town(repo_root)
    os.makedirs(out, exist_ok=True)
    model.save(os.path.join(out, "model.json"))
    rows.save(os.path.join(out, "rows.json"))
    plat.save(os.path.join(out, "plat.json"))
    return model, rows, plat, out


def town(model, rows, plat, layout=DISTRICTS, changed=None, sites=()):
    """The viewer for a surveyed town; changed is a session's focus, sites its new files."""
    found = problems.find(model, rows)
    if layout == ROLES:
        plat, rows = by_roles(model, rows)
    tmap = TownMap(model, plat, rows, found, sites)
    return viewer.Viewer(tmap, Roads(tmap, model, found), model, found, changed)


def _session(args, model):
    """(focus, new files) for --session: the transcript named, or the newest for the repo."""
    if args.session is None:
        return None, ()
    if args.session == "":
        found = session.transcripts(args.path)
        transcript = found[-1] if found else None
    else:
        transcript = args.session
    if not transcript:
        raise SystemExit(f"no Claude Code or Cursor transcript found for {args.path}")
    if not os.path.isfile(transcript):
        raise SystemExit(f"no such transcript: {transcript}")
    steps = session.load(transcript, args.path)
    changed = focus.changed(model, focus.changed_by(steps, model))
    return changed, focus.unbuilt(steps, model, Repo(args.path).files())


def _session_note(v, sites):
    return f"{v.session_line()}; {_n(len(sites), 'new file')} not committed yet"


def _versions():
    found = []
    for package in ("tree-sitter", "tree-sitter-language-pack"):
        try:
            found.append(f"{package} {metadata.version(package)}")
        except metadata.PackageNotFoundError:
            pass
    return ", ".join(found)


def languages_line(model):
    """'Languages: Python 149 full, Shell 10 floor (no adapter yet)', biggest first."""
    counts = {}
    for m in model.modules.values():
        if m.kind != "unsurveyed":
            key = (m.lang, m.depth)
            counts[key] = counts.get(key, 0) + 1
    parts = []
    for (lang, depth), n in sorted(counts.items(), key=lambda x: (-x[1], x[0])):
        text = f"{langs.label(lang)} {n} {depth}"
        reason = langs.depth_reason(lang) if depth == "floor" else None
        parts.append(f"{text} ({reason})" if reason else text)
    return "Languages: " + (", ".join(parts) if parts else "none found")


def report(model, rows, found):
    counts = {k: len(model.of_kind(k)) for k in ("source", "test", "unsurveyed")}
    lines = [f"{model.repo}: {_n(counts['source'], 'module')}, {_n(counts['test'], 'test')}, "
             f"{_n(counts['unsurveyed'], 'unsurveyed file')}, {_n(len(model.edges), 'road')}, "
             f"{_n(len(model.externals), 'outside package')}", languages_line(model)]
    versions = _versions()
    if versions:
        lines.append(f"Parsers: {versions}")
    lines += ["", "Districts, back row first:"]
    sizes = {}
    for m in model.of_kind("source"):
        sizes[m.district] = sizes.get(m.district, 0) + 1
    for name in sorted(sizes, key=lambda d: (rows.districts.get(d, 0), d)):
        lines.append(f"  row {rows.districts.get(name, 0)}  {name} ({_n(sizes[name], 'module')})")
    lines += ["", "Problems, worst first:" if found else "No problems found."]
    groups = {}
    for x in found:
        groups.setdefault(x.kind, []).append(x)
    for kind in problems.KINDS:
        group = groups.get(kind, [])
        if not group:
            continue
        lines.append(f"{kind} ({len(group)})")
        lines += [f"  {x.module}: {x.reason}" for x in group[:REPORT_LIMIT]]
        if len(group) > REPORT_LIMIT:
            lines.append(f"  ... and {len(group) - REPORT_LIMIT} more")
    return "\n".join(lines)


def _survey(args):
    tracked = set(Repo(args.path).files()) if args.check_untouched else None
    before = _fingerprint(args.path, tracked) if args.check_untouched else None
    model, rows, _, out = run(args.path)
    print(report(model, rows, problems.find(model, rows)))
    print(f"\nsaved to {out}")
    if before is None:
        return 0
    diff = untouched.differences(before, _fingerprint(args.path, tracked))
    if diff:
        print(f"untouched: NO, {sum(len(v) for v in diff.values())} paths differ")
        for change, paths in diff.items():
            print(f"  {change}: {', '.join(paths[:REPORT_LIMIT])}")
        return 1
    print(f"untouched: yes, {len(before)} paths identical before and after")
    return 0


def _browser(args):
    """Serve the town in 3D on this machine, and open it in the browser."""
    model, rows, plat, _ = run(args.path)
    changed, sites = _session(args, model)
    v = town(model, rows, plat, args.layout, changed, sites)
    name = os.path.basename(os.path.realpath(args.path))
    site = webserve.Site(townjson.town(v.m, v.roads, v.describe, repo=name),
                         partial(townjson.selection, v.m, v.roads, v.model))
    return webserve.serve(site, port=args.port, open_browser=not args.no_open)


def _view(args):
    if args.browser:
        return _browser(args)
    if not sys.stdin.isatty():
        raise SystemExit("towncode view needs an interactive terminal.")
    model, rows, plat, out = run(args.path)
    changed, sites = _session(args, model)
    v = town(model, rows, plat, args.layout, changed, sites)
    truecolor = term.supports_truecolor() and not args.force256
    try:
        viewer.run(v, truecolor)
    except KeyboardInterrupt:
        pass
    note = f" {_session_note(v, sites)}." if changed is not None else ""
    print(f"{model.repo}: {_n(len(v.found), 'problem')}.{note} Saved to {out}")
    return 0


def _parse_size(size):
    parts = size.split("x")
    if len(parts) != 2:
        raise SystemExit(f"--size must be WxH pixels, got {size!r}")
    try:
        w, h = int(parts[0]), int(parts[1])
    except ValueError:
        raise SystemExit(f"--size must be WxH pixels, got {size!r}")
    if w <= 0 or h <= 0:
        raise SystemExit(f"--size must be WxH pixels, got {size!r}")
    return w, h


def _watch_live(args, *, home="~", survey_dir=None, clock=time.monotonic, watch_obj=None,
                resurvey_runner=None):
    """Everything watch --browser runs, wired but not started."""
    import watch as watch_mod
    model, rows, plat, out = _watch_town(args.path)
    found = problems.find(model, rows)
    tmap = TownMap(model, plat, rows, found)
    sd = survey_dir or out
    w = watch_obj or watch_mod.Watch(args.path, home=home, survey_dir=sd, model=model)
    try:
        repo_name = os.path.basename(os.path.realpath(args.path))
        live = livetown.LiveTown(tmap, Roads(tmap, model, found), model, rows, plat, repo_name,
                                 w.state().main_tip, args.path, w.clock,
                                 resurvey_runner=resurvey_runner)
        director = crowd.CameraDirector(livetown.TargetRecorder(), live.crowd, tmap)
        snapshots = queue.Queue()
        poller = livetown.WatchPoller(w, snapshots, clock)
        live.note_resurvey = lambda m, tip: poller.inbox.put((m, tip))

        def build_town(lt):
            v = viewer.Viewer(lt.m, lt.roads, lt.model, lt.found)
            return (townjson.town(lt.m, lt.roads, v.describe, repo=repo_name,
                                  version=lt.version, live=True),
                    partial(townjson.selection, lt.m, lt.roads, lt.model))

        site = webserve.LiveSite(*build_town(live))
        sim = webserve.Simulation(live, director, site, snapshots, build_town, clock=clock)
        sim.step_once(0.0, 0.0)
    except Exception:
        if watch_obj is None:
            w.close()
        raise
    return types.SimpleNamespace(live=live, director=director, site=site, sim=sim,
                                 poller=poller, watch=w, snapshots=snapshots)


def _watch_browser(args, *, home="~", survey_dir=None, serve=None, clock=time.monotonic):
    """watch --browser: poll and simulate on threads, serve until Ctrl-C, then close the watch."""
    lw = _watch_live(args, home=home, survey_dir=survey_dir, clock=clock)
    lw.poller.start()
    lw.sim.start()

    def close():
        lw.sim.stop()
        lw.poller.close_event.set()
        lw.sim.join(timeout=2)
        lw.poller.join(timeout=2)
        lw.watch.close()

    return (serve or webserve.serve)(lw.site, port=args.port, open_browser=not args.no_open,
                                     on_close=close)


def _watch_viewer(args, *, home="~", survey_dir=None, resurvey_runner=None):
    import watch as watch_mod
    model, rows, plat, out = _watch_town(args.path)
    found = problems.find(model, rows)
    tmap = TownMap(model, plat, rows, found)
    sd = survey_dir or out
    w = watch_mod.Watch(args.path, home=home, survey_dir=sd, model=model)
    try:
        tip = w.state().main_tip
        repo_name = os.path.basename(os.path.realpath(args.path))
        zoom = getattr(args, "zoom", viewer.DISTRICT)
        v = viewer.WatchViewer(
            tmap, Roads(tmap, model, found), model, rows, plat,
            repo_name, tip, sd, args.path, w, zoom=zoom,
            resurvey_runner=resurvey_runner)
    except Exception:
        w.close()
        raise
    return v, w


def _snapshot(args, *, home="~", survey_dir=None):
    if _inside(args.out, args.path):
        raise SystemExit(f"refusing to write inside the surveyed repository: {args.out}")
    w, h = _parse_size(args.size)
    if getattr(args, "watch", False):
        if args.at:
            raise SystemExit("snapshot --watch cannot be combined with --at")
        v, watch_obj = _watch_viewer(
            args, home=home, survey_dir=survey_dir, resurvey_runner=lambda fn: fn())
        try:
            watch_obj.poll()
            v.ingest(viewer.WatchSnapshot([], watch_obj.state()))
            snapshot.write_png(args.out, v.frame(w, h), args.scale)
        finally:
            watch_obj.close()
        print(f"wrote {args.out}")
        return 0
    model, rows, plat, _ = run(args.path)
    changed, sites = _session(args, model)
    v = town(model, rows, plat, args.layout, changed, sites)
    if not args.at:
        v.select_focuses = False
    if args.at:
        tile = v.m.centre(args.at)
        if tile is None:
            raise SystemExit(f"no building or plot for {args.at}")
        v.cursor, v.problem = tile, None
        v.sync_camera()
    v.zoom = args.zoom
    snapshot.write_png(args.out, v.frame(w, h), args.scale)
    if changed is not None:
        print(_session_note(v, sites))
    print(f"wrote {args.out}")
    return 0


def _languages(args):
    rows = langs.status()
    width = max(len(r[0]) for r in rows)
    ext_width = max(len(r[2]) for r in rows)
    for label, depth, exts, note in rows:
        print(f"{label:<{width}}  {depth:<5}  {exts:<{ext_width}}  {note}")
    print(f"\nFloor only (no adapter): {', '.join(langs.floor_only())}")
    if not langkit.available():
        print("\ntree-sitter is not installed: every language but Python stays at floor depth.")
    return 0


def _format_event(event):
    agent = event.agent.id if event.agent else "-"
    path = event.path or "-"
    return f"{event.kind}\t{agent}\t{path}"


def _watch(args, sleep=time.sleep, *, home="~", survey_dir=None):
    import watch as watch_mod
    if getattr(args, "browser", False):
        if args.events:
            raise SystemExit("watch --browser can't be combined with --events")
        return _watch_browser(args, home=home, survey_dir=survey_dir)
    if args.events:
        w = watch_mod.Watch(args.path, home=home, clock=None, survey_dir=survey_dir)
        try:
            while True:
                for event in w.poll():
                    print(_format_event(event))
                sys.stdout.flush()
                sleep(1)
        except KeyboardInterrupt:
            pass
        except BrokenPipeError:
            sys.stdout = open(os.devnull, "w")
        finally:
            w.close()
        return 0
    if not sys.stdin.isatty():
        raise SystemExit("towncode watch needs an interactive terminal.")
    v, w = _watch_viewer(args, home=home, survey_dir=survey_dir)
    truecolor = term.supports_truecolor()
    try:
        viewer.run_watch(v, w, truecolor)
    except KeyboardInterrupt:
        pass
    finally:
        w.close()
    return 0


def _setup(args):
    if not langkit.available():
        raise SystemExit("tree-sitter is not installed. Run: python3 -m venv .venv && "
                         ".venv/bin/pip install -r requirements.txt")
    names = langs.setup_grammars()
    if not names:
        print("No adapter needs a grammar yet.")
        return 0
    langkit.pack.download(names)
    langs.reset()
    missing = [n for n in names if not langkit.grammar_ready(n)]
    print(f"Grammars ready: {', '.join(n for n in names if n not in missing) or 'none'}")
    print(f"Cache: {langkit.pack.cache_dir()}")
    print(f"Versions: {_versions()}")
    if missing:
        print(f"Still missing: {', '.join(missing)}")
        return 1
    return 0


def _town_options(cmd):
    cmd.add_argument("--layout", choices=LAYOUTS, default=DISTRICTS,
                     help="districts by folder (default), or roles: front door, main street, "
                          "scripts, and what nothing imports")
    cmd.add_argument("--session", nargs="?", const="", metavar="TRANSCRIPT",
                     help="show what an agent session changed and what imports it "
                          "(default: the repository's newest transcript)")


def _parser():
    parser = argparse.ArgumentParser(prog="towncode")
    commands = parser.add_subparsers(dest="command", required=True)
    cmd = commands.add_parser("survey", help="survey a git repository without changing it")
    cmd.add_argument("path")
    cmd.add_argument("--check-untouched", action="store_true",
                     help="fingerprint the repository before and after; fail on any change")
    cmd = commands.add_parser("view", help="survey a repository, then walk its town")
    cmd.add_argument("path")
    cmd.add_argument("--256", dest="force256", action="store_true", help="force 256 colours")
    cmd.add_argument("--browser", action="store_true",
                     help="show the town in 3D in a browser tab on this machine")
    cmd.add_argument("--port", type=int, default=webserve.DEFAULT_PORT,
                     help=f"port for --browser (default {webserve.DEFAULT_PORT}; 0 picks any free port)")
    cmd.add_argument("--no-open", action="store_true",
                     help="with --browser, print the address without opening a browser")
    _town_options(cmd)
    snap = commands.add_parser("snapshot", help="survey a repository and draw its town to a PNG")
    snap.add_argument("path")
    snap.add_argument("out")
    snap.add_argument("--zoom", choices=viewer.ZOOMS, default=viewer.TOWN)
    snap.add_argument("--at", help="module to centre on (default: the worst problem)")
    snap.add_argument("--size", default="160x90", help="frame in pixels, WxH")
    snap.add_argument("--scale", type=int, default=4)
    snap.add_argument("--watch", action="store_true",
                      help="one frame of live watch state (no terminal required)")
    _town_options(snap)
    commands.add_parser("languages", help="list the languages read in full and at floor depth")
    commands.add_parser("setup", help="download the parser grammars (the only network use)")
    cmd = commands.add_parser("watch", help="watch agents working in a git repository")
    cmd.add_argument("path")
    cmd.add_argument("--browser", action="store_true",
                     help="watch in 3D in a browser tab on this machine")
    cmd.add_argument("--port", type=int, default=webserve.DEFAULT_PORT,
                     help=f"port for --browser (default {webserve.DEFAULT_PORT}; 0 picks any free port)")
    cmd.add_argument("--no-open", action="store_true",
                     help="with --browser, print the address without opening a browser")
    cmd.add_argument("--events", action="store_true", help="stream lifecycle events")
    cmd.add_argument("--zoom", choices=viewer.ZOOMS, default=viewer.DISTRICT)
    return parser


COMMANDS = {"survey": _survey, "view": _view, "snapshot": _snapshot,
            "languages": _languages, "setup": _setup, "watch": _watch}


def main(argv=None):
    args = _parser().parse_args(argv)
    try:
        if hasattr(args, "path"):
            _require_repo(args.path)
        return COMMANDS[args.command](args)
    except subprocess.CalledProcessError as e:
        err = e.stderr.decode("utf-8", errors="replace")
        first_line = next((line for line in err.splitlines() if line.strip()), err.strip())
        if not first_line:
            first_line = "unknown error"
        raise SystemExit(f"git failed in {args.path}: {first_line}") from e


if __name__ == "__main__":
    sys.exit(main())
