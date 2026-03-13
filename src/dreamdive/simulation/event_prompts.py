from __future__ import annotations

import json
from typing import Dict, List

from dreamdive.language_guidance import format_language_guidance_block
from dreamdive.schemas import (
    AgentContextPacket,
    BackgroundEventPayload,
    CharacterSnapshot,
    PromptRequest,
    ResolutionCheckPayload,
    SceneSetupPayload,
    StateUpdatePayload,
)
from dreamdive.simulation.seeds import SimulationSeed


def _json_contract(example: dict) -> str:
    return (
        "Return exactly one JSON object using these exact keys.\n"
        "Do not rename keys, do not add extra keys, do not add any prose before or after the JSON, "
        "and do not wrap the JSON in markdown fences.\n"
        "All free-text values must stay in the manuscript language. Do not output English labels, slugs, "
        "or headings unless they are directly quoted from the source text.\n"
        "Keep every string concise and concrete.\n"
        f"{json.dumps(example, indent=2, ensure_ascii=False, sort_keys=True)}\n\n"
    )


def _compressed_snapshot(snapshot: CharacterSnapshot) -> Dict[str, object]:
    return {
        "character_id": snapshot.identity.character_id,
        "name": snapshot.identity.name,
        "goal": snapshot.goals[0].goal if snapshot.goals else "",
        "emotional_state": (
            snapshot.inferred_state.emotional_state.model_dump(mode="json")
            if snapshot.inferred_state is not None
            else snapshot.current_state.get("emotional_state", "")
        ),
        "location": snapshot.current_state.get("location", ""),
        "relationships": [
            {
                "target_id": relation.to_character_id,
                "trust_value": relation.trust_value,
                "sentiment_shift": relation.sentiment_shift,
            }
            for relation in snapshot.relationships
        ],
    }


def build_background_event_prompt(
    *,
    seed: SimulationSeed,
    snapshots: List[CharacterSnapshot],
    current_time: str,
    writing_style_note: str,
    language_guidance: str = "",
) -> PromptRequest:
    compressed = [_compressed_snapshot(snapshot) for snapshot in snapshots]
    language_block = format_language_guidance_block(language_guidance)
    output_contract = _json_contract(
        {
            "narrative_summary": "2-4句简洁叙述",
            "outcomes": [
                {
                    "agent_id": "agent_a",
                    "goal_status": "advanced",
                    "new_knowledge": "这个角色新获得的关键信息",
                    "emotional_delta": "简洁的情绪变化",
                }
            ],
            "relationship_deltas": [
                {
                    "from_id": "agent_a",
                    "to_id": "agent_b",
                    "change": "一句简洁的关系变化",
                }
            ],
            "unexpected": "",
        }
    )
    return PromptRequest(
        system=(
            "You are narrating a minor scene in a story simulation. "
            "Keep it brief, grounded, and return valid JSON only."
        ),
        user=(
            f"{language_block}"
            "SCENE SETUP:\n"
            f"Time: {current_time}\n"
            f"Location: {seed.location}\n"
            f"Participants: {', '.join(seed.participants)}\n"
            f"What was about to happen: {seed.description}\n\n"
            "PARTICIPANT STATES (compressed):\n"
            f"{json.dumps(compressed, indent=2, sort_keys=True)}\n\n"
            f"Writing style note: {writing_style_note}\n\n"
            "Narrate this scene in 2-4 sentences, then return outcomes, relationship deltas, "
            "and any unexpected development as JSON.\n\n"
            "OUTPUT CONTRACT:\n"
            f"{output_contract}"
        ),
        max_tokens=1_000,
        stream=False,
        metadata={
            "prompt_name": "p2_5_background_event",
            "response_schema": BackgroundEventPayload.__name__,
            "seed_id": seed.seed_id,
        },
    )


