from __future__ import annotations

from collections.abc import Sequence
from typing import Optional

from dreamdive.db.replay import StateReplay
from dreamdive.memory.retrieval import rank_memories
from dreamdive.schemas import (
    CharacterIdentity,
    CharacterSnapshot,
    EpisodicMemory,
    GoalStackSnapshot,
    JSONValue,
    RelationshipLogEntry,
    ReplayKey,
    SnapshotInference,
    StateChangeLogEntry,
)


class SnapshotBootstrapper:
    """Build the deterministic part of a character snapshot at timeline T."""

    def __init__(self, replay: Optional[StateReplay] = None) -> None:
        self.replay = replay or StateReplay()

    def build_snapshot(
        self,
        *,
        identity: CharacterIdentity,
        replay_key: ReplayKey,
        state_entries: Sequence[StateChangeLogEntry],
        goal_stack: Optional[GoalStackSnapshot],
        memories: Sequence[EpisodicMemory],
        relationships: Sequence[RelationshipLogEntry],
        inferred_state: Optional[SnapshotInference] = None,
        default_state: Optional[dict[str, JSONValue]] = None,
    ) -> CharacterSnapshot:
        replay = StateReplay(default_state)
        current_state = replay.replay_character_state(
            state_entries,
            character_id=identity.character_id,
            timeline_index=replay_key.timeline_index,
        )
        working_memory = rank_memories(memories, max_results=5)

        return CharacterSnapshot(
            identity=identity,
            replay_key=replay_key,
            current_state=current_state,
            goals=goal_stack.goals if goal_stack else [],
            working_memory=working_memory,
            relationships=list(relationships),
            inferred_state=inferred_state,
        )
