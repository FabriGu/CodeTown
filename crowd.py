"""Clawd crowd simulation for towncode watch (pure, no I/O, no drawing)."""

from __future__ import annotations

from dataclasses import dataclass

import game
import iso
import roads as R
import watch
import watch_sites
from events import Agent, Event
from townmap import Building, TownMap

IDLE_AFTER = 20.0
HAMMER_TIME = 0.5
PEER_TIME = 3.0
TOUR_STAY = 4.0
HOP_HEIGHTS = (15, 8, 4)
HOP_TIME = 0.15
MIN_STAY = 4.0

EVENT_PRIORITY = {
    "edit": 0, "create": 0, "delete": 0, "commit": 0, "merge": 0,
    "finish": 1,
    "read": 2, "start": 2, "review_start": 2,
}


def town_hall_tile(tmap: TownMap) -> tuple[int, int]:
    if tmap.hall:
        return tmap.hall
    front_y = max(y for y in range(tmap.height)
                  if any(tmap.kind(x, y) == "avenue" and tmap.walkable(x, y)
                         for x in range(tmap.width)))
    cx = tmap.width // 2
    cands = [(x, front_y) for x in range(tmap.width) if tmap.walkable(x, front_y)]
    return min(cands, key=lambda t: (abs(t[0] - cx), t[1], t[0]))


def _manhattan_ring(ox, oy, dist, width, height):
    tiles = []
    for x in range(max(0, ox - dist), min(width - 1, ox + dist) + 1):
        dy = dist - abs(x - ox)
        ys = (oy - dy, oy + dy) if dy else (oy,)
        for y in ys:
            if 0 <= y < height:
                tiles.append((x, y))
    return sorted(set(tiles), key=lambda t: (t[1], t[0]))


def _pick_standing(tmap: TownMap, origin: tuple[int, int], seed: tuple[int, int],
                   occupied: set[tuple[int, int]]) -> tuple[int, int]:
    ox, oy = origin
    first = None
    for dist in range(tmap.width + tmap.height + 1):
        for tile in _manhattan_ring(ox, oy, dist, tmap.width, tmap.height):
            if tile != seed and not tmap.walkable(*tile):
                continue
            if first is None:
                first = tile
            if tile not in occupied:
                return tile
    return first if first is not None else seed


def hall_standing_spot(tmap: TownMap, hall: tuple[int, int],
                       occupied: set[tuple[int, int]]) -> tuple[int, int]:
    return _pick_standing(tmap, hall, hall, occupied)


def standing_spot(tmap: TownMap, building: Building,
                  occupied: set[tuple[int, int]]) -> tuple[int, int]:
    door = building.door()
    return _pick_standing(tmap, door, building.front(), occupied)


@dataclass
class CrowdClawd:
    agent_id: str
    role: str
    team: str | None
    colour: int
    worktree: str | None
    tile: tuple[int, int]
    facing: tuple[int, int] = (0, 1)
    pose: str = "idle"
    walk_t: float = 1.0
    walk_frame: int = 0
    path: tuple[tuple[int, int], ...] = ()
    path_i: int = 0
    follow: int | None = None
    flag_building: str | None = None
    hop_y: float = 0.0
    hop_i: int = 0
    hop_phase: float = 0.0
    idle_phase: float = 0.0
    last_event: float = 0.0
    hammer_until: float = 0.0
    peer_until: float = 0.0
    tour: tuple[str, ...] = ()
    tour_i: int = 0
    tour_until: float = 0.0
    at_hall: bool = False
    leaving: bool = False
    goal_module: str | None = None
    goal_kind: str | None = None
    reserved_tile: tuple[int, int] | None = None


STANDING_GOALS = frozenset({"module", "nearest", "tour", "read", "hall"})


