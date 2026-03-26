from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


JSONValue = Any


class TimeHorizon(str, Enum):
    IMMEDIATE = "immediate"
    TODAY = "today"
    THIS_WEEK = "this_week"
    LONGER = "longer"


class ReplayKey(BaseModel):
    tick: str
    timeline_index: int = Field(ge=0)
    event_sequence: int = Field(default=0, ge=0)

    model_config = ConfigDict(frozen=True)


class StateChangeLogEntry(BaseModel):
    character_id: str
    dimension: str
    replay_key: ReplayKey
    event_id: Optional[str] = None
    from_value: Optional[JSONValue] = None
    to_value: JSONValue
    trigger: Optional[str] = None
    emotional_tag: Optional[str] = None
    pinned: bool = False


class RelationshipLogEntry(BaseModel):
    from_character_id: str
    to_character_id: str
    replay_key: ReplayKey
    event_id: Optional[str] = None
    summary: str = ""
    reason: str = ""
    pinned: bool = False


class Goal(BaseModel):
    priority: int = Field(ge=1)
    description: str
    challenge: str = ""
    time_horizon: TimeHorizon


class GoalStackSnapshot(BaseModel):
    character_id: str
    replay_key: ReplayKey
    goals: List[Goal]
    actively_avoiding: Optional[str] = None
    most_uncertain_relationship: Optional[str] = None


class EpisodicMemory(BaseModel):
    character_id: str
    replay_key: ReplayKey
    event_id: Optional[str] = None
    participants: List[str] = Field(default_factory=list)
    location: Optional[str] = None
    summary: str
    emotional_tag: Optional[str] = None
    salience: float = Field(ge=0.0, le=1.0)
    pinned: bool = False
    compressed: bool = False
    semantic_score: Optional[float] = Field(default=None, ge=0.0, le=1.0, exclude=True)
    embedding: Optional[List[float]] = Field(default=None, exclude=True)


class NarrativeArcState(BaseModel):
    current_phase: str
    tension_level: float = Field(ge=0.0, le=1.0)
    unresolved_threads: List[str] = Field(default_factory=list)
    approaching_climax: bool = False


class WorldSnapshot(BaseModel):
    replay_key: ReplayKey
    agent_locations: Dict[str, str] = Field(default_factory=dict)
    narrative_arc: NarrativeArcState
    unresolved_threads: List[str] = Field(default_factory=list)
    next_tick_size_minutes: int = Field(ge=1)


class CharacterIdentity(BaseModel):
    character_id: str
    name: str
    background: Optional[str] = None
    core_traits: List[str] = Field(default_factory=list)
    values: List[str] = Field(default_factory=list)
    fears: List[str] = Field(default_factory=list)
    desires: List[str] = Field(default_factory=list)
    personality_summary: str = ""
    domain_attributes: Dict[str, JSONValue] = Field(default_factory=dict)


class SnapshotInference(BaseModel):
    emotional_summary: str
    immediate_tension: str
    unspoken_subtext: str
    physical_status: str = ""
    location: str = ""
    knowledge: List[str] = Field(default_factory=list)


class GoalSeedPayload(BaseModel):
    goal_stack: List[Goal]
    actively_avoiding: str = ""
    most_uncertain_relationship: str = ""


class UnifiedInitPayload(BaseModel):
    """Combined snapshot inference + goal seeding output for a single character."""

    emotional_summary: str
    immediate_tension: str
    unspoken_subtext: str
    physical_status: str = ""
    location: str = ""
    knowledge: List[str] = Field(default_factory=list)
    goal_stack: List[Goal]
    actively_avoiding: str = ""
    most_uncertain_relationship: str = ""

    def to_snapshot_inference(self) -> SnapshotInference:
        return SnapshotInference(
            emotional_summary=self.emotional_summary,
            immediate_tension=self.immediate_tension,
            unspoken_subtext=self.unspoken_subtext,
            physical_status=self.physical_status,
            location=self.location,
            knowledge=list(self.knowledge),
        )

    def to_goal_seed(self) -> GoalSeedPayload:
        return GoalSeedPayload(
            goal_stack=self.goal_stack,
            actively_avoiding=self.actively_avoiding,
            most_uncertain_relationship=self.most_uncertain_relationship,
        )


