import unittest

import floor


class FloorFactsTest(unittest.TestCase):
    def test_lines_notes_and_rough_complexity_use_the_language_comment_markers(self):
        text = ("#!/usr/bin/env elixir\n# TODO: split\ndefmodule A do\n"
                "  def f(x), do: if x && y, do: 1\nend\n\n")
        self.assertEqual(floor.facts("lib/a.ex", text), (3, 3, 1))

    def test_c_like_block_comment_lines_are_not_code(self):
        text = "/*\n * FIXME: later\n */\nint main() { while (1) {} }\n"
        self.assertEqual(floor.facts("a.zig", text)[0], 4)
        self.assertEqual(floor.facts("a.d", text), (1, 2, 1))

    def test_unknown_extensions_use_common_markers(self):
        self.assertEqual(floor.facts("a.weird", "// note\n# note\ncode\n")[0], 1)


class FloorTestsByNameTest(unittest.TestCase):
    def test_test_names_point_at_a_stem(self):
        cases = {"a.test.ts": "a", "a.spec.js": "a", "a_test.go": "a", "test_a.py": "a",
                 "ATest.java": "A", "ATests.cs": "A", "user_spec.rb": "user",
                 "foo.min.js": None, "Test.java": None, "Contest.java": None, "x.go": None}
        for name, stem in cases.items():
            self.assertEqual(floor.test_stem(name), stem, name)

    def test_test_folders_and_names_make_a_test(self):
        self.assertTrue(floor.is_test("spec/helper.rb"))
        self.assertTrue(floor.is_test("lib/a_test.exs"))
        self.assertFalse(floor.is_test("lib/contest.ex"))

    def test_pairing_prefers_the_same_folder_then_the_mirrored_path(self):
        sources = {"lib/a/b.ex": "elixir", "lib/c/b.ex": "elixir", "src/x/d.ex": "elixir"}
        tests = {"lib/a/b_test.exs": "elixir", "test/x/d_test.exs": "elixir"}
        self.assertEqual(floor.pair_tests(tests, sources),
                         {"lib/a/b_test.exs": "lib/a/b.ex", "test/x/d_test.exs": "src/x/d.ex"})

    def test_ambiguous_or_other_language_matches_pair_nothing(self):
        sources = {"a/b.ex": "elixir", "c/b.ex": "elixir", "e/f.lua": "lua"}
        tests = {"t/b_test.exs": "elixir", "t/f_test.exs": "elixir"}
        self.assertEqual(floor.pair_tests(tests, sources), {})


class FloorHelpersTest(unittest.TestCase):
    def test_interpreter_reads_env_and_direct_shebangs(self):
        self.assertEqual(floor.interpreter("#!/usr/bin/env bash\n"), "bash")
        self.assertEqual(floor.interpreter("#!/bin/sh -e\n"), "sh")
        self.assertEqual(floor.interpreter("#!/usr/bin/env -S node --flag\n"), "node")
        self.assertIsNone(floor.interpreter("echo hi\n"))

    def test_minified_means_one_huge_line_and_long_lines_on_average(self):
        self.assertTrue(floor.is_minified("x" * 5000 + "\n"))
        self.assertFalse(floor.is_minified("x" * 5000 + "\n" + "y\n" * 100))
        self.assertFalse(floor.is_minified(""))


if __name__ == "__main__":
    unittest.main()
