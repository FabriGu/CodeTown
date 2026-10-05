"""Fingerprint a directory tree to prove that reading it changed nothing."""

import hashlib
import os
import stat


def _digest(path):
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            for block in iter(lambda: f.read(1 << 20), b""):
                h.update(block)
    except OSError:
        return None
    return h.hexdigest()


def fingerprint(root, hashable=None):
    """Map each path to its type, size, mtime and (if `hashable` allows) content hash."""
    prints = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        prints[os.path.relpath(dirpath, root) + "/"] = ("dir", os.lstat(dirpath).st_mtime_ns)
        for name in dirnames:
            path = os.path.join(dirpath, name)
            if os.path.islink(path):
                prints[os.path.relpath(path, root)] = ("link", os.readlink(path))
        for name in sorted(filenames):
            path = os.path.join(dirpath, name)
            st = os.lstat(path)
            key = os.path.relpath(path, root)
            if stat.S_ISLNK(st.st_mode):
                prints[key] = ("link", os.readlink(path), st.st_mtime_ns)
            elif stat.S_ISREG(st.st_mode):
                digest = _digest(path) if hashable is None or hashable(key) else None
                prints[key] = ("file", st.st_size, st.st_mtime_ns, digest)
            else:
                prints[key] = ("other", st.st_mtime_ns)
    return prints


def differences(before, after):
    found = {
        "added": sorted(after.keys() - before.keys()),
        "removed": sorted(before.keys() - after.keys()),
        "changed": sorted(k for k in before.keys() & after.keys() if before[k] != after[k]),
    }
    return {k: v for k, v in found.items() if v}
