import glob
import os
import shutil
import stat
import subprocess
import tempfile
import unittest

import fixture
import watch
from events import Agent


def temp_survey(test):
    out = tempfile.mkdtemp(prefix="watch-survey-")
    test.addCleanup(shutil.rmtree, out)
    return out


def temp_wts(test, main):
    out = tempfile.mkdtemp(prefix="watch-wts-", dir=os.path.dirname(main))
    test.addCleanup(shutil.rmtree, out, ignore_errors=True)
    return out


def add_worktree(test, main, path, branch, files=None):
    wt = fixture.worktree(main, path, branch, files)
    def cleanup():
        try:
            fixture.git(main, "worktree", "remove", "--force", path)
        except subprocess.CalledProcessError:
            pass
    test.addCleanup(cleanup)
    return wt


class WatchWorktreesTest(unittest.TestCase):
    def setUp(self):
        self.main = fixture.make_repo(self, {"hub/a.py": "x = 1\n"})
        self.wts = temp_wts(self, self.main)
        self.clock = watch.FakeClock()
        self.survey = temp_survey(self)

    def _watch(self):
        return watch.Watch(self.main, clock=self.clock, survey_dir=self.survey)

    def test_team_from_branch_or_folder_name(self):
        self.assertEqual(watch.team_of("team/world/demo", "ignored"), "world")
        self.assertEqual(watch.team_of("feature/x", "my-folder"), "my-folder")

    def test_two_worktrees_on_team_branches(self):
        a = add_worktree(self, self.main, os.path.join(self.wts, "wa"), "team/a/x")
        b = add_worktree(self, self.main, os.path.join(self.wts, "wb"), "team/b/y")
        main = os.path.realpath(self.main)
        names = {w.name: w.team for w in self._watch().worktrees() if w.path != main}
        self.assertEqual(names, {"wa": "a", "wb": "b"})
        paths = {w.path for w in self._watch().worktrees()}
        self.assertEqual(paths, {main, os.path.realpath(a), os.path.realpath(b)})

    def test_refresh_worktrees_keeps_list_when_git_fails_once(self):
        add_worktree(self, self.main, os.path.join(self.wts, "wa"), "team/a/x")
        w = self._watch()
        w.poll()
        before = {x.name for x in w.worktrees()}
        real = watch._git
        calls = [0]

        def fail_once(root, *args):
            if args[:2] == ("worktree", "list"):
                calls[0] += 1
                if calls[0] == 1:
                    raise subprocess.CalledProcessError(1, "git", b"", b"")
            return real(root, *args)

        watch._git = fail_once
        try:
            self.clock.advance(watch.WORKTREE_INTERVAL)
            w.poll()
            self.assertEqual({x.name for x in w.worktrees()}, before)
            self.clock.advance(watch.WORKTREE_INTERVAL)
            w.poll()
            self.assertEqual({x.name for x in w.worktrees()}, before)
        finally:
            watch._git = real
        w.close()

    def test_merged_branch_worktree_is_not_shown(self):
        wt = add_worktree(self, self.main, os.path.join(self.wts, "done"), "team/done/x",
                          {"hub/b.py": "y = 2\n"})
        fixture.git(wt, "add", "hub/b.py")
        fixture.git(wt, "commit", "-q", "-m", "work")
        fixture.git(self.main, "merge", "--no-ff", "-q", "team/done/x", "-m", "merge done")
        w = self._watch()
        w.poll()
        shown = {i.name for i in w.worktrees() if w._shown(i)}
        self.assertNotIn("done", shown)

    def test_removed_worktree_emits_leave(self):
        wt = add_worktree(self, self.main, os.path.join(self.wts, "gone"), "team/gone/x")
        w = self._watch()
        w.poll()
        fixture.git(self.main, "worktree", "remove", "--force", wt)
        self.clock.advance(5)
        kinds = [e.kind for e in w.poll()]
        self.assertIn("leave", kinds)

    def test_removed_worktree_leave_ids_match_agents(self):
        wt = add_worktree(self, self.main, os.path.join(self.wts, "gone"), "team/gone/x")
        ledger = os.path.join(wt, ".superpowers/sdd/run-1")
        os.makedirs(ledger, exist_ok=True)
        with open(os.path.join(ledger, "task-1-brief.md"), "w", encoding="utf-8") as f:
            f.write("brief\n")
        w = self._watch()
        w.poll()
        fixture.git(self.main, "worktree", "remove", "--force", wt)
        self.clock.advance(5)
        leaves = [e for e in w.poll() if e.kind == "leave"]
        self.assertTrue(any(e.agent.id == "gone/task-1" for e in leaves))

    def test_inactive_unmerged_worktree_not_shown_at_t0(self):
        add_worktree(self, self.main, os.path.join(self.wts, "idle"), "team/idle/x")
        w = self._watch()
        idle = next(i for i in w.worktrees() if i.name == "idle")
        self.assertFalse(w._shown(idle))

    def test_fast_forward_merged_worktree_with_open_brief_is_hidden(self):
        wt = add_worktree(self, self.main, os.path.join(self.wts, "ff"), "team/ff/x",
                          {"hub/b.py": "y = 2\n"})
        fixture.git(wt, "add", "hub/b.py")
        fixture.git(wt, "commit", "-q", "-m", "work")
        ledger = os.path.join(wt, ".superpowers/sdd/run-1")
        os.makedirs(ledger, exist_ok=True)
        with open(os.path.join(ledger, "task-1-brief.md"), "w", encoding="utf-8") as f:
            f.write("x")
        fixture.git(self.main, "merge", "-q", "team/ff/x", "-m", "ff merge")
        w = self._watch()
        w.poll()
        self.clock.advance(1)
        w.poll()
        ff = next(i for i in w.worktrees() if i.name == "ff")
        self.assertFalse(w._shown(ff))

    def test_fresh_worktree_at_main_tip_with_open_brief_is_shown(self):
        wt = add_worktree(self, self.main, os.path.join(self.wts, "fresh"), "team/fresh/x")
        ledger = os.path.join(wt, ".superpowers/sdd/run-1")
        os.makedirs(ledger, exist_ok=True)
        with open(os.path.join(ledger, "task-1-brief.md"), "w", encoding="utf-8") as f:
            f.write("x")
        w = self._watch()
        w.poll()
        self.clock.advance(1)
        w.poll()
        fresh = next(i for i in w.worktrees() if i.name == "fresh")
        self.assertTrue(w._shown(fresh))

    def test_fresh_worktree_stays_shown_after_main_advances(self):
        wt = add_worktree(self, self.main, os.path.join(self.wts, "live"), "team/live/x")
        ledger = os.path.join(wt, ".superpowers/sdd/run-1")
        os.makedirs(ledger, exist_ok=True)
        with open(os.path.join(ledger, "task-1-brief.md"), "w", encoding="utf-8") as f:
            f.write("x")
        other = add_worktree(self, self.main, os.path.join(self.wts, "other"), "team/other/y",
                             {"hub/c.py": "z = 3\n"})
        fixture.git(other, "add", "hub/c.py")
        fixture.git(other, "commit", "-q", "-m", "other work")
        fixture.git(self.main, "merge", "--no-ff", "-q", "team/other/y", "-m", "other merge")
        w = self._watch()
        w.poll()
        self.clock.advance(1)
        w.poll()
        live = next(i for i in w.worktrees() if i.name == "live")
        self.assertTrue(w._shown(live))

    def test_vanished_worktree_folder_emits_leave(self):
        wt = add_worktree(self, self.main, os.path.join(self.wts, "vanished"), "team/van/x")
        w = self._watch()
        w.poll()
        shutil.rmtree(wt)
        w.poll()
        self.clock.advance(5)
        kinds = [e.kind for e in w.poll()]
        self.assertIn("leave", kinds)


