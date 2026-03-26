from __future__ import annotations

import json
from typing import Any, List, Optional, Protocol

from dreamdive.ingestion.models import MetaLayerRecord
from dreamdive.language_guidance import build_language_guidance, format_language_guidance_block
from dreamdive.meta_injection import format_meta_section
from dreamdive.schemas import PromptRequest
from dreamdive.user_config import UserMeta


class _EventWindowLike(Protocol):
    tick_range: str
    events: List[Any]
    high_salience_events: List[str]


class _ChapterSummaryLike(Protocol):
    chapter_number: int
    summary: str


class _CharacterStateLike(Protocol):
    name: str
    location: str
    emotional_state: str
    active_goals: List[str]


def build_chapter_synthesis_prompt(
    event_window: _EventWindowLike,
    novel_meta: MetaLayerRecord,
    user_meta: UserMeta,
    *,
    chapter_number: int | None = None,
    previous_chapter_summary: Optional[_ChapterSummaryLike] = None,
    narrative_arc_unresolved_threads: Optional[List[str]] = None,
    character_states: Optional[List[_CharacterStateLike]] = None,
    author: str = "",
    voice_samples: Optional[List[str]] = None,
    source_heading_examples: Optional[List[str]] = None,
) -> PromptRequest:
    """P5.1: Synthesize simulation events into a novel chapter."""
    meta_section = format_meta_section(novel_meta=novel_meta, user_meta=user_meta)
    language_guidance = format_language_guidance_block(
        build_language_guidance(novel_meta)
    )

    voice_block = ""
    if voice_samples:
        voice_block = "\nVOICE SAMPLES:\n" + "\n\n".join(
            f"[{i + 1}] {s}" for i, s in enumerate(voice_samples[:3])
        )

    previous_summary_block = ""
    if previous_chapter_summary:
        previous_summary_block = (
            f"\nPREVIOUS CHAPTER: Ch.{previous_chapter_summary.chapter_number}: "
            f"{previous_chapter_summary.summary}\n"
        )

    threads_block = ""
    if narrative_arc_unresolved_threads:
        threads_block = "\nOPEN THREADS:\n" + "\n".join(
            f"- {t}" for t in narrative_arc_unresolved_threads[:5]
        )

    format_lines: List[str] = []
    learned_chapter_format = novel_meta.writing_style.chapter_format
    effective_heading_examples = list(source_heading_examples or [])
    if not effective_heading_examples and learned_chapter_format.heading_examples:
        effective_heading_examples = list(learned_chapter_format.heading_examples)
    chapter_architecture = (
        novel_meta.design_tendencies.story_architecture.chapter_architecture
    )
    if chapter_architecture:
        format_lines.append(f"- Learned chapter architecture: {chapter_architecture}")
    if novel_meta.writing_style.sentence_rhythm:
        format_lines.append(
            f"- Learned sentence rhythm: {novel_meta.writing_style.sentence_rhythm}"
        )
    if novel_meta.writing_style.dialogue_narration_balance:
        format_lines.append(
            "- Learned dialogue/narration balance: "
            f"{novel_meta.writing_style.dialogue_narration_balance}"
        )
    if learned_chapter_format.heading_style:
        format_lines.append(
            f"- Learned heading style: {learned_chapter_format.heading_style}"
        )
    if learned_chapter_format.opening_pattern:
        format_lines.append(
            f"- Learned chapter opening pattern: {learned_chapter_format.opening_pattern}"
        )
    if learned_chapter_format.closing_pattern:
        format_lines.append(
            f"- Learned chapter closing pattern: {learned_chapter_format.closing_pattern}"
        )
    if learned_chapter_format.paragraphing_style:
        format_lines.append(
            f"- Learned paragraphing style: {learned_chapter_format.paragraphing_style}"
        )
    if effective_heading_examples:
        example_lines = "\n".join(
            f"  - {example}" for example in effective_heading_examples[:4]
        )
        format_lines.append(
            "Source chapter heading examples:\n"
            f"{example_lines}"
        )
        if chapter_number is not None and user_meta.chapter_format.chapter_structure == "match_original":
            format_lines.append(
                "- Start with a heading line for this chapter that matches the original format. "
                f"This is chapter {chapter_number}. If the source uses titled headings, invent a fitting title."
            )
            format_lines.append(
                "- After the heading line, leave one blank line, then continue with prose."
            )

    format_block = ""
    if format_lines:
        format_block = "\nCHAPTER FORMAT:\n" + "\n".join(format_lines) + "\n"

    # Build character state summary for the synthesis LLM
    character_states_block = ""
    if character_states:
        state_lines = []
        for cs in character_states:
            goals_str = "; ".join(cs.active_goals[:3]) if cs.active_goals else "none"
            state_lines.append(
                f"- {cs.name}: location={cs.location}, "
                f"emotional_state={cs.emotional_state}, "
                f"goals=[{goals_str}]"
            )
        character_states_block = (
            "\nCHARACTER STATES AT CHAPTER START:\n"
            + "\n".join(state_lines) + "\n"
        )

    events_json = json.dumps(
        [event.model_dump(mode="json") for event in event_window.events],
        indent=2,
        ensure_ascii=False,
    )

    high_salience_note = ""
    if event_window.high_salience_events:
        high_salience_note = (
            f"\nMust-include events: {', '.join(event_window.high_salience_events)}\n"
        )

    system_prompt = (
        "Write the next chapter of a novel from simulation events. "
        "Author's voice, not summary. Output chapter text only. No markdown, no commentary."
    )

    user_prompt = (
        f"{meta_section}\n"
        f"{language_guidance}"
        f"Author: {author or 'Unknown'}\n"
        f"{voice_block}\n"
        f"{previous_summary_block}"
        f"{character_states_block}"
        f"{threads_block}\n"
        f"{format_block}"
        f"EVENTS (tick range: {event_window.tick_range})\n"
        f"{high_salience_note}"
        "These event records are canonical. You may compress low-salience beats, "
        "but do not contradict outcomes, erase state changes, or reverse causality.\n"
        "Weave the selected events into one coherent chapter while preserving the simulated plot.\n\n"
        f"{events_json}\n\n"
        f"REQUIREMENTS:\n"
        f"- ~{user_meta.chapter_format.target_word_count} words\n"
        f"- POV: {user_meta.chapter_format.pov_style}\n"
        f"- Emphasize: {', '.join(user_meta.emphasis.primary) if user_meta.emphasis.primary else 'balanced'}\n"
        f"- Focus: {', '.join(user_meta.focus_characters) if user_meta.focus_characters else 'even'}\n\n"
        "- High-salience events must appear on-page.\n"
        "- Preserve key emotional and state transitions implied by the event records.\n\n"
        "CONTINUITY RULES:\n"
        "- Do not repeat events from the previous chapter. Move the story forward.\n"
        "- Each character's emotional arc must progress — they should not reset to the same state.\n"
        "- Reference earlier events through character memory and reaction, not re-narration.\n"
        "- Ensure clear cause-and-effect between scenes. The reader should understand WHY events happen.\n"
        "- Characters should feel like natural people, not walking personality checklists. "
        "Not every scene needs to showcase every trait. Let characterization emerge "
        "through action and dialogue, not through explicit internal narration of traits.\n\n"
        "Write now. Author's voice. Every sentence must feel like the original."
    )

    return PromptRequest(
        system=system_prompt,
        user=user_prompt,
        max_tokens=6_000,
        stream=False,
        metadata={
            "prompt_name": "p5_1_chapter_synthesis",
            "tick_range": event_window.tick_range,
            "event_count": len(event_window.events),
        },
    )


