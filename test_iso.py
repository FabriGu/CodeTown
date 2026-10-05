import unittest

import iso


class ToScreenTest(unittest.TestCase):
    def test_origin_projects_to_origin(self):
        self.assertEqual(iso.to_screen(0, 0), (0, 0))

    def test_plus_x_goes_down_right(self):
        self.assertEqual(iso.to_screen(1, 0), (iso.HALF_W, iso.HALF_H))

    def test_plus_y_goes_down_left(self):
        self.assertEqual(iso.to_screen(0, 1), (-iso.HALF_W, iso.HALF_H))

    def test_fractional_positions_interpolate(self):
        self.assertEqual(iso.to_screen(0.5, 0), (iso.HALF_W / 2, iso.HALF_H / 2))


class TileMaskTest(unittest.TestCase):
    def test_neighbouring_tiles_tessellate_without_gaps_or_overlaps(self):
        owner = {}
        for tx in range(-2, 3):
            for ty in range(-2, 3):
                sx, sy = iso.to_screen(tx, ty)
                for dx, dy in iso.TILE_MASK:
                    p = (sx + dx, sy + dy)
                    self.assertNotIn(p, owner, f"{p} claimed by {owner.get(p)} and {(tx, ty)}")
                    owner[p] = (tx, ty)
        # every pixel of the centre tile's bounding box is owned by some tile
        for dy in range(iso.TILE_H):
            for dx in range(-iso.HALF_W, iso.HALF_W):
                self.assertIn((dx, dy), owner)

    def test_column_bottom_is_lowest_mask_pixel_per_column(self):
        for dx, bottom in iso.COLUMN_BOTTOM.items():
            ys = [my for mx, my in iso.TILE_MASK if mx == dx]
            self.assertEqual(bottom, max(ys))


if __name__ == "__main__":
    unittest.main()