class WatchLedgerTest(unittest.TestCase):
    def setUp(self):
        self.main = fixture.make_repo(self, {"hub/a.py": "x = 1\n"})
        self.wts = temp_wts(self, self.main)
        self.wt = add_worktree(self, self.main, os.path.join(self.wts, "w1"), "team/world/demo")
        self.clock = watch.FakeClock()
        self.survey = temp_survey(self)
        self.ledger = os.path.join(self.wt, ".superpowers/sdd/run-1")
        os.makedirs(self.ledger, exist_ok=True)
        with open(os.path.join(self.ledger, "task-0-brief.md"), "w", encoding="utf-8") as f:
            f.write("keep worktree shown\n")

    def _write(self, name, text="x"):
        path = os.path.join(self.ledger, name)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        return path

    def test_ledger_names_emit_lifecycle_events(self):
        w = watch.Watch(self.main, clock=self.clock, survey_dir=self.survey)
        w.poll()
        self._write("task-1-brief.md")
        self.clock.advance(1)
        kinds = [e.kind for e in w.poll()]
        self.assertIn("start", kinds)
        with open(os.path.join(self.wt, "hub/a.py"), "a", encoding="utf-8") as f:
            f.write("# e\n")
        self.clock.advance(1)
        w.poll()
        self._write("task-1-report.md")
        self.clock.advance(1)
        self.assertIn("finish", [e.kind for e in w.poll()])
        self._write("review-task-1.md")
        self.clock.advance(1)
        self.assertIn("review_start", [e.kind for e in w.poll()])
        self._write("review-task-1-result.md")
        self.clock.advance(1)
        self.assertIn("review_finish", [e.kind for e in w.poll()])

    def test_ledger_files_never_opened_even_when_unreadable(self):
        w = watch.Watch(self.main, clock=self.clock, survey_dir=self.survey)
        w.poll()
        brief = self._write("task-2-brief.md")
        os.chmod(brief, 0)
        self.addCleanup(os.chmod, brief, stat.S_IRUSR | stat.S_IWUSR)
        self.clock.advance(1)
        kinds = [e.kind for e in w.poll()]
        self.assertIn("start", kinds)

    def test_review_result_id_matches_review_stem(self):
        events = watch.scan_ledger(self.wt)
        self._write("review-task-1.md")
        self._write("review-task-1-result.md")
        events = watch.scan_ledger(self.wt)
        finishes = [e for e in events if e[0] == "review_finish"]
        self.assertEqual(len(finishes), 1)
        self.assertEqual(finishes[0][1], "w1/review-task-1")

    def test_review_result_closes_review_in_state(self):
        self._write("review-task-1.md")
        self._write("review-task-1-result.md")
        w = watch.Watch(self.main, clock=self.clock, survey_dir=self.survey)
        reviewers = [a for a in w.state().agents if a.agent.role == "reviewer"]
        self.assertEqual([], reviewers)

    def test_existing_ledger_not_replayed_on_first_poll(self):
        self._write("task-1-brief.md")
        self._write("task-1-report.md")
        self._write("review-task-1.md")
        self._write("review-task-1-result.md")
        w = watch.Watch(self.main, clock=self.clock, survey_dir=self.survey)
        lifecycle = {"start", "finish", "review_start", "review_finish"}
        first = [e.kind for e in w.poll() if e.kind in lifecycle]
        self.assertEqual([], first)
        task1 = [a for a in w.state().agents if a.agent.id == "w1/task-1"]
        self.assertEqual([], task1)
        reviewers = [a for a in w.state().agents if a.agent.role == "reviewer"]
        self.assertEqual([], reviewers)

    def test_ledger_order_start_before_finish_same_scan(self):
        w = watch.Watch(self.main, clock=self.clock, survey_dir=self.survey)
        w.poll()
        brief = self._write("task-2-brief.md")
        report = self._write("task-2-report.md")
        os.utime(brief, (100, 100))
        os.utime(report, (100, 100))
        self.clock.advance(1)
        kinds = [e.kind for e in w.poll() if e.kind in ("start", "finish")]
        self.assertEqual(["start", "finish"], kinds)


