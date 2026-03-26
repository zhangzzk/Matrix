from __future__ import annotations

import json
from typing import List

from dreamdive.language_guidance import format_language_guidance_block
from dreamdive.prompts.common import (
    MANUSCRIPT_JSON_RULES,
    build_character_isolation_header,
    build_information_barrier,
    build_json_contract,
    build_multi_agent_preamble,
    format_character_block,
    meta_block as _meta_block,
)
from dreamdive.schemas import (
    AgentContextPacket,
    BatchedTrajectoryProjectionPayload,
    CharacterIdentity,
    GoalSeedPayload,
    PromptRequest,
    RelationshipLogEntry,
    SnapshotInference,
    TrajectoryProjectionPayload,
)


def build_snapshot_inference_prompt(
    *,
    identity: CharacterIdentity,
    text_excerpt: str,
    event_summary_up_to_t: List[str],
    location: str,
    nearby_characters: List[str],
    known_state: dict | None = None,
    language_guidance: str = "",
    meta_section: str = "",
) -> PromptRequest:
    identity_json = json.dumps(
        identity.model_dump(mode="json"),
        indent=2,
        sort_keys=True,
        ensure_ascii=False,
    )
    event_summary = "\n".join(f"- {item}" for item in event_summary_up_to_t) or "- None provided"
    known_state_json = json.dumps(
        known_state or {},
        indent=2,
        sort_keys=True,
        ensure_ascii=False,
    )
    language_block = format_language_guidance_block(language_guidance)
    meta_block = _meta_block(meta_section)
    output_contract = build_json_contract(
        {
            "emotional_state": {
                "dominant": "主导情绪",
                "secondary": ["次级情绪"],
            },
            "immediate_tension": "具体压力",
            "unspoken_subtext": "潜台词",
            "physical_state": {
                "injuries_or_constraints": "",
                "location": location,
                "current_activity": "当前动作",
            },
            "knowledge_state": {
                "new_knowledge": ["新事实"],
                "active_misbeliefs": ["错误认知"],
            },
        },
        extra_rules=MANUSCRIPT_JSON_RULES,
    )
    user = (
        "You are initializing a character simulation engine at a specific moment in a novel.\n\n"
        f"{meta_block}"
        f"{language_block}"
        "CHARACTER PROFILE:\n"
        f"{identity_json}\n\n"
        "KNOWN SNAPSHOT FACTS FOR THIS CHARACTER:\n"
        f"{known_state_json}\n\n"
        "NOVEL PASSAGE:\n"
        f"{text_excerpt}\n\n"
        "WHAT HAS HAPPENED TO THIS CHARACTER UP TO NOW:\n"
        f"{event_summary}\n"
        f"- Current location: {location}\n"
        f"- Nearby characters: {', '.join(nearby_characters) if nearby_characters else 'None'}\n\n"
        "POV SAFETY RULES:\n"
        f"- The target character is {identity.name}. Infer only this character's state.\n"
        "- Do not copy another character's inner monologue, fear, desire, or private decision into the target.\n"
        "- If the passage is focalized through someone else, stay conservative and rely on directly supported facts plus observable behavior.\n"
        "- Prefer the known snapshot facts above over weak inference when they conflict.\n\n"
        "Infer this character's precise psychological state at this exact moment. "
        "Be specific and grounded in the text. Mark uncertain details as inferred in wording if needed. "
        "Return JSON only.\n\n"
        "OUTPUT CONTRACT:\n"
        f"{output_contract}"
    )
    return PromptRequest(
        system=(
            "Infer psychological state, immediate tension, unspoken subtext, physical state, "
            "and knowledge state for exactly one target character. Never attribute another "
            "character's private thoughts or goals to the target. Output valid JSON only."
        ),
        user=user,
        max_tokens=1_500,
        metadata={
            "prompt_name": "p2_1_snapshot_inference",
            "response_schema": SnapshotInference.__name__,
            "character_id": identity.character_id,
        },
    )


