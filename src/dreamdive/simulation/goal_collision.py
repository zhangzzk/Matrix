from __future__ import annotations

import asyncio
import json
from typing import Dict, List, Optional

from dreamdive.language_guidance import format_language_guidance_block
from dreamdive.schemas import (
    AgentContextPacket,
    CharacterSnapshot,
    GoalCollisionBatchPayload,
    PromptRequest,
    TrajectoryProjectionPayload,
)
from dreamdive.simulation.seeds import SimulationSeed


def _json_contract(example: dict) -> str:
    return (
        "Return exactly one JSON object using these exact keys.\n"
        "Do not rename keys, do not add extra keys, do not add any prose before or after the JSON, "
        "and do not wrap the JSON in markdown fences.\n"
        "All free-text values must stay in the manuscript language. Do not invent English labels, "
        "headings, or slug-style summaries.\n"
        "Keep every string concise and concrete.\n"
        f"{json.dumps(example, indent=2, ensure_ascii=False, sort_keys=True)}\n\n"
    )


def build_goal_collision_prompt(
    *,
    current_time: str,
    active_agent_intentions: List[Dict[str, object]],
    world_state_summary: Dict[str, object],
    tension_level: float,
    language_guidance: str = "",
) -> PromptRequest:
    language_block = format_language_guidance_block(language_guidance)
    output_contract = _json_contract(
        {
            "goal_tensions": [
                {
                    "tension_id": "tension_001",
                    "type": "goal_conflict",
                    "agents": ["agent_a", "agent_b"],
                    "location": "地点名称，若无则留空",
                    "description": "一句简洁的冲突描述",
                    "information_asymmetry": {"agent_a": "这个角色尚不知道的事"},
                    "stakes": {"agent_a": "这个角色此刻面临的代价"},
                    "emergence_probability": 0.7,
                    "salience_factors": ["因素一", "因素二"],
                }
            ],
            "solo_seeds": [
                {
                    "agent_id": "agent_a",
                    "trigger": "触发单人事件的原因",
                    "description": "一句简洁的单人发展描述",
                }
            ],
            "world_events": [
                {
                    "description": "一句简洁的世界事件描述",
                    "affected_agents": ["agent_a"],
                    "urgency": "low",
                }
            ],
        }
    )
    return PromptRequest(
        system=(
            "You are the World Manager of a character simulation. "
            "Identify tensions among active agents this tick, plus notable solo seeds and world events. "
            "Return valid JSON only."
        ),
        user=(
            f"{language_block}"
            f"CURRENT TIME: {current_time}\n\n"
            "ACTIVE AGENTS AND THEIR CURRENT INTENTIONS:\n"
            f"{json.dumps(active_agent_intentions, indent=2, sort_keys=True, ensure_ascii=False)}\n\n"
            "WORLD STATE:\n"
            f"{json.dumps(world_state_summary, indent=2, sort_keys=True, ensure_ascii=False)}\n"
            f"Current narrative tension level: {tension_level}\n\n"
            "Identify goal tensions, solo seeds, and world events that logically follow from the stated intentions.\n\n"
            "OUTPUT CONTRACT:\n"
            f"{output_contract}"
        ),
        max_tokens=2_000,
        stream=False,
        metadata={
            "prompt_name": "p2_4_goal_collision_detection",
            "response_schema": GoalCollisionBatchPayload.__name__,
        },
    )


class GoalCollisionDetector:
    def __init__(self, llm_client) -> None:
        self.llm_client = llm_client

    def detect_goal_collisions(
        self,
        *,
        current_time: str,
        snapshots: List[CharacterSnapshot],
        trajectories: Dict[str, TrajectoryProjectionPayload],
        contexts: Dict[str, AgentContextPacket],
        world_state_summary: Dict[str, object],
        tension_level: float,
        language_guidance: str = "",
    ) -> GoalCollisionBatchPayload:
        active_agent_intentions = []
        for snapshot in snapshots:
            character_id = snapshot.identity.character_id
            trajectory = trajectories.get(character_id)
            if trajectory is None:
                continue
            active_agent_intentions.append(
                {
                    "character_id": character_id,
                    "name": snapshot.identity.name,
                    "location": snapshot.current_state.get("location", ""),
                    "primary_intention": trajectory.primary_intention,
                    "immediate_next_action": trajectory.immediate_next_action,
                    "planning_horizon": trajectory.projection_horizon,
                    "active_goal": snapshot.goals[0].goal if snapshot.goals else "",
                    "emotional_state": (
                        snapshot.inferred_state.emotional_state.dominant
                        if snapshot.inferred_state is not None
                        else snapshot.current_state.get("emotional_state", "")
                    ),
                    "known_context": contexts[character_id].scene_context,
                }
            )

        if not active_agent_intentions:
            return GoalCollisionBatchPayload()

        prompt = build_goal_collision_prompt(
            current_time=current_time,
            active_agent_intentions=active_agent_intentions,
            world_state_summary=world_state_summary,
            tension_level=tension_level,
            language_guidance=language_guidance,
        )
        return asyncio.run(
            self.llm_client.call_json(prompt, GoalCollisionBatchPayload)
        )

    @staticmethod
    def tensions_to_seeds(payload: GoalCollisionBatchPayload) -> List[SimulationSeed]:
        seeds: List[SimulationSeed] = []
        for tension in payload.goal_tensions:
            seeds.append(
                SimulationSeed(
                    seed_id=tension.tension_id,
                    seed_type=tension.type or "goal",
                    participants=tension.agents,
                    location=tension.location,
                    description=tension.description,
                    urgency=tension.emergence_probability,
                    conflict=min(1.0, 0.4 + (0.2 * len(tension.salience_factors))),
                    emotional_charge=0.5 if tension.information_asymmetry else 0.3,
                    world_importance=0.5 if tension.stakes else 0.2,
                    novelty=0.4,
                )
            )
        for suggestion in payload.solo_seeds:
            seeds.append(
                SimulationSeed(
                    seed_id="solo_llm_{}".format(suggestion.agent_id),
                    seed_type="solo",
                    participants=[suggestion.agent_id],
                    location="",
                    description=suggestion.description,
                    urgency=0.7,
                    conflict=0.2,
                    emotional_charge=0.7,
                    world_importance=0.1,
                    novelty=0.3,
                )
            )
        for index, event in enumerate(payload.world_events):
            seeds.append(
                SimulationSeed(
                    seed_id="world_llm_{:03d}".format(index + 1),
                    seed_type="world",
                    participants=event.affected_agents,
                    location="",
                    description=event.description,
                    urgency=0.8 if event.urgency.lower() == "high" else 0.4,
                    conflict=0.2,
                    emotional_charge=0.5,
                    world_importance=0.8,
                    novelty=0.4,
                )
            )
        return seeds