class BatchedUnifiedInitPayload(BaseModel):
    """Batched unified init results keyed by character_id."""

    characters: Dict[str, UnifiedInitPayload] = Field(default_factory=dict)


class TrajectoryProjectionPayload(BaseModel):
    intention: str
    next_steps: str = ""
    projection_horizon: str = ""


class BatchedTrajectoryProjectionPayload(BaseModel):
    projections: Dict[str, TrajectoryProjectionPayload] = Field(default_factory=dict)


class AgentContextPacket(BaseModel):
    identity: Dict[str, Any]
    current_state: Dict[str, JSONValue]
    working_memory: List[str] = Field(default_factory=list)
    recent_events: List[str] = Field(default_factory=list)
    relationship_context: List[Dict[str, Any]] = Field(default_factory=list)
    world_entities: List[Dict[str, Any]] = Field(default_factory=list)
    scene_context: Dict[str, JSONValue] = Field(default_factory=dict)


class SubjectiveEntityRepresentation(BaseModel):
    agent_id: str
    entity_id: str
    name: str
    type: str
    narrative_role: str = ""
    objective_facts: List[str] = Field(default_factory=list)
    belief: str = ""
    emotional_charge: str = ""
    goal_relevance: str = ""
    misunderstanding: str = ""
    confidence: str = ""
    semantic_text: str = ""
    semantic_embedding: Optional[List[float]] = None


class GoalTensionRecord(BaseModel):
    tension_id: str
    type: str
    agents: List[str] = Field(default_factory=list)
    location: str = ""
    description: str
    information_asymmetry: Dict[str, str] = Field(default_factory=dict)
    stakes: Dict[str, str] = Field(default_factory=dict)
    likelihood: str = ""
    salience_factors: List[str] = Field(default_factory=list)


class SoloSeedSuggestion(BaseModel):
    agent_id: str
    trigger: str
    description: str


class WorldEventSuggestion(BaseModel):
    description: str
    affected_agents: List[str] = Field(default_factory=list)
    urgency: str = ""


class GoalCollisionBatchPayload(BaseModel):
    goal_tensions: List[GoalTensionRecord] = Field(default_factory=list)
    solo_seeds: List[SoloSeedSuggestion] = Field(default_factory=list)
    world_events: List[WorldEventSuggestion] = Field(default_factory=list)


class UnifiedProjectionPayload(BaseModel):
    trajectories: Dict[str, TrajectoryProjectionPayload] = Field(default_factory=dict)
    goal_tensions: List[GoalTensionRecord] = Field(default_factory=list)
    solo_seeds: List[SoloSeedSuggestion] = Field(default_factory=list)
    world_events: List[WorldEventSuggestion] = Field(default_factory=list)


class BackgroundAgentOutcome(BaseModel):
    agent_id: str
    new_knowledge: str = ""


class BackgroundEventPayload(BaseModel):
    narrative_summary: str
    outcomes: List[BackgroundAgentOutcome] = Field(default_factory=list)


class SceneResolutionConditions(BaseModel):
    primary: str
    secondary: str
    forced_exit: str


class SceneSetupPayload(BaseModel):
    scene_opening: str
    resolution_conditions: SceneResolutionConditions
    agent_perceptions: Dict[str, str] = Field(default_factory=dict)
    tension_signature: str


class AgentBeatInternal(BaseModel):
    thought: str = ""
    emotion_now: str = ""
    goal_update: str = ""
    what_i_noticed: str = ""


class AgentBeatExternal(BaseModel):
    dialogue: str = ""
    physical_action: str = ""
    tone: str = ""


class AgentBeatPayload(BaseModel):
    internal: AgentBeatInternal = Field(default_factory=AgentBeatInternal)
    external: AgentBeatExternal = Field(default_factory=AgentBeatExternal)
    held_back: str = ""


class ResolutionCheckPayload(BaseModel):
    resolved: bool
    resolution_type: str
    scene_outcome: str
    continue_scene: bool = Field(
        default=True,
        alias="continue",
        serialization_alias="continue",
    )


class UnifiedSceneBeat(BaseModel):
    """A single beat within a unified scene response."""

    agent_id: str
    internal: AgentBeatInternal = Field(default_factory=AgentBeatInternal)
    external: AgentBeatExternal = Field(default_factory=AgentBeatExternal)
    held_back: str = ""


