import unittest
from unittest import mock

import langkit
from langtest import needs_grammar

JS = ("// TODO: tidy\n"
      "import a from './a';\n"
      "/* a block\n   comment */\n"
      "function f(x) { if (x && y || z) { return `two\nlines`; } }\n")


@needs_grammar("javascript")
class TreeHelpersTest(unittest.TestCase):
    def setUp(self):
        self.tree = langkit.parse("javascript", JS)

    def test_lines_skip_comments_and_count_every_line_of_a_multiline_string(self):
        self.assertEqual(langkit.loc(JS, self.tree, {"comment"}), 3)

    def test_notes_are_comment_lines_with_todo_or_fixme(self):
        self.assertEqual(langkit.notes(self.tree, {"comment"}), 1)

    def test_count_types_filters_operators(self):
        root = self.tree.root_node
        self.assertEqual(langkit.count_types(root, ["if_statement"]), 1)
        self.assertEqual(langkit.count_types(root, [("binary_expression", ("&&", "||"))]), 2)
        self.assertEqual(langkit.count_types(root, [("binary_expression", ("??",))]), 0)

    def test_walk_visits_the_root_first_then_source_order(self):
        types = [n.type for n in langkit.walk(self.tree.root_node)]
        self.assertEqual(types[0], "program")
        self.assertLess(types.index("import_statement"), types.index("function_declaration"))

    def test_captures_and_matches_run_queries(self):
        pattern = "(import_statement source: (string (string_fragment) @spec))"
        caps = langkit.captures("javascript", pattern, self.tree.root_node)
        self.assertEqual([langkit.node_text(n) for n in caps["spec"]], ["./a"])
        self.assertEqual(len(langkit.matches("javascript", pattern, self.tree.root_node)), 1)

    def test_first_error_names_the_line(self):
        self.assertIsNone(langkit.first_error(self.tree))
        error = langkit.first_error(langkit.parse("javascript", "let a = 1;\nfunction (\n"))
        self.assertTrue(error.startswith("line 2: "), error)


class GrammarGuardTest(unittest.TestCase):
    def test_a_grammar_that_is_not_downloaded_is_never_requested(self):
        with mock.patch.object(langkit, "_ready", frozenset()), \
                mock.patch.object(langkit, "_parsers", {}), \
                mock.patch.object(langkit, "_languages", {}):
            if langkit.pack is not None:
                with mock.patch.object(langkit.pack, "get_language",
                                       side_effect=AssertionError("would download")):
                    self.assertIsNone(langkit.parse("javascript", "x"))
                    with self.assertRaises(LookupError):
                        langkit.language("javascript")
            else:
                self.assertIsNone(langkit.parse("javascript", "x"))

    def test_ready_grammars_come_from_what_is_already_downloaded(self):
        if langkit.pack is None:
            self.skipTest("tree-sitter not installed")
        with mock.patch.object(langkit, "_ready", None), \
                mock.patch.object(langkit.pack, "downloaded_languages", return_value=["go"]):
            self.assertTrue(langkit.grammar_ready("go"))
            self.assertFalse(langkit.grammar_ready("rust"))


class SymbolIndexTest(unittest.TestCase):
    def setUp(self):
        self.index = langkit.SymbolIndex([
            ("com.a", "App", "a/App.java"), ("com.a", "Util", "a/Util.java"),
            ("com.b", "Dup", "b/One.java"), ("com.b", "Dup", "b/Two.java"),
        ])

    def test_lookup_finds_the_one_declaring_file(self):
        self.assertEqual(self.index.lookup("com.a", "Util"), "a/Util.java")
        self.assertIsNone(self.index.lookup("com.a", "Missing"))

    def test_an_ambiguous_name_finds_nothing_unless_all_are_asked_for(self):
        self.assertIsNone(self.index.lookup("com.b", "Dup"))
        self.assertEqual(self.index.lookup_all("com.b", "Dup"), ("b/One.java", "b/Two.java"))

    def test_in_scope_lists_every_file_declaring_there(self):
        self.assertEqual(self.index.in_scope("com.a"), ("a/App.java", "a/Util.java"))


if __name__ == "__main__":
    unittest.main()