def build_chapter_summary_prompt(chapter_text: str) -> PromptRequest:
    """P5.2: Summarize a written chapter for continuity."""
    from dreamdive.prompts.common import build_source_language_policy
    language_policy = build_source_language_policy(chapter_text)
    return PromptRequest(
        system=(
            "You are summarizing a novel chapter for continuity tracking. "
            "The next chapter's author will use this summary to maintain continuity. "
            "Be precise about character states, relationships, and plot progression. "
            "Do not editorialize. Just the facts of the narrative. "
            "Keep it to 200-300 words."
        ),
        user=(
            "Summarize the following chapter:\n\n"
            f"{chapter_text}\n\n"
            "Return a 200-300 word summary covering:\n"
            "- What happened (key events in order)\n"
            "- Who was affected and how\n"
            "- Character states at chapter end (where they are, how they feel, what they now know)\n"
            "- Key decisions made by characters\n"
            "- Relationships that changed (and how)\n"
            "- What threads are now open or closed\n"
            "- What the next logical story progression would be (what needs to happen next)\n\n"
            f"{language_policy}"
        ),
        max_tokens=600,
        stream=False,
        metadata={
            "prompt_name": "p5_2_chapter_summary",
        },
    )


def build_unified_synthesis_prompt(
    event_window: _EventWindowLike,
    novel_meta: MetaLayerRecord,
    user_meta: UserMeta,
    *,
    chapter_number: int | None = None,
    previous_chapter_summary: Optional[_ChapterSummaryLike] = None,
    narrative_arc_unresolved_threads: Optional[List[str]] = None,
    character_states: Optional[List[_CharacterStateLike]] = None,
    author: str = "",
    voice_samples: Optional[List[str]] = None,
    source_heading_examples: Optional[List[str]] = None,
) -> PromptRequest:
    """P5.3: Synthesize simulation events into a novel chapter AND produce a
    continuity summary in a single LLM call.

    The LLM is asked to return JSON with two keys:
    - ``chapter_text``: the full chapter prose
    - ``summary``: a 200-300 word continuity summary
    """
    # Re-use the existing synthesis prompt builder for the heavy lifting.
    base = build_chapter_synthesis_prompt(
        event_window=event_window,
        novel_meta=novel_meta,
        user_meta=user_meta,
        chapter_number=chapter_number,
        previous_chapter_summary=previous_chapter_summary,
        narrative_arc_unresolved_threads=narrative_arc_unresolved_threads,
        character_states=character_states,
        author=author,
        voice_samples=voice_samples,
        source_heading_examples=source_heading_examples,
    )

    # Extend the system prompt to also request a summary.
    system_prompt = (
        "Write the next chapter of a novel from simulation events AND produce a "
        "continuity summary. Author's voice, not summary, for the chapter text. "
        "Return ONLY valid JSON with exactly two keys:\n"
        '  "chapter_text": the full chapter prose (no markdown, no commentary)\n'
        '  "summary": a 200-300 word factual continuity summary covering key events, '
        "character states at chapter end, decisions made, relationship changes, "
        "open/closed threads, and what the next logical story progression would be."
    )

    # Append summary instructions to the user prompt.
    user_prompt = (
        base.user + "\n\n"
        "ADDITIONAL INSTRUCTION:\n"
        "After writing the chapter, also produce a concise 200-300 word continuity "
        "summary of the chapter you just wrote. The summary should cover:\n"
        "- What happened (key events in order)\n"
        "- Who was affected and how\n"
        "- Character states at chapter end\n"
        "- Key decisions made\n"
        "- Relationship changes\n"
        "- Open/closed threads\n"
        "- Next logical story progression\n\n"
        "Return your response as JSON with two keys: "
        '"chapter_text" and "summary".'
    )

    return PromptRequest(
        system=system_prompt,
        user=user_prompt,
        max_tokens=7_000,
        stream=False,
        metadata={
            "prompt_name": "p5_3_unified_synthesis",
            "tick_range": event_window.tick_range,
            "event_count": len(event_window.events),
        },
    )


__all__ = [
    "build_chapter_summary_prompt",
    "build_chapter_synthesis_prompt",
    "build_unified_synthesis_prompt",
]
