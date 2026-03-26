from __future__ import annotations

import asyncio
import json

from dreamdive.debug import DebugSession
from dreamdive.ingestion.chunker import TextChunk, estimate_token_count
from dreamdive.ingestion.extractor import ChapterSource
from dreamdive.ingestion.models import (
    AccumulatedExtraction,
    DramaticBlueprintRecord,
    MetaLayerRecord,
    StructuralScanPayload,
)
from dreamdive.llm.client import StructuredLLMClient
from dreamdive.llm.prompts import (
    build_chapter_extraction_prompt,
    build_meta_layer_prompt,
    build_structural_scan_prompt,
)
from dreamdive.prompts.p1_ingestion import build_dramatic_blueprint_prompt


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

    def run_dramatic_blueprint_pass(
        self,
        accumulated: AccumulatedExtraction,
    ) -> object:
        if self.debug_session is not None:
            self.debug_session.event(
                "ingestion.dramatic_blueprint.start",
                character_count=len(accumulated.characters),
                event_count=len(accumulated.events),
            )
        prompt = build_dramatic_blueprint_prompt(accumulated)
        try:
            result = asyncio.run(self.client.call_json(prompt, DramaticBlueprintRecord))
        except Exception as exc:
            raise RuntimeError("Dramatic blueprint extraction failed during ingestion") from exc
        if self.debug_session is not None:
            self.debug_session.event(
                "ingestion.dramatic_blueprint.done",
                arc_count=len(result.character_arcs),
                conflict_count=len(result.major_conflicts),
            )
        return result.model_dump(mode="json")


