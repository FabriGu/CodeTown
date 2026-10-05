"""Browser smoke check for the 3D town. Run it by hand, not with unittest:

    python3 smoke_web.py [REPO] [--headed]
    python3 smoke_web.py --watch [--headed]

It serves REPO (by default a small throwaway repository) with `towncode view --browser`, or with
`towncode watch --browser` when `--watch` is set,
loads the page in Playwright through playwright-cli, and checks the scene against /town.json:
every building and road drawn, and no key look.js should define missing. It needs npx, and
leaves a screenshot in /tmp.
"""

import argparse
import base64
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request

import fixture

HERE = os.path.dirname(os.path.abspath(__file__))
PWCLI = os.environ.get("PWCLI") or os.path.expanduser(
    "~/.codex/skills/playwright/scripts/playwright_cli.sh")
SESSION = "towncode-3d-smoke"
FILES = {
    "app/main.py": "import app.loop_a\nimport core.base\n\n\ndef run():\n"
                   "    return core.base.load()\n",
    "app/loop_a.py": "import app.loop_b\n",
    "app/loop_b.py": "import app.loop_a\n",
    "core/base.py": "import yaml\n\n\ndef load():\n    return yaml.safe_load('1')\n",
    "core/broken.py": "def half(:\n",
    "tests/test_base.py": "import core.base\n\n\ndef test_load():\n"
                          "    assert core.base.load() == 1\n",
}


class SmokeFailed(Exception):
    pass


def check(ok, what):
    if not ok:
        raise SmokeFailed(what)


# playwright-cli writes snapshot files into its working folder, so it runs in a scratch one.
WORK = tempfile.mkdtemp(prefix="towncode-smoke-pw-")


def pw(*args, timeout=180):
    done = subprocess.run([PWCLI, "--session", SESSION, *args], capture_output=True, text=True,
                          timeout=timeout, cwd=WORK)
    if done.returncode != 0 or "### Error" in done.stdout:
        raise SmokeFailed(f"playwright-cli {args[0]}: {(done.stdout + done.stderr).strip()[-600:]}")
    return done.stdout


def wait_for(condition, timeout_ms):
    pw("run-code", f"async page => {{ await page.waitForFunction(() => {condition}, null, "
                   f"{{timeout: {timeout_ms}}}); }}")


def report():
    out = pw("eval", "'SMOKE ' + btoa(unescape(encodeURIComponent("
                     "JSON.stringify(window.town3d.report()))))")
    found = re.search(r"SMOKE ([A-Za-z0-9+/=]+)", out)
    check(found, f"no report in: {out.strip()[:300]}")
    return json.loads(base64.b64decode(found.group(1)).decode("utf-8"))


def server_status_line1(url, timeout=15):
    req = urllib.request.urlopen(url + "events", timeout=timeout)
    event = None
    try:
        for raw in req:
            line = raw.decode().strip()
            if line.startswith("event: "):
                event = line[7:]
            elif line.startswith("data: ") and event == "state":
                return json.loads(line[6:])["status"][0]
    finally:
        req.close()
    raise SmokeFailed("no state event on /events")


def first_follow_key(line3):
    found = re.search(r"\b([1-9]) \S+", line3)
    return found.group(1) if found else None


def make_repo():
    root = tempfile.mkdtemp(prefix="towncode-smoke-repo-")
    subprocess.run(["git", "init", "-q", "-b", "main", root], check=True, capture_output=True)
    fixture.write(root, FILES)
    fixture.git(root, "add", "-A")
    fixture.git(root, "commit", "-q", "-m", "smoke")
    return root


def parse_port(url):
    found = re.search(r":(\d+)/", url)
    check(found, f"no port in {url!r}")
    return int(found.group(1))


def start_server(root, scratch, *, watch=False, port=0):
    env = dict(os.environ, TOWNCODE_SURVEY_DIR=scratch)
    cmd = [sys.executable, os.path.join(HERE, "towncode.py"),
           "watch" if watch else "view", root, "--browser", "--no-open", "--port", str(port)]
    server = subprocess.Popen(cmd, stdout=subprocess.PIPE, text=True, env=env)
    for line in server.stdout:
        found = re.search(r"http://127\.0\.0\.1:\d+/", line)
        if found:
            return server, found.group(0)
    server.wait()
    raise SmokeFailed(f"the server stopped before serving (exit {server.returncode})")


