import contextlib
import io
import json
import os
import shutil
import tempfile
import time
import unittest
from datetime import datetime, timezone
from unittest import mock

import fixture
import session
import towncode
import untouched

FILES = {"hub/a.py": "x = 1\n", "hub/b.py": "y = 2\n", "hub/c.py": "z = 3\n"}


def iso(seconds):
    return datetime.fromtimestamp(seconds, timezone.utc).isoformat().replace("+00:00", "Z")


def use(name, id=None, **args):
    return {"type": "tool_use", "id": id, "name": name, "input": args}


def result(id, error):
    return {"type": "tool_result", "tool_use_id": id, "is_error": error}


def claude(*turns):
    """Claude Code lines: (seconds, role, blocks)."""
    return [{"type": role, "timestamp": iso(at), "message": {"role": role, "content": blocks}}
            for at, role, blocks in turns]


def cursor(*blocks):
    return [{"role": "assistant", "message": {"content": list(blocks)}}]


def write_lines(path, entries):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.writelines(json.dumps(e) + "\n" for e in entries)
    return path


class SessionTest(unittest.TestCase):
    def setUp(self):
        self.root = fixture.make_repo(self, FILES)
        self.scratch = tempfile.mkdtemp(prefix="session-test-")
        self.addCleanup(shutil.rmtree, self.scratch)
        self.t0 = time.time() - 1000

    def at(self, rel):
        return os.path.join(self.root, rel)

    def claude_file(self, *turns, name="chat.jsonl"):
        return write_lines(os.path.join(self.scratch, name), claude(*turns))

    def test_claude_steps_keep_paths_and_drop_contents(self):
        path = self.claude_file(
            (self.t0, "assistant", [use("Read", "r1", file_path=self.at("hub/a.py"))]),
            (self.t0 + 1, "assistant", [use("Edit", "e1", file_path=self.at("hub/a.py"),
                                            old_string="SECRET-OLD", new_string="SECRET-NEW")]),
            (self.t0 + 2, "assistant", [use("Bash", "b1", command="python3 -m unittest\nSECRET")]),
            (self.t0 + 3, "assistant", [use("Write", "w1", file_path="/elsewhere/x.py",
                                            content="SECRET-BODY")]),
            (self.t0 + 4, "assistant", [use("WebFetch", "f1", url="https://example.com")]))
        steps = session.load(path, self.root)
        self.assertEqual([(s.kind, s.path, s.command) for s in steps], [
            ("read", "hub/a.py", None), ("edit", "hub/a.py", None),
            ("command", None, "python3 -m unittest"), ("write", "/elsewhere/x.py", None)])
        self.assertNotIn("SECRET", json.dumps([s.__dict__ for s in steps]))

    def test_a_failed_change_is_marked_and_not_counted_as_changed(self):
        path = self.claude_file(
            (self.t0, "assistant", [use("Edit", "e1", file_path=self.at("hub/a.py"))]),
            (self.t0 + 1, "user", [result("e1", True)]))
        steps = session.load(path, self.root)
        self.assertTrue(steps[0].failed)
        text = session.report("repo", path, steps, [])
        self.assertIn("changed 0 files", text)
        self.assertIn("1 failed change", text)

    def test_cursor_transcripts_map_their_own_tool_names_and_have_no_times(self):
        path = write_lines(os.path.join(self.scratch, "c", "c.jsonl"), cursor(
            use("StrReplace", path=self.at("hub/a.py")), use("Delete", path=self.at("hub/b.py")),
            use("Shell", command="git status")))
        steps = session.load(path, self.root)
        self.assertEqual([(s.kind, s.path, s.at) for s in steps], [
            ("edit", "hub/a.py", None), ("delete", "hub/b.py", None), ("command", None, None)])
        self.assertIsNone(session.changed_outside_tools(self.root, steps))
        self.assertIn("can't be checked", session.report("repo", path, steps, None))

    def test_a_tool_call_whose_input_is_not_a_dictionary_is_skipped(self):
        path = write_lines(os.path.join(self.scratch, "c", "c.jsonl"), cursor(
            {"type": "tool_use", "name": "Write", "input": "SECRET-BODY"},
            {"type": "tool_use", "name": "Shell", "input": ["git", "status"]},
            use("StrReplace", path=self.at("hub/a.py"))))
        steps = session.load(path, self.root)
        self.assertEqual([(s.kind, s.path) for s in steps], [("edit", "hub/a.py")])

    def test_without_results_an_edit_to_a_file_that_does_not_exist_counts_as_failed(self):
        path = write_lines(os.path.join(self.scratch, "c", "c.jsonl"), cursor(
            use("StrReplace", path=self.at("missing.py")), use("StrReplace", path=self.at("hub/a.py"))))
        steps = session.load(path, self.root)
        self.assertEqual([s.failed for s in steps], [True, False])
        text = session.report("repo", path, steps, None)
        self.assertIn("changed 1 file", text)
        self.assertNotIn("missing.py", text)

    def test_subagent_steps_are_included_in_time_order_and_marked(self):
        path = self.claude_file(
            (self.t0, "assistant", [use("Read", "r1", file_path=self.at("hub/a.py"))]),
            (self.t0 + 5, "assistant", [use("Read", "r2", file_path=self.at("hub/c.py"))]))
        write_lines(os.path.join(self.scratch, "chat", "subagents", "agent-x.jsonl"), claude(
            (self.t0 + 2, "assistant", [use("Edit", "s1", file_path=self.at("hub/b.py"))])))
        steps = session.load(path, self.root)
        self.assertEqual([(s.path, s.agent) for s in steps], [
            ("hub/a.py", "main"), ("hub/b.py", "agent-x"), ("hub/c.py", "main")])

    def test_an_edit_without_a_read_first_is_flagged(self):
        path = write_lines(os.path.join(self.scratch, "c", "c.jsonl"), cursor(
            use("Read", path=self.at("hub/a.py")), use("StrReplace", path=self.at("hub/a.py")),
            use("StrReplace", path=self.at("hub/b.py"))))
        text = session.report("repo", path, session.load(path, self.root), None)
        flagged = text.split("Edited without reading it first:")[1].split("\n\n")[0]
        self.assertIn("hub/b.py", flagged)
        self.assertNotIn("hub/a.py", flagged)

    def test_files_changed_during_the_session_but_not_by_a_tool_are_listed(self):
        path = self.claude_file(
            (self.t0, "assistant", [use("Edit", "e1", file_path=self.at("hub/a.py"))]),
            (self.t0 + 100, "assistant", [use("Bash", "b1", command="sed -i '' s/y/q/ hub/b.py")]))
        during = self.t0 + 50
        for rel in ("hub/a.py", "hub/b.py"):
            os.utime(self.at(rel), (during, during))
        stray = session.changed_outside_tools(self.root, session.load(path, self.root))
        self.assertEqual(stray, ["hub/b.py"])

    def test_transcripts_for_a_repo_are_found_for_both_agents_oldest_first(self):
        home = os.path.join(self.scratch, "home")
        slug = os.path.realpath(self.root).replace("/", "-").replace(".", "-").replace("_", "-")
        old = write_lines(os.path.join(home, ".claude", "projects", slug, "a.jsonl"), [])
        new = write_lines(os.path.join(home, ".cursor", "projects", slug.lstrip("-"),
                                       "agent-transcripts", "b", "b.jsonl"), [])
        write_lines(os.path.join(home, ".claude", "projects", "-elsewhere", "c.jsonl"), [])
        os.utime(old, (self.t0, self.t0))
        self.assertEqual(session.transcripts(self.root, home), [old, new])

    def test_main_saves_outside_the_repo_and_leaves_it_untouched(self):
        out = os.path.join(self.scratch, "out")
        path = self.claude_file(
            (self.t0, "assistant", [use("Edit", "e1", file_path=self.at("hub/a.py"))]))
        before = untouched.fingerprint(self.root)
        with mock.patch.dict(os.environ, {"TOWNCODE_SURVEY_DIR": out}), \
                contextlib.redirect_stdout(io.StringIO()) as buf:
            self.assertEqual(session.main([self.root, path]), 0)
            saved = os.path.join(towncode.output_dir(self.root), "session.json")
        self.assertIn("hub/a.py (edit)", buf.getvalue())
        with open(saved, encoding="utf-8") as f:
            self.assertEqual(json.load(f)["steps"][0]["path"], "hub/a.py")
        self.assertEqual(untouched.differences(before, untouched.fingerprint(self.root)), {})


if __name__ == "__main__":
    unittest.main()