class WatchStateAgentsTest(unittest.TestCase):
    def setUp(self):
        self.main = fixture.make_repo(self, {"hub/a.py": "x = 1\n"})
        self.wts = temp_wts(self, self.main)
        self.clock = watch.FakeClock()
        self.survey = temp_survey(self)

    def test_state_excludes_merged_worktree_agents(self):
        wt = add_worktree(self, self.main, os.path.join(self.wts, "done"), "team/done/x",
                          {"hub/b.py": "y = 2\n"})
        fixture.git(wt, "add", "hub/b.py")
        fixture.git(wt, "commit", "-q", "-m", "work")
        ledger = os.path.join(wt, ".superpowers/sdd/run-1")
        os.makedirs(ledger, exist_ok=True)
        with open(os.path.join(ledger, "task-1-brief.md"), "w", encoding="utf-8") as f:
            f.write("stale brief\n")
        fixture.git(self.main, "merge", "--no-ff", "-q", "team/done/x", "-m", "merge done")
        w = watch.Watch(self.main, clock=self.clock, survey_dir=self.survey)
        w.poll()
        ids = [a.agent.id for a in w.state().agents if a.agent.worktree == "done"]
        self.assertEqual([], ids)


class WatchCommitsTest(unittest.TestCase):
    def setUp(self):
        self.main = fixture.make_repo(self, {"hub/a.py": "x = 1\n"})
        self.wts = temp_wts(self, self.main)
        self.wt = add_worktree(self, self.main, os.path.join(self.wts, "w1"), "team/world/demo")
        self.clock = watch.FakeClock()
        self.survey = temp_survey(self)
        ledger = os.path.join(self.wt, ".superpowers/sdd/run-1")
        os.makedirs(ledger, exist_ok=True)
        with open(os.path.join(ledger, "task-0-brief.md"), "w", encoding="utf-8") as f:
            f.write("active\n")

    def test_branch_tip_commit_emits_commit(self):
        w = watch.Watch(self.main, clock=self.clock, survey_dir=self.survey)
        w.poll()
        fixture.commit(self.wt, {"hub/a.py": "x = 2\n"})
        self.clock.advance(1)
        commits = [e for e in w.poll() if e.kind == "commit"]
        self.assertEqual(len(commits), 1)
        self.assertEqual(commits[0].agent.role, "implementer")


from test_survey import MONOREPO_LIKE

import focus
import survey
from session import Step, WRITE


class WatchMappingTest(unittest.TestCase):
    def setUp(self):
        self.main = fixture.make_repo(self, MONOREPO_LIKE)
        self.model = survey.survey(self.main)
        self.tracked = set(__import__("repo").Repo(self.main).files())

    def test_path_maps_to_module(self):
        kind, target = watch.map_path("hub/app.py", self.model, [], self.tracked)
        self.assertEqual((kind, target), ("module", "hub/app.py"))

    def test_unbuilt_path_maps_to_site(self):
        steps = [Step(WRITE, "Write", path="hub/newmod.py")]
        kind, target = watch.map_path("hub/newmod.py", self.model, steps, self.tracked)
        self.assertEqual(kind, "site")

    def test_unknown_file_maps_to_nearest_building(self):
        mod = watch.nearest_building("hub/deep/x.json", self.model)
        self.assertTrue(mod.startswith("hub/"))


