import json
import os
import shutil
import tempfile
import unittest

import fixture
import transcripts
import watch
from test_watch import add_worktree, temp_survey


def write_lines(path, entries):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.writelines(json.dumps(e) + "\n" for e in entries)


def use(name, **args):
    return {"type": "tool_use", "name": name, "input": args}


class WatchTranscriptsTest(unittest.TestCase):
    def setUp(self):
        self.main = fixture.make_repo(self, {"hub/a.py": "x = 1\n", "hub/b.py": "y = 2\n"})
        self.wts = os.path.join(os.path.dirname(self.main), "wts")
        self.wt = add_worktree(self, self.main, os.path.join(self.wts, "w1"), "team/world/demo")
        self.home = tempfile.mkdtemp(prefix="watch-home-")
        self.addCleanup(shutil.rmtree, self.home)
        self.survey = temp_survey(self)
        self.clock = watch.FakeClock(start=1_000_000.0)
        slug = os.path.realpath(self.main).replace("/", "-").replace(".", "-").replace("_", "-")
        self.main_transcript = os.path.join(
            self.home, ".cursor", "projects", slug.lstrip("-"),
            "agent-transcripts", "chat-1", "chat-1.jsonl")

    def _watch(self):
        return watch.Watch(self.main, home=self.home, clock=self.clock, survey_dir=self.survey)

    def _touch(self, path):
        os.utime(path, (self.clock.time(), self.clock.time()))

    def _append_read(self, path, file_path):
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps({"role": "assistant", "message": {"content": [
                use("Read", path=file_path)]}}) + "\n")
        self._touch(path)

    def test_cursor_reads_become_relative_paths(self):
        os.makedirs(os.path.dirname(self.main_transcript), exist_ok=True)
        open(self.main_transcript, "w").close()
        self._touch(self.main_transcript)
        w = self._watch()
        w.poll()
        self._append_read(self.main_transcript, os.path.join(self.main, "hub/a.py"))
        self.clock.advance(1)
        reads = [e for e in w.poll() if e.kind == "read"]
        self.assertEqual(reads[0].path, "hub/a.py")
        self.assertEqual(reads[0].agent.role, "agent")
        self.assertEqual(reads[0].agent.id, "agent:chat-1")

    def test_partial_last_line_waits_for_newline(self):
        read_path = os.path.join(self.main, "hub/a.py")
        line = json.dumps({"role": "assistant", "message": {"content": [
            use("Read", path=read_path)]}})
        os.makedirs(os.path.dirname(self.main_transcript), exist_ok=True)
        with open(self.main_transcript, "w", encoding="utf-8") as f:
            f.write(line)
        self._touch(self.main_transcript)
        w = self._watch()
        w.poll()
        self.assertEqual([], [e for e in w.poll() if e.kind == "read"])
        with open(self.main_transcript, "a", encoding="utf-8") as f:
            f.write("\n")
        self._touch(self.main_transcript)
        self.clock.advance(1)
        self.assertEqual(1, len([e for e in w.poll() if e.kind == "read"]))

    def test_touch_at_eof_emits_no_reads(self):
        os.makedirs(os.path.dirname(self.main_transcript), exist_ok=True)
        open(self.main_transcript, "w").close()
        self._touch(self.main_transcript)
        w = self._watch()
        w.poll()
        self._append_read(self.main_transcript, os.path.join(self.main, "hub/a.py"))
        self.clock.advance(1)
        self.assertEqual(1, len([e for e in w.poll() if e.kind == "read"]))
        self._touch(self.main_transcript)
        self.clock.advance(1)
        self.assertEqual([], [e for e in w.poll() if e.kind == "read"])

    def test_replaced_transcript_is_reread_from_start(self):
        os.makedirs(os.path.dirname(self.main_transcript), exist_ok=True)
        open(self.main_transcript, "w").close()
        self._touch(self.main_transcript)
        w = self._watch()
        w.poll()
        self._append_read(self.main_transcript, os.path.join(self.main, "hub/a.py"))
        self.clock.advance(1)
        w.poll()
        replacement = self.main_transcript + ".new"
        write_lines(replacement, [
            {"role": "assistant", "message": {"content": [
                use("Read", path=os.path.join(self.main, "hub/b.py"))]}}])
        os.replace(replacement, self.main_transcript)
        self._touch(self.main_transcript)
        self.clock.advance(1)
        paths = [e.path for e in w.poll() if e.kind == "read"]
        self.assertIn("hub/b.py", paths)
        self.assertNotIn("hub/a.py", paths)

    def test_shrinking_transcript_is_reread_from_start(self):
        os.makedirs(os.path.dirname(self.main_transcript), exist_ok=True)
        open(self.main_transcript, "w").close()
        self._touch(self.main_transcript)
        w = self._watch()
        w.poll()
        self._append_read(self.main_transcript, os.path.join(self.main, "hub/a.py"))
        with open(self.main_transcript, "a", encoding="utf-8") as f:
            f.write(" " * 5000 + "\n")
        self._touch(self.main_transcript)
        self.clock.advance(1)
        w.poll()
        write_lines(self.main_transcript, [
            {"role": "assistant", "message": {"content": [
                use("Read", path=os.path.join(self.main, "hub/b.py"))]}}])
        self._touch(self.main_transcript)
        self.clock.advance(1)
        paths = [e.path for e in w.poll() if e.kind == "read"]
        self.assertIn("hub/b.py", paths)

    def test_unrelated_transcript_becomes_agent_on_repo_read(self):
        os.makedirs(os.path.dirname(self.main_transcript), exist_ok=True)
        with open(self.main_transcript, "w", encoding="utf-8") as f:
            f.write(json.dumps({"role": "assistant", "message": {"content": [
                use("Read", path="/tmp/unrelated.txt")]}}) + "\n")
        self._touch(self.main_transcript)
        w = self._watch()
        w.poll()
        self.clock.advance(1)
        self.assertEqual([], [e for e in w.poll() if e.kind == "read"])
        self._append_read(self.main_transcript, os.path.join(self.main, "hub/a.py"))
        self.clock.advance(1)
        reads = [e for e in w.poll() if e.kind == "read"]
        self.assertEqual(1, len(reads))
        self.assertEqual("hub/a.py", reads[0].path)

    def test_subagent_folder_makes_orchestrator(self):
        write_lines(self.main_transcript, [{"role": "assistant", "message": {"content": []}}])
        sub = os.path.join(os.path.dirname(self.main_transcript), "subagents", "sub1.jsonl")
        write_lines(sub, [{"role": "assistant", "message": {"content": [
            use("Read", path=os.path.join(self.wt, "hub/a.py"))]}}])
        self._touch(self.main_transcript)
        w = self._watch()
        w.poll()
        self._append_read(self.main_transcript, os.path.join(self.main, "hub/a.py"))
        self.clock.advance(1)
        orch = [e for e in w.poll() if e.kind == "read" and e.agent.role == "orchestrator"]
        self.assertEqual(len(orch), 1)

    def test_subagent_outside_worktrees_stays_plain_agent(self):
        write_lines(self.main_transcript, [{"role": "assistant", "message": {"content": []}}])
        sub = os.path.join(os.path.dirname(self.main_transcript), "subagents", "sub1.jsonl")
        write_lines(sub, [{"role": "assistant", "message": {"content": [
            use("Read", path="/tmp/nowhere.txt")]}}])
        self._touch(self.main_transcript)
        w = self._watch()
        w.poll()
        self._append_read(self.main_transcript, os.path.join(self.main, "hub/a.py"))
        self.clock.advance(1)
        reads = [e for e in w.poll() if e.kind == "read"]
        self.assertEqual(1, len(reads))
        self.assertEqual("agent", reads[0].agent.role)
        self.assertEqual("agent:chat-1", reads[0].agent.id)

    def test_new_subagent_records_read_count_for_finish(self):
        write_lines(self.main_transcript, [{"role": "assistant", "message": {"content": []}}])
        self._touch(self.main_transcript)
        w = self._watch()
        w.poll()
        sub = os.path.join(os.path.dirname(self.main_transcript), "subagents", "agent-x.jsonl")
        write_lines(sub, [{"role": "assistant", "message": {"content": [
            use("Read", path=os.path.join(self.wt, "hub/a.py")),
            use("Read", path=os.path.join(self.wt, "hub/a.py"))]}}])
        self.clock.advance(1)
        w.poll()
        self.assertEqual(w.finish_read_count("w1"), 2)
        self.assertIn("read 2", w.finish_summary("w1"))

    def test_match_subagent_picks_worktree_with_most_paths(self):
        w2 = add_worktree(self, self.main, os.path.join(self.wts, "w2"), "team/other/demo")
        w = self._watch()
        paths = [
            os.path.join(self.wt, "hub/a.py"),
            os.path.join(self.wt, "hub/a.py"),
            os.path.join(w2, "other/x.py"),
        ]
        self.assertEqual(transcripts.match_subagent(paths, w.worktrees()), "w1")
        self.assertIsNone(transcripts.match_subagent(
            [os.path.join(self.main, "hub/a.py")], w.worktrees(), repo_root=self.main))


if __name__ == "__main__":
    unittest.main()