class Crowd:
    def __init__(self, tmap, roads, model, tracked, town_hall, clock):
        self.tmap = tmap
        self.roads = roads
        self.model = model
        self.tracked = tracked
        self.town_hall = town_hall
        self.clock = clock
        self._clawds: dict[str, CrowdClawd] = {}
        self._departed: set[str] = set()
        self._provisional: dict[str, str] = {}
        self._slots: dict[int, str] = {}
        self._free: list[int] = []
        self._standing: set[tuple[int, int]] = set()
        self._reservations: dict[str, tuple[int, int]] = {}
        self.target_log: list[tuple[str, tuple[int, int], str]] = []
        self._site_paths: set[str] = set()
        self._site_path_wts: dict[str, str] = {}
        self._provisional_wts: dict[str, str] = {}
        self._reviewer_tours: dict[str, tuple[str, ...]] = {}
        self._now = 0.0

    def clawds(self):
        return list(self._clawds.values())

    def departed(self):
        return set(self._departed)

    def _slot_for(self, agent_id, role):
        if role == "orchestrator":
            return None
        if agent_id in {v for v in self._slots.values()}:
            return next(k for k, v in self._slots.items() if v == agent_id)
        if self._free:
            n = self._free.pop(0)
        else:
            used = set(self._slots)
            free = [n for n in range(1, 10) if n not in used]
            if not free:
                return None
            n = min(free)
        self._slots[n] = agent_id
        return n

    def _free_slot(self, agent_id):
        for n, aid in list(self._slots.items()):
            if aid == agent_id:
                del self._slots[n]
                self._free.append(n)
                self._free.sort()
                return

    def _ensure(self, agent: Agent, colour_idx: int) -> CrowdClawd:
        if agent.id in self._clawds:
            return self._clawds[agent.id]
        c = CrowdClawd(agent.id, agent.role, agent.team, colour_idx, agent.worktree,
                       self.town_hall, follow=self._slot_for(agent.id, agent.role))
        self._clawds[agent.id] = c
        return c

    def _route(self, start, goal):
        path = R.route(self.tmap, start, goal)
        return path or (start, goal)

    def _site_tile(self, path: str, state: watch.WatchState) -> tuple[int, int]:
        sites = watch_sites.layout_sites(self.tmap, self.effective_sites(state))
        tx, ty, _ = sites[path]
        return (tx, ty)

    def _nearest_building(self, path: str) -> str | None:
        best, best_len = None, -1
        for mid in self.tmap.buildings:
            mod = self.model.modules[mid]
            for candidate in [mid] + list(mod.members):
                folder = candidate.rsplit("/", 1)[0] + "/" if "/" in candidate else ""
                if path.startswith(folder) and len(folder) > best_len:
                    best, best_len = mid, len(folder)
        return best

    def _goal_tile(self, path: str, state: watch.WatchState):
        if path in self._site_paths or path in state.sites:
            return self._site_tile(path, state), path, "site"
        kind, target = watch.map_path(path, self.model, [], self.tracked)
        if kind == "module" and target in self.tmap.buildings:
            b = self.tmap.buildings[target]
            return self._stand_tile(b), target, kind
        if kind == "site":
            return self._site_tile(target, state), target, kind
        nb = self._nearest_building(path)
        if nb:
            return self._stand_tile(self.tmap.buildings[nb]), nb, "nearest"
        return self.town_hall, path, "file"

    def _stand_tile(self, building: Building):
        return standing_spot(self.tmap, building, self._standing)

    def _hall_tile(self) -> tuple[int, int]:
        return hall_standing_spot(self.tmap, self.town_hall, self._standing)

    def _departing(self, c: CrowdClawd) -> bool:
        return c.pose in ("hop", "leave") or c.leaving or c.goal_kind == "exit"

    def _start_exit_if_ready(self, c: CrowdClawd, now: float) -> bool:
        if not c.leaving or c.goal_kind == "exit":
            return False
        if c.goal_kind == "hall" and (c.pose != "idle" or not c.at_hall):
            return False
        self._release_standing(c)
        self._send(c, (c.tile[0], self.tmap.height), "exit", now)
        c.leaving = False
        return True

    def _release_standing(self, c: CrowdClawd):
        tile = self._reservations.pop(c.agent_id, None)
        if tile is not None:
            self._standing.discard(tile)
        c.reserved_tile = None

    def _reserve_standing(self, c: CrowdClawd, tile: tuple[int, int]):
        self._release_standing(c)
        self._standing.add(tile)
        self._reservations[c.agent_id] = tile
        c.reserved_tile = tile

    def _send(self, c: CrowdClawd, goal, reason: str, now: float, *, module: str | None = None):
        self._release_standing(c)
        if c.pose == "walk" and c.walk_t < 1.0:
            start = c.path[c.path_i] if c.path_i < len(c.path) else c.tile
        else:
            start = c.tile
        c.path = self._route(start, goal)
        c.path_i = 0
        c.at_hall = reason == "hall"
        if len(c.path) <= 1 and c.tile == goal:
            c.walk_t = 1.0
            c.pose = "idle"
        else:
            c.walk_t = 0.0
            c.pose = "walk"
        c.last_event = now
        c.idle_phase = 0.0
        c.goal_module = module
        c.goal_kind = reason
        if reason in STANDING_GOALS:
            self._reserve_standing(c, goal)
        self.target_log.append((c.agent_id, goal, reason))

    def _tour_tile(self, mod: str) -> tuple[int, int]:
        if mod not in self.tmap.buildings:
            return self.town_hall
        return standing_spot(self.tmap, self.tmap.buildings[mod], self._standing)

    def _nearest_walkable(self, tile: tuple[int, int]) -> tuple[int, int]:
        if self.tmap.walkable(*tile):
            return tile
        tx, ty = tile
        for dist in range(1, self.tmap.width + self.tmap.height):
            for dx in range(-dist, dist + 1):
                for dy in (-dist, dist):
                    t = (tx + dx, ty + dy)
                    if self.tmap.walkable(*t):
                        return t
        return self.town_hall

    def _retown_goal(self, c: CrowdClawd) -> tuple[int, int]:
        if c.goal_module:
            if c.goal_kind == "site" and c.goal_module in self.tmap.buildings:
                return self._stand_tile(self.tmap.buildings[c.goal_module])
            tile, _, _ = self._goal_tile(c.goal_module, watch.WatchState())
            return tile
        if c.path:
            return c.path[-1]
        return c.tile

    def retown(self, tmap, roads, model, tracked, town_hall):
        """Swap town map without resetting Clawds (re-survey)."""
        self.tmap = tmap
        self.roads = roads
        self.model = model
        self.tracked = tracked
        self.town_hall = town_hall
        self._standing.clear()
        self._reservations.clear()
        for c in self._clawds.values():
            c.reserved_tile = None
            if not tmap.walkable(*c.tile):
                c.tile = self._nearest_walkable(c.tile)
        for c in sorted(self._clawds.values(), key=lambda x: x.agent_id):
            if self._departing(c):
                continue
            if c.at_hall and c.goal_kind in (None, "hall", "file"):
                goal = hall_standing_spot(tmap, town_hall, self._standing)
                self._reserve_standing(c, goal)
                if c.path or c.goal_module:
                    start = c.path[c.path_i] if c.pose == "walk" and c.path_i < len(c.path) else c.tile
                    c.path = self._route(start, goal)
                    c.path_i = 0
                    c.walk_t = 0.0
                    c.pose = "walk"
                else:
                    c.tile = goal
            elif c.path or c.goal_module:
                goal = self._retown_goal(c)
                if c.goal_kind in STANDING_GOALS:
                    self._reserve_standing(c, goal)
                start = c.path[c.path_i] if c.pose == "walk" and c.path_i < len(c.path) else c.tile
                c.path = self._route(start, goal)
                c.path_i = 0
                c.walk_t = 0.0
                c.pose = "walk"

    def apply(self, events: list[Event], state: watch.WatchState,
              team_colours: dict[str, int], now: float):
        self._now = now
        self._reviewer_tours = {aid: tuple(mods) for aid, mods in state.reviewer_tours.items()}
        for ev in sorted(events, key=lambda e: e.seen):
            if ev.agent is None:
                continue
            if ev.kind == "leave":
                wt = ev.agent.worktree or ""
                drop = [aid for aid in self._clawds
                        if aid == ev.agent.id
                        or (wt and (aid == wt or aid.startswith(f"{wt}/")))]
                for aid in drop:
                    gone = self._clawds[aid]
                    self._release_standing(gone)
                    self._free_slot(aid)
                    self._clawds.pop(aid, None)
                    self._departed.add(aid)
                if wt:
                    self._provisional = {k: v for k, v in self._provisional.items()
                                         if self._provisional_wts.get(k) != wt}
                    self._provisional_wts = {k: w for k, w in self._provisional_wts.items()
                                             if w != wt}
                    self._site_paths = {p for p in self._site_paths
                                        if self._site_path_wts.get(p) != wt}
                    self._site_path_wts = {p: w for p, w in self._site_path_wts.items()
                                           if w != wt}
                continue
            idx = team_colours.get(ev.agent.team or "", 0)
            c = self._ensure(ev.agent, idx)
            c.last_event = now
            c.idle_phase = 0.0
            if ev.kind == "start":
                if c.follow is None and ev.agent.role != "orchestrator":
                    c.follow = self._slot_for(ev.agent.id, ev.agent.role)
                self._send(c, self._hall_tile(), "hall", now)
            elif ev.kind in ("edit", "delete"):
                if ev.path:
                    tile, mod, kind = self._goal_tile(ev.path, state)
                    if kind == "module":
                        self._provisional[mod] = ev.agent.team or ""
                        if ev.agent.worktree:
                            self._provisional_wts[mod] = ev.agent.worktree
                    self._send(c, tile, kind, now, module=mod if kind in ("module", "site", "nearest") else None)
            elif ev.kind == "create" and ev.path:
                self._site_paths.add(ev.path)
                if ev.agent.worktree:
                    self._site_path_wts[ev.path] = ev.agent.worktree
                tile, mod, kind = self._goal_tile(ev.path, state)
                self._send(c, tile, "site", now, module=ev.path)
            elif ev.kind == "commit":
                c.pose = "hammer"
                c.hammer_until = now + HAMMER_TIME
            elif ev.kind == "finish":
                wt = ev.agent.worktree or ""
                fb = state.flags.get(wt)
                c.flag_building = fb
                self._send(c, self._hall_tile(), "hall", now)
            elif ev.kind == "merge":
                self._release_standing(c)
                c.goal_module = None
                c.goal_kind = None
                c.at_hall = False
                c.pose = "hop"
                c.hop_i = 0
                c.hop_y = HOP_HEIGHTS[0]
                c.hop_phase = 0.0
            elif ev.kind == "review_start":
                c.tour = tuple(state.reviewer_tours.get(ev.agent.id, ()))
                c.tour_i = 0
                c.tour_until = 0.0
                self._send(c, self._hall_tile(), "hall", now)
            elif ev.kind == "review_finish":
                c.tour = ()
                c.tour_i = 0
                c.tour_until = 0.0
                self._send(c, self._hall_tile(), "hall", now)
                c.leaving = True
            elif ev.kind == "read" and ev.agent.role == "orchestrator" and ev.path:
                tile, _, _ = self._goal_tile(ev.path, state)
                self._send(c, tile, "read", now)
                c.pose = "peer"
                c.peer_until = now + PEER_TIME
            if ev.kind in ("edit", "create", "delete") and c.flag_building:
                c.flag_building = None

    def effective_scaffold(self, state: watch.WatchState) -> dict[str, str]:
        out = dict(state.scaffolded)
        for mod, team in self._provisional.items():
            out.setdefault(mod, team)
            if mod in state.scaffolded:
                out[mod] = state.scaffolded[mod]
        return out

    def effective_sites(self, state: watch.WatchState) -> list[str]:
        return sorted(set(state.sites) | self._site_paths)

    def seed(self, state: watch.WatchState, team_colours: dict[str, int]):
        self._clawds.clear()
        self._standing.clear()
        self._reservations.clear()
        self._reviewer_tours = {aid: tuple(mods) for aid, mods in state.reviewer_tours.items()}
        for astate in sorted(state.agents, key=lambda s: s.agent.id):
            a = astate.agent
            idx = team_colours.get(a.team or "", 0)
            c = self._ensure(a, idx)
            if a.role == "orchestrator" or astate.status == "waiting":
                c.tile = self._hall_tile()
                c.at_hall = True
                c.goal_kind = "hall"
                self._reserve_standing(c, c.tile)
            elif a.role == "reviewer" and a.id in state.reviewer_tours:
                c.tour = tuple(state.reviewer_tours[a.id])
                c.tour_i = 0
                if c.tour:
                    mod = c.tour[0]
                    c.tile = self._tour_tile(mod)
                    c.goal_module = mod
                    c.goal_kind = "tour"
                    self._reserve_standing(c, c.tile)
            elif astate.latest_path:
                tile, mod, kind = self._goal_tile(astate.latest_path, state)
                c.tile = tile
                if kind in STANDING_GOALS:
                    c.goal_module = mod
                    c.goal_kind = kind
                    self._reserve_standing(c, tile)
            if state.flags.get(a.worktree or ""):
                c.flag_building = state.flags[a.worktree]

    def _advance_walk(self, c: CrowdClawd, dt: float, now: float) -> bool:
        if c.pose != "walk" or not c.path:
            return False
        c.walk_t += dt / game.STEP_TIME
        while c.walk_t >= 1.0 and c.path_i + 1 < len(c.path):
            c.path_i += 1
            c.tile = c.path[c.path_i]
            c.walk_t -= 1.0
            c.walk_frame = 1 + (c.walk_frame % 2)
        if c.path_i + 1 >= len(c.path) and c.walk_t >= 1.0:
            c.pose = "idle"
            c.walk_t = 1.0
            if c.goal_kind == "tour":
                c.tour_until = now + TOUR_STAY
        return True

    def step(self, dt: float) -> bool:
        self._now += dt
        moving = False
        now = self._now
        for c in list(self._clawds.values()):
            if c.pose == "hammer" and now >= c.hammer_until:
                c.pose = "idle"
            if c.pose == "peer" and now >= c.peer_until:
                self._send(c, self._hall_tile(), "hall", now)
            if c.pose == "hop":
                moving = True
                c.hop_y = float(HOP_HEIGHTS[min(c.hop_i, len(HOP_HEIGHTS) - 1)])
                c.hop_phase += dt
                if c.hop_phase >= HOP_TIME:
                    c.hop_phase = 0.0
                    c.hop_i += 1
                    if c.hop_i >= len(HOP_HEIGHTS):
                        c.pose = "leave"
                        c.leaving = True
            if self._start_exit_if_ready(c, now):
                moving = True
            moving = self._advance_walk(c, dt, now) or moving
            if (c.tour and c.at_hall and c.pose != "walk" and c.tour_i < len(c.tour)
                    and not c.tour_until):
                mod = c.tour[c.tour_i]
                tile = self._tour_tile(mod)
                self._send(c, tile, "tour", now, module=mod)
                moving = self._advance_walk(c, dt, now) or moving
            if c.tour and c.tour_until and now >= c.tour_until and c.pose != "walk":
                c.tour_i += 1
                c.tour_until = 0.0
                if c.tour_i >= len(c.tour):
                    c.tour_i = 0
                    if c.agent_id in self._reviewer_tours:
                        c.tour = self._reviewer_tours[c.agent_id]
                if c.tour and c.tour_i < len(c.tour):
                    mod = c.tour[c.tour_i]
                    self._send(c, self._tour_tile(mod), "tour", now, module=mod)
                    moving = self._advance_walk(c, dt, now) or moving
            if c.pose == "idle" and now - c.last_event >= IDLE_AFTER:
                c.idle_phase += dt
                c.facing = (0, 1) if int(c.idle_phase) % 2 == 0 else (1, 0)
                moving = True
            if c.goal_kind == "exit" and c.tile[1] >= self.tmap.height - 1:
                self._release_standing(c)
                self._free_slot(c.agent_id)
                self._clawds.pop(c.agent_id, None)
                self._departed.add(c.agent_id)
        return moving

    def is_moving(self) -> bool:
        """Pure query: any timed pose or walk/hop/leave active at self._now."""
        now = self._now
        for c in self._clawds.values():
            if c.pose in ("walk", "hop") or c.leaving:
                return True
            if c.pose == "hammer" and now < c.hammer_until:
                return True
            if c.pose == "peer" and now < c.peer_until:
                return True
            if c.tour_until and now < c.tour_until:
                return True
        return False

    def allowed_targets(self, events, state):
        allowed = {}
        for ev in events:
            if not ev.agent:
                continue
            a = allowed.setdefault(ev.agent.id, set())
            a.add((self.town_hall, "hall"))
            if ev.path:
                tile, _, kind = self._goal_tile(ev.path, state)
                a.add((tile, "read" if ev.kind == "read" else kind))
            if ev.kind == "review_start":
                for mod in state.reviewer_tours.get(ev.agent.id, ()):
                    a.add((self._tour_tile(mod), "tour"))
        for agent_id, tile, reason in self.target_log:
            allowed.setdefault(agent_id, set()).add((tile, reason))
        for c in self._clawds.values():
            allowed.setdefault(c.agent_id, set()).add(
                (c.tile, "exit") if c.leaving else (c.tile, "stand"))
        return allowed