class WatchDiffStatsTest(unittest.TestCase):
    def setUp(self):
        self.main = fixture.make_repo(self, {"hub/a.py": "x = 1\n"})
        self.wts = temp_wts(self, self.main)
        self.wt = add_worktree(self, self.main, os.path.join(self.wts, "w1"), "team/world/demo")
        self.clock = watch.FakeClock()
        self.survey = temp_survey(self)
        ledger = os.path.join(self.wt, ".superpowers/sdd/r1")
        os.makedirs(ledger, exist_ok=True)
        with open(os.path.join(ledger, "task-1-brief.md"), "w", encoding="utf-8") as f:
            f.write("brief\n")

    def test_diff_stats_after_file_event(self):
        w = watch.Watch(self.main, clock=self.clock, survey_dir=self.survey)
        w.poll()
        with open(os.path.join(self.wt, "hub/a.py"), "a", encoding="utf-8") as f:
            f.write("# two more lines\n#line2\n")
        self.clock.advance(1)
        w.poll()
        self.clock.advance(2)
        w.poll()
        stats = w.state().diff_stats.get("w1")
        self.assertIsNotNone(stats)
        self.assertGreater(stats[0] + stats[1], 0)


class WatchMergeTest(unittest.TestCase):
    def setUp(self):
        self.main = fixture.make_repo(self, {"hub/a.py": "x = 1\n"})
        self.wts = temp_wts(self, self.main)
        self.wt = add_worktree(self, self.main, os.path.join(self.wts, "w1"), "team/world/demo")
        self.clock = watch.FakeClock()
        self.survey = temp_survey(self)

    def test_merge_emitted_when_main_moves_and_clean(self):
        w = watch.Watch(self.main, clock=self.clock, survey_dir=self.survey)
        w.poll()
        fixture.commit(self.wt, {"hub/a.py": "x = 2\n"})
        fixture.git(self.main, "merge", "--no-ff", "-q", "team/world/demo", "-m", "merge")
        self.clock.advance(1)
        merges = [e for e in w.poll() if e.kind == "merge"]
        self.assertEqual(len(merges), 1)
        self.assertEqual(merges[0].agent.role, "implementer")
        self.assertTrue(w.state().main_moved_clean)

    def test_conflicting_merge_waits_then_emits_one(self):
        wt2 = add_worktree(self, self.main, os.path.join(self.wts, "w2"), "team/other/demo",
                            {"hub/b.py": "y = 1\n"})
        fixture.git(wt2, "add", "hub/b.py")
        fixture.git(wt2, "commit", "-q", "-m", "other")
        with open(os.path.join(self.main, "hub/a.py"), "w", encoding="utf-8") as f:
            f.write("main change\n")
        fixture.git(self.main, "add", "hub/a.py")
        fixture.git(self.main, "commit", "-q", "-m", "main")
        w = watch.Watch(self.main, clock=self.clock, survey_dir=self.survey)
        w.poll()
        fixture.commit(self.wt, {"hub/a.py": "wt change\n"})
        try:
            fixture.git(self.main, "merge", "--no-ff", "team/world/demo", "-m", "conflict")
        except subprocess.CalledProcessError:
            pass
        self.clock.advance(1)
        events = w.poll()
        self.assertEqual([], [e for e in events if e.kind == "merge"])
        self.assertTrue(w.state().main_mid_merge)
        with open(os.path.join(self.main, "hub/a.py"), "w", encoding="utf-8") as f:
            f.write("resolved\n")
        fixture.git(self.main, "add", "hub/a.py")
        fixture.git(self.main, "commit", "-q", "-m", "resolve")
        self.clock.advance(1)
        merges = [e for e in w.poll() if e.kind == "merge"]
        self.assertEqual(len(merges), 1)
        self.assertFalse(w.state().main_mid_merge)


class WatchColoursTest(unittest.TestCase):
    def setUp(self):
        self.main = fixture.make_repo(self, {"a.py": "x\n"})
        self.survey = temp_survey(self)
        self.clock = watch.FakeClock()

    def test_team_keeps_colour_and_ninth_reuses_lru(self):
        teams, last = watch.load_colours(self.survey)
        now = self.clock.time()
        indices = []
        for name in ("t1", "t2", "t3", "t4", "t5", "t6", "t7", "t8", "t9"):
            self.clock.advance(10)
            indices.append(watch.assign_colour(name, teams, last, self.clock.time()))
        saved = watch.save_colours_if_changed(self.survey, teams, last, {})
        teams2, _ = watch.load_colours(self.survey)
        self.assertEqual(teams2["t1"], teams["t1"])
        self.assertEqual(indices[8], indices[0])
        self.assertIn("t1", teams2)
        self.assertIn("t9", teams2)


