from __future__ import annotations

import json
from typing import Any, List

from dreamdive.ingestion.chunker import TextChunk
from dreamdive.ingestion.extractor import ChapterSource
from dreamdive.ingestion.models import (
    AccumulatedExtraction,
    DramaticBlueprintRecord,
    EntityExtractionPayload,
    FateExtensionRecord,
    MetaLayerRecord,
    StructuralScanPayload,
    TimelineSkeleton,
)
from dreamdive.language_guidance import format_language_guidance_block
from dreamdive.meta_injection import format_meta_section
from dreamdive.prompts.common import build_json_contract, build_source_language_policy
from dreamdive.schemas import PromptRequest
from dreamdive.user_config import UserMeta


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
            "setting": accumulated.world.setting
            or (structural_world.setting if structural_world else None),
            "time_period": accumulated.world.time_period
            or (structural_world.time_period if structural_world else None),
            "locations": _dedupe_strings(
                [
                    *accumulated.world.locations,
                    *(
                        location.name
                        for location in (
                            structural_world.key_locations if structural_world else []
                        )
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
                        faction.name
                        for faction in (
                            structural_world.factions if structural_world else []
                        )
                    ),
                ]
            ),
        },
        "domain_systems": [
            system.model_dump(mode="json")
            for system in (
                structural_scan.domain_systems if structural_scan is not None else []
            )
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
            current_state["goal_stack"] = _dedupe_strings(
                current_state.get("goal_stack", [])
            )[:4]
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
            "rules_and_constraints": _dedupe_strings(
                accumulated.world.rules_and_constraints
            ),
            "factions": _dedupe_strings(accumulated.world.factions),
        },
        "event_spine": event_spine,
        "existing_entity_hints": existing_entity_hints,
        "meta_hints": meta_hints,
    }


