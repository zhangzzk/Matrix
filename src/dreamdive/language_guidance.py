from __future__ import annotations

from typing import Iterable

from dreamdive.ingestion.models import MetaLayerRecord


def build_language_guidance(meta: MetaLayerRecord) -> str:
    context = meta.language_context
    writing_style = meta.writing_style
    authorial = meta.authorial
    parts: list[str] = []

    _append_line(parts, "Primary language", context.primary_language)
    _append_line(parts, "Language variety", context.language_variety)
    _append_line(parts, "Language style", context.language_style)
    _append_line(parts, "Author style", context.author_style)
    _append_line(parts, "Register profile", context.register_profile)
    _append_line(parts, "Dialogue style", context.dialogue_style)
    _append_list(parts, "Figurative patterns", context.figurative_patterns)
    _append_list(parts, "Multilingual features", context.multilingual_features)
    _append_list(parts, "Translation notes", context.translation_notes)
    _append_line(parts, "Prose description", writing_style.prose_description)
    _append_line(parts, "Sentence rhythm", writing_style.sentence_rhythm)
    _append_line(parts, "Dialogue vs narration", writing_style.dialogue_narration_balance)
    _append_list(parts, "Stylistic signatures", writing_style.stylistic_signatures)
    _append_line(parts, "Dominant tone", authorial.dominant_tone)
    _append_line(parts, "Narrative perspective", authorial.narrative_perspective)

    return "\n".join(f"- {part}" for part in parts[:10])


def format_language_guidance_block(language_guidance: str) -> str:
    cleaned = language_guidance.strip()
    if not cleaned:
        return ""
    return (
        f"LANGUAGE AND STYLE CONTEXT:\n{cleaned}\n\n"
        "OUTPUT LANGUAGE RULES:\n"
        "- Keep every free-text value in the primary language above.\n"
        "- JSON keys may remain English to match the schema, but descriptions, locations, dialogue, motivations, summaries, thread labels, and other narrative text must stay in the manuscript language.\n"
        "- Do not translate names, place names, institutions, or coined terms into English unless the source itself already uses that form.\n\n"
    )


def _append_line(parts: list[str], label: str, value: str) -> None:
    cleaned = value.strip()
    if cleaned:
        parts.append(f"{label}: {cleaned}")


def _append_list(parts: list[str], label: str, values: Iterable[str]) -> None:
    cleaned = [item.strip() for item in values if item.strip()]
    if cleaned:
        parts.append(f"{label}: {', '.join(cleaned)}")
