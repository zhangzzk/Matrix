from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Protocol

from pydantic import BaseModel

from dreamdive.ingestion.chunker import TextChunk, chunk_text, estimate_token_count
from dreamdive.ingestion.models import (
    AccumulatedExtraction,
    DramaticBlueprintRecord,

    FateLayerRecord,
    MetaLayerRecord,
    StructuralScanPayload,
)
from dreamdive.ingestion.validator import ExtractionValidator

INGESTION_CACHE_VERSION = 6
CHAPTER_PASS_MAX_TOKENS = 2_000
CHAPTER_PASS_OVERLAP_TOKENS = 80
CHAPTER_SECTION_RETRY_MIN_TOKENS = 100
CHAPTER_SECTION_RETRY_OVERLAP_TOKENS = 40
CHAPTER_SECTION_MAX_SPLIT_DEPTH = 3


@dataclass
class ChapterSource:
    chapter_id: str
    text: str
    title: str = ""
    order_index: int = 0

    @property
    def checksum(self) -> str:
        return hashlib.sha256(self.text.encode("utf-8")).hexdigest()


@dataclass
class StructuralScanState:
    checksum: str = ""
    chunk_ids: List[str] = field(default_factory=list)
    completed: bool = False
    version: int = INGESTION_CACHE_VERSION


@dataclass
class AnalysisPassState:
    checksum: str = ""
    completed: bool = False
    version: int = INGESTION_CACHE_VERSION


@dataclass
class ChapterCheckpoint:
    chapter_id: str
    checksum: str
    order_index: int
    completed: bool = False
    version: int = INGESTION_CACHE_VERSION


@dataclass
class IngestionManifest:
    structural_scan: StructuralScanState = field(default_factory=StructuralScanState)
    chapters: Dict[str, ChapterCheckpoint] = field(default_factory=dict)
    meta_layer: AnalysisPassState = field(default_factory=AnalysisPassState)
    dramatic_blueprint: AnalysisPassState = field(default_factory=AnalysisPassState)


IngestionProgressCallback = Callable[[str, Dict[str, Any]], None]


class ExtractionBackend(Protocol):
    def run_structural_scan(
        self,
        chunks: List[TextChunk],
    ) -> object:
        ...

    def run_chapter_pass(
        self,
        chapter: ChapterSource,
        accumulated: AccumulatedExtraction,
        *,
        structural_scan: StructuralScanPayload | None = None,
    ) -> object:
        ...

    def run_meta_layer_pass(
        self,
        excerpts: List[str],
        *,
        major_character_ids: List[str],
    ) -> object:
        ...

    def run_dramatic_blueprint_pass(
        self,
        accumulated: AccumulatedExtraction,
    ) -> object:
        ...


class ManifestStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> IngestionManifest:
        if not self.path.exists():
            return IngestionManifest()

        data = json.loads(self.path.read_text(encoding="utf-8"))
        structural = StructuralScanState(**self._state_payload(data.get("structural_scan", {})))
        chapters = {
            chapter_id: ChapterCheckpoint(**self._state_payload(checkpoint))
            for chapter_id, checkpoint in data.get("chapters", {}).items()
        }
        return IngestionManifest(
            structural_scan=structural,
            chapters=chapters,
            meta_layer=AnalysisPassState(**self._state_payload(data.get("meta_layer", {}))),
        )

    def save(self, manifest: IngestionManifest) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "structural_scan": asdict(manifest.structural_scan),
            "chapters": {chapter_id: asdict(checkpoint) for chapter_id, checkpoint in manifest.chapters.items()},
            "meta_layer": asdict(manifest.meta_layer),
        }
        self.path.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False), encoding="utf-8")

    @staticmethod
    def _state_payload(payload: dict) -> dict:
        normalized = dict(payload)
        normalized.setdefault("version", 0)
        return normalized