def build_structural_scan_prompt(
    chunks: List[TextChunk],
    *,
    user_meta: UserMeta | None = None,
) -> PromptRequest:
    joined_chunks = "\n\n".join(
        f"[{chunk.chunk_id} | approx_tokens={chunk.approx_token_count}]\n{chunk.text}"
        for chunk in chunks
    )
    system = (
        "You are initializing a character simulation engine from a novel. "
        "Build the structural skeleton that later chapter passes will extend. "
        "Do not invent facts. Return valid JSON only."
    )
    output_contract = build_json_contract(
        {
            "world": {
                "setting": "简洁的背景描述",
                "time_period": "时代",
                "rules_and_constraints": ["世界规则"],
                "factions": [
                    {
                        "name": "阵营名称",
                        "goal": "阵营目标",
                        "relationships": {"其他阵营": "关系"},
                    }
                ],
                "key_locations": [
                    {
                        "name": "地点名称",
                        "description": "简短描述",
                        "narrative_significance": "叙事意义",
                    }
                ],
            },
            "cast_list": [
                {
                    "id": "char_001",
                    "name": "角色名",
                    "aliases": ["别名"],
                    "role": "角色定位",
                    "first_appearance": "首次出场",
                    "tier": 2,
                }
            ],
            "timeline_skeleton": {
                "story_start": "故事开始时间",
                "pre_story_events": ["前史事件"],
                "known_future_events": ["伏笔暗示的未来事件"],
            },
            "domain_systems": [
                {
                    "name": "系统名称",
                    "description": "系统描述",
                    "scale": "等级体系",
                }
            ],
        }
    )
    meta_section = format_meta_section(novel_meta=None, user_meta=user_meta)
    meta_block = f"{meta_section}\n" if meta_section else ""

    user = (
        f"{meta_block}"
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
        f"{build_source_language_policy(joined_chunks)}"
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
    user_meta: UserMeta | None = None,
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
        "IMPORTANT: The context you receive was extracted by previous LLM passes and may contain errors, "
        "misidentifications, or false assignments (e.g., an unknown character incorrectly merged with a known one). "
        "This is an additive section pass: preserve existing data when it's correct, extend it with new information, "
        "and correct it when this chapter provides stronger evidence. When you detect errors in the provided context "
        "based on clear evidence in the current chapter text, create new correct records or update existing ones. "
        "Return valid JSON only."
    )
    output_contract = build_json_contract(
        {
            "characters": [
                {
                    "id": "char_001",
                    "name": "角色名",
                    "aliases": ["别名"],
                    "identity": {"role": "身份信息"},
                    "personality": {"trait": "性格特征"},
                    "current_state": {
                        "emotional_state": "简短的情感状态",
                        "physical_state": "简短的身体状态",
                        "location": "地点",
                        "goal_stack": ["具体目标"],
                    },
                    "relationships": [
                        {
                            "target_id": "char_002",
                            "type": "关系类型",
                            "trust": 0.5,
                            "sentiment": "情感倾向",
                            "shared_history_summary": "简短的共同经历",
                        }
                    ],
                    "memory_seeds": [
                        {
                            "summary": "被确认为S级血统持有者的那一刻，他只觉得荒谬又发冷，像是命运突然把自己推进了一个陌生而危险的世界。",
                            "time": "3E考试后",
                            "location": "卡塞尔学院",
                        }
                    ],
                }
            ],
            "world": {
                "setting": "故事背景设定",
                "time_period": "时代",
                "locations": ["地点名称"],
                "rules_and_constraints": ["世界规则"],
                "factions": ["阵营名称"],
            },
            "events": [
                {
                    "id": "evt_001",
                    "time": "时间",
                    "location": "地点",
                    "participants": ["char_001"],
                    "summary": "客观事件概述",
                    "consequences": ["后果"],
                    "participant_knowledge": {"char_001": "该角色知道的"},
                }
            ],
            "entities": [
                {
                    "entity_id": "ent_001",
                    "name": "实体名称",
                    "type": "object",
                    "objective_facts": ["客观事实"],
                    "narrative_role": "叙事作用",
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
                            "belief": "该角色的认知",
                            "emotional_charge": "情感",
                            "goal_relevance": "为什么重要",
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
    meta_section = format_meta_section(
        novel_meta=accumulated.meta if accumulated.meta else None,
        user_meta=user_meta,
    )
    meta_block = f"{meta_section}\n" if meta_section else ""

    user = (
        f"{meta_block}"
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
        "- CRITICAL: The retrieved context was generated by prior LLM extraction and is NOT 100% accurate.\n"
        "- Validate all context against the current chapter text. If a character ID, name, alias, or relationship "
        "contradicts clear evidence in this chapter, prioritize the chapter text over the context.\n"
        "- When uncertain whether a character mentioned in this chapter is the same as one in the retrieved context, "
        "prefer creating a new character with a new ID rather than incorrectly merging distinct characters.\n"
        "- You can correct errors: if context misidentified someone or merged distinct people, create correct separate records.\n"
        "- Return only deltas: new records, changed records, or newly supported fields from this section.\n"
        "- Omit unchanged characters, events, entities, and world/meta fields entirely.\n"
        "- Within a returned record, include only fields that this section supports or updates.\n"
        "- The ingestion pipeline will merge your delta into the accumulated database.\n"
        "- Treat retrieved character cards as the only prior character state you need for this section.\n"
        "- If a chapter character is missing from the retrieved cards, create a new character record from the chapter text.\n"
        "- Each character record must describe only that character. Do not blend one person's body, motives, or inner thoughts with another nearby character.\n"
        "- When a scene strongly centers one viewpoint character, keep other characters' `current_state`, goals, and memory seeds limited to what this section directly supports for them.\n"
        "- Goals must be concrete intentions, not traits.\n"
        "- Relationship directionality matters.\n"
        "- Memory seeds must be short structured records with `summary`, `time`, and `location`.\n"
        "- Each `summary` must be a full-sentence subjective recollection from that character's perspective, not a terse objective plot bullet.\n"
        "- Each memory seed should capture how the moment felt, what it meant, or why it would stay with that character emotionally.\n"
        "- Keep `time` and `location` concise and concrete; use null only when the chapter truly does not support them.\n"
        "- Prefer a few vivid memory seeds over many thin ones.\n"
        f"{build_source_language_policy(chapter.text)}"
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
    user_meta: UserMeta | None = None,
    web_research_context: str = "",
) -> PromptRequest:
    excerpt_block = "\n\n".join(excerpts)
    output_contract = build_json_contract(
        {
            "authorial": {
                "central_thesis": {"summary": "用原文语言写的核心命题"},
                "themes": [
                    {
                        "name": "主题名称",
                        "description": "主题描述",
                        "confidence": "INFERRED",
                    }
                ],
                "dominant_tone": "主导基调",
                "beliefs_about": {"power": "关于权力的信念"},
                "symbolic_motifs": ["象征意象"],
                "narrative_perspective": "叙事视角",
            },
            "writing_style": {
                "prose_description": "散文风格描述",
                "sentence_rhythm": "句子节奏",
                "description_density": "描写密度",
                "dialogue_narration_balance": "对话与叙事的平衡",
                "chapter_format": {
                    "heading_style": "章节标题的格式风格",
                    "heading_examples": ["原文章节标题示例"],
                    "opening_pattern": "章节通常如何开头",
                    "closing_pattern": "章节通常如何结尾",
                    "paragraphing_style": "段落分隔方式",
                },
                "stylistic_signatures": ["风格标志"],
                "sample_passages": [
                    {
                        "text": "原文中的短段落样本",
                        "why_representative": "为什么有代表性",
                    }
                ],
            },
            "language_context": {
                "primary_language": "Chinese",
                "language_variety": "语言变体",
                "language_style": "语言风格",
                "author_style": "作者风格",
                "register_profile": "语域特征",
                "dialogue_style": "对话风格",
                "figurative_patterns": ["修辞手法"],
                "multilingual_features": ["多语言特征"],
                "translation_notes": ["翻译注意事项"],
            },
            "character_voices": [
                {
                    "character_id": "char_001",
                    "vocabulary_register": "词汇语域",
                    "speech_patterns": ["说话模式"],
                    "rhetorical_tendencies": "修辞倾向",
                    "gravitates_toward": ["惯用表达"],
                    "what_they_never_say": "绝不会说的话",
                    "emotional_register": "情感语域",
                    "sample_dialogues": [
                        {
                            "text": "原文对话样本",
                            "why_representative": "为什么有代表性",
                        }
                    ],
                }
            ],
            "real_world_context": {
                "written_when": "写作年代",
                "historical_context": "历史背景",
                "historical_moment": "时代质感",
                "anxieties_encoded": ["编码在故事中的焦虑"],
                "what_story_is_secretly_about": "故事真正在讲的事",
                "biographical_influences": "传记影响",
                "what_author_could_not_conceive": ["作者无法想象的事"],
                "unspeakable_constraints": ["不可言说的限制"],
                "literary_tradition": "文学传统",
                "in_dialogue_with": ["对话的前辈作品"],
                "autobiographical_elements": "自传元素",
            },
            "tone_and_register": {
                "dominant_register": "主导语域",
                "emotional_contract": "与读者的情感契约",
                "how_author_handles": {
                    "death": "处理死亡的方式",
                    "violence": "处理暴力的方式",
                    "love": "处理爱情的方式",
                    "humor": "幽默的功能",
                },
                "what_prose_does_to_reader": "文字对读者的效果",
                "tonal_range": "基调范围",
                "sentence_level_markers": ["句子层面的标志"],
                "what_author_refuses_tonally": ["作者在基调上拒绝的事"],
            },
            "authors_taste": {
                "recurring_preoccupations": ["反复出现的主题关注"],
                "finds_interesting": ["作者觉得有趣的"],
                "finds_uninteresting": ["作者觉得无趣的"],
                "moral_sensibility_toward_characters": "对角色的道德态度",
                "categorical_refusals": ["绝对拒绝的事"],
                "signature_moves": ["标志性手法"],
                "aesthetic_values": "美学价值观",
            },
            "design_tendencies": {
                "character_construction": {
                    "method": "塑造方法",
                    "what_makes_character_real": "角色真实感的来源",
                    "how_change_works": "角色变化的方式",
                    "recurring_types": ["常见角色类型"],
                },
                "world_building": {
                    "historical_texture": "历史质感",
                    "rule_consistency": "规则一致性",
                    "priorities": ["世界观优先事项"],
                    "introduction_method": "世界展示方式",
                },
                "story_architecture": {
                    "structure_and_pacing": "结构与节奏",
                    "time_management": "时间处理方式",
                    "revelation_strategy": "揭示策略",
                    "what_makes_scene_good": "好场景的标准",
                    "chapter_architecture": "章节结构",
                    "foreshadowing_method": "伏笔方法",
                },
            },
        }
    )
    meta_section = format_meta_section(novel_meta=None, user_meta=user_meta)
    meta_block = f"{meta_section}\n" if meta_section else ""
    research_block = ""
    if web_research_context:
        research_block = (
            f"\n{web_research_context}\n"
            "Use the web research above as additional evidence — it provides external "
            "context about the author's biography, literary reputation, known influences, "
            "and critical reception that cannot be inferred from the novel text alone. "
            "Mark claims derived from web research as [CONTEXTUAL].\n\n"
        )

    return PromptRequest(
        system=(
            "You are performing a deep literary analysis of a novel to extract "
            "a complete authorial meta profile for a story simulation engine. "
            "You have access to both the novel text AND external research about the author. "
            "This profile serves four functions: "
            "(1) Narrative synthesis — every generated chapter must sound like this author. "
            "(2) Fate extension — new story elements must fit this author's aesthetic logic. "
            "(3) Character voice — dialogue must match each character's established register. "
            "(4) Simulation constraints — what this world can and cannot produce. "
            "Return valid JSON only."
        ),
        user=(
            f"{meta_block}"
            "NOVEL EXCERPTS (representative samples: opening, middle, climax, resolution):\n"
            f"{excerpt_block}\n\n"
            f"{research_block}"
            f"MAJOR CHARACTER IDS TO COVER: {json.dumps(major_character_ids)}\n\n"
            "Extract all areas below. For each claim mark:\n"
            "  [EXPLICIT]    directly stated in text\n"
            "  [INFERRED]    derived from patterns across the novel\n"
            "  [CONTEXTUAL]  requires external knowledge to establish\n\n"
            "AREA 1: TONE & REGISTER\n"
            "- Dominant emotional register (not a single adjective — the specific emotional contract)\n"
            "- How the author handles: death, violence, love, humor\n"
            "- What the prose does to the reader sentence by sentence\n"
            "- Tonal range and flexibility\n"
            "- 3-5 sentence-level tonal markers (rhythmic or imagistic patterns)\n"
            "- What the author categorically refuses tonally\n\n"
            "AREA 2: REAL-WORLD CONTEXT\n"
            "- When exactly written and the specific historical moment\n"
            "- Anxieties from the author's real world encoded in the story\n"
            "- What the story is secretly about at the level of the author's world\n"
            "- Biographical context that structurally shapes the work\n"
            "- What the author genuinely could NOT have conceived (constrains Fate extension)\n"
            "- Literary tradition relationship and who they are in dialogue with\n"
            "- What characters cannot say or do given their context\n\n"
            "AREA 3: AUTHOR'S TASTE\n"
            "- Recurring preoccupations (subjects they return to obsessively)\n"
            "- What they find genuinely interesting vs. uninteresting or beneath them\n"
            "- Moral sensibility toward characters (love and destroy / ironic distance / etc.)\n"
            "- Categorical aesthetic refusals\n"
            "- Signature moves they can't resist\n"
            "- What this author believes a novel should do (aesthetic values)\n\n"
            "AREA 4: DESIGN TENDENCIES\n"
            "- Character construction: method, what makes character real, how change works, types\n"
            "- World-building: historical texture, rule consistency, priorities, introduction method\n"
            "- Story architecture: pacing, time management, revelation strategy, scene criteria, "
            "chapter structure, foreshadowing method\n\n"
            "AREA 5: AUTHORIAL LAYER, WRITING STYLE, LANGUAGE CONTEXT & CHARACTER VOICES\n"
            "- Thesis, recurring themes, dominant tone, beliefs, motifs, perspective\n"
            "- Concrete prose description, rhythm, description density, chapter formatting, signatures, samples\n"
            "- Language context for downstream simulation prompts\n"
            "- Per-character voice: vocabulary, speech patterns, rhetorical tendencies, "
            "what they never say, sample dialogues\n\n"
            "Rules:\n"
            "- Make the language context operational for future simulation prompts.\n"
            "- Treat sample passages and dialogue samples as short few-shot anchors.\n"
            "- Be specific, not flattering.\n"
            "- The author's categorical refusals and signature moves together define the "
            "space of permissible new story. This is critical for Fate extension.\n"
            "- 'What they never say' is as important as how they speak.\n"
            f"{build_source_language_policy(excerpt_block)}"
            "- Output only JSON matching the meta-layer schema.\n\n"
            "OUTPUT CONTRACT:\n"
            f"{output_contract}"
        ),
        max_tokens=6_000,
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
    user_meta: UserMeta | None = None,
) -> PromptRequest:
    if context is None:
        if accumulated is None:
            raise ValueError(
                "Either accumulated or context must be provided for entity extraction"
            )
        context = build_entity_extraction_context(accumulated)
    context_json = json.dumps(context, indent=2, sort_keys=True, ensure_ascii=False)
    output_contract = build_json_contract(
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
    novel_meta_obj = accumulated.meta if accumulated else None
    meta_section = format_meta_section(novel_meta=novel_meta_obj, user_meta=user_meta)
    meta_block = f"{meta_section}\n" if meta_section else ""

    return PromptRequest(
        system=(
            "You are extracting the entity model for a character simulation engine. "
            "Entities are significant non-agent things: absent figures, objects, places, and concepts. "
            "IMPORTANT: The context you receive (character cards, events, existing entity hints) was extracted "
            "by previous LLM passes and may contain errors or inconsistencies. Validate and refine it based on "
            "the evidence provided in the context. "
            "Return valid JSON only."
        ),
        user=(
            f"{meta_block}"
            "ENTITY EXTRACTION CONTEXT:\n"
            f"{context_json}\n\n"
            "Identify simulation-relevant entities and, for each one, extract:\n"
            "1. Identity: entity_id, name, type, objective facts, narrative role.\n"
            "2. Agent-relative representations: belief, emotional charge, goal relevance, misunderstanding, confidence.\n"
            "3. Absent-figure details when relevant.\n"
            "4. Concept-specific details when relevant.\n\n"
            "Rules:\n"
            "- CRITICAL: The provided context was generated by prior LLM extraction and may contain errors.\n"
            "- Only include entities that meaningfully affect simulation behavior.\n"
            "- The context may be a condensed batch of the full novel state; infer only from the provided batch.\n"
            "- Use existing_entity_hints to deduplicate or refine prior entity guesses, not as license to invent.\n"
            "- If existing_entity_hints contain incorrect assignments or duplicates, create correct separate entities.\n"
            "- Agent-relative meaning matters as much as objective facts.\n"
            f"{build_source_language_policy(context_json)}"
            "- Output only JSON matching the entity extraction schema.\n\n"
            "OUTPUT CONTRACT:\n"
            f"{output_contract}"
        ),
        max_tokens=8_000,
        stream=False,
        metadata={
            "prompt_name": "p1_5_entity_extraction",
            "response_schema": EntityExtractionPayload.__name__,
            "batch_index": batch_index,
            "batch_count": batch_count,
        },
    )


def build_dramatic_blueprint_prompt(
    accumulated: AccumulatedExtraction,
    *,
    user_meta: UserMeta | None = None,
    language_guidance: str = "",
) -> PromptRequest:
    """P1.6 — Dramatic Blueprint Extraction.

    Runs once during ingestion after all chapter passes are complete.
    Requires holistic read of accumulated extraction data.
    """
    # Compact character models — only fields needed for dramatic blueprint
    compact_characters = []
    for record in accumulated.characters:
        identity = _first_non_empty_mapping_values(
            record.identity,
            preferred_keys=["role", "title", "occupation", "affiliation", "status"],
            max_items=3,
        )
        compact_characters.append({
            "id": record.id,
            "name": record.name,
            "identity": identity,
            "current_state": {
                k: v for k, v in _non_empty_state(record.current_state.model_dump(mode="json")).items()
                if k in ("emotional_state", "goal_stack", "location", "status")
            },
            "relationships": [
                {"target_id": r.target_id, "type": r.type, "summary": r.summary}
                for r in record.relationships[:5]
            ],
        })
    character_cards_json = json.dumps(compact_characters, indent=1, ensure_ascii=False)

    # Compact timeline — summary and participants only
    compact_events = [
        {
            "id": event.id,
            "time": event.time,
            "participants": _dedupe_strings(event.participants),
            "summary": event.summary,
        }
        for event in accumulated.events
    ]
    timeline_json = json.dumps(compact_events, indent=1, ensure_ascii=False)

    # Compact meta — only structural aspects needed for blueprint
    meta_compact = {
        "themes": [{"name": t.name, "description": t.description} for t in accumulated.meta.authorial.themes[:4]],
        "tone": accumulated.meta.tone_and_register.model_dump(mode="json"),
        "design_tendencies": accumulated.meta.design_tendencies.model_dump(mode="json"),
    }
    meta_json = json.dumps(meta_compact, indent=1, ensure_ascii=False)
    output_contract = build_json_contract(
        {
            "central_question": "故事的主题脊柱（可以用是/否回答）",
            "thematic_payload": "故事在情节之下真正在讲什么",
            "dramatic_clock": "在整个故事中制造宏观紧迫感的因素",
            "current_phase": "exposition | rising_action | climax | falling_action | resolution",
            "world_truths": [
                {
                    "id": "truth_001",
                    "description": "真正的事实是什么",
                    "reveal_state": "concealed",
                    "reveal_conditions": ["需要发生什么才能揭示"],
                    "reveal_cost": "揭示后会改变什么",
                    "knowers": ["char_001"],
                }
            ],
            "character_arcs": [
                {
                    "character_id": "char_001",
                    "starting_condition": "故事开始时他们是谁",
                    "central_tension": "驱动其弧线的力量",
                    "designed_transformation": "旅程的形状",
                    "dramatic_question_role": "与核心问题的关系",
                    "arc_phase": "early | middle | late | complete",
                    "on_arc": True,
                    "drift_note": "",
                }
            ],
            "major_conflicts": [
                {
                    "id": "conflict_001",
                    "description": "故事构建的大型结构性碰撞",
                    "parties": ["faction_a", "faction_b"],
                    "current_state": "building",
                    "dramatic_weight": 0.8,
                }
            ],
        }
    )
    meta_section = format_meta_section(
        novel_meta=accumulated.meta,
        user_meta=user_meta,
    )
    meta_block = f"{meta_section}\n" if meta_section else ""

    language_block = format_language_guidance_block(language_guidance)

    return PromptRequest(
        system=(
            "You are extracting the dramatic blueprint of a novel. "
            "This is the hidden structural architecture — the facts, arcs, and "
            "designs that exist beneath the surface narrative and guide the whole story. "
            "Do not invent — extract only what is in the source material. "
            "Return valid JSON only."
        ),
        user=(
            f"{language_block}"
            f"{meta_block}"
            "All free-text values must be in the source material's language. "
            "JSON keys remain in English.\n\n"
            "CHARACTER MODELS:\n"
            f"{character_cards_json}\n\n"
            "NOVEL TIMELINE:\n"
            f"{timeline_json}\n\n"
            "META LAYER:\n"
            f"{meta_json}\n\n"
            "Extract the dramatic blueprint across three levels.\n\n"
            "LEVEL 1: WORLD DESIGN\n"
            "- Hidden structural truths operating beneath the surface narrative\n"
            "  (forces, facts, or conditions that exist but are not fully understood by characters)\n"
            "- The dramatic clock: what creates macro-level urgency across the whole story?\n"
            "- What does the world ultimately punish or reward, regardless of what characters believe?\n\n"
            "LEVEL 2: CHARACTER ARC DESIGN\n"
            "Cover ALL named or recurring characters, not just the protagonists.\n"
            "Any character who has a name, appears in multiple scenes, or whose actions\n"
            "affect the plot should have an arc entry.\n\n"
            "For MAJOR characters (protagonists, key antagonists, central allies):\n"
            "- Starting condition (who they are when the story begins)\n"
            "- Central dramatic tension (the force driving their arc)\n"
            "- Designed transformation or endpoint (the shape of the journey — not specific events)\n"
            "- Their relationship to the central dramatic question\n"
            "- What they must lose, learn, or become\n\n"
            "For SECONDARY and MINOR named characters (mentors, rivals, supporting cast,\n"
            "recurring named figures):\n"
            "- Starting condition\n"
            "- Central tension (can be concise)\n"
            "- Designed transformation (can be shorter — even one sentence is fine)\n"
            "- Their thematic function in the story\n\n"
            "LEVEL 3: DRAMATIC DESIGN\n"
            "- The central dramatic question (the thematic spine — answerable yes or no by the end)\n"
            "- Major structural conflicts (large collisions the story builds toward)\n"
            "- Hidden truths: facts that exist from the beginning but are revealed over time\n"
            "  For each: what is true, who knows it, reveal conditions, what revelation costs\n"
            "- The thematic payload: what the story is actually about beneath the plot\n\n"
            "Rules:\n"
            "- Think at the level of arc shape, not specific events\n"
            "- Distinguish between what characters believe and what is structurally true\n"
            "- Hidden truths should be things that, when revealed, reframe what came before\n"
            "- The dramatic question should be answerable yes or no by the end of the story\n"
            "- Do not invent — extract only what is in the source material\n"
            "- Output only JSON matching the dramatic blueprint schema.\n\n"
            "OUTPUT CONTRACT:\n"
            f"{output_contract}"
        ),
        max_tokens=10_000,
        stream=False,
        metadata={
            "prompt_name": "p1_6_dramatic_blueprint",
            "response_schema": DramaticBlueprintRecord.__name__,
        },
    )


def build_fate_extension_prompt(
    extracted_fate: DramaticBlueprintRecord,
    accumulated: AccumulatedExtraction,
    *,
    snapshot_t: str = "",
    user_meta: UserMeta | None = None,
    language_guidance: str = "",
) -> PromptRequest:
    """P1.7 — Fate Extension.

    Runs after P1.6 (extraction) and after P0 (user configuration).
    Takes extracted Fate as foundation, authorial fidelity profile as constraint,
    and user configuration as direction.
    """
    extracted_fate_json = json.dumps(
        extracted_fate.model_dump(mode="json"),
        indent=1,
        ensure_ascii=False,
    )
    authorial_fidelity_json = json.dumps(
        {
            "tone_and_register": accumulated.meta.tone_and_register.model_dump(mode="json"),
            "design_tendencies": accumulated.meta.design_tendencies.model_dump(mode="json"),
        },
        indent=1,
        ensure_ascii=False,
    )
    user_config_block = ""
    if user_meta is not None:
        user_parts = []
        if user_meta.divergence_seeds:
            user_parts.append(
                "Divergence seeds: "
                + "; ".join(seed.description for seed in user_meta.divergence_seeds)
            )
        if user_meta.tone.overall:
            user_parts.append(f"Tone direction: {user_meta.tone.overall}")
        if user_meta.free_notes:
            user_parts.append(f"Free notes: {user_meta.free_notes}")
        if user_parts:
            user_config_block = "\n".join(user_parts) + "\n"

    output_contract = build_json_contract(
        {
            "arc_extensions": [
                {
                    "character_id": "char_001",
                    "starting_condition": "角色在快照T时刻的状态",
                    "central_tension": "从T时刻延伸的核心张力",
                    "designed_transformation": "接下来的变化走向",
                    "dramatic_question_role": "在戏剧性问题中的角色",
                    "arc_phase": "early",
                    "on_arc": True,
                    "drift_note": "",
                }
            ],
            "new_hidden_truths": [
                {
                    "id": "ext_truth_001",
                    "description": "符合这个世界的新真相",
                    "reveal_state": "concealed",
                    "reveal_conditions": ["需要发生什么才能揭示"],
                    "reveal_cost": "揭示后会改变什么",
                    "knowers": [],
                }
            ],
            "new_conflicts": [
                {
                    "id": "ext_conflict_001",
                    "description": "由分歧种下的新冲突",
                    "parties": ["faction_a", "faction_b"],
                    "current_state": "building",
                    "dramatic_weight": 0.7,
                }
            ],
            "dramatic_clock_extension": "宏观紧迫感如何从T时刻演化",
        }
    )

    language_block = format_language_guidance_block(language_guidance)

    return PromptRequest(
        system=(
            "You are extending the Fate of a story beyond what the original novel describes. "
            "The simulation will diverge from the source material starting at snapshot point T. "
            "You must design Fate that governs the simulation from that point forward. "
            "Everything you design must feel like it could belong in the original author's work. "
            "Return valid JSON only."
        ),
        user=(
            f"{language_block}"
            "All free-text values must be in the source material's language. "
            "JSON keys remain in English.\n\n"
            "FOUNDATION — EXTRACTED FATE (Layer A, authoritative):\n"
            f"{extracted_fate_json}\n\n"
            "AUTHORIAL FIDELITY PROFILE (from P1.3 meta layer):\n"
            f"{authorial_fidelity_json}\n\n"
            f"USER CONFIGURATION (Layer C, highest priority where specified):\n"
            f"{user_config_block}\n"
            f"SIMULATION SNAPSHOT POINT: {snapshot_t or 'latest available'}\n"
            "This is where the story branches. Everything before T is established.\n"
            "Everything after T is yours to design — within the above constraints.\n\n"
            "Design the following for Layer B:\n\n"
            "1. ARC EXTENSIONS\n"
            "   For ALL named or recurring characters from the extracted fate (not just\n"
            "   the protagonists): given their arc shape up to T, extend the designed\n"
            "   trajectory forward. Not what will happen — the shape of what comes next.\n"
            "   Stay true to the author's way of completing arcs.\n\n"
            "   Major characters should receive detailed extensions with full tension\n"
            "   and transformation descriptions. Secondary and minor named characters\n"
            "   can have shorter extensions — even a sentence or two — but every named\n"
            "   character in the extracted fate MUST have a corresponding arc extension.\n\n"
            "2. NEW HIDDEN TRUTHS\n"
            "   Design 2-4 new hidden truths that don't exist in the source novel\n"
            "   but fit naturally in this world. Each must:\n"
            "   - Follow the author's structural instincts\n"
            "   - Have a reveal condition and a reveal cost\n"
            "   - Reframe something when revealed\n"
            "   - Feel inevitable in retrospect\n\n"
            "3. NEW CONFLICTS\n"
            "   Design 1-3 new major conflicts seeded by the divergence from T.\n"
            "   These emerge from the changed conditions. They must feel like\n"
            "   conflicts this author would have constructed.\n\n"
            "4. DRAMATIC CLOCK EXTENSION\n"
            "   How does the macro-level urgency evolve from T onward?\n"
            "   What new pressures emerge? Does the existing clock accelerate?\n\n"
            "For every element you design, ask:\n"
            "  'Would this author have written this?'\n"
            "  'Does it follow the world's moral logic?'\n"
            "  'Does it fit the thematic payload of the original?'\n\n"
            "Do not invent for novelty's sake. Invent in service of the story's\n"
            "existing gravity. The best agent-designed Fate feels like it was\n"
            "always there, waiting.\n\n"
            "OUTPUT CONTRACT:\n"
            f"{output_contract}"
        ),
        max_tokens=6_000,
        stream=False,
        metadata={
            "prompt_name": "p1_7_fate_extension",
            "response_schema": FateExtensionRecord.__name__,
        },
    )


__all__ = [
    "build_chapter_extraction_prompt",
    "build_dramatic_blueprint_prompt",
    "build_entity_extraction_context",
    "build_entity_extraction_prompt",
    "build_fate_extension_prompt",
    "build_meta_layer_prompt",
    "build_structural_scan_prompt",
]
