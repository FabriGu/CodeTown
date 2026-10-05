import math
import unittest

import camera


class CameraTest(unittest.TestCase):
    def test_step_moves_toward_the_target(self):
        c = camera.Camera((0.0, 0.0))
        c.set_target(100.0, 50.0)
        moved = c.step(0.1)
        self.assertTrue(moved)
        self.assertGreater(c.focus[0], 0.0)
        self.assertLess(c.focus[0], 100.0)

    def test_step_reaches_the_target_over_many_frames(self):
        c = camera.Camera((0.0, 0.0))
        c.set_target(40.0, 20.0)
        for _ in range(200):
            c.step(1 / 24)
        self.assertAlmostEqual(c.focus[0], 40.0, places=1)
        self.assertAlmostEqual(c.focus[1], 20.0, places=1)
        self.assertFalse(c.step(1 / 24))

    def test_ease_constant_matches_the_spec(self):
        self.assertEqual(camera.EASE, 6.5)
        c = camera.Camera((0.0, 0.0))
        c.set_target(10.0, 0.0)
        c.step(1.0)
        expected = 10.0 * (1 - math.exp(-6.5))
        self.assertAlmostEqual(c.focus[0], expected, places=5)

    def test_jump_snaps_focus_and_target(self):
        c = camera.Camera((0.0, 0.0))
        c.set_target(100.0, 50.0)
        c.step(0.1)
        c.jump(40.0, 20.0)
        self.assertEqual(c.focus, [40.0, 20.0])
        self.assertEqual(c.target, [40.0, 20.0])
        self.assertFalse(c.gliding())

    def test_gliding_is_public(self):
        c = camera.Camera((0.0, 0.0))
        c.set_target(10.0, 0.0)
        self.assertTrue(c.gliding())
        c.jump(10.0, 0.0)
        self.assertFalse(c.gliding())
