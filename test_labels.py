import unittest

import problems
import term
from labels import LOUD_KINDS, place, selected_building, shorten
from test_townmap import build


class ShortenTest(unittest.TestCase):
    def test_short_paths_unchanged(self):
        self.assertEqual(shorten("core/base.py"), "core/base.py")

    def test_long_paths_shorten_from_the_left(self):
        path = "packages/deep/nested/module/file.py"
        self.assertTrue(shorten(path).startswith("…"))
        self.assertLessEqual(len(shorten(path)), 28)


class SelectedLabelTest(unittest.TestCase):
    def setUp(self):
        self.model, _, _, self.town = build()
        self.roof = (84, 108, 150)

    def test_fire_beats_name(self):
        b = self.town.buildings["core/broken.py"]
        rows = self.town.problems.get(b.module, ())
        reqs = selected_building(b, rows, self.roof)
        self.assertEqual(len(reqs), 1)
        self.assertIn("▲", reqs[0].text)
        self.assertIn("broken.py", reqs[0].text)

    def test_loud_problem_beats_name(self):
        b = self.town.buildings["core/tower.py"]
        rows = self.town.problems.get(b.module, ())
        reqs = selected_building(b, rows, self.roof)
        self.assertIn("◆", reqs[0].text)
        self.assertIn("tower", reqs[0].text)

    def test_name_label_has_two_parts_for_the_dot(self):
        b = self.town.buildings["core/base.py"]
        rows = self.town.problems.get(b.module, ())
        reqs = selected_building(b, rows, self.roof)
        self.assertEqual(len(reqs), 2)
        self.assertEqual(reqs[0].text, "●")
        self.assertIn("base.py", reqs[1].text)
        ovs = place(reqs, 40, 20)
        self.assertEqual(len(ovs), 2)
        self.assertEqual(ovs[0].text, "●")
        self.assertEqual(term.pixel_col(ovs[1].x), term.pixel_col(ovs[0].x) + 1)


class PlaceTest(unittest.TestCase):
    def test_centres_on_the_roof(self):
        from labels import LabelRequest, DARK_GREY, LIGHT
        r = LabelRequest("hello", 5.0, 5, LIGHT, DARK_GREY, priority=0)
        ovs = place([r], 40, 20)
        self.assertEqual(len(ovs), 1)
        self.assertEqual(ovs[0].y, 5)
        self.assertEqual(term.pixel_col(ovs[0].x), term.pixel_col(5.0) - len("hello") // 2)

    def test_moves_up_when_overlapping(self):
        from labels import LabelRequest, DARK_GREY, LIGHT
        first = LabelRequest("first", 5.0, 5, LIGHT, DARK_GREY, priority=0)
        second = LabelRequest("second", 5.0, 5, LIGHT, DARK_GREY, priority=1)
        taken = set()
        for ov in place([first], 40, 20, taken):
            for j in range(len(ov.text)):
                taken.add((term.pixel_col(ov.x) + j, ov.y))
        ovs = place([second], 40, 20, taken)
        self.assertEqual(ovs[0].y, 4)

    def test_drops_after_two_rows_up(self):
        from labels import LabelRequest, DARK_GREY, LIGHT
        centre = term.pixel_col(5.0)
        col = centre - len("blocked") // 2
        taken = ({(col + i, 5) for i in range(7)} | {(col + i, 4) for i in range(7)}
                 | {(col + i, 3) for i in range(7)})
        r = LabelRequest("blocked", 5.0, 5, LIGHT, DARK_GREY, priority=0)
        self.assertEqual(place([r], 40, 20, taken), [])

    def test_respects_taken_cells(self):
        from labels import LabelRequest, DARK_GREY, LIGHT
        centre = term.pixel_col(5.0)
        taken = {(centre, 5), (centre + 1, 5)}
        r = LabelRequest("x", 5.0, 5, LIGHT, DARK_GREY, priority=0)
        ovs = place([r], 40, 20, taken)
        self.assertEqual(ovs[0].y, 4)

    def test_clamps_inside_the_screen(self):
        from labels import LabelRequest, DARK_GREY, LIGHT
        r = LabelRequest("edge", 1.0, 5, LIGHT, DARK_GREY, priority=0)
        ovs = place([r], 8, 20)
        term_w = 8 * 2
        self.assertGreaterEqual(term.pixel_col(ovs[0].x), 0)
        self.assertLess(term.pixel_col(ovs[0].x) + len(ovs[0].text), term_w)