def build_spotlight_setup_prompt(
    *,
    seed: SimulationSeed,
    narrative_phase: str,
    tension_level: float,
    relevant_threads: List[str],
    language_guidance: str = "",
) -> PromptRequest:
    collision_record = {
        "seed_id": seed.seed_id,
        "participants": seed.participants,
        "location": seed.location,
        "description": seed.description,
        "salience": seed.salience,
    }
    language_block = format_language_guidance_block(language_guidance)
    output_contract = _json_contract(
        {
            "scene_opening": "一句到两句的开场概述",
            "resolution_conditions": {
                "primary": "主要达成条件",
                "secondary": "次要达成条件",
                "forced_exit": "强制退出条件",
            },
            "agent_perceptions": {
                "agent_a": "这个角色此刻注意到的内容",
            },
            "tension_signature": "一句中文张力概括",
        }
    )
    return PromptRequest(
        system=(
            "You are the World Manager setting up a scene for full simulation. "
            "Define opening state, perceptions, and resolution conditions. Return JSON only."
        ),
        user=(
            f"{language_block}"
            "COLLISION RECORD:\n"
            f"{json.dumps(collision_record, indent=2, sort_keys=True)}\n\n"
            "NARRATIVE CONTEXT:\n"
            f"Current story phase: {narrative_phase}\n"
            f"Tension level: {tension_level}\n"
            f"Unresolved threads relevant to this scene: {json.dumps(relevant_threads)}\n\n"
            "Define scene opening, resolution conditions, agent perceptions, and tension signature.\n\n"
            "OUTPUT CONTRACT:\n"
            f"{output_contract}"
        ),
        max_tokens=1_500,
        stream=False,
        metadata={
            "prompt_name": "p2_6_spotlight_setup",
            "response_schema": SceneSetupPayload.__name__,
            "seed_id": seed.seed_id,
        },
    )


def build_agent_beat_prompt(
    *,
    snapshot: CharacterSnapshot,
    context_packet: AgentContextPacket,
    perceived_transcript: List[Dict[str, object]],
    scene_setup: SceneSetupPayload,
    last_beat: Dict[str, object],
    voice_samples: List[str],
    language_guidance: str = "",
) -> PromptRequest:
    language_block = format_language_guidance_block(language_guidance)
    output_contract = _json_contract(
        {
            "internal": {
                "thought": "一句简洁内心想法",
                "emotion_now": "当前情绪",
                "goal_update": "简短的目标变化",
                "what_i_noticed": "此刻注意到的关键细节",
            },
            "external": {
                "dialogue": "可选对白",
                "physical_action": "外显动作",
                "tone": "说话或行动的语气",
            },
            "held_back": "刻意压下没有说出的内容",
        }
    )
    return PromptRequest(
        system=(
            "You are a character in the middle of a scene. "
            "You only know what your character knows and must separate internal from external output. "
            "Return JSON only."
        ),
        user=(
            f"{language_block}"
            f"WHO YOU ARE:\n{json.dumps(context_packet.identity, indent=2, sort_keys=True)}\n\n"
            "YOUR CURRENT STATE:\n"
            f"{json.dumps(context_packet.current_state, indent=2, sort_keys=True)}\n\n"
            "WHAT YOU REMEMBER THAT'S RELEVANT:\n"
            f"{json.dumps(context_packet.working_memory, indent=2)}\n\n"
            "WORLD ENTITIES IN YOUR SUBJECTIVE FRAMING:\n"
            f"{json.dumps(context_packet.world_entities, indent=2, sort_keys=True)}\n\n"
            "RELATIONSHIP CONTEXT:\n"
            f"{json.dumps(context_packet.relationship_context, indent=2, sort_keys=True)}\n\n"
            "THE SCENE SO FAR:\n"
            f"{json.dumps(perceived_transcript, indent=2, sort_keys=True)}\n\n"
            "WHAT JUST HAPPENED (the last beat):\n"
            f"{json.dumps(last_beat, indent=2, sort_keys=True)}\n\n"
            "YOUR VOICE:\n"
            f"{json.dumps(voice_samples, indent=2)}\n\n"
            "SCENE OPENING / TENSION:\n"
            f"{scene_setup.scene_opening}\n"
            f"Tension signature: {scene_setup.tension_signature}\n\n"
            "Respond with internal thoughts, external action, and what is held back.\n\n"
            "OUTPUT CONTRACT:\n"
            f"{output_contract}"
        ),
        max_tokens=1_400,
        stream=False,
        metadata={
            "prompt_name": "p2_6_agent_beat",
            "character_id": snapshot.identity.character_id,
        },
    )


