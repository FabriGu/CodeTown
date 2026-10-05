import unittest

import cake
import iso

WIDTHS = [0.35 + 0.05 * i for i in range(14)]


class TiersTest(unittest.TestCase):
    def test_biggest_function_at_the_bottom(self):
        stack = cake.tiers([("small", 5, 1), ("big", 120, 9), ("mid", 40, 3)], 2, 13)
        self.assertEqual([t.amber for t in stack], [True, False, False])
        self.assertEqual([t.z1 - t.z0 for t in stack], [6, 2, 2])

    def test_ties_break_by_complexity_then_name(self):
        stack = cake.tiers([("b", 10, 1), ("a", 10, 1), ("c", 10, 5)], 1, 7)
        self.assertEqual([t.z1 - t.z0 for t in stack], [4, 2, 2])

    def test_floors_touch_and_never_overhang(self):
        stack = cake.tiers([(f"f{i}", 3 + i * 7, i % 5) for i in range(12)], 3, 30)
        self.assertEqual(stack[0].z0, 0)
        for below, above in zip(stack, stack[1:]):
            self.assertEqual(above.z0, below.z1)
            self.assertLessEqual(above.half, below.half)

    def test_no_functions_is_one_full_width_tier(self):
        self.assertEqual(cake.tiers([], 2, 10), [cake.Tier(cake.half_width(2, 1.0), 0, 7, False)])
        self.assertEqual(cake.tiers([], 1, 0)[0].z1, cake.MIN_THICKNESS)

    def test_half_width_fits_the_lot_in_odd_steps(self):
        for size in range(1, 5):
            for w in WIDTHS + [1.0]:
                half = cake.half_width(size, w)
                self.assertEqual(half % 4, 2)
                self.assertLessEqual(half, max(2, size * iso.HALF_W))


class WindowsTest(unittest.TestCase):
    def test_windows_stay_inside_their_wall_and_floor(self):
        for size in range(1, 5):
            for w in WIDTHS + [1.0]:
                half = cake.half_width(size, w)
                walls = {(wall, col): t for wall, col, t in cake.wall_columns(half)}
                for height in range(2, 60):
                    seen = set()
                    for wall, pixels in cake.windows(half, 10, 10 + height):
                        self.assertEqual(len(pixels), 4)
                        for col, row in pixels:
                            t = walls[wall, col]
                            k = t // 2 - row
                            self.assertGreaterEqual(k, 10 + cake.WINDOW_BOTTOM)
                            self.assertLess(k, 10 + height - cake.WINDOW_TOP)
                            self.assertGreaterEqual(t // 2, cake.WINDOW_SIDE)
                            self.assertLess(t // 2, half // 2 - cake.WINDOW_SIDE)
                        self.assertFalse(seen & set(pixels))
                        seen |= set(pixels)

    def test_windows_are_centred_and_mirrored(self):
        for size in range(1, 5):
            for w in WIDTHS + [1.0]:
                half = cake.half_width(size, w)
                found = cake.windows(half, 0, 30)
                left = sorted(p for wall, px in found if wall == "left" for p in px)
                right = sorted((-1 - col, row) for wall, px in found if wall == "right"
                               for col, row in px)
                self.assertEqual(left, right)
                if left:
                    corner = min(col for col, _ in left) + half
                    middle = -1 - max(col for col, _ in left)
                    self.assertEqual(corner, middle)

    def test_no_window_when_it_doesnt_fit(self):
        self.assertEqual(cake.windows(2, 0, 30), [])
        self.assertEqual(cake.windows(30, 0, 4), [])


if __name__ == "__main__":
    unittest.main()
