from __future__ import annotations

import json
import re
from typing import Any, List

from dreamdive.ingestion.chunker import TextChunk
from dreamdive.ingestion.extractor import ChapterSource
from dreamdive.ingestion.models import (
    AccumulatedExtraction,
    EntityExtractionPayload,
    MetaLayerRecord,
    StructuralScanPayload,
    TimelineSkeleton,
)
from dreamdive.schemas import PromptRequest


SOURCE_LANGUAGE_RULES = (
    "Language policy:\n"
    "- Keep all free-text fields in the same language as the source text.\n"
    "- Do not translate source material into English.\n"
    "- Preserve original wording, names, titles, and culturally specific terms unless a normalized ID is required.\n"
)

_PROMPT_CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")


def _json_contract(example: dict) -> str:
    return (
        "Return exactly one JSON object using these exact keys.\n"
        "Do not rename keys, do not add extra keys, and do not wrap the JSON in markdown fences.\n"
        "Keep strings concrete and concise.\n"
        f"{json.dumps(example, indent=2, ensure_ascii=False, sort_keys=True)}\n\n"
    )


def _language_policy(*texts: str) -> str:
    joined = "\n".join(texts)
    primary_language = "Chinese" if _PROMPT_CJK_RE.search(joined) else "English"
    return f"Primary language: {primary_language}\n{SOURCE_LANGUAGE_RULES}"


def _matching_terms(text: str, candidates: List[str]) -> bool:
    haystack = text.strip()
    if not haystack:
        return False
    return any(candidate and candidate in haystack for candidate in candidates)


def _non_empty_state(current_state: dict) -> dict:
    return {
        key: value
        for key, value in current_state.items()
        if value not in ("", None, [], {})
    }


def _build_chapter_context(
    accumulated: AccumulatedExtraction,
    *,
    chapter_text: str,
    structural_scan: StructuralScanPayload | None = None,
) -> dict:
    accumulated_by_id = {record.id: record for record in accumulated.characters}
    structural_by_id = (
        {member.id: member for member in structural_scan.cast_list}
        if structural_scan is not None
        else {}
    )
    direct_character_ids: list[str] = []
    seen_direct_ids: set[str] = set()

    for record in accumulated.characters:
        terms = [record.name, *record.aliases]
        if not _matching_terms(chapter_text, [term for term in terms if term]):
            continue
        if record.id in seen_direct_ids:
            continue
        direct_character_ids.append(record.id)
        seen_direct_ids.add(record.id)

    if structural_scan is not None:
        for cast_member in structural_scan.cast_list:
            terms = [cast_member.name, *cast_member.aliases]
            if cast_member.id in seen_direct_ids:
                continue
            if not _matching_terms(chapter_text, [term for term in terms if term]):
                continue
            direct_character_ids.append(cast_member.id)
            seen_direct_ids.add(cast_member.id)

    one_hop_character_ids: list[str] = []
    seen_one_hop_ids: set[str] = set()
    for character_id in direct_character_ids:
        record = accumulated_by_id.get(character_id)
        if record is not None:
            for relationship in record.relationships:
                target_id = relationship.target_id.strip()
                if (
                    target_id
                    and target_id not in seen_direct_ids
                    and target_id not in seen_one_hop_ids
                ):
                    one_hop_character_ids.append(target_id)
                    seen_one_hop_ids.add(target_id)
        for candidate in accumulated.characters:
            if candidate.id in seen_direct_ids or candidate.id in seen_one_hop_ids:
                continue
            if any(rel.target_id == character_id for rel in candidate.relationships):
                one_hop_character_ids.append(candidate.id)
                seen_one_hop_ids.add(candidate.id)

    relevant_character_cards = []
    for character_id in [*direct_character_ids, *one_hop_character_ids]:
        record = accumulated_by_id.get(character_id)
        if record is not None:
            relevant_character_cards.append(record.model_dump(mode="json"))
            continue
        cast_member = structural_by_id.get(character_id)
        if cast_member is not None:
            relevant_character_cards.append(
                {
                    "id": cast_member.id,
                    "name": cast_member.name,
                    "aliases": cast_member.aliases,
                    "identity": {
                        "role": cast_member.role,
                        "first_appearance": cast_member.first_appearance,
                        "tier": cast_member.tier,
                    },
                    "personality": {},
                    "current_state": {},
                    "relationships": [],
                    "memory_seeds": [],
                }
            )

    structural_world = structural_scan.world if structural_scan is not None else None
    timeline_spine = (
        structural_scan.timeline_skeleton.model_dump(mode="json")
        if structural_scan is not None
        else TimelineSkeleton().model_dump(mode="json")
    )
    return {
        "character_cards": relevant_character_cards,
        "timeline_spine": timeline_spine,
        "world_primer": {
            "setting": accumulated.world.setting or (structural_world.setting if structural_world else None),
            "time_period": accumulated.world.time_period
            or (structural_world.time_period if structural_world else None),
            "locations": _dedupe_strings(
                [
                    *accumulated.world.locations,
                    *(
                        location.name
                        for location in (structural_world.key_locations if structural_world else [])
                    ),
                ]
            ),
            "rules_and_constraints": _dedupe_strings(
                [
                    *accumulated.world.rules_and_constraints,
                    *(
                        structural_world.rules_and_constraints
                        if structural_world is not None
                        else []
                    ),
                ]
            ),
            "factions": _dedupe_strings(
                [
                    *accumulated.world.factions,
                    *(
                        faction.name for faction in (structural_world.factions if structural_world else [])
                    ),
                ]
            ),
        },
        "domain_systems": [
            system.model_dump(mode="json")
            for system in (structural_scan.domain_systems if structural_scan is not None else [])
        ],
    }


