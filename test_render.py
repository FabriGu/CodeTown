import random
import unittest

import game
import render
import sprites
import world


def make_game(npcs=()):
    return game.Game(world.load(), rng=random.Random(1), npc_specs=list(npcs))


def count(fb, color, box=None):
    x0, y0, x1, y1 = box or (0, 0, fb.w, fb.h)
    return sum(1 for y in range(y0, y1) for x in range(x0, x1) if fb.get(x, y) == color)


class SpriteTest(unittest.TestCase):
    def test_parse_skips_transparent_and_maps_palette(self):
        pixels = sprites.parse([".A", "B."], {"A": (1, 2, 3), "B": (4, 5, 6)})
        self.assertEqual(pixels, [(1, 0, (1, 2, 3)), (0, 1, (4, 5, 6))])

    def test_clawd_shows_two_eyes_from_the_front_and_none_from_behind(self):
        front = "".join(sprites.clawd_rows(facing=(0, 1), frame=0))
        back = "".join(sprites.clawd_rows(facing=(0, -1), frame=0))
        self.assertEqual(front.count("E"), 2)
        self.assertEqual(back.count("E"), 0)

    def test_clawd_walk_frames_lift_the_body(self):
        idle = sprites.clawd_rows(facing=(0, 1), frame=0)
        for frame in (1, 2):
            walk = sprites.clawd_rows(facing=(0, 1), frame=frame)
            self.assertEqual(len(walk), len(idle) + 1)
        self.assertNotEqual(sprites.clawd_rows((0, 1), 1), sprites.clawd_rows((0, 1), 2))


class FramebufferTest(unittest.TestCase):
    def test_out_of_bounds_writes_are_ignored(self):
        fb = render.Framebuffer(3, 2, (0, 0, 0))
        fb.set(-1, 0, (9, 9, 9))
        fb.set(3, 1, (9, 9, 9))
        fb.set(1, 1, (9, 9, 9))
        self.assertEqual(count(fb, (9, 9, 9)), 1)


class SceneTest(unittest.TestCase):
    def test_frame_has_requested_size(self):
        fb = render.render_scene(make_game(), 40, 22)
        self.assertEqual((fb.w, fb.h), (40, 22))
        self.assertEqual(len(fb.rows), 22)
        self.assertEqual({len(r) for r in fb.rows}, {40})

    def test_clawd_is_drawn_near_the_centre(self):
        w, h = 60, 40
        fb = render.render_scene(make_game(), w, h)
        box = (w // 2 - 8, h // 2 - 8, w // 2 + 8, int(h * 0.75))
        self.assertGreater(count(fb, sprites.CLAWD["O"], box), 10)

    def test_clawd_shows_through_buildings_as_a_ghost(self):
        g = make_game()
        g.player.place(3, 1)  # directly behind the Town Hall
        fb = render.render_scene(g, 60, 40)
        self.assertLess(count(fb, sprites.CLAWD["O"]), 5)
        self.assertGreater(count(fb, render.GHOST), 4)

    def test_pond_water_animates_over_time(self):
        g = make_game()
        g.player.place(16, 8)
        before = render.render_scene(g, 60, 40).rows
        g.time += 1.7
        after = render.render_scene(g, 60, 40).rows
        self.assertNotEqual(before, after)

    def test_tiny_and_large_viewports_render(self):
        g = make_game()
        render.render_scene(g, 1, 1)
        render.render_scene(g, 160, 90)


if __name__ == "__main__":
    unittest.main()
