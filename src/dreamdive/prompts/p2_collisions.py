from __future__ import annotations

import json
from typing import Dict, List

from dreamdive.language_guidance import format_language_guidance_block
from dreamdive.prompts.common import (
    MANUSCRIPT_JSON_RULES,
    build_json_contract,
    build_participant_roster,
    format_character_block,
    meta_block as _meta_block,
)
from dreamdive.schemas import GoalCollisionBatchPayload, PromptRequest


def build_goal_collision_prompt(
    *,
    current_time: str,
    active_agent_intentions: List[Dict[str, object]],
    world_state_summary: Dict[str, object],
    tension_level: float,
    language_guidance: str = "",
    meta_section: str = "",
) -> PromptRequest:
    language_block = format_language_guidance_block(language_guidance)
    meta_block = _meta_block(meta_section)
    output_contract = build_json_contract(
        {
            "goal_tensions": [
                {
                    "tension_id": "tension_001",
                    "type": "goal_conflict",
                    "agents": ["agent_a", "agent_b"],
                    "location": "",
                    "description": "冲突描述",
                    "information_asymmetry": {"agent_a": "不知道的事"},
                    "stakes": {"agent_a": "面临的代价"},
                    "likelihood": "描述发生可能性，如'很可能'、'不太可能'",
                    "salience_factors": ["因素"],
                }
            ],
            "solo_seeds": [
                {"agent_id": "agent_a", "trigger": "触发原因", "description": "单人发展"}
            ],
            "world_events": [
                {"description": "世界事件", "affected_agents": ["agent_a"], "urgency": "low"}
            ],
        },
        extra_rules=MANUSCRIPT_JSON_RULES,
    )

    # Build per-agent sections with clear identification
    agent_sections: list[str] = []
    for i, agent in enumerate(active_agent_intentions):
        char_id = agent.get("character_id", f"unknown_{i}")
        char_name = agent.get("name", char_id)
        agent_sections.append(
            format_character_block(
                character_id=str(char_id),
                character_name=str(char_name),
                data=agent,
                block_index=i + 1,
                total_blocks=len(active_agent_intentions),
            )
        )
    agent_blocks_text = "\n".join(agent_sections)

    roster = build_participant_roster(
        [
            {
                "character_id": a.get("character_id", f"unknown_{i}"),
                "name": a.get("name", a.get("character_id", f"unknown_{i}")),
            }
            for i, a in enumerate(active_agent_intentions)
        ]
    )

    return PromptRequest(
        system=(
            "You are the World Manager of a character simulation. "
            "Identify tensions among active agents this tick. "
            "CRITICAL: Each agent has their own goals, knowledge, and emotional state. "
            "When describing information_asymmetry and stakes, be precise about WHICH "
            "agent doesn't know what, and WHICH agent faces what cost. "
            "Do not swap agents. Return valid JSON only."
        ),
        user=(
            f"{meta_block}"
            f"{language_block}"
            f"CURRENT TIME: {current_time}\n\n"
            f"{roster}"
            "ACTIVE AGENTS (each agent's state shown separately):\n\n"
            f"{agent_blocks_text}\n\n"
            "WORLD STATE:\n"
            f"{json.dumps(world_state_summary, indent=2, sort_keys=True, ensure_ascii=False)}\n"
            f"Current narrative tension level: {tension_level}\n\n"
            "Identify goal tensions, solo seeds, and world events.\n"
            "For each tension:\n"
            "- Name the EXACT agents involved by their character_id\n"
            "- Describe what EACH specific agent doesn't know (information_asymmetry)\n"
            "- Describe what EACH specific agent stands to lose (stakes)\n"
            "- Do not attribute Agent A's fears/goals to Agent B\n\n"
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


__all__ = ["build_goal_collision_prompt"]
