import unittest
from unittest import mock

import focus
import problems
import roads as R
from roads import USED_BY, USES
from drawtown import (AMBER, FLAMES, FOCUS_ROOF, GLASS, LIT, OUTLINE, ROAD_COLORS, ROOFS, SEA,
                      SELECT, SITE, WEED, TownScene, roof_index, shrink, window_kind)
from plat import Plat
from render import Framebuffer, shade
from roads import Roads
from test_townmap import build
from townmap import TownMap


def colours(fb):
    return {c for row in fb.rows for c in row}


class DrawTownTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.model, cls.rows, cls.found, cls.town = build()
        cls.roads = Roads(cls.town, cls.model, cls.found)
        cls.plain = TownScene.whole(cls.town, visible=cls.roads.visible()).render()

    def test_the_whole_town_fits_inside_its_frame(self):
        fb = self.plain
        drawn = [y for y in range(fb.h) if any(c != SEA for c in fb.rows[y])]
        self.assertGreater(drawn[0], 0)
        self.assertLess(drawn[-1], fb.h - 1)
        self.assertTrue(all(fb.rows[y][0] == SEA and fb.rows[y][-1] == SEA for y in range(fb.h)))

    def test_fire_burns_only_where_a_module_will_not_parse(self):
        self.assertTrue({FLAMES[0], FLAMES[1]} <= colours(self.plain))
        self.model.modules["core/broken.py"].parse_error = None
        try:
            found = problems.find(self.model, self.rows)
            calm = TownMap(self.model, Plat().update(self.model, self.rows), self.rows, found)
            fb = TownScene.whole(calm).render()
        finally:
            self.model.modules["core/broken.py"].parse_error = "line 3: invalid syntax"
        self.assertFalse({FLAMES[0], FLAMES[1]} & colours(fb))

    def test_unsurveyed_plots_get_a_gray_outline(self):
        self.assertIn(OUTLINE, colours(self.plain))

    def test_problem_roads_always_show_and_plain_roads_wait_for_selection(self):
        self.assertIn(ROAD_COLORS[R.CYCLE], colours(self.plain))
        self.assertIn(ROAD_COLORS[R.BACKWARDS], colours(self.plain))
        self.assertNotIn(ROAD_COLORS[R.ROAD], colours(self.plain))
        self.assertNotIn(SELECT, colours(self.plain))
        b = self.town.buildings["app/main.py"]
        chosen = TownScene.whole(self.town, selected=b, visible=self.roads.visible(b)).render()
        self.assertIn(ROAD_COLORS[R.ROAD], colours(chosen))
        self.assertIn(SELECT, colours(chosen))

    def test_loud_roads_and_the_selection_show_through_the_tower_in_front(self):
        loop_a = self.town.buildings["core/loop_a.py"]
        scene = TownScene.whole(self.town, selected=loop_a, visible=self.roads.visible(loop_a))
        fb = scene.render()
        ghost = scene.ghost.items()
        covered = {c for (x, y), c in ghost if (x + y) % 2 and fb.get(x, y) != c}
        self.assertTrue({SELECT, ROAD_COLORS[R.CYCLE]} <= covered)
        self.assertTrue(all(fb.get(x, y) == c for (x, y), c in ghost if (x + y) % 2 == 0))

    def test_drawing_is_deterministic(self):
        again = TownScene.whole(self.town, visible=self.roads.visible()).render()
        self.assertEqual(again.rows, self.plain.rows)

    def test_render_is_idempotent(self):
        scene = TownScene.whole(self.town, visible=self.roads.visible())
        first = scene.render().rows
        second = scene.render().rows
        self.assertEqual(first, second)

    def test_a_street_view_is_the_size_asked_for(self):
        fb = TownScene.around(self.town, 50, 30, self.town.centre("core/base.py")).render()
        self.assertEqual((fb.w, fb.h, len(fb.rows), len(fb.rows[0])), (50, 30, 30, 50))

    def test_shrink_averages_each_block(self):
        fb = Framebuffer(4, 2, (0, 0, 0))
        fb.rows[0][0] = (40, 80, 120)
        small = shrink(fb, 2)
        self.assertEqual((small.w, small.h), (2, 1))
        self.assertEqual(small.rows[0], [(10, 20, 30), (0, 0, 0)])

    def test_a_long_function_is_an_amber_floor(self):
        self.assertIn(shade(AMBER, 0.95), colours(self.plain))

    def test_windows_are_whole_or_not_drawn_at_all(self):
        scene = TownScene.whole(self.town)
        fb = scene.render()
        whole = 0
        for key, face, pixels, glass in scene.planned:
            pane = glass if face == "left" else shade(glass, 0.82)
            lit = [fb.get(*p) == pane for p in pixels]
            self.assertIn(sum(lit), (0, len(lit)), key)
            whole += all(lit)
        self.assertGreater(whole, 0)

    def test_tested_code_has_lit_windows_and_abandoned_code_grows_weeds(self):
        self.assertIn(LIT, colours(self.plain))
        self.assertIn(WEED, colours(self.plain))

    def test_each_building_is_drawn_once(self):
        scene = TownScene.whole(self.town)
        with mock.patch.object(scene, "draw_cake", wraps=scene.draw_cake) as draw:
            scene.render()
        self.assertEqual(sorted(c.args[0].module for c in draw.call_args_list),
                         sorted(self.town.buildings))

    def test_focus_roads_are_blue_and_pink(self):
        b = self.town.buildings["core/base.py"]
        f = focus.select(self.model, "core/base.py")
        fb = TownScene.whole(self.town, selected=b, visible=self.roads.visible(b, f)).render()
        self.assertIn(ROAD_COLORS[USED_BY], colours(fb))
        main = self.town.buildings["app/main.py"]
        f = focus.select(self.model, "app/main.py")
        fb = TownScene.whole(self.town, selected=main, visible=self.roads.visible(main, f)).render()
        self.assertIn(ROAD_COLORS[USES], colours(fb))

    def test_selection_rim_stays_bright_when_dimmed(self):
        b = self.town.buildings["app/lonely.py"]
        fb = TownScene.whole(self.town, selected=b, dim=lambda m: 0.38,
                             visible=self.roads.visible(b)).render()
        self.assertIn(SELECT, colours(fb))
        self.assertNotIn(shade(SELECT, 0.38), colours(fb))

    def test_a_focus_dims_the_rest_and_whitens_its_roof(self):
        plain = TownScene.whole(self.town)
        plain.render()
        level = {"app/main.py": 1.0, "core/base.py": 0.72}
        scene = TownScene.whole(self.town, dim=lambda m: level.get(m, 0.38),
                                focused={"app/main.py"})
        fb = scene.render()
        self.assertIn(shade(FOCUS_ROOF, 0.95), colours(fb))
        self.assertNotIn(shade(FOCUS_ROOF, 0.95), colours(plain.fb))
        showing = lambda module: [(p, c) for p, ((m, key), _, c) in plain.owner.items()
                                  if m == module and key != "roof" and plain.fb.get(*p) == c]
        self.assertTrue(showing("app/lonely.py"))
        self.assertTrue(all(fb.get(*p) == shade(c, 0.38) for p, c in showing("app/lonely.py")))
        self.assertTrue(all(fb.get(*p) == shade(c, 0.72) for p, c in showing("core/base.py")))
        self.assertTrue(all(fb.get(*p) == c for p, c in showing("app/main.py")))

    def test_new_files_are_orange_sites_that_never_dim(self):
        town = TownMap(self.model, Plat().update(self.model, self.rows), self.rows, self.found,
                       sites=["app/new.py"])
        fb = TownScene.whole(town, dim=lambda m: 0.38).render()
        self.assertIn(shade(SITE, 0.95), colours(fb))

    def test_many_orange_sites_stay_visible_when_dimmed(self):
        paths = [f"new/f{i:03}.py" for i in range(100)]
        town = TownMap(self.model, Plat().update(self.model, self.rows), self.rows, self.found,
                       sites=paths)
        scene = TownScene.whole(town, dim=lambda m: 0.38)
        fb = scene.render()
        for path in paths:
            showing = [(x, y) for (x, y), (key, face, colour) in scene.owner.items()
                       if key == (path, 0) and face == "left" and fb.get(x, y) == colour]
            self.assertTrue(showing, path)


class WindowAndRoofRulesTest(unittest.TestCase):
    def setUp(self):
        self.model, self.rows, self.found, self.town = build()
        self.scene = TownScene(self.town, 40, 30, 0, 0)

    def test_window_kind_names_the_glass_each_building_gets(self):
        seen = set()
        for b in self.town.buildings.values():
            kind = window_kind(b)
            seen.add(kind)
            self.assertEqual(self.scene.glass(b), GLASS[kind], b.module)
        self.assertEqual(seen, {"board", "door", "lit", "dark"})

    def test_roof_index_gives_each_district_the_roof_the_scene_paints(self):
        index = roof_index(self.town)
        self.assertEqual({name: ROOFS[i] for name, i in index.items()}, self.scene.roofs)
        self.assertEqual(set(index),
                         set(self.town.boxes) | {b.district for b in self.town.buildings.values()})
