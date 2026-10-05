import random
import unittest

import game
import world


def make_game(npcs=()):
    return game.Game(world.load(), rng=random.Random(7), npc_specs=list(npcs))


def npc_spec(pos, role="Tester"):
    return dict(role=role, pos=pos, hair=(0, 0, 0), skin=(0, 0, 0),
                shirt=(0, 0, 0), pants=(0, 0, 0), lines=["first", "second"])


class MovementTest(unittest.TestCase):
    def test_step_moves_player_one_tile_after_step_time(self):
        g = make_game()
        x, y = g.player.x, g.player.y
        g.press("right")
        g.update(game.STEP_TIME)
        self.assertEqual((g.player.x, g.player.y), (x + 1, y))
        self.assertFalse(g.player.moving)

    def test_position_interpolates_mid_step(self):
        g = make_game()
        x, y = g.player.x, g.player.y
        g.press("right")
        g.update(game.STEP_TIME / 2)
        self.assertAlmostEqual(g.player.pos()[0], x + 0.5)
        self.assertAlmostEqual(g.player.pos()[1], y)

    def test_blocked_step_turns_without_moving(self):
        g = make_game()
        g.player.place(11, 22)
        start = (11, 22)
        g.press("down")  # tree line at the bottom edge
        g.update(game.STEP_TIME)
        self.assertEqual((g.player.x, g.player.y), start)
        self.assertEqual(g.player.facing, (0, 1))

    def test_press_during_step_queues_next_step(self):
        g = make_game()
        x = g.player.x
        g.press("right")
        g.update(game.STEP_TIME / 2)
        g.press("right")
        g.update(game.STEP_TIME * 2)
        self.assertEqual(g.player.x, x + 2)

    def test_player_cannot_walk_through_villager(self):
        g = make_game()
        x, y = g.player.x, g.player.y
        g = make_game([npc_spec((x + 1, y))])
        g.npcs[0].pause = 999
        g.press("right")
        g.update(game.STEP_TIME)
        self.assertEqual(g.player.x, x)


class InteractionTest(unittest.TestCase):
    def test_reading_the_sign_you_face(self):
        g = make_game()
        g.player.place(13, 6)
        g.player.facing = (0, -1)
        g.interact()
        self.assertIn("NORTH ROAD", g.message)

    def test_talking_to_villager_cycles_lines(self):
        x, y = world.load().start
        g = make_game([npc_spec((x + 1, y), role="Tester")])
        g.player.facing = (1, 0)
        g.interact()
        first = g.message
        g.interact()
        self.assertEqual(first, "Tester: first")
        self.assertEqual(g.message, "Tester: second")

    def test_message_expires(self):
        g = make_game()
        g.player.place(13, 6)
        g.player.facing = (0, -1)
        g.interact()
        g.update(game.MESSAGE_TIME + 0.1)
        self.assertIsNone(g.message)

    def test_prompt_appears_next_to_something_interesting(self):
        g = make_game()
        self.assertIsNone(g.prompt())
        g.player.place(13, 6)
        self.assertIsNotNone(g.prompt())


class WanderTest(unittest.TestCase):
    def test_villagers_wander_within_home_radius_on_walkable_tiles(self):
        g = game.Game(world.load(), rng=random.Random(3))
        homes = [(n.home, n) for n in g.npcs]
        moved = set()
        for _ in range(2000):
            g.update(0.05)
            for home, n in homes:
                self.assertFalse(g.world.blocked(n.x, n.y))
                self.assertLessEqual(abs(n.x - home[0]) + abs(n.y - home[1]), game.WANDER_RADIUS)
                if (n.x, n.y) != home:
                    moved.add(n.role)
        self.assertGreaterEqual(len(moved), 3)


if __name__ == "__main__":
    unittest.main()