def add_demo_worktree(root, wt_dir):
    subprocess.run(["git", "-C", root, "worktree", "add", "-b", "team/world/demo", wt_dir],
                   check=True, capture_output=True)
    ledger = os.path.join(wt_dir, ".superpowers", "sdd", "run-1")
    os.makedirs(ledger, exist_ok=True)
    with open(os.path.join(ledger, "task-1-brief.md"), "w", encoding="utf-8") as f:
        f.write("smoke\n")


def remove_worktree(root, wt_dir):
    subprocess.run(["git", "-C", root, "worktree", "remove", "--force", wt_dir],
                   capture_output=True)


def smoke(url, shot, headed):
    raw = urllib.request.urlopen(url + "town.json", timeout=60).read()
    doc = json.loads(raw)
    pw("open", url, *(["--headed"] if headed else []))
    wait_for("window.town3d && (window.town3d.ready || window.town3d.error)", 120000)
    r = report()
    check(r["error"] is None, f"the page failed: {r['error']}")
    check(r["missing"] == [], f"look.js doesn't define {r['missing']}")
    check(r["buildings"] == len(doc["buildings"]),
          f"{r['buildings']} buildings drawn, {len(doc['buildings'])} in town.json")
    check(r["warehouses"] == len(doc["warehouses"]),
          f"{r['warehouses']} warehouses drawn, {len(doc['warehouses'])} in town.json")
    check(r["roads"] == len(doc["roads"]),
          f"{r['roads']} roads drawn, {len(doc['roads'])} in town.json")
    target = next((b for b in doc["buildings"] if b["path"] in
                   {p for r in doc["roads"] for p in (r["from"], r["to"])}), doc["buildings"][0])
    pw("eval", f"window.town3d.select({json.dumps(target['path'])}).then(() => 'selected')")
    wait_for("window.town3d.report().focused.length === 1", 15000)
    r = report()
    check(r["focused"] == [target["path"]], f"focused {r['focused']}, wanted {target['path']}")
    check(r["inspector"] == target["inspect"]["title"],
          f"the inspector says {r['inspector']!r}, wanted {target['inspect']['title']!r}")
    check(r["dimmed"] > 0 or len(doc["buildings"]) == 1, "nothing dimmed around the focus")
    pw("run-code", "async page => { await page.waitForTimeout(1500); await page.screenshot("
                   f"{{path: {json.dumps(shot.replace('.png', '-focus.png'))}}}); }}")
    pw("press", "Escape")
    wait_for("window.town3d.report().focused.length === 0", 15000)
    r = report()
    check(r["inspector"] is None and r["dimmed"] == 0, "Escape left the focus on")
    check(r["roads"] == len(doc["roads"]), "Escape didn't bring the town's roads back")
    pw("run-code", "async page => { await page.waitForTimeout(2000); "
                   f"await page.screenshot({{path: {json.dumps(shot)}}}); }}")
    return doc, raw, report()


