from __future__ import annotations

import json
from typing import Dict, List

from dreamdive.language_guidance import format_language_guidance_block
from dreamdive.prompts.common import (
    MANUSCRIPT_JSON_RULES,
    build_character_isolation_header,
    build_json_contract,
    build_multi_agent_preamble,
    build_participant_roster,
    format_character_block,
    meta_block as _meta_block,
)
from dreamdive.schemas import (
    AgentContextPacket,
    BackgroundEventPayload,
    CharacterSnapshot,
    PromptRequest,
    ResolutionCheckPayload,
    SceneSetupPayload,
    StateUpdatePayload,
)
from dreamdive.simulation.casualty_guard import build_casualty_constraint
from dreamdive.simulation.seeds import SimulationSeed


def _compressed_snapshot(
    snapshot: CharacterSnapshot,
    name_lookup: Dict[str, str] | None = None,
) -> Dict[str, object]:
    goals = sorted(snapshot.goals, key=lambda g: g.priority)[:3]
    return {
        "character_id": snapshot.identity.character_id,
        "name": snapshot.identity.name,
        "background": snapshot.identity.background,
        "core_traits": snapshot.identity.core_traits[:3],
        "values": snapshot.identity.values[:3],
        "goals": [
            {"priority": g.priority, "description": g.description, "challenge": g.challenge}
            for g in goals
        ] if goals else [],
        "emotional_state": (
            snapshot.inferred_state.emotional_summary
            if snapshot.inferred_state is not None
            else snapshot.current_state.get("emotional_state", "")
        ),
        "location": snapshot.current_state.get("location", ""),
        "relationships": [
            {
                "target": (name_lookup or {}).get(relation.to_character_id, relation.to_character_id),
                "summary": relation.summary,
                "reason": relation.reason,
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
    meta_section: str = "",
) -> PromptRequest:
    language_block = format_language_guidance_block(language_guidance)
    meta_block = _meta_block(meta_section)
    output_contract = build_json_contract(
        {
            "narrative_summary": "2-4句叙述",
            "outcomes": [
                {
                    "agent_id": "agent_a",
                    "new_knowledge": "新信息",
                }
            ],
        },
        extra_rules=MANUSCRIPT_JSON_RULES,
    )

    # Build name lookup for resolving relationship target IDs to names
    name_lookup = {s.identity.character_id: s.identity.name for s in snapshots}

    # Build clearly labeled per-character sections
    participant_blocks: list[str] = []
    agent_names: list[str] = []
    for i, snapshot in enumerate(snapshots):
        char_id = snapshot.identity.character_id
        char_name = snapshot.identity.name
        agent_names.append(char_name)
        compressed = _compressed_snapshot(snapshot, name_lookup=name_lookup)
        participant_blocks.append(
            format_character_block(
                character_id=char_id,
                character_name=char_name,
                data=compressed,
                block_index=i + 1,
                total_blocks=len(snapshots),
            )
        )
    participant_sections = "\n".join(participant_blocks)

    roster = build_participant_roster(
        [
            {"character_id": s.identity.character_id, "name": s.identity.name}
            for s in snapshots
        ]
    )

    preamble = ""
    if len(snapshots) > 1:
        preamble = build_multi_agent_preamble(agent_names)

    return PromptRequest(
        system=(
            "You are narrating a minor scene in a story simulation. "
            "Each character has their own knowledge, goals, and emotional state — "
            "do not mix them up. Keep it brief, grounded, and return valid JSON only. "
            "Characters should behave naturally — let their traits inform actions subtly, "
            "do not have every line showcase every personality trait."
        ),
        user=(
            f"{meta_block}"
            f"{language_block}"
            f"{preamble}"
            f"{roster}"
            "SCENE SETUP:\n"
            f"Time: {current_time}\n"
            f"Location: {seed.location}\n"
            f"What was about to happen: {seed.description}\n\n"
            "PARTICIPANT STATES (each character shown separately):\n\n"
            f"{participant_sections}\n\n"
            f"Writing style note: {writing_style_note}\n\n"
            f"{build_casualty_constraint()}\n"
            "Narrate this scene in 2-4 sentences. Then for EACH participant, "
            "provide their specific outcome (new_knowledge) — "
            "make sure each outcome matches THAT character's goals and emotional state, "
            "not another participant's.\n\n"
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
    snapshots: List[CharacterSnapshot] | None = None,
    narrative_phase: str,
    tension_level: float,
    relevant_threads: List[str],
    language_guidance: str = "",
    meta_section: str = "",
) -> PromptRequest:
    collision_record = {
        "seed_id": seed.seed_id,
        "participants": seed.participants,
        "location": seed.location,
        "description": seed.description,
        "salience": seed.salience,
    }
    language_block = format_language_guidance_block(language_guidance)
    meta_block = _meta_block(meta_section)
    output_contract = build_json_contract(
        {
            "scene_opening": "开场概述",
            "resolution_conditions": {
                "primary": "主要条件",
                "secondary": "次要条件",
                "forced_exit": "强制退出",
            },
            "agent_perceptions": {"agent_a": "注意到的内容"},
            "tension_signature": "张力概括",
        },
        extra_rules=MANUSCRIPT_JSON_RULES,
    )

    # Build participant context so the World Manager knows who these characters are
    participant_context = ""
    if snapshots:
        name_lookup = {s.identity.character_id: s.identity.name for s in snapshots}
        participant_lines = []
        for s in snapshots:
            emotional = (
                s.inferred_state.emotional_summary
                if s.inferred_state
                else str(s.current_state.get("emotional_state", ""))
            )
            top_goal = s.goals[0].description if s.goals else "none"
            # Key relationships to other participants in this scene
            scene_rels = [
                f"{name_lookup.get(r.to_character_id, r.to_character_id)}: {r.summary or r.reason}"
                for r in s.relationships
                if r.to_character_id in name_lookup and r.to_character_id != s.identity.character_id
            ][:3]
            rels_str = "; ".join(scene_rels) if scene_rels else "no prior relationship"
            participant_lines.append(
                f"- {s.identity.name} ({s.identity.character_id}): "
                f"emotional={emotional}, goal=\"{top_goal}\", "
                f"relationships=[{rels_str}]"
            )
        participant_context = (
            "PARTICIPANT CONTEXT (who is in this scene):\n"
            + "\n".join(participant_lines) + "\n\n"
        )

    return PromptRequest(
        system=(
            "You are the World Manager setting up a scene for full simulation. "
            "Define opening state, perceptions, and resolution conditions. Return JSON only."
        ),
        user=(
            f"{meta_block}"
            f"{language_block}"
            "COLLISION RECORD:\n"
            f"{json.dumps(collision_record, indent=1, sort_keys=True, ensure_ascii=False)}\n\n"
            f"{participant_context}"
            "NARRATIVE CONTEXT:\n"
            f"Current story phase: {narrative_phase}\n"
            f"Tension level: {tension_level}\n"
            f"Unresolved threads relevant to this scene: {json.dumps(relevant_threads, ensure_ascii=False)}\n\n"
            f"{build_casualty_constraint()}\n"
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
    beat_index: int = 0,
    language_guidance: str = "",
    meta_section: str = "",
) -> PromptRequest:
    language_block = format_language_guidance_block(language_guidance)
    meta_block = _meta_block(meta_section)
    output_contract = build_json_contract(
        {
            "internal": {
                "thought": "内心想法",
                "emotion_now": "情绪",
                "goal_update": "目标变化",
                "what_i_noticed": "注意到的细节",
            },
            "external": {
                "dialogue": "对白",
                "physical_action": "动作",
                "tone": "语气",
            },
            "held_back": "压下的内容",
        },
        extra_rules=MANUSCRIPT_JSON_RULES,
    )
    char_id = snapshot.identity.character_id
    char_name = snapshot.identity.name
    isolation_header = build_character_isolation_header(
        character_id=char_id,
        character_name=char_name,
        role_instruction=(
            "You are acting as this character in a scene. "
            "The scene transcript below shows what other characters said and did — "
            "but their internal thoughts are INVISIBLE to you."
        ),
    )
    # Build identity anchor - concise reminder of who this character is
    identity = snapshot.identity
    identity_anchor = (
        f"IDENTITY ANCHOR:\n"
        f"You are {char_name}. {identity.background}\n"
        f"Core drives: {', '.join(identity.desires[:3])}\n"
        f"Key values: {', '.join(identity.values[:3])}\n"
        f"Greatest fears: {', '.join(identity.fears[:2])}\n"
    )

    # --- Context anchor + delta pattern ---
    # Beat 0: send full context (anchor). Beats 1+: send only the delta
    # (transcript changes + last beat) with a compact state reminder.
    is_first_beat = beat_index == 0

    if is_first_beat:
        # Full context anchor — sent once per scene per character
        recent_events_block = ""
        if context_packet.recent_events:
            recent_events_block = (
                "WHAT HAS HAPPENED RECENTLY (chronological — this is your timeline):\n"
                + "\n".join(f"- {evt}" for evt in context_packet.recent_events)
                + "\n\n"
            )
        context_section = (
            f"WHO YOU ARE (full reference):\n{json.dumps(context_packet.identity, indent=1, sort_keys=True, ensure_ascii=False)}\n\n"
            "YOUR CURRENT STATE:\n"
            f"{json.dumps(context_packet.current_state, indent=1, sort_keys=True, ensure_ascii=False)}\n\n"
            f"{recent_events_block}"
            "WHAT YOU REMEMBER THAT'S RELEVANT:\n"
            f"{json.dumps(context_packet.working_memory, indent=1, ensure_ascii=False)}\n\n"
            "YOUR RELATIONSHIPS (your perception only):\n"
            f"{json.dumps(context_packet.relationship_context, indent=1, sort_keys=True, ensure_ascii=False)}\n\n"
            f"YOUR VOICE (speak like {char_name}, not anyone else):\n"
            f"{json.dumps(voice_samples, indent=1, ensure_ascii=False)}\n\n"
            "SCENE OPENING / TENSION:\n"
            f"{scene_setup.scene_opening}\n"
            f"Tension signature: {scene_setup.tension_signature}\n\n"
        )
        transcript_section = (
            "THE SCENE SO FAR (external actions only — you cannot see others' thoughts):\n"
            f"{json.dumps(perceived_transcript, indent=1, sort_keys=True, ensure_ascii=False)}\n\n"
        )
    else:
        # Delta-only context — compact reminder + only new transcript entries
        top_goal = snapshot.goals[0].description if snapshot.goals else "none"
        emotional = (
            snapshot.inferred_state.emotional_summary
            if snapshot.inferred_state
            else str(snapshot.current_state.get("emotional_state", ""))
        )
        context_section = (
            f"[Context anchor was provided in beat 0 — refer to your established identity, "
            f"memories, relationships, and world entities.]\n\n"
            f"STATE REMINDER: goal=\"{top_goal}\", emotion={emotional}\n\n"
        )
        # Only send the last few new transcript entries as delta
        # The character already saw earlier entries in previous beats
        new_entries = perceived_transcript[-(len(perceived_transcript) - max(0, beat_index - 1)):]
        if new_entries:
            transcript_section = (
                "NEW IN SCENE (since your last beat):\n"
                f"{json.dumps(new_entries, indent=1, sort_keys=True, ensure_ascii=False)}\n\n"
            )
        else:
            transcript_section = ""

    return PromptRequest(
        system=(
            f"Act as {char_name} (ID: {char_id}). "
            "Separate internal/external. No other character's voice or knowledge. JSON only.\n"
            "NATURALISM: Your traits inform your behavior subtly — do NOT perform them. "
            "A sarcastic person doesn't quip in every line. A fearful person doesn't "
            "mention their fear in every thought. Let traits emerge through choices "
            "and reactions naturally. Focus on what THIS SCENE demands — most traits "
            "stay dormant most of the time. Speak and act like a real person, not "
            "like a character sheet being read aloud."
        ),
        user=(
            f"{isolation_header}\n"
            f"{meta_block}"
            f"{language_block}"
            f"{identity_anchor}\n"
            f"{context_section}"
            f"{transcript_section}"
            "WHAT JUST HAPPENED (the last beat):\n"
            f"{json.dumps(last_beat, indent=1, sort_keys=True, ensure_ascii=False)}\n\n"
            f"As {char_name}, respond with internal thoughts, external action, and what is held back.\n\n"
            "OUTPUT CONTRACT:\n"
            f"{output_contract}"
        ),
        max_tokens=1_400,
        stream=False,
        metadata={
            "prompt_name": "p2_6_agent_beat",
            "character_id": char_id,
            "beat_index": beat_index,
        },
    )


def build_resolution_check_prompt(
    *,
    scene_transcript: List[Dict[str, object]],
    scene_setup: SceneSetupPayload,
    beat_count: int,
    max_beats: int,
    language_guidance: str = "",
    meta_section: str = "",
) -> PromptRequest:
    language_block = format_language_guidance_block(language_guidance)
    meta_block = _meta_block(meta_section)
    output_contract = build_json_contract(
        {"resolved": False, "resolution_type": "continue", "scene_outcome": "结果", "continue": True},
        extra_rules=MANUSCRIPT_JSON_RULES,
    )

    # Send a compact summary of early beats + full detail for recent beats
    # to avoid re-sending the entire transcript every resolution check.
    if len(scene_transcript) > 4:
        early_summary_lines = []
        for entry in scene_transcript[:-3]:
            agent = entry.get("agent_id", "?")
            ext = entry.get("external", {})
            action = ext.get("physical_action", "") if isinstance(ext, dict) else ""
            dialogue = ext.get("dialogue", "") if isinstance(ext, dict) else ""
            parts = [p for p in [action, dialogue] if p]
            early_summary_lines.append(f"  beat {entry.get('beat_index', '?')}: {agent} — {'; '.join(parts) or '(action)'}")
        early_summary = "EARLIER BEATS (summary):\n" + "\n".join(early_summary_lines) + "\n\n"
        recent_detail = json.dumps(scene_transcript[-3:], indent=1, sort_keys=True, ensure_ascii=False)
        transcript_block = f"{early_summary}RECENT BEATS (full detail):\n{recent_detail}\n\n"
    else:
        transcript_block = (
            "SCENE SO FAR:\n"
            f"{json.dumps(scene_transcript, indent=1, sort_keys=True, ensure_ascii=False)}\n\n"
        )

    return PromptRequest(
        system=(
            "You are the World Manager monitoring a scene. "
            "Decide whether a resolution condition has been met. Return JSON only."
        ),
        user=(
            f"{meta_block}"
            f"{transcript_block}"
            "RESOLUTION CONDITIONS:\n"
            f"{json.dumps(scene_setup.resolution_conditions.model_dump(mode='json'), indent=1, sort_keys=True, ensure_ascii=False)}\n\n"
            f"Beat {beat_count}/{max_beats}.\n"
            f"{build_casualty_constraint()}\n"
            "Has a resolution condition been met?\n"
            "`scene_outcome` must describe the concrete result that actually happened in this scene. "
            "Do not copy a hypothetical condition verbatim, and do not use conditional phrasing such as "
            "`if/when/or` or `若/如果/当/或` unless it appears inside dialogue.\n\n"
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
    meta_section: str = "",
) -> PromptRequest:
    language_block = format_language_guidance_block(language_guidance)
    meta_block = _meta_block(meta_section)
    output_contract = build_json_contract(
        {
            "emotional_delta": {
                "dominant_now": "主导情绪",
                "shift_reason": "变化原因",
            },
            "goal_stack_update": {
                "top_goal_status": "advanced",
                "top_goal_still_priority": True,
                "new_goal": None,
                "resolved_goal": None,
            },
            "relationship_updates": [
                {"target_id": "agent_b", "summary": "用自然语言描述关系的当前状态和变化", "pinned": False, "pin_reason": ""}
            ],
            "needs_reprojection": False,
            "reprojection_reason": "",
        },
        extra_rules=MANUSCRIPT_JSON_RULES,
    )
    char_id = snapshot.identity.character_id
    char_name = snapshot.identity.name
    isolation_header = build_character_isolation_header(
        character_id=char_id,
        character_name=char_name,
        role_instruction=(
            "You are updating ONLY this character's internal state after an event. "
            "The event description may mention other characters — update only "
            f"{char_name}'s reaction, not theirs."
        ),
    )
    return PromptRequest(
        system=(
            f"You are updating {char_name} (ID: {char_id}) after an event. "
            "Return emotional delta, goal stack update, relationship updates, "
            "and reprojection decision as JSON. Do NOT update any other character."
        ),
        user=(
            f"{isolation_header}\n"
            f"{meta_block}"
            f"{language_block}"
            "CORE IDENTITY (brief):\n"
            f"Primary drives: {', '.join(snapshot.identity.desires)}\n"
            f"Key values: {', '.join(snapshot.identity.values)}\n"
            f"Personality: {snapshot.identity.personality_summary}\n\n"
            f"STATE BEFORE THE EVENT (for {char_name} only):\n"
            f"Emotional state: {snapshot.inferred_state.emotional_summary if snapshot.inferred_state else snapshot.current_state.get('emotional_state', '')}\n"
            f"Active goal: {snapshot.goals[0].description if snapshot.goals else ''}\n"
            f"Fear: {', '.join(snapshot.identity.fears)}\n\n"
            f"WHAT JUST HAPPENED (from {char_name}'s perspective):\n"
            f"{event_outcome_from_agent_perspective}\n\n"
            f"WHAT {char_name.upper()} NOW KNOWS:\n"
            f"{json.dumps(new_knowledge, indent=1, ensure_ascii=False)}\n\n"
            f"Update {char_name}'s emotional state, goal stack, relationships, "
            "and trajectory invalidation.\n\n"
            "OUTPUT CONTRACT:\n"
            f"{output_contract}"
        ),
        max_tokens=1_000,
        stream=False,
        metadata={
            "prompt_name": "p2_7_state_update",
            "response_schema": StateUpdatePayload.__name__,
            "character_id": char_id,
        },
    )


__all__ = [
    "build_agent_beat_prompt",
    "build_background_event_prompt",
    "build_resolution_check_prompt",
    "build_spotlight_setup_prompt",
    "build_state_update_prompt",
]
