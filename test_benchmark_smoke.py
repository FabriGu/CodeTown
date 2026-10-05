import importlib.util
import os
import unittest

from drawtown import _clawd_anchor


def _load_benchmark():
    path = os.path.join(os.path.dirname(__file__), "scripts", "benchmark_watch_frame.py")
    spec = importlib.util.spec_from_file_location("benchmark_watch_frame", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class BenchmarkSmokeTest(unittest.TestCase):
    def test_ten_clawds_on_screen(self):
        mod = _load_benchmark()
        v, w, cleanup, _paths = mod.build_scene()
        self.addCleanup(w.close)
        self.addCleanup(cleanup)
        self.assertEqual(len(v._crowd.clawds()), 10)
        for _ in range(2):
            v.tick(1 / 24, v.t + 1 / 24)
            fb = v.frame(120, 57)
            scene = v._last_street_scene
            self.assertIsNotNone(scene)
            for c in v._crowd.clawds():
                ax, ay = _clawd_anchor(scene, c)
                self.assertGreaterEqual(ax, 0, c.agent_id)
                self.assertLess(ax, fb.w, c.agent_id)
                self.assertGreaterEqual(ay, 0, c.agent_id)
                self.assertLess(ay, fb.h, c.agent_id)

    def test_build_scene_leaves_no_temp_dirs(self):
        mod = _load_benchmark()
        v, w, cleanup, paths = mod.build_scene()
        w.close()
        cleanup()
        for path in paths:
            self.assertFalse(os.path.exists(path), path)


if __name__ == "__main__":
    unittest.main()
