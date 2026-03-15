from __future__ import annotations

import asyncio
import json

from dreamdive.debug import DebugSession
from dreamdive.ingestion.chunker import TextChunk, estimate_token_count
from dreamdive.ingestion.extractor import ChapterSource
from dreamdive.ingestion.models import (
    AccumulatedExtraction,
    EntityExtractionPayload,
    MetaLayerRecord,
    StructuralScanPayload,
)
from dreamdive.llm.client import StructuredLLMClient
from dreamdive.llm.prompts import (
    build_chapter_extraction_prompt,
    build_entity_extraction_context,
    build_entity_extraction_prompt,
    build_meta_layer_prompt,
    build_structural_scan_prompt,
)

ENTITY_PASS_MAX_CONTEXT_TOKENS = 5_000
ENTITY_PASS_MAX_SPLIT_DEPTH = 6


class LLMExtractionBackend:
    """Prompt-driven extraction backend for P1.1 and P1.2."""

    def __init__(
        self,
        client: StructuredLLMClient,
        *,
        debug_session: DebugSession | None = None,
    ) -> None:
        self.client = client
        self.debug_session = debug_session

    def run_structural_scan(self, chunks: list[TextChunk]) -> object:
        if self.debug_session is not None:
            self.debug_session.event(
                "ingestion.structural_scan.start",
                chunk_count=len(chunks),
                approx_tokens=sum(chunk.approx_token_count for chunk in chunks),
            )
        prompt = build_structural_scan_prompt(chunks)
        try:
            result = asyncio.run(self.client.call_json(prompt, StructuralScanPayload)).model_dump(
                mode="json"
            )
        except Exception as exc:
            raise RuntimeError("Structural scan failed during ingestion") from exc
        if self.debug_session is not None:
            self.debug_session.event(
                "ingestion.structural_scan.done",
                character_count=len(result.get("cast_list", [])),
                location_count=len(result.get("world", {}).get("key_locations", [])),
            )
        return result

    def run_chapter_pass(
        self,
        chapter: ChapterSource,
        accumulated: AccumulatedExtraction,
        *,
        structural_scan: StructuralScanPayload | None = None,
    ) -> object:
        if self.debug_session is not None:
            self.debug_session.event(
                "ingestion.chapter.start",
                chapter_id=chapter.chapter_id,
                chapter_order=chapter.order_index,
                prior_character_count=len(accumulated.characters),
                prior_event_count=len(accumulated.events),
                has_structural_scan=structural_scan is not None,
            )
        prompt = build_chapter_extraction_prompt(
            chapter,
            accumulated,
            structural_scan=structural_scan,
        )
        try:
            result = asyncio.run(self.client.call_json(prompt, AccumulatedExtraction))
        except Exception as exc:
            title = chapter.title or chapter.chapter_id
            raise RuntimeError(
                f"Chapter extraction failed for {chapter.chapter_id} ({title})"
            ) from exc
        if self.debug_session is not None:
            self.debug_session.event(
                "ingestion.chapter.done",
                chapter_id=chapter.chapter_id,
                character_count=len(result.characters),
                event_count=len(result.events),
            )
        return result

    def run_meta_layer_pass(
        self,
        excerpts: list[str],
        *,
        major_character_ids: list[str],
    ) -> object:
        if self.debug_session is not None:
            self.debug_session.event(
                "ingestion.meta_layer.start",
                excerpt_count=len(excerpts),
                major_character_count=len(major_character_ids),
            )
        prompt = build_meta_layer_prompt(excerpts, major_character_ids=major_character_ids)
        try:
            result = asyncio.run(self.client.call_json(prompt, MetaLayerRecord)).model_dump(
                mode="json"
            )
        except Exception as exc:
            raise RuntimeError("Meta-layer extraction failed during ingestion") from exc
        if self.debug_session is not None:
            self.debug_session.event(
                "ingestion.meta_layer.done",
                voice_count=len(result.get("character_voices", [])),
                theme_count=len(result.get("authorial", {}).get("themes", [])),
            )
        return result

    def run_entity_pass(
        self,
        accumulated: AccumulatedExtraction,
    ) -> object:
        contexts = _build_entity_context_batches(
            build_entity_extraction_context(accumulated),
            max_tokens=ENTITY_PASS_MAX_CONTEXT_TOKENS,
        )
        if self.debug_session is not None:
            self.debug_session.event(
                "ingestion.entity_pass.start",
                character_count=len(accumulated.characters),
                event_count=len(accumulated.events),
                batch_count=len(contexts),
            )
        merged_result = {"entities": []}
        
        async def _call_batch(batch_index, context):
            prompt = build_entity_extraction_prompt(
                context=context,
                batch_index=batch_index,
                batch_count=len(contexts),
            )
            return await self.client.call_json(prompt, EntityExtractionPayload)

        async def _run_all():
            tasks = [
                _call_batch(i + 1, ctx)
                for i, ctx in enumerate(contexts)
            ]
            return await asyncio.gather(*tasks)

        try:
            batch_results = asyncio.run(_run_all())
            for batch_res in batch_results:
                merged_result = _merge_entity_payloads(
                    merged_result, 
                    batch_res.model_dump(mode="json")
                )
        except Exception as exc:
            raise RuntimeError("Entity extraction failed during ingestion") from exc
        if self.debug_session is not None:
            self.debug_session.event(
                "ingestion.entity_pass.done",
                entity_count=len(merged_result.get("entities", [])),
            )
        return merged_result


