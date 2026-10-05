"""The interactive town: a cursor, three zoom levels, the inspector, and n/p through problems.

Street level is drawn live around the cursor. District and town levels are cut
from one drawing of the whole town, shrunk; that drawing is redone only when the
selection changes. Selecting a building puts it in focus: what it uses and what
uses it stay bright, the rest dims. With a session, the session's changes stay in
focus instead.
"""

import math
import queue
import signal
import time
from functools import partial

import camera
import crowd
import drawtown
import focus
import iso
import labels
import problems
import term
import watch
import watch_ui
from livetown import (LiveTown, WatchPoller, WatchSnapshot, _n, default_resurvey_runner,
                      resurvey_main, survey_diff)
from drawtown import FLAMES, SEA, SELECT, TownScene, height_px, shrink
from render import Framebuffer
from roads import Roads
from townmap import Building, TownMap, Warehouse

STREET, DISTRICT, TOWN = "street", "district", "town"
ZOOMS = [STREET, DISTRICT, TOWN]
DISTRICT_FACTOR = 2
STEPS = {STREET: 1, DISTRICT: 2, TOWN: 4}
MOVES = {"up": (0, -1), "right": (1, 0), "down": (0, 1), "left": (-1, 0)}
KEYMAP = {"w": "up", "a": "left", "s": "down", "d": "right",
          "+": "zoom in", "=": "zoom in", "-": "zoom out", "_": "zoom out",
          "\r": "inspect", "\n": "inspect", " ": "inspect",
          "n": "next", "p": "previous", "q": "quit", "\x03": "quit"}
HINT = "WASD/arrows move   +/- zoom   Enter inspect   n/p next/previous problem   q quit"
FPS_MOVE = 24
FPS_STILL = 12
FRAME_BUDGET = 0.035
STATUS_LINES = 3
MIN_COLS, MIN_LINES = 40, 16
STYLES = ["\x1b[1;38;5;230m", "\x1b[38;5;250m", "\x1b[38;5;245m"]
RELATION = {0: "changed this session", 1: "uses a changed module"}


class FramePace:
    def __init__(self, clock=time.monotonic):
        self._clock = clock
        self._slow = False
        self._fps = FPS_STILL

    @property
    def fps(self):
        return self._fps

    def after_frame(self, frame_seconds, moving):
        if frame_seconds > FRAME_BUDGET:
            self._slow = True
        if not moving:
            self._slow = False
        if moving and not self._slow:
            self._fps = FPS_MOVE
        else:
            self._fps = FPS_STILL
        return max(0.0, 1 / self._fps - frame_seconds)


