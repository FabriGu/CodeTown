import unittest

from pyscan import Import
from resolve import Resolver

FILES = [
    "desktop/__init__.py", "desktop/main.py", "desktop/launcher.py",
    "hub/app.py", "hub/records.py",
    "apps/sample-app/app.py",
    "packages/core_sdk/__init__.py", "packages/core_sdk/manifest.py",
    "tests/test_hub.py",
]


class ResolveTest(unittest.TestCase):
    def setUp(self):
        self.r = Resolver(FILES, known_external={"flask"})

    def resolve(self, importer, module, level=0, names=()):
        return self.r.resolve(importer, Import(module, level, tuple(names)))

    def test_package_import(self):
        self.assertEqual(self.resolve("desktop/main.py", "desktop.launcher"),
                         ({"desktop/launcher.py"}, None))

    def test_from_import_of_a_submodule_skips_the_package(self):
        self.assertEqual(self.resolve("desktop/main.py", "core_sdk", names=["manifest"]),
                         ({"packages/core_sdk/manifest.py"}, None))

    def test_from_import_of_a_name_lands_on_the_package(self):
        self.assertEqual(self.resolve("hub/app.py", "core_sdk", names=["check_app"]),
                         ({"packages/core_sdk/__init__.py"}, None))

    def test_sibling_script_import(self):
        self.assertEqual(self.resolve("hub/app.py", "records"), ({"hub/records.py"}, None))

    def test_ambiguous_name_prefers_the_same_folder(self):
        self.assertEqual(self.resolve("apps/sample-app/views.py", "app"),
                         ({"apps/sample-app/app.py"}, None))

    def test_ambiguous_name_then_prefers_the_shortest_path(self):
        self.assertEqual(self.resolve("tests/test_hub.py", "app"), ({"hub/app.py"}, None))

    def test_relative_import(self):
        self.assertEqual(self.resolve("desktop/main.py", "", level=1, names=["launcher"]),
                         ({"desktop/launcher.py"}, None))

    def test_stdlib_is_ignored_and_third_party_is_external(self):
        self.assertEqual(self.resolve("hub/app.py", "json"), (set(), None))
        self.assertEqual(self.resolve("hub/app.py", "flask"), (set(), "flask"))
        self.assertEqual(self.resolve("hub/app.py", "boto3.session"), (set(), "boto3"))

    def test_declared_requirement_beats_a_same_named_repo_file(self):
        r = Resolver(FILES + ["tools/flask.py"], known_external={"flask"})
        self.assertEqual(r.resolve("hub/app.py", Import("flask", 0, ())), (set(), "flask"))


if __name__ == "__main__":
    unittest.main()