def build_resolution_check_prompt(
    *,
    scene_transcript: List[Dict[str, object]],
    scene_setup: SceneSetupPayload,
    beat_count: int,
    max_beats: int,
    language_guidance: str = "",
) -> PromptRequest:
    language_block = format_language_guidance_block(language_guidance)
    output_contract = _json_contract(
        {
            "resolved": False,
            "resolution_type": "continue",
            "scene_outcome": "一句简短的场景结果概括",
            "continue": True,
        }
    )
    return PromptRequest(
        system=(
            "You are the World Manager monitoring a scene. "
            "Decide whether a resolution condition has been met. Return JSON only."
        ),
        user=(
            f"{language_block}"
            "SCENE SO FAR:\n"
            f"{json.dumps(scene_transcript, indent=2, sort_keys=True)}\n\n"
            "RESOLUTION CONDITIONS:\n"
            f"{json.dumps(scene_setup.resolution_conditions.model_dump(mode='json'), indent=2, sort_keys=True)}\n\n"
            f"Current beat count: {beat_count}\n"
            f"Maximum beats before forced exit: {max_beats}\n\n"
            "Has a resolution condition been met?\n\n"
            "OUTPUT CONTRACT:\n"
            f"{output_contract}"
        ),
        max_tokens=500,
        stream=False,
        metadata={
            "prompt_name": "p2_6_resolution_check",
            "response_schema": ResolutionCheckPayload.__name__,
        },
    )


def build_state_update_prompt(
    *,
    snapshot: CharacterSnapshot,
    event_outcome_from_agent_perspective: str,
    new_knowledge: List[str],
    language_guidance: str = "",
) -> PromptRequest:
    language_block = format_language_guidance_block(language_guidance)
    output_contract = _json_contract(
        {
            "emotional_delta": {
                "dominant_now": "当前主导情绪",
                "underneath": "底层情绪暗流",
                "shift_reason": "情绪变化原因",
            },
            "goal_stack_update": {
                "top_goal_status": "advanced",
                "top_goal_still_priority": True,
                "new_goal": None,
                "resolved_goal": None,
            },
            "relationship_updates": [
                {
                    "target_id": "agent_b",
                    "trust_delta": 0.0,
                    "sentiment_shift": "一句简洁的关系变化",
                    "pinned": False,
                    "pin_reason": "",
                }
            ],
            "needs_reprojection": False,
            "reprojection_reason": "若需要重投影，用一句中文说明原因；否则留空",
        }
    )
    return PromptRequest(
        system=(
            "You are updating a character's internal state after an event in a story simulation. "
            "Return emotional delta, goal stack update, relationship updates, and reprojection decision as JSON."
        ),
        user=(
            f"{language_block}"
            f"CHARACTER: {snapshot.identity.name}\n\n"
            "CORE IDENTITY (brief):\n"
            f"Primary drives: {', '.join(snapshot.identity.desires)}\n"
            f"Key values: {', '.join(snapshot.identity.values)}\n"
            f"Prominent dimensions: {json.dumps(snapshot.identity.prominent_dimensions, sort_keys=True)}\n\n"
            "STATE BEFORE THE EVENT:\n"
            f"Emotional state: {snapshot.inferred_state.emotional_state.dominant if snapshot.inferred_state else snapshot.current_state.get('emotional_state', '')}\n"
            f"Active goal: {snapshot.goals[0].goal if snapshot.goals else ''}\n"
            f"Fear: {', '.join(snapshot.identity.fears)}\n\n"
            "WHAT JUST HAPPENED:\n"
            f"{event_outcome_from_agent_perspective}\n\n"
            "WHAT THEY NOW KNOW:\n"
            f"{json.dumps(new_knowledge, indent=2)}\n\n"
            "Update emotional state, goal stack, relationships, and trajectory invalidation.\n\n"
            "OUTPUT CONTRACT:\n"
            f"{output_contract}"
        ),
        max_tokens=1_000,
        stream=False,
        metadata={
            "prompt_name": "p2_7_state_update",
            "response_schema": StateUpdatePayload.__name__,
            "character_id": snapshot.identity.character_id,
        },
    )
