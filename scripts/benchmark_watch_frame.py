#!/usr/bin/env python3
"""Median street frame time with 10 Clawds at 120x57. Exit 1 if median > 35 ms."""
import os
import shutil
import statistics
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import fixture
import towncode
import viewer
import watch
from events import Agent, Event
from problems import find
from roads import Roads
from test_survey import MONOREPO_LIKE
from townmap import TownMap

FRAME_W, FRAME_H = 120, 57
FRAMES = 30
DT = 1 / 24
WARMUP = 3

# Buildings near Town Hall stay inside the default street frame at 120x57.
_NEAR_HALL = (
    ("hub/app.py", "world"),
    ("hub/records.py", "render"),
    ("hub/unused.py", "gameplay"),
    ("packages/core_sdk/manifest.py", "world"),
    ("packages/core_sdk/dev.py", "render"),
    ("tests/test_manifest.py", "gameplay"),
    ("scripts/tool.sh", "qa"),
    ("desktop/broken.py", "review"),
    ("packages/core_sdk/__init__.py", "world"),
)


class _Cleanup:
    def __init__(self):
        self._fns = []
        self.paths = []

    def addCleanup(self, fn, *args):
        self._fns.append((fn, args))
        if fn is shutil.rmtree and args:
            self.paths.append(args[0])

    def run(self):
        for fn, args in reversed(self._fns):
            fn(*args)


def build_scene(*, repo=None, survey_dir=None):
    """Build a warm street scene with 10 on-screen Clawds. Returns (viewer, watch, cleanup)."""
    cleanup = _Cleanup()
    if repo is None:
        dummy = _Cleanup()
        repo = fixture.make_repo(dummy, MONOREPO_LIKE)
        cleanup.addCleanup(shutil.rmtree, repo, True)
    if survey_dir is None:
        survey_dir = tempfile.mkdtemp(prefix="bench-survey-")
        cleanup.addCleanup(shutil.rmtree, survey_dir, True)
    model, rows, plat, _out = towncode._watch_town(repo)
    found = find(model, rows)
    tmap = TownMap(model, plat, rows, found)
    rds = Roads(tmap, model, found)
    clock = watch.FakeClock()
    w = watch.Watch(repo, survey_dir=survey_dir, clock=clock, model=model)
    cleanup.addCleanup(w.close)
    v = viewer.WatchViewer(
        tmap, rds, model, rows, plat, "bench", w.state().main_tip,
        survey_dir, repo, w, zoom=viewer.STREET,
        resurvey_runner=lambda fn: fn())
    orch = Agent("orchestrator", "orchestrator", None, None)
    v.ingest(viewer.WatchSnapshot(
        [Event("start", orch, None, 0.0)],
        watch.WatchState(team_colours={"world": 0, "render": 1, "gameplay": 2,
                                       "qa": 3, "review": 4})))
    for i, (path, team) in enumerate(_NEAR_HALL):
        a = Agent(f"w{i}/task-1", "implementer", team, f"w{i}")
        v.ingest(viewer.WatchSnapshot(
            [Event("edit", a, path, float(i + 1))],
            watch.WatchState(scaffolded={path: team},
                             team_colours={"world": 0, "render": 1, "gameplay": 2,
                                           "qa": 3, "review": 4})))
    v.tick(DT, DT)
    return v, w, cleanup.run, list(cleanup.paths)


def time_street_frame(v):
    t0 = time.perf_counter()
    v.tick(DT, v.t + DT)
    fb = v.frame(FRAME_W, FRAME_H)
    v.overlays(fb.w, fb.h)
    return (time.perf_counter() - t0) * 1000


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    repo = argv[0] if argv else None
    survey_dir = None
    cleanup = _Cleanup()
    if repo:
        survey_dir = tempfile.mkdtemp(prefix="bench-survey-")
        cleanup.addCleanup(shutil.rmtree, survey_dir, True)
        os.environ["TOWNCODE_SURVEY_DIR"] = survey_dir
    try:
        v, w, scene_cleanup, _paths = build_scene(repo=repo, survey_dir=survey_dir)
        try:
            for _ in range(WARMUP):
                time_street_frame(v)
            times = [time_street_frame(v) for _ in range(FRAMES)]
        finally:
            w.close()
            scene_cleanup()
    finally:
        cleanup.run()
    med = statistics.median(times)
    mx = max(times)
    label = "OK" if med <= 35 else "SLOW"
    print(f"{label}: {med:.1f} ms (max {mx:.1f} ms, 10 Clawds, {FRAME_W}x{FRAME_H})")
    return 1 if med > 35 else 0


if __name__ == "__main__":
    sys.exit(main())
