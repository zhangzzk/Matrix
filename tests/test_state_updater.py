import json
import unittest

from dreamdive.config import LLMProfileSettings
from dreamdive.llm.client import StructuredLLMClient
from dreamdive.schemas import (
    CharacterIdentity,
    CharacterSnapshot,
    Goal,
    ReplayKey,
    SnapshotInference,
)
from dreamdive.simulation.state_updater import EventStateUpdater


class RecordingTransport:
    def __init__(self, responses):
        self.responses = responses
        self.calls = 0

    async def complete(self, profile, prompt):
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


def make_snapshot():
    return CharacterSnapshot(
        identity=CharacterIdentity(
            character_id="ned",
            name="Ned Stark",
            fears=["failing his family"],
            values=["honor"],
            desires=["protect the children"],
        ),
        replay_key=ReplayKey(tick="chapter_03", timeline_index=3),
        current_state={"location": "throne_room"},
        goals=[
            Goal(
                priority=1,
                goal="protect the children",
                motivation="duty",
                obstacle="royal power",
                time_horizon="immediate",
                emotional_charge="grave resolve",
                abandon_condition="children are safe",
            )
        ],
        working_memory=[],
        relationships=[],
        inferred_state=SnapshotInference.model_validate(
            {
                "emotional_state": {
                    "dominant": "dread",
                    "secondary": ["resolve"],
                    "confidence": 0.9,
                },
                "immediate_tension": "Cersei already knows",
                "unspoken_subtext": "This was never negotiation",
                "physical_state": {
                    "energy": 0.6,
                    "injuries_or_constraints": "",
                    "location": "throne_room",
                    "current_activity": "standing firm",
                },
                "knowledge_state": {
                    "new_knowledge": [],
                    "active_misbeliefs": [],
                },
            }
        ),
    )


class StateUpdaterTests(unittest.TestCase):
    def test_state_updater_emits_diffs_and_goal_stack(self) -> None:
        response = {
            "emotional_delta": {
                "dominant_now": "protective fury",
                "underneath": "dread",
                "shift_reason": "Threat to the children became explicit",
            },
            "goal_stack_update": {
                "top_goal_status": "advanced",
                "top_goal_still_priority": True,
                "new_goal": {
                    "priority": 2,
                    "goal": "buy time to get the girls away",
                    "motivation": "honor and duty",
                    "obstacle": "guards and political isolation",
                    "time_horizon": "immediate",
                    "emotional_charge": "urgent resolve",
                    "abandon_condition": "safe escape route secured",
                },
                "resolved_goal": None,
            },
            "relationship_updates": [
                {
                    "target_id": "cersei",
                    "trust_delta": -0.4,
                    "sentiment_shift": "wary respect -> open hostility",
                    "pinned": True,
                    "pin_reason": "The confrontation in the throne room",
                }
            ],
            "needs_reprojection": True,
            "reprojection_reason": "A new urgent tactical goal emerged",
        }
        updater = EventStateUpdater(build_client([json.dumps(response)]))
        replay_key = ReplayKey(tick="day_003_noon", timeline_index=30)

        result = updater.update_after_event(
            snapshot=make_snapshot(),
            event_id="evt_042",
            replay_key=replay_key,
            event_outcome_from_agent_perspective="Cersei made the threat plain.",
            new_knowledge=["Cersei will move against the children."],
        )

        self.assertEqual(result.state_changes[0].dimension, "emotional_state")
        self.assertEqual(result.state_changes[0].to_value, "protective fury")
        self.assertEqual(result.state_changes[1].dimension, "knowledge_state")
        self.assertEqual(result.goal_stack.goals[0].goal, "protect the children")
        self.assertEqual(result.goal_stack.goals[1].goal, "buy time to get the girls away")
        self.assertTrue(result.needs_reprojection)
        self.assertEqual(result.relationship_changes[0].to_character_id, "cersei")


if __name__ == "__main__":
    unittest.main()