class UnifiedSceneResolution(BaseModel):
    """Resolution information returned as part of the unified scene."""

    resolved: bool = True
    resolution_type: str = "natural"
    scene_outcome: str = ""


class UnifiedScenePayload(BaseModel):
    """Complete scene output from a single LLM call.

    Replaces the beat-by-beat loop (scene setup + N beat calls +
    resolution checks) with one structured response that contains
    the full scene: opening, all beats, summary, and resolution.
    """

    scene_opening: str
    tension_signature: str = ""
    beats: List[UnifiedSceneBeat] = Field(default_factory=list)
    scene_summary: str = ""
    resolution: UnifiedSceneResolution = Field(default_factory=UnifiedSceneResolution)


class StateUpdateRelationshipPayload(BaseModel):
    target_id: str
    summary: str = ""
    pinned: bool = False
    pin_reason: str = ""


class GoalStackUpdatePayload(BaseModel):
    top_goal_status: str
    top_goal_still_priority: bool
    new_goal: Optional[Goal] = None
    resolved_goal: Optional[str] = None


class EmotionalDeltaPayload(BaseModel):
    dominant_now: str
    shift_reason: str = ""


class StateUpdatePayload(BaseModel):
    emotional_delta: EmotionalDeltaPayload
    goal_stack_update: GoalStackUpdatePayload
    relationship_updates: List[StateUpdateRelationshipPayload] = Field(default_factory=list)
    needs_reprojection: bool
    reprojection_reason: str = ""


class PreservedMemoryPayload(BaseModel):
    event_id: str = ""
    tick: str = ""
    participants: List[str] = Field(default_factory=list)
    summary: str = ""
    emotional_tag: str = ""
    salience: float = Field(default=0.0, ge=0.0, le=1.0)
    pinned: bool = False


class CompressedMemorySummaryPayload(BaseModel):
    tick_range: str = ""
    summary: str
    emotional_tone: str = ""
    net_relationship_changes: str = ""
    net_goal_changes: str = ""
    source_event_ids: List[str] = Field(default_factory=list)


class MemoryCompressionPayload(BaseModel):
    preserved_full: List[PreservedMemoryPayload] = Field(default_factory=list)
    compressed_summaries: List[CompressedMemorySummaryPayload] = Field(default_factory=list)
    discarded_event_ids: List[str] = Field(default_factory=list)


class NarrativeThreadPayload(BaseModel):
    thread_id: str
    description: str = ""
    agents_involved: List[str] = Field(default_factory=list)
    urgency: str = ""
    resolution_condition: str = ""


class ApproachingNodePayload(BaseModel):
    description: str = ""
    agents_involved: List[str] = Field(default_factory=list)
    estimated_ticks_away: int = Field(default=0, ge=0)
    estimated_salience: float = Field(default=0.0, ge=0.0, le=1.0)


class NarrativeDriftPayload(BaseModel):
    drifting: bool = False
    drift_description: str = ""
    suggested_correction: str = ""


class NarrativeArcUpdatePayload(BaseModel):
    phase: str
    phase_changed: bool = False
    phase_change_reason: str = ""
    tension_level: float = Field(ge=0.0, le=1.0)
    tension_delta: float = 0.0
    tension_reason: str = ""
    unresolved_threads: List[NarrativeThreadPayload] = Field(default_factory=list)
    approaching_nodes: List[ApproachingNodePayload] = Field(default_factory=list)
    narrative_drift: NarrativeDriftPayload = Field(default_factory=NarrativeDriftPayload)


class CharacterSnapshot(BaseModel):
    identity: CharacterIdentity
    replay_key: ReplayKey
    current_state: Dict[str, JSONValue]
    goals: List[Goal]
    working_memory: List[EpisodicMemory]
    relationships: List[RelationshipLogEntry]
    inferred_state: Optional[SnapshotInference] = None


class UnifiedSynthesisPayload(BaseModel):
    """Combined chapter text + summary from a single LLM call."""

    chapter_text: str
    summary: str


class LLMMessage(BaseModel):
    role: str
    content: str


class StructuredResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PromptRequest(BaseModel):
    system: str
    user: str
    max_tokens: int = Field(default=2_000, ge=1)
    stream: bool = False
    metadata: Dict[str, Any] = Field(default_factory=dict)
