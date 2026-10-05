import re
import unittest

import render
import term

LIGHT, DARK, RED, BLUE = (230, 230, 230), (58, 58, 66), (255, 0, 0), (0, 0, 255)


def fb_of(*rows):
    fb = render.Framebuffer(len(rows[0]), len(rows))
    fb.rows = [list(r) for r in rows]
    return fb


class EncodeTest(unittest.TestCase):
    def test_runs_of_one_color_share_a_single_escape(self):
        out = term.encode_row([RED, RED], truecolor=True)
        self.assertEqual(out.count("\x1b[38;2;255;0;0"), 1)
        self.assertEqual(out.count(term.PIXEL), 2)

    def test_color_changes_emit_new_escape(self):
        out = term.encode_row([RED, BLUE], truecolor=True)
        self.assertIn("38;2;255;0;0", out)
        self.assertIn("38;2;0;0;255", out)

    def test_256_color_fallback(self):
        self.assertEqual(term.rgb_to_256((255, 0, 0)), 196)
        self.assertEqual(term.rgb_to_256((0, 0, 0)), 16)
        self.assertIn("38;5;196", term.encode_row([RED], truecolor=False))


class ScreenTest(unittest.TestCase):
    def test_first_frame_draws_every_row(self):
        s = term.Screen(truecolor=True)
        out = s.frame(fb_of([RED], [BLUE]), [])
        self.assertIn("\x1b[1;1H", out)
        self.assertIn("\x1b[2;1H", out)

    def test_unchanged_frame_moves_no_cursor(self):
        s = term.Screen(truecolor=True)
        s.frame(fb_of([RED], [BLUE]), ["hi"])
        out = s.frame(fb_of([RED], [BLUE]), ["hi"])
        self.assertNotIn(";1H", out)

    def test_only_changed_rows_are_redrawn(self):
        s = term.Screen(truecolor=True)
        s.frame(fb_of([RED], [BLUE]), [])
        out = s.frame(fb_of([RED], [RED]), [])
        self.assertNotIn("\x1b[1;1H", out)
        self.assertIn("\x1b[2;1H", out)

    def test_status_lines_render_below_the_picture(self):
        s = term.Screen(truecolor=True)
        out = s.frame(fb_of([RED], [BLUE]), ["hello"])
        self.assertIn("\x1b[3;1H", out)
        self.assertIn("hello", out)


class OverlayTest(unittest.TestCase):
    def test_pixel_col_whole_and_half(self):
        self.assertEqual(term.pixel_col(0), 0)
        self.assertEqual(term.pixel_col(5), 10)
        self.assertEqual(term.pixel_col(5.5), 11)

    def test_compose_row_places_text_over_pixels(self):
        row = [RED, RED]
        ov = term.Overlay(0, 0, "Hi", LIGHT, DARK)
        out = term.compose_row(row, [ov], truecolor=True)
        self.assertIn("Hi", out)
        self.assertIn("38;2;230;230;230", out)
        self.assertIn("48;2;58;58;66", out)

    def test_half_pixel_tail_fills_with_pixel_colour(self):
        row = [RED, BLUE]
        ov = term.Overlay(0, 0, "A", LIGHT, DARK)
        out = term.compose_row(row, [ov], truecolor=True)
        tail = f"{term.color_code(RED, True)}{term.PIXEL[0]}"
        pos = out.index("A") + 1
        self.assertEqual(out[pos:pos + len(tail)], tail)
        self.assertIn(f"{term.color_code(BLUE, True)}{term.PIXEL}", out)
        visible = lambda s: re.sub(r"\x1b\[[0-9;]*m", "", s)
        self.assertEqual(len(visible(out)), len(visible(term.encode_row(row, True))))

    def test_only_overlay_change_redraws_the_row(self):
        s = term.Screen(truecolor=True)
        fb = fb_of([RED])
        s.frame(fb, [], [term.Overlay(0, 0, "a", LIGHT, DARK)])
        out = s.frame(fb, [], [term.Overlay(0, 0, "b", LIGHT, DARK)])
        self.assertIn("\x1b[1;1H", out)
        self.assertIn("b", out)

    def test_frame_without_overlays_still_works(self):
        s = term.Screen(truecolor=True)
        out = s.frame(fb_of([RED], [BLUE]), ["hi"])
        self.assertIn("\x1b[1;1H", out)
        self.assertIn("\x1b[3;1H", out)
        self.assertIn("hi", out)


class KeysTest(unittest.TestCase):
    def test_arrows_and_wasd_map_to_directions(self):
        self.assertEqual(term.parse_keys("\x1b[A\x1b[Dwsad"),
                         ["up", "left", "up", "down", "left", "right"])

    def test_application_mode_arrows(self):
        self.assertEqual(term.parse_keys("\x1bOC\x1bOB"), ["right", "down"])

    def test_interact_and_quit(self):
        self.assertEqual(term.parse_keys("E \rqQ\x03"),
                         ["interact", "interact", "interact", "quit", "quit", "quit"])

    def test_unknown_input_is_ignored(self):
        self.assertEqual(term.parse_keys("zx\x1b[5~"), [])


if __name__ == "__main__":
    unittest.main()
