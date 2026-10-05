import unittest

import crowd
import drawtown
import roads
import watch
import watch_sites
from test_townmap import build as build_town


def _clawd(*, agent_id, role, team=None, colour=0, tile=(0, 0), follow=None):
    return crowd.CrowdClawd(
        agent_id=agent_id,
        role=role,
        team=team,
        colour=colour,
        worktree=None,
        tile=tile,
        facing=(0, 1),
        pose="idle",
        walk_t=1.0,
        walk_frame=0,
        path=(),
        path_i=0,
        follow=follow,
        flag_building=None,
        hop_y=0.0,
        hop_i=0,
        hop_phase=0.0,
        idle_phase=0.0,
        last_event=0.0,
        hammer_until=0.0,
        peer_until=0.0,
        tour=(),
        tour_i=0,
        tour_until=0.0,
        at_hall=False,
        leaving=False,
    )


def _layer(tmap, clawds=(), scaffolded=None, sites=None, flags=None, drops=None,
           team_colours=None):
    return drawtown.WatchLayer(
        scaffolded=scaffolded or {},
        team_colours=team_colours or {"world": 0, "render": 1},
        sites=sites or {},
        flags=flags or {},
        drops=drops or {},
        clawds=list(clawds),
        town_hall=crowd.town_hall_tile(tmap),
    )


class WatchDrawTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.model, cls.rows, cls.found, cls.tmap = build_town()
        cls.roads = roads.Roads(cls.tmap, cls.model, cls.found)

    def _scene(self, **kw):
        return drawtown.TownScene.whole(self.tmap, visible=self.roads.visible(), **kw)

    def test_drop_offset_is_48_at_zero_and_zero_at_042(self):
        self.assertAlmostEqual(drawtown.drop_offset(0.0), 48.0)
        self.assertAlmostEqual(drawtown.drop_offset(0.42), 0.0, places=1)
        self.assertAlmostEqual(drawtown.drop_offset(1.0), 0.0)

    def test_scaffold_front_wall_uses_team_colour_shades(self):
        scene = self._scene()
        mod_a, mod_b = "app/main.py", "app/helper.py"
        layer = _layer(self.tmap, scaffolded={mod_a: "world", mod_b: "render"})
        scene.set_watch(layer, "street")
        fb = scene.render()
        world = watch.PALETTE[0]
        render = watch.PALETTE[1]
        for mod, team_colour in ((mod_a, world), (mod_b, render)):
            b = self.tmap.buildings[mod]
            pixels = drawtown.scaffold_front_pixels(scene, b)
            self.assertGreater(len(pixels), 8)
            painted = [fb.get(x, y) for x, y in pixels]
            self.assertTrue(all(c in {drawtown.scaffold_shade(team_colour, i, len(pixels))
                                      for i in range(len(pixels))} for c in painted))
            self.assertGreater(sum(c != drawtown.WALLS[0] for c in painted), len(pixels) // 2)

    def test_three_clawds_scarf_grey_glasses_and_hat_colours(self):
        scene = self._scene()
        impl = _clawd(agent_id="w/task-1", role="implementer", team="world", tile=(10, 10), follow=1)
        rev = _clawd(agent_id="w/rev", role="reviewer", team="world", tile=(13, 10), follow=2)
        orch = _clawd(agent_id="orch", role="orchestrator", team=None, tile=(16, 10), follow=None)
        layer = _layer(self.tmap, clawds=[impl, rev, orch])
        scene.set_watch(layer, "street")
        fb = scene.render()
        for x, y in drawtown.scarf_pixel_positions(scene, impl, layer.team_colours):
            self.assertEqual(fb.get(x, y), watch.PALETTE[0])
        for x, y in drawtown.scarf_pixel_positions(scene, rev, layer.team_colours):
            self.assertEqual(fb.get(x, y), watch.RESERVED["reviewer_grey"])
        for x, y in drawtown.glasses_pixel_positions(scene, rev):
            self.assertEqual(fb.get(x, y), drawtown.GLASSES)
        for x, y in drawtown.hat_pixel_positions(scene, orch):
            self.assertEqual(fb.get(x, y), drawtown.HAT)

    def test_flag_uses_worktree_team_not_worktree_name(self):
        scene = self._scene()
        mod = "app/main.py"
        layer = _layer(self.tmap, flags={"w2-render": (mod, "render")})
        scene.set_watch(layer, "street")
        fb = scene.render()
        b = self.tmap.buildings[mod]
        expected = watch.PALETTE[1]
        for x, y in drawtown.flag_pixel_positions(scene, b):
            self.assertEqual(fb.get(x, y), expected)

    def test_site_orange_block_with_team_accent(self):
        scene = self._scene()
        lots = watch_sites.layout_sites(self.tmap, ["app/new_a.py", "lib/new_b.py"])
        sites = {
            "app/new_a.py": (*lots["app/new_a.py"], "world"),
            "lib/new_b.py": (*lots["lib/new_b.py"], "render"),
        }
        layer = _layer(self.tmap, sites=sites)
        scene.set_watch(layer, "street")
        fb = scene.render()
        for path, team in (("app/new_a.py", "world"), ("lib/new_b.py", "render")):
            tx, ty, size, _ = sites[path]
            ax, ay = drawtown.site_accent_pixel(scene, tx, ty, size)
            self.assertEqual(fb.get(ax, ay), watch.PALETTE[layer.team_colours[team]])
            wx, wy, wall_colour = drawtown.site_wall_pixel(scene, tx, ty, size)
            self.assertEqual(fb.get(wx, wy), wall_colour)

    def test_lectern_prop_and_no_trees_on_hall_tiles(self):
        scene = self._scene()
        hall = crowd.town_hall_tile(self.tmap)
        layer = _layer(self.tmap)
        scene.set_watch(layer, "street")
        fb = scene.render()
        for x, y in drawtown.lectern_pixel_positions(scene, hall):
            self.assertNotIn(fb.get(x, y), drawtown.PINE if hasattr(drawtown, "PINE") else ())
        self.assertEqual(fb.get(*drawtown.lectern_pixel_positions(scene, hall)[5]), drawtown.LECTERN)
        hall_px = drawtown.hall_tile_pixels(scene, hall, self.tmap)
        tree_cols = {drawtown.TRUNK, drawtown.TRUNK_DARK} if hasattr(drawtown, "TRUNK") else set()
        import sprites
        tree_cols = {sprites.TRUNK, sprites.TRUNK_DARK, *sprites.PINE, *sprites.LEAF}
        for x, y in hall_px:
            self.assertNotIn(fb.get(x, y), tree_cols)

    def test_clawd_behind_building_is_partly_hidden(self):
        scene = self._scene()
        b = self.tmap.buildings["core/tower.py"]
        front = b.front()
        behind = _clawd(agent_id="behind", role="implementer", team="world", tile=(front[0], front[1] - 1))
        layer = _layer(self.tmap, clawds=[behind])
        scene.set_watch(layer, "street")
        fb = scene.render()
        visible_scarf = sum(
            1 for x, y in drawtown.scarf_pixel_positions(scene, behind, layer.team_colours)
            if fb.get(x, y) == watch.PALETTE[0]
        )
        scarf_count = len(list(drawtown.scarf_pixel_positions(scene, behind, layer.team_colours)))
        self.assertGreater(visible_scarf, 0)
        self.assertLess(visible_scarf, scarf_count)

    def test_tree_in_front_hides_clawd_scarf(self):
        scene = self._scene()
        tree_tile = (15, 13)
        self.assertIn(tree_tile, self.tmap.trees)
        clawd = _clawd(agent_id="w/t", role="implementer", team="world", tile=(12, 10), follow=1)
        layer = _layer(self.tmap, clawds=[clawd])
        scene.set_watch(layer, "street")
        fb = scene.render()
        covered = sum(
            1 for x, y in drawtown.scarf_pixel_positions(scene, clawd, layer.team_colours)
            if fb.get(x, y) != watch.PALETTE[0]
        )
        self.assertGreater(covered, 0)

    def test_clawd_in_front_hides_tree_pixels(self):
        scene = self._scene()
        tree_tile = (15, 13)
        self.assertIn(tree_tile, self.tmap.trees)
        clawd = _clawd(agent_id="w/t", role="implementer", team="world", tile=tree_tile, follow=1)
        layer = _layer(self.tmap, clawds=[clawd])
        scene.set_watch(layer, "street")
        fb = scene.render()
        import sprites
        tree_cols = set(sprites.PINE + sprites.LEAF + [sprites.TRUNK, sprites.TRUNK_DARK])
        ax, ay = drawtown._clawd_anchor(scene, clawd)
        rows = sprites.clawd_rows(clawd.facing, clawd.walk_frame)
        pal = drawtown.clawd_palette(clawd, layer.team_colours)
        y0 = ay - len(rows) + 1
        x0 = ax - 4
        clawd_px = {(x0 + x, y0 + y) for x, y, c in sprites.parse(rows, pal)}
        overlap = set(drawtown.tree_sprite_pixels(scene, *tree_tile)) & clawd_px
        self.assertTrue(overlap)
        wins = [p for p in overlap if fb.get(*p) not in tree_cols]
        self.assertTrue(wins)
        clawd_cols = set(pal.values())
        for x, y in wins:
            self.assertIn(fb.get(x, y), clawd_cols)

    def test_merge_drop_offsets_building_then_rests(self):
        mod = "app/main.py"
        b = self.tmap.buildings[mod]
        mid_t = 0.21
        off = int(drawtown.drop_offset(mid_t))
        self.assertGreater(off, 0)
        scene_drop = self._scene(t=mid_t)
        layer = _layer(self.tmap, drops={mod: 0.0})
        scene_drop.set_watch(layer, "street")
        fb_drop = scene_drop.render()
        scene_rest = self._scene(t=0.5)
        scene_rest.set_watch(_layer(self.tmap), "street")
        fb_rest = scene_rest.render()
        rx, ry = scene_rest.centre_px(b)
        ry -= drawtown.height_px(b)
        self.assertEqual(fb_drop.get(rx, ry - off), fb_rest.get(rx, ry))
        self.assertNotEqual(fb_drop.get(rx, ry), fb_rest.get(rx, ry))

    def test_town_zoom_markers_are_three_pixels(self):
        scene = self._scene()
        c = _clawd(agent_id="w/t", role="implementer", team="world", tile=(5, 5), follow=1)
        layer = _layer(self.tmap, clawds=[c])
        scene.set_watch(layer, "town")
        fb = scene.render()
        px, py = drawtown.clawd_marker_px(scene, c)
        marker = {(px + dx, py + dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1)}
        self.assertEqual(len(marker), 9)
        for x, y in marker:
            if 0 <= x < fb.w and 0 <= y < fb.h:
                self.assertEqual(fb.get(x, y), watch.PALETTE[0])

    def test_render_without_watch_is_unchanged(self):
        scene = self._scene()
        fb_before = scene.render()
        scene2 = self._scene()
        fb_after = scene2.render()
        self.assertEqual(fb_before.rows, fb_after.rows)


if __name__ == "__main__":
    unittest.main()
