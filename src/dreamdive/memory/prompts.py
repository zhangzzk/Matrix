from __future__ import annotations

import json
from typing import Dict, List

from dreamdive.language_guidance import format_language_guidance_block
from dreamdive.schemas import (
    EpisodicMemory,
    MemoryCompressionPayload,
    NarrativeArcState,
    NarrativeArcUpdatePayload,
    PromptRequest,
)


def _json_contract(example: dict) -> str:
    return (
        "Return exactly one JSON object using these exact keys.\n"
        "Do not rename keys, do not add extra keys, and do not wrap the JSON in markdown fences.\n"
        "Keep every string concise and concrete.\n"
        f"{json.dumps(example, indent=2, ensure_ascii=False, sort_keys=True)}\n\n"
    )


def build_memory_compression_prompt(
    *,
    character_name: str,
    primary_drive: str,
    values: List[str],
    top_concerns: List[str],
    episodic_entries: List[EpisodicMemory],
    pinned_entries: List[EpisodicMemory],
    age_threshold: int,
    high_salience_threshold: float,
    discard_threshold: float,
    language_guidance: str = "",
) -> PromptRequest:
    serializable_entries = [
        {
            "tick": memory.replay_key.tick,
            "event_id": memory.event_id,
            "participants": memory.participants,
            "location": memory.location,
            "summary": memory.summary,
            "emotional_tag": memory.emotional_tag,
            "salience": memory.salience,
        }
        for memory in episodic_entries
    ]
    serializable_pinned = [
        {
            "tick": memory.replay_key.tick,
            "event_id": memory.event_id,
            "summary": memory.summary,
            "emotional_tag": memory.emotional_tag,
            "salience": memory.salience,
            "pinned": memory.pinned,
        }
        for memory in pinned_entries
    ]
    language_block = format_language_guidance_block(language_guidance)
    return PromptRequest(
        system=(
            "You are managing the long-term memory of a character in a story simulation. "
            "Compress old episodic memories without losing what matters. Return valid JSON only."
        ),
        user=(
            f"{language_block}"
            f"CHARACTER: {character_name}\n\n"
            "CORE IDENTITY (brief):\n"
            f"Primary drive: {primary_drive}\n"
            f"Key values: {json.dumps(values, ensure_ascii=False)}\n"
            f"What they care most about: {json.dumps(top_concerns, ensure_ascii=False)}\n\n"
            f"EPISODIC BUFFER (entries older than {age_threshold} ticks):\n"
            f"{json.dumps(serializable_entries, indent=2, sort_keys=True, ensure_ascii=False)}\n\n"
            "PINNED ENTRIES (do not touch these):\n"
            f"{json.dumps(serializable_pinned, indent=2, sort_keys=True, ensure_ascii=False)}\n\n"
            "Preserve high-salience, relationship-turning-point, promise/betrayal/revelation, "
            "or goal-changing entries at full detail. Compress clusters of lower-salience entries into "
            "semantic summaries. Discard pure filler.\n\n"
            f"High salience threshold: {high_salience_threshold}\n"
            f"Discard threshold: {discard_threshold}\n"
        ),
        max_tokens=1_800,
        metadata={
            "prompt_name": "p3_1_memory_compression",
            "response_schema": MemoryCompressionPayload.__name__,
        },
    )


def build_arc_update_prompt(
    *,
    story_context: str,
    authorial_intent: str,
    central_tension: str,
    current_arc_state: NarrativeArcState,
    ticks_elapsed: int,
    recent_event_log: List[Dict[str, object]],
    agent_state_summary: List[Dict[str, object]],
    horizon: int = 5,
    language_guidance: str = "",
) -> PromptRequest:
    language_block = format_language_guidance_block(language_guidance)
    output_contract = _json_contract(
        {
            "phase": "rising_action",
            "phase_changed": False,
            "phase_change_reason": "Why the phase did or did not change",
            "tension_level": 0.62,
            "tension_delta": 0.07,
            "tension_reason": "What changed the dramatic pressure",
            "unresolved_threads": [
                {
                    "thread_id": "thread_001",
                    "description": "One concise unresolved thread",
                    "agents_involved": ["agent_a"],
                    "urgency": "medium",
                    "resolution_condition": "What would resolve this thread",
                }
            ],
            "approaching_nodes": [
                {
                    "description": "One upcoming dramatic node",
                    "agents_involved": ["agent_a", "agent_b"],
                    "estimated_ticks_away": 2,
                    "estimated_salience": 0.8,
                }
            ],
            "narrative_drift": {
                "drifting": False,
                "drift_description": "",
                "suggested_correction": "",
            },
        }
    )
    return PromptRequest(
        system=(
            "You are the narrative tracker for a story simulation. "
            "Assess the current dramatic arc and update the tension model. Return valid JSON only."
        ),
        user=(
            f"{language_block}"
            "STORY CONTEXT:\n"
            f"Title / setting: {story_context}\n"
            f"Authorial intent: {authorial_intent}\n"
            f"Central tension: {central_tension}\n\n"
            "CURRENT NARRATIVE ARC STATE:\n"
            f"Phase: {current_arc_state.current_phase}\n"
            f"Tension level: {current_arc_state.tension_level}\n"
            f"Unresolved threads: {json.dumps(current_arc_state.unresolved_threads, ensure_ascii=False)}\n"
            f"Ticks since last update: {ticks_elapsed}\n\n"
            "RECENT EVENTS:\n"
            f"{json.dumps(recent_event_log, indent=2, sort_keys=True, ensure_ascii=False)}\n\n"
            "ACTIVE AGENT STATES (compressed):\n"
            f"{json.dumps(agent_state_summary, indent=2, sort_keys=True, ensure_ascii=False)}\n\n"
            f"Assess phase, tension, unresolved threads, approaching nodes within the next {horizon} ticks, "
            "and whether the story is drifting from authorial intent.\n\n"
            "Use descriptive thread text in `description`; do not use opaque slug-style English labels as the only human-readable output.\n\n"
            "OUTPUT CONTRACT:\n"
            f"{output_contract}"
        ),
        max_tokens=2_000,
        stream=False,
        metadata={
            "prompt_name": "p3_2_narrative_arc_update",
            "response_schema": NarrativeArcUpdatePayload.__name__,
        },
    )
