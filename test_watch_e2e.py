import contextlib
import io
import os
import shutil
import tempfile
import unittest
from unittest import mock

import fixture
import survey
import towncode
import untouched
import watch
from events import Agent, Event
from test_watch import add_worktree, temp_survey, temp_wts


class WatchE2ETest(unittest.TestCase):
    def setUp(self):
        self.main = fixture.make_repo(self, {"hub/a.py": "x = 1\n"})
        self.wts = temp_wts(self, self.main)
        self.clock = watch.FakeClock()
        self.survey = temp_survey(self)
        self.home = tempfile.mkdtemp(prefix="watch-e2e-home-")
        self.addCleanup(shutil.rmtree, self.home)

    def _run_script(self, *, on_poll=None):
        wt = add_worktree(self, self.main, os.path.join(self.wts, "demo"), "team/world/demo")
        ledger = os.path.join(wt, ".superpowers/sdd/run-1")
        os.makedirs(ledger, exist_ok=True)
        with open(os.path.join(ledger, "task-0-brief.md"), "w", encoding="utf-8") as f:
            f.write("active\n")
        events = []
        w = watch.Watch(self.main, home=self.home, clock=self.clock, survey_dir=self.survey)

        def poll():
            def poll_once():
                batch = w.poll()
                events.extend(batch)
                self.clock.advance(1)
                return batch

            if on_poll is not None:
                on_poll(w, poll_once)
            else:
                poll_once()

        poll()
        with open(os.path.join(ledger, "task-1-brief.md"), "w", encoding="utf-8") as f:
            f.write("brief\n")
        poll()
        with open(os.path.join(wt, "hub/a.py"), "a", encoding="utf-8") as f:
            f.write("# e\n")
        poll()
        with open(os.path.join(wt, "hub/new.py"), "w", encoding="utf-8") as f:
            f.write("y = 2\n")
        poll()
        fixture.git(wt, "add", "--", "hub/a.py", "hub/new.py")
        fixture.git(wt, "commit", "-q", "-m", "change")
        poll()
        with open(os.path.join(ledger, "task-1-report.md"), "w", encoding="utf-8") as f:
            f.write("done\n")
        poll()
        with open(os.path.join(ledger, "review-task-1.md"), "w", encoding="utf-8") as f:
            f.write("review\n")
        poll()
        with open(os.path.join(ledger, "review-task-1-result.md"), "w", encoding="utf-8") as f:
            f.write("ok\n")
        poll()
        fixture.git(self.main, "merge", "--no-ff", "-q", "team/world/demo", "-m", "merge")
        poll()
        fixture.git(self.main, "worktree", "remove", "--force", wt)
        self.clock.advance(5)
        poll()
        return [e.kind for e in events]

    def test_event_order_for_fake_run(self):
        kinds = self._run_script()
        expected = ["start", "edit", "create", "commit", "finish",
                    "review_start", "review_finish", "merge", "leave"]
        filtered = [k for k in kinds if k in expected]
        self.assertEqual(filtered, expected)

    def test_lifecycle_agent_ids(self):
        wt = add_worktree(self, self.main, os.path.join(self.wts, "demo"), "team/world/demo")
        ledger = os.path.join(wt, ".superpowers/sdd/run-1")
        os.makedirs(ledger, exist_ok=True)
        with open(os.path.join(ledger, "task-0-brief.md"), "w", encoding="utf-8") as f:
            f.write("active\n")
        events = []
        w = watch.Watch(self.main, home=self.home, clock=self.clock, survey_dir=self.survey)

        def poll():
            events.extend(w.poll())
            self.clock.advance(1)

        poll()
        with open(os.path.join(ledger, "task-1-brief.md"), "w", encoding="utf-8") as f:
            f.write("brief\n")
        poll()
        with open(os.path.join(ledger, "task-1-report.md"), "w", encoding="utf-8") as f:
            f.write("done\n")
        poll()
        with open(os.path.join(ledger, "review-task-1.md"), "w", encoding="utf-8") as f:
            f.write("review\n")
        poll()
        with open(os.path.join(ledger, "review-task-1-result.md"), "w", encoding="utf-8") as f:
            f.write("ok\n")
        poll()
        lifecycle = [e for e in events if e.kind in (
            "start", "finish", "review_start", "review_finish")]
        self.assertEqual(
            [(e.kind, e.agent.id) for e in lifecycle],
            [("start", "demo/task-1"), ("finish", "demo/task-1"),
             ("review_start", "demo/review-task-1"), ("review_finish", "demo/review-task-1")])

    def test_watch_leaves_repo_and_worktrees_untouched(self):
        wt_path = add_worktree(self, self.main, os.path.join(self.wts, "x"), "team/x/y")
        before_main = untouched.fingerprint(self.main)
        before_wt = untouched.fingerprint(wt_path)
        w = watch.Watch(self.main, home=self.home, clock=self.clock, survey_dir=self.survey)
        for _ in range(5):
            w.poll()
            self.clock.advance(1)
        self.assertEqual(untouched.differences(before_main, untouched.fingerprint(self.main)), {})
        self.assertEqual(untouched.differences(before_wt, untouched.fingerprint(wt_path)), {})


