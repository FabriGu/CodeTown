import unittest

import fixture
import survey
from model import Model

MONOREPO_LIKE = {
    "packages/core_sdk/__init__.py": "",
    "packages/core_sdk/manifest.py": "def load(path):\n    return path\n",
    "packages/core_sdk/dev.py": "def run():\n    pass\n",
    "hub/app.py": ("from core_sdk import manifest\nimport records\nimport flask\nimport json\n\n"
                   "if __name__ == '__main__':\n    manifest.load('x')\n"),
    "hub/records.py": "import app\n# TODO: split this up\ndef save():\n    pass\n",
    "hub/unused.py": "def nobody():\n    pass\n",
    "desktop/broken.py": "def broken(:\n",
    "scripts/tool.sh": "echo hi\n",
    "tests/test_manifest.py": "from core_sdk import manifest\nMARKER = 'CANARY_SOURCE_TEXT'\n",
    "requirements.txt": "flask==3.0\n# a comment\n",
    "README.md": "Run `python -m core_sdk.dev` to preview an app.\n",
}


class SurveyTest(unittest.TestCase):
    def setUp(self):
        root = fixture.make_repo(self, MONOREPO_LIKE, untracked={
            "token.txt": "SECRET-TOKEN-123\n", "leftover.py": "x = 1\n"})
        self.model = survey.survey(root)

    def test_modules_tests_and_floor_buildings_are_classified(self):
        kinds = {m.id: m.kind for m in self.model.modules.values()}
        self.assertEqual(kinds["hub/app.py"], "source")
        self.assertEqual(kinds["tests/test_manifest.py"], "test")
        self.assertEqual(kinds["scripts/tool.sh"], "source")
        self.assertNotIn("token.txt", kinds)
        self.assertNotIn("leftover.py", kinds)
        self.assertNotIn("README.md", kinds)

    def test_districts_are_top_level_folders(self):
        self.assertEqual(self.model.modules["packages/core_sdk/manifest.py"].district, "packages")

    def test_imports_become_edges(self):
        self.assertEqual(self.model.edges, {
            ("hub/app.py", "packages/core_sdk/manifest.py"): 1,
            ("hub/app.py", "hub/records.py"): 1,
            ("hub/records.py", "hub/app.py"): 1,
        })

    def test_outside_packages_skip_the_standard_library(self):
        self.assertEqual(self.model.externals, {"flask": ["hub/app.py"]})

    def test_tests_mark_what_they_import(self):
        self.assertEqual(self.model.modules["packages/core_sdk/manifest.py"].tested_by,
                         ["tests/test_manifest.py"])

    def test_facts_from_the_parser(self):
        mods = self.model.modules
        self.assertTrue(mods["hub/app.py"].is_entry)
        self.assertEqual(mods["hub/records.py"].notes, 1)
        self.assertIn("line 1", mods["desktop/broken.py"].parse_error)
        self.assertEqual(mods["hub/records.py"].churn, 1)

    def test_mentions_in_docs_and_config_count(self):
        self.assertTrue(self.model.modules["packages/core_sdk/dev.py"].mentioned)
        self.assertFalse(self.model.modules["hub/unused.py"].mentioned)

    def test_importers_lists_who_imports_each_module(self):
        self.assertEqual(self.model.importers()["hub/app.py"], ["hub/records.py"])

    def test_model_round_trips_through_json(self):
        self.assertEqual(Model.from_dict(self.model.to_dict()), self.model)

    def test_a_model_saved_before_renames_still_loads(self):
        data = self.model.to_dict()
        del data["renames"]
        self.assertEqual(Model.from_dict(data).renames, {})

    def test_renames_that_end_at_a_current_module_are_recorded(self):
        root = fixture.make_repo(self, {"hub/old.py": "x = 1\n", "hub/keep.py": "y = 2\n"})
        fixture.git(root, "mv", "hub/old.py", "hub/new.py")
        fixture.git(root, "commit", "-q", "-m", "rename")
        self.assertEqual(survey.survey(root).renames, {"hub/old.py": "hub/new.py"})


FILENAME_MENTION = {
    "scripts/tool_x.py": 'print("tool_x runs")\n',
    "apps/a/main.py": "def run_a():\n    pass\n",
    "apps/b/main.py": "def run_b():\n    pass\n",
    "tests/test_tools.py": (
        'import importlib.util\n'
        'from pathlib import Path\n\n'
        'ROOT = Path(__file__).resolve().parents[1]\n'
        'TOOL = ROOT / "scripts" / "tool_x.py"\n'
        'MAIN = "main.py"\n\n'
        'def test_tool_x():\n'
        '    spec = importlib.util.spec_from_file_location("tool_x", TOOL)\n'
        '    assert spec is not None\n'
    ),
}


class FilenameMentionTest(unittest.TestCase):
    def setUp(self):
        root = fixture.make_repo(self, FILENAME_MENTION)
        self.model = survey.survey(root)

    def test_unique_basename_quoted_in_test_counts_as_tested(self):
        self.assertEqual(self.model.modules["scripts/tool_x.py"].tested_by,
                         ["tests/test_tools.py"])

    def test_ambiguous_basename_is_not_linked(self):
        self.assertEqual(self.model.modules["apps/a/main.py"].tested_by, [])
        self.assertEqual(self.model.modules["apps/b/main.py"].tested_by, [])


VENDOR_FILTER = {
    "apps/a/main.py": "",
    "apps/a/site/vendor/lib.mjs": "",
    "vendor/pkg/thing.py": "",
    "lib/vendor.py": "",
    "tools/vendored/x.py": "",
    "README.md": "See vendor/pkg/thing.py for details.\n",
}


class VendorFilterTest(unittest.TestCase):
    def setUp(self):
        root = fixture.make_repo(self, VENDOR_FILTER)
        self.model = survey.survey(root)

    def test_vendored_folders_are_excluded_from_modules(self):
        ids = set(self.model.modules)
        self.assertNotIn("apps/a/site/vendor/lib.mjs", ids)
        self.assertNotIn("vendor/pkg/thing.py", ids)
        self.assertIn("lib/vendor.py", ids)
        self.assertIn("tools/vendored/x.py", ids)


if __name__ == "__main__":
    unittest.main()
