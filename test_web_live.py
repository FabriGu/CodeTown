import os
import shutil
import subprocess
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))


@unittest.skipUnless(shutil.which("node"), "node is not installed")
class WebLiveTest(unittest.TestCase):
    def test_the_browser_live_logic(self):
        done = subprocess.run(["node", "--test", os.path.join(HERE, "web", "live.test.mjs"),
                               os.path.join(HERE, "web", "transit.test.mjs")],
                              capture_output=True, text=True, timeout=120)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)


if __name__ == "__main__":
    unittest.main()