def clawd_focus_px(tmap, clawd: CrowdClawd) -> tuple[float, float]:
    if clawd.path and clawd.walk_t < 1.0 and clawd.path_i + 1 < len(clawd.path):
        a = clawd.path[clawd.path_i]
        b = clawd.path[clawd.path_i + 1]
        t = clawd.walk_t
        fx, fy = a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t
    else:
        fx, fy = clawd.tile[0] + 0.5, clawd.tile[1] + 0.5
    sx, sy = iso.to_screen(fx, fy)
    return float(sx), float(sy) - clawd.hop_y


class CameraDirector:
    def __init__(self, camera, crowd: Crowd, tmap, *, scene_offset=(0, 0)):
        self.camera = camera
        self.crowd = crowd
        self.tmap = tmap
        self._ox, self._oy = scene_offset
        self.mode = "auto"
        self.follow_slot = None
        self._auto_agent = None
        self._auto_seen = 0.0
        self._stay_until = 0.0
        self._pending: dict[str, tuple[int, float, str]] = {}

    def press(self, key: str):
        if key == "0":
            self.mode = "auto"
            self.follow_slot = None
            return
        if len(key) == 1 and key.isdigit() and key != "0":
            self.mode = "follow"
            self.follow_slot = int(key)

    def apply_events(self, events: list[Event], now: float):
        for ev in events:
            if ev.agent is None:
                continue
            aid = ev.agent.id
            if aid in self.crowd.departed() or aid not in self.crowd._clawds:
                continue
            pr = EVENT_PRIORITY.get(ev.kind, 9)
            prev = self._pending.get(aid)
            entry = (pr, ev.seen, aid)
            if prev is None or (pr, -ev.seen, aid) < (prev[0], -prev[1], prev[2]):
                self._pending[aid] = entry

    def follow_labels(self) -> dict[str, int]:
        out = {}
        for n, aid in self.crowd._slots.items():
            c = self.crowd._clawds.get(aid)
            if c and c.role != "orchestrator":
                out[aid] = n
        return out

    def _present(self, agent_id: str) -> bool:
        return agent_id not in self.crowd.departed() and agent_id in self.crowd._clawds

    @property
    def auto_agent(self) -> str | None:
        """The Clawd the automatic camera has chosen, if it is still in town."""
        aid = self._auto_agent
        return aid if aid is not None and self._present(aid) else None

    def _focus_target(self, clawd: CrowdClawd):
        fx, fy = clawd_focus_px(self.tmap, clawd)
        return fx + self._ox, fy + self._oy

    def update_town(self, tmap, scene_offset):
        self.tmap = tmap
        self._ox, self._oy = scene_offset

    def step(self, dt: float, now: float):
        if self.mode == "follow" and self.follow_slot is not None:
            aid = self.crowd._slots.get(self.follow_slot)
            if aid is None or not self._present(aid):
                self.mode = "auto"
                self.follow_slot = None
            else:
                c = self.crowd._clawds[aid]
                self.camera.set_target(*self._focus_target(c))
                return
        if self._pending and now >= self._stay_until:
            candidates = [e for e in self._pending.values() if self._present(e[2])]
            self._pending.clear()
            if candidates:
                pr, seen, agent_id = min(candidates, key=lambda e: (e[0], -e[1], e[2]))
                self._auto_agent = agent_id
                self._auto_seen = seen
                self._stay_until = now + MIN_STAY
        if self._auto_agent and self._present(self._auto_agent):
            c = self.crowd._clawds[self._auto_agent]
            self.camera.set_target(*self._focus_target(c))
        elif self._auto_agent:
            self._auto_agent = None
