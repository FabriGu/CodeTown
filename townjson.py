"""The town as JSON-ready dictionaries for the 3D view: plain data in, plain data out, no I/O.

Python sends meanings (tile kinds, problem kinds, roof indexes, paths), never colours; the
browser's web/look.js turns each meaning into a colour. Inspector text comes from the caller's
describe, the terminal Viewer's, so the two views say the same thing.
"""

import crowd
import drawtown
import focus
import game
import iso
import problems
import roads as R
import watch_ui
from events import Agent

LETTERS = {"grass": "g", "water": "w", "quay": "q", "dock": "d", "avenue": "a",
           "street": "s", "lot": "l", "plot": "p", "vacant": "v", "site": "c"}

MOTION = ("tile", "facing", "path_i", "walk_t")
LIVE_FIELDS = ("scaffold", "sites", "flags", "status", "camera")


def road(r):
    """One road: its ends, kind, width in tiles, draw layer and tile run."""
    return {"from": r.src, "to": r.dst, "kind": r.kind, "weight": r.weight,
            "half": R.half_width(r.kind, r.weight), "layer": R.ORDER.index(r.kind),
            "tiles": [list(t) for t in r.path]}


def network(roads):
    """Every road in the town, always drawn. Each has an id the selection lights by, and a line:
    the roads leaving one building share a line, so its imports read as one route."""
    found = roads.network()
    lines = {src: i for i, src in enumerate(sorted({r.src for r in found}))}
    return [{**road(r), "id": i, "line": lines[r.src]} for i, r in enumerate(found)]


def _inspect(describe, thing):
    title, facts, reasons = describe(thing)
    return {"title": title, "facts": facts, "reasons": list(reasons)}


def _building(b, describe):
    return {"path": b.module, "district": b.district, "lot": [b.x, b.y, b.size],
            "tiers": [{"half": t.half, "z0": t.z0, "z1": t.z1, "amber": t.amber}
                      for t in b.stack],
            "glass": drawtown.window_kind(b),
            "problems": [k for k in problems.KINDS if k in b.problems],
            "inspect": _inspect(describe, b)}


def town(tmap, roads, describe, *, repo, version=1, live=False):
    """Everything the browser builds once: ground, trees, buildings, warehouses and roads."""
    return {
        "version": version,
        "repo": repo,
        "size": [tmap.width, tmap.height],
        "half_w": iso.HALF_W,
        "legend": {letter: kind for kind, letter in LETTERS.items()},
        "tiles": ["".join(LETTERS[tmap.kind(x, y)] for x in range(tmap.width))
                  for y in range(tmap.height)],
        "trees": [list(t) for t in sorted(tmap.trees)],
        "districts": [{"name": name,
                       "box": list(tmap.boxes[name]) if name in tmap.boxes else None,
                       "roof": i}
                      for name, i in sorted(drawtown.roof_index(tmap).items())],
        "buildings": [_building(b, describe) for _, b in sorted(tmap.buildings.items())],
        "warehouses": [{"package": w.package, "lot": [w.x, w.y, w.size],
                        "inspect": _inspect(describe, w)}
                       for _, w in sorted(tmap.warehouses.items())],
        "roads": network(roads),
        "hall": list(crowd.town_hall_tile(tmap)),
        "step_time": game.STEP_TIME,
        "live": live,
    }


def clawd(c, live, follow, team_colours):
    """One Clawd as the browser needs it: who it is, its label, and where it is walking."""
    state = live.state
    diff = state.diff_stats.get(c.worktree or "", (0, 0))
    files = len(state.reviewer_tours.get(c.agent_id, ())) if c.role == "reviewer" else None
    label = watch_ui.agent_label(Agent(c.agent_id, c.role, c.team, c.worktree), c.role, c.team,
                                 diff, files)
    return {"id": c.agent_id, "role": c.role, "team": c.team,
            "scarf": team_colours.get(c.team or "", c.colour), "label": label,
            "follow": follow.get(c.agent_id), "tile": list(c.tile), "facing": list(c.facing),
            "pose": c.pose, "path": [list(t) for t in c.path], "path_i": c.path_i,
            "walk_t": round(c.walk_t, 3), "flag": c.flag_building}


def live_state(live, director):
    """Everything moving in the town, as meanings: Clawds, scaffolding, sites, flags, status."""
    tc = live.team_colours()
    follow = director.follow_labels()
    present = {c.worktree: c.agent_id for c in live.crowd.clawds()
               if c.role == "implementer" and c.worktree}
    return {
        "version": live.version,
        "clawds": {c.agent_id: clawd(c, live, follow, tc)
                   for c in sorted(live.crowd.clawds(), key=lambda c: c.agent_id)},
        "scaffold": {m: tc.get(team, 0) for m, team in sorted(live.scaffold().items())},
        "sites": [{"path": p, "tile": [x, y], "size": size, "scarf": tc.get(team, 0)}
                  for p, (x, y, size, team) in sorted(live.sites().items())],
        "flags": [{"agent": present.get(wt, wt), "building": mod, "scarf": tc.get(team, 0)}
                  for wt, (mod, team) in sorted(live.flags().items())],
        "status": list(live.lines()),
        "camera": director.auto_agent,
    }


def state_message(cur, t):
    return {"t": t, **cur, "clawds": list(cur["clawds"].values())}


def _key(record):
    return {k: v for k, v in record.items() if k not in MOTION}


def tick_message(prev, cur, t):
    """What changed since prev; None if nothing did. Walking on along a path changes nothing."""
    out = {}
    changed = [r for aid, r in cur["clawds"].items()
               if aid not in prev["clawds"] or _key(prev["clawds"][aid]) != _key(r)]
    if changed:
        out["clawds"] = changed
    gone = sorted(set(prev["clawds"]) - set(cur["clawds"]))
    if gone:
        out["gone"] = gone
    for name in LIVE_FIELDS:
        if prev[name] != cur[name]:
            out[name] = cur[name]
    if not out:
        return None
    out["t"] = t
    return out


def town_message(version, t):
    return {"t": t, "version": version}


def selection(tmap, roads, model, *, module=None, package=None):
    """What clicking a building or warehouse lights up; the rest of the network greys out.

    For a building: its focus (focus.select), every building's brightness (focus.dim), and the
    ids of the network's roads into or out of it. For a warehouse: the ids of its users' roads,
    nothing dimmed. None for a name that isn't in the town.
    """
    net = network(roads)
    if module is not None:
        if module not in tmap.buildings:
            return None
        f = focus.select(model, module)
        return {"focused": [module],
                "dim": {m: focus.dim(f, m) for m in sorted(tmap.buildings)},
                "lit": [r["id"] for r in net if module in (r["from"], r["to"])]}
    if package is not None:
        if package not in tmap.warehouses:
            return None
        return {"focused": [], "dim": {}, "lit": [r["id"] for r in net if r["to"] == package]}
    return None
