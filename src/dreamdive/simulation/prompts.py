from __future__ import annotations

import json
from typing import Dict, List

from dreamdive.language_guidance import format_language_guidance_block
from dreamdive.prompts.common import (
    build_character_isolation_header,
    build_information_barrier,
    build_multi_agent_preamble,
)
from dreamdive.schemas import (
    AgentContextPacket,
    BatchedTrajectoryProjectionPayload,
    BatchedUnifiedInitPayload,
    CharacterIdentity,
    GoalSeedPayload,
    PromptRequest,
    RelationshipLogEntry,
    SnapshotInference,
    TrajectoryProjectionPayload,
    UnifiedInitPayload,
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
    identity_json = json.dumps(identity.model_dump(mode="json"), indent=2, sort_keys=True, ensure_ascii=False)
    event_summary = "\n".join(f"- {item}" for item in event_summary_up_to_t) or "- None provided"
    language_block = format_language_guidance_block(language_guidance)
    output_contract = _json_contract(
        {
            "emotional_state": {
                "dominant": "一种主导情绪",
                "secondary": ["一种次级情绪"],
            },
            "immediate_tension": "此刻最具体的压力",
            "unspoken_subtext": "想说却没有说出的真实心思",
            "physical_state": {
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
    identity_json = json.dumps(identity.model_dump(mode="json"), indent=2, sort_keys=True, ensure_ascii=False)
    inferred_json = json.dumps(inferred_state.model_dump(mode="json"), indent=2, sort_keys=True, ensure_ascii=False)
    language_block = format_language_guidance_block(language_guidance)
    output_contract = _json_contract(
        {
            "goal_stack": [
                {
                    "priority": 1,
                    "description": "当前最具体的目标（含动机与情绪）",
                    "challenge": "主要阻碍或压力",
                    "time_horizon": "immediate",
                }
            ],
            "actively_avoiding": "刻意不去面对或触发的内容",
            "most_uncertain_relationship": "最不确定的关系对象",
        }
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


def build_unified_init_prompt(
    *,
    identity: CharacterIdentity,
    text_excerpt: str,
    event_summary_up_to_t: List[str],
    location: str,
    nearby_characters: List[str],
    relationships: List[RelationshipLogEntry],
    language_guidance: str = "",
) -> PromptRequest:
    """Build a single prompt that infers snapshot state AND seeds goals together."""
    identity_json = json.dumps(identity.model_dump(mode="json"), indent=2, sort_keys=True, ensure_ascii=False)
    event_summary = "\n".join(f"- {item}" for item in event_summary_up_to_t) or "- None provided"
    language_block = format_language_guidance_block(language_guidance)
    relationship_summary = [
        {
            "target_id": item.to_character_id,
            "summary": item.summary,
            "reason": item.reason,
        }
        for item in relationships
    ]
    output_contract = _json_contract(
        {
            "emotional_state": {
                "dominant": "一种主导情绪",
                "secondary": ["一种次级情绪"],
            },
            "immediate_tension": "此刻最具体的压力",
            "unspoken_subtext": "想说却没有说出的真实心思",
            "physical_state": {
                "injuries_or_constraints": "简短的身体限制，若无则留空",
                "location": location,
                "current_activity": "此刻正在做的动作",
            },
            "knowledge_state": {
                "new_knowledge": ["刚获得的事实"],
                "active_misbeliefs": ["仍在影响行动的错误认知"],
            },
            "goal_stack": [
                {
                    "priority": 1,
                    "description": "当前最具体的目标（含动机与情绪）",
                    "challenge": "主要阻碍或压力",
                    "time_horizon": "immediate",
                }
            ],
            "actively_avoiding": "刻意不去面对或触发的内容",
            "most_uncertain_relationship": "最不确定的关系对象",
        }
    )
    user = (
        "You are initializing a character simulation engine at a specific moment in a novel.\n"
        "Your task has TWO parts in a single response:\n\n"
        "PART 1 — SNAPSHOT INFERENCE:\n"
        "Infer this character's precise psychological state, physical state, immediate tension, "
        "unspoken subtext, and knowledge state at this exact moment.\n\n"
        "PART 2 — GOAL SEEDING:\n"
        "Based on the inferred state, define up to four concrete, prioritized goals grounded in "
        "this character's actual psychology. Also identify what they are actively avoiding and "
        "the relationship they are most uncertain about.\n\n"
        f"{language_block}"
        "CHARACTER PROFILE:\n"
        f"{identity_json}\n\n"
        "NOVEL PASSAGE:\n"
        f"{text_excerpt}\n\n"
        "WHAT HAS HAPPENED TO THIS CHARACTER UP TO NOW:\n"
        f"{event_summary}\n"
        f"- Current location: {location}\n"
        f"- Nearby characters: {', '.join(nearby_characters) if nearby_characters else 'None'}\n\n"
        "KEY RELATIONSHIPS:\n"
        f"{json.dumps(relationship_summary, indent=2, sort_keys=True, ensure_ascii=False)}\n\n"
        "Be specific and grounded in the text. Mark uncertain details as inferred in wording if needed. "
        "Return JSON only.\n\n"
        "OUTPUT CONTRACT:\n"
        f"{output_contract}"
    )
    return PromptRequest(
        system=(
            "Infer the full psychological, physical, and knowledge state for one character at a snapshot "
            "moment, then seed a concrete goal stack based on that state. Goals must be actionable "
            "intentions rather than personality traits. Output valid JSON only."
        ),
        user=user,
        max_tokens=2_500,
        metadata={
            "prompt_name": "p2_unified_init",
            "response_schema": UnifiedInitPayload.__name__,
            "character_id": identity.character_id,
        },
    )


def build_batched_unified_init_prompt(
    *,
    character_blocks: List[Dict[str, object]],
    language_guidance: str = "",
) -> PromptRequest:
    """Build a single prompt that initializes multiple characters at once.

    Each entry in *character_blocks* must contain:
      - character_id: str
      - identity: dict
      - text_excerpt: str
      - event_summary: list[str]
      - location: str
      - nearby_characters: list[str]
      - relationships: list[dict]
    """
    language_block = format_language_guidance_block(language_guidance)

    single_char_example = {
        "emotional_state": {
            "dominant": "一种主导情绪",
            "secondary": ["一种次级情绪"],
        },
        "immediate_tension": "此刻最具体的压力",
        "unspoken_subtext": "想说却没有说出的真实心思",
        "physical_state": {
            "injuries_or_constraints": "",
            "location": "地点",
            "current_activity": "此刻正在做的动作",
        },
        "knowledge_state": {
            "new_knowledge": ["刚获得的事实"],
            "active_misbeliefs": [],
        },
        "goal_stack": [
            {
                "priority": 1,
                "description": "当前目标、动机和情绪状态的自然语言描述",
                "challenge": "主要阻碍和可能放弃的条件",
                "time_horizon": "immediate",
            }
        ],
        "actively_avoiding": "刻意不去面对或触发的内容",
        "most_uncertain_relationship": "最不确定的关系对象",
    }
    output_contract = _json_contract(
        {
            "characters": {
                "character_id_example": single_char_example,
            }
        }
    )

    char_data_blocks = []
    for block in character_blocks:
        char_id = block.get("character_id", "unknown")
        char_data_blocks.append(
            f"--- CHARACTER: {char_id} ---\n"
            f"IDENTITY:\n{json.dumps(block.get('identity', {}), indent=2, sort_keys=True, ensure_ascii=False)}\n\n"
            f"NOVEL PASSAGE:\n{block.get('text_excerpt', '')}\n\n"
            f"EVENTS:\n"
            + ("\n".join(f"- {e}" for e in block.get("event_summary", [])) or "- None provided")
            + f"\n- Current location: {block.get('location', '')}\n"
            f"- Nearby characters: {', '.join(block.get('nearby_characters', [])) or 'None'}\n\n"
            f"RELATIONSHIPS:\n{json.dumps(block.get('relationships', []), indent=2, sort_keys=True, ensure_ascii=False)}\n"
        )
    characters_text = "\n\n".join(char_data_blocks)

    user = (
        "You are initializing a character simulation engine at a specific moment in a novel.\n"
        "For EACH character below, perform TWO tasks:\n\n"
        "1. SNAPSHOT INFERENCE: Infer their psychological, physical, and knowledge state.\n"
        "2. GOAL SEEDING: Seed up to four concrete, prioritized goals for each character.\n\n"
        "Treat each character independently. Do not leak information between them.\n\n"
        f"{language_block}"
        "CHARACTER DATA:\n\n"
        f"{characters_text}\n\n"
        "Return a JSON object with a `characters` field whose keys are character IDs "
        "and whose values contain both the inferred state and goal stack.\n\n"
        "OUTPUT CONTRACT:\n"
        f"{output_contract}"
    )
    return PromptRequest(
        system=(
            "Initialize multiple characters in batch: infer their full state and seed goal stacks. "
            "Treat each character independently. Output valid JSON only."
        ),
        user=user,
        max_tokens=2_500 * max(len(character_blocks), 1),
        metadata={
            "prompt_name": "p2_batched_unified_init",
            "response_schema": BatchedUnifiedInitPayload.__name__,
            "batch_size": len(character_blocks),
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
            "intention": "一句简洁的当前意图（含动机与权衡）",
            "next_steps": "下一步具体动作与应变",
            "projection_horizon": horizon,
        }
    )
    user = (
        "You are simulating the intentions of a character in a story.\n"
        "Speak and reason entirely from this character's first-person perspective.\n\n"
        f"{language_block}"
        "WHO YOU ARE:\n"
        f"{json.dumps(context_packet.identity, indent=2, sort_keys=True, ensure_ascii=False)}\n\n"
        "YOUR CURRENT STATE:\n"
        f"{json.dumps(context_packet.current_state, indent=2, sort_keys=True, ensure_ascii=False)}\n"
        f"Time: {current_time}\n\n"
        "WHAT YOU REMEMBER:\n"
        f"{json.dumps(context_packet.working_memory, indent=2, ensure_ascii=False)}\n\n"
        "WHO YOU KNOW IS AROUND:\n"
        f"{json.dumps(context_packet.relationship_context, indent=2, sort_keys=True, ensure_ascii=False)}\n\n"
        f"Your planning horizon: {horizon}\n\n"
        "From your perspective only, provide your intention (including motivation and what you are considering), "
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
) -> PromptRequest:
    language_block = format_language_guidance_block(language_guidance)
    output_contract = _json_contract(
        {
            "projections": {
                "character_id": {
                    "intention": "一句简洁的当前意图（含动机与权衡）",
                    "next_steps": "下一步具体动作与应变",
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
        f"{json.dumps(requests, indent=2, sort_keys=True, ensure_ascii=False)}\n\n"
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


def build_unified_projection_and_collision_prompt(
    *,
    agent_contexts: List[Dict[str, object]],
    current_time: str,
    tension_level: float,
    world_state_summary: Dict[str, object],
    language_guidance: str = "",
) -> PromptRequest:
    """Build a single prompt that projects trajectories AND detects goal collisions.

    Each entry in *agent_contexts* must contain:
      - identity: dict with character_id, name, etc.
      - current_state: dict of the character's current state
      - working_memory: list of memory strings
      - relationships: list of relationship dicts
      - planning_horizon: str like "4 ticks (~240 minutes)"
    """
    from dreamdive.schemas import UnifiedProjectionPayload

    language_block = format_language_guidance_block(language_guidance)

    output_contract = _json_contract(
        {
            "trajectories": {
                "character_id_example": {
                    "intention": "一句简洁的当前意图（含动机与权衡）",
                    "next_steps": "下一步具体动作与应变",
                    "projection_horizon": "4 ticks (~240 minutes)",
                }
            },
            "goal_tensions": [
                {
                    "tension_id": "tension_001",
                    "type": "goal_conflict",
                    "agents": ["agent_a", "agent_b"],
                    "location": "地点名称，若无则留空",
                    "description": "一句简洁的冲突描述",
                    "information_asymmetry": {"agent_a": "这个角色尚不知道的事"},
                    "stakes": {"agent_a": "这个角色此刻面临的代价"},
                    "likelihood": "描述发生可能性，如'很可能'、'不太可能'",
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

    # Build character blocks with epistemic isolation
    agent_names = [
        str(ctx.get("identity", {}).get("name", ctx.get("identity", {}).get("character_id", "unknown")))
        for ctx in agent_contexts
    ]
    preamble = build_multi_agent_preamble(agent_names)

    character_blocks = []
    prev_name = ""
    for i, ctx in enumerate(agent_contexts):
        identity = ctx.get("identity", {})
        character_id = str(identity.get("character_id", f"agent_{i}"))
        character_name = str(identity.get("name", character_id))

        if prev_name:
            character_blocks.append(
                build_information_barrier(
                    from_character=prev_name,
                    to_character=character_name,
                )
            )

        character_blocks.append(
            build_character_isolation_header(
                character_id=character_id,
                character_name=character_name,
                role_instruction="Project this character's trajectory from their first-person perspective.",
            )
        )
        character_blocks.append(
            f"IDENTITY:\n{json.dumps(identity, indent=2, sort_keys=True, ensure_ascii=False)}\n\n"
            f"CURRENT STATE:\n{json.dumps(ctx.get('current_state', {}), indent=2, sort_keys=True, ensure_ascii=False)}\n\n"
            f"WORKING MEMORY:\n{json.dumps(ctx.get('working_memory', []), indent=2, ensure_ascii=False)}\n\n"
            f"RELATIONSHIPS:\n{json.dumps(ctx.get('relationships', []), indent=2, sort_keys=True, ensure_ascii=False)}\n\n"
            f"PLANNING HORIZON: {ctx.get('planning_horizon', '4 ticks')}\n"
        )
        prev_name = character_name

    characters_text = "\n".join(character_blocks)

    user = (
        "You are the World Manager of a character simulation engine.\n"
        "Your task has TWO parts in a single response:\n\n"
        "PART 1 — TRAJECTORY PROJECTION:\n"
        "For each character below, project their intentions from THEIR first-person perspective.\n"
        "Each character's trajectory must be based ONLY on what THEY know — do not leak information "
        "between characters. Secrets, plans, and inner states of one character are INVISIBLE to others.\n\n"
        "PART 2 — COLLISION DETECTION:\n"
        "After projecting all trajectories, step back as the omniscient World Manager and identify:\n"
        "- goal_tensions: where characters' plans create conflict or dramatic tension\n"
        "- solo_seeds: individual character moments that deserve development\n"
        "- world_events: environmental or situational events\n\n"
        f"{language_block}"
        f"{preamble}"
        f"CURRENT TIME: {current_time}\n\n"
        "WORLD STATE:\n"
        f"{json.dumps(world_state_summary, indent=2, sort_keys=True, ensure_ascii=False)}\n"
        f"Current narrative tension level: {tension_level}\n\n"
        "CHARACTER DATA (each block is epistemically isolated):\n\n"
        f"{characters_text}\n\n"
        "Return a single JSON object containing:\n"
        "- `trajectories`: keyed by character_id, each with the trajectory fields\n"
        "- `goal_tensions`: list of tensions between characters\n"
        "- `solo_seeds`: list of solo development seeds\n"
        "- `world_events`: list of world events\n\n"
        "OUTPUT CONTRACT:\n"
        f"{output_contract}"
    )

    return PromptRequest(
        system=(
            "You are a story simulation World Manager. "
            "First, project each character's trajectory from their isolated first-person perspective. "
            "Then, as omniscient narrator, detect goal collisions, solo seeds, and world events. "
            "Return valid JSON only."
        ),
        user=user,
        max_tokens=4_000,
        stream=False,
        metadata={
            "prompt_name": "p2_unified_projection_and_collision",
            "response_schema": UnifiedProjectionPayload.__name__,
            "agent_count": len(agent_contexts),
        },
    )