class Viewer:
    def __init__(self, tmap, roads, model, found, session=None):
        self.m, self.roads, self.model, self.found = tmap, roads, model, found
        self.session = session
        self.importers = model.importers()
        self.import_counts = {}
        for src, _ in model.edges:
            self.import_counts[src] = self.import_counts.get(src, 0) + 1
        self.zoom = STREET
        self.inspecting = False
        self.problem = None
        self.t = 0.0
        self._whole = None
        self._whole_key = None
        self._shrunk = None
        self.select_focuses = True
        start = next((tmap.centre(p.module) for p in found if tmap.centre(p.module)), None)
        self.cursor = start or (tmap.width // 2, tmap.height // 2)
        self._last_street_scene = None
        self.camera = camera.Camera((0.0, 0.0))
        self.sync_camera()

    # --- input ------------------------------------------------------------

    def press(self, key):
        if key in MOVES:
            dx, dy = MOVES[key]
            step = STEPS[self.zoom]
            x = min(max(self.cursor[0] + dx * step, 0), self.m.width - 1)
            y = min(max(self.cursor[1] + dy * step, 0), self.m.height - 1)
            self.cursor = (x, y)
            self.problem = None
            self.camera.set_target(*self._target_for_cursor())
        elif key == "zoom in":
            self.zoom = ZOOMS[max(0, ZOOMS.index(self.zoom) - 1)]
        elif key == "zoom out":
            self.zoom = ZOOMS[min(len(ZOOMS) - 1, ZOOMS.index(self.zoom) + 1)]
        elif key == "inspect":
            self.inspecting = not self.inspecting
        elif key in ("next", "previous") and self.found:
            step = 1 if key == "next" else -1
            if self.problem is None:
                self.problem = 0 if step == 1 else len(self.found) - 1
            else:
                self.problem = (self.problem + step) % len(self.found)
            self.cursor = self.m.centre(self.found[self.problem].module) or self.cursor
            self.camera.set_target(*self._target_for_cursor())

    def selected(self):
        return self.m.thing_at(*self.cursor)

    def in_focus(self, chosen):
        """The session's changes when there is a session, else the selected building."""
        if self.session is not None:
            return self.session
        if isinstance(chosen, Building) and self.select_focuses:
            return focus.select(self.model, chosen.module)
        return None

    def scene_args(self, chosen):
        f = self.in_focus(chosen)
        if f is None:
            return {"selected": chosen, "visible": self.roads.visible(chosen)}
        return {"selected": chosen, "visible": self.roads.visible(chosen, f),
                "dim": partial(focus.dim, f),
                "focused": frozenset(m for m, d in f.distance.items() if d == 0)}

    def session_line(self):
        near = [self.session.distance[m] for m in self.m.buildings if m in self.session.distance]
        return (f"session: {near.count(0)} changed, {near.count(1)} use them directly, "
                f"{sum(d > 1 for d in near)} through them")

    def _whole_px(self, tile):
        whole = self._whole_town(None)
        sx, sy = iso.to_screen(tile[0] + 0.5, tile[1] + 0.5)
        return round(sx) + whole.ox, round(sy) + whole.oy

    def _target_for_cursor(self):
        thing = self.selected()
        whole = self._whole_town(None)
        if isinstance(thing, Building):
            fx, fy = whole.centre_px(thing)
            return fx, fy - height_px(thing)
        return self._whole_px(self.cursor)

    def sync_camera(self):
        self.camera.jump(*self._target_for_cursor())

    def moving(self):
        return self.camera.gliding()

    def overlays(self, w, h):
        if self.zoom != STREET or self._last_street_scene is None:
            return []
        thing = self.selected()
        if not isinstance(thing, Building):
            return []
        scene = self._last_street_scene
        roof_x, roof_y = scene.centre_px(thing)
        roof_y -= height_px(thing)
        roof = scene.roofs.get(thing.district, (112, 112, 124))
        raw = labels.selected_building(thing, self.m.problems.get(thing.module, ()), roof)
        anchored = [labels.LabelRequest(r.text, float(roof_x), roof_y - 1, r.fg, r.bg, r.bold, r.priority)
                    for r in raw]
        return labels.place(anchored, w, h)

    # --- drawing ----------------------------------------------------------

    def frame(self, w, h):
        thing = self.selected()
        chosen = thing if isinstance(thing, (Building, Warehouse)) else None
        if self.zoom == STREET:
            whole = self._whole_town(chosen)
            fx, fy = self.camera.focus[0], self.camera.focus[1]
            sx = fx - whole.ox
            sy = fy - whole.oy
            lift = height_px(chosen) // 2 if isinstance(chosen, Building) else 0
            scene = TownScene(self.m, w, h, w // 2 - round(sx), h // 2 - round(sy) + lift,
                              t=self.t, cursor=None if chosen else self.cursor,
                              **self.scene_args(chosen))
            fb = scene.render()
            self._last_street_scene = scene
            self._mark_fires(fb, lambda b: scene.centre_px(b), inside=False)
            return fb
        self._last_street_scene = None
        whole = self._whole_town(chosen)
        factor = DISTRICT_FACTOR if self.zoom == DISTRICT else self.town_factor(w, h)
        if self.zoom == TOWN:
            cx, cy = whole.fb.w // 2, whole.fb.h // 2
        else:
            cx, cy = round(self.camera.focus[0]), round(self.camera.focus[1])
        left, top = cx - w * factor // 2, cy - h * factor // 2

        def where(x, y):
            px, py = self._point(whole, x, y)
            return (px - left) // factor, (py - top) // factor

        key = (self._whole_key, left, top, w, h, factor)
        if self._shrunk is None or self._shrunk[0] != key:
            self._shrunk = (key, shrink(_crop(whole.fb, left, top, w * factor, h * factor), factor))
        fb = Framebuffer(w, h)
        fb.rows = [list(row) for row in self._shrunk[1].rows]
        _cross(fb, *where(self.cursor[0] + 0.5, self.cursor[1] + 0.5), self.t)
        self._mark_fires(fb, lambda b: where(b.x + b.size / 2, b.y + b.size / 2), inside=True)
        return fb

    def town_factor(self, w, h):
        whole = self._whole_town(None) if self._whole is None else self._whole
        return max(DISTRICT_FACTOR + 1, math.ceil(whole.fb.w / w), math.ceil(whole.fb.h / h))

    def _whole_town(self, chosen):
        key = chosen.module if isinstance(chosen, Building) else \
            (chosen.package if chosen else None)
        if self._whole is None or self._whole_key != key:
            scene = TownScene.whole(self.m, **self.scene_args(chosen))
            scene.render()
            self._whole, self._whole_key = scene, key
        return self._whole

    @staticmethod
    def _point(scene, x, y):
        sx, sy = iso.to_screen(x, y)
        return round(sx) + scene.ox, round(sy) + scene.oy

    def _mark_fires(self, fb, where, inside):
        frame = int(self.t * 6) % 2
        for b in self.m.buildings.values():
            if problems.FIRE not in b.problems:
                continue
            x, y = where(b)
            on_screen = 0 <= x < fb.w and 0 <= y < fb.h
            if on_screen and not inside:
                continue
            ex, ey = min(max(x, 2), fb.w - 3), min(max(y, 2), fb.h - 3)
            for i in range(-1, 2):
                for j in range(-1, 2):
                    fb.set(ex + i, ey + j, FLAMES[(i + j + frame) % 2])
            if not on_screen:
                ux, uy = (x > ex) - (x < ex), (y > ey) - (y < ey)
                fb.set(ex + 2 * ux, ey + 2 * uy, FLAMES[0])

    # --- words ------------------------------------------------------------

    def status(self, cols):
        thing = self.selected()
        title, facts, issues = self.describe(thing)
        if self.session is not None:
            title = f"{self.session_line()} · {title}"
        if self.problem is not None:
            title = f"problem {self.problem + 1} of {len(self.found)} · {title}"
        lines = [title, facts if self.inspecting else "; ".join(issues[:2]),
                 "; ".join(issues) if self.inspecting else f"{HINT}   [{self.zoom}]"]
        width = max(10, cols - 2)
        return [f" {line[:width]}" for line in lines]

    def describe(self, thing):
        """A title, a line of facts, and the reasons behind each problem."""
        if isinstance(thing, Building):
            m = self.model.modules[thing.module]
            kinds = ", ".join(dict.fromkeys(p.kind for p in self.m.problems.get(m.id, ())))
            title = f"{m.id}  ({m.district})" + (f": {kinds}" if kinds else "")
            imports = self.import_counts.get(m.id, 0)
            facts = [_n(m.loc, "line"), f"complexity {m.complexity}", _n(thing.floors, "floor"),
                     _n(len(m.exports), "export"),
                     f"imported by {len(self.importers.get(m.id, ()))}",
                     f"imports {imports}", _n(len(m.tested_by), "test"),
                     f"{_n(m.churn, 'commit')} in 90 days"]
            longest = max(thing.functions, key=lambda f: (f[1], f[0]), default=None)
            if longest:
                facts.append(f"longest function {longest[0] or '(unnamed)'}: "
                             f"{_n(longest[1], 'line')}")
            d = self.session.distance.get(m.id) if self.session else None
            if d is not None:
                facts.append(RELATION.get(d, "uses a changed module through another"))
            if m.is_entry:
                facts.append("run directly")
            return title, ", ".join(facts), [f"{p.kind}: {p.reason}"
                                             for p in self.m.problems.get(m.id, ())]
        if isinstance(thing, Warehouse):
            return (f"warehouse: {thing.package}  (outside package)",
                    f"used by {_n(len(thing.users), 'module')}: {', '.join(thing.users)}", [])
        if thing and thing[0] == "plot":
            m = self.model.modules[thing[1]]
            reasons = [f"{p.kind}: {p.reason}" for p in self.m.problems.get(m.id, ())]
            return (f"{m.id}  ({m.district}): unsurveyed",
                    f"{_n(m.loc, 'line')}, {_n(m.churn, 'commit')} in 90 days", reasons)
        if thing and thing[0] == "site":
            return f"new file: {thing[1]}", "not committed yet, so it has no building", []
        if thing and thing[0] == "vacant":
            return "vacant lot: a module that stood here was deleted", "", []
        kind = self.m.kind(*self.cursor)
        names = {"grass": "free land", "street": "street", "avenue": "avenue",
                 "quay": "quay", "water": "harbor", "dock": "dock"}
        return names.get(kind, kind), "", []


def _crop(fb, left, top, w, h):
    out = Framebuffer(w, h, SEA)
    for y in range(h):
        sy = top + y
        if 0 <= sy < fb.h:
            row = fb.rows[sy]
            x0, x1 = max(0, -left), min(w, fb.w - left)
            if x0 < x1:
                out.rows[y][x0:x1] = row[left + x0:left + x1]
    return out


def _cross(fb, x, y, t):
    if int(t * 4) % 2:
        return
    for d in (-2, -1, 1, 2):
        fb.set(x + d, y, SELECT)
        fb.set(x, y + d, SELECT)


def parse_keys(data, keymap=KEYMAP):
    return term.parse_keys(data, keymap)


WATCH_KEYMAP = {"0": "0", "1": "1", "2": "2", "3": "3", "4": "4", "5": "5",
                "6": "6", "7": "7", "8": "8", "9": "9",
                "+": "zoom in", "=": "zoom in", "-": "zoom out", "_": "zoom out",
                "q": "quit", "\x03": "quit"}


def drain_viewer(viewer, q):
    while not q.empty():
        viewer.ingest(q.get_nowait())


class WatchViewer:
    def __init__(self, tmap, roads, model, rows, plat, repo_name, main_tip,
                 survey_dir, repo_root, watch_obj, zoom=DISTRICT, *,
                 resurvey_runner=None, note_resurvey=None):
        self.repo_name = repo_name
        self.repo_root = repo_root
        self.survey_dir = survey_dir
        self._watch = watch_obj
        self.zoom = zoom
        self._last_street_scene = None
        self._town_cache_key = None
        self._town_whole_fb = None
        self._town_scene = None
        clock = getattr(watch_obj, "clock", watch.FakeClock())
        self.live = LiveTown(tmap, roads, model, rows, plat, repo_name, main_tip, repo_root, clock,
                             resurvey_runner=resurvey_runner, note_resurvey=note_resurvey,
                             resurvey=lambda repo, plat_, rows_: resurvey_main(repo, plat_, rows_))
        self._town_version = self.live.version
        hall = crowd.town_hall_tile(tmap)
        whole = TownScene.whole(tmap, visible=roads.visible())
        self._whole_ox, self._whole_oy = whole.ox, whole.oy
        self._whole_w, self._whole_h = whole.fb.w, whole.fb.h
        self._hall_reserved = frozenset(
            drawtown.hall_tile_pixels(whole, hall, tmap))
        self._reserved_pixels = self._hall_reserved
        self._reserved_key = None
        self.camera = camera.Camera((0.0, 0.0))
        self._director = crowd.CameraDirector(
            self.camera, self.live.crowd, tmap, scene_offset=(self._whole_ox, self._whole_oy))
        sx, sy = iso.to_screen(hall[0] + 0.5, hall[1] + 0.5)
        self.camera.jump(round(sx) + self._whole_ox, round(sy) + self._whole_oy)

    @property
    def m(self):
        return self.live.m

    @property
    def roads(self):
        return self.live.roads

    @property
    def model(self):
        return self.live.model

    @property
    def rows(self):
        return self.live.rows

    @property
    def plat(self):
        return self.live.plat

    @property
    def main_tip(self):
        return self.live.main_tip

    @property
    def _crowd(self):
        return self.live.crowd

    @property
    def _latest_state(self):
        return self.live.state

    @property
    def _latest_event(self):
        return self.live.latest_event

    @property
    def _drops(self):
        return self.live.drops

    @property
    def _merge_line2(self):
        return self.live.merge_line2

    @property
    def t(self):
        return self.live.t

    @t.setter
    def t(self, value):
        self.live.t = value

    @property
    def _resurvey_error(self):
        return self.live.resurvey_error

    @_resurvey_error.setter
    def _resurvey_error(self, value):
        self.live.resurvey_error = value

    @property
    def _resurvey_runner(self):
        return self.live.resurvey_runner

    @_resurvey_runner.setter
    def _resurvey_runner(self, value):
        self.live.resurvey_runner = value

    @property
    def _note_resurvey(self):
        return self.live.note_resurvey

    @_note_resurvey.setter
    def _note_resurvey(self, value):
        self.live.note_resurvey = value

    def ingest(self, snapshot: WatchSnapshot):
        events = self.live.ingest(snapshot)
        if events:
            self._director.apply_events(events, self.live.t)
        self._town_cache_key = None
        self._sync_town()

    def _drain_resurvey(self):
        self.live._drain_resurvey()
        self._sync_town()

    def _sync_town(self):
        """Redo the drawing state when a re-survey has swapped the town."""
        if self.live.version == self._town_version:
            return
        self._town_version = self.live.version
        whole = TownScene.whole(self.m, visible=self.roads.visible())
        self._director.update_town(self.m, (whole.ox, whole.oy))
        self._whole_ox, self._whole_oy = whole.ox, whole.oy
        self._whole_w, self._whole_h = whole.fb.w, whole.fb.h
        self._town_cache_key = None
        self._hall_reserved = frozenset(
            drawtown.hall_tile_pixels(whole, crowd.town_hall_tile(self.m), self.m))
        self._reserved_key = None

    def tick(self, dt, now):
        live_moving = self.live.step(dt, now)
        self._sync_town()
        self._director.step(dt, now)
        return self.camera.step(dt) or live_moving

    def moving(self):
        return self.camera.gliding() or self.live.moving()

    def press(self, key):
        if key in ("zoom in", "zoom out"):
            idx = ZOOMS.index(self.zoom)
            self.zoom = ZOOMS[max(0, min(len(ZOOMS) - 1, idx + (-1 if key == "zoom in" else 1)))]
        elif len(key) == 1 and key.isdigit():
            self._director.press(key)
        elif key == "quit":
            raise KeyboardInterrupt

    def status(self, cols):
        line1, line2 = self.live.lines()
        line3 = watch_ui.line3(self._director, self.zoom)
        width = max(10, cols - 2)
        return [f" {s[:width]}" for s in (line1, line2, line3)]

    def overlays(self, w, h):
        if self.zoom != STREET or self._last_street_scene is None:
            return []
        scene = self._last_street_scene
        fx, fy = self.camera.focus
        cam_focus = (fx - self._whole_ox + scene.ox, fy - self._whole_oy + scene.oy)
        tc = self.live.team_colours()
        reqs = watch_ui.label_requests(
            self._crowd, self._director, scene, self._latest_state,
            tc, tuple(cam_focus), self.zoom,
            scaffolded=self.live.scaffold())
        return labels.place(reqs, w, h, watch_ui.clawd_taken_cells(scene, self._crowd.clawds(), tc))

    def _watch_layer(self, *, clawds=None):
        if clawds is None:
            clawds = self._crowd.clawds()
        return drawtown.WatchLayer(
            self.live.scaffold(), self.live.team_colours(),
            self.live.sites(), self.live.flags(), self.live.drops, list(clawds),
            crowd.town_hall_tile(self.m))

    @staticmethod
    def _static_layer_key(layer):
        return (
            tuple(sorted(layer.scaffolded.items())),
            tuple(sorted((p, site[:3]) for p, site in layer.sites.items())),
            tuple(sorted(layer.flags.items())),
            tuple(sorted(layer.drops.items())),
        )

    def _site_reserved_pixels(self, layer):
        if not layer.sites:
            return self._hall_reserved
        whole = TownScene.whole(self.m, visible=self.roads.visible())
        pixels = set(self._hall_reserved)
        for tx, ty, size, _team in layer.sites.values():
            for dx in range(size):
                for dy in range(size):
                    tsx, tsy = whole.screen(tx + dx, ty + dy)
                    for mask_dx, mask_dy in iso.TILE_MASK:
                        pixels.add((tsx + mask_dx, tsy + mask_dy))
        return frozenset(pixels)

    def _set_watch(self, scene, layer, zoom):
        key = tuple(sorted((p, s[:3]) for p, s in layer.sites.items()))
        if self._reserved_key != key:
            self._reserved_pixels = self._site_reserved_pixels(layer)
            self._reserved_key = key
        scene.set_watch(layer, zoom, reserved_pixels=self._reserved_pixels)

    def _town_factor(self, w, h):
        return max(DISTRICT_FACTOR + 1, math.ceil(self._whole_w / w), math.ceil(self._whole_h / h))

    def _district_frame(self, w, h, layer):
        factor = DISTRICT_FACTOR
        pw, ph = w * factor, h * factor
        cx, cy = round(self.camera.focus[0]), round(self.camera.focus[1])
        scene = TownScene(
            self.m, pw, ph,
            pw // 2 - round(cx - self._whole_ox), ph // 2 - round(cy - self._whole_oy),
            t=self.t, visible=self.roads.visible())
        self._set_watch(scene, layer, DISTRICT)
        return shrink(scene.render(), factor)

    def _town_frame(self, w, h, layer):
        factor = self._town_factor(w, h)
        static = self._watch_layer(clawds=[])
        cache_key = (id(self.m), self._static_layer_key(static))
        if self._drops or self._town_cache_key != cache_key:
            whole = TownScene.whole(self.m, visible=self.roads.visible())
            whole.t = self.t
            self._set_watch(whole, static, TOWN)
            whole.render()
            if not self._drops:
                self._town_whole_fb = whole.fb
                self._town_scene = whole
                self._town_cache_key = cache_key
            source, scene = whole.fb, whole
        else:
            source, scene = self._town_whole_fb, self._town_scene
        cx, cy = source.w // 2, source.h // 2
        left, top = cx - w * factor // 2, cy - h * factor // 2
        cropped = _crop(source, left, top, w * factor, h * factor)
        fb = shrink(cropped, factor)
        drawtown.draw_town_markers(fb, scene, layer.clawds, layer.team_colours,
                                   origin=(left, top), scale=factor)
        return fb

    def frame(self, w, h):
        layer = self._watch_layer()
        if self.zoom == STREET:
            fx, fy = self.camera.focus
            sx, sy = fx - self._whole_ox, fy - self._whole_oy
            scene = TownScene(
                self.m, w, h, w // 2 - round(sx), h // 2 - round(sy),
                t=self.t, visible=self.roads.visible())
            self._set_watch(scene, layer, STREET)
            fb = scene.render()
            self._last_street_scene = scene
            return fb
        if self.zoom == DISTRICT:
            return self._district_frame(w, h, layer)
        return self._town_frame(w, h, layer)


def run_watch(viewer, watch_obj, truecolor, clock=time.monotonic, *,
              poller_factory=WatchPoller, resurvey_runner=None):
    q = queue.Queue()
    poller = poller_factory(watch_obj, q, clock)
    if resurvey_runner is not None:
        viewer._resurvey_runner = resurvey_runner
    viewer._note_resurvey = lambda model, tip: poller.inbox.put((model, tip))
    poller.start()
    screen = term.Screen(truecolor)
    pace = FramePace(clock)
    resized = [True]
    signal.signal(signal.SIGWINCH, lambda *_: resized.__setitem__(0, True))
    with term.Terminal() as t:
        t.write("\x1b]0;CodeTown watch\x07")
        start = clock()
        prev = start
        timeout = 0.0
        cols = lines = 0
        try:
            while True:
                frame_start = clock()
                if resized[0]:
                    resized[0] = False
                    cols, lines = t.size()
                    screen.invalidate()
                    t.write("\x1b[2J")
                    if cols < MIN_COLS or lines < MIN_LINES:
                        msg = f"Make the window at least {MIN_COLS}x{MIN_LINES}"
                        t.write(f"\x1b[{max(1, lines // 2)};1H{msg[:cols]}")
                drain_viewer(viewer, q)
                now = clock() - start
                dt = now - prev
                prev = now
                for key in parse_keys(t.read(timeout), WATCH_KEYMAP):
                    if key == "quit":
                        return
                    viewer.press(key)
                if cols >= MIN_COLS and lines >= MIN_LINES:
                    fb = viewer.frame(cols // 2, lines - STATUS_LINES)
                    status = [style + line for style, line in zip(STYLES, viewer.status(cols))]
                    t.write(screen.frame(fb, status, viewer.overlays(fb.w, fb.h)))
                moving = viewer.tick(dt, now)
                timeout = pace.after_frame(clock() - frame_start, moving)
        finally:
            poller.close_event.set()
            poller.join(timeout=2)
            watch_obj.close()


def run(viewer, truecolor, clock=time.monotonic):
    """The terminal loop: read keys, draw a frame, repeat until q."""
    screen = term.Screen(truecolor)
    pace = FramePace(clock)
    resized = [True]
    signal.signal(signal.SIGWINCH, lambda *_: resized.__setitem__(0, True))
    with term.Terminal() as t:
        t.write("\x1b]0;CodeTown\x07")
        start = clock()
        timeout = 0.0
        cols = lines = 0
        while True:
            frame_start = clock()
            if resized[0]:
                resized[0] = False
                cols, lines = t.size()
                screen.invalidate()
                t.write("\x1b[2J")
                if cols < MIN_COLS or lines < MIN_LINES:
                    msg = f"Make the window at least {MIN_COLS}x{MIN_LINES}"
                    t.write(f"\x1b[{max(1, lines // 2)};1H{msg[:cols]}")
            for key in parse_keys(t.read(timeout)):
                if key == "quit":
                    return
                viewer.press(key)
            viewer.t = clock() - start
            if cols >= MIN_COLS and lines >= MIN_LINES:
                fb = viewer.frame(cols // 2, lines - STATUS_LINES)
                status = [style + line for style, line in zip(STYLES, viewer.status(cols))]
                t.write(screen.frame(fb, status, viewer.overlays(fb.w, fb.h)))
            frame_seconds = clock() - frame_start
            moving = viewer.camera.step(frame_seconds)
            timeout = pace.after_frame(frame_seconds, moving)