class TowncodeWatchCLITest(unittest.TestCase):
    def setUp(self):
        self.root = fixture.make_repo(self, {"a.py": "x\n"})
        self.survey = temp_survey(self)
        self.home = tempfile.mkdtemp(prefix="watch-cli-home-")
        self.addCleanup(shutil.rmtree, self.home)

    def test_plain_watch_starts_viewer_with_tty(self):
        with mock.patch("sys.stdin.isatty", return_value=True):
            with mock.patch("viewer.run_watch", side_effect=KeyboardInterrupt):
                code = towncode.main(["watch", self.root])
        self.assertEqual(code, 0)

    def test_watch_requires_tty_like_view(self):
        with mock.patch("sys.stdin.isatty", return_value=False):
            with self.assertRaises(SystemExit) as ctx:
                towncode.main(["watch", self.root])
            self.assertIn("interactive terminal", str(ctx.exception))

    def test_watch_surveys_main_once(self):
        calls = []
        real = survey.survey

        def counting(root):
            calls.append(root)
            return real(root)

        with mock.patch.object(towncode.survey, "survey", side_effect=counting):
            with mock.patch("sys.stdin.isatty", return_value=True):
                with mock.patch("viewer.run_watch", side_effect=KeyboardInterrupt):
                    towncode.main(["watch", self.root])
        self.assertEqual(len(calls), 1)

    def test_watch_without_prior_survey_writes_only_watch_json(self):
        out = towncode.output_dir(self.root)
        self.assertFalse(os.path.exists(out))
        with mock.patch("sys.stdin.isatty", return_value=True):
            with mock.patch("viewer.run_watch", side_effect=KeyboardInterrupt):
                towncode.main(["watch", self.root])
        if os.path.isdir(out):
            names = set(os.listdir(out))
            self.assertTrue(names <= {"watch.json"}, msg=f"unexpected files: {names - {'watch.json'}}")

    def test_events_loop_uses_injectable_sleep(self):
        root = fixture.make_repo(self, {"a.py": "x\n"})
        sleeps = []
        args = towncode._parser().parse_args(["watch", root, "--events"])
        with contextlib.redirect_stdout(io.StringIO()):
            code = towncode._watch(args, sleep=lambda s: sleeps.append(s) or (_ for _ in ()).throw(
                KeyboardInterrupt), home=self.home, survey_dir=self.survey)
        self.assertEqual(code, 0)
        self.assertEqual(sleeps, [1])

    def test_events_print_tab_separated_format(self):
        event = Event("start", Agent("demo/task-1", "implementer", "world", "demo"), "hub/a.py")

        class FakeWatch:
            def __init__(self, *_a, **_k):
                self._n = 0

            def poll(self):
                self._n += 1
                if self._n == 1:
                    return [event]
                raise KeyboardInterrupt

            def close(self):
                pass

        root = fixture.make_repo(self, {"a.py": "x\n"})
        args = towncode._parser().parse_args(["watch", root, "--events"])
        buf = io.StringIO()
        with mock.patch("watch.Watch", FakeWatch):
            with contextlib.redirect_stdout(buf):
                towncode._watch(args, sleep=lambda _: None, home=self.home, survey_dir=self.survey)
        self.assertEqual(buf.getvalue(), "start\tdemo/task-1\thub/a.py\n")

    def test_broken_pipe_exits_zero(self):
        event = Event("start", Agent("w1/task-1", "implementer", "world", "w1"), None)

        class FakeWatch:
            def __init__(self, *_a, **_k):
                pass

            def poll(self):
                return [event]

            def close(self):
                pass

        class BrokenStdout(io.TextIOBase):
            def write(self, _s):
                raise BrokenPipeError()

            def flush(self):
                raise BrokenPipeError()

        root = fixture.make_repo(self, {"a.py": "x\n"})
        args = towncode._parser().parse_args(["watch", root, "--events"])
        with mock.patch("watch.Watch", FakeWatch):
            with mock.patch("sys.stdout", BrokenStdout()):
                code = towncode._watch(args, sleep=lambda _: None, home=self.home,
                                       survey_dir=self.survey)
        self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