def _dedupe_strings(values: List[str]) -> List[str]:
    result: List[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = value.strip() if isinstance(value, str) else ""
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result


def _first_non_empty_mapping_values(
    payload: dict[str, Any],
    *,
    preferred_keys: List[str],
    max_items: int,
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    seen_keys: set[str] = set()
    for key in preferred_keys:
        value = payload.get(key)
        if value in ("", None, [], {}):
            continue
        result[key] = value
        seen_keys.add(key)
        if len(result) >= max_items:
            return result
    for key, value in payload.items():
        if key in seen_keys or value in ("", None, [], {}):
            continue
        result[str(key)] = value
        if len(result) >= max_items:
            break
    return result


def build_entity_extraction_context(accumulated: AccumulatedExtraction) -> dict[str, Any]:
    character_cards: list[dict[str, Any]] = []
    for record in accumulated.characters:
        identity = _first_non_empty_mapping_values(
            record.identity,
            preferred_keys=[
                "role",
                "title",
                "occupation",
                "affiliation",
                "status",
                "bloodline",
            ],
            max_items=4,
        )
        current_state = _non_empty_state(record.current_state.model_dump(mode="json"))
        if "goal_stack" in current_state:
            current_state["goal_stack"] = _dedupe_strings(current_state.get("goal_stack", []))[:4]
            if not current_state["goal_stack"]:
                current_state.pop("goal_stack", None)
        character_cards.append(
            {
                "id": record.id,
                "name": record.name,
                "aliases": _dedupe_strings(record.aliases),
                "identity": identity,
                "current_state": current_state,
            }
        )

    event_spine: list[dict[str, Any]] = []
    for record in accumulated.events:
        event_spine.append(
            {
                "id": record.id,
                "time": record.time,
                "location": record.location,
                "participants": _dedupe_strings(record.participants),
                "summary": record.summary,
                "consequences": _dedupe_strings(record.consequences)[:4],
            }
        )

    existing_entity_hints: list[dict[str, Any]] = []
    for entity in accumulated.entities:
        existing_entity_hints.append(
            {
                "entity_id": entity.entity_id,
                "name": entity.name,
                "type": entity.type,
                "objective_facts": _dedupe_strings(entity.objective_facts)[:3],
                "narrative_role": entity.narrative_role,
            }
        )

    meta_hints = {
        "language_context": {
            "primary_language": accumulated.meta.language_context.primary_language,
            "language_style": accumulated.meta.language_context.language_style,
            "author_style": accumulated.meta.language_context.author_style,
        },
        "authorial_themes": [
            {
                "name": theme.name,
                "description": theme.description,
            }
            for theme in accumulated.meta.authorial.themes[:6]
            if theme.name or theme.description
        ],
        "symbolic_motifs": _dedupe_strings(accumulated.meta.authorial.symbolic_motifs)[:6],
    }

    return {
        "character_cards": character_cards,
        "world_primer": {
            "setting": accumulated.world.setting,
            "time_period": accumulated.world.time_period,
            "locations": _dedupe_strings(accumulated.world.locations),
            "rules_and_constraints": _dedupe_strings(accumulated.world.rules_and_constraints),
            "factions": _dedupe_strings(accumulated.world.factions),
        },
        "event_spine": event_spine,
        "existing_entity_hints": existing_entity_hints,
        "meta_hints": meta_hints,
    }


def build_structural_scan_prompt(chunks: List[TextChunk]) -> PromptRequest:
    joined_chunks = "\n\n".join(
        f"[{chunk.chunk_id} | approx_tokens={chunk.approx_token_count}]\n{chunk.text}"
        for chunk in chunks
    )
    system = (
        "You are initializing a character simulation engine from a novel. "
        "Build the structural skeleton that later chapter passes will extend. "
        "Do not invent facts. Return valid JSON only."
    )
    output_contract = _json_contract(
        {
            "world": {
                "setting": "One concise setting description or null",
                "time_period": "One concise time period or null",
                "rules_and_constraints": ["Constraint"],
                "factions": [
                    {
                        "name": "Faction name",
                        "goal": "Faction goal or null",
                        "relationships": {"Other faction": "Relationship"},
                    }
                ],
                "key_locations": [
                    {
                        "name": "Location name",
                        "description": "Short description or null",
                        "narrative_significance": "Why it matters or null",
                    }
                ],
            },
            "cast_list": [
                {
                    "id": "char_001",
                    "name": "Character name",
                    "aliases": ["Alias"],
                    "role": "Role or null",
                    "first_appearance": "First appearance or null",
                    "tier": 2,
                }
            ],
            "timeline_skeleton": {
                "story_start": "Story start or null",
                "pre_story_events": ["Earlier event"],
                "known_future_events": ["Foreshadowed future event"],
            },
            "domain_systems": [
                {
                    "name": "System name",
                    "description": "System description or null",
                    "scale": "Scale or null",
                }
            ],
        }
    )
    user = (
        "NOVEL TEXT (opening section):\n"
        f"{joined_chunks}\n\n"
        "Extract the following and return valid JSON:\n"
        "1. WORLD: setting, time period, rules and hard constraints, factions, key locations.\n"
        "2. CAST LIST: id, name, aliases, role, first appearance, tier.\n"
        "3. TIMELINE SKELETON: story start, pre-story events, known future events.\n"
        "4. DOMAIN SYSTEMS: world-specific ranking or skill systems and their scales.\n\n"
        "Rules:\n"
        "- Do not invent anything not in the text.\n"
        "- Mark uncertain fields as null instead of guessing.\n"
        f"{_language_policy(joined_chunks)}"
        "- Output only JSON matching the structural scan schema.\n\n"
        "OUTPUT CONTRACT:\n"
        f"{output_contract}"
    )
    return PromptRequest(
        system=system,
        user=user,
        max_tokens=4_000,
        stream=False,
        metadata={
            "prompt_name": "p1_1_structural_scan",
            "response_schema": "StructuralScanPayload",
        },
    )


def build_chapter_extraction_prompt(
    chapter: ChapterSource,
    accumulated: AccumulatedExtraction,
    *,
    structural_scan: StructuralScanPayload | None = None,
) -> PromptRequest:
    context_json = json.dumps(
        _build_chapter_context(
            accumulated,
            chapter_text=chapter.text,
            structural_scan=structural_scan,
        ),
        indent=2,
        sort_keys=True,
        ensure_ascii=False,
    )
    system = (
        "You are updating a structured character simulation database from a novel chapter. "
        "This is an additive section pass: preserve existing data, extend it, and correct only when the "
        "section provides stronger evidence. Return valid JSON only."
    )
    output_contract = _json_contract(
        {
            "characters": [
                {
                    "id": "char_001",
                    "name": "Character name",
                    "aliases": ["Alias"],
                    "identity": {"role": "Identity fact"},
                    "personality": {"trait": "Personality fact"},
                    "current_state": {
                        "emotional_state": "Short emotional state or null",
                        "physical_state": "Short physical state or null",
                        "location": "Location or null",
                        "goal_stack": ["Concrete goal"],
                    },
                    "relationships": [
                        {
                            "target_id": "char_002",
                            "type": "Relationship type or null",
                            "trust": 0.5,
                            "sentiment": "Sentiment or null",
                            "shared_history_summary": "Short shared history or null",
                        }
                    ],
                    "memory_seeds": ["Short memory seed"],
                }
            ],
            "world": {
                "setting": "Setting or null",
                "time_period": "Time period or null",
                "locations": ["Location name"],
                "rules_and_constraints": ["Constraint"],
                "factions": ["Faction name"],
            },
            "events": [
                {
                    "id": "evt_001",
                    "time": "Time or null",
                    "location": "Location or null",
                    "participants": ["char_001"],
                    "summary": "Objective event summary",
                    "consequences": ["Consequence"],
                    "participant_knowledge": {"char_001": "What they know"},
                }
            ],
            "entities": [
                {
                    "entity_id": "ent_001",
                    "name": "Entity name",
                    "type": "object",
                    "objective_facts": ["Fact"],
                    "narrative_role": "Narrative role",
                    "absent_figure_details": {
                        "reason_absent": "",
                        "most_present_in": [],
                        "counterfactual": "",
                    },
                    "concept_details": {
                        "definitions_by_character": {},
                        "who_weaponizes": [],
                        "who_is_bound_by": [],
                        "authorial_stance": "",
                    },
                    "agent_representations": [
                        {
                            "agent_id": "char_001",
                            "belief": "Belief",
                            "emotional_charge": "Emotion",
                            "goal_relevance": "Why it matters",
                            "misunderstanding": "",
                            "confidence": "EXPLICIT",
                        }
                    ],
                }
            ],
            "meta": {
                "authorial": {},
                "writing_style": {},
                "language_context": {},
                "character_voices": [],
                "real_world_context": {},
            },
        }
    )
    user = (
        f"CHAPTER ID: {chapter.chapter_id}\n"
        f"CHAPTER TITLE: {chapter.title or chapter.chapter_id}\n"
        f"CHAPTER ORDER: {chapter.order_index}\n\n"
        "CHAPTER TEXT:\n"
        f"{chapter.text}\n\n"
        "RETRIEVED CHAPTER CONTEXT:\n"
        f"{context_json}\n\n"
        "This context package contains chapter-relevant character cards, a timeline spine, "
        "and world/domain scaffolding retrieved from prior extraction.\n"
        "Update the global database based on this chapter section.\n"
        "For characters, refine identity, personality, state-at-end-of-chapter, concrete goals, "
        "relationships, and domain attributes when directly supported.\n"
        "For events, capture time, location, participants, objective summary, consequences, and "
        "participant-specific knowledge.\n"
        "For world elements, extend locations, factions, rules, and historical facts.\n\n"
        "Rules:\n"
        "- Return only deltas: new records, changed records, or newly supported fields from this section.\n"
        "- Omit unchanged characters, events, entities, and world/meta fields entirely.\n"
        "- Within a returned record, include only fields that this section supports or updates.\n"
        "- The ingestion pipeline will merge your delta into the accumulated database.\n"
        "- Treat retrieved character cards as the only prior character state you need for this section.\n"
        "- If a chapter character is missing from the retrieved cards, create a new character record from the chapter text.\n"
        "- Goals must be concrete intentions, not traits.\n"
        "- Relationship directionality matters.\n"
        f"{_language_policy(chapter.text)}"
        "- Output only JSON matching the accumulated extraction schema.\n\n"
        "OUTPUT CONTRACT:\n"
        f"{output_contract}"
    )
    return PromptRequest(
        system=system,
        user=user,
        max_tokens=3_500,
        stream=False,
        metadata={
            "prompt_name": "p1_2_chapter_extraction",
            "chapter_id": chapter.chapter_id,
            "response_schema": "AccumulatedExtraction",
        },
    )


def build_meta_layer_prompt(
    excerpts: List[str],
    *,
    major_character_ids: List[str],
) -> PromptRequest:
    excerpt_block = "\n\n".join(excerpts)
    output_contract = _json_contract(
        {
            "authorial": {
                "central_thesis": {"summary": "Central thesis"},
                "themes": [
                    {
                        "name": "Theme name",
                        "description": "Theme description",
                        "confidence": "INFERRED",
                    }
                ],
                "dominant_tone": "Dominant tone",
                "beliefs_about": {"power": "Belief"},
                "symbolic_motifs": ["Motif"],
                "narrative_perspective": "Perspective",
            },
            "writing_style": {
                "prose_description": "Prose description",
                "sentence_rhythm": "Sentence rhythm",
                "description_density": "Description density",
                "dialogue_narration_balance": "Dialogue/narration balance",
                "stylistic_signatures": ["Signature"],
                "sample_passages": [
                    {
                        "text": "Short sample passage",
                        "why_representative": "Why it matters",
                    }
                ],
            },
            "language_context": {
                "primary_language": "Primary language",
                "language_variety": "Language variety",
                "language_style": "Language style",
                "author_style": "Author style",
                "register_profile": "Register profile",
                "dialogue_style": "Dialogue style",
                "figurative_patterns": ["Pattern"],
                "multilingual_features": ["Feature"],
                "translation_notes": ["Note"],
            },
            "character_voices": [
                {
                    "character_id": "char_001",
                    "vocabulary_register": "Vocabulary register",
                    "speech_patterns": ["Pattern"],
                    "rhetorical_tendencies": "Rhetorical tendency",
                    "gravitates_toward": ["Habit"],
                    "what_they_never_say": "Forbidden phrase",
                    "emotional_register": "Emotional register",
                    "sample_dialogues": [
                        {
                            "text": "Dialogue sample",
                            "why_representative": "Why representative",
                        }
                    ],
                }
            ],
            "real_world_context": {
                "written_when": "Written when",
                "historical_context": "Historical context",
                "unspeakable_constraints": ["Constraint"],
                "literary_tradition": "Literary tradition",
                "autobiographical_elements": "Autobiographical relevance",
            },
        }
    )
    return PromptRequest(
        system=(
            "You are performing a literary analysis of a novel to extract meta-level information "
            "for a character simulation engine. Return valid JSON only."
        ),
        user=(
            "NOVEL EXCERPTS (representative samples from across the novel):\n"
            f"{excerpt_block}\n\n"
            f"MAJOR CHARACTER IDS TO COVER: {json.dumps(major_character_ids)}\n\n"
            "Extract:\n"
            "1. AUTHORIAL LAYER: thesis, recurring themes, dominant tone, beliefs about power/love/morality/fate, motifs, perspective.\n"
            "2. WRITING STYLE: concrete prose description, rhythm, description density, dialogue/narration balance, stylistic signatures, representative sample passages.\n"
            "3. LANGUAGE CONTEXT: primary language, language variety, style of the language, style of the author, register profile, dialogue style, figurative patterns, multilingual features, and translation/localization notes useful for downstream prompts.\n"
            "4. CHARACTER VOICES: vocabulary/register, speech patterns, rhetorical tendencies, conversational gravity, what they never say, emotional register, sample dialogues.\n"
            "5. REAL-WORLD CONTEXT: written when, historical context, unspeakable constraints, literary tradition, autobiographical relevance.\n\n"
            "Rules:\n"
            "- Make the language context operational for future simulation prompts.\n"
            "- Treat sample passages and dialogue samples as short few-shot anchors.\n"
            "- Be specific, not flattering.\n"
            f"{_language_policy(excerpt_block)}"
            "- Output only JSON matching the meta-layer schema.\n\n"
            "OUTPUT CONTRACT:\n"
            f"{output_contract}"
        ),
        max_tokens=4_000,
        stream=False,
        metadata={
            "prompt_name": "p1_3_meta_layer",
            "response_schema": MetaLayerRecord.__name__,
        },
    )


def build_entity_extraction_prompt(
    accumulated: AccumulatedExtraction | None = None,
    *,
    context: dict[str, Any] | None = None,
    batch_index: int | None = None,
    batch_count: int | None = None,
) -> PromptRequest:
    if context is None:
        if accumulated is None:
            raise ValueError("Either accumulated or context must be provided for entity extraction")
        context = build_entity_extraction_context(accumulated)
    context_json = json.dumps(context, indent=2, sort_keys=True, ensure_ascii=False)
    output_contract = _json_contract(
        {
            "entities": [
                {
                    "entity_id": "ent_001",
                    "name": "Entity name",
                    "type": "object",
                    "objective_facts": ["Fact"],
                    "narrative_role": "Narrative role",
                    "absent_figure_details": {
                        "reason_absent": "",
                        "most_present_in": [],
                        "counterfactual": "",
                    },
                    "concept_details": {
                        "definitions_by_character": {"char_001": "Definition"},
                        "who_weaponizes": ["char_001"],
                        "who_is_bound_by": ["char_002"],
                        "authorial_stance": "Authorial stance",
                    },
                    "agent_representations": [
                        {
                            "agent_id": "char_001",
                            "belief": "Belief",
                            "emotional_charge": "Emotion",
                            "goal_relevance": "Why it matters",
                            "misunderstanding": "",
                            "confidence": "EXPLICIT",
                        }
                    ],
                }
            ]
        }
    )
    return PromptRequest(
        system=(
            "You are extracting the entity model for a character simulation engine. "
            "Entities are significant non-agent things: absent figures, objects, places, and concepts. "
            "Return valid JSON only."
        ),
        user=(
            "ENTITY EXTRACTION CONTEXT:\n"
            f"{context_json}\n\n"
            "Identify simulation-relevant entities and, for each one, extract:\n"
            "1. Identity: entity_id, name, type, objective facts, narrative role.\n"
            "2. Agent-relative representations: belief, emotional charge, goal relevance, misunderstanding, confidence.\n"
            "3. Absent-figure details when relevant.\n"
            "4. Concept-specific details when relevant.\n\n"
            "Rules:\n"
            "- Only include entities that meaningfully affect simulation behavior.\n"
            "- The context may be a condensed batch of the full novel state; infer only from the provided batch.\n"
            "- Use existing_entity_hints to deduplicate or refine prior entity guesses, not as license to invent.\n"
            "- Agent-relative meaning matters as much as objective facts.\n"
            f"{_language_policy(context_json)}"
            "- Output only JSON matching the entity extraction schema.\n\n"
            "OUTPUT CONTRACT:\n"
            f"{output_contract}"
        ),
        max_tokens=4_000,
        stream=False,
        metadata={
            "prompt_name": "p1_5_entity_extraction",
            "response_schema": EntityExtractionPayload.__name__,
            "batch_index": batch_index,
            "batch_count": batch_count,
        },
    )
