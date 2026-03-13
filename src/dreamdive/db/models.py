from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class CharacterRecord:
    id: str
    name: str
    background: Optional[str] = None
    identity: dict = field(default_factory=dict)
    universal_dimensions: dict = field(default_factory=dict)
    prominent_dimensions: dict = field(default_factory=dict)
    domain_attributes: dict = field(default_factory=dict)
    created_at: datetime = field(default_factory=utc_now)


@dataclass
class StateChangeLogRecord:
    character_id: str
    dimension: str
    tick: str
    timeline_index: int
    event_sequence: int
    to_value: Any
    id: int = 0
    event_id: Optional[str] = None
    from_value: Any = None
    trigger: Optional[str] = None
    emotional_tag: Optional[str] = None
    pinned: bool = False
    created_at: datetime = field(default_factory=utc_now)


@dataclass
class GoalStackRecord:
    character_id: str
    tick: str
    timeline_index: int
    event_sequence: int
    goals: list = field(default_factory=list)
    id: int = 0
    actively_avoiding: Optional[str] = None
    most_uncertain_relationship: Optional[str] = None
    created_at: datetime = field(default_factory=utc_now)


@dataclass
class RelationshipLogRecord:
    from_character_id: str
    to_character_id: str
    tick: str
    timeline_index: int
    event_sequence: int
    trust_value: float
    id: int = 0
    event_id: Optional[str] = None
    trust_delta: float = 0.0
    sentiment_shift: str = ""
    reason: str = ""
    pinned: bool = False
    created_at: datetime = field(default_factory=utc_now)


@dataclass
class EpisodicMemoryRecord:
    character_id: str
    tick: str
    timeline_index: int
    event_sequence: int
    summary: str
    salience: float
    id: int = 0
    event_id: Optional[str] = None
    participants: list = field(default_factory=list)
    location: Optional[str] = None
    emotional_tag: Optional[str] = None
    pinned: bool = False
    compressed: bool = False
    embedding: Optional[list] = None
    created_at: datetime = field(default_factory=utc_now)


@dataclass
class WorldSnapshotRecord:
    tick: str
    timeline_index: int
    event_sequence: int
    next_tick_size_minutes: int
    id: int = 0
    agent_locations: dict = field(default_factory=dict)
    narrative_arc: dict = field(default_factory=dict)
    unresolved_threads: list = field(default_factory=list)
    created_at: datetime = field(default_factory=utc_now)


@dataclass
class EventLogRecord:
    event_id: str
    tick: str
    timeline_index: int
    seed_type: str
    location: str
    participants: list
    description: str
    salience: float
    outcome_summary: str
    resolution_mode: str
    id: int = 0
    created_at: datetime = field(default_factory=utc_now)


@dataclass
class EntityRepresentationRecord:
    agent_id: str
    entity_id: str
    name: str
    type: str
    id: int = 0
    narrative_role: str = ""
    objective_facts: list = field(default_factory=list)
    belief: str = ""
    emotional_charge: str = ""
    goal_relevance: str = ""
    misunderstanding: str = ""
    confidence: str = ""
    semantic_text: str = ""
    semantic_embedding: Optional[list] = None
    created_at: datetime = field(default_factory=utc_now)