def smoke_watch(url, shot, wt_dir, root, scratch, server, headed):
    doc = json.loads(urllib.request.urlopen(url + "town.json", timeout=60).read())
    initial_buildings = len(doc["buildings"])
    pw("open", url, *(["--headed"] if headed else []))
    wait_for("window.town3d && window.town3d.ready && window.town3d.report().clawds >= 1", 60000)
    with open(os.path.join(wt_dir, "app", "main.py"), "a", encoding="utf-8") as f:
        f.write("\n# smoke edit\n")
    wait_for("window.town3d.report().scaffolded >= 1", 30000)
    pw("run-code", "async page => { await page.waitForTimeout(2000); "
                   f"await page.screenshot({{path: {json.dumps(shot)}}}); }}")
    r = report()
    check(r["error"] is None, f"the page failed: {r['error']}")
    check(r["live"] is True, "the event stream is not connected")
    check(r["missing"] == [], f"look.js doesn't define {r['missing']}")
    check(r["scaffold_boxes"] > 0, f"no scaffold boxes drawn ({r['scaffold_boxes']})")
    check(r["labels"] >= 1, f"no labels shown ({r['labels']})")
    check(r["mode"] == "auto", f"camera mode is {r['mode']!r}, wanted auto")
    expected = server_status_line1(url)
    wait_for(f"window.town3d.report().line1 === {json.dumps(expected)}", 5000)
    r = report()
    follow = first_follow_key(r["line3"])
    check(follow, f"no follow key in line3: {r['line3']!r}")
    pw("eval", f"window.town3d.press({json.dumps(follow)})")
    wait_for(f"window.town3d.report().mode === 'follow {follow}'", 5000)
    pw("eval", "window.town3d.press('0')")
    wait_for("window.town3d.report().mode === 'auto'", 5000)
    labels_shot = "/tmp/towncode-3d-watch-labels.png"
    pw("run-code", "async page => { await page.waitForTimeout(1500); "
                   f"await page.screenshot({{path: {json.dumps(labels_shot)}}}); }}")

    extra = os.path.join(wt_dir, "app", "extra.py")
    with open(extra, "w", encoding="utf-8") as f:
        f.write("import core.base\n")
    wait_for("window.town3d.report().sites >= 1", 30000)
    subprocess.run(["git", "-C", wt_dir, "add", "-A"], check=True, capture_output=True)
    subprocess.run(["git", "-C", wt_dir, "commit", "-q", "-m", "smoke extra"], check=True,
                   capture_output=True)
    subprocess.run(["git", "-C", root, "merge", "--no-ff", "-q", "team/world/demo", "-m",
                    "smoke merge"], check=True, capture_output=True)
    wait_for("window.town3d.report().line2.startsWith('merged')", 30000)
    wait_for("window.town3d.report().version === 2", 90000)
    r = report()
    check(r["buildings"] == initial_buildings + 1,
          f"{r['buildings']} buildings after merge, wanted {initial_buildings + 1}")
    merged_shot = "/tmp/towncode-3d-watch-merged.png"
    pw("run-code", "async page => { await page.waitForTimeout(2000); "
                   f"await page.screenshot({{path: {json.dumps(merged_shot)}}}); }}")

    port = parse_port(url)
    server.terminate()
    server.wait(timeout=10)
    wait_for("window.town3d.report().line2 === 'reconnecting…'", 10000)
    time.sleep(2)
    server, url = start_server(root, scratch, watch=True, port=port)
    wait_for("window.town3d.report().live === true", 30000)
    r = report()
    check(r["error"] is None, f"after reconnect the page failed: {r['error']}")
    check(r["live"] is True, "the page did not reconnect to the event stream")
    return r, server


def main(argv=None):
    parser = argparse.ArgumentParser(description="Browser smoke check for the 3D town.")
    parser.add_argument("repo", nargs="?", help="repository to serve (default: a throwaway one)")
    parser.add_argument("--headed", action="store_true", help="show the browser window")
    parser.add_argument("--watch", action="store_true", help="serve towncode watch and check Clawds")
    args = parser.parse_args(argv)
    scratch = tempfile.mkdtemp(prefix="towncode-smoke-survey-")
    root = os.path.abspath(args.repo) if args.repo else make_repo()
    name = os.path.basename(root) if args.repo else "fixture"
    shot = "/tmp/towncode-3d-watch.png" if args.watch else f"/tmp/towncode-3d-smoke-{name}.png"
    wt_parent = wt_dir = None
    server = None
    try:
        if args.watch:
            wt_parent = tempfile.mkdtemp(prefix="towncode-smoke-wts-")
            wt_dir = os.path.join(wt_parent, "wt-demo")
            add_demo_worktree(root, wt_dir)
        server, url = start_server(root, scratch, watch=args.watch)
        if args.watch:
            r, server = smoke_watch(url, shot, wt_dir, root, scratch, server, args.headed)
            print(f"ok: {r['clawds']} clawds, {r['scaffolded']} scaffolded, "
                  f"{r['scaffold_boxes']} scaffold boxes, {r['sites']} sites, "
                  f"{r['flags']} flags, {r['labels']} labels, mode={r['mode']}; "
                  f"live={r['live']}; version={r['version']}; {r['fps']} fps; {shot}; "
                  f"/tmp/towncode-3d-watch-labels.png; /tmp/towncode-3d-watch-merged.png")
        else:
            doc, raw, r = smoke(url, shot, args.headed)
            print(f"ok: {r['buildings']} buildings, {r['warehouses']} warehouses, {r['roads']} roads; "
                  f"town.json {len(raw) // 1024} KB; built in {r['build_ms']} ms; {r['fps']} fps; {shot}")
        return 0
    except SmokeFailed as e:
        print(f"FAILED: {e}", file=sys.stderr)
        return 1
    finally:
        subprocess.run([PWCLI, "--session", SESSION, "close"], capture_output=True, cwd=WORK,
                       timeout=60)
        if server:
            server.terminate()
            server.wait(timeout=10)
        if wt_dir:
            remove_worktree(root, wt_dir)
        for path in (scratch, WORK, wt_parent) + (() if args.repo else (root,)):
            if path:
                shutil.rmtree(path, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