class WatchMidBuildTest(unittest.TestCase):
    def setUp(self):
        self.main = fixture.make_repo(self, MONOREPO_LIKE)
        self.wts = temp_wts(self, self.main)
        self.wt = add_worktree(self, self.main, os.path.join(self.wts, "w1"), "team/world/demo")
        self.clock = watch.FakeClock()
        self.survey = temp_survey(self)
        ledger = os.path.join(self.wt, ".superpowers/sdd/r1")
        os.makedirs(ledger, exist_ok=True)
        with open(os.path.join(ledger, "task-1-brief.md"), "w", encoding="utf-8") as f:
            f.write("brief\n")
        with open(os.path.join(self.wt, "hub/app.py"), "a", encoding="utf-8") as f:
            f.write("# mid\n")

    def test_mid_build_places_implementer_at_latest_change(self):
        w = watch.Watch(self.main, clock=self.clock, survey_dir=self.survey)
        w.poll()
        st = w.state()
        impl = [a for a in st.agents if a.agent.role == "implementer"][0]
        self.assertEqual(impl.latest_path, "hub/app.py")


class WatchStateCheapTest(unittest.TestCase):
    def setUp(self):
        self.main = fixture.make_repo(self, {"hub/a.py": "x = 1\n"})
        self.wts = temp_wts(self, self.main)
        self.wt = add_worktree(self, self.main, os.path.join(self.wts, "w1"), "team/world/demo")
        self.clock = watch.FakeClock()
        self.survey = temp_survey(self)

    def test_state_does_not_run_git(self):
        w = watch.Watch(self.main, clock=self.clock, survey_dir=self.survey)
        w.poll()
        real_git = watch._git
        watch._git = lambda *a, **k: (_ for _ in ()).throw(AssertionError("git in state()"))
        try:
            w.state()
        finally:
            watch._git = real_git


class WatchScaffoldTest(unittest.TestCase):
    def setUp(self):
        self.main = fixture.make_repo(self, MONOREPO_LIKE)
        self.wts = temp_wts(self, self.main)
        self.wt = add_worktree(self, self.main, os.path.join(self.wts, "w1"), "team/world/demo")
        self.clock = watch.FakeClock()
        self.survey = temp_survey(self)
        ledger = os.path.join(self.wt, ".superpowers/sdd/r1")
        os.makedirs(ledger, exist_ok=True)
        with open(os.path.join(ledger, "task-1-brief.md"), "w", encoding="utf-8") as f:
            f.write("brief\n")

    def test_scaffolded_module_gets_team(self):
        with open(os.path.join(self.wt, "hub/app.py"), "a", encoding="utf-8") as f:
            f.write("# edit\n")
        w = watch.Watch(self.main, clock=self.clock, survey_dir=self.survey)
        w.poll()
        self.clock.advance(1)
        w.poll()
        st = w.state()
        self.assertIn("hub/app.py", st.scaffolded)
        self.assertEqual(st.scaffolded["hub/app.py"], "world")

    def test_scaffold_cleared_after_revert(self):
        with open(os.path.join(self.wt, "hub/app.py"), "a", encoding="utf-8") as f:
            f.write("# edit\n")
        w = watch.Watch(self.main, clock=self.clock, survey_dir=self.survey)
        w.poll()
        self.assertIn("hub/app.py", w.state().scaffolded)
        fixture.git(self.wt, "checkout", "--", "hub/app.py")
        self.clock.advance(1)
        w.poll()
        self.clock.advance(2)
        w.poll()
        self.assertNotIn("hub/app.py", w.state().scaffolded)

    def test_merge_clears_scaffold_and_sites(self):
        with open(os.path.join(self.wt, "hub/app.py"), "a", encoding="utf-8") as f:
            f.write("# edit\n")
        newmod = os.path.join(self.wt, "hub/newmod.py")
        with open(newmod, "w", encoding="utf-8") as f:
            f.write("def new():\n    pass\n")
        w = watch.Watch(self.main, clock=self.clock, survey_dir=self.survey)
        w.poll()
        st = w.state()
        self.assertIn("hub/app.py", st.scaffolded)
        self.assertIn("hub/newmod.py", st.sites)
        fixture.commit(self.wt, {"hub/newmod.py": "def new():\n    pass\n"},
                       paths=["hub/app.py", "hub/newmod.py"])
        fixture.git(self.main, "merge", "--no-ff", "-q", "team/world/demo", "-m", "merge")
        self.clock.advance(1)
        w.poll()
        st = w.state()
        self.assertNotIn("hub/app.py", st.scaffolded)
        self.assertNotIn("hub/newmod.py", st.sites)


