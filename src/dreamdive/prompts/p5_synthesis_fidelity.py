"""
Fidelity-First Synthesis Prompts

Enforces TWO CRITICAL REQUIREMENTS:
1. SIMULATION FIDELITY: Follow simulated events exactly
2. STYLE TRANSFER: Match original author's writing style

The LLM's job is NOT to create new story - it's to RENDER simulation results
into prose that reads like the original author wrote it.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from dreamdive.context_salience import format_salience_aware_context
from dreamdive.enhanced_synthesis import (
    extract_synthesis_meta_context,
    format_synthesis_instructions,
)
from dreamdive.synthesis_fidelity import (
    SynthesisConstraints,
    build_grounded_event_summary,
    extract_style_template_from_meta,
    format_grounded_events_for_synthesis,
    format_style_template_for_synthesis,
)
from dreamdive.ingestion.models import MetaLayerRecord
from dreamdive.language_guidance import build_language_guidance, format_language_guidance_block
from dreamdive.meta_injection import format_meta_section
from dreamdive.schemas import PromptRequest
from dreamdive.user_config import UserMeta


def build_fidelity_first_synthesis_prompt(
    event_window: Any,
    novel_meta: MetaLayerRecord,
    user_meta: UserMeta,
    *,
    chapter_number: int | None = None,
    previous_chapter_summary: Optional[Any] = None,
    narrative_arc_unresolved_threads: Optional[List[str]] = None,
    author: str = "",
    recent_chapter_outputs: Optional[List[str]] = None,
    # NEW: Enhanced event information
    beat_details_by_event: Optional[Dict[str, List[Dict[str, Any]]]] = None,
    state_changes_by_event: Optional[Dict[str, List[Dict[str, Any]]]] = None,
    relationship_changes_by_event: Optional[Dict[str, List[Dict[str, Any]]]] = None,
) -> PromptRequest:
    """
    Build synthesis prompt with FIDELITY-FIRST approach.

    Key differences from standard synthesis:
    1. Events are presented with explicit mandatory facts
    2. Clear rules about what's allowed vs. forbidden
    3. Style examples guide HOW to write (not WHAT to write)
    4. Emphasis on RENDERING simulation, not INVENTING story

    Args:
        event_window: Window of simulated events
        novel_meta: Meta-layer with style information
        user_meta: User configuration
        chapter_number: Chapter number
        previous_chapter_summary: Summary of previous chapter
        narrative_arc_unresolved_threads: Open plot threads
        author: Author name
        recent_chapter_outputs: Recent chapters (for repetition checking)
        beat_details_by_event: Detailed beat info per event (dialogue, actions)
        state_changes_by_event: State changes per event
        relationship_changes_by_event: Relationship changes per event

    Returns:
        Prompt that enforces simulation fidelity while matching style
    """
    # Extract meta-layer as dict
    meta_dict = novel_meta.model_dump(mode="json") if hasattr(novel_meta, "model_dump") else novel_meta

    # Build grounded event summaries
    grounded_events = []
    for event in event_window.events:
        event_dict = event.model_dump(mode="json") if hasattr(event, "model_dump") else event
        event_id = event_dict.get("event_id", "")

        grounded = build_grounded_event_summary(
            event=event_dict,
            beat_details=beat_details_by_event.get(event_id) if beat_details_by_event else None,
            state_change_log=state_changes_by_event.get(event_id) if state_changes_by_event else None,
            relationship_changes=relationship_changes_by_event.get(event_id) if relationship_changes_by_event else None,
        )
        grounded_events.append(grounded)

    # Define synthesis constraints
    constraints = SynthesisConstraints(
        must_include_events=[
            e.event_id for e in grounded_events if e.salience >= 0.7
        ],
        forbidden_inventions=[
            "New plot events not in simulation",
            "Character actions contradicting simulation",
            "Dialogue not from simulation",
            "Outcomes different from simulation",
        ],
        mandatory_outcomes=[
            e.outcome_summary for e in grounded_events if e.outcome_summary
        ],
        allow_scene_expansion=True,  # Can add sensory details
        allow_internal_monologue_invention=True,  # Can invent thoughts (if consistent)
        allow_dialogue_paraphrasing=False,  # Must use exact dialogue from simulation
        allow_transitional_scenes=True,  # Can add brief transitions
    )

    # Format grounded events
    grounded_events_text = format_grounded_events_for_synthesis(
        grounded_events, constraints
    )

    # Extract style template
    sample_passages_raw = meta_dict.get("writing_style", {}).get("sample_passages", [])
    style_template = extract_style_template_from_meta(
        meta_layer=meta_dict,
        sample_passages=sample_passages_raw,
    )

    # Format style template
    style_template_text = format_style_template_for_synthesis(style_template)

    # Extract synthesis meta-context (for length, density, etc.)
    synthesis_meta = extract_synthesis_meta_context(meta_layer=meta_dict)
    synthesis_instructions = format_synthesis_instructions(
        meta_context=synthesis_meta,
        event_count=len(grounded_events),
    )

    # Standard components
    meta_section = format_meta_section(novel_meta=novel_meta, user_meta=user_meta)
    language_guidance = format_language_guidance_block(
        build_language_guidance(novel_meta)
    )

    # Previous chapter
    previous_summary_block = ""
    if previous_chapter_summary:
        previous_summary_block = (
            f"\n## PREVIOUS CHAPTER: Ch.{previous_chapter_summary.chapter_number}\n"
            f"{previous_chapter_summary.summary}\n"
        )

    # Unresolved threads
    threads_block = ""
    if narrative_arc_unresolved_threads:
        threads_block = "\n## OPEN NARRATIVE THREADS\n" + "\n".join(
            f"- {t}" for t in narrative_arc_unresolved_threads[:5]
        )

    # System prompt - emphasize RENDERING not INVENTING
    system_prompt = (
        "You are a PROSE RENDERER, not a story creator. "
        "Your job is to take canonical simulation events and render them into literary prose "
        "that matches the original author's style. "
        "\n\n"
        "Think of yourself as a cinematographer, not a screenwriter: "
        "- The screenplay (simulation events) is already written and CANNOT be changed "
        "- Your job is to film it beautifully in the style of the original work "
        "- Add cinematography (sensory details, rhythm, atmosphere) "
        "- But NEVER change the plot, outcomes, or character actions"
    )

    # User prompt
    user_prompt = (
        f"{meta_section}\n\n"
        f"{language_guidance}\n"
        f"**Author**: {author or 'Unknown'}\n"
        f"{previous_summary_block}\n"
        f"{threads_block}\n\n"
        "═══════════════════════════════════════════════════════════════\n\n"
        f"{grounded_events_text}\n\n"
        "═══════════════════════════════════════════════════════════════\n\n"
        f"{style_template_text}\n\n"
        "═══════════════════════════════════════════════════════════════\n\n"
        f"{synthesis_instructions}\n\n"
        "═══════════════════════════════════════════════════════════════\n\n"
        "## YOUR TASK\n\n"
        "Render the simulation events above into a full literary chapter.\n\n"
        "**Remember**:\n"
        "1. ✅ CONTENT comes from simulation (events, outcomes, dialogue, states)\n"
        "2. ✅ STYLE comes from original author (rhythm, tone, techniques)\n"
        "3. ❌ DO NOT invent new plot points\n"
        "4. ❌ DO NOT change simulation outcomes\n"
        "5. ✅ DO add sensory details, atmosphere, internal monologue (if consistent)\n"
        "6. ✅ DO match the original author's writing style\n\n"
        "**Quality check before writing**:\n"
        f"- [ ] Am I following ALL {len(grounded_events)} simulation events?\n"
        "- [ ] Am I using exact dialogue from simulation?\n"
        "- [ ] Am I preserving all mandatory facts?\n"
        "- [ ] Am I writing in the original author's style?\n"
        f"- [ ] Will this be ~{synthesis_meta.density_metrics.average_word_count} words?\n"
        "- [ ] Does every sentence sound like the original work?\n\n"
        "**Write now. Render the simulation. Match the style. Stay faithful to the facts.**"
    )

    return PromptRequest(
        system=system_prompt,
        user=user_prompt,
        max_tokens=8_000,
        stream=False,
        metadata={
            "prompt_name": "p5_fidelity_first_synthesis",
            "tick_range": event_window.tick_range,
            "event_count": len(grounded_events),
            "target_word_count": synthesis_meta.density_metrics.average_word_count,
            "mandatory_fact_count": sum(len(e.mandatory_facts) for e in grounded_events),
        },
    )


def build_synthesis_validation_prompt(
    chapter_text: str,
    grounded_events: List[Any],
    constraints: SynthesisConstraints,
) -> PromptRequest:
    """
    Validate that synthesis followed simulation events correctly.

    Use this to check fidelity after generation.
    """
    events_summary = "\n".join([
        f"- Event {i+1}: {e.description} → {e.outcome_summary}"
        for i, e in enumerate(grounded_events)
    ])

    mandatory_facts = []
    for event in grounded_events:
        for fact in event.mandatory_facts:
            if fact.is_mandatory:
                mandatory_facts.append(fact.fact_statement)

    facts_list = "\n".join([f"- {f}" for f in mandatory_facts])

    from dreamdive.prompts.common import build_source_language_policy
    language_policy = build_source_language_policy(chapter_text)

    system = (
        "You are a fidelity validator checking if generated prose follows simulation events."
    )

    user = (
        f"{language_policy}\n"
        "## SIMULATION EVENTS\n\n"
        f"{events_summary}\n\n"
        "## MANDATORY FACTS\n\n"
        f"{facts_list}\n\n"
        "## GENERATED CHAPTER\n\n"
        f"{chapter_text}\n\n"
        "---\n\n"
        "Check if the chapter:\n"
        "1. Includes all simulation events\n"
        "2. Preserves all mandatory facts\n"
        "3. Doesn't invent new plot points\n"
        "4. Doesn't contradict simulation outcomes\n\n"
        "Return JSON:\n"
        "```json\n"
        "{\n"
        "  \"fidelity_score\": 0.95,  // 0.0-1.0\n"
        "  \"missing_facts\": [\"被遗漏的事实\"],\n"
        "  \"contradictions\": [\"章节与模拟矛盾之处\"],\n"
        "  \"invented_content\": [\"模拟中不存在的情节\"],\n"
        "  \"overall_assessment\": \"简要评估\"\n"
        "}\n"
        "```"
    )

    return PromptRequest(
        system=system,
        user=user,
        max_tokens=500,
        stream=False,
        metadata={
            "prompt_name": "p5_synthesis_validation",
        },
    )


__all__ = [
    "build_fidelity_first_synthesis_prompt",
    "build_synthesis_validation_prompt",
]
