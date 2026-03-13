from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from dreamdive.schemas import (
    CharacterIdentity,
    CharacterSnapshot,
    NarrativeArcState,
    TrajectoryProjectionPayload,
)


class AgentRuntimeState(BaseModel):
    snapshot: CharacterSnapshot
    needs_reprojection: bool = True
    trajectory: Optional[TrajectoryProjectionPayload] = None
    voice_samples: List[str] = Field(default_factory=list)
    world_entities: List[dict] = Field(default_factory=list)


class SimulationSessionState(BaseModel):
    source_path: str
    current_tick_label: str
    current_timeline_index: int
    arc_state: NarrativeArcState
    agents: Dict[str, AgentRuntimeState] = Field(default_factory=dict)
    pending_world_events: List[dict] = Field(default_factory=list)
    pending_background_jobs: List[dict] = Field(default_factory=list)
    append_only_log: Dict[str, List[dict]] = Field(default_factory=dict)
    metadata: Dict[str, object] = Field(default_factory=dict)


class SnapshotInitializationRequest(BaseModel):
    source_path: str
    chapter_id: str
    tick_label: str
    timeline_index: int
    character_ids: List[str] = Field(default_factory=list)
    arc_state: NarrativeArcState = Field(
        default_factory=lambda: NarrativeArcState(
            current_phase="setup",
            tension_level=0.2,
            unresolved_threads=[],
            approaching_climax=False,
        )
    )
