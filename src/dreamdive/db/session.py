from __future__ import annotations

from dataclasses import dataclass, field

from dreamdive.db.models import (
    EntityRepresentationRecord,
    EpisodicMemoryRecord,
    EventLogRecord,
    GoalStackRecord,
    RelationshipLogRecord,
    StateChangeLogRecord,
    WorldSnapshotRecord,
)


@dataclass
class InMemoryStore:
    state_change_log: list[StateChangeLogRecord] = field(default_factory=list)
    goal_stack: list[GoalStackRecord] = field(default_factory=list)
    relationship_log: list[RelationshipLogRecord] = field(default_factory=list)
    episodic_memory: list[EpisodicMemoryRecord] = field(default_factory=list)
    episodic_memory_by_char: dict[str, list[EpisodicMemoryRecord]] = field(default_factory=dict)
    entity_representations: list[EntityRepresentationRecord] = field(default_factory=list)
    entity_representations_by_agent: dict[str, list[EntityRepresentationRecord]] = field(default_factory=dict)
    world_snapshot: list[WorldSnapshotRecord] = field(default_factory=list)
    event_log: list[EventLogRecord] = field(default_factory=list)


def build_session_factory() -> InMemoryStore:
    return InMemoryStore()
