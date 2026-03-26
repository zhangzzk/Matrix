"""
Enhanced Chapter Synthesis System

Addresses issues with:
1. Insufficient content density
2. Missing poetic chapter titles
3. Incorrect timescale and pacing
4. Lack of meta-layer awareness

This system makes agents aware of:
- Original chapter length and density
- Chapter titling style and poetics
- Pacing and scene development patterns
- Structural expectations from meta-layer
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ChapterDensityMetrics(BaseModel):
    """
    Metrics derived from original chapters to guide synthesis density.
    """
    average_word_count: int = Field(
        description="Average words per chapter in source material"
    )
    average_scene_count: int = Field(
        default=3,
        description="Average number of distinct scenes per chapter"
    )
    average_event_count: int = Field(
        default=5,
        description="Average number of plot events per chapter"
    )
    dialogue_to_narration_ratio: float = Field(
        default=0.3,
        description="Ratio of dialogue to narration (0.3 = 30% dialogue)"
    )
    description_density: str = Field(
        default="moderate",
        description="low | moderate | high - how much sensory/environmental detail"
    )
    internal_monologue_frequency: str = Field(
        default="frequent",
        description="rare | occasional | frequent | constant"
    )


class ChapterTitlingStyle(BaseModel):
    """
    Patterns for generating chapter titles that match source material.
    """
    style_type: str = Field(
        description="numbered_only | simple_descriptive | poetic | symbolic | mixed"
    )
    title_length: str = Field(
        default="short",
        description="short (1-5 chars) | medium (6-15 chars) | long (15+ chars)"
    )
    title_examples: List[str] = Field(
        default_factory=list,
        description="Actual titles from source material"
    )
    title_pattern_description: str = Field(
        default="",
        description="Pattern description (e.g., 'Uses classical Chinese poetry references')"
    )
    title_generation_guidance: str = Field(
        default="",
        description="How to create fitting titles for new chapters"
    )


class PacingGuidance(BaseModel):
    """
    Guidance on scene pacing and development.
    """
    scene_opening_style: str = Field(
        default="",
        description="How scenes typically open (e.g., 'Immediate action', 'Atmospheric description')"
    )
    scene_closing_style: str = Field(
        default="",
        description="How scenes typically close (e.g., 'Cliffhanger', 'Reflection')"
    )
    time_dilation_tendency: str = Field(
        default="moderate",
        description="low | moderate | high - how much author slows time for key moments"
    )
    scene_transition_method: str = Field(
        default="",
        description="How author transitions between scenes (e.g., 'Hard cuts', 'Flowing transitions')"
    )
    climax_building_pattern: str = Field(
        default="",
        description="How tension builds to chapter climax"
    )


class SynthesisMetaContext(BaseModel):
    """
    Complete meta-context for chapter synthesis.
    Extracted from MetaLayerRecord and original material analysis.
    """
    density_metrics: ChapterDensityMetrics
    titling_style: ChapterTitlingStyle
    pacing_guidance: PacingGuidance

    # Author-specific guidance
    sentence_rhythm_guidance: str = Field(
        default="",
        description="From meta-layer: how sentences should flow"
    )
    paragraphing_guidance: str = Field(
        default="",
        description="From meta-layer: paragraph structure"
    )
    tone_guidance: str = Field(
        default="",
        description="From meta-layer: dominant tone to maintain"
    )


def extract_synthesis_meta_context(
    meta_layer: Dict[str, Any],
    sample_chapters: Optional[List[Dict[str, Any]]] = None,
) -> SynthesisMetaContext:
    """
    Extract synthesis guidance from meta-layer and sample chapters.

    Args:
        meta_layer: MetaLayerRecord dict
        sample_chapters: Optional list of sample chapters with word counts

    Returns:
        Meta-context for synthesis
    """
    # Extract density metrics
    avg_word_count = 3000  # Default
    if sample_chapters:
        word_counts = [ch.get("word_count", 3000) for ch in sample_chapters]
        avg_word_count = int(sum(word_counts) / len(word_counts))

    description_density_raw = meta_layer.get("writing_style", {}).get(
        "description_density", ""
    )
    density_level = "moderate"
    if "sparse" in description_density_raw.lower() or "minimal" in description_density_raw.lower():
        density_level = "low"
    elif "rich" in description_density_raw.lower() or "dense" in description_density_raw.lower():
        density_level = "high"

    density_metrics = ChapterDensityMetrics(
        average_word_count=avg_word_count,
        description_density=density_level,
        dialogue_to_narration_ratio=extract_dialogue_ratio(meta_layer),
        internal_monologue_frequency=extract_monologue_frequency(meta_layer),
    )

    # Extract titling style
    chapter_format = meta_layer.get("writing_style", {}).get("chapter_format", {})
    heading_style = chapter_format.get("heading_style", "")
    heading_examples = chapter_format.get("heading_examples", [])

    # Determine style type
    style_type = "numbered_only"
    if heading_examples:
        first_example = heading_examples[0]
        if any(c.isalpha() or ord(c) > 127 for c in first_example):
            # Has letters/characters, not just numbers
            if len(first_example) > 15:
                style_type = "poetic"
            elif any(keyword in first_example.lower() for keyword in ["chapter", "第", "幕", "回"]):
                style_type = "simple_descriptive"
            else:
                style_type = "symbolic"

    title_length = "short"
    if heading_examples:
        avg_len = sum(len(ex) for ex in heading_examples) / len(heading_examples)
        if avg_len > 15:
            title_length = "long"
        elif avg_len > 5:
            title_length = "medium"

    titling_style = ChapterTitlingStyle(
        style_type=style_type,
        title_length=title_length,
        title_examples=heading_examples[:5],
        title_pattern_description=heading_style,
        title_generation_guidance=generate_titling_guidance(
            style_type, heading_examples
        ),
    )

    # Extract pacing guidance
    story_arch = meta_layer.get("design_tendencies", {}).get("story_architecture", {})
    pacing_guidance = PacingGuidance(
        scene_opening_style=chapter_format.get("opening_pattern", ""),
        scene_closing_style=chapter_format.get("closing_pattern", ""),
        scene_transition_method=story_arch.get("time_management", ""),
        climax_building_pattern=story_arch.get("foreshadowing_method", ""),
    )

    # Extract author-specific guidance
    writing_style = meta_layer.get("writing_style", {})
    sentence_rhythm = writing_style.get("sentence_rhythm", "")
    paragraphing = chapter_format.get("paragraphing_style", "")
    tone = meta_layer.get("tone_and_register", {}).get("dominant_register", "")

    return SynthesisMetaContext(
        density_metrics=density_metrics,
        titling_style=titling_style,
        pacing_guidance=pacing_guidance,
        sentence_rhythm_guidance=sentence_rhythm,
        paragraphing_guidance=paragraphing,
        tone_guidance=tone,
    )


def extract_dialogue_ratio(meta_layer: Dict[str, Any]) -> float:
    """Extract dialogue to narration ratio from meta-layer."""
    balance = meta_layer.get("writing_style", {}).get("dialogue_narration_balance", "")
    if not balance:
        return 0.3

    balance_lower = balance.lower()
    if "heavy dialogue" in balance_lower or "dialogue-driven" in balance_lower:
        return 0.5
    elif "sparse dialogue" in balance_lower or "narration-heavy" in balance_lower:
        return 0.2
    else:
        return 0.3


def extract_monologue_frequency(meta_layer: Dict[str, Any]) -> str:
    """Extract internal monologue frequency."""
    prose = meta_layer.get("writing_style", {}).get("prose_description", "")
    if not prose:
        return "frequent"

    prose_lower = prose.lower()
    if "stream of consciousness" in prose_lower or "heavy internal" in prose_lower:
        return "constant"
    elif "external focus" in prose_lower or "minimal internal" in prose_lower:
        return "occasional"
    else:
        return "frequent"


def generate_titling_guidance(style_type: str, examples: List[str]) -> str:
    """Generate guidance for creating chapter titles."""
    if style_type == "numbered_only":
        return "Use simple numbered format (e.g., 'Chapter 1', '第一章')"

    if style_type == "poetic":
        if examples:
            return (
                f"Create poetic, evocative titles in the style of: {', '.join(examples[:3])}. "
                "Capture the emotional or thematic essence of the chapter in literary language."
            )
        return "Create poetic, literary titles that evoke mood and theme"

    if style_type == "symbolic":
        return "Use symbolic or metaphorical titles that hint at chapter content"

    if style_type == "simple_descriptive":
        return "Use clear, descriptive titles that summarize chapter content"

    return "Match the titling style of the source material"


def format_synthesis_instructions(
    meta_context: SynthesisMetaContext,
    event_count: int,
) -> str:
    """
    Format meta-context into clear synthesis instructions for LLM.

    Returns markdown with explicit guidance.
    """
    lines = ["# SYNTHESIS REQUIREMENTS", ""]

    # Length and density
    lines.append("## Target Length and Density")
    lines.append(
        f"- **Target word count**: ~{meta_context.density_metrics.average_word_count} words "
        "(this is NOT a summary - match source material length!)"
    )
    lines.append(
        f"- **Scene development**: Develop each scene fully. Don't rush. "
        f"Original chapters have {meta_context.density_metrics.average_scene_count} well-developed scenes."
    )
    lines.append(
        f"- **Description density**: {meta_context.density_metrics.description_density.upper()} - "
        "include sensory details, environmental description, internal states"
    )
    lines.append(
        f"- **Dialogue ratio**: ~{int(meta_context.density_metrics.dialogue_to_narration_ratio * 100)}% dialogue, "
        f"rest narration"
    )
    lines.append(
        f"- **Internal monologue**: {meta_context.density_metrics.internal_monologue_frequency.upper()} - "
        "show character thoughts and reactions"
    )
    lines.append("")

    # Chapter title
    if meta_context.titling_style.style_type != "numbered_only":
        lines.append("## Chapter Title")
        lines.append(f"- **Style**: {meta_context.titling_style.style_type}")
        if meta_context.titling_style.title_examples:
            lines.append(
                f"- **Examples from source**: {', '.join(meta_context.titling_style.title_examples[:3])}"
            )
        lines.append(f"- **Guidance**: {meta_context.titling_style.title_generation_guidance}")
        lines.append(
            "- **IMPORTANT**: Start output with chapter heading matching this style, "
            "then blank line, then prose"
        )
        lines.append("")

    # Pacing
    lines.append("## Pacing and Structure")
    if meta_context.pacing_guidance.scene_opening_style:
        lines.append(
            f"- **Scene openings**: {meta_context.pacing_guidance.scene_opening_style}"
        )
    if meta_context.pacing_guidance.scene_closing_style:
        lines.append(
            f"- **Scene closings**: {meta_context.pacing_guidance.scene_closing_style}"
        )
    if meta_context.pacing_guidance.scene_transition_method:
        lines.append(
            f"- **Transitions**: {meta_context.pacing_guidance.scene_transition_method}"
        )
    lines.append(
        f"- **Events to weave in**: {event_count} simulation events - "
        "don't list them, DRAMATIZE them with full scenes"
    )
    lines.append("")

    # Style
    lines.append("## Writing Style")
    if meta_context.sentence_rhythm_guidance:
        lines.append(f"- **Sentence rhythm**: {meta_context.sentence_rhythm_guidance}")
    if meta_context.paragraphing_guidance:
        lines.append(f"- **Paragraphing**: {meta_context.paragraphing_guidance}")
    if meta_context.tone_guidance:
        lines.append(f"- **Tone**: {meta_context.tone_guidance}")
    lines.append("")

    # Quality reminder
    lines.append("## Quality Standards")
    lines.append(
        "- This is NOT a summary or synopsis - it's a full literary chapter"
    )
    lines.append(
        "- Every sentence must feel like the original author wrote it"
    )
    lines.append(
        "- Show, don't tell - dramatize events as scenes, not bullet points"
    )
    lines.append(
        "- Maintain narrative tension throughout"
    )
    lines.append(
        "- Match the original's depth and richness"
    )

    return "\n".join(lines)
