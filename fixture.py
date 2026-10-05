"""Test helper: throwaway git repositories for survey tests."""

import os
import shutil
import subprocess
import tempfile

GIT_ID = ["-c", "user.name=Fixture", "-c", "user.email=fixture@example.com",
          "-c", "commit.gpgsign=false", "-c", "core.hooksPath=/dev/null",
          "-c", "core.fsmonitor=false"]


def git(root, *args):
    subprocess.run(["git", "-C", root, *GIT_ID, *args], check=True, capture_output=True)


def write(root, files):
    for rel, text in files.items():
        path = os.path.join(root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)


def make_repo(test, files, untracked=None):
    """Create a committed repo; `untracked` files are written but never added."""
    root = tempfile.mkdtemp(prefix="towncode-fixture-")
    test.addCleanup(shutil.rmtree, root)
    subprocess.run(["git", "init", "-q", "-b", "main", root], check=True, capture_output=True)
    write(root, files)
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "fixture")
    if untracked:
        write(root, untracked)
    return root


def commit(root, files, message="change", paths=None):
    write(root, files)
    git(root, "add", "--", *(paths or list(files)))
    git(root, "commit", "-q", "-m", message)


def worktree(main, path, branch, files=None):
    """Add a linked worktree on `branch`; optional `files` are written inside it."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    git(main, "worktree", "add", "-b", branch, path)
    if files:
        write(path, files)
    return path
