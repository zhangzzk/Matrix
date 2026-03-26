"""P5 Narrative Synthesis Layer - converts simulation events to novel chapters.

This layer reads event windows from the simulation database and writes them
as prose in the style of the source material, shaped by user preferences.
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from dreamdive.ingestion.models import MetaLayerRecord
from dreamdive.ingestion.source_loader import (
    format_synthesized_chapter_heading,
    looks_like_chapter_heading,
)
from dreamdive.llm.client import StructuredLLMClient
from dreamdive.prompts import (
    build_chapter_summary_prompt,
    build_chapter_synthesis_prompt,
    build_unified_synthesis_prompt,
)
from dreamdive.schemas import UnifiedSynthesisPayload
from dreamdive.user_config import UserMeta


class EventSummary(BaseModel):
    """Condensed event for synthesis prompt."""

    event_id: str
    salience: float = Field(ge=0.0, le=1.0)
    participants: List[str] = Field(default_factory=list)
    location: str = ""
    summary: str
    scene_transcript: str = ""  # For external events
    state_changes: Dict[str, Any] = Field(default_factory=dict)


class ChapterWindow(BaseModel):
    """Event window for one chapter synthesis."""

    tick_range: str
    events: List[EventSummary] = Field(default_factory=list)
    high_salience_events: List[str] = Field(default_factory=list)


class ChapterSummary(BaseModel):
    """Summary of a written chapter for continuity."""

    chapter_number: int
    summary: str
    open_threads: List[str] = Field(default_factory=list)
    key_state_changes: Dict[str, str] = Field(default_factory=dict)


class ChapterTextResponse(BaseModel):
    """Wrapper for chapter synthesis text response."""

    chapter_text: str


class ChapterSummaryResponse(BaseModel):
    """Wrapper for chapter summary text response."""

    summary: str


class CharacterStateSummary(BaseModel):
    """Character state at chapter boundary for continuity."""

    name: str
    location: str = ""
    emotional_state: str = ""
    active_goals: List[str] = Field(default_factory=list)


class NarrativeSynthesisBackend:
    """Backend for P5 narrative synthesis operations."""

    def __init__(self, client: StructuredLLMClient) -> None:
        self.client = client

    async def synthesize_chapter_async(
        self,
        event_window: ChapterWindow,
        novel_meta: MetaLayerRecord,
        user_meta: UserMeta,
        *,
        chapter_number: int | None = None,
        previous_chapter_summary: Optional[ChapterSummary] = None,
        narrative_arc_unresolved_threads: Optional[List[str]] = None,
        character_states: Optional[List[CharacterStateSummary]] = None,
        author: str = "",
        voice_samples: Optional[List[str]] = None,
        source_heading_examples: Optional[List[str]] = None,
    ) -> str:
        """Synthesize simulation events into a novel chapter (async).

        Args:
            event_window: Events to synthesize
            novel_meta: Novel meta layer (style, themes, etc.)
            user_meta: User preferences
            previous_chapter_summary: Summary of previous chapter for continuity
            narrative_arc_unresolved_threads: Open thematic threads
            character_states: Character states at chapter start for continuity
            author: Novel author name
            voice_samples: Sample passages from original novel

        Returns:
            Chapter text as prose

        Raises:
            RuntimeError: If synthesis fails
        """
        prompt = build_chapter_synthesis_prompt(
            event_window=event_window,
            novel_meta=novel_meta,
            user_meta=user_meta,
            chapter_number=chapter_number,
            previous_chapter_summary=previous_chapter_summary,
            narrative_arc_unresolved_threads=narrative_arc_unresolved_threads,
            character_states=character_states,
            author=author,
            voice_samples=voice_samples,
            source_heading_examples=source_heading_examples,
        )

        try:
            # Use call_text for prose generation
            response = await self.client.call_text(prompt)
            return self._normalize_chapter_text(
                response,
                chapter_number=chapter_number,
                source_heading_examples=source_heading_examples,
            )
        except Exception as exc:
            raise RuntimeError(
                f"Chapter synthesis failed for tick range {event_window.tick_range}"
            ) from exc

    def synthesize_chapter(
        self,
        event_window: ChapterWindow,
        novel_meta: MetaLayerRecord,
        user_meta: UserMeta,
        *,
        chapter_number: int | None = None,
        previous_chapter_summary: Optional[ChapterSummary] = None,
        narrative_arc_unresolved_threads: Optional[List[str]] = None,
        character_states: Optional[List[CharacterStateSummary]] = None,
        author: str = "",
        voice_samples: Optional[List[str]] = None,
        source_heading_examples: Optional[List[str]] = None,
    ) -> str:
        """Synthesize simulation events into a novel chapter (sync wrapper).

        See synthesize_chapter_async for full documentation.
        """
        return asyncio.run(
            self.synthesize_chapter_async(
                event_window=event_window,
                novel_meta=novel_meta,
                user_meta=user_meta,
                chapter_number=chapter_number,
                previous_chapter_summary=previous_chapter_summary,
                narrative_arc_unresolved_threads=narrative_arc_unresolved_threads,
                character_states=character_states,
                author=author,
                voice_samples=voice_samples,
                source_heading_examples=source_heading_examples,
            )
        )

    async def summarize_chapter_async(self, chapter_text: str) -> str:
        """Summarize a chapter for continuity (async).

        Args:
            chapter_text: Full chapter prose

        Returns:
            150-200 word summary

        Raises:
            RuntimeError: If summarization fails
        """
        prompt = build_chapter_summary_prompt(chapter_text)

        try:
            # Use call_text for summary generation
            response = await self.client.call_text(prompt)
            return response
        except Exception as exc:
            raise RuntimeError("Chapter summarization failed") from exc

    def summarize_chapter(self, chapter_text: str) -> str:
        """Summarize a chapter for continuity (sync wrapper).

        See summarize_chapter_async for full documentation.
        """
        return asyncio.run(self.summarize_chapter_async(chapter_text))

    # ------------------------------------------------------------------
    # Unified synthesis + summary (optimization #4)
    # ------------------------------------------------------------------

    async def synthesize_and_summarize_async(
        self,
        event_window: ChapterWindow,
        novel_meta: MetaLayerRecord,
        user_meta: UserMeta,
        *,
        chapter_number: int | None = None,
        previous_chapter_summary: Optional[ChapterSummary] = None,
        narrative_arc_unresolved_threads: Optional[List[str]] = None,
        character_states: Optional[List[CharacterStateSummary]] = None,
        author: str = "",
        voice_samples: Optional[List[str]] = None,
        source_heading_examples: Optional[List[str]] = None,
    ) -> tuple[str, str]:
        """Synthesize a chapter and produce its summary in a single LLM call.

        This merges the work of ``synthesize_chapter_async`` and
        ``summarize_chapter_async`` into one request, saving one full
        round-trip to the LLM.

        Returns:
            A ``(chapter_text, summary)`` tuple.

        Raises:
            RuntimeError: If the unified call fails.
        """
        prompt = build_unified_synthesis_prompt(
            event_window=event_window,
            novel_meta=novel_meta,
            user_meta=user_meta,
            chapter_number=chapter_number,
            previous_chapter_summary=previous_chapter_summary,
            narrative_arc_unresolved_threads=narrative_arc_unresolved_threads,
            character_states=character_states,
            author=author,
            voice_samples=voice_samples,
            source_heading_examples=source_heading_examples,
        )

        try:
            payload: UnifiedSynthesisPayload = await self.client.call_json(
                prompt, UnifiedSynthesisPayload
            )
            chapter_text = self._normalize_chapter_text(
                payload.chapter_text,
                chapter_number=chapter_number,
                source_heading_examples=source_heading_examples,
            )
            return chapter_text, payload.summary
        except Exception as exc:
            raise RuntimeError(
                f"Unified chapter synthesis+summary failed for tick range "
                f"{event_window.tick_range}"
            ) from exc

    def synthesize_and_summarize(
        self,
        event_window: ChapterWindow,
        novel_meta: MetaLayerRecord,
        user_meta: UserMeta,
        *,
        chapter_number: int | None = None,
        previous_chapter_summary: Optional[ChapterSummary] = None,
        narrative_arc_unresolved_threads: Optional[List[str]] = None,
        character_states: Optional[List[CharacterStateSummary]] = None,
        author: str = "",
        voice_samples: Optional[List[str]] = None,
        source_heading_examples: Optional[List[str]] = None,
    ) -> tuple[str, str]:
        """Synthesize and summarize a chapter (sync wrapper).

        See synthesize_and_summarize_async for full documentation.
        """
        return asyncio.run(
            self.synthesize_and_summarize_async(
                event_window=event_window,
                novel_meta=novel_meta,
                user_meta=user_meta,
                chapter_number=chapter_number,
                previous_chapter_summary=previous_chapter_summary,
                narrative_arc_unresolved_threads=narrative_arc_unresolved_threads,
                character_states=character_states,
                author=author,
                voice_samples=voice_samples,
                source_heading_examples=source_heading_examples,
            )
        )

    @staticmethod
    def _normalize_chapter_text(
        chapter_text: str,
        *,
        chapter_number: int | None = None,
        source_heading_examples: Optional[List[str]] = None,
    ) -> str:
        text = str(chapter_text or "").strip()
        if not text:
            return text
        if chapter_number is None or not source_heading_examples:
            return text

        first_content_line = next(
            (line.strip() for line in text.splitlines() if line.strip()),
            "",
        )
        if first_content_line and looks_like_chapter_heading(first_content_line):
            return text

        heading = format_synthesized_chapter_heading(
            chapter_number,
            source_heading_examples,
        )
        if not heading:
            return text
        return f"{heading}\n\n{text}"