class WatchLedgerFilterTest(unittest.TestCase):
    def setUp(self):
        self.main = fixture.make_repo(self, {"hub/a.py": "x = 1\n"})
        self.wts = temp_wts(self, self.main)
        self.wt = add_worktree(self, self.main, os.path.join(self.wts, "w1"), "team/world/demo")
        self.clock = watch.FakeClock()
        self.survey = temp_survey(self)
        ledger = os.path.join(self.wt, ".superpowers/sdd/r1")
        os.makedirs(ledger, exist_ok=True)
        with open(os.path.join(ledger, "task-1-brief.md"), "w", encoding="utf-8") as f:
            f.write("brief\n")

    def test_ledger_paths_not_file_events_or_sites(self):
        w = watch.Watch(self.main, clock=self.clock, survey_dir=self.survey)
        w.poll()
        with open(os.path.join(self.wt, ".superpowers/sdd/r1/task-2-brief.md"), "w", encoding="utf-8") as f:
            f.write("new brief\n")
        self.clock.advance(1)
        kinds = [e.kind for e in w.poll()]
        self.assertNotIn("create", kinds)
        self.assertNotIn("edit", kinds)
        paths = [e.path for e in w.poll() if e.path and ".superpowers/" in e.path]
        self.assertEqual([], paths)
        st = w.state()
        self.assertEqual([], [p for p in st.sites if ".superpowers" in p])


class WatchFlagsTest(unittest.TestCase):
    def setUp(self):
        self.main = fixture.make_repo(self, MONOREPO_LIKE)
        self.wts = temp_wts(self, self.main)
        self.wt = add_worktree(self, self.main, os.path.join(self.wts, "w1"), "team/world/demo")
        self.clock = watch.FakeClock()
        self.survey = temp_survey(self)
        self.ledger = os.path.join(self.wt, ".superpowers/sdd/r1")
        os.makedirs(self.ledger, exist_ok=True)
        with open(os.path.join(self.ledger, "task-1-brief.md"), "w", encoding="utf-8") as f:
            f.write("brief\n")

    def test_flag_on_finish_removed_on_edit(self):
        with open(os.path.join(self.wt, "hub/app.py"), "a", encoding="utf-8") as f:
            f.write("# work\n")
        w = watch.Watch(self.main, clock=self.clock, survey_dir=self.survey)
        w.poll()
        self.clock.advance(1)
        w.poll()
        with open(os.path.join(self.ledger, "task-1-report.md"), "w", encoding="utf-8") as f:
            f.write("done\n")
        self.clock.advance(1)
        w.poll()
        self.assertEqual(w.state().flags.get("w1"), "hub/app.py")
        with open(os.path.join(self.wt, "hub/app.py"), "a", encoding="utf-8") as f:
            f.write("# fix\n")
        self.clock.advance(1)
        w.poll()
        self.assertNotIn("w1", w.state().flags)

    def test_flag_on_finish_removed_on_merge(self):
        with open(os.path.join(self.wt, "hub/app.py"), "a", encoding="utf-8") as f:
            f.write("# work\n")
        w = watch.Watch(self.main, clock=self.clock, survey_dir=self.survey)
        w.poll()
        self.clock.advance(1)
        w.poll()
        with open(os.path.join(self.ledger, "task-1-report.md"), "w", encoding="utf-8") as f:
            f.write("done\n")
        self.clock.advance(1)
        w.poll()
        self.assertEqual(w.state().flags.get("w1"), "hub/app.py")
        fixture.commit(self.wt, {}, paths=["hub/app.py"])
        fixture.git(self.main, "merge", "--no-ff", "-q", "team/world/demo", "-m", "merge")
        self.clock.advance(1)
        w.poll()
        self.assertNotIn("w1", w.state().flags)