class ArtifactStore:
    def __init__(self, base_dir: Path) -> None:
        self.base_dir = base_dir

    def save_structural_scan(self, payload: StructuralScanPayload) -> None:
        self.base_dir.mkdir(parents=True, exist_ok=True)
        path = self.base_dir / "structural_scan.json"
        path.write_text(
            json.dumps(payload.model_dump(mode="json"), indent=2, sort_keys=True, ensure_ascii=False),
            encoding="utf-8",
        )

    def load_structural_scan(self) -> Optional[StructuralScanPayload]:
        path = self.base_dir / "structural_scan.json"
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return StructuralScanPayload.model_validate(data)

    def clear_structural_scan(self) -> None:
        path = self.base_dir / "structural_scan.json"
        if path.exists():
            path.unlink()

    def save_chapter_snapshot(
        self,
        chapter: "ChapterSource",
        payload: AccumulatedExtraction,
    ) -> None:
        chapter_dir = self.base_dir / "chapters"
        chapter_dir.mkdir(parents=True, exist_ok=True)
        path = chapter_dir / self._chapter_filename(chapter.chapter_id, chapter.order_index)
        path.write_text(
            json.dumps(payload.model_dump(mode="json"), indent=2, sort_keys=True, ensure_ascii=False),
            encoding="utf-8",
        )

    def load_chapter_snapshot(
        self,
        chapter_id: str,
        order_index: int,
    ) -> Optional[AccumulatedExtraction]:
        path = self.base_dir / "chapters" / self._chapter_filename(chapter_id, order_index)
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return AccumulatedExtraction.model_validate(data)

    def clear_chapter_snapshots(self) -> None:
        chapter_dir = self.base_dir / "chapters"
        if not chapter_dir.exists():
            return
        for path in chapter_dir.glob("*.json"):
            path.unlink()

    def save_meta_layer(self, payload: MetaLayerRecord) -> None:
        self.base_dir.mkdir(parents=True, exist_ok=True)
        path = self.base_dir / "meta_layer.json"
        path.write_text(
            json.dumps(payload.model_dump(mode="json"), indent=2, sort_keys=True, ensure_ascii=False),
            encoding="utf-8",
        )

    def load_meta_layer(self) -> Optional[MetaLayerRecord]:
        path = self.base_dir / "meta_layer.json"
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return MetaLayerRecord.model_validate(data)

    def clear_meta_layer(self) -> None:
        path = self.base_dir / "meta_layer.json"
        if path.exists():
            path.unlink()

    def save_fate(self, payload: FateLayerRecord) -> None:
        self.base_dir.mkdir(parents=True, exist_ok=True)
        path = self.base_dir / "fate.json"
        path.write_text(
            json.dumps(payload.model_dump(mode="json"), indent=2, sort_keys=True, ensure_ascii=False),
            encoding="utf-8",
        )

    def load_fate(self) -> Optional[FateLayerRecord]:
        path = self.base_dir / "fate.json"
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return FateLayerRecord.model_validate(data)

    def clear_fate(self) -> None:
        path = self.base_dir / "fate.json"
        if path.exists():
            path.unlink()

    @staticmethod
    def _chapter_filename(chapter_id: str, order_index: int) -> str:
        return f"{order_index:04d}_{chapter_id}.json"


@dataclass
class StructuralScanPlan:
    chunks: List[TextChunk]
    should_run: bool


@dataclass
class ChapterRunResult:
    chapter_id: str
    skipped: bool
    accumulated: AccumulatedExtraction


