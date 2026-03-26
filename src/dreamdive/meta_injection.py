"""Utilities for injecting [META] sections into prompts.

The [META] section combines novel meta (authorial intent, style, taste,
design tendencies) with fate layer (dramatic blueprint) and user
preferences (user_meta) to shape downstream LLM behavior.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from dreamdive.ingestion.models import FateLayerRecord, MetaLayerRecord
    from dreamdive.user_config import UserMeta


def format_meta_section(
    novel_meta: MetaLayerRecord | None = None,
    user_meta: UserMeta | None = None,
    fate: FateLayerRecord | None = None,
) -> str:
    """Format [META] section for prompt injection.

    Combines novel meta (from ingestion), fate layer (from P1.6/P1.7),
    and user preferences (from P0).
    During ingestion, novel_meta may be incomplete or None.
    During simulation and synthesis, all three should be present.
    """
    lines: list[str] = ["[META]"]

    if novel_meta is not None:
        # Authorial layer
        if novel_meta.authorial.central_thesis:
            thesis = novel_meta.authorial.central_thesis.get("summary", "")
            if thesis:
                lines.append(f"Original authorial intent: {thesis}")

        if novel_meta.authorial.dominant_tone:
            lines.append(f"Original tone: {novel_meta.authorial.dominant_tone}")

        if novel_meta.authorial.themes:
            theme_names = [t.name for t in novel_meta.authorial.themes[:3] if t.name]
            if theme_names:
                lines.append(f"Original themes: {', '.join(theme_names)}")

        # Writing style
        if novel_meta.writing_style.prose_description:
            lines.append(f"Original style: {novel_meta.writing_style.prose_description}")

        # Language context
        if novel_meta.language_context.primary_language:
            lines.append(f"Primary language: {novel_meta.language_context.primary_language}")

        # Tone and register (expanded meta)
        if novel_meta.tone_and_register.dominant_register:
            lines.append(f"Dominant register: {novel_meta.tone_and_register.dominant_register}")
        if novel_meta.tone_and_register.emotional_contract:
            lines.append(f"Emotional contract: {novel_meta.tone_and_register.emotional_contract}")

        # Author's taste (critical constraints)
        if novel_meta.authors_taste.categorical_refusals:
            refusals = novel_meta.authors_taste.categorical_refusals[:3]
            lines.append(f"Author refuses: {'; '.join(refusals)}")
        if novel_meta.authors_taste.aesthetic_values:
            lines.append(f"Aesthetic values: {novel_meta.authors_taste.aesthetic_values}")

        # Genre taste benchmark (gold-standard from genre masters)
        if novel_meta.genre_taste.taste_profile:
            lines.append(f"Genre taste benchmark: {novel_meta.genre_taste.taste_profile}")
        if novel_meta.genre_taste.reference_masters:
            masters = [
                f"{m.name} ({m.why})" for m in novel_meta.genre_taste.reference_masters[:4]
                if m.name
            ]
            if masters:
                lines.append(f"Reference masters: {'; '.join(masters)}")

    # Fate layer (dramatic blueprint)
    if fate is not None:
        extracted = fate.extracted
        if extracted.central_question:
            lines.append(f"Central dramatic question: {extracted.central_question}")
        if extracted.thematic_payload:
            lines.append(f"Thematic payload: {extracted.thematic_payload}")
        if extracted.current_phase:
            lines.append(f"Story phase: {extracted.current_phase}")

    if user_meta is not None:
        # User preferences
        if user_meta.tone.overall:
            lines.append(f"User desired tone: {user_meta.tone.overall}")

        if user_meta.emphasis.primary:
            lines.append(f"User emphasis: {', '.join(user_meta.emphasis.primary)}")

        if user_meta.divergence_seeds:
            seed_descriptions = [seed.description for seed in user_meta.divergence_seeds[:3]]
            lines.append(f"Divergence seeds active: {'; '.join(seed_descriptions)}")

        if user_meta.focus_characters:
            lines.append(f"Focus characters: {', '.join(user_meta.focus_characters)}")

        if user_meta.free_notes:
            lines.append(f"Additional user notes: {user_meta.free_notes}")

    if len(lines) == 1:  # Only "[META]" header
        return ""

    return "\n".join(lines) + "\n"
