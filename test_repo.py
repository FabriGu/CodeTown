import os
import unittest

import fixture
import untouched
from repo import NotTracked, Repo


class RepoTest(unittest.TestCase):
    def setUp(self):
        self.root = fixture.make_repo(
            self, {"a.py": "x = 1\n", "pkg/b.py": "y = 2\n"},
            untracked={"token.txt": "SECRET-TOKEN-123\n"})

    def test_files_lists_only_tracked_files(self):
        self.assertEqual(Repo(self.root).files(), ["a.py", "pkg/b.py"])

    def test_reading_an_untracked_file_is_refused(self):
        with self.assertRaises(NotTracked):
            Repo(self.root).read_text("token.txt")

    def test_reads_tracked_text(self):
        self.assertEqual(Repo(self.root).read_text("pkg/b.py"), "y = 2\n")

    def test_tracked_symlinks_are_not_followed(self):
        os.symlink(os.path.join(self.root, "token.txt"), os.path.join(self.root, "link.txt"))
        fixture.commit(self.root, {}, "add link", paths=["link.txt"])
        self.assertIsNone(Repo(self.root).read_text("link.txt"))

    def test_churn_counts_commits_per_file(self):
        fixture.commit(self.root, {"a.py": "x = 2\n"})
        fixture.commit(self.root, {"a.py": "x = 3\n"})
        churn = Repo(self.root).churn(days=90)
        self.assertEqual(churn["a.py"], 3)
        self.assertEqual(churn["pkg/b.py"], 1)

    def test_renames_follow_a_chain_to_the_current_path(self):
        fixture.git(self.root, "mv", "a.py", "b.py")
        fixture.git(self.root, "commit", "-q", "-m", "rename")
        fixture.git(self.root, "mv", "b.py", "pkg/c.py")
        fixture.git(self.root, "commit", "-q", "-m", "move")
        self.assertEqual(Repo(self.root).renames(), {"a.py": "pkg/c.py", "b.py": "pkg/c.py"})

    def test_reading_leaves_the_repo_untouched(self):
        before = untouched.fingerprint(self.root)
        r = Repo(self.root)
        r.files()
        r.read_text("a.py")
        r.churn()
        self.assertEqual(untouched.differences(before, untouched.fingerprint(self.root)), {})

    def test_fingerprint_only_opens_files_it_is_allowed_to(self):
        prints = untouched.fingerprint(self.root, hashable=lambda rel: rel != "token.txt")
        self.assertIsNone(prints["token.txt"][3])
        self.assertIsNotNone(prints["a.py"][3])


if __name__ == "__main__":
    unittest.main()
