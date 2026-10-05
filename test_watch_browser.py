import argparse
import json
import os
import shutil
import tempfile
import unittest

import fixture
import livetown
import towncode
import untouched
from test_watch import temp_survey
from test_watch_e2e import WatchE2ETest
from test_watch_e2e_view import WatchViewEndStateTest


def _args(path):
    return argparse.Namespace(path=path, browser=True, events=False, port=0, no_open=True)


def _decode(raw):
    head, data = raw.decode("utf-8").split("\n")[:2]
    return head[len("event: "):], json.loads(data[len("data: "):])


class WatchBrowserEndToEndTest(WatchE2ETest):
    _seed_orchestrator = WatchViewEndStateTest._seed_orchestrator

    def test_a_browser_sees_the_whole_run(self):
        """Phase 2's scripted run, fed through the server's own wiring, as a browser hears it."""
        self._seed_orchestrator(os.path.join(self.wts, "demo"))
        self.clock.advance(10)
        lw, messages = {}, []

        def drive(w, poll_once):
            if not lw:
                lw["it"] = towncode._watch_live(_args(self.main), home=self.home,
                                                survey_dir=self.survey, watch_obj=w,
                                                resurvey_runner=lambda fn: fn())
                lw["q"], state = lw["it"].site.subscribe()
                messages.append(("state", state))
                lw["w"] = w
                self.addCleanup(w.close)
            it = lw["it"]
            before = untouched.fingerprint(self.main)
            it.poller._drain_inbox()
            it.snapshots.put(livetown.WatchSnapshot(poll_once(), w.state()))
            for _ in range(10):
                it.sim.step_once(0.1, it.live.t + 0.1)
            while not lw["q"].empty():
                raw = lw["q"].get_nowait()
                if raw is not None:
                    messages.append(_decode(raw))
            self.assertEqual(untouched.differences(before, untouched.fingerprint(self.main)), {})

        self._run_script(on_poll=drive)
        it, w = lw["it"], lw["w"]
        for _ in range(120):
            if not any(c.role != "orchestrator" for c in it.live.crowd.clawds()):
                break

            def poll_once():
                batch = w.poll()
                self.clock.advance(1)
                return batch

            drive(w, poll_once)
        else:
            self.fail("non-orchestrator Clawds did not leave within 120 polls")

        ticks = [m for kind, m in messages if kind == "tick"]
        records = [r for t in ticks for r in t.get("clawds", [])]
        poses = {r["pose"] for r in records if r["id"] == "demo/task-1"}
        self.assertTrue({"walk", "hammer", "hop"} <= poses, poses)
        self.assertTrue(any("hub/a.py" in t.get("scaffold", {}) for t in ticks))
        self.assertTrue(any(s["path"] == "hub/new.py" for t in ticks for s in t.get("sites", [])))
        self.assertTrue(any("demo/task-1" in t.get("gone", []) for t in ticks))
        self.assertTrue(any(t.get("status", ["", ""])[1].startswith("merged team/world/demo")
                            for t in ticks))
        self.assertEqual([m["version"] for kind, m in messages if kind == "town"], [2])
        self.assertIn("hub/new.py", {b["path"] for b in it.site.town["buildings"]})
        self.assertEqual(it.site.town["version"], 2)
        _, final = it.site.subscribe()
        self.assertEqual((final["scaffold"], final["sites"]), ({}, []))
        self.assertEqual({r["role"] for r in final["clawds"]}, {"orchestrator"})
        for _kind, m in messages:
            self.assertNotIn("# e", json.dumps(m, ensure_ascii=False))


class WatchBrowserCLITest(unittest.TestCase):
    def setUp(self):
        self.main = fixture.make_repo(self, {"hub/a.py": "x = 1\n"})
        self.survey = temp_survey(self)
        self.home = tempfile.mkdtemp(prefix="watch-browser-home-")
        self.addCleanup(shutil.rmtree, self.home)

    def test_browser_and_events_dont_mix(self):
        with self.assertRaises(SystemExit) as cm:
            towncode.main(["watch", self.main, "--browser", "--events"])
        self.assertIn("--browser can't be combined with --events", str(cm.exception))

    def test_the_server_starts_with_state_and_closes_the_watch(self):
        served = {}

        def fake_serve(site, port, *, open_browser, on_close):
            served.update(site=site, port=port, open_browser=open_browser)
            served["state"] = site.subscribe()[1]
            on_close()
            served["closed"] = True
            return 0

        code = towncode._watch_browser(_args(self.main), home=self.home, survey_dir=self.survey,
                                       serve=fake_serve)
        self.assertEqual(code, 0)
        self.assertEqual((served["port"], served["open_browser"]), (0, False))
        self.assertIs(served["site"].town["live"], True)
        name = os.path.basename(os.path.realpath(self.main))
        self.assertEqual(served["state"]["status"][0],
                         f"{name}: no agents working. Watching main and 0 worktrees.")
        self.assertEqual(served["state"]["clawds"], [])
        self.assertTrue(served["closed"])


if __name__ == "__main__":
    unittest.main()
