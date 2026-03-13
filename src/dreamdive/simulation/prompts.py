from __future__ import annotations

import json
from typing import List

from dreamdive.language_guidance import format_language_guidance_block
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


def _json_contract(example: dict) -> str:
    return (
        "Return exactly one JSON object using these exact keys.\n"
        "Do not rename keys, do not add extra keys, do not add any prose before or after the JSON, "
        "and do not wrap the JSON in markdown fences.\n"
        "All free-text values must stay in the manuscript language. Do not switch into English labels, "
        "headings, or slug-style phrases unless the source text itself uses them.\n"
        "Keep every string concise and concrete.\n"
        f"{json.dumps(example, indent=2, ensure_ascii=False, sort_keys=True)}\n\n"
    )


def build_snapshot_inference_prompt(
    *,
    identity: CharacterIdentity,
    text_excerpt: str,
    event_summary_up_to_t: List[str],
    location: str,
    nearby_characters: List[str],
    language_guidance: str = "",
) -> PromptRequest:
    identity_json = json.dumps(identity.model_dump(mode="json"), indent=2, sort_keys=True)
    event_summary = "\n".join(f"- {item}" for item in event_summary_up_to_t) or "- None provided"
    language_block = format_language_guidance_block(language_guidance)
    output_contract = _json_contract(
        {
            "emotional_state": {
                "dominant": "一种主导情绪",
                "secondary": ["一种次级情绪"],
                "confidence": 0.7,
            },
            "immediate_tension": "此刻最具体的压力",
            "unspoken_subtext": "想说却没有说出的真实心思",
            "physical_state": {
                "energy": 0.6,
                "injuries_or_constraints": "简短的身体限制，若无则留空",
                "location": location,
                "current_activity": "此刻正在做的动作",
            },
            "knowledge_state": {
                "new_knowledge": ["刚获得的事实"],
                "active_misbeliefs": ["仍在影响行动的错误认知"],
            },
        }
    )
    user = (
        "You are initializing a character simulation engine at a specific moment in a novel.\n\n"
        f"{language_block}"
        "CHARACTER PROFILE:\n"
        f"{identity_json}\n\n"
        "NOVEL PASSAGE:\n"
        f"{text_excerpt}\n\n"
        "WHAT HAS HAPPENED TO THIS CHARACTER UP TO NOW:\n"
        f"{event_summary}\n"
        f"- Current location: {location}\n"
        f"- Nearby characters: {', '.join(nearby_characters) if nearby_characters else 'None'}\n\n"
        "Infer this character's precise psychological state at this exact moment. "
        "Be specific and grounded in the text. Mark uncertain details as inferred in wording if needed. "
        "Return JSON only.\n\n"
        "OUTPUT CONTRACT:\n"
        f"{output_contract}"
    )
    return PromptRequest(
        system=(
            "Infer psychological state, immediate tension, unspoken subtext, physical state, "
            "and knowledge state for one character at a snapshot moment. Output valid JSON only."
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
) -> PromptRequest:
    identity_json = json.dumps(identity.model_dump(mode="json"), indent=2, sort_keys=True)
    inferred_json = json.dumps(inferred_state.model_dump(mode="json"), indent=2, sort_keys=True)
    language_block = format_language_guidance_block(language_guidance)
    output_contract = _json_contract(
        {
            "goal_stack": [
                {
                    "priority": 1,
                    "goal": "当前最具体的目标",
                    "motivation": "此刻为什么在意",
                    "obstacle": "主要阻碍或压力",
                    "time_horizon": "immediate",
                    "emotional_charge": "简短情绪描述",
                    "abandon_condition": "什么情况下会放弃",
                }
            ],
            "actively_avoiding": "刻意不去面对或触发的内容",
            "most_uncertain_relationship": "最不确定的关系对象",
        }
    )
    relationship_summary = [
        {
            "target_id": item.to_character_id,
            "trust_value": item.trust_value,
            "sentiment_shift": item.sentiment_shift,
            "reason": item.reason,
        }
        for item in relationships
    ]
    user = (
        "You are seeding the initial goal stack for a character simulation engine.\n\n"
        f"{language_block}"
        "CHARACTER PROFILE:\n"
        f"{identity_json}\n\n"
        "CURRENT STATE:\n"
        f"{inferred_json}\n\n"
        "RECENT EVENTS:\n"
        + ("\n".join(f"- {item}" for item in recent_events) or "- None provided")
        + "\n\nKEY RELATIONSHIPS:\n"
        + json.dumps(relationship_summary, indent=2, sort_keys=True)
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
) -> PromptRequest:
    language_block = format_language_guidance_block(language_guidance)
    output_contract = _json_contract(
        {
            "primary_intention": "一句简洁的当前意图",
            "motivation": "此刻为什么重要",
            "immediate_next_action": "下一步具体动作",
            "contingencies": [
                {
                    "trigger": "如果发生某事",
                    "response": "我将采取的应对",
                }
            ],
            "greatest_fear_this_horizon": "这个时段里最害怕的事",
            "abandon_condition": "什么时候会放弃这条路线",
            "held_back_impulse": "想做但在克制的冲动",
            "projection_horizon": horizon,
        }
    )
    user = (
        "You are simulating the intentions of a character in a story.\n"
        "Speak and reason entirely from this character's first-person perspective.\n\n"
        f"{language_block}"
        "WHO YOU ARE:\n"
        f"{json.dumps(context_packet.identity, indent=2, sort_keys=True)}\n\n"
        "YOUR CURRENT STATE:\n"
        f"{json.dumps(context_packet.current_state, indent=2, sort_keys=True)}\n"
        f"Time: {current_time}\n\n"
        "WHAT YOU REMEMBER:\n"
        f"{json.dumps(context_packet.working_memory, indent=2)}\n\n"
        "WHO YOU KNOW IS AROUND:\n"
        f"{json.dumps(context_packet.relationship_context, indent=2, sort_keys=True)}\n\n"
        "WORLD CONTEXT (as you understand it):\n"
        f"{json.dumps(context_packet.world_entities, indent=2, sort_keys=True)}\n\n"
        f"Your planning horizon: {horizon}\n\n"
        "From your perspective only, provide your primary intention, motivation, immediate next action, "
        "2-3 structured contingencies, greatest_fear_this_horizon, abandon_condition, held_back_impulse, "
        "and projection_horizon.\n\n"
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
) -> PromptRequest:
    language_block = format_language_guidance_block(language_guidance)
    output_contract = _json_contract(
        {
            "projections": {
                "character_id": {
                    "primary_intention": "一句简洁的当前意图",
                    "motivation": "此刻为什么重要",
                    "immediate_next_action": "下一步具体动作",
                    "contingencies": [
                        {
                            "trigger": "如果发生某事",
                            "response": "我将采取的应对",
                        }
                    ],
                    "greatest_fear_this_horizon": "这个时段里最害怕的事",
                    "abandon_condition": "什么时候会放弃这条路线",
                    "held_back_impulse": "想做但在克制的冲动",
                    "projection_horizon": "4 ticks (~240 minutes)",
                }
            }
        }
    )
    user = (
        "You are simulating the short-horizon intentions of several low-priority characters in a story.\n"
        "Treat each character independently. Do not leak information between them.\n"
        "Each request below already contains only what that character knows.\n\n"
        f"{language_block}"
        f"CURRENT TIME: {current_time}\n\n"
        "CHARACTER REQUESTS:\n"
        f"{json.dumps(requests, indent=2, sort_keys=True)}\n\n"
        "Return a JSON object with a `projections` field whose keys are character IDs and whose values "
        "match the single-character trajectory schema.\n\n"
        "OUTPUT CONTRACT:\n"
        f"{output_contract}"
    )
    return PromptRequest(
        system=(
            "Project low-priority character trajectories in batch. "
            "Handle each character independently from first-person perspective only. "
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
