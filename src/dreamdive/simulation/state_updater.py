from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Dict, List

from dreamdive.schemas import (
    CharacterSnapshot,
    GoalStackSnapshot,
    RelationshipLogEntry,
    ReplayKey,
    StateChangeLogEntry,
    StateUpdatePayload,
)
from dreamdive.simulation.event_prompts import build_state_update_prompt


@dataclass
class StateUpdateResult:
    state_changes: List[StateChangeLogEntry]
    relationship_changes: List[RelationshipLogEntry]
    goal_stack: GoalStackSnapshot
    needs_reprojection: bool
    reprojection_reason: str
    raw_update: StateUpdatePayload


class EventStateUpdater:
    def __init__(self, llm_client) -> None:
        self.llm_client = llm_client

    def update_after_event(
        self,
        *,
        snapshot: CharacterSnapshot,
        event_id: str,
        replay_key: ReplayKey,
        event_outcome_from_agent_perspective: str,
        new_knowledge: List[str],
        language_guidance: str = "",
    ) -> StateUpdateResult:
        prompt = build_state_update_prompt(
            snapshot=snapshot,
            event_outcome_from_agent_perspective=event_outcome_from_agent_perspective,
            new_knowledge=new_knowledge,
            language_guidance=language_guidance,
        )
        update = asyncio.run(self.llm_client.call_json(prompt, StateUpdatePayload))

        emotional_before = (
            snapshot.inferred_state.emotional_summary
            if snapshot.inferred_state is not None
            else str(snapshot.current_state.get("emotional_state", ""))
        )
        state_changes = [
            StateChangeLogEntry(
                character_id=snapshot.identity.character_id,
                dimension="emotional_state",
                replay_key=replay_key,
                event_id=event_id,
                from_value=emotional_before,
                to_value=update.emotional_delta.dominant_now,
                trigger=update.emotional_delta.shift_reason,
                emotional_tag=update.emotional_delta.dominant_now,
            )
        ]
        if new_knowledge:
            state_changes.append(
                StateChangeLogEntry(
                    character_id=snapshot.identity.character_id,
                    dimension="knowledge_state",
                    replay_key=replay_key,
                    event_id=event_id,
                    from_value=[],
                    to_value=new_knowledge,
                    trigger="event_knowledge_gain",
                )
            )

        goals = list(snapshot.goals)
        resolved = update.goal_stack_update.resolved_goal
        if resolved:
            goals = [goal for goal in goals if goal.description != resolved]
        if update.goal_stack_update.new_goal is not None:
            goals = [goal for goal in goals if goal.priority != update.goal_stack_update.new_goal.priority]
            goals.append(update.goal_stack_update.new_goal)
        goals = sorted(goals, key=lambda goal: goal.priority)
        renumbered = [
            goal.model_copy(update={"priority": index + 1})
            for index, goal in enumerate(goals)
        ]

        relationship_changes = [
            RelationshipLogEntry(
                from_character_id=snapshot.identity.character_id,
                to_character_id=rel.target_id,
                replay_key=replay_key,
                event_id=event_id,
                summary=rel.summary,
                reason=rel.pin_reason or update.emotional_delta.shift_reason,
                pinned=rel.pinned,
            )
            for rel in update.relationship_updates
        ]

        return StateUpdateResult(
            state_changes=state_changes,
            relationship_changes=relationship_changes,
            goal_stack=GoalStackSnapshot(
                character_id=snapshot.identity.character_id,
                replay_key=replay_key,
                goals=renumbered,
            ),
            needs_reprojection=update.needs_reprojection,
            reprojection_reason=update.reprojection_reason,
            raw_update=update,
        )

