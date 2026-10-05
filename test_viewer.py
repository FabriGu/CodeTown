import unittest

import focus
import problems
import term
from drawtown import FLAMES, FOCUS_ROOF, ROAD_COLORS
from render import shade
from roads import Roads, USED_BY
from test_townmap import build
from viewer import DISTRICT, STREET, TOWN, FramePace, Viewer, parse_keys, run


def colours(fb):
    return {c for row in fb.rows for c in row}


class ViewerTest(unittest.TestCase):
    def setUp(self):
        self.model, self.rows, self.found, self.town = build()
        self.v = Viewer(self.town, Roads(self.town, self.model, self.found), self.model, self.found)

    def press(self, data):
        for key in parse_keys(data):
            self.v.press(key)

    def test_keys(self):
        self.assertEqual(parse_keys("+-=_n p\r\x1b[Bq"),
                         ["zoom in", "zoom out", "zoom in", "zoom out", "next", "inspect",
                          "previous", "inspect", "down", "quit"])

    def test_starts_on_the_worst_problem(self):
        self.assertEqual(self.found[0].kind, problems.FIRE)
        self.assertEqual(self.v.selected().module, self.found[0].module)

    def test_keys_move_the_cursor_and_stop_at_the_edge(self):
        x, y = self.v.cursor
        self.press("d")
        self.assertEqual(self.v.cursor, (x + 1, y))
        self.press("\x1b[A")
        self.assertEqual(self.v.cursor, (x + 1, y - 1))
        self.press("w" * 200)
        self.assertEqual(self.v.cursor, (x + 1, 0))

    def test_zoom_steps_between_street_district_and_town(self):
        self.press("+")
        self.assertEqual(self.v.zoom, STREET)
        self.press("-")
        self.assertEqual(self.v.zoom, DISTRICT)
        self.press("--")
        self.assertEqual(self.v.zoom, TOWN)
        self.press("=")
        self.assertEqual(self.v.zoom, DISTRICT)

    def test_every_zoom_level_fills_the_frame(self):
        for zoom in (STREET, DISTRICT, TOWN):
            self.v.zoom = zoom
            fb = self.v.frame(60, 30)
            self.assertEqual((fb.w, fb.h, len(fb.rows), len(fb.rows[0])), (60, 30, 30, 60), zoom)

    def test_n_and_p_walk_the_problems_worst_first_and_wrap(self):
        self.press("n")
        self.assertEqual(self.v.problem, 0)
        self.press("n")
        self.assertEqual(self.v.problem, 1)
        self.press("pp")
        last = len(self.found) - 1
        self.assertEqual(self.v.problem, last)
        self.assertEqual(self.v.cursor, self.town.centre(self.found[last].module))
        self.assertIn(f"problem {last + 1} of {last + 1}", self.v.status(200)[0])

    def test_moving_away_clears_the_problem_count(self):
        self.press("nd")
        self.assertIsNone(self.v.problem)

    def test_the_inspector_shows_the_facts_behind_a_building(self):
        self.v.cursor = self.town.centre("core/tower.py")
        self.press("\r")
        title, facts, reasons = self.v.status(300)
        self.assertIn("core/tower.py", title)
        for fact in ("2400 lines", "complexity 260", "1 floor", "imported by 1", "1 test"):
            self.assertIn(fact, facts)
        self.assertIn("tower: 2400 lines, complexity 260", reasons)

    def test_the_hint_shows_while_the_inspector_is_closed(self):
        hint = self.v.status(300)[2]
        self.assertIn("q quit", hint)
        self.assertIn("[street]", hint)

    def test_warehouses_plots_and_streets_describe_themselves(self):
        w = self.town.warehouses["flask"]
        self.v.cursor = (w.x, w.y)
        self.assertIn("warehouse: flask", self.v.status(200)[0])
        x, y, _ = self.town.plots["web/ui.js"]
        self.v.cursor = (x, y)
        self.assertIn("unsurveyed", self.v.status(200)[0])
        self.v.cursor = self.town.buildings["core/base.py"].front()
        self.assertIn("street", self.v.status(200)[0])

    def test_an_off_screen_fire_gets_an_arrow_at_the_edge(self):
        self.v.cursor = (0, self.town.height - 1)
        self.v.sync_camera()
        fb = self.v.frame(40, 24)
        edge = {fb.rows[y][x] for y in range(fb.h) for x in range(fb.w)
                if min(x, y, fb.w - 1 - x, fb.h - 1 - y) <= 4}
        self.assertTrue(set(FLAMES[:2]) & edge)

    def test_fire_can_be_seen_from_the_whole_town_view(self):
        self.v.zoom = TOWN
        fb = self.v.frame(60, 30)
        self.assertTrue(any(c in FLAMES for row in fb.rows for c in row))

    def test_a_selected_building_is_in_focus(self):
        self.v.cursor = self.town.centre("core/base.py")
        f = self.v.in_focus(self.v.selected())
        self.assertEqual((f.kind, f.distance["core/base.py"]), ("select", 0))
        fb = self.v.frame(120, 90)
        self.assertIn(shade(FOCUS_ROOF, 0.95), colours(fb))
        self.assertIn(ROAD_COLORS[USED_BY], colours(fb))

    def test_select_focuses_off_means_no_focus_on_a_building(self):
        self.v.cursor = self.town.centre("core/base.py")
        self.v.select_focuses = False
        self.assertIsNone(self.v.in_focus(self.v.selected()))

    def test_select_focuses_off_renders_undimmed_at_town_zoom(self):
        self.v.cursor = self.town.centre("core/base.py")
        self.v.select_focuses = False
        self.v.zoom = TOWN
        fb = self.v.frame(120, 90)
        self.assertNotIn(shade(FOCUS_ROOF, 0.95), colours(fb))
        scene = self.v._whole_town(self.v.selected())
        showing = lambda module: [(p, c) for p, ((m, key), _, c) in scene.owner.items()
                                  if m == module and key != "roof" and scene.fb.get(*p) == c]
        lonely = showing("app/lonely.py")
        self.assertTrue(lonely)
        self.assertTrue(all(scene.fb.get(*p) == c for p, c in lonely))
        self.assertFalse(any(scene.fb.get(*p) == shade(c, 0.38) for p, c in lonely))

    def test_nothing_is_in_focus_off_a_building(self):
        self.v.cursor = (0, self.town.height - 1)
        self.assertIsNone(self.v.in_focus(self.v.selected()))

    def test_a_session_stays_in_focus_wherever_the_cursor_is(self):
        changed = focus.changed(self.model, {"core/base.py"})
        v = Viewer(self.town, Roads(self.town, self.model, self.found), self.model, self.found,
                   session=changed)
        v.cursor = self.town.centre("app/lonely.py")
        self.assertIs(v.in_focus(v.selected()), changed)
        self.assertTrue(v.status(300)[0].startswith(
            " session: 1 changed, 2 use them directly, 0 through them"))
        _, facts, _ = v.describe(self.town.buildings["app/main.py"])
        self.assertIn("uses a changed module", facts)
        self.assertIn(shade(FOCUS_ROOF, 0.95), colours(v._whole_town(v.selected()).fb))

    def test_the_inspector_names_the_longest_function(self):
        _, facts, _ = self.v.describe(self.town.buildings["core/base.py"])
        self.assertIn("longest function load: 120 lines", facts)

    def test_a_site_describes_itself(self):
        title, facts, _ = self.v.describe(("site", "app/new.py"))
        self.assertEqual(title, "new file: app/new.py")
        self.assertIn("not committed yet", facts)


