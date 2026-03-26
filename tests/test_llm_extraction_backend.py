import json
import unittest

from dreamdive.config import LLMProfileSettings
from dreamdive.ingestion.backend import LLMExtractionBackend
from dreamdive.ingestion.chunker import TextChunk
from dreamdive.ingestion.extractor import ChapterSource
from dreamdive.ingestion.models import AccumulatedExtraction, StructuralScanPayload
from dreamdive.llm.client import StructuredLLMClient


class RecordingTransport:
    def __init__(self, responses):
        self.responses = responses
        self.prompts = []
        self.calls = 0

    async def complete(self, profile, prompt):
        self.prompts.append(prompt)
        response = self.responses[self.calls]
        self.calls += 1
        return response


class LLMExtractionBackendTests(unittest.TestCase):
    def build_client(self, responses):
        return StructuredLLMClient(
            primary=LLMProfileSettings(
                name="moonshot",
                base_url="https://api.moonshot.ai/v1",
                model="kimi-k2.5",
            ),
            fallback=LLMProfileSettings(
                name="gemini",
                base_url="https://generativelanguage.googleapis.com/v1beta/openai",
                model="gemini-3.1-flash-lite-preview",
            ),
            transport=RecordingTransport(responses),
            retry_attempts=1,
            retry_delay_seconds=0,
        )

    def test_structural_scan_backend_builds_prompt_and_parses_response(self) -> None:
        payload = {
            "world": {
                "setting": "Port city",
                "time_period": "Industrial era",
                "rules_and_constraints": [],
                "factions": [],
                "key_locations": [],
            },
            "cast_list": [],
            "timeline_skeleton": {
                "story_start": "Dawn",
                "pre_story_events": [],
                "known_future_events": [],
            },
            "domain_systems": [],
        }
        client = self.build_client([json.dumps(payload)])
        backend = LLMExtractionBackend(client)

        result = backend.run_structural_scan(
            [TextChunk("structural_scan_001", "Opening chapter", 0, 15, 4)]
        )

        self.assertEqual(result["world"]["setting"], "Port city")
        transport = client.transport
        self.assertEqual(transport.prompts[0].metadata["prompt_name"], "p1_1_structural_scan")
        self.assertIn("Opening chapter", transport.prompts[0].user)
        self.assertIn("Primary language: English", transport.prompts[0].user)
        self.assertIn("Keep all free-text fields in the same language as the source text.", transport.prompts[0].user)
        self.assertIn("Do not translate source material into English.", transport.prompts[0].user)
        self.assertIn("OUTPUT CONTRACT:", transport.prompts[0].user)
        self.assertEqual(transport.prompts[0].metadata["response_schema"], "StructuralScanPayload")

    def test_chapter_backend_embeds_accumulated_json_in_prompt(self) -> None:
        payload = {
            "events": [
                {
                    "id": "evt_001",
                    "time": "T1",
                    "location": "docks",
                    "participants": [],
                    "summary": "Dockside argument",
                    "consequences": [],
                    "participant_knowledge": {},
                }
            ],
            "meta": {},
        }
        client = self.build_client([json.dumps(payload)])
        backend = LLMExtractionBackend(client)
        accumulated = AccumulatedExtraction()

        result = backend.run_chapter_pass(
            ChapterSource(chapter_id="001", title="Arrival", order_index=1, text="Ships arrive."),
            accumulated,
        )

        self.assertEqual(result.events[0].id, "evt_001")
        transport = client.transport
        self.assertEqual(transport.prompts[0].metadata["chapter_id"], "001")
        self.assertIn('"character_cards": []', transport.prompts[0].user)
        self.assertIn('"timeline_spine"', transport.prompts[0].user)
        self.assertIn("RETRIEVED CHAPTER CONTEXT", transport.prompts[0].user)
        self.assertIn("Primary language: English", transport.prompts[0].user)
        self.assertIn("Return only deltas", transport.prompts[0].user)
        self.assertIn("Keep all free-text fields in the same language as the source text.", transport.prompts[0].user)
        self.assertIn("OUTPUT CONTRACT:", transport.prompts[0].user)
        self.assertEqual(transport.prompts[0].metadata["response_schema"], "AccumulatedExtraction")

    def test_chapter_prompt_prioritizes_relevant_context(self) -> None:
        payload = {
            "characters": [
                {
                    "id": "lu",
                    "name": "路明非",
                    "aliases": ["明非"],
                    "current_state": {"location": "步行街"},
                    "relationships": [{"target_id": "third", "type": "ally"}],
                },
                {
                    "id": "other",
                    "name": "楚子航",
                    "aliases": [],
                    "current_state": {"location": "英灵殿"},
                },
                {
                    "id": "third",
                    "name": "诺诺",
                    "aliases": [],
                    "current_state": {"location": "校园"},
                },
                {
                    "id": "fourth",
                    "name": "老唐",
                    "aliases": [],
                    "current_state": {"location": "街角"},
                },
                {
                    "id": "fifth",
                    "name": "路鸣泽",
                    "aliases": [],
                    "current_state": {"location": "梦境"},
                },
            ],
            "events": [],
            "world": {"locations": ["步行街"], "rules_and_constraints": [], "factions": []},
            "meta": {
                "language_context": {"primary_language": "Chinese"},
                "writing_style": {},
            },
        }
        client = self.build_client([json.dumps({"events": []})])
        backend = LLMExtractionBackend(client)

        backend.run_chapter_pass(
            ChapterSource(chapter_id="002", title="Chapter 1", order_index=2, text="路明非在街上遇见新的邀请。"),
            AccumulatedExtraction.model_validate(payload),
        )

        prompt = client.transport.prompts[0].user
        self.assertIn("路明非", prompt)
        self.assertIn("诺诺", prompt)
        self.assertNotIn("梦境", prompt)

    def test_chapter_prompt_includes_reverse_one_hop_relationship_neighbors(self) -> None:
        payload = {
            "characters": [
                {
                    "id": "lu",
                    "name": "路明非",
                    "aliases": ["明非"],
                    "current_state": {"location": "步行街"},
                },
                {
                    "id": "chen",
                    "name": "陈雯雯",
                    "aliases": [],
                    "relationships": [{"target_id": "lu", "type": "crush"}],
                    "current_state": {"location": "图书馆"},
                },
                {
                    "id": "far",
                    "name": "芬格尔",
                    "aliases": [],
                    "relationships": [{"target_id": "other", "type": "friend"}],
                    "current_state": {"location": "宿舍"},
                },
            ],
            "events": [],
            "world": {"locations": ["步行街"], "rules_and_constraints": [], "factions": []},
            "meta": {
                "language_context": {"primary_language": "Chinese"},
                "writing_style": {},
            },
        }
        client = self.build_client([json.dumps({"events": []})])
        backend = LLMExtractionBackend(client)

        backend.run_chapter_pass(
            ChapterSource(chapter_id="003", title="Chapter 2", order_index=3, text="路明非独自走过步行街。"),
            AccumulatedExtraction.model_validate(payload),
        )

        prompt = client.transport.prompts[0].user
        self.assertIn("陈雯雯", prompt)
        self.assertNotIn("芬格尔", prompt)

    def test_chapter_prompt_uses_structural_timeline_and_cast_for_retrieval_context(self) -> None:
        client = self.build_client([json.dumps({"events": []})])
        backend = LLMExtractionBackend(client)
        structural_scan = StructuralScanPayload.model_validate(
            {
                "world": {
                    "setting": "卡塞尔学院的隐秘世界",
                    "time_period": "2009",
                    "rules_and_constraints": ["必须通过3E考试"],
                    "factions": [{"name": "卡塞尔学院", "goal": "培养屠龙者", "relationships": {}}],
                    "key_locations": [{"name": "英灵殿", "description": "", "narrative_significance": ""}],
                },
                "cast_list": [
                    {
                        "id": "char_001",
                        "name": "路明非",
                        "aliases": ["明非"],
                        "role": "protagonist",
                        "first_appearance": "chapter_001",
                        "tier": 1,
                    }
                ],
                "timeline_skeleton": {
                    "story_start": "高考前三个月",
                    "pre_story_events": ["白帝城旧事"],
                    "known_future_events": ["前往卡塞尔学院"],
                },
                "domain_systems": [
                    {"name": "血统评级", "description": "龙族血统强度", "scale": "S-A-B-C"}
                ],
            }
        )

        backend.run_chapter_pass(
            ChapterSource(
                chapter_id="002",
                title="Chapter 1",
                order_index=2,
                text="路明非收到来自卡塞尔学院的邀请。",
            ),
            AccumulatedExtraction(),
            structural_scan=structural_scan,
        )

        prompt = client.transport.prompts[0].user
        self.assertIn('"story_start": "高考前三个月"', prompt)
        self.assertIn('"name": "路明非"', prompt)
        self.assertIn('"domain_systems"', prompt)
        self.assertIn('"rules_and_constraints"', prompt)

    def test_meta_layer_backend_builds_prompt_and_parses_response(self) -> None:
        payload = {
            "authorial": {
                "central_thesis": {"value": "Power corrodes intimacy", "confidence": "INFERRED"},
                "themes": [{"name": "power", "description": "Power isolates", "confidence": "INFERRED"}],
                "dominant_tone": "bleak",
                "beliefs_about": {"power": "corrupting"},
                "symbolic_motifs": ["ash"],
                "narrative_perspective": "third_limited",
            },
            "writing_style": {
                "prose_description": "short, cold sentences",
                "sentence_rhythm": "clipped",
                "description_density": "sparse",
                "dialogue_narration_balance": "dialogue-led",
                "stylistic_signatures": ["hard stops"],
                "sample_passages": [{"text": "Ash fell.", "why_representative": "minimal"}],
            },
            "language_context": {
                "primary_language": "English",
                "language_variety": "modern literary English",
                "language_style": "compressed, image-heavy, and unsentimental",
                "author_style": "disciplined restraint with sharp tonal pivots",
                "register_profile": "plainspoken narration with occasional ceremonial diction",
                "dialogue_style": "brief, loaded exchanges with emotional withholding",
                "figurative_patterns": ["ash imagery", "hard sensory contrasts"],
                "multilingual_features": ["ritual titles kept untranslated"],
                "translation_notes": ["Preserve the blunt surface and implied menace."],
            },
            "character_voices": [
                {
                    "character_id": "arya",
                    "vocabulary_register": "plain",
                    "speech_patterns": ["short sentences"],
                    "rhetorical_tendencies": "declarative",
                    "gravitates_toward": ["survival"],
                    "what_they_never_say": "I am afraid",
                    "emotional_register": "suppressed",
                    "sample_dialogues": [{"text": "Not today.", "why_representative": "blunt"}],
                }
            ],
            "real_world_context": {
                "written_when": "modern",
                "historical_context": "war",
                "unspeakable_constraints": ["treason"],
                "literary_tradition": "realist",
                "autobiographical_elements": "",
            },
        }
        client = self.build_client([json.dumps(payload)])
        backend = LLMExtractionBackend(client)

        result = backend.run_meta_layer_pass(
            ["[001 | Chapter 1]\nOpening excerpt"],
            major_character_ids=["arya"],
        )

        self.assertEqual(result["language_context"]["primary_language"], "English")
        self.assertEqual(result["character_voices"][0]["character_id"], "arya")
        transport = client.transport
        self.assertEqual(transport.prompts[0].metadata["prompt_name"], "p1_3_meta_layer")
        self.assertIn("MAJOR CHARACTER IDS TO COVER", transport.prompts[0].user)
        self.assertIn("LANGUAGE CONTEXT", transport.prompts[0].user)
        self.assertIn("Primary language: English", transport.prompts[0].user)
        self.assertIn("Do not translate source material into English.", transport.prompts[0].user)
        self.assertIn("OUTPUT CONTRACT:", transport.prompts[0].user)

    def test_chapter_backend_wraps_llm_validation_failure_with_chapter_context(self) -> None:
        client = self.build_client(["{not valid json}"])
        backend = LLMExtractionBackend(client)

        with self.assertRaises(RuntimeError) as ctx:
            backend.run_chapter_pass(
                ChapterSource(chapter_id="004", title="Chapter 3 · 恺撒", order_index=4, text="A duel begins."),
                AccumulatedExtraction(),
            )

        self.assertIn("Chapter extraction failed for 004", str(ctx.exception))
        self.assertIn("p1_2_chapter_extraction", str(ctx.exception.__cause__))


if __name__ == "__main__":
    unittest.main()