def _estimate_context_tokens(context: dict) -> int:
    return estimate_token_count(json.dumps(context, ensure_ascii=False, sort_keys=True))


def _build_entity_context_batches(
    context: dict,
    *,
    max_tokens: int,
    depth: int = 0,
) -> list[dict]:
    if _estimate_context_tokens(context) <= max_tokens or depth >= ENTITY_PASS_MAX_SPLIT_DEPTH:
        return [context]

    for key in ("event_spine", "character_cards", "existing_entity_hints"):
        items = context.get(key)
        if not isinstance(items, list) or len(items) <= 1:
            continue
        midpoint = max(1, len(items) // 2)
        left = dict(context)
        right = dict(context)
        left[key] = items[:midpoint]
        right[key] = items[midpoint:]
        return [
            *_build_entity_context_batches(left, max_tokens=max_tokens, depth=depth + 1),
            *_build_entity_context_batches(right, max_tokens=max_tokens, depth=depth + 1),
        ]

    return [context]


def _merge_entity_payloads(existing: dict, incoming: dict) -> dict:
    merged: dict[str, dict] = {}
    ordered_keys: list[str] = []
    for payload in (existing, incoming):
        for entity in payload.get("entities", []):
            key = _entity_merge_key(entity)
            if key not in merged:
                merged[key] = dict(entity)
                ordered_keys.append(key)
                continue
            merged[key] = _merge_entity_record_dicts(merged[key], entity)
    return {"entities": [merged[key] for key in ordered_keys]}


def _entity_merge_key(entity: dict) -> str:
    entity_id = str(entity.get("entity_id", "") or "").strip()
    if entity_id:
        return f"id:{entity_id}"
    entity_type = str(entity.get("type", "") or "").strip().lower()
    name = str(entity.get("name", "") or "").strip().lower()
    return f"name:{entity_type}:{name}"


def _merge_entity_record_dicts(existing: dict, incoming: dict) -> dict:
    merged = dict(existing)
    for field_name in ("entity_id", "name", "type", "narrative_role"):
        incoming_value = str(incoming.get(field_name, "") or "").strip()
        if incoming_value and not str(merged.get(field_name, "") or "").strip():
            merged[field_name] = incoming_value

    merged["objective_facts"] = _dedupe_non_empty(
        [*existing.get("objective_facts", []), *incoming.get("objective_facts", [])]
    )
    merged["agent_representations"] = _merge_agent_representations(
        existing.get("agent_representations", []),
        incoming.get("agent_representations", []),
    )
    merged["absent_figure_details"] = _merge_nested_entity_dict(
        existing.get("absent_figure_details", {}),
        incoming.get("absent_figure_details", {}),
        list_fields={"most_present_in"},
    )
    merged["concept_details"] = _merge_concept_details(
        existing.get("concept_details", {}),
        incoming.get("concept_details", {}),
    )
    return merged


def _merge_agent_representations(existing: list[dict], incoming: list[dict]) -> list[dict]:
    merged: dict[str, dict] = {}
    ordered_keys: list[str] = []
    for item in [*existing, *incoming]:
        agent_id = str(item.get("agent_id", "") or "").strip()
        key = agent_id or f"anon:{len(ordered_keys)}"
        if key not in merged:
            merged[key] = dict(item)
            ordered_keys.append(key)
            continue
        combined = dict(merged[key])
        for field_name in (
            "agent_id",
            "belief",
            "emotional_charge",
            "goal_relevance",
            "misunderstanding",
            "confidence",
        ):
            incoming_value = str(item.get(field_name, "") or "").strip()
            if incoming_value:
                combined[field_name] = incoming_value
        merged[key] = combined
    return [merged[key] for key in ordered_keys]


def _merge_concept_details(existing: dict, incoming: dict) -> dict:
    merged = _merge_nested_entity_dict(
        existing,
        incoming,
        list_fields={"who_weaponizes", "who_is_bound_by"},
    )
    definitions = dict(existing.get("definitions_by_character", {}))
    for key, value in incoming.get("definitions_by_character", {}).items():
        normalized_key = str(key).strip()
        normalized_value = str(value).strip()
        if normalized_key and normalized_value:
            definitions[normalized_key] = normalized_value
    merged["definitions_by_character"] = definitions
    return merged


def _merge_nested_entity_dict(existing: dict, incoming: dict, *, list_fields: set[str]) -> dict:
    merged = dict(existing)
    for key, value in incoming.items():
        if key in list_fields:
            merged[key] = _dedupe_non_empty([*existing.get(key, []), *value])
            continue
        normalized = str(value).strip() if isinstance(value, str) else value
        if normalized in ("", None, [], {}):
            continue
        merged[key] = normalized
    return merged


def _dedupe_non_empty(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = str(value or "").strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result