class FramePaceTest(unittest.TestCase):
    def test_still_is_twelve_fps(self):
        p = FramePace(clock=lambda: 0.0)
        self.assertEqual(p.after_frame(0.01, moving=False), 1 / 12 - 0.01)
        self.assertEqual(p.fps, 12)

    def test_moving_is_twenty_four_fps(self):
        p = FramePace(clock=lambda: 0.0)
        self.assertEqual(p.after_frame(0.01, moving=True), 1 / 24 - 0.01)
        self.assertEqual(p.fps, 24)

    def test_slow_frame_drops_to_twelve_until_movement_ends(self):
        p = FramePace(clock=lambda: 0.0)
        p.after_frame(0.04, moving=True)
        self.assertEqual(p.fps, 12)
        self.assertEqual(p.after_frame(0.01, moving=True), 1 / 12 - 0.01)
        p.after_frame(0.01, moving=False)
        self.assertEqual(p.fps, 12)


class CameraViewerTest(unittest.TestCase):
    def setUp(self):
        self.model, self.rows, self.found, self.town = build()
        self.v = Viewer(self.town, Roads(self.town, self.model, self.found), self.model, self.found)

    def test_camera_glides_after_n(self):
        for key in parse_keys("nn"):
            self.v.press(key)
        t0 = self.v.camera.focus[0]
        self.v.camera.step(1 / 24)
        self.assertNotEqual(self.v.camera.focus[0], t0)
        self.assertTrue(self.v.moving())

    def test_sync_camera_jumps_to_the_cursor(self):
        self.v.cursor = (0, self.town.height - 1)
        self.v.sync_camera()
        self.assertFalse(self.v.moving())
        tx, ty = self.v._target_for_cursor()
        self.assertEqual(self.v.camera.focus, [tx, ty])

    def test_street_zoom_selected_building_gets_an_overlay(self):
        self.v.zoom = STREET
        b = self.v.selected()
        self.v.cursor = self.town.centre(b.module)
        self.v.sync_camera()
        self.v.frame(60, 30)
        ovs = self.v.overlays(60, 30)
        self.assertTrue(ovs)
        joined = "".join(o.text for o in ovs)
        self.assertIn("broken", joined)


class RunLoopTest(unittest.TestCase):
    def test_run_writes_frames_and_picks_pace_with_injected_clock(self):
        tick = [0.0]

        def clock():
            return tick[0]

        class FakeTerm:
            last = None

            def __init__(self):
                self.writes = []
                self.timeouts = []
                FakeTerm.last = self

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                pass

            def size(self):
                return 80, 24

            def read(self, timeout):
                self.timeouts.append(timeout)
                tick[0] += timeout
                if tick[0] > 0.05:
                    return "q"
                return ""

            def write(self, s):
                self.writes.append(s)

        model, rows, found, town = build()
        v = Viewer(town, Roads(town, model, found), model, found)
        import viewer as viewer_mod
        old_term = viewer_mod.term.Terminal
        viewer_mod.term.Terminal = FakeTerm
        try:
            run(v, True, clock=clock)
        finally:
            viewer_mod.term.Terminal = old_term
        fake = FakeTerm.last
        self.assertGreaterEqual(len(fake.writes), 2)
        self.assertTrue(any(term.SYNC_BEGIN in w for w in fake.writes))
        self.assertTrue(fake.timeouts)
        self.assertAlmostEqual(fake.timeouts[1], 1 / 12, places=2)
