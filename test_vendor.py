import hashlib
import os
import re
import unittest

VENDOR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web", "vendor")
FILES = ["LICENSE", "OrbitControls.js", "three.core.js", "three.module.js"]
# Statements only: OrbitControls.js mentions an import path in a doc comment too.
SOURCES = re.compile(r"^(?:import|export)\b[^;]*?\bfrom '([^']+)'", re.M)


def read(name):
    with open(os.path.join(VENDOR, name), encoding="utf-8") as f:
        return f.read()


def digest(name):
    with open(os.path.join(VENDOR, name), "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def pinned():
    first, *rest = read("VERSION").splitlines()
    pairs = (line.split(maxsplit=1) for line in rest if line.strip())
    return first, {name: sha for sha, name in pairs}


class VendoredThreeTest(unittest.TestCase):
    def test_version_names_one_three_release_from_npm(self):
        first, _ = pinned()
        self.assertRegex(first, r"^three (\d+\.\d+\.\d+) from "
                                r"https://registry\.npmjs\.org/three/-/three-\1\.tgz$")

    def test_every_file_matches_its_pinned_sha256(self):
        _, sums = pinned()
        self.assertEqual(sorted(sums), FILES)
        for name in FILES:
            self.assertEqual(digest(name), sums[name], name)

    def test_the_module_imports_only_the_vendored_core(self):
        self.assertEqual(set(SOURCES.findall(read("three.module.js"))), {"./three.core.js"})

    def test_the_core_imports_nothing(self):
        self.assertEqual(SOURCES.findall(read("three.core.js")), [])

    def test_orbit_controls_imports_only_three(self):
        self.assertEqual(set(SOURCES.findall(read("OrbitControls.js"))), {"three"})

    def test_three_is_mit_licensed(self):
        self.assertTrue(read("LICENSE").startswith("The MIT License"))


if __name__ == "__main__":
    unittest.main()
