"""
Enhanced P5 Synthesis Prompts

Addresses issues with:
1. Repetitive signature phrases
2. Insufficient chapter length/density
3. Missing poetic chapter titles
4. Poor timescale and pacing

New features:
- Salience-aware context with frequency guidance
- Meta-layer density metrics
- Chapter titling instructions
- Explicit pacing and structure requirements
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from dreamdive.context_salience import (
    ContextElement,
    CharacterContextPacket,
    format_salience_aware_context,
    COMMON_SIGNATURE_GUIDANCE,
)
from dreamdive.enhanced_synthesis import (
    SynthesisMetaContext,
    extract_synthesis_meta_context,
    format_synthesis_instructions,
)
from dreamdive.ingestion.models import MetaLayerRecord
from dreamdive.language_guidance import build_language_guidance, format_language_guidance_block
from dreamdive.meta_injection import format_meta_section
from dreamdive.schemas import PromptRequest
from dreamdive.user_config import UserMeta


def build_enhanced_chapter_synthesis_prompt(
    event_window: Any,
    novel_meta: MetaLayerRecord,
    user_meta: UserMeta,
    *,
    chapter_number: int | None = None,
    previous_chapter_summary: Optional[Any] = None,
    narrative_arc_unresolved_threads: Optional[List[str]] = None,
    author: str = "",
    voice_samples: Optional[List[str]] = None,
    source_heading_examples: Optional[List[str]] = None,
    recent_chapter_outputs: Optional[List[str]] = None,
) -> PromptRequest:
    """
    Enhanced P5.1: Synthesize simulation events into a novel chapter.

    New features:
    - Salience-aware context with signature phrase warnings
    - Meta-layer density and pacing guidance
    - Chapter title generation instructions
    - Explicit length and development requirements
    """
    # Extract meta-layer as dict
    meta_dict = novel_meta.model_dump(mode="json") if hasattr(novel_meta, "model_dump") else novel_meta

    # Build synthesis meta-context
    synthesis_meta = extract_synthesis_meta_context(
        meta_layer=meta_dict,
        sample_chapters=None,  # TODO: pass actual sample chapters if available
    )

    # Format synthesis instructions
    synthesis_instructions = format_synthesis_instructions(
        meta_context=synthesis_meta,
        event_count=len(event_window.events),
    )

    # Build signature phrase awareness
    signature_awareness = build_signature_phrase_awareness(
        meta_dict, recent_chapter_outputs
    )

    # Standard meta section
    meta_section = format_meta_section(novel_meta=novel_meta, user_meta=user_meta)
    language_guidance = format_language_guidance_block(
        build_language_guidance(novel_meta)
    )

    # Voice samples
    voice_block = ""
    if voice_samples:
        voice_block = "\n## VOICE SAMPLES (study the style, don't copy literally)\n" + "\n\n".join(
            f"[{i + 1}] {s}" for i, s in enumerate(voice_samples[:3])
        )

    # Previous chapter continuity
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

    # Events
    events_json = json.dumps(
        [event.model_dump(mode="json") for event in event_window.events],
        indent=2,
        ensure_ascii=False,
    )

    high_salience_note = ""
    if event_window.high_salience_events:
        high_salience_note = (
            f"\n**Must-include events (high salience)**: {', '.join(event_window.high_salience_events)}\n"
        )

    # System prompt
    system_prompt = (
        "You are a novelist writing a full literary chapter from simulation events. "
        "This is NOT a summary or synopsis - it's a complete chapter matching the source material's "
        "length, depth, and style. Every sentence must feel like the original author wrote it."
    )

    # User prompt
    user_prompt = (
        f"{meta_section}\n\n"
        f"{language_guidance}\n"
        f"**Author**: {author or 'Unknown'}\n"
        f"{voice_block}\n"
        f"{previous_summary_block}\n"
        f"{threads_block}\n\n"
        "---\n\n"
        f"{synthesis_instructions}\n\n"
        "---\n\n"
        f"{signature_awareness}\n\n"
        "---\n\n"
        f"## SIMULATION EVENTS (tick range: {event_window.tick_range})\n\n"
        f"{high_salience_note}\n"
        "These event records are canonical facts. Weave them into a coherent narrative.\n"
        "- Do NOT list events as bullet points\n"
        "- Do NOT summarize - DRAMATIZE each event as a full scene\n"
        "- Preserve all state changes and outcomes\n"
        "- You may compress trivial beats, but high-salience events must appear on-page\n\n"
        f"```json\n{events_json}\n```\n\n"
        "---\n\n"
        "## FINAL CHECKLIST BEFORE YOU WRITE\n\n"
        f"- [ ] Will output be ~{synthesis_meta.density_metrics.average_word_count} words? (NOT a brief summary)\n"
        f"- [ ] Does opening match source style? ({synthesis_meta.pacing_guidance.scene_opening_style})\n"
        "- [ ] Am I SHOWING scenes, not TELLING summaries?\n"
        "- [ ] Are signature phrases used SPARINGLY (not in every paragraph)?\n"
        f"- [ ] Does it have a proper chapter title? ({synthesis_meta.titling_style.style_type})\n"
        "- [ ] Does every sentence sound like the original author?\n\n"
        "**Write now. Full chapter. Author's voice. Make it feel real.**"
    )

    return PromptRequest(
        system=system_prompt,
        user=user_prompt,
        max_tokens=8_000,  # Increased for longer chapters
        stream=False,
        metadata={
            "prompt_name": "p5_1_enhanced_chapter_synthesis",
            "tick_range": event_window.tick_range,
            "event_count": len(event_window.events),
            "target_word_count": synthesis_meta.density_metrics.average_word_count,
        },
    )


def build_signature_phrase_awareness(
    meta_layer: Dict[str, Any],
    recent_outputs: Optional[List[str]] = None,
) -> str:
    """
    Build a warning section about signature phrase overuse.
    """
    lines = ["## ⚠️ SIGNATURE PHRASE USAGE GUIDANCE", ""]

    # Extract signature moves
    signature_moves = meta_layer.get("authors_taste", {}).get("signature_moves", [])

    if not signature_moves:
        return ""

    lines.append(
        "The following are signature stylistic elements. They are POWERFUL when used sparingly. "
        "OVERUSE will make the writing feel repetitive and artificial."
    )
    lines.append("")

    # Check for known problematic phrases
    for phrase_key, guidance in COMMON_SIGNATURE_GUIDANCE.items():
        if any(phrase_key in move for move in signature_moves):
            lines.append(f"### {phrase_key}")
            lines.append(f"- **Usage frequency**: {guidance.usage_frequency.value.upper()}")
            lines.append(f"- **Guidance**: {guidance.usage_guidance}")
            if guidance.avoid_patterns:
                lines.append(f"- **Avoid**: {', '.join(guidance.avoid_patterns)}")

            # Check recent usage
            if recent_outputs:
                count = sum(1 for output in recent_outputs if phrase_key in output)
                if count > 0:
                    lines.append(
                        f"- **⚠️ WARNING**: This phrase was used {count} time(s) in recent chapters. "
                        "DO NOT REPEAT unless absolutely essential."
                    )
            lines.append("")

    # Generic guidance for other signatures
    lines.append("### Other Signature Elements")
    for move in signature_moves[:5]:  # Show first 5
        if not any(key in move for key in COMMON_SIGNATURE_GUIDANCE.keys()):
            lines.append(f"- {move}")
            lines.append("  _Use sparingly for maximum impact_")

    lines.append("")
    lines.append(
        "**CRITICAL**: If you find yourself using a signature phrase, ask: "
        "'Is this THE perfect moment for it, or am I using it as filler?' "
        "Save signatures for moments of maximum dramatic impact."
    )

    return "\n".join(lines)


def build_chapter_title_generation_prompt(
    chapter_number: int,
    chapter_summary: str,
    titling_style: Dict[str, Any],
    meta_layer: Dict[str, Any],
) -> PromptRequest:
    """
    Separate prompt to generate poetic chapter titles.

    Use this if you want to generate titles separately from chapter content.
    """
    examples = titling_style.get("title_examples", [])
    pattern = titling_style.get("title_pattern_description", "")
    guidance = titling_style.get("title_generation_guidance", "")

    examples_block = ""
    if examples:
        examples_block = "## Example Titles from Source Material\n" + "\n".join(
            f"- {ex}" for ex in examples
        )

    from dreamdive.prompts.common import build_source_language_policy
    language_policy = build_source_language_policy(chapter_summary)

    system = (
        "You are a literary editor creating chapter titles in the exact style of the source material."
    )

    user = (
        f"Create a chapter title for Chapter {chapter_number}.\n\n"
        f"## Chapter Summary\n{chapter_summary}\n\n"
        f"{examples_block}\n\n"
        f"## Titling Style\n{pattern}\n\n"
        f"## Guidance\n{guidance}\n\n"
        "Generate ONE title that:\n"
        "- Matches the style and length of the examples\n"
        "- Captures the essence of this chapter\n"
        "- Feels like it could be from the original work\n\n"
        "Output the title ONLY, no explanation.\n\n"
        f"{language_policy}"
    )

    return PromptRequest(
        system=system,
        user=user,
        max_tokens=100,
        stream=False,
        metadata={
            "prompt_name": "p5_title_generation",
            "chapter_number": chapter_number,
        },
    )


__all__ = [
    "build_enhanced_chapter_synthesis_prompt",
    "build_chapter_title_generation_prompt",
    "build_signature_phrase_awareness",
]
