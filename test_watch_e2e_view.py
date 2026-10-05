"""End-to-end view state: WatchViewer driven during Phase 2's fake run script."""

import os
import unittest

import towncode
import untouched
import viewer
from problems import find
from roads import Roads
from test_transcripts import write_lines, use
from test_watch_e2e import WatchE2ETest
from townmap import TownMap


class WatchViewEndStateTest(WatchE2ETest):
    def _seed_orchestrator(self, wt_path):
        slug = (os.path.realpath(self.main).replace("/", "-")
                .replace(".", "-").replace("_", "-"))
        tr = os.path.join(
            self.home, ".cursor", "projects", slug.lstrip("-"),
            "agent-transcripts", "chat-1", "chat-1.jsonl")
        write_lines(tr, [{"role": "assistant", "message": {"content": [
            {"type": "tool_use", "name": "Task", "input": {"subagent": True}}]}}])
        sub = os.path.join(os.path.dirname(tr), "subagents", "sub1.jsonl")
        write_lines(sub, [{"role": "assistant", "message": {"content": [
            use("Read", path=os.path.join(wt_path, "hub/a.py"))]}}])
        os.utime(tr, (self.clock.time(), self.clock.time()))

    def _make_viewer(self, w):
        model, rows, plat, _out = towncode._watch_town(self.main)
        found = find(model, rows)
        tmap = TownMap(model, plat, rows, found)
        return viewer.WatchViewer(
            tmap, Roads(tmap, model, found), model, rows, plat,
            os.path.basename(self.main), w.state().main_tip,
            self.survey, self.main, w, zoom=viewer.STREET,
            resurvey_runner=lambda fn: fn(),
            note_resurvey=w.note_resurvey)

    def _drive_poll(self, v, w, poll_once, *, drops_seen, merge_lines):
        wt_path = next((wt.path for wt in w.worktrees() if wt.name == "demo"), None)
        before_main = untouched.fingerprint(self.main)
        before_wt = (untouched.fingerprint(wt_path)
                     if wt_path and os.path.isdir(wt_path) else None)
        new_events = poll_once()
        v.ingest(viewer.WatchSnapshot(new_events, w.state()))
        v.tick(1.0, v.t + 1.0)
        for zoom in (viewer.STREET, viewer.DISTRICT, viewer.TOWN):
            saved = v.zoom
            v.zoom = zoom
            fb = v.frame(120, 57)
            v.overlays(fb.w, fb.h)
            v.status(80)
            v.zoom = saved
        drops_seen.update(v._drops.keys())
        if v._merge_line2:
            merge_lines.append(v._merge_line2)
        self.assertEqual(
            untouched.differences(before_main, untouched.fingerprint(self.main)), {})
        if before_wt is not None:
            self.assertEqual(
                untouched.differences(before_wt, untouched.fingerprint(wt_path)), {})

    def test_view_end_state_matches_spec(self):
        """Watch poll/ingest/tick must not touch the repo; per-step fingerprints catch that."""
        self._seed_orchestrator(os.path.join(self.wts, "demo"))
        self.clock.advance(10)
        v_holder = []
        w_holder = []
        drops_seen = set()
        merge_lines = []

        def on_poll(w, poll_once):
            if not v_holder:
                v_holder.append(self._make_viewer(w))
                w_holder.append(w)
                self.addCleanup(w.close)
            self._drive_poll(v_holder[0], w, poll_once,
                             drops_seen=drops_seen, merge_lines=merge_lines)

        kinds = self._run_script(on_poll=on_poll)
        expected = ["start", "edit", "create", "commit", "finish",
                    "review_start", "review_finish", "merge", "leave"]
        filtered = [k for k in kinds if k in expected]
        self.assertEqual(filtered, expected)

        v, w = v_holder[0], w_holder[0]
        deadline = v.t + 120.0
        while any(c.role != "orchestrator" for c in v._crowd.clawds()):
            if v.t >= deadline:
                self.fail("non-orchestrator Clawds did not depart within 120 simulated seconds")

            def poll_once():
                batch = w.poll()
                self.clock.advance(1)
                return batch

            self._drive_poll(v, w, poll_once,
                             drops_seen=drops_seen, merge_lines=merge_lines)

        self.assertIn("hub/new.py", v.m.buildings)
        self.assertIn("hub/new.py", drops_seen)
        self.assertEqual(v._crowd.effective_scaffold(v._latest_state), {})
        self.assertEqual(v._crowd.effective_sites(v._latest_state), [])
        roles = {c.role for c in v._crowd.clawds()}
        self.assertEqual(roles, {"orchestrator"})
        self.assertTrue(any("merged team/world/demo" in line for line in merge_lines))


if __name__ == "__main__":
    unittest.main()