class WatchBranchViewTest(unittest.TestCase):
    def setUp(self):
        self.main = fixture.make_repo(self, MONOREPO_LIKE)
        self.wts = temp_wts(self, self.main)
        self.wt = add_worktree(self, self.main, os.path.join(self.wts, "w1"), "team/world/demo")
        self.clock = watch.FakeClock()
        self.survey = temp_survey(self)
        self.ledger = os.path.join(self.wt, ".superpowers/sdd/r1")
        os.makedirs(self.ledger, exist_ok=True)
        with open(os.path.join(self.ledger, "task-1-brief.md"), "w", encoding="utf-8") as f:
            f.write("brief\n")

    def test_branch_view_retained_and_retries_after_transient_git_failure(self):
        with open(os.path.join(self.wt, "hub/app.py"), "a", encoding="utf-8") as f:
            f.write("# v1\n")
        w = watch.Watch(self.main, clock=self.clock, survey_dir=self.survey)
        w.poll()
        before_scaffold = dict(w.state().scaffolded)
        before_stats = w.state().diff_stats["w1"]
        self.assertIn("hub/app.py", before_scaffold)
        with open(os.path.join(self.wt, "hub/app.py"), "a", encoding="utf-8") as f:
            f.write("# v2\n")
        self.clock.advance(1)
        w.poll()
        self.assertTrue(w._branch_dirty.get("w1"))
        remaining = {"n": 1}
        real_safe = watch._git_safe
        def flaky_safe(root, *args):
            if args[:1] == ("merge-base",) and remaining["n"] > 0:
                remaining["n"] -= 1
                return None
            return real_safe(root, *args)
        watch._git_safe = flaky_safe
        try:
            w._merge_base_cache.pop("w1", None)
            self.clock.advance(2)
            w.poll()
            self.assertTrue(w._branch_dirty.get("w1"))
            self.assertEqual(before_scaffold, w.state().scaffolded)
            self.assertEqual(before_stats, w.state().diff_stats["w1"])
            self.assertNotIn("w1", w._merge_base_cache)
            self.clock.advance(2)
            w.poll()
            self.assertFalse(w._branch_dirty.get("w1"))
            after = w.state().diff_stats["w1"]
            self.assertGreater(after[0] + after[1], before_stats[0] + before_stats[1])
        finally:
            watch._git_safe = real_safe

    def test_new_worktree_scaffolded_on_refresh(self):
        w = watch.Watch(self.main, clock=self.clock, survey_dir=self.survey)
        w.poll()
        late = add_worktree(self, self.main, os.path.join(self.wts, "late"), "team/late/demo")
        with open(os.path.join(late, "hub/app.py"), "a", encoding="utf-8") as f:
            f.write("# late edit\n")
        self.clock.advance(5)
        kinds = [e.kind for e in w.poll() if e.agent and e.agent.worktree == "late"]
        self.assertNotIn("edit", kinds)
        self.assertIn("hub/app.py", w.state().scaffolded)

    def test_new_worktree_emits_start_not_preseeded(self):
        w = watch.Watch(self.main, clock=self.clock, survey_dir=self.survey)
        w.poll()
        late = add_worktree(self, self.main, os.path.join(self.wts, "late"), "team/late/demo")
        ledger = os.path.join(late, ".superpowers/sdd/r1")
        os.makedirs(ledger, exist_ok=True)
        with open(os.path.join(ledger, "task-1-brief.md"), "w", encoding="utf-8") as f:
            f.write("brief\n")
        self.assertNotIn("late", w._open_briefs)
        self.clock.advance(5)
        events = w.poll()
        self.clock.advance(1)
        events += w.poll()
        starts = [e for e in events if e.kind == "start" and e.agent and e.agent.worktree == "late"]
        self.assertEqual(1, len(starts))
        self.assertEqual("late/task-1", starts[0].agent.id)
        self.assertIn(1, w._open_briefs.get("late", set()))


class WatchMergedBatchTest(unittest.TestCase):
    def setUp(self):
        self.main = fixture.make_repo(self, {"hub/a.py": "x = 1\n"})
        self.wts = temp_wts(self, self.main)
        self.clock = watch.FakeClock()
        self.survey = temp_survey(self)

    def _watch(self):
        return watch.Watch(self.main, clock=self.clock, survey_dir=self.survey)

    def test_batch_merged_matches_per_worktree_rule(self):
        ff = add_worktree(self, self.main, os.path.join(self.wts, "ff"), "team/ff/x",
                          {"hub/b.py": "y = 2\n"})
        fixture.git(ff, "add", "hub/b.py")
        fixture.git(ff, "commit", "-q", "-m", "work")
        fixture.git(self.main, "merge", "-q", "team/ff/x", "-m", "ff merge")
        noff = add_worktree(self, self.main, os.path.join(self.wts, "noff"), "team/noff/x",
                            {"hub/c.py": "z = 3\n"})
        fixture.git(noff, "add", "hub/c.py")
        fixture.git(noff, "commit", "-q", "-m", "work")
        fixture.git(self.main, "merge", "--no-ff", "-q", "team/noff/x", "-m", "noff merge")
        fresh = add_worktree(self, self.main, os.path.join(self.wts, "fresh"), "team/fresh/x")
        w = self._watch()
        for wt in w.worktrees():
            if wt.path == os.path.realpath(self.main) or not wt.branch:
                continue
            wt_tip = w._worktree_tip(wt)
            main_tip = w._poll_main_tip
            self.assertEqual(w._branch_merged(wt, wt_tip, main_tip), w._is_merged(wt))

    def test_reflog_creation_tip_from_file(self):
        wt = add_worktree(self, self.main, os.path.join(self.wts, "w1"), "team/world/demo",
                          {"hub/b.py": "y = 2\n"})
        fixture.git(wt, "add", "hub/b.py")
        fixture.git(wt, "commit", "-q", "-m", "work")
        w = self._watch()
        from_file = w._branch_creation_tip_from_file("team/world/demo")
        self.assertIsNotNone(from_file)
        self.assertEqual(from_file, w._branch_creation_tip("team/world/demo"))

    def test_reflog_creation_tip_falls_back_without_log_file(self):
        wt = add_worktree(self, self.main, os.path.join(self.wts, "fb"), "team/fb/x",
                          {"hub/b.py": "y = 2\n"})
        fixture.git(wt, "add", "hub/b.py")
        fixture.git(wt, "commit", "-q", "-m", "work")
        w = self._watch()
        log_path = os.path.join(w._git_common_dir, "logs", "refs", "heads", "team", "fb", "x")
        self.assertTrue(os.path.isfile(log_path))
        backup = log_path + ".bak"
        os.rename(log_path, backup)
        self.addCleanup(lambda: os.path.exists(backup) and os.rename(backup, log_path))
        w._creation_tip_cache.pop("team/fb/x", None)
        via_git = watch._git_safe(self.main, "log", "-g", "--format=%H", "refs/heads/team/fb/x")
        git_tip = via_git.splitlines()[-1].strip() if via_git else None
        self.assertIsNone(w._branch_creation_tip_from_file("team/fb/x"))
        self.assertEqual(w._branch_creation_tip("team/fb/x"), git_tip)


