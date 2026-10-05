import os
import shutil
import stat
import subprocess
import tempfile
import unittest

import fixture
from observer import Observer


class ObserverTest(unittest.TestCase):
    def setUp(self):
        self.root = fixture.make_repo(self, {"a.py": "x = 1\n", "pkg/b.py": "y = 2\n"})

    def test_create_edit_delete_and_rename(self):
        obs = Observer(self.root)
        self.assertEqual(obs.poll(), [])
        with open(os.path.join(self.root, "new.py"), "w", encoding="utf-8") as f:
            f.write("z = 3\n")
        self.assertEqual(obs.poll(), [("create", "new.py")])
        with open(os.path.join(self.root, "a.py"), "a", encoding="utf-8") as f:
            f.write("# edit\n")
        self.assertEqual(obs.poll(), [("edit", "a.py")])
        os.rename(os.path.join(self.root, "pkg/b.py"), os.path.join(self.root, "pkg/c.py"))
        self.assertEqual(obs.poll(), [("delete", "pkg/b.py"), ("create", "pkg/c.py")])
        os.remove(os.path.join(self.root, "new.py"))
        self.assertEqual(obs.poll(), [("delete", "new.py")])

    def test_ignored_files_are_never_reported(self):
        os.makedirs(os.path.join(self.root, "build"), exist_ok=True)
        with open(os.path.join(self.root, "build", "out.o"), "w", encoding="utf-8") as f:
            f.write("binary\n")
        with open(os.path.join(self.root, ".gitignore"), "w", encoding="utf-8") as f:
            f.write("build/\n")
        obs = Observer(self.root)
        self.assertEqual(obs.poll(), [])

    def test_unreadable_files_still_produce_events(self):
        path = os.path.join(self.root, "a.py")
        os.chmod(path, 0)
        self.addCleanup(os.chmod, path, stat.S_IRUSR | stat.S_IWUSR)
        obs = Observer(self.root)
        obs.poll()
        os.utime(path, None)
        kinds = [k for k, _ in obs.poll()]
        self.assertIn("edit", kinds)

    def test_empty_repo_baseline_then_create(self):
        root = tempfile.mkdtemp(prefix="towncode-fixture-")
        self.addCleanup(shutil.rmtree, root)
        subprocess.run(["git", "init", "-q", "-b", "main", root], check=True, capture_output=True)
        obs = Observer(root)
        self.assertEqual(obs.poll(), [])
        with open(os.path.join(root, "new.py"), "w", encoding="utf-8") as f:
            f.write("z = 3\n")
        self.assertEqual(obs.poll(), [("create", "new.py")])

    def test_observer_never_opens_tracked_files(self):
        with open(os.path.join(self.root, "a.py"), "a", encoding="utf-8") as f:
            f.write("# touch\n")
        opened = []
        real = open

        def spy(path, *args, **kwargs):
            if os.path.realpath(path).startswith(os.path.realpath(self.root)):
                opened.append(os.path.relpath(path, self.root))
            return real(path, *args, **kwargs)

        with __import__("unittest.mock", fromlist=["patch"]).patch("builtins.open", spy):
            obs = Observer(self.root)
            obs.poll()
            obs.poll()
        self.assertEqual(opened, [])


if __name__ == "__main__":
    unittest.main()