def build_goal_seed_prompt(
    *,
    identity: CharacterIdentity,
    inferred_state: SnapshotInference,
    recent_events: List[str],
    relationships: List[RelationshipLogEntry],
    language_guidance: str = "",
    meta_section: str = "",
) -> PromptRequest:
    identity_json = json.dumps(
        identity.model_dump(mode="json"),
        indent=2,
        sort_keys=True,
        ensure_ascii=False,
    )
    inferred_json = json.dumps(
        inferred_state.model_dump(mode="json"),
        indent=2,
        sort_keys=True,
        ensure_ascii=False,
    )
    language_block = format_language_guidance_block(language_guidance)
    meta_block = _meta_block(meta_section)
    output_contract = build_json_contract(
        {
            "goal_stack": [
                {
                    "priority": 1,
                    "description": "具体目标（含动机与情绪）",
                    "challenge": "主要阻碍",
                    "time_horizon": "immediate",
                }
            ],
            "actively_avoiding": "回避的内容",
            "most_uncertain_relationship": "最不确定的关系",
        },
        extra_rules=MANUSCRIPT_JSON_RULES,
    )
    relationship_summary = [
        {
            "target_id": item.to_character_id,
            "summary": item.summary,
            "reason": item.reason,
        }
        for item in relationships
    ]
    user = (
        "You are seeding the initial goal stack for a character simulation engine.\n\n"
        f"{meta_block}"
        f"{language_block}"
        "CHARACTER PROFILE:\n"
        f"{identity_json}\n\n"
        "CURRENT STATE:\n"
        f"{inferred_json}\n\n"
        "RECENT EVENTS:\n"
        + ("\n".join(f"- {item}" for item in recent_events) or "- None provided")
        + "\n\nKEY RELATIONSHIPS:\n"
        + json.dumps(relationship_summary, indent=2, sort_keys=True, ensure_ascii=False)
        + "\n\nDefine up to four concrete, prioritized goals grounded in this character's actual psychology. "
        "Also identify what they are actively avoiding and the relationship they are most uncertain about. "
        "Return JSON only.\n\n"
        "OUTPUT CONTRACT:\n"
        f"{output_contract}"
    )
    return PromptRequest(
        system=(
            "Seed a concrete goal stack for one character at the start of simulation. "
            "Goals must be actionable intentions rather than personality traits. Output valid JSON only."
        ),
        user=user,
        max_tokens=1_800,
        metadata={
            "prompt_name": "p2_2_goal_seeding",
            "response_schema": GoalSeedPayload.__name__,
            "character_id": identity.character_id,
        },
    )


def build_trajectory_projection_prompt(
    *,
    context_packet: AgentContextPacket,
    current_time: str,
    horizon: str,
    language_guidance: str = "",
    meta_section: str = "",
) -> PromptRequest:
    language_block = format_language_guidance_block(language_guidance)
    meta_block = _meta_block(meta_section)
    output_contract = build_json_contract(
        {
            "intention": "当前意图（含动机与权衡）",
            "next_steps": "下一步动作与应变",
            "projection_horizon": horizon,
        },
        extra_rules=MANUSCRIPT_JSON_RULES,
    )
    char_id = context_packet.identity.get("character_id", "unknown")
    char_name = context_packet.identity.get("name", char_id)
    isolation_header = build_character_isolation_header(
        character_id=char_id,
        character_name=char_name,
        role_instruction="You are projecting this character's short-horizon intentions.",
    )
    # Build recent events block (chronological context)
    recent_events_block = ""
    if context_packet.recent_events:
        recent_events_block = (
            "WHAT HAS HAPPENED RECENTLY (chronological):\n"
            + "\n".join(f"- {evt}" for evt in context_packet.recent_events)
            + "\n\n"
        )

    user = (
        f"{isolation_header}\n"
        f"{meta_block}"
        f"{language_block}"
        "WHO YOU ARE:\n"
        f"{json.dumps(context_packet.identity, indent=2, sort_keys=True, ensure_ascii=False)}\n\n"
        "YOUR CURRENT STATE:\n"
        f"{json.dumps(context_packet.current_state, indent=2, sort_keys=True, ensure_ascii=False)}\n"
        f"Time: {current_time}\n\n"
        f"{recent_events_block}"
        "WHAT YOU REMEMBER:\n"
        f"{json.dumps(context_packet.working_memory, indent=2, ensure_ascii=False)}\n\n"
        "WHO YOU KNOW IS AROUND:\n"
        f"{json.dumps(context_packet.relationship_context, indent=2, sort_keys=True, ensure_ascii=False)}\n\n"
        f"Your planning horizon: {horizon}\n\n"
        f"From {char_name}'s perspective only, provide your intention (including motivation and what you are considering), "
        "and your next steps (immediate action and contingencies).\n\n"
        "OUTPUT CONTRACT:\n"
        f"{output_contract}"
    )
    return PromptRequest(
        system=(
            "Project this character's short-horizon intention tree from first-person perspective only. "
            "Stay strictly within what the character knows. Return valid JSON only."
        ),
        user=user,
        max_tokens=1_400,
        stream=False,
        metadata={
            "prompt_name": "p2_3_trajectory_projection",
            "response_schema": TrajectoryProjectionPayload.__name__,
            "character_id": context_packet.identity["character_id"],
        },
    )


