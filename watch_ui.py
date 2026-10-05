"""Watch status lines and label assembly."""

import labels
import sprites
import watch
from drawtown import _clawd_anchor, clawd_extra_rows, clawd_palette
from events import Agent, Event

_CLAWD_LABEL_LIFT = 8
_HALL_LABEL_LIFT = 10
_SCAFFOLD_LABEL_LIFT = 12


def _task_num(agent_id: str) -> str | None:
    for part in agent_id.split("/"):
        if part.startswith("task-"):
            return part.replace("task-", "")
    return None


def _worktree_name(agent: Agent) -> str:
    return agent.worktree or agent.id.split("/", 1)[0]


def _action_subject(agent: Agent) -> str:
    team = agent.team or agent.worktree or "agent"
    n = _task_num(agent.id)
    if n is not None:
        return f"{team} task {n}"
    wt = _worktree_name(agent)
    if team == wt:
        return team
    return f"{team} {wt}"


def _review_stem(agent_id: str) -> str:
    stem = agent_id.split("/", 1)[-1]
    if stem.startswith("review-"):
        stem = stem.replace("review-", "", 1).replace("-result", "")
    if stem.startswith("task-"):
        return f"task {stem.replace('task-', '')}"
    return stem


def agent_label(agent, role, team, diff_stats, review_file_count):
    if role == "orchestrator":
        return "orchestrator"
    if role == "agent" or not team:
        return "agent"
    if role == "reviewer":
        stem = _review_stem(agent.id)
        files = f" ({review_file_count} files)" if review_file_count else ""
        return f"review · {team} {stem}{files}"
    added, removed = diff_stats
    n = _task_num(agent.id)
    stats = f"  +{added} −{removed}"
    if n is None:
        wt = _worktree_name(agent)
        if team == wt:
            return f"{team}{stats}"
        return f"{team} · {wt}{stats}"
    return f"{team} · task {n}{stats}"


def _team_line(agents):
    order = []
    counts = {}
    for a in agents:
        if a.agent.role == "orchestrator":
            continue
        if a.agent.role == "reviewer":
            name = "review"
        else:
            name = a.agent.team or "agent"
        if name not in counts:
            order.append(name)
        counts[name] = counts.get(name, 0) + 1
    parts = []
    for name in order:
        n = counts[name]
        parts.append(f"{name} ×{n}" if n > 1 else name)
    if any(a.agent.role == "orchestrator" for a in agents):
        parts.append("orchestrator")
    return ", ".join(parts)


def line1(repo_name, state, main_tip, worktree_count, *, resurvey_error=None, mid_merge=False):
    if resurvey_error:
        return f"couldn't re-survey main: {resurvey_error}"
    if mid_merge or state.main_mid_merge:
        return "main is mid-merge"
    if not state.agents:
        return f"{repo_name}: no agents working. Watching main and {worktree_count} worktrees."
    active = [a for a in state.agents if a.status in ("working", "touring")]
    if not active and not any(a.agent.role == "orchestrator" for a in state.agents):
        return f"{repo_name}: no agents working. Watching main and {worktree_count} worktrees."
    teams = _team_line(state.agents)
    tip = main_tip[:7]
    return f"{repo_name}: {len(state.agents)} agents: {teams}. main at {tip}"


def line2(event: Event | None, state, repo_name, *, merge_line2=None):
    if event is None:
        return ""
    if event.kind == "merge" and merge_line2:
        return merge_line2
    if event.kind == "commit" and event.agent:
        return f"{_action_subject(event.agent)} committed"
    if event.kind in ("edit", "create", "delete") and event.agent and event.path:
        verb = {"edit": "edited", "create": "created", "delete": "deleted"}[event.kind]
        return f"{_action_subject(event.agent)} {verb} {event.path}"
    if event.kind == "read" and event.agent and event.path:
        return f"orchestrator read {event.path}"
    return ""


def line3(director, zoom):
    """follow_labels() -> {agent_id: slot}; emit slots ascending."""
    labels_map = director.follow_labels()
    parts = ["0 auto"]
    for slot in sorted(labels_map.values()):
        agent_id = director.crowd._slots[slot]
        team = director.crowd._clawds[agent_id].team or "?"
        parts.append(f"{slot} {team}")
    return f"{'  '.join(parts)}   +/- zoom   q quit   [{zoom}]"


def clawd_label_anchor(scene, clawd):
    """Label anchor in scene framebuffer pixels (same space as scene.centre_px)."""
    ax, ay = _clawd_anchor(scene, clawd)
    return float(ax), ay - _CLAWD_LABEL_LIFT


def clawd_taken_cells(scene, clawds, team_colours):
    """Terminal cells occupied by Clawd sprites (for labels.place `taken`)."""
    cells = set()
    for c in clawds:
        ax, ay = _clawd_anchor(scene, c)
        rows = clawd_extra_rows(c) + sprites.clawd_rows(c.facing, c.walk_frame)
        y0 = ay - len(rows) + 1
        x0 = ax - 4
        for x, y, _ in sprites.parse(rows, clawd_palette(c, team_colours)):
            px = x0 + x
            py = y0 + y
            cells.add((px * 2, py))
            cells.add((px * 2 + 1, py))
    return frozenset(cells)


def label_requests(crowd, director, scene, state, team_colours, camera_focus, zoom, *,
                    scaffolded=None):
    """Build label requests in scene framebuffer pixel space.

    ``camera_focus`` is ``(x, y)`` in the same coordinates as ``scene.centre_px``
    and label ``anchor_x`` / ``anchor_y`` (Phase 1 viewer passes ``camera.focus``
    after viewport crop).
    """
    requests = []
    scaff = scaffolded if scaffolded is not None else crowd.effective_scaffold(state)
    for c in crowd.clawds():
        diff = state.diff_stats.get(c.worktree or "", (0, 0))
        nfiles = len(state.reviewer_tours.get(c.agent_id, ()))
        text = agent_label(
            Agent(c.agent_id, c.role, c.team, c.worktree),
            c.role, c.team, diff, nfiles if c.role == "reviewer" else None)
        ax, ay = clawd_label_anchor(scene, c)
        fg, bg = labels.style_agent(labels.LIGHT, labels.DARK_GREY)
        requests.append(labels.LabelRequest(text, ax, ay, fg, bg))
    hx, hy = scene.screen(crowd.town_hall[0] + 0.5, crowd.town_hall[1] + 0.5)
    requests.append(labels.LabelRequest("Town Hall", float(hx), int(hy) - _HALL_LABEL_LIFT,
                                        *labels.style_name((112, 112, 124))))
    if zoom == "street":
        focus_x = camera_focus[0]
        ranked = sorted(scaff, key=lambda m: abs(scene.centre_px(scene.m.buildings[m])[0] - focus_x)
                        if m in scene.m.buildings else 9999)[:8]
        for mod in ranked:
            if mod not in scene.m.buildings:
                continue
            bx, by = scene.centre_px(scene.m.buildings[mod])
            path = labels.shorten(mod)
            requests.append(labels.LabelRequest(f"● {path}", float(bx), int(by) - _SCAFFOLD_LABEL_LIFT,
                                                *labels.style_name((112, 112, 124))))
    return requests
