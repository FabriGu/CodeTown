import contextlib
import io
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))

import fixture
import survey
import towncode
import untouched
import viewer
from drawtown import FOCUS_ROOF
from render import shade
from test_survey import MONOREPO_LIKE


def colours(fb):
    return {c for row in fb.rows for c in row}


class TowncodeTest(unittest.TestCase):
    def setUp(self):
        self.root = fixture.make_repo(self, MONOREPO_LIKE,
                                      untracked={"token.txt": "SECRET-TOKEN-123\n"})
        self.out = tempfile.mkdtemp(prefix="towncode-out-")
        self.addCleanup(shutil.rmtree, self.out)
        env = mock.patch.dict(os.environ, {"TOWNCODE_SURVEY_DIR": self.out})
        env.start()
        self.addCleanup(env.stop)

    def survey(self, *flags):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = towncode.main(["survey", self.root, *flags])
        return code, buf.getvalue()

    def saved(self, name):
        with open(os.path.join(towncode.output_dir(self.root), name), encoding="utf-8") as f:
            return f.read()

    def test_report_lists_districts_back_row_first_and_problems(self):
        code, text = self.survey()
        self.assertEqual(code, 0)
        for expected in ["row 0  packages", "row 1  hub", "won't parse (1)", "import cycle (2)",
                         "hub/unused.py: nothing imports it", "Languages: Python 8 full, Shell 1",
                         "row 0  scripts (1 module)"]:
            self.assertIn(expected, text)
        self.assertLess(text.index("row 0  packages"), text.index("row 1  hub"))

    def test_model_and_rows_are_saved_outside_the_repo(self):
        self.survey()
        self.assertEqual(os.path.dirname(towncode.output_dir(self.root)), self.out)
        self.assertIn('"hub/app.py"', self.saved("model.json"))
        self.assertIn('"packages": 0', self.saved("rows.json"))

    def test_the_repo_is_untouched(self):
        before = untouched.fingerprint(self.root)
        self.survey()
        self.assertEqual(untouched.differences(before, untouched.fingerprint(self.root)), {})

    def test_check_untouched_confirms(self):
        code, text = self.survey("--check-untouched")
        self.assertEqual(code, 0)
        self.assertIn("untouched: yes", text)

    def test_check_untouched_fails_when_something_changes(self):
        real = towncode.survey.survey

        def meddling(root):
            with open(os.path.join(root, "hub", "records.py"), "a", encoding="utf-8") as f:
                f.write("# meddled\n")
            return real(root)

        with mock.patch.object(towncode.survey, "survey", meddling):
            code, text = self.survey("--check-untouched")
        self.assertEqual(code, 1)
        self.assertIn("untouched: NO", text)
        self.assertIn("hub/records.py", text)

    def test_check_untouched_never_opens_untracked_files(self):
        opened = []
        real = untouched._digest

        def spy(path):
            opened.append(os.path.relpath(path, self.root))
            return real(path)

        with mock.patch.object(untouched, "_digest", spy):
            self.survey("--check-untouched")
        self.assertIn("hub/app.py", opened)
        self.assertTrue(any(p.startswith(".git" + os.sep) for p in opened))
        self.assertNotIn("token.txt", opened)

    def test_no_file_contents_or_untracked_names_leak(self):
        _, text = self.survey()
        saved = self.saved("model.json") + self.saved("rows.json") + self.saved("plat.json")
        for secret in ["CANARY_SOURCE_TEXT", "SECRET-TOKEN-123", "token.txt"]:
            self.assertNotIn(secret, text)
            self.assertNotIn(secret, saved)

    def test_surveys_are_repeatable(self):
        self.survey()
        first = self.saved("model.json"), self.saved("rows.json")
        self.survey()
        self.assertEqual((self.saved("model.json"), self.saved("rows.json")), first)

    def test_refuses_to_write_inside_the_repo(self):
        inside = os.path.join(self.root, ".survey")
        with mock.patch.dict(os.environ, {"TOWNCODE_SURVEY_DIR": inside}):
            with self.assertRaises(SystemExit):
                self.survey()
        self.assertFalse(os.path.exists(inside))

    def test_refuses_a_folder_that_is_not_a_repo(self):
        with self.assertRaises(SystemExit):
            towncode.main(["survey", self.out])

    def test_git_failure_exits_with_readable_message(self):
        root = tempfile.mkdtemp(prefix="towncode-badgit-")
        self.addCleanup(shutil.rmtree, root)
        with open(os.path.join(root, ".git"), "w", encoding="utf-8") as f:
            f.write("gitdir: /nonexistent-towncode-test\n")
        with self.assertRaises(SystemExit) as ctx:
            towncode.main(["survey", root])
        self.assertTrue(str(ctx.exception).startswith("git failed in"))

    def test_corrupt_saved_rows_exits_without_overwriting(self):
        self.survey()
        rows_path = os.path.join(towncode.output_dir(self.root), "rows.json")
        corrupt = "{not json"
        with open(rows_path, "w", encoding="utf-8") as f:
            f.write(corrupt)
        with self.assertRaises(SystemExit) as ctx:
            self.survey()
        self.assertIn("rows.json", str(ctx.exception))
        self.assertIn("Delete it", str(ctx.exception))
        with open(rows_path, encoding="utf-8") as f:
            self.assertEqual(f.read(), corrupt)

    def test_survey_saves_the_plat_and_a_second_survey_keeps_every_lot(self):
        self.survey()
        first = self.saved("plat.json")
        self.assertIn('"hub/app.py"', first)
        self.survey()
        self.assertEqual(self.saved("plat.json"), first)

    def test_corrupt_saved_plat_exits_without_overwriting(self):
        self.survey()
        path = os.path.join(towncode.output_dir(self.root), "plat.json")
        with open(path, "w", encoding="utf-8") as f:
            f.write("[]")
        with self.assertRaises(SystemExit) as ctx:
            self.survey()
        self.assertIn("plat.json", str(ctx.exception))
        with open(path, encoding="utf-8") as f:
            self.assertEqual(f.read(), "[]")

    def snapshot(self, *args):
        with contextlib.redirect_stdout(io.StringIO()):
            return towncode.main(["snapshot", self.root, *args])

    def test_snapshot_lays_out_by_roles_without_saving_it(self):
        png = os.path.join(self.out, "town.png")
        self.assertEqual(self.snapshot(png, "--size", "40x30"), 0)
        saved = self.saved("plat.json")
        self.assertEqual(self.snapshot(png, "--layout", "roles", "--size", "40x30"), 0)
        self.assertEqual(self.saved("plat.json"), saved)

    def test_snapshot_draws_the_town_to_a_png_and_leaves_the_repo_untouched(self):
        before = untouched.fingerprint(self.root)
        png = os.path.join(self.out, "town.png")
        self.assertEqual(self.snapshot(png, "--size", "40x30", "--scale", "1"), 0)
        with open(png, "rb") as f:
            data = f.read()
        self.assertTrue(data.startswith(b"\x89PNG"))
        self.assertEqual(struct.unpack(">II", data[16:24]), (40, 30))
        self.assertEqual(untouched.differences(before, untouched.fingerprint(self.root)), {})

    def test_plain_snapshot_does_not_focus(self):
        png = os.path.join(self.out, "town.png")
        captured = []
        orig = towncode.town
        def watch(*a, **k):
            v = orig(*a, **k)
            captured.append(v)
            return v
        with mock.patch.object(towncode, "town", watch):
            self.assertEqual(self.snapshot(png, "--size", "40x30"), 0)
        self.assertFalse(captured[-1].select_focuses)
        chosen = captured[-1].selected()
        self.assertIsNone(captured[-1].in_focus(chosen))

    def test_snapshot_at_still_focuses(self):
        png = os.path.join(self.out, "town.png")
        captured = []
        orig = towncode.town
        def watch(*a, **k):
            v = orig(*a, **k)
            captured.append(v)
            return v
        with mock.patch.object(towncode, "town", watch):
            self.assertEqual(self.snapshot(png, "--at", "hub/app.py", "--size", "40x30"), 0)
        self.assertTrue(captured[-1].select_focuses)
        self.assertIsNotNone(captured[-1].in_focus(captured[-1].selected()))

    def test_snapshot_session_without_at_still_renders_focus(self):
        home, _ = self.transcript(("Edit", "hub/records.py"), ("Write", "hub/new_tool.py"))
        png = os.path.join(self.out, "town.png")
        captured = []
        orig = towncode.town
        def watch(*a, **k):
            v = orig(*a, **k)
            captured.append(v)
            return v
        with mock.patch.dict(os.environ, {"HOME": home}), \
             mock.patch.object(towncode, "town", watch):
            self.assertEqual(self.snapshot(png, "--session", "--size", "60x40"), 0)
        v = captured[-1]
        self.assertFalse(v.select_focuses)
        self.assertIs(v.in_focus(v.selected()), v.session)
        v.frame(60, 40)
        self.assertIn(shade(FOCUS_ROOF, 0.95), colours(v._whole_town(v.selected()).fb))

    def test_snapshot_can_centre_on_a_module_at_any_zoom(self):
        png = os.path.join(self.out, "town.png")
        for zoom in ("street", "district", "town"):
            self.assertEqual(self.snapshot(png, "--at", "hub/app.py", "--zoom", zoom,
                                           "--size", "30x20", "--scale", "1"), 0)
        with self.assertRaises(SystemExit) as ctx:
            self.snapshot(png, "--at", "nope.py")
        self.assertIn("nope.py", str(ctx.exception))

    def test_snapshot_at_module_syncs_camera_for_street_and_district(self):
        self.survey()
        model, rows, plat, _ = towncode.run(self.root)
        at = "hub/app.py"
        w, h = 30, 20
        tile = towncode.town(model, rows, plat).m.centre(at)
        default = towncode.town(model, rows, plat)
        self.assertNotEqual(default.selected().module, at)

        for zoom in (viewer.STREET, viewer.DISTRICT):
            ref = towncode.town(model, rows, plat)
            ref.zoom = zoom
            ref.cursor, ref.problem = tile, None
            ref.sync_camera()
            expected = ref.frame(w, h)

            unsynced = towncode.town(model, rows, plat)
            unsynced.zoom = zoom
            unsynced.cursor, unsynced.problem = tile, None
            self.assertNotEqual(unsynced.frame(w, h).rows, expected.rows)

            captured = []
            png = os.path.join(self.out, f"{zoom}.png")
            with mock.patch("towncode.snapshot.write_png",
                            side_effect=lambda path, fb, scale: captured.append(fb)):
                self.assertEqual(self.snapshot(png, "--at", at, "--zoom", zoom,
                                               "--size", f"{w}x{h}", "--scale", "1"), 0)
            self.assertEqual(captured[0].rows, expected.rows)

    def test_snapshot_rejects_a_malformed_size(self):
        png = os.path.join(self.out, "town.png")
        with self.assertRaises(SystemExit) as ctx:
            self.snapshot(png, "--size", "big")
        self.assertIn("WxH", str(ctx.exception))
        self.assertFalse(os.path.exists(png))

    def test_snapshot_refuses_to_write_inside_the_repo(self):
        inside = os.path.join(self.root, "town.png")
        with self.assertRaises(SystemExit) as ctx:
            self.snapshot(inside)
        self.assertIn("refusing to write inside", str(ctx.exception))
        self.assertFalse(os.path.exists(inside))

    def test_view_needs_an_interactive_terminal(self):
        with mock.patch("sys.stdin") as stdin:
            stdin.isatty.return_value = False
            with self.assertRaises(SystemExit) as ctx:
                towncode.main(["view", self.root])
        self.assertIn("interactive terminal", str(ctx.exception))

    def test_focus_and_session_load_without_the_command_line(self):
        code = "import sys, focus, session; sys.exit('towncode' in sys.modules)"
        done = subprocess.run([sys.executable, "-c", code], cwd=HERE, capture_output=True,
                              text=True)
        self.assertEqual(done.returncode, 0, done.stderr)

    def test_each_renderer_module_imports_on_its_own(self):
        for name in ("roads", "drawtown", "viewer", "towncode"):
            done = subprocess.run([sys.executable, "-c", f"import {name}"], cwd=HERE,
                                    capture_output=True, text=True)
            self.assertEqual(done.returncode, 0, f"{name}: {done.stderr}")

    def transcript(self, *steps):
        """A Claude Code transcript of steps (tool, path) under a fake home, for this repo."""
        home = tempfile.mkdtemp(prefix="towncode-home-")
        self.addCleanup(shutil.rmtree, home)
        slug = re.sub(r"[^A-Za-z0-9]", "-", os.path.realpath(self.root))
        folder = os.path.join(home, ".claude", "projects", slug)
        os.makedirs(folder)
        path = os.path.join(folder, "session.jsonl")
        with open(path, "w", encoding="utf-8") as f:
            for i, (tool, rel) in enumerate(steps):
                block = {"type": "tool_use", "id": str(i), "name": tool,
                         "input": {"file_path": os.path.join(self.root, rel)}}
                f.write(json.dumps({"timestamp": f"2026-10-01T10:00:{i:02}Z",
                                    "message": {"content": [block]}}) + "\n")
        return home, path

    def test_snapshot_shows_what_a_session_changed_and_leaves_the_repo_untouched(self):
        home, _ = self.transcript(("Edit", "hub/records.py"), ("Write", "hub/new_tool.py"))
        png = os.path.join(self.out, "town.png")
        before = untouched.fingerprint(self.root)
        buf = io.StringIO()
        with mock.patch.dict(os.environ, {"HOME": home}), contextlib.redirect_stdout(buf):
            code = towncode.main(["snapshot", self.root, png, "--session", "--size", "40x30",
                                  "--scale", "1"])
        self.assertEqual(code, 0)
        self.assertIn("session: 1 changed", buf.getvalue())
        self.assertIn("1 new file not committed yet", buf.getvalue())
        self.assertEqual(untouched.differences(before, untouched.fingerprint(self.root)), {})

    def test_a_named_transcript_is_used_as_given(self):
        _, path = self.transcript(("Edit", "hub/app.py"))
        png = os.path.join(self.out, "town.png")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            towncode.main(["snapshot", self.root, png, "--session", path, "--size", "40x30"])
        self.assertIn("session: 1 changed", buf.getvalue())

    def test_a_named_transcript_does_not_scan_for_transcripts(self):
        _, path = self.transcript(("Edit", "hub/app.py"))
        png = os.path.join(self.out, "town.png")
        home = tempfile.mkdtemp(prefix="towncode-home-")
        self.addCleanup(shutil.rmtree, home)
        buf = io.StringIO()
        with mock.patch.dict(os.environ, {"HOME": home}), \
             mock.patch("towncode.session.transcripts") as transcripts, \
             contextlib.redirect_stdout(buf):
            towncode.main(["snapshot", self.root, png, "--session", path, "--size", "40x30"])
        transcripts.assert_not_called()
        self.assertIn("session: 1 changed", buf.getvalue())

    def test_session_without_a_transcript_says_so(self):
        home = tempfile.mkdtemp(prefix="towncode-home-")
        self.addCleanup(shutil.rmtree, home)
        png = os.path.join(self.out, "town.png")
        with mock.patch.dict(os.environ, {"HOME": home}), self.assertRaises(SystemExit) as ctx:
            self.snapshot(png, "--session")
        self.assertIn("no Claude Code or Cursor transcript", str(ctx.exception))
        with self.assertRaises(SystemExit) as ctx:
            self.snapshot(png, "--session", os.path.join(home, "missing.jsonl"))
        self.assertIn("no such transcript", str(ctx.exception))

    def browse(self, *flags):
        with mock.patch.object(towncode.webserve, "serve", return_value=0) as serve:
            self.assertEqual(towncode.main(["view", self.root, "--browser", *flags]), 0)
        (site,), options = serve.call_args
        return site, options

    def test_view_browser_serves_the_town_on_the_default_port(self):
        site, options = self.browse()
        self.assertEqual(options, {"port": 8765, "open_browser": True})
        self.assertEqual(site.town["repo"], os.path.basename(os.path.realpath(self.root)))
        self.assertTrue(site.town["buildings"])
        first = site.town["buildings"][0]["path"]
        self.assertEqual(site.select(module=first)["focused"], [first])

    def test_view_browser_takes_a_port_and_can_leave_the_browser_closed(self):
        _, options = self.browse("--port", "0", "--no-open")
        self.assertEqual(options, {"port": 0, "open_browser": False})

    def test_view_browser_needs_no_terminal(self):
        with mock.patch("sys.stdin") as stdin:
            stdin.isatty.return_value = False
            site, _ = self.browse()
        self.assertTrue(site.town["buildings"])

    def test_watch_browser_needs_no_terminal(self):
        with mock.patch("sys.stdin") as stdin:
            stdin.isatty.return_value = False
            with mock.patch.object(towncode.webserve, "serve", return_value=0) as serve:
                self.assertEqual(towncode.main(["watch", self.root, "--browser", "--port", "0",
                                                "--no-open"]), 0)
            serve.assert_called_once()

    def test_view_browser_lays_the_town_out_as_the_terminal_does(self):
        def lots(v):
            return {path: [b.x, b.y, b.size] for path, b in v.m.buildings.items()}
        site, _ = self.browse("--layout", "roles")
        model, rows, plat, _ = towncode.run(self.root)
        roles = towncode.town(model, rows, plat, "roles")
        self.assertEqual({b["path"]: b["lot"] for b in site.town["buildings"]}, lots(roles))
        self.assertNotEqual(lots(roles), lots(towncode.town(model, rows, plat)))

    def test_view_browser_sends_no_secrets_and_leaves_the_repo_untouched(self):
        before = untouched.fingerprint(self.root)
        site, _ = self.browse()
        self.assertNotIn("SECRET-TOKEN-123", json.dumps(site.town))
        self.assertEqual(untouched.differences(before, untouched.fingerprint(self.root)), {})

    def test_snapshot_watch_writes_png(self):
        out = os.path.join(tempfile.mkdtemp(), "frame.png")
        self.addCleanup(shutil.rmtree, os.path.dirname(out))
        towncode.run(self.root)
        code = towncode.main(["snapshot", self.root, out, "--watch", "--size", "40x20", "--scale", "1"])
        self.assertEqual(code, 0)
        self.assertTrue(os.path.isfile(out))
        self.assertGreater(os.path.getsize(out), 100)

    def test_snapshot_watch_leaves_repo_untouched(self):
        before = untouched.fingerprint(self.root)
        out = os.path.join(self.out, "watch-frame.png")
        self.assertEqual(self.snapshot(out, "--watch", "--size", "40x30", "--scale", "1"), 0)
        self.assertEqual(untouched.differences(before, untouched.fingerprint(self.root)), {})

    def _survey_files(self, survey_dir):
        files = {}
        if not os.path.isdir(survey_dir):
            return files
        for name in os.listdir(survey_dir):
            path = os.path.join(survey_dir, name)
            if os.path.isfile(path):
                st = os.stat(path)
                files[name] = (st.st_mtime_ns, st.st_size)
        return files

    def test_snapshot_watch_leaves_survey_folder_unwritten(self):
        towncode.run(self.root)
        survey_dir = towncode.output_dir(self.root)
        before = self._survey_files(survey_dir)
        self.assertIn("model.json", before)
        out = os.path.join(self.out, "watch-frame.png")
        self.assertEqual(self.snapshot(out, "--watch", "--size", "40x30", "--scale", "1"), 0)
        after = self._survey_files(survey_dir)
        for name, meta in before.items():
            self.assertEqual(after.get(name), meta, msg=f"{name} changed")
        extra = set(after) - set(before)
        self.assertTrue(extra <= {"watch.json"}, msg=f"unexpected new files: {extra}")

    def test_snapshot_at_with_watch_is_refused(self):
        out = os.path.join(self.out, "watch-frame.png")
        with self.assertRaises(SystemExit) as ctx:
            self.snapshot(out, "--watch", "--at", "hub/app.py")
        self.assertIn("--watch", str(ctx.exception))

    def test_snapshot_watch_surveys_main_once(self):
        calls = []
        real = survey.survey

        def counting(root):
            calls.append(root)
            return real(root)

        out = os.path.join(self.out, "watch-frame.png")
        with mock.patch.object(towncode.survey, "survey", side_effect=counting):
            towncode.main(["snapshot", self.root, out, "--watch", "--size", "40x20", "--scale", "1"])
        self.assertEqual(len(calls), 1)


if __name__ == "__main__":
    unittest.main()
