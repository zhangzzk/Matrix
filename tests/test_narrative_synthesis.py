import json
import unittest

from dreamdive.config import LLMProfileSettings
from dreamdive.ingestion.models import MetaLayerRecord
from dreamdive.llm.client import StructuredLLMClient
from dreamdive.narrative_synthesis import (
    ChapterWindow,
    EventSummary,
    NarrativeSynthesisBackend,
)
from dreamdive.prompts.p5_synthesis import (
    build_chapter_synthesis_prompt,
    build_unified_synthesis_prompt,
)
from dreamdive.user_config import UserMeta


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


def build_client(responses):
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


def make_meta() -> MetaLayerRecord:
    return MetaLayerRecord.model_validate(
        {
            "writing_style": {
                "sentence_rhythm": "clipped, pressure-driven",
                "dialogue_narration_balance": "dialogue-led with sharp narration bridges",
                "chapter_format": {
                    "heading_style": "Chinese numbered act headings with short title",
                    "heading_examples": ["第一幕 卡塞尔之门"],
                    "opening_pattern": "Opens with sensory pressure before clarifying the immediate conflict",
                    "closing_pattern": "Ends on a threat, reveal, or hard pivot",
                    "paragraphing_style": "Short to medium paragraphs with clean blank-line breaks",
                },
            },
            "design_tendencies": {
                "story_architecture": {
                    "chapter_architecture": "Begins with a titled chapter heading, then accelerates through one central collision.",
                }
            },
            "language_context": {
                "primary_language": "Chinese",
                "language_style": "economical and vivid",
                "author_style": "high-contrast and ironic",
                "dialogue_style": "brief and tactical",
            },
        }
    )


def make_window() -> ChapterWindow:
    return ChapterWindow(
        tick_range="tick_0010-tick_0019",
        events=[
            EventSummary(
                event_id="evt_1",
                salience=0.82,
                participants=["char_001"],
                location="courtyard",
                summary="路明非在庭院里做了一个危险决定。",
                state_changes={"char_001": {"resolve": "hardened"}},
            )
        ],
        high_salience_events=["evt_1"],
    )


class NarrativeSynthesisTests(unittest.TestCase):
    def test_chapter_synthesis_prompt_includes_format_guidance_and_plot_constraints(self) -> None:
        prompt = build_chapter_synthesis_prompt(
            make_window(),
            make_meta(),
            UserMeta(),
            chapter_number=12,
            source_heading_examples=["第一幕 卡塞尔之门", "第二幕 黄金瞳"],
        )

        self.assertIn("CHAPTER FORMAT:", prompt.user)
        self.assertIn("Learned heading style", prompt.user)
        self.assertIn("Source chapter heading examples:", prompt.user)
        self.assertIn("第一幕 卡塞尔之门", prompt.user)
        self.assertIn("This is chapter 12", prompt.user)
        self.assertIn("These event records are canonical.", prompt.user)
        self.assertIn("High-salience events must appear on-page.", prompt.user)

    def test_synthesize_chapter_prepends_source_style_heading_when_model_omits_one(self) -> None:
        client = build_client(["路明非觉得不对劲。"])
        backend = NarrativeSynthesisBackend(client)

        chapter_text = backend.synthesize_chapter(
            make_window(),
            make_meta(),
            UserMeta(),
            chapter_number=3,
            source_heading_examples=["第一幕 卡塞尔之门", "第二幕 黄金瞳"],
        )

        self.assertEqual(chapter_text, "第三幕\n\n路明非觉得不对劲。")
        self.assertIn("第一幕 卡塞尔之门", client.transport.prompts[0].user)


    def test_unified_synthesis_prompt_requests_json_with_both_keys(self) -> None:
        prompt = build_unified_synthesis_prompt(
            make_window(),
            make_meta(),
            UserMeta(),
            chapter_number=5,
            source_heading_examples=["第一幕 卡塞尔之门", "第二幕 黄金瞳"],
        )

        self.assertIn("chapter_text", prompt.system)
        self.assertIn("summary", prompt.system)
        self.assertIn("chapter_text", prompt.user)
        self.assertIn("summary", prompt.user)
        self.assertEqual(prompt.metadata["prompt_name"], "p5_3_unified_synthesis")

    def test_synthesize_and_summarize_returns_both_in_one_call(self) -> None:
        unified_response = json.dumps(
            {
                "chapter_text": "路明非觉得不对劲。",
                "summary": "路明非在庭院里做出了一个危险的决定。",
            }
        )
        client = build_client([unified_response])
        backend = NarrativeSynthesisBackend(client)

        chapter_text, summary = backend.synthesize_and_summarize(
            make_window(),
            make_meta(),
            UserMeta(),
            chapter_number=3,
            source_heading_examples=["第一幕 卡塞尔之门", "第二幕 黄金瞳"],
        )

        # Heading should be prepended since the model omitted it.
        self.assertEqual(chapter_text, "第三幕\n\n路明非觉得不对劲。")
        self.assertEqual(summary, "路明非在庭院里做出了一个危险的决定。")
        # Only ONE LLM call should have been made.
        self.assertEqual(client.transport.calls, 1)


if __name__ == "__main__":
    unittest.main()
