import unittest

import pyscan
from pyscan import Import

BRANCHY = """\
def f(a, b):
    if a and b:
        return [x for x in a if x]
    for i in b:
        pass
    try:
        pass
    except ValueError:
        pass
    return 1 if a else 2
"""


class ImportsTest(unittest.TestCase):
    def test_plain_from_and_relative_imports(self):
        facts = pyscan.scan("import os, a.b\nfrom c import d, e\nfrom . import f\nfrom ..g import h\n")
        self.assertEqual(facts.imports, [
            Import("os", 0, ()), Import("a.b", 0, ()), Import("c", 0, ("d", "e")),
            Import("", 1, ("f",)), Import("g", 2, ("h",)),
        ])

    def test_imports_inside_functions_count(self):
        self.assertEqual(pyscan.scan("def f():\n    import late\n").imports, [Import("late", 0, ())])


class ExportsTest(unittest.TestCase):
    def test_dunder_all_wins(self):
        self.assertEqual(pyscan.scan("__all__ = ['b', 'a']\ndef c(): pass\n").exports, ("b", "a"))

    def test_public_functions_and_classes_by_default(self):
        src = "def run(): pass\ndef _hidden(): pass\nclass Thing: pass\nLIMIT = 3\n"
        self.assertEqual(pyscan.scan(src).exports, ("run", "Thing"))


class SizeTest(unittest.TestCase):
    def test_loc_skips_blank_and_comment_lines(self):
        self.assertEqual(pyscan.scan("# c\n\nx = 1\n  # d\ny = 2\n").loc, 2)

    def test_complexity_counts_decisions(self):
        # if, and, comprehension, its if, for, except, conditional expression
        self.assertEqual(pyscan.scan(BRANCHY).complexity, 1 + 7)


class NotesAndEntryTest(unittest.TestCase):
    def test_counts_todo_and_fixme_comments(self):
        src = "x = 1  # TODO: tidy\n# FIXME later\ns = 'TODO in a string'\n"
        self.assertEqual(pyscan.scan(src).notes, 2)

    def test_main_block_marks_an_entry_point(self):
        self.assertTrue(pyscan.scan("if __name__ == '__main__':\n    main()\n").is_entry)
        self.assertFalse(pyscan.scan("def main(): pass\n").is_entry)

    def test_top_level_call_marks_an_entry_point(self):
        self.assertTrue(pyscan.scan('"""Run me."""\nimport sys\nprint("hi")\n').is_entry)
        self.assertFalse(pyscan.scan("x = compute()\n").is_entry)
        self.assertFalse(pyscan.scan('"""Just a docstring."""\ndef helper():\n    pass\n').is_entry)


class ParseErrorTest(unittest.TestCase):
    def test_syntax_error_is_reported_not_raised(self):
        facts = pyscan.scan("def broken(:\n    pass\n")
        self.assertIn("line 1", facts.parse_error)
        self.assertEqual(facts.loc, 2)
        self.assertEqual(facts.imports, [])


if __name__ == "__main__":
    unittest.main()
