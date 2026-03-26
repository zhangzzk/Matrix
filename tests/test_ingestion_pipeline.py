import json
import tempfile
import unittest
from pathlib import Path

from dreamdive.ingestion.chunker import chunk_text
from dreamdive.ingestion.extractor import (
    ArtifactStore,
    ChapterSource,
    IngestionPipeline,
    ManifestStore,
)
from dreamdive.ingestion.models import AccumulatedExtraction, StructuralScanPayload


class FakeBackend:
    def __init__(self) -> None:
        self.structural_calls = 0
        self.chapter_calls = []
        self.meta_calls = 0

    def run_structural_scan(self, chunks):
        self.structural_calls += 1
        return {
            "world": {
                "setting": "A city-state",
                "time_period": "Late bronze age",
                "rules_and_constraints": [],
                "factions": [],
                "key_locations": [],
            },
            "cast_list": [],
            "timeline_skeleton": {
                "story_start": "Day 1",
                "pre_story_events": [],
                "known_future_events": [],
            },
            "domain_systems": [],
        }

    def run_chapter_pass(self, chapter, accumulated, *, structural_scan=None):
        self.chapter_calls.append(chapter.chapter_id)
        payload = accumulated.model_dump(mode="json")
        payload["events"].append(
            {
                "id": f"evt_{chapter.chapter_id}",
                "time": f"T{chapter.order_index}",
                "location": chapter.title or chapter.chapter_id,
                "participants": [],
                "summary": f"Processed {chapter.chapter_id}",
                "consequences": [],
                "participant_knowledge": {},
            }
        )
        return payload

    def run_meta_layer_pass(self, excerpts, *, major_character_ids):
        self.meta_calls += 1
        return {
            "authorial": {
                "central_thesis": {"value": "Test thesis", "confidence": "INFERRED"},
                "themes": [],
                "dominant_tone": "tense",
                "beliefs_about": {},
                "symbolic_motifs": [],
                "narrative_perspective": "third_limited",
            },
            "writing_style": {
                "prose_description": "lean",
                "sentence_rhythm": "clipped",
                "description_density": "sparse",
                "dialogue_narration_balance": "balanced",
                "stylistic_signatures": [],
                "sample_passages": [],
            },
            "language_context": {
                "primary_language": "English",
                "language_variety": "close-third literary English",
                "language_style": "economical and pressure-driven",
                "author_style": "spare realism with controlled lyric flashes",
                "register_profile": "mostly plain diction with occasional ceremonial lifts",
                "dialogue_style": "short and tactical",
                "figurative_patterns": ["metal and heat imagery"],
                "multilingual_features": [],
                "translation_notes": ["Keep the pressure under the surface."],
            },
            "character_voices": [],
            "real_world_context": {
                "written_when": "",
                "historical_context": "",
                "unspeakable_constraints": [],
                "literary_tradition": "",
                "autobiographical_elements": "",
            },
        }



class DeltaBackend(FakeBackend):
    def run_chapter_pass(self, chapter, accumulated, *, structural_scan=None):
        self.chapter_calls.append(chapter.chapter_id)
        if chapter.chapter_id == "001":
            return {
                "characters": [
                    {
                        "id": "char_001",
                        "name": "路明非",
                        "current_state": {"location": "教室"},
                    }
                ]
            }
        return {
            "characters": [
                {
                    "id": "char_001",
                    "name": "路明非",
                    "current_state": {"emotional_state": "紧张"},
                }
            ],
            "events": [
                {
                    "id": f"evt_{chapter.chapter_id}",
                    "time": f"T{chapter.order_index}",
                    "location": chapter.title or chapter.chapter_id,
                    "participants": ["char_001"],
                    "summary": f"Processed {chapter.chapter_id}",
                    "consequences": [],
                    "participant_knowledge": {},
                }
            ],
        }


