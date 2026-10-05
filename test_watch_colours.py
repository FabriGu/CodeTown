import os
import unittest

import watch
from test_watch import temp_survey


class WatchColoursTest(unittest.TestCase):
    def test_every_scarf_colour_is_far_from_reserved_colours(self):
        self.assertGreaterEqual(watch.min_palette_distance(), 80)

    def test_rgb_distance_is_euclidean(self):
        self.assertAlmostEqual(watch.rgb_distance((0, 0, 0), (3, 4, 0)), 5.0)

    def test_palette_colours_are_distinct_from_each_other(self):
        self.assertGreaterEqual(watch.min_palette_pairwise_distance(), 60)

    def test_team_keeps_colour_across_sessions(self):
        survey = temp_survey(self)
        teams, last_used = {}, {}
        idx = watch.assign_colour("world", teams, last_used, 1.0)
        watch.save_colours_if_changed(survey, teams, last_used, {})
        self.assertEqual(watch.load_colours(survey)[0]["world"], idx)
        self.assertTrue(os.path.isfile(os.path.join(survey, "watch.json")))

    def test_reserved_copies_match_mock_roles_when_available(self):
        try:
            import mock_roles
            import focus as focus_mod
        except ImportError:
            raise unittest.SkipTest("mock_roles not importable")
        self.assertEqual(watch.RESERVED["uses"], mock_roles.ROAD_COLORS[focus_mod.USES])
        self.assertEqual(watch.RESERVED["site"], mock_roles.SITE)
        self.assertEqual(watch.RESERVED["reviewer_grey"], mock_roles.GRAY)
