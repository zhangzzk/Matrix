"""
Context Salience and Filtering System

Prevents agents from over-relying on specific phrases, patterns, or motifs
by implementing intelligent salience weighting and frequency control.

The problem: When meta-layer extraction identifies signature phrases like "真烦"
or "麦乐鸡", agents see them as important and overuse them in every scene.

The solution: Add salience layers and usage guidance to prevent repetition.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class UsageFrequency(str, Enum):
    """How often should this element appear?"""
    CONSTANT = "constant"  # Every scene (e.g., core personality trait)
    FREQUENT = "frequent"  # Most scenes (e.g., common behavior pattern)
    OCCASIONAL = "occasional"  # Some scenes (e.g., recurring motif)
    RARE = "rare"  # Few key moments (e.g., signature phrase, catchphrase)
    CLIMACTIC = "climactic"  # Only at dramatic peaks (e.g., transformation moment)


class ContextElement(BaseModel):
    """
    A piece of context with salience metadata.
    Guides agents on HOW to use information, not just WHAT it is.
    """
    content: str = Field(description="The actual information")
    element_type: str = Field(
        description="Type: core_trait | behavior_pattern | signature_phrase | motif | fact"
    )
    salience: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="How important is this? 1.0 = critical, 0.0 = flavor"
    )
    usage_frequency: UsageFrequency = Field(
        default=UsageFrequency.FREQUENT,
        description="How often should this appear in agent output?"
    )
    usage_guidance: str = Field(
        default="",
        description="How to use this appropriately (e.g., 'Only when frustrated', 'Sparingly for impact')"
    )
    avoid_patterns: List[str] = Field(
        default_factory=list,
        description="Anti-patterns to avoid (e.g., 'Don't use in every paragraph', 'Not in formal scenes')"
    )


class CharacterContextPacket(BaseModel):
    """
    Enhanced context packet with salience-aware organization.
    Separates CORE traits from SIGNATURE moves to prevent overuse.
    """
    character_id: str

    # Core identity - always relevant
    core_traits: List[ContextElement] = Field(
        default_factory=list,
        description="Fundamental personality traits (use constantly)"
    )

    # Behavioral patterns - frequently relevant
    behavior_patterns: List[ContextElement] = Field(
        default_factory=list,
        description="Common behaviors and reactions (use frequently)"
    )

    # Signature elements - USE SPARINGLY
    signature_phrases: List[ContextElement] = Field(
        default_factory=list,
        description="Catchphrases and signature moves (use rarely for impact)"
    )

    # Motifs and symbols - occasional use
    recurring_motifs: List[ContextElement] = Field(
        default_factory=list,
        description="Recurring themes and symbols (use occasionally)"
    )

    # Current state facts - always relevant
    current_state: Dict[str, Any] = Field(default_factory=dict)

    # Working memory - high salience
    working_memory: List[str] = Field(default_factory=list)


def convert_legacy_context_to_salience_aware(
    legacy_identity: Dict[str, Any],
    meta_layer: Optional[Dict[str, Any]] = None,
) -> CharacterContextPacket:
    """
    Convert legacy character identity + meta-layer into salience-aware format.

    Args:
        legacy_identity: CharacterIdentity dict
        meta_layer: MetaLayerRecord dict with signature moves, etc.

    Returns:
        Salience-aware context packet
    """
    packet = CharacterContextPacket(character_id=legacy_identity.get("character_id", ""))

    # Extract core traits (always relevant)
    core_traits_raw = legacy_identity.get("core_traits", [])
    for trait in core_traits_raw:
        packet.core_traits.append(
            ContextElement(
                content=trait,
                element_type="core_trait",
                salience=1.0,
                usage_frequency=UsageFrequency.CONSTANT,
                usage_guidance="This is fundamental to who they are - weave into all actions",
            )
        )

    # Extract values/fears/desires (frequent)
    for value in legacy_identity.get("values", []):
        packet.behavior_patterns.append(
            ContextElement(
                content=f"Values: {value}",
                element_type="behavior_pattern",
                salience=0.8,
                usage_frequency=UsageFrequency.FREQUENT,
                usage_guidance="Influences decisions and reactions",
            )
        )

    # Extract signature moves from meta-layer (RARE usage!)
    if meta_layer:
        signature_moves = meta_layer.get("authors_taste", {}).get("signature_moves", [])
        for move in signature_moves:
            # Check if this is a phrase-based signature
            is_phrase_signature = any(
                marker in move.lower()
                for marker in ["'", '"', "说", "phrase", "catchphrase", "口头禅"]
            )

            usage_freq = UsageFrequency.RARE if is_phrase_signature else UsageFrequency.OCCASIONAL

            packet.signature_phrases.append(
                ContextElement(
                    content=move,
                    element_type="signature_phrase",
                    salience=0.9,  # High salience but LOW frequency
                    usage_frequency=usage_freq,
                    usage_guidance=(
                        "Use sparingly for maximum impact. This is a signature move - "
                        "overuse will dilute its effect. Save for key moments."
                    ),
                    avoid_patterns=[
                        "Don't use in every scene",
                        "Don't use multiple times per chapter",
                        "Avoid in formal or serious confrontations unless dramatically appropriate",
                    ],
                )
            )

    return packet


def format_salience_aware_context(packet: CharacterContextPacket) -> str:
    """
    Format context packet for LLM prompt with usage guidance.

    Returns markdown with clear frequency signals.
    """
    lines = [f"# Character Context: {packet.character_id}", ""]

    # Core traits - no frequency warning needed
    if packet.core_traits:
        lines.append("## Core Personality (fundamental - constant)")
        for elem in packet.core_traits:
            lines.append(f"- {elem.content}")
        lines.append("")

    # Behavior patterns
    if packet.behavior_patterns:
        lines.append("## Behavioral Patterns (frequent)")
        for elem in packet.behavior_patterns:
            lines.append(f"- {elem.content}")
        lines.append("")

    # Signature phrases - WITH STRONG WARNING
    if packet.signature_phrases:
        lines.append("## Signature Elements ⚠️ USE SPARINGLY")
        lines.append("_These are signature moves - save for KEY MOMENTS. Overuse dilutes impact._")
        lines.append("")
        for elem in packet.signature_phrases:
            freq_label = elem.usage_frequency.value.upper()
            lines.append(f"- **[{freq_label}]** {elem.content}")
            if elem.usage_guidance:
                lines.append(f"  _Guidance: {elem.usage_guidance}_")
            if elem.avoid_patterns:
                lines.append(f"  _Avoid: {', '.join(elem.avoid_patterns)}_")
        lines.append("")

    # Recurring motifs
    if packet.recurring_motifs:
        lines.append("## Recurring Motifs (occasional)")
        for elem in packet.recurring_motifs:
            lines.append(f"- {elem.content}")
        lines.append("")

    return "\n".join(lines)


def extract_signature_phrases_from_meta(meta_layer: Dict[str, Any]) -> List[str]:
    """
    Extract specific signature phrases that should be used rarely.

    Examples:
    - "真烦" for Lu Mingfei
    - "麦乐鸡" references
    - Character-specific catchphrases
    """
    phrases = []

    # From signature moves
    signature_moves = meta_layer.get("authors_taste", {}).get("signature_moves", [])
    for move in signature_moves:
        # Look for quoted phrases or specific terms
        if "'" in move or '"' in move or "«" in move or "»" in move:
            phrases.append(move)

    # From symbolic motifs
    motifs = meta_layer.get("authorial", {}).get("symbolic_motifs", [])
    for motif in motifs:
        phrases.append(f"Motif: {motif}")

    # From character voices
    char_voices = meta_layer.get("character_voices", [])
    for voice in char_voices:
        # Speech patterns that are signature
        rhetorical = voice.get("rhetorical_tendencies", "")
        if rhetorical:
            phrases.append(f"Speech pattern: {rhetorical}")

        # Things they gravitate toward
        gravitates = voice.get("gravitates_toward", [])
        for g in gravitates:
            phrases.append(f"Verbal tendency: {g}")

    return phrases


# Pre-built guidance for common problematic elements

COMMON_SIGNATURE_GUIDANCE = {
    "真烦": ContextElement(
        content="Catchphrase: '真烦' (So annoying)",
        element_type="signature_phrase",
        salience=0.9,
        usage_frequency=UsageFrequency.RARE,
        usage_guidance="Only when genuinely frustrated at absurd situations. Not a verbal tic. Save for 1-2 moments per chapter maximum.",
        avoid_patterns=[
            "Don't use as filler",
            "Not in every internal monologue",
            "Avoid when character is genuinely scared or serious",
            "Don't combine with other catchphrases in same scene",
        ],
    ),
    "麦乐鸡": ContextElement(
        content="Motif: McNuggets (麦乐鸡) - symbol of mundane desires vs. epic stakes",
        element_type="motif",
        salience=0.8,
        usage_frequency=UsageFrequency.RARE,
        usage_guidance="Use as stark contrast between ordinary life and extraordinary danger. Once per major arc, not every chapter.",
        avoid_patterns=[
            "Don't literally mention McNuggets every time character is hungry",
            "Use the CONCEPT (mundane vs. epic) not the literal object repeatedly",
            "Save for moments of maximum ironic contrast",
        ],
    ),
}


def apply_signature_phrase_filtering(
    character_id: str,
    context_packet: CharacterContextPacket,
    recent_output_history: Optional[List[str]] = None,
) -> CharacterContextPacket:
    """
    Apply dynamic filtering based on recent usage.

    If signature phrases were used recently, suppress them from current context.

    Args:
        character_id: Character ID
        context_packet: Context to filter
        recent_output_history: Last N agent outputs (to check for overuse)

    Returns:
        Filtered context packet
    """
    if not recent_output_history:
        return context_packet

    # Count signature phrase occurrences in recent history
    phrase_counts: Dict[str, int] = {}
    for elem in context_packet.signature_phrases:
        count = sum(
            1 for output in recent_output_history
            if any(marker in output for marker in extract_key_markers(elem.content))
        )
        phrase_counts[elem.content] = count

    # Filter out overused signatures
    filtered_signatures = []
    for elem in context_packet.signature_phrases:
        count = phrase_counts.get(elem.content, 0)

        # If used recently, add strong suppression warning
        if count > 0:
            elem.avoid_patterns.insert(
                0,
                f"⚠️ ALREADY USED {count} time(s) recently - DO NOT REPEAT"
            )
            if count >= 2:
                # Skip entirely if used 2+ times
                continue

        filtered_signatures.append(elem)

    context_packet.signature_phrases = filtered_signatures
    return context_packet


def extract_key_markers(signature_desc: str) -> List[str]:
    """Extract key phrases/words that would indicate usage of a signature."""
    markers = []

    # Extract quoted phrases
    import re
    quoted = re.findall(r"['\"\u00ab\u00bb](.*?)['\"\u00ab\u00bb]", signature_desc)
    markers.extend(quoted)

    # Extract Chinese characters (likely catchphrases)
    chinese = re.findall(r"[\u4e00-\u9fff]+", signature_desc)
    markers.extend(chinese)

    return markers