class SplittingBackend(FakeBackend):
    def __init__(self, max_tokens_before_failure: int) -> None:
        super().__init__()
        self.max_tokens_before_failure = max_tokens_before_failure

    def run_chapter_pass(self, chapter, accumulated, *, structural_scan=None):
        self.chapter_calls.append(chapter.title or chapter.chapter_id)
        approx_tokens = max(1, len(chapter.text) // 4)
        if approx_tokens > self.max_tokens_before_failure:
            raise RuntimeError(f"Section too large: {approx_tokens}")
        payload = accumulated.model_dump(mode="json")
        payload["events"].append(
            {
                "id": f"evt_{len(self.chapter_calls):03d}",
                "time": f"T{chapter.order_index}",
                "location": chapter.title or chapter.chapter_id,
                "participants": [],
                "summary": f"Processed {chapter.title or chapter.chapter_id}",
                "consequences": [],
                "participant_knowledge": {},
            }
        )
        return payload


class ChunkerTests(unittest.TestCase):
    def test_chunk_text_splits_large_text_and_preserves_order(self) -> None:
        text = "\n\n".join(
            [f"Paragraph {index} " + ("x" * 600) for index in range(1, 8)]
        )

        chunks = chunk_text(text, prefix="novel", max_tokens=300, overlap_tokens=0)

        self.assertGreater(len(chunks), 1)
        self.assertEqual(chunks[0].chunk_id, "novel_001")
        self.assertLessEqual(max(chunk.approx_token_count for chunk in chunks), 300)
        self.assertTrue(chunks[0].text.startswith("Paragraph 1"))

    def test_chunk_text_hard_splits_single_oversized_block(self) -> None:
        text = "序幕 白帝城\n" + ("龙" * 6000)

        chunks = chunk_text(text, prefix="novel", max_tokens=300, overlap_tokens=0)

        self.assertGreater(len(chunks), 1)
        self.assertLessEqual(max(chunk.approx_token_count for chunk in chunks), 300)
        self.assertTrue(chunks[0].text.startswith("序幕 白帝城"))


class IngestionPipelineTests(unittest.TestCase):
    def test_pipeline_passes_saved_structural_scan_into_chapter_backend(self) -> None:
        class RecordingStructuralBackend(FakeBackend):
            def __init__(self) -> None:
                super().__init__()
                self.seen_story_start = None

            def run_chapter_pass(self, chapter, accumulated, *, structural_scan=None):
                self.chapter_calls.append(chapter.chapter_id)
                if structural_scan is not None:
                    self.seen_story_start = structural_scan.timeline_skeleton.story_start
                return accumulated.model_dump(mode="json")

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            manifest_store = ManifestStore(root / "manifest.json")
            artifact_store = ArtifactStore(root / "artifacts")
            pipeline = IngestionPipeline(manifest_store, artifact_store=artifact_store)
            backend = RecordingStructuralBackend()
            artifact_store.save_structural_scan(
                StructuralScanPayload.model_validate(
                    {
                        "world": {
                            "setting": "城市",
                            "time_period": "2009",
                            "rules_and_constraints": [],
                            "factions": [],
                            "key_locations": [],
                        },
                        "cast_list": [],
                        "timeline_skeleton": {
                            "story_start": "高考前三个月",
                            "pre_story_events": [],
                            "known_future_events": [],
                        },
                        "domain_systems": [],
                    }
                )
            )
            chapter = ChapterSource(
                chapter_id="001",
                title="Chapter 1",
                order_index=1,
                text="新的开始。",
            )

            pipeline.run_chapter_passes([chapter], backend)

            self.assertEqual(backend.seen_story_start, "高考前三个月")

    def test_manifest_persists_completed_chapters(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest_path = Path(tmpdir) / ".dreamdive" / "ingestion_manifest.json"
            store = ManifestStore(manifest_path)
            pipeline = IngestionPipeline(store)
            backend = FakeBackend()
            chapter = ChapterSource(
                chapter_id="001",
                title="Chapter 1",
                order_index=1,
                text="A beginning.",
            )

            result = pipeline.run_single_chapter(
                chapter,
                backend,
                AccumulatedExtraction(),
            )

            self.assertFalse(result.skipped)
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertTrue(data["chapters"]["001"]["completed"])

    def test_pipeline_skips_chapter_when_checksum_matches_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = ManifestStore(Path(tmpdir) / "manifest.json")
            pipeline = IngestionPipeline(store)
            backend = FakeBackend()
            chapter = ChapterSource(
                chapter_id="001",
                title="Chapter 1",
                order_index=1,
                text="A beginning.",
            )

            first = pipeline.run_single_chapter(chapter, backend, AccumulatedExtraction())
            second = pipeline.run_single_chapter(chapter, backend, first.accumulated)

            self.assertFalse(first.skipped)
            self.assertTrue(second.skipped)
            self.assertEqual(backend.chapter_calls, ["001"])

    def test_pipeline_resumes_and_processes_only_new_chapters(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = ManifestStore(Path(tmpdir) / "manifest.json")
            pipeline = IngestionPipeline(store)
            backend = FakeBackend()
            chapters = [
                ChapterSource(chapter_id="001", title="One", order_index=1, text="First"),
                ChapterSource(chapter_id="002", title="Two", order_index=2, text="Second"),
            ]

            first_pass = pipeline.run_chapter_passes([chapters[0]], backend)
            resumed = pipeline.run_chapter_passes(chapters, backend, initial_accumulated=first_pass)

            self.assertEqual(backend.chapter_calls, ["001", "002"])
            self.assertEqual([event.id for event in resumed.events], ["evt_001", "evt_002"])

    def test_pipeline_restores_saved_snapshot_when_skipping_from_fresh_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            manifest_store = ManifestStore(root / "manifest.json")
            artifact_store = ArtifactStore(root / "artifacts")
            pipeline = IngestionPipeline(manifest_store, artifact_store=artifact_store)
            backend = FakeBackend()
            chapter = ChapterSource(
                chapter_id="001",
                title="Chapter 1",
                order_index=1,
                text="A beginning.",
            )

            first = pipeline.run_single_chapter(chapter, backend, AccumulatedExtraction())
            restored = pipeline.run_single_chapter(chapter, backend, AccumulatedExtraction())

            self.assertFalse(first.skipped)
            self.assertTrue(restored.skipped)
            self.assertEqual([event.id for event in restored.accumulated.events], ["evt_001"])

    def test_pipeline_splits_oversized_chapter_into_multiple_section_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = ManifestStore(Path(tmpdir) / "manifest.json")
            pipeline = IngestionPipeline(
                store,
                chapter_max_tokens=200,
                chapter_overlap_tokens=0,
            )
            backend = FakeBackend()
            long_text = "\n\n".join([f"段落{index} " + ("龙" * 600) for index in range(1, 6)])
            chapter = ChapterSource(
                chapter_id="002",
                title="Chapter 1 · 卡塞尔之门",
                order_index=2,
                text=long_text,
            )

            result = pipeline.run_single_chapter(
                chapter,
                backend,
                AccumulatedExtraction(),
            )

            self.assertFalse(result.skipped)
            self.assertGreater(len(backend.chapter_calls), 1)
            self.assertTrue(all(chapter_id == "002" for chapter_id in backend.chapter_calls))

    def test_pipeline_merges_delta_chapter_updates_without_losing_prior_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = ManifestStore(Path(tmpdir) / "manifest.json")
            pipeline = IngestionPipeline(store)
            backend = DeltaBackend()
            chapters = [
                ChapterSource(chapter_id="001", title="One", order_index=1, text="First"),
                ChapterSource(chapter_id="002", title="Two", order_index=2, text="Second"),
            ]

            accumulated = pipeline.run_chapter_passes(chapters, backend)

            self.assertEqual(len(accumulated.characters), 1)
            self.assertEqual(accumulated.characters[0].name, "路明非")
            self.assertEqual(accumulated.characters[0].current_state.location, "教室")
            self.assertEqual(accumulated.characters[0].current_state.emotional_state, "紧张")
            self.assertEqual([event.id for event in accumulated.events], ["evt_002"])

    def test_pipeline_recursively_splits_failed_section_and_continues(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = ManifestStore(Path(tmpdir) / "manifest.json")
            pipeline = IngestionPipeline(
                store,
                chapter_max_tokens=500,
                chapter_overlap_tokens=0,
            )
            backend = SplittingBackend(max_tokens_before_failure=160)
            chapter = ChapterSource(
                chapter_id="002",
                title="Chapter 1 · 卡塞尔之门",
                order_index=2,
                text="\n\n".join([f"段落{index} " + ("龙" * 600) for index in range(1, 4)]),
            )

            result = pipeline.run_single_chapter(
                chapter,
                backend,
                AccumulatedExtraction(),
            )

            self.assertFalse(result.skipped)
            self.assertGreater(len(result.accumulated.events), 1)
            self.assertTrue(any("[retry " in title for title in backend.chapter_calls))

    def test_pipeline_reports_chapter_section_progress(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = ManifestStore(Path(tmpdir) / "manifest.json")
            pipeline = IngestionPipeline(
                store,
                chapter_max_tokens=200,
                chapter_overlap_tokens=0,
            )
            backend = FakeBackend()
            chapter = ChapterSource(
                chapter_id="002",
                title="Chapter 1 · 卡塞尔之门",
                order_index=2,
                text="\n\n".join([f"段落{index} " + ("龙" * 600) for index in range(1, 4)]),
            )
            progress_events = []

            pipeline.run_single_chapter(
                chapter,
                backend,
                AccumulatedExtraction(),
                chapter_index=2,
                chapter_count=12,
                progress_callback=lambda stage, payload: progress_events.append((stage, payload)),
            )

            section_events = [event for event in progress_events if event[0] == "chapter_section"]
            self.assertGreater(len(section_events), 1)
            self.assertEqual(section_events[0][1]["chapter_index"], 2)
            self.assertEqual(section_events[0][1]["chapter_count"], 12)
            self.assertIn("[section 1/", section_events[0][1]["section_title"])

    def test_structural_scan_uses_saved_artifact_when_available(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            manifest_store = ManifestStore(root / "manifest.json")
            artifact_store = ArtifactStore(root / "artifacts")
            pipeline = IngestionPipeline(manifest_store, artifact_store=artifact_store)
            backend = FakeBackend()
            novel_opening = "Opening pages of the novel."

            first = pipeline.run_structural_scan(novel_opening, backend)
            second = pipeline.run_structural_scan(novel_opening, backend)

            self.assertEqual(first.world.setting, "A city-state")
            self.assertEqual(second.world.setting, "A city-state")
            self.assertEqual(backend.structural_calls, 1)

    def test_force_rerun_structural_scan_ignores_cache(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            manifest_store = ManifestStore(root / "manifest.json")
            artifact_store = ArtifactStore(root / "artifacts")
            pipeline = IngestionPipeline(manifest_store, artifact_store=artifact_store)
            backend = FakeBackend()
            novel_opening = "Opening pages of the novel."

            pipeline.run_structural_scan(novel_opening, backend)
            pipeline.run_structural_scan(novel_opening, backend, force_rerun=True)

            self.assertEqual(backend.structural_calls, 2)

    def test_pipeline_caches_meta_pass(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            manifest_store = ManifestStore(root / "manifest.json")
            artifact_store = ArtifactStore(root / "artifacts")
            pipeline = IngestionPipeline(manifest_store, artifact_store=artifact_store)
            backend = FakeBackend()

            meta_first = pipeline.run_meta_layer(["[001]\nOpening"], backend, major_character_ids=["arya"])
            meta_second = pipeline.run_meta_layer(["[001]\nOpening"], backend, major_character_ids=["arya"])

            self.assertEqual(meta_first.writing_style.prose_description, "lean")
            self.assertEqual(meta_first.language_context.primary_language, "English")
            self.assertEqual(meta_second.writing_style.prose_description, "lean")
            self.assertEqual(backend.meta_calls, 1)

    def test_force_rerun_chapters_reprocesses_completed_snapshots(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            manifest_store = ManifestStore(root / "manifest.json")
            artifact_store = ArtifactStore(root / "artifacts")
            pipeline = IngestionPipeline(manifest_store, artifact_store=artifact_store)
            backend = FakeBackend()
            chapter = ChapterSource(
                chapter_id="001",
                title="Chapter 1",
                order_index=1,
                text="A beginning.",
            )

            first = pipeline.run_chapter_passes([chapter], backend)
            second = pipeline.run_chapter_passes([chapter], backend, force_rerun=True)

            self.assertEqual(backend.chapter_calls, ["001", "001"])
            self.assertEqual([event.id for event in first.events], ["evt_001"])
            self.assertEqual([event.id for event in second.events], ["evt_001"])

    def test_force_rerun_meta_ignores_cache(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            manifest_store = ManifestStore(root / "manifest.json")
            artifact_store = ArtifactStore(root / "artifacts")
            pipeline = IngestionPipeline(manifest_store, artifact_store=artifact_store)
            backend = FakeBackend()

            pipeline.run_meta_layer(["[001]\nOpening"], backend, major_character_ids=["arya"])
            pipeline.run_meta_layer(
                ["[001]\nOpening"],
                backend,
                major_character_ids=["arya"],
                force_rerun=True,
            )

            self.assertEqual(backend.meta_calls, 2)


if __name__ == "__main__":
    unittest.main()
