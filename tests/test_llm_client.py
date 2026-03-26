import asyncio
import json
import tempfile
import unittest
from pathlib import Path

from pydantic import BaseModel

from dreamdive.config import LLMProfileSettings, SimulationSettings
from dreamdive.debug import DebugSession
from dreamdive.ingestion.models import AccumulatedExtraction
from dreamdive.llm.client import StructuredLLMClient
from dreamdive.llm.openai_transport import TransportError
from dreamdive.schemas import (
    GoalCollisionBatchPayload,
    GoalSeedPayload,
    NarrativeArcUpdatePayload,
    PromptRequest,
    ResolutionCheckPayload,
    SnapshotInference,
    StateUpdatePayload,
    TrajectoryProjectionPayload,
)


class FakeResponse(BaseModel):
    answer: str


class FakeTransport:
    def __init__(self, responses: list[str]) -> None:
        self.responses = responses
        self.calls = 0
        self.prompts = []

    async def complete(self, profile: LLMProfileSettings, prompt: PromptRequest) -> str:
        self.prompts.append(prompt)
        response = self.responses[self.calls]
        self.calls += 1
        return response


class StructuredLLMClientTests(unittest.TestCase):
    def test_from_settings_uses_all_configured_profiles_in_order(self) -> None:
        settings = SimulationSettings(
            llm_provider_order=["moonshot", "gemini", "openai", "qwen"],
            llm_moonshot_api_key="moonshot-key",
            llm_gemini_api_key="gemini-key",
            llm_openai_api_key="openai-key",
        )

        client = StructuredLLMClient.from_settings(
            transport=FakeTransport(responses=[]),
            settings=settings,
        )

        self.assertEqual(
            [profile.name for profile in client.profiles],
            ["moonshot", "gemini", "openai"],
        )

    def test_llm_client_retries_and_uses_fallback(self) -> None:
        transport = FakeTransport(
            responses=[
                "{not valid json}",
                json.dumps({"answer": "validated"}),
            ]
        )
        client = StructuredLLMClient(
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
            transport=transport,
            retry_attempts=1,
            retry_delay_seconds=0,
        )

        response = asyncio.run(
            client.call_json(
                PromptRequest(system="You are JSON", user="Return JSON"),
                FakeResponse,
            )
        )

        self.assertEqual(response.answer, "validated")
        self.assertEqual(transport.calls, 2)

    def test_llm_client_uses_third_provider_when_first_two_fail(self) -> None:
        transport = FakeTransport(
            responses=[
                "{not valid json}",
                "{still not valid json}",
                json.dumps({"answer": "from-third-provider"}),
            ]
        )
        client = StructuredLLMClient(
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
            additional_profiles=[
                LLMProfileSettings(
                    name="openai",
                    base_url="https://api.openai.com/v1",
                    model="gpt-5-mini",
                )
            ],
            transport=transport,
            retry_attempts=1,
            retry_delay_seconds=0,
        )

        response = asyncio.run(
            client.call_json(
                PromptRequest(system="You are JSON", user="Return JSON"),
                FakeResponse,
            )
        )

        self.assertEqual(response.answer, "from-third-provider")
        self.assertEqual(transport.calls, 3)

    def test_llm_client_uses_correction_prompt_on_validation_retry(self) -> None:
        transport = FakeTransport(
            responses=[
                "{not valid json}",
                json.dumps({"answer": "fixed"}),
            ]
        )
        client = StructuredLLMClient(
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
            transport=transport,
            retry_attempts=2,
            retry_delay_seconds=0,
        )

        response = asyncio.run(
            client.call_json(
                PromptRequest(system="You are JSON", user="Return JSON"),
                FakeResponse,
            )
        )

        self.assertEqual(response.answer, "fixed")
        self.assertEqual(transport.calls, 2)
        self.assertIn("previous response was invalid json", transport.prompts[1].user.lower())
        self.assertIn("return valid json matching this schema", transport.prompts[1].user.lower())
        self.assertEqual(transport.prompts[1].system, "You are JSON")
        self.assertFalse(transport.prompts[1].stream)

    def test_provider_usage_summary_tracks_successful_profiles_in_order(self) -> None:
        transport = FakeTransport(
            responses=[
                "{not valid json}",
                json.dumps({"answer": "validated"}),
            ]
        )
        client = StructuredLLMClient(
            primary=LLMProfileSettings(
                name="moonshot",
                base_url="https://api.moonshot.ai/v1",
                model="kimi-k2.5",
            ),
            fallback=LLMProfileSettings(
                name="gemini",
                base_url="https://generativelanguage.googleapis.com/v1beta/openai",
                model="gemini-2.5-flash-lite",
            ),
            transport=transport,
            retry_attempts=1,
            retry_delay_seconds=0,
        )

        response = asyncio.run(
            client.call_json(
                PromptRequest(system="You are JSON", user="Return JSON"),
                FakeResponse,
            )
        )

        self.assertEqual(response.answer, "validated")
        self.assertEqual(
            client.provider_usage_summary(),
            {
                "ordered_profiles": ["gemini"],
                "counts": {"gemini": 1},
                "total_calls": 1,
            },
        )

    def test_provider_usage_summary_respects_configured_profile_order(self) -> None:
        client = StructuredLLMClient(
            profiles=[
                LLMProfileSettings(
                    name="qwen",
                    base_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
                    model="qwen3.5-flash",
                ),
                LLMProfileSettings(
                    name="moonshot",
                    base_url="https://api.moonshot.ai/v1",
                    model="kimi-k2.5",
                ),
                LLMProfileSettings(
                    name="gemini",
                    base_url="https://generativelanguage.googleapis.com/v1beta/openai",
                    model="gemini-2.5-flash-lite",
                ),
                LLMProfileSettings(
                    name="openai",
                    base_url="https://api.openai.com/v1",
                    model="gpt-5-mini",
                ),
            ],
            transport=FakeTransport(responses=[]),
            retry_attempts=1,
            retry_delay_seconds=0,
        )
        client.success_records.extend(
            [
                {"profile_name": "openai"},
                {"profile_name": "qwen"},
                {"profile_name": "moonshot"},
            ]
        )

        self.assertEqual(
            client.provider_usage_summary(),
            {
                "ordered_profiles": ["qwen", "moonshot", "openai"],
                "counts": {"openai": 1, "qwen": 1, "moonshot": 1},
                "total_calls": 3,
            },
        )

    def test_llm_client_extracts_json_wrapped_in_prose(self) -> None:
        transport = FakeTransport(
            responses=[
                "先给你结果。\n\n```json\n{\"answer\": \"validated\"}\n```"
            ]
        )
        client = StructuredLLMClient(
            primary=LLMProfileSettings(
                name="qwen",
                base_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
                model="qwen3.5-flash",
            ),
            transport=transport,
            retry_attempts=1,
            retry_delay_seconds=0,
        )

        response = asyncio.run(
            client.call_json(
                PromptRequest(system="You are JSON", user="Return JSON"),
                FakeResponse,
            )
        )

        self.assertEqual(response.answer, "validated")

    def test_prompt_types_share_the_same_configured_provider_order(self) -> None:
        class RecordingProfileTransport:
            def __init__(self) -> None:
                self.profile_names = []

            async def complete(self, profile: LLMProfileSettings, _prompt: PromptRequest) -> str:
                self.profile_names.append(profile.name)
                return json.dumps({"answer": profile.name})

        transport = RecordingProfileTransport()
        client = StructuredLLMClient(
            profiles=[
                LLMProfileSettings(
                    name="qwen",
                    base_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
                    model="qwen3.5-flash",
                ),
                LLMProfileSettings(
                    name="moonshot",
                    base_url="https://api.moonshot.ai/v1",
                    model="kimi-k2.5",
                ),
            ],
            transport=transport,
            retry_attempts=1,
            retry_delay_seconds=0,
        )

        response = asyncio.run(
            client.call_json(
                PromptRequest(
                    system="You are JSON",
                    user="Return JSON",
                    metadata={"prompt_name": "p2_6_agent_beat"},
                ),
                FakeResponse,
            )
        )

        self.assertEqual(response.answer, "qwen")
        self.assertEqual(transport.profile_names, ["qwen"])

    def test_llm_client_includes_prompt_name_and_schema_in_final_validation_error(self) -> None:
        transport = FakeTransport(responses=["{not valid json}", "{still not valid json}"])
        client = StructuredLLMClient(
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
            transport=transport,
            retry_attempts=1,
            retry_delay_seconds=0,
        )

        with self.assertRaises(RuntimeError) as ctx:
            asyncio.run(
                client.call_json(
                    PromptRequest(
                        system="You are JSON",
                        user="Return JSON",
                        metadata={"prompt_name": "p1_2_chapter_extraction"},
                    ),
                    FakeResponse,
                )
            )

        self.assertIn("p1_2_chapter_extraction", str(ctx.exception))
        self.assertIn("FakeResponse", str(ctx.exception))

    def test_llm_client_labels_empty_response_body_clearly(self) -> None:
        transport = FakeTransport(responses=["", ""])
        client = StructuredLLMClient(
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
            transport=transport,
            retry_attempts=1,
            retry_delay_seconds=0,
        )

        with self.assertRaises(RuntimeError) as ctx:
            asyncio.run(
                client.call_json(
                    PromptRequest(
                        system="You are JSON",
                        user="Return JSON",
                        metadata={"prompt_name": "p1_2_chapter_extraction"},
                    ),
                    FakeResponse,
                )
            )

        self.assertIn("empty response body", str(ctx.exception).lower())

    def test_llm_client_records_critical_terminal_issue_when_all_providers_fail(self) -> None:
        transport = FakeTransport(responses=["", ""])
        client = StructuredLLMClient(
            primary=LLMProfileSettings(
                name="moonshot",
                base_url="https://api.moonshot.ai/v1",
                model="kimi-k2.5",
            ),
            fallback=LLMProfileSettings(
                name="gemini",
                base_url="https://generativelanguage.googleapis.com/v1beta/openai",
                model="gemini-2.5-flash-lite",
            ),
            transport=transport,
            retry_attempts=1,
            retry_delay_seconds=0,
        )

        with self.assertRaises(RuntimeError):
            asyncio.run(
                client.call_json(
                    PromptRequest(
                        system="You are JSON",
                        user="Return JSON",
                        metadata={"prompt_name": "p2_5_background_event"},
                    ),
                    FakeResponse,
                )
            )

        issues = client.drain_issue_records()
        terminal = issues[-1]
        self.assertEqual(terminal["stage"], "exhausted")
        self.assertEqual(terminal["severity"], "critical")
        self.assertEqual(terminal["profiles_tried"], ["moonshot", "gemini"])

    def test_llm_client_rejects_english_ingestion_text_when_chinese_is_expected(self) -> None:
        transport = FakeTransport(
            responses=[
                json.dumps(
                    {
                        "events": [
                            {
                                "id": "evt_001",
                                "summary": "Lu Mingfei receives a mysterious letter from Cassell College.",
                            }
                        ]
                    }
                ),
                json.dumps(
                    {
                        "events": [
                            {
                                "id": "evt_001",
                                "summary": "路明非收到卡塞尔学院寄来的神秘信件。",
                            }
                        ]
                    }
                ),
            ]
        )
        client = StructuredLLMClient(
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
            transport=transport,
            retry_attempts=2,
            retry_delay_seconds=0,
        )

        response = asyncio.run(
            client.call_json(
                PromptRequest(
                    system="You are JSON",
                    user="Primary language: Chinese\nReturn JSON",
                    metadata={"prompt_name": "p1_2_chapter_extraction"},
                ),
                AccumulatedExtraction,
            )
        )

        self.assertEqual(response.events[0].summary, "路明非收到卡塞尔学院寄来的神秘信件。")
        self.assertEqual(transport.calls, 2)
        self.assertIn("primary language: chinese", transport.prompts[1].user.lower())

    def test_llm_client_normalizes_common_ingestion_aliases(self) -> None:
        transport = FakeTransport(
            responses=[
                json.dumps(
                    {
                        "characters": {
                            "hero": {
                                "character_id": "hero",
                                "display_name": "Hero",
                                "current_state": {"goals": "escape"},
                                "relationships": {"friend": "trusted ally"},
                            }
                        },
                        "world": {
                            "locations": [{"name": "yard"}],
                            "factions": [{"name": "watch"}],
                        },
                        "events": {
                            "first": {
                                "event_id": "evt_1",
                                "description": "Alarm rings",
                                "participants": "hero",
                            }
                        },
                        "meta": {
                            "authorial": {"central_thesis": "Fear reveals character"}
                        },
                    }
                )
            ]
        )
        client = StructuredLLMClient(
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
            transport=transport,
            retry_attempts=1,
            retry_delay_seconds=0,
        )

        response = asyncio.run(
            client.call_json(
                PromptRequest(system="You are JSON", user="Return JSON"),
                AccumulatedExtraction,
            )
        )

        self.assertEqual(response.characters[0].name, "Hero")
        self.assertEqual(response.characters[0].current_state.goal_stack, ["escape"])
        self.assertEqual(response.events[0].participants, ["hero"])
        self.assertEqual(response.meta.authorial.central_thesis["summary"], "Fear reveals character")

    def test_llm_client_reports_transport_failure_as_request_failure(self) -> None:
        class FailingTransport:
            async def complete(self, _profile, _prompt):
                raise TransportError("LLM transport timed out after 90 seconds")

        client = StructuredLLMClient(
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
            transport=FailingTransport(),
            retry_attempts=1,
            retry_delay_seconds=0,
        )

        with self.assertRaises(RuntimeError) as ctx:
            asyncio.run(
                client.call_json(
                    PromptRequest(
                        system="You are JSON",
                        user="Return JSON",
                        metadata={"prompt_name": "p1_2_chapter_extraction"},
                    ),
                    AccumulatedExtraction,
                )
            )

        self.assertIn("LLM request for p1_2_chapter_extraction", str(ctx.exception))
        self.assertIn("timed out after 90 seconds", str(ctx.exception))

    def test_llm_client_normalizes_snapshot_inference_aliases(self) -> None:
        transport = FakeTransport(
            responses=[
                json.dumps(
                    {
                        "psychological_state": "惊惧与压抑并存",
                        "tension": "必须立刻判断眼前的异象是真是假",
                        "subtext": "他害怕自己已经失控",
                        "physical_state": "冷汗和僵硬让他几乎无法放松",
                        "knowledge_state": "只知道异象与自己有关，但不知道原因",
                    }
                )
            ]
        )
        client = StructuredLLMClient(
            primary=LLMProfileSettings(
                name="qwen",
                base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
                model="qwen3.5-flash",
            ),
            transport=transport,
            retry_attempts=1,
            retry_delay_seconds=0,
        )

        response = asyncio.run(
            client.call_json(
                PromptRequest(system="You are JSON", user="Return JSON"),
                SnapshotInference,
            )
        )

        self.assertEqual(response.emotional_summary, "惊惧与压抑并存")
        self.assertEqual(response.immediate_tension, "必须立刻判断眼前的异象是真是假")
        self.assertIn("冷汗和僵硬让他几乎无法放松", response.physical_status)
        self.assertIn(
            "只知道异象与自己有关，但不知道原因",
            response.knowledge,
        )

    def test_llm_client_normalizes_goal_seed_aliases(self) -> None:
        transport = FakeTransport(
            responses=[
                json.dumps(
                    {
                        "goals": [
                            {
                                "priority": 1,
                                "action": "先稳住局面，不让别人看出异常",
                                "why": "避免局势彻底失控",
                                "risk": "一旦暴露会立刻陷入被动",
                                "emotion": "紧绷的恐惧",
                                "stop_when": "确认身边有可靠援手",
                            }
                        ],
                        "avoiding": "承认自己已经害怕了",
                        "relationship_uncertainty": "楚子航",
                    }
                )
            ]
        )
        client = StructuredLLMClient(
            primary=LLMProfileSettings(
                name="qwen",
                base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
                model="qwen3.5-flash",
            ),
            transport=transport,
            retry_attempts=1,
            retry_delay_seconds=0,
        )

        response = asyncio.run(
            client.call_json(
                PromptRequest(system="You are JSON", user="Return JSON"),
                GoalSeedPayload,
            )
        )

        self.assertIn("先稳住局面，不让别人看出异常", response.goal_stack[0].description)
        self.assertIn("一旦暴露会立刻陷入被动", response.goal_stack[0].challenge)
        self.assertEqual(response.goal_stack[0].time_horizon.value, "today")
        self.assertEqual(response.actively_avoiding, "承认自己已经害怕了")
        self.assertEqual(response.most_uncertain_relationship, "楚子航")

    def test_llm_client_preserves_stream_flag_on_correction_retry(self) -> None:
        transport = FakeTransport(
            responses=[
                "{not valid json}",
                json.dumps({"answer": "fixed"}),
            ]
        )
        client = StructuredLLMClient(
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
            transport=transport,
            retry_attempts=2,
            retry_delay_seconds=0,
        )

        response = asyncio.run(
            client.call_json(
                PromptRequest(system="You are JSON", user="Return JSON", stream=True),
                FakeResponse,
            )
        )

        self.assertEqual(response.answer, "fixed")
        self.assertTrue(transport.prompts[0].stream)
        self.assertTrue(transport.prompts[1].stream)

    def test_llm_client_records_debug_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            debug_session = DebugSession.create(debug_dir=Path(tmpdir))
            transport = FakeTransport(
                responses=[
                    json.dumps({"answer": "logged"}),
                ]
            )
            client = StructuredLLMClient(
                primary=LLMProfileSettings(
                    name="moonshot",
                    api_key="secret",
                    base_url="https://api.moonshot.ai/v1",
                    model="kimi-k2.5",
                ),
                fallback=LLMProfileSettings(
                    name="gemini",
                    api_key="secret",
                    base_url="https://generativelanguage.googleapis.com/v1beta/openai",
                    model="gemini-3.1-flash-lite-preview",
                ),
                transport=transport,
                retry_attempts=1,
                retry_delay_seconds=0,
                debug_session=debug_session,
            )

            response = asyncio.run(
                client.call_json(
                    PromptRequest(
                        system="You are JSON",
                        user="Return JSON",
                        metadata={"prompt_name": "debug_prompt"},
                    ),
                    FakeResponse,
                )
            )

            self.assertEqual(response.answer, "logged")
            llm_dir = debug_session.root_dir / "llm"
            attempt_dirs = list(llm_dir.iterdir())
            self.assertEqual(len(attempt_dirs), 1)
            self.assertTrue((attempt_dirs[0] / "request.json").exists())
            self.assertTrue((attempt_dirs[0] / "response.txt").exists())
            self.assertTrue((attempt_dirs[0] / "parsed.json").exists())
            self.assertTrue((debug_session.root_dir / "session.json").exists())

    def test_debug_session_uses_unique_child_directory_for_configured_parent(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            parent = Path(tmpdir)
            first = DebugSession.create(debug_dir=parent)
            second = DebugSession.create(debug_dir=parent)

            self.assertEqual(first.root_dir.parent, parent)
            self.assertEqual(second.root_dir.parent, parent)
            self.assertNotEqual(first.root_dir, second.root_dir)
            self.assertTrue((first.root_dir / "llm").exists())
            self.assertTrue((second.root_dir / "llm").exists())

    def test_llm_client_normalizes_common_trajectory_aliases(self) -> None:
        transport = FakeTransport(
            responses=[
                json.dumps(
                    {
                        "primary_intention": "stay hidden",
                        "immediate_next_action": "wait behind the crates",
                        "contingencies": [
                            "If the guard turns, slip deeper into shadow.",
                            "If Arya is spotted: run for the gate",
                        ],
                        "greatest_fear": "being seen",
                        "abandon_condition": "safe route opens",
                        "held_back_impulse": "run immediately",
                    }
                )
            ]
        )
        client = StructuredLLMClient(
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
            transport=transport,
            retry_attempts=1,
            retry_delay_seconds=0,
        )

        response = asyncio.run(
            client.call_json(
                PromptRequest(system="You are JSON", user="Return JSON"),
                TrajectoryProjectionPayload,
            )
        )

        # Legacy fields are merged into the unified fields.
        self.assertIn("stay hidden", response.intention)
        self.assertIn("being seen", response.intention)
        self.assertIn("safe route opens", response.intention)
        self.assertIn("run immediately", response.intention)
        self.assertIn("wait behind the crates", response.next_steps)
        self.assertIn("If the guard turns", response.next_steps)

    def test_llm_client_normalizes_goal_collision_aliases(self) -> None:
        transport = FakeTransport(
            responses=[
                json.dumps(
                    {
                        "tensions": [
                            {
                                "involved_agents": ["arya", "gendry"],
                                "tension_type": "ethical_dissonance",
                                "description": "They want the same thing for different reasons.",
                                "severity": 0.8,
                            }
                        ],
                        "solo_seeds": [
                            {
                                "character_id": "arya",
                                "seed": "Arya considers leaving alone.",
                            }
                        ],
                        "world_events": [
                            {
                                "event_name": "Gate opens",
                                "impact": "High",
                                "description": "The gate suddenly opens.",
                            }
                        ],
                    }
                )
            ]
        )
        client = StructuredLLMClient(
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
            transport=transport,
            retry_attempts=1,
            retry_delay_seconds=0,
        )

        response = asyncio.run(
            client.call_json(
                PromptRequest(system="You are JSON", user="Return JSON"),
                GoalCollisionBatchPayload,
            )
        )

        self.assertEqual(response.goal_tensions[0].agents, ["arya", "gendry"])
        self.assertEqual(response.goal_tensions[0].type, "ethical_dissonance")
        self.assertEqual(response.goal_tensions[0].likelihood, "0.8")
        self.assertEqual(response.solo_seeds[0].agent_id, "arya")
        self.assertEqual(response.solo_seeds[0].description, "Arya considers leaving alone.")
        self.assertEqual(response.world_events[0].urgency, "High")

    def test_llm_client_normalizes_nested_arc_update_assessment(self) -> None:
        transport = FakeTransport(
            responses=[
                json.dumps(
                    {
                        "narrative_assessment": {
                            "phase": "escalation",
                            "tension_level": 0.725,
                            "unresolved_threads": [
                                "Liberty Day (fallout)",
                                {
                                    "id": "bronze_plan",
                                    "description": "Bronze Plan containment breach",
                                    "participants": ["Lu Mingfei", "Chu Zihang"],
                                },
                            ],
                            "approaching_nodes": [
                                {
                                    "description": "Arc climax setup",
                                    "ticks_away": 2,
                                    "salience": 0.9,
                                }
                            ],
                        },
                        "narrative_drift": {
                            "needs_correction": True,
                            "description": "The setup is lingering too long.",
                            "correction": "Escalate institutional pressure.",
                        },
                    }
                )
            ]
        )
        client = StructuredLLMClient(
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
            transport=transport,
            retry_attempts=1,
            retry_delay_seconds=0,
        )

        response = asyncio.run(
            client.call_json(
                PromptRequest(system="You are JSON", user="Return JSON"),
                NarrativeArcUpdatePayload,
            )
        )

        self.assertEqual(response.phase, "escalation")
        self.assertAlmostEqual(response.tension_level, 0.725)
        self.assertEqual(response.unresolved_threads[0].thread_id, "Liberty Day (fallout)")
        self.assertEqual(response.unresolved_threads[1].thread_id, "bronze_plan")
        self.assertEqual(response.approaching_nodes[0].estimated_ticks_away, 2)
        self.assertTrue(response.narrative_drift.drifting)
        self.assertEqual(
            response.narrative_drift.suggested_correction,
            "Escalate institutional pressure.",
        )

    def test_llm_client_retries_when_chinese_output_leaks_into_english_text(self) -> None:
        transport = FakeTransport(
            responses=[
                json.dumps(
                    {
                        "goal_tensions": [
                            {
                                "tension_id": "tension_001",
                                "type": "goal_conflict",
                                "agents": ["路明非", "楚子航"],
                                "location": "Lu Mingfei's bedroom",
                                "description": "Chu Zihang tries to recover the sample while Lu Mingfei wants complete isolation.",
                                "information_asymmetry": {},
                                "stakes": {},
                                "likelihood": "very likely",
                                "salience_factors": ["conflicting goals", "personal exposure"],
                            }
                        ],
                        "solo_seeds": [],
                        "world_events": [],
                    }
                ),
                json.dumps(
                    {
                        "goal_tensions": [
                            {
                                "tension_id": "tension_001",
                                "type": "goal_conflict",
                                "agents": ["路明非", "楚子航"],
                                "location": "路明非的卧室",
                                "description": "楚子航试图强行回收样本，而路明非只想把自己彻底隔绝起来。",
                                "information_asymmetry": {},
                                "stakes": {},
                                "likelihood": "very likely",
                                "salience_factors": ["目标冲突", "身份暴露"],
                            }
                        ],
                        "solo_seeds": [],
                        "world_events": [],
                    }
                ),
            ]
        )
        client = StructuredLLMClient(
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
            transport=transport,
            retry_attempts=2,
            retry_delay_seconds=0,
        )

        response = asyncio.run(
            client.call_json(
                PromptRequest(
                    system="You are JSON",
                    user=(
                        "LANGUAGE AND STYLE CONTEXT:\n"
                        "- Primary language: 中文 (简体)\n\n"
                        "OUTPUT LANGUAGE RULES:\n"
                        "- Keep every free-text value in the primary language above.\n\n"
                        "Return JSON"
                    ),
                ),
                GoalCollisionBatchPayload,
            )
        )

        self.assertEqual(transport.calls, 2)
        self.assertEqual(response.goal_tensions[0].location, "路明非的卧室")

    def test_llm_client_normalizes_resolution_and_state_update_aliases(self) -> None:
        transport = FakeTransport(
            responses=[
                json.dumps({"condition_met": False}),
                json.dumps(
                    {
                        "emotional_delta": {
                            "from": "fear",
                            "to": "focus",
                            "reasoning": "The patrol moved away.",
                        },
                        "goal_stack_update": {
                            "remove": ["stay hidden"],
                            "current_primary_goal": "reach the gate",
                        },
                        "relationship_updates": {
                            "gendry": {
                                "status": "warier",
                                "note": "He saw Arya hesitate.",
                            }
                        },
                        "reprojection_decision": {
                            "recalculate": True,
                            "reasoning": "The tactical window changed.",
                        },
                    }
                ),
            ]
        )
        client = StructuredLLMClient(
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
            transport=transport,
            retry_attempts=1,
            retry_delay_seconds=0,
        )

        resolution = asyncio.run(
            client.call_json(
                PromptRequest(system="You are JSON", user="Return JSON"),
                ResolutionCheckPayload,
            )
        )
        state_update = asyncio.run(
            client.call_json(
                PromptRequest(system="You are JSON", user="Return JSON"),
                StateUpdatePayload,
            )
        )

        self.assertFalse(resolution.resolved)
        self.assertEqual(resolution.resolution_type, "continue")
        self.assertTrue(resolution.continue_scene)
        self.assertEqual(state_update.emotional_delta.dominant_now, "focus")
        self.assertEqual(state_update.goal_stack_update.resolved_goal, "stay hidden")
        self.assertTrue(state_update.needs_reprojection)
        self.assertEqual(state_update.relationship_updates[0].target_id, "gendry")


if __name__ == "__main__":
    unittest.main()