class WatchMergedObserverTest(unittest.TestCase):
    def setUp(self):
        self.main = fixture.make_repo(self, {"hub/a.py": "x = 1\n"})
        self.wts = temp_wts(self, self.main)
        self.clock = watch.FakeClock()
        self.survey = temp_survey(self)

    def test_merged_worktree_has_no_observer_until_unmerged(self):
        wt = add_worktree(self, self.main, os.path.join(self.wts, "done"), "team/done/x",
                          {"hub/b.py": "y = 2\n"})
        fixture.git(wt, "add", "hub/b.py")
        fixture.git(wt, "commit", "-q", "-m", "work")
        fixture.git(self.main, "merge", "--no-ff", "-q", "team/done/x", "-m", "merge done")
        w = watch.Watch(self.main, clock=self.clock, survey_dir=self.survey)
        self.assertNotIn(wt, w._observers)
        w.poll()
        self.assertNotIn(os.path.realpath(wt), w._observers)
        with open(os.path.join(wt, "hub/b.py"), "a", encoding="utf-8") as f:
            f.write("# new work\n")
        self.clock.advance(1)
        w.poll()
        self.assertNotIn(os.path.realpath(wt), w._observers)


class WatchLsFilesUnmergedTest(unittest.TestCase):
    def setUp(self):
        self.main = fixture.make_repo(self, {"hub/a.py": "x = 1\n"})
        self.wts = temp_wts(self, self.main)
        self.wt = add_worktree(self, self.main, os.path.join(self.wts, "w1"), "team/world/demo")
        self.clock = watch.FakeClock()
        self.survey = temp_survey(self)
        ledger = os.path.join(self.wt, ".superpowers/sdd/r1")
        os.makedirs(ledger, exist_ok=True)
        with open(os.path.join(ledger, "task-1-brief.md"), "w", encoding="utf-8") as f:
            f.write("brief\n")

    def test_ls_files_u_not_called_on_steady_poll(self):
        w = watch.Watch(self.main, clock=self.clock, survey_dir=self.survey)
        self.clock.advance(1)
        w.poll()
        calls = []

        real = watch._git

        def track(root, *args):
            if args[:1] == ("ls-files",) and "-u" in args:
                calls.append(args)
            return real(root, *args)

        watch._git = track
        try:
            self.clock.advance(1)
            w.poll()
            self.clock.advance(1)
            w.poll()
        finally:
            watch._git = real
        self.assertEqual([], calls)


class WatchObserverOrderTest(unittest.TestCase):
    def setUp(self):
        self.main = fixture.make_repo(self, {"hub/a.py": "x = 1\n"})
        self.wts = temp_wts(self, self.main)
        self.clock = watch.FakeClock()
        self.survey = temp_survey(self)

    def test_concurrent_observer_events_keep_worktree_order(self):
        names = []
        for i in range(3):
            wt = add_worktree(self, self.main, os.path.join(self.wts, f"w{i}"),
                              f"team/t{i}/demo")
            ledger = os.path.join(wt, ".superpowers/sdd/r1")
            os.makedirs(ledger, exist_ok=True)
            with open(os.path.join(ledger, "task-1-brief.md"), "w", encoding="utf-8") as f:
                f.write("brief\n")
            names.append(f"w{i}")
        w = watch.Watch(self.main, clock=self.clock, survey_dir=self.survey)
        w.poll()
        order = []
        real_poll = watch.Observer.poll

        def slow_poll(self_obs):
            wt_name = os.path.basename(self_obs.root.rstrip("/"))
            order.append(wt_name)
            return real_poll(self_obs)

        watch.Observer.poll = slow_poll
        try:
            for i, wt_path in enumerate(sorted(glob.glob(os.path.join(self.wts, "w*")))):
                with open(os.path.join(wt_path, "hub/a.py"), "a", encoding="utf-8") as f:
                    f.write(f"# {i}\n")
            self.clock.advance(1)
            events = w.poll()
        finally:
            watch.Observer.poll = real_poll
        file_events = [e for e in events if e.kind in ("create", "edit", "delete")]
        wt_order = [e.agent.worktree for e in file_events if e.agent]
        self.assertEqual(wt_order, sorted(wt_order, key=names.index))


if __name__ == "__main__":
    unittest.main()