def build_batched_trajectory_projection_prompt(
    *,
    requests: List[dict],
    current_time: str,
    language_guidance: str = "",
    meta_section: str = "",
) -> PromptRequest:
    language_block = format_language_guidance_block(language_guidance)
    meta_block = _meta_block(meta_section)
    output_contract = build_json_contract(
        {
            "projections": {
                "<character_id>": {
                    "intention": "当前意图（含动机与权衡）",
                    "next_steps": "下一步动作与应变",
                    "projection_horizon": "时段",
                }
            }
        },
        extra_rules=MANUSCRIPT_JSON_RULES,
    )

    # Build isolated character blocks instead of dumping all as one JSON array
    agent_names = [
        req.get("identity", {}).get("name", req.get("character_id", "unknown"))
        for req in requests
    ]
    preamble = build_multi_agent_preamble(agent_names)

    character_sections: list[str] = []
    for i, req in enumerate(requests):
        char_id = req.get("identity", {}).get(
            "character_id", req.get("character_id", f"unknown_{i}")
        )
        char_name = req.get("identity", {}).get("name", char_id)
        block = format_character_block(
            character_id=char_id,
            character_name=char_name,
            data=req,
            block_index=i + 1,
            total_blocks=len(requests),
        )
        character_sections.append(block)
        if i < len(requests) - 1:
            next_req = requests[i + 1]
            next_name = next_req.get("identity", {}).get(
                "name",
                next_req.get("character_id", f"unknown_{i + 1}"),
            )
            character_sections.append(
                build_information_barrier(
                    from_character=char_name,
                    to_character=next_name,
                )
            )

    character_blocks_text = "\n".join(character_sections)

    user = (
        "You are simulating the short-horizon intentions of several characters in a story.\n\n"
        f"{preamble}"
        f"{meta_block}"
        f"{language_block}"
        f"CURRENT TIME: {current_time}\n\n"
        "CHARACTER REQUESTS (each character's data is isolated below):\n\n"
        f"{character_blocks_text}\n\n"
        "For each character above, project their trajectory from THEIR OWN first-person perspective.\n"
        "Each character's projection must be based ONLY on the information shown in their block.\n"
        "Do NOT let one character's fears, goals, or knowledge leak into another's projection.\n\n"
        "Return a JSON object with a `projections` field whose keys are character IDs and whose values "
        "match the single-character trajectory schema.\n\n"
        "OUTPUT CONTRACT:\n"
        f"{output_contract}"
    )
    return PromptRequest(
        system=(
            "Project character trajectories in batch. "
            "CRITICAL: Each character is epistemically isolated — they can only know what "
            "appears in their own data block. Never transfer knowledge, voice, emotions, or "
            "intentions between characters. "
            "Return valid JSON only."
        ),
        user=user,
        max_tokens=3_200,
        stream=False,
        metadata={
            "prompt_name": "p2_3_trajectory_projection_batched",
            "response_schema": BatchedTrajectoryProjectionPayload.__name__,
            "batch_size": len(requests),
        },
    )


__all__ = [
    "build_batched_trajectory_projection_prompt",
    "build_goal_seed_prompt",
    "build_snapshot_inference_prompt",
    "build_trajectory_projection_prompt",
]
