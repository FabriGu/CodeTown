"""How much the live 3D server costs: /town.json's size and the simulation thread's CPU share.

    python3 scripts/benchmark_watch_browser.py [REPO] [--seconds N]

REPO is read only; its survey goes to a temporary folder. Without REPO it uses a small fixture
repository. Exits 1 if town.json is 1 MB or more, or the simulation thread uses
5% of one core or more.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

import fixture  # noqa: E402
import towncode  # noqa: E402

LIMIT_BYTES = 1_000_000
LIMIT_SHARE = 0.05


def measure(repo, seconds):
    args = argparse.Namespace(path=repo, browser=True, events=False, port=0, no_open=True)
    survey_dir = tempfile.mkdtemp(prefix="towncode-bench-survey-")
    prev_survey = os.environ.get("TOWNCODE_SURVEY_DIR")
    os.environ["TOWNCODE_SURVEY_DIR"] = survey_dir
    lw = None
    try:
        lw = towncode._watch_live(args, survey_dir=survey_dir)
        size = len(json.dumps(lw.site.town, separators=(",", ":")).encode("utf-8"))
        lw.poller.start()
        used = [0.0]

        def run():
            start, prev = time.monotonic(), 0.0
            cpu0 = time.thread_time()
            while time.monotonic() - start < seconds:
                time.sleep(0.1)
                now = time.monotonic() - start
                lw.sim.step_once(now - prev, now)
                prev = now
            used[0] = time.thread_time() - cpu0

        t = threading.Thread(target=run, name="Simulation")
        t.start()
        t.join()
        return size, used[0] / seconds, len(lw.live.crowd.clawds())
    finally:
        if lw is not None:
            lw.poller.close_event.set()
            lw.poller.join(timeout=2)
            lw.watch.close()
        shutil.rmtree(survey_dir, ignore_errors=True)
        if prev_survey is None:
            os.environ.pop("TOWNCODE_SURVEY_DIR", None)
        else:
            os.environ["TOWNCODE_SURVEY_DIR"] = prev_survey


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("repo", nargs="?")
    p.add_argument("--seconds", type=float, default=10.0)
    a = p.parse_args(argv)
    repo = a.repo or _fixture()
    try:
        size, share, clawds = measure(repo, a.seconds)
    finally:
        if not a.repo:
            shutil.rmtree(repo, ignore_errors=True)
    print(f"town.json: {size} bytes; simulation: {share:.1%} of one core over "
          f"{a.seconds:g} s ({clawds} Clawds)")
    return 0 if size < LIMIT_BYTES and share < LIMIT_SHARE else 1


def _fixture():
    root = tempfile.mkdtemp(prefix="towncode-bench-repo-")
    subprocess.run(["git", "init", "-q", "-b", "main", root], check=True, capture_output=True)
    fixture.write(root, {"app/main.py": "x = 1\n", "core/base.py": "y = 2\n"})
    fixture.git(root, "add", "-A")
    fixture.git(root, "commit", "-q", "-m", "bench")
    return root


if __name__ == "__main__":
    sys.exit(main())