class IngestionPipeline:
    """Idempotent ingestion planner and orchestrator for structural and chapter passes."""

    def __init__(
        self,
        manifest_store: ManifestStore,
        artifact_store: Optional[ArtifactStore] = None,
        validator: Optional[ExtractionValidator] = None,
        *,
        chapter_max_tokens: int = CHAPTER_PASS_MAX_TOKENS,
        chapter_overlap_tokens: int = CHAPTER_PASS_OVERLAP_TOKENS,
    ) -> None:
        self.manifest_store = manifest_store
        self.artifact_store = artifact_store
        self.validator = validator or ExtractionValidator()
        self.chapter_max_tokens = chapter_max_tokens
        self.chapter_overlap_tokens = chapter_overlap_tokens

    def prepare_structural_scan(
        self,
        text: str,
        *,
        max_tokens: int = 5_000,
        overlap_tokens: int = 200,
    ) -> StructuralScanPlan:
        manifest = self.manifest_store.load()
        checksum = hashlib.sha256(text.encode("utf-8")).hexdigest()
        chunks = chunk_text(
            text,
            prefix="structural_scan",
            max_tokens=max_tokens,
            overlap_tokens=overlap_tokens,
        )
        should_run = not (
            manifest.structural_scan.completed
            and manifest.structural_scan.checksum == checksum
            and manifest.structural_scan.version == INGESTION_CACHE_VERSION
        )
        return StructuralScanPlan(chunks=chunks, should_run=should_run)

    def run_structural_scan(
        self,
        text: str,
        backend: ExtractionBackend,
        *,
        max_tokens: int = 5_000,
        overlap_tokens: int = 200,
        force_rerun: bool = False,
        progress_callback: Optional[IngestionProgressCallback] = None,
    ) -> StructuralScanPayload:
        manifest = self.manifest_store.load()
        checksum = hashlib.sha256(text.encode("utf-8")).hexdigest()
        chunks = chunk_text(
            text,
            prefix="structural_scan",
            max_tokens=max_tokens,
            overlap_tokens=overlap_tokens,
        )
        _emit_progress(
            progress_callback,
            "structural_scan",
            chunk_count=len(chunks),
        )

        if (
            not force_rerun
            and (
            manifest.structural_scan.completed
            and manifest.structural_scan.checksum == checksum
            and manifest.structural_scan.version == INGESTION_CACHE_VERSION
            )
        ):
            _emit_progress(
                progress_callback,
                "structural_scan",
                chunk_count=len(chunks),
                cached=True,
            )
            if self.artifact_store is not None:
                saved = self.artifact_store.load_structural_scan()
                if saved is not None:
                    return saved
            raw = backend.run_structural_scan(chunks)
            validated = self.validator.validate_payload(raw, StructuralScanPayload)
            if self.artifact_store is not None:
                self.artifact_store.save_structural_scan(validated)
            return validated

        raw = backend.run_structural_scan(chunks)
        validated = self.validator.validate_payload(raw, StructuralScanPayload)
        manifest.structural_scan = StructuralScanState(
            checksum=checksum,
            chunk_ids=[chunk.chunk_id for chunk in chunks],
            completed=True,
            version=INGESTION_CACHE_VERSION,
        )
        self.manifest_store.save(manifest)
        if self.artifact_store is not None:
            self.artifact_store.save_structural_scan(validated)
        return validated

    def run_meta_layer(
        self,
        excerpts: List[str],
        backend: ExtractionBackend,
        *,
        major_character_ids: List[str],
        force_rerun: bool = False,
        progress_callback: Optional[IngestionProgressCallback] = None,
    ) -> MetaLayerRecord:
        manifest = self.manifest_store.load()
        checksum = hashlib.sha256("\n\n".join(excerpts).encode("utf-8")).hexdigest()
        _emit_progress(
            progress_callback,
            "meta_layer",
            excerpt_count=len(excerpts),
            major_character_count=len(major_character_ids),
        )

        if (
            not force_rerun
            and (
            manifest.meta_layer.completed
            and manifest.meta_layer.checksum == checksum
            and manifest.meta_layer.version == INGESTION_CACHE_VERSION
            )
        ):
            _emit_progress(
                progress_callback,
                "meta_layer",
                excerpt_count=len(excerpts),
                major_character_count=len(major_character_ids),
                cached=True,
            )
            if self.artifact_store is not None:
                saved = self.artifact_store.load_meta_layer()
                if saved is not None:
                    return saved

        raw = backend.run_meta_layer_pass(excerpts, major_character_ids=major_character_ids)
        validated = self.validator.validate_payload(raw, MetaLayerRecord)
        manifest.meta_layer = AnalysisPassState(
            checksum=checksum,
            completed=True,
            version=INGESTION_CACHE_VERSION,
        )
        self.manifest_store.save(manifest)
        if self.artifact_store is not None:
            self.artifact_store.save_meta_layer(validated)
        return validated

    def run_genre_taste(
        self,
        meta: MetaLayerRecord,
        *,
        web_searcher: object,
        llm_client: object,
        progress_callback: Optional[IngestionProgressCallback] = None,
    ) -> MetaLayerRecord:
        """Enrich the meta layer with a genre taste benchmark.

        Runs a web search to find the most acclaimed authors in the
        detected genre, then synthesises their shared taste into a
        concise profile that guides the simulation.

        Returns an updated MetaLayerRecord with ``genre_taste`` populated.
        """
        import asyncio as _asyncio

        from dreamdive.ingestion.author_research import GenreTasteAgent

        _emit_progress(progress_callback, "genre_taste")

        # Already populated?  Skip unless empty.
        if meta.genre_taste.taste_profile:
            _emit_progress(progress_callback, "genre_taste", cached=True)
            return meta

        # Derive genres from authorial themes + tone
        genres: List[str] = []
        for theme in meta.authorial.themes:
            if theme.name:
                genres.append(theme.name)
        if meta.authorial.dominant_tone:
            genres.append(meta.authorial.dominant_tone)
        if not genres:
            return meta

        style_desc = meta.writing_style.prose_description or ""
        primary_lang = meta.language_context.primary_language or ""

        agent = GenreTasteAgent(
            web_searcher=web_searcher,  # type: ignore[arg-type]
            llm_client=llm_client,  # type: ignore[arg-type]
        )
        try:
            taste = _asyncio.run(
                agent.research(
                    genres=genres[:5],
                    style_description=style_desc,
                    primary_language=primary_lang,
                )
            )
        except Exception:
            import logging
            logging.getLogger(__name__).warning("Genre taste research failed, skipping")
            return meta

        enriched = meta.model_copy(update={"genre_taste": taste})
        if self.artifact_store is not None:
            self.artifact_store.save_meta_layer(enriched)
        return enriched

    def run_dramatic_blueprint(
        self,
        accumulated: AccumulatedExtraction,
        backend: ExtractionBackend,
        *,
        force_rerun: bool = False,
        progress_callback: Optional[IngestionProgressCallback] = None,
    ) -> FateLayerRecord:
        manifest = self.manifest_store.load()
        checksum = hashlib.sha256(
            json.dumps(accumulated.model_dump(mode="json"), sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest()
        _emit_progress(
            progress_callback,
            "dramatic_blueprint",
            character_count=len(accumulated.characters),
            event_count=len(accumulated.events),
        )

        if (
            not force_rerun
            and (
            manifest.dramatic_blueprint.completed
            and manifest.dramatic_blueprint.checksum == checksum
            and manifest.dramatic_blueprint.version == INGESTION_CACHE_VERSION
            )
        ):
            _emit_progress(
                progress_callback,
                "dramatic_blueprint",
                character_count=len(accumulated.characters),
                event_count=len(accumulated.events),
                cached=True,
            )
            if self.artifact_store is not None:
                saved = self.artifact_store.load_fate()
                if saved is not None:
                    return saved

        raw = backend.run_dramatic_blueprint_pass(accumulated)
        validated = self.validator.validate_payload(raw, DramaticBlueprintRecord)
        fate = FateLayerRecord(extracted=validated)
        manifest.dramatic_blueprint = AnalysisPassState(
            checksum=checksum,
            completed=True,
            version=INGESTION_CACHE_VERSION,
        )
        self.manifest_store.save(manifest)
        if self.artifact_store is not None:
            self.artifact_store.save_fate(fate)
        return fate

    def run_chapter_passes(
        self,
        chapters: List[ChapterSource],
        backend: ExtractionBackend,
        *,
        initial_accumulated: Optional[AccumulatedExtraction] = None,
        force_rerun: bool = False,
        progress_callback: Optional[IngestionProgressCallback] = None,
        max_workers: int = 4,
        section_max_workers: int = 1,
    ) -> AccumulatedExtraction:
        accumulated = initial_accumulated or AccumulatedExtraction()
        if force_rerun:
            accumulated = AccumulatedExtraction()
            manifest = self.manifest_store.load()
            manifest.chapters = {}
            self.manifest_store.save(manifest)
            if self.artifact_store is not None:
                self.artifact_store.clear_chapter_snapshots()
        ordered_chapters = sorted(chapters, key=lambda chapter: chapter.order_index)
        chapter_count = len(ordered_chapters)
        structural_scan = (
            self.artifact_store.load_structural_scan()
            if self.artifact_store is not None
            else None
        )

        if max_workers <= 1:
            for chapter_index, chapter in enumerate(ordered_chapters, start=1):
                result = self.run_single_chapter(
                    chapter,
                    backend,
                    accumulated,
                    structural_scan=structural_scan,
                    chapter_index=chapter_index,
                    chapter_count=chapter_count,
                    force_rerun=force_rerun,
                    progress_callback=progress_callback,
                    section_max_workers=section_max_workers,
                )
                accumulated = result.accumulated
            return accumulated

        from concurrent.futures import ThreadPoolExecutor, as_completed

        # In parallel mode, we process all chapters concurrently.
        # Note: Since they are independent extracts, we merge them at the end.
        results: List[ChapterRunResult] = []
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_chapter = {
                executor.submit(
                    self.run_single_chapter,
                    chapter,
                    backend,
                    accumulated, # Use the initial or current accumulated base
                    structural_scan=structural_scan,
                    chapter_index=i + 1,
                    chapter_count=chapter_count,
                    force_rerun=force_rerun,
                    progress_callback=progress_callback,
                    section_max_workers=section_max_workers,
                ): chapter
                for i, chapter in enumerate(ordered_chapters)
            }
            for future in as_completed(future_to_chapter):
                results.append(future.result())

        # Merge results in order of chapter index to preserve sequence as much as possible,
        # although merge_accumulated_extraction is designed to be generally order-independent.
        sorted_results = sorted(
            results, 
            key=lambda r: next(c.order_index for c in ordered_chapters if c.chapter_id == r.chapter_id)
        )
        for res in sorted_results:
            accumulated = merge_accumulated_extraction(accumulated, res.accumulated)
            
        return accumulated

    def run_single_chapter(
        self,
        chapter: ChapterSource,
        backend: ExtractionBackend,
        accumulated: AccumulatedExtraction,
        *,
        structural_scan: Optional[StructuralScanPayload] = None,
        chapter_index: int | None = None,
        chapter_count: int | None = None,
        force_rerun: bool = False,
        progress_callback: Optional[IngestionProgressCallback] = None,
        section_max_workers: int = 1,
    ) -> ChapterRunResult:
        manifest = self.manifest_store.load()
        checkpoint = manifest.chapters.get(chapter.chapter_id)
        chapter_title = chapter.title or chapter.chapter_id
        if (
            not force_rerun
            and (
            checkpoint
            and checkpoint.completed
            and checkpoint.checksum == chapter.checksum
            and checkpoint.version == INGESTION_CACHE_VERSION
            )
        ):
            _emit_progress(
                progress_callback,
                "chapter",
                chapter_id=chapter.chapter_id,
                chapter_title=chapter_title,
                chapter_index=chapter_index,
                chapter_count=chapter_count,
                cached=True,
            )
            restored = None
            if self.artifact_store is not None:
                restored = self.artifact_store.load_chapter_snapshot(
                    chapter.chapter_id,
                    chapter.order_index,
                )
            return ChapterRunResult(
                chapter_id=chapter.chapter_id,
                skipped=True,
                accumulated=restored or accumulated,
            )

        sections = self._chapter_sections(chapter)

        if section_max_workers > 1 and len(sections) > 1:
            # Parallel section processing: extract each section independently, then merge.
            from concurrent.futures import ThreadPoolExecutor, as_completed as _as_completed

            section_results: List[AccumulatedExtraction] = []
            with ThreadPoolExecutor(max_workers=min(len(sections), section_max_workers)) as pool:
                future_to_idx = {
                    pool.submit(
                        self._run_section_with_fallback,
                        section=section,
                        backend=backend,
                        accumulated=accumulated,
                        structural_scan=structural_scan,
                        chapter_title=chapter_title,
                        chapter_index=chapter_index,
                        chapter_count=chapter_count,
                        progress_callback=progress_callback,
                    ): idx
                    for idx, section in enumerate(sections)
                }
                indexed_results = []
                for future in _as_completed(future_to_idx):
                    indexed_results.append((future_to_idx[future], future.result()))
            indexed_results.sort(key=lambda pair: pair[0])
            validated = accumulated
            for _, section_accumulated in indexed_results:
                validated = merge_accumulated_extraction(validated, section_accumulated)
        else:
            validated = accumulated
            for section in sections:
                validated = self._run_section_with_fallback(
                    section=section,
                    backend=backend,
                    accumulated=validated,
                    structural_scan=structural_scan,
                    chapter_title=chapter_title,
                    chapter_index=chapter_index,
                    chapter_count=chapter_count,
                    progress_callback=progress_callback,
                )

        manifest.chapters[chapter.chapter_id] = ChapterCheckpoint(
            chapter_id=chapter.chapter_id,
            checksum=chapter.checksum,
            order_index=chapter.order_index,
            completed=True,
            version=INGESTION_CACHE_VERSION,
        )
        self.manifest_store.save(manifest)
        if self.artifact_store is not None:
            self.artifact_store.save_chapter_snapshot(chapter, validated)
        return ChapterRunResult(
            chapter_id=chapter.chapter_id,
            skipped=False,
            accumulated=validated,
        )

    def _chapter_sections(self, chapter: ChapterSource) -> List[ChapterSource]:
        if len(chapter.text.strip()) == 0:
            return [chapter]
        chunks = chunk_text(
            chapter.text,
            prefix=f"chapter_{chapter.chapter_id}",
            max_tokens=self.chapter_max_tokens,
            overlap_tokens=self.chapter_overlap_tokens,
        )
        if len(chunks) <= 1:
            return [chapter]
        total = len(chunks)
        sections: List[ChapterSource] = []
        for index, chunk in enumerate(chunks, start=1):
            title = chapter.title or chapter.chapter_id
            section_title = f"{title} [section {index}/{total}]"
            sections.append(
                ChapterSource(
                    chapter_id=chapter.chapter_id,
                    title=section_title,
                    order_index=chapter.order_index,
                    text=chunk.text,
                )
            )
        return sections

    def _run_section_with_fallback(
        self,
        *,
        section: ChapterSource,
        backend: ExtractionBackend,
        accumulated: AccumulatedExtraction,
        structural_scan: Optional[StructuralScanPayload],
        chapter_title: str,
        chapter_index: int | None = None,
        chapter_count: int | None = None,
        progress_callback: Optional[IngestionProgressCallback] = None,
        depth: int = 0,
    ) -> AccumulatedExtraction:
        _emit_progress(
            progress_callback,
            "chapter_section",
            chapter_id=section.chapter_id,
            chapter_title=chapter_title,
            chapter_index=chapter_index,
            chapter_count=chapter_count,
            section_title=section.title or section.chapter_id,
            depth=depth,
        )
        try:
            raw = backend.run_chapter_pass(
                section,
                accumulated,
                structural_scan=structural_scan,
            )
        except Exception:
            fallback_sections = self._split_section_for_retry(section, depth=depth)
            if not fallback_sections:
                raise
            _emit_progress(
                progress_callback,
                "chapter_retry_split",
                chapter_id=section.chapter_id,
                chapter_title=chapter_title,
                chapter_index=chapter_index,
                chapter_count=chapter_count,
                section_title=section.title or section.chapter_id,
                retry_count=len(fallback_sections),
                depth=depth + 1,
            )
            validated = accumulated
            for subsection in fallback_sections:
                validated = self._run_section_with_fallback(
                    section=subsection,
                    backend=backend,
                    accumulated=validated,
                    structural_scan=structural_scan,
                    chapter_title=chapter_title,
                    chapter_index=chapter_index,
                    chapter_count=chapter_count,
                    progress_callback=progress_callback,
                    depth=depth + 1,
                )
            return validated

        delta = raw if isinstance(raw, AccumulatedExtraction) else self.validator.validate_payload(
            raw,
            AccumulatedExtraction,
        )
        return merge_accumulated_extraction(accumulated, delta)

    def _split_section_for_retry(
        self,
        section: ChapterSource,
        *,
        depth: int,
    ) -> List[ChapterSource]:
        if depth >= CHAPTER_SECTION_MAX_SPLIT_DEPTH:
            return []
        approx_tokens = estimate_token_count(section.text)
        if approx_tokens <= CHAPTER_SECTION_RETRY_MIN_TOKENS:
            return []
        target_tokens = max(CHAPTER_SECTION_RETRY_MIN_TOKENS, approx_tokens // 2)
        if target_tokens >= approx_tokens:
            return []

        chunks = chunk_text(
            section.text,
            prefix=f"chapter_{section.chapter_id}_retry_{depth + 1}",
            max_tokens=target_tokens,
            overlap_tokens=CHAPTER_SECTION_RETRY_OVERLAP_TOKENS,
        )
        if len(chunks) <= 1:
            return []

        subsections: List[ChapterSource] = []
        total = len(chunks)
        base_title = section.title or section.chapter_id
        for index, chunk in enumerate(chunks, start=1):
            subsections.append(
                ChapterSource(
                    chapter_id=section.chapter_id,
                    title=f"{base_title} [retry {index}/{total}]",
                    order_index=section.order_index,
                    text=chunk.text,
                )
            )
        return subsections


def merge_accumulated_extraction(
    accumulated: AccumulatedExtraction,
    delta: AccumulatedExtraction,
) -> AccumulatedExtraction:
    return _merge_model(accumulated, delta)


def _emit_progress(
    callback: Optional[IngestionProgressCallback],
    stage: str,
    **payload: Any,
) -> None:
    if callback is None:
        return
    callback(stage, payload)


def _merge_model(existing: BaseModel, incoming: BaseModel) -> BaseModel:
    merged = existing.model_copy(deep=True)
    for field_name in incoming.model_fields_set:
        incoming_value = getattr(incoming, field_name)
        existing_value = getattr(merged, field_name)
        setattr(
            merged,
            field_name,
            _merge_value(
                existing_value,
                incoming_value,
                field_name=field_name,
            ),
        )
    return merged


def _merge_value(existing: Any, incoming: Any, *, field_name: str = "") -> Any:
    if isinstance(existing, BaseModel) and isinstance(incoming, BaseModel):
        return _merge_model(existing, incoming)
    if isinstance(existing, list) and isinstance(incoming, list):
        return _merge_list(existing, incoming, field_name=field_name)
    if isinstance(existing, dict) and isinstance(incoming, dict):
        return _merge_dict(existing, incoming)
    if isinstance(incoming, str):
        return incoming if incoming.strip() else existing
    return incoming


def _merge_list(existing: list[Any], incoming: list[Any], *, field_name: str) -> list[Any]:
    if field_name == "goal_stack":
        return _dedupe_scalars(incoming)
    if not incoming:
        return list(existing)

    if all(_is_scalar_list_item(item) for item in [*existing, *incoming]):
        return _dedupe_scalars([*existing, *incoming])

    merge_key = _infer_merge_key([*existing, *incoming])
    if merge_key is None:
        return [*existing, *incoming]

    merged: dict[str, Any] = {}
    ordered_keys: list[str] = []
    for item in existing:
        key = _list_item_merge_key(item, merge_key)
        if key is None:
            ordered_keys.append(f"__existing_{len(ordered_keys)}")
            merged[ordered_keys[-1]] = item
            continue
        merged[key] = item
        ordered_keys.append(key)
    for item in incoming:
        key = _list_item_merge_key(item, merge_key)
        if key is None:
            ordered_keys.append(f"__incoming_{len(ordered_keys)}")
            merged[ordered_keys[-1]] = item
            continue
        if key in merged:
            merged[key] = _merge_value(merged[key], item, field_name=field_name)
            continue
        merged[key] = item
        ordered_keys.append(key)

    seen: set[str] = set()
    result: list[Any] = []
    for key in ordered_keys:
        if key in seen:
            continue
        seen.add(key)
        result.append(merged[key])
    return result


def _merge_dict(existing: dict[Any, Any], incoming: dict[Any, Any]) -> dict[Any, Any]:
    merged = dict(existing)
    for key, value in incoming.items():
        if key in merged:
            merged[key] = _merge_value(merged[key], value, field_name=str(key))
            continue
        if isinstance(value, str) and not value.strip():
            continue
        merged[key] = value
    return merged


def _dedupe_scalars(values: list[Any]) -> list[Any]:
    result: list[Any] = []
    seen: set[Any] = set()
    for value in values:
        normalized = value.strip() if isinstance(value, str) else value
        if normalized in {None, ""}:
            continue
        if normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result


def _is_scalar_list_item(value: Any) -> bool:
    return not isinstance(value, (BaseModel, dict, list))


def _infer_merge_key(items: list[Any]) -> str | None:
    candidates = ("id", "entity_id", "character_id", "target_id", "agent_id", "name", "text")
    for candidate in candidates:
        if any(_list_item_merge_key(item, candidate) is not None for item in items):
            return candidate
    return None


def _list_item_merge_key(item: Any, field_name: str) -> str | None:
    if isinstance(item, BaseModel):
        value = getattr(item, field_name, None)
    elif isinstance(item, dict):
        value = item.get(field_name)
    else:
        return None
    if value is None:
        return None
    text = str(value).strip()
    return text or None
