import unittest

import lang_python
from langtest import edges, survey_files


class PythonAdapterTest(unittest.TestCase):
    def test_the_sample_town(self):
        model = survey_files(self, lang_python.SAMPLE)
        mods = model.modules
        self.assertEqual(edges(model), {("pkg/a.py", "pkg/b.py")})
        self.assertEqual(model.externals, {"requests": ["pkg/b.py"]})
        self.assertEqual(mods["pkg/a.py"].tested_by, ["tests/test_a.py"])
        self.assertTrue(mods["pkg/__init__.py"].is_package)
        self.assertEqual({m.lang for m in mods.values()}, {"python"})
        self.assertEqual({m.depth for m in mods.values()}, {"full"})
        self.assertNotIn("requirements.txt", mods)

    def test_relative_imports_keep_their_level(self):
        model = survey_files(self, {"pkg/__init__.py": "", "pkg/a.py": "from . import b\n",
                                    "pkg/b.py": "", "pkg/sub/__init__.py": "",
                                    "pkg/sub/c.py": "from ..a import x\n"})
        self.assertEqual(edges(model), {("pkg/a.py", "pkg/b.py"), ("pkg/sub/c.py", "pkg/a.py")})

    def test_functions_are_top_level_functions_and_class_methods(self):
        model = survey_files(self, {
            "a.py": "def f(x):\n    if x:\n        return 1\n\n\nclass C:\n    def m(self):\n"
                    "        def inner():\n            pass\n        return [y for y in x if y]\n",
            "bad.py": "def broken(:\n",
        })
        self.assertEqual(model.modules["a.py"].functions, [("f", 3, 2), ("m", 4, 3)])
        self.assertEqual(model.modules["bad.py"].functions, [])

    def test_python_shebang_scripts_without_an_extension_are_not_read(self):
        model = survey_files(self, {"bin/tool": "#!/usr/bin/env python3\nprint(1)\n"})
        self.assertNotIn("bin/tool", model.modules)


if __name__ == "__main__":
    unittest.main()
