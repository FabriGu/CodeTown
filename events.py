"""Agents and events for watch and v3."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Agent:
    id: str
    role: str
    team: str | None
    worktree: str | None


@dataclass(frozen=True)
class Event:
    kind: str
    agent: Agent | None
    path: str | None = None
    seen: float = 0.0
