import json
import unittest

from dreamdive.config import LLMProfileSettings
from dreamdive.llm.client import StructuredLLMClient
from dreamdive.schemas import (
    CharacterIdentity,
    EpisodicMemory,
    RelationshipLogEntry,
    ReplayKey,
    SnapshotInference,
    StateChangeLogEntry,
)
from dreamdive.simulation.initializer import (
    SnapshotInitializationInput,
    SnapshotInitializer,
)
from dreamdive.simulation.prompts import (
    build_goal_seed_prompt,
    build_snapshot_inference_prompt,
)


class RecordingTransport:
    def __init__(self, responses):
        self.responses = responses
        self.calls = 0
        self.prompts = []

    async def complete(self, profile, prompt):
        self.prompts.append(prompt)
        response = self.responses[self.calls]
        self.calls += 1
        return response


class FailingTransport:
    async def complete(self, profile, prompt):
        raise RuntimeError(f"synthetic failure for {profile.name}")


class SnapshotInitializationTests(unittest.TestCase):
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

    def test_snapshot_prompts_include_expected_metadata(self) -> None:
        identity = CharacterIdentity(character_id="arya", name="Arya Stark")
        inference_prompt = build_snapshot_inference_prompt(
            identity=identity,
            text_excerpt="Arya watches from the shadows.",
            event_summary_up_to_t=["She escaped the castle."],
            location="courtyard",
            nearby_characters=["Sansa"],
            language_guidance="- Primary language: English\n- Author style: lean and cold",
        )
        goal_prompt = build_goal_seed_prompt(
            identity=identity,
            inferred_state=SnapshotInference.model_validate(
                {
                    "emotional_state": {
                        "dominant": "fear",
                        "secondary": ["defiance"],
                        "confidence": 0.8,
                    },
                    "immediate_tension": "Avoid discovery",
                    "unspoken_subtext": "She wants revenge.",
                    "physical_state": {
                        "energy": 0.6,
                        "injuries_or_constraints": "",
                        "location": "courtyard",
                        "current_activity": "hiding",
                    },
                    "knowledge_state": {
                        "new_knowledge": ["The guard changed routes."],
                        "active_misbeliefs": [],
                    },
                }
            ),
            recent_events=["She escaped the castle."],
            relationships=[],
            language_guidance="- Primary language: English\n- Dialogue style: brief and loaded",
        )

        self.assertEqual(inference_prompt.metadata["prompt_name"], "p2_1_snapshot_inference")
        self.assertEqual(goal_prompt.metadata["prompt_name"], "p2_2_goal_seeding")
        self.assertIn("Arya watches from the shadows.", inference_prompt.user)
        self.assertIn("LANGUAGE AND STYLE CONTEXT", inference_prompt.user)
        self.assertIn("OUTPUT CONTRACT:", inference_prompt.user)
        self.assertIn("Dialogue style: brief and loaded", goal_prompt.user)
        self.assertIn("OUTPUT CONTRACT:", goal_prompt.user)

    def test_snapshot_initializer_combines_llm_outputs_with_replayed_state(self) -> None:
        inference_response = json.dumps(
            {
                "emotional_state": {
                    "dominant": "fear",
                    "secondary": ["defiance"],
                    "confidence": 0.9,
                },
                "immediate_tension": "Avoid discovery",
                "unspoken_subtext": "She wants to strike back but cannot yet.",
                "physical_state": {
                    "energy": 0.5,
                    "injuries_or_constraints": "minor bruising",
                    "location": "courtyard",
                    "current_activity": "hiding",
                },
                "knowledge_state": {
                    "new_knowledge": ["The guard changed routes."],
                    "active_misbeliefs": ["Sansa is safe"],
                },
            }
        )
        goal_response = json.dumps(
            {
                "goal_stack": [
                    {
                        "priority": 1,
                        "goal": "escape the castle unnoticed",
                        "motivation": "survival",
                        "obstacle": "guards sweeping the yard",
                        "time_horizon": "immediate",
                        "emotional_charge": "urgent fear",
                        "abandon_condition": "find safe allies",
                    }
                ],
                "actively_avoiding": "thinking about her father",
                "most_uncertain_relationship": "Sansa",
            }
        )
        client = self.build_client([inference_response, goal_response])
        initializer = SnapshotInitializer(client)
        replay_key = ReplayKey(tick="chapter_12", timeline_index=12)
        payload = SnapshotInitializationInput(
            identity=CharacterIdentity(character_id="arya", name="Arya Stark"),
            replay_key=replay_key,
            text_excerpt="Arya watches from the shadows.",
            event_summary_up_to_t=["She escaped the castle."],
            nearby_characters=["Sansa"],
            state_entries=[
                StateChangeLogEntry(
                    character_id="arya",
                    dimension="location",
                    replay_key=ReplayKey(tick="chapter_11", timeline_index=11),
                    to_value="courtyard",
                )
            ],
            memories=[
                EpisodicMemory(
                    character_id="arya",
                    replay_key=ReplayKey(tick="chapter_10", timeline_index=10),
                    summary="Needle hidden in the straw.",
                    salience=0.9,
                    pinned=True,
                )
            ],
            relationships=[
                RelationshipLogEntry(
                    from_character_id="arya",
                    to_character_id="sansa",
                    replay_key=replay_key,
                    trust_value=0.4,
                    trust_delta=-0.1,
                    sentiment_shift="strained worry",
                    reason="conflicting choices",
                )
            ],
            language_guidance="- Primary language: English\n- Author style: clipped and unsentimental",
            default_state={"location": "unknown"},
        )

        snapshot = initializer.initialize(payload)

        self.assertEqual(snapshot.current_state["location"], "courtyard")
        self.assertEqual(snapshot.inferred_state.immediate_tension, "Avoid discovery")
        self.assertEqual(snapshot.goals[0].goal, "escape the castle unnoticed")
        transport = client.transport
        self.assertEqual(len(transport.prompts), 2)
        self.assertEqual(
            transport.prompts[0].metadata["prompt_name"],
            "p2_1_snapshot_inference",
        )
        self.assertIn("Author style: clipped and unsentimental", transport.prompts[0].user)

    def test_snapshot_initializer_falls_back_to_heuristics_when_llm_fails(self) -> None:
        client = StructuredLLMClient(
            primary=LLMProfileSettings(
                name="moonshot",
                base_url="https://api.moonshot.ai/v1",
                model="kimi-k2.5",
            ),
            transport=FailingTransport(),
            retry_attempts=1,
            retry_delay_seconds=0,
        )
        initializer = SnapshotInitializer(client)
        replay_key = ReplayKey(tick="chapter_03", timeline_index=3)
        payload = SnapshotInitializationInput(
            identity=CharacterIdentity(
                character_id="lumingfei",
                name="路明非",
                desires=["弄清楚发生了什么"],
                fears=["被当成异类"],
            ),
            replay_key=replay_key,
            text_excerpt="路明非盯着窗外，觉得一切都不太对劲。",
            event_summary_up_to_t=["他刚刚经历了一场难以解释的异常。"],
            nearby_characters=["楚子航"],
            goal_hints=["先稳住局面"],
            state_entries=[
                StateChangeLogEntry(
                    character_id="lumingfei",
                    dimension="location",
                    replay_key=ReplayKey(tick="chapter_02", timeline_index=2),
                    to_value="宿舍",
                ),
                StateChangeLogEntry(
                    character_id="lumingfei",
                    dimension="emotional_state",
                    replay_key=ReplayKey(tick="chapter_02", timeline_index=2),
                    to_value="心神不宁",
                ),
            ],
            memories=[],
            relationships=[],
            language_guidance="- Primary language: Chinese",
            default_state={"location": "宿舍"},
        )

        snapshot = initializer.initialize(payload)
        issues = client.drain_issue_records()

        self.assertEqual(snapshot.current_state["location"], "宿舍")
        self.assertEqual(snapshot.inferred_state.emotional_state.dominant, "心神不宁")
        self.assertEqual(snapshot.goals[0].goal, "先稳住局面")
        self.assertTrue(any(issue.get("severity") == "critical" for issue in issues))


if __name__ == "__main__":
    unittest.main()
