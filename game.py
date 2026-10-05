"""Game state: grid movement with tweening, wandering villagers, talking."""

import random

import world as world_mod

STEP_TIME = 0.16
NPC_STEP_TIME = 0.32
MESSAGE_TIME = 6.0
TALK_PAUSE = 4.0
WANDER_RADIUS = 3

# Screen-relative: up = up-right, right = down-right, down = down-left, left = up-left.
DIRECTIONS = {"up": (0, -1), "right": (1, 0), "down": (0, 1), "left": (-1, 0)}
NEIGHBOURS = list(DIRECTIONS.values())


class Actor:
    def __init__(self, x, y, step_time=STEP_TIME):
        self.step_time = step_time
        self.facing = (0, 1)
        self.steps = 0
        self.place(x, y)

    def place(self, x, y):
        self.x, self.y = x, y
        self.from_x, self.from_y = x, y
        self.t = 1.0

    @property
    def moving(self):
        return self.t < 1.0

    def pos(self):
        return (self.from_x + (self.x - self.from_x) * self.t,
                self.from_y + (self.y - self.from_y) * self.t)

    def tiles(self):
        if self.moving:
            return {(self.x, self.y), (self.from_x, self.from_y)}
        return {(self.x, self.y)}

    def start_step(self, dx, dy):
        self.from_x, self.from_y = self.x, self.y
        self.x += dx
        self.y += dy
        self.t = 0.0
        self.steps += 1

    def advance(self, dt):
        """Progress the current step; return time left over once it finishes."""
        if not self.moving:
            return dt
        remaining = (1.0 - self.t) * self.step_time
        if dt < remaining:
            self.t += dt / self.step_time
            return 0.0
        self.t = 1.0
        return dt - remaining

    def walk_frame(self):
        if not self.moving:
            return 0
        return 1 + ((self.t >= 0.5) ^ (self.steps % 2))


class Npc(Actor):
    def __init__(self, spec, rng):
        super().__init__(*spec["pos"], step_time=NPC_STEP_TIME)
        self.spec = spec
        self.role = spec["role"]
        self.lines = spec["lines"]
        self.line_index = 0
        self.home = spec["pos"]
        self.pause = rng.uniform(0.5, 3.0)

    def next_line(self):
        line = self.lines[self.line_index % len(self.lines)]
        self.line_index += 1
        return f"{self.role}: {line}"


class Game:
    def __init__(self, world, rng=None, npc_specs=None):
        self.world = world
        self.rng = rng or random.Random()
        self.time = 0.0
        self.player = Actor(*world.start)
        specs = world_mod.NPCS if npc_specs is None else npc_specs
        self.npcs = [Npc(s, self.rng) for s in specs]
        self.queued = None
        self.message = None
        self.message_timer = 0.0

    def actors(self):
        return [self.player] + self.npcs

    def occupied(self, x, y, exclude=None):
        return any((x, y) in a.tiles() for a in self.actors() if a is not exclude)

    def npc_at(self, tile):
        for n in self.npcs:
            if tile in n.tiles():
                return n
        return None

    def press(self, direction):
        self.queued = DIRECTIONS[direction]

    def say(self, text):
        self.message = text
        self.message_timer = MESSAGE_TIME

    def _try_step(self, actor, d):
        actor.facing = d
        nx, ny = actor.x + d[0], actor.y + d[1]
        if self.world.blocked(nx, ny) or self.occupied(nx, ny, exclude=actor):
            return False
        actor.start_step(*d)
        return True

    def _candidate_tiles(self):
        p = self.player
        fx, fy = p.facing
        facing = (p.x + fx, p.y + fy)
        return [facing] + [(p.x + dx, p.y + dy) for dx, dy in NEIGHBOURS
                           if (p.x + dx, p.y + dy) != facing]

    def _describe(self, tile):
        npc = self.npc_at(tile)
        if npc:
            return f"E: talk to the {npc.role}"
        if self.world.interaction_at(*tile):
            return "E: take a look"
        return None

    def prompt(self):
        if self.player.moving:
            return None
        for tile in self._candidate_tiles():
            text = self._describe(tile)
            if text:
                return text
        return None

    def interact(self):
        p = self.player
        for tile in self._candidate_tiles():
            npc = self.npc_at(tile)
            text = None
            if npc:
                npc.pause = TALK_PAUSE
                npc.facing = (p.x - tile[0], p.y - tile[1])
                text = npc.next_line()
            else:
                text = self.world.interaction_at(*tile)
            if text:
                p.facing = (tile[0] - p.x, tile[1] - p.y)
                self.say(text)
                return

    def update(self, dt):
        self.time += dt
        self._update_player(dt)
        for n in self.npcs:
            self._update_npc(n, dt)
        if self.message:
            self.message_timer -= dt
            if self.message_timer <= 0:
                self.message = None

    def _update_player(self, dt):
        p = self.player
        while True:
            if not p.moving and self.queued:
                d, self.queued = self.queued, None
                self._try_step(p, d)
            if not p.moving:
                return
            dt = p.advance(dt)
            if dt <= 0:
                return

    def _update_npc(self, n, dt):
        if n.moving:
            n.advance(dt)
            return
        n.pause -= dt
        if n.pause > 0:
            return
        n.pause = self.rng.uniform(1.0, 3.5)
        dx, dy = self.rng.choice(NEIGHBOURS)
        tx, ty = n.x + dx, n.y + dy
        if abs(tx - n.home[0]) + abs(ty - n.home[1]) <= WANDER_RADIUS:
            self._try_step(n, (dx, dy))
