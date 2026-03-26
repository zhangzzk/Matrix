import json
import unittest

from dreamdive.config import LLMProfileSettings
from dreamdive.llm.client import StructuredLLMClient
from dreamdive.schemas import (
    BackgroundEventPayload,
    CharacterIdentity,
    CharacterSnapshot,
    Goal,
    ReplayKey,
    SnapshotInference,
)
from dreamdive.simulation.event_prompts import (
    build_background_event_prompt,
    build_state_update_prompt,
)
from dreamdive.simulation.event_simulator import EventSimulator
from dreamdive.simulation.seeds import SimulationSeed


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


def make_snapshot(character_id, name, location, goal_text):
    return CharacterSnapshot(
        identity=CharacterIdentity(
            character_id=character_id,
            name=name,
            fears=["failure"],
            values=["duty"],
            desires=["protect family"],
        ),
        replay_key=ReplayKey(tick="chapter_02", timeline_index=2),
        current_state={"location": location},
        goals=[
            Goal(
                priority=1,
                description=f"{goal_text}; duty; tense",
                challenge="conflict; safety restored",
                time_horizon="immediate",
            )
        ],
        working_memory=[],
        relationships=[],
        inferred_state=SnapshotInference(
            emotional_summary="anxious",
            immediate_tension="Keep control",
            unspoken_subtext="Cannot admit fear",
            physical_status="waiting",
            location=location,
            knowledge=[],
        ),
    )


class EventSimulationTests(unittest.TestCase):
    def test_background_prompt_has_expected_metadata(self) -> None:
        seed = SimulationSeed(
            seed_id="seed_1",
            seed_type="solo",
            participants=["arya"],
            location="courtyard",
            description="Arya slips past the guard.",
        )
        prompt = build_background_event_prompt(
            seed=seed,
            snapshots=[make_snapshot("arya", "Arya", "courtyard", "escape")],
            current_time="day_1_noon",
            writing_style_note="short and cold",
            language_guidance="- Primary language: English\n- Dialogue style: sharp and compressed",
        )

        self.assertEqual(prompt.metadata["prompt_name"], "p2_5_background_event")
        self.assertFalse(prompt.stream)
        self.assertIn("Arya slips past the guard.", prompt.user)
        self.assertIn("Dialogue style: sharp and compressed", prompt.user)
        self.assertIn('"narrative_summary"', prompt.user)

    def test_background_simulation_parses_payload(self) -> None:
        payload = BackgroundEventPayload(
            narrative_summary="Arya slips by without being seen.",
            outcomes=[],
        )
        client = build_client([json.dumps(payload.model_dump(mode="json"))])
        simulator = EventSimulator(client)
        seed = SimulationSeed(
            seed_id="seed_1",
            seed_type="solo",
            participants=["arya"],
            location="courtyard",
            description="Arya slips past the guard.",
        )

        result = simulator.simulate_background(
            seed=seed,
            snapshots=[make_snapshot("arya", "Arya", "courtyard", "escape")],
            current_time="day_1_noon",
            writing_style_note="short and cold",
            language_guidance="- Primary language: English\n- Author style: lean and severe",
        )

        self.assertEqual(result.narrative_summary, "Arya slips by without being seen.")

    def test_spotlight_simulation_keeps_internal_private_between_agents(self) -> None:
        setup = {
            "scene_opening": "They meet in the courtyard.",
            "resolution_conditions": {
                "primary": "One yields",
                "secondary": "A bargain is struck",
                "forced_exit": "The bell interrupts them",
            },
            "agent_perceptions": {"arya": "Sees Sansa watching", "sansa": "Sees Arya tense"},
            "tension_signature": "Family loyalty under threat",
        }
        beat_arya = {
            "internal": {
                "thought": "I cannot trust her",
                "emotion_now": "fear",
                "goal_update": "leave fast",
                "what_i_noticed": "the gate is open",
            },
            "external": {
                "dialogue": "Do not follow me.",
                "physical_action": "steps back",
                "tone": "sharp",
            },
            "held_back": "asking for help",
        }
        resolution_continue = {
            "resolved": False,
            "resolution_type": "continue",
            "scene_outcome": "",
            "continue": True,
        }
        beat_sansa = {
            "internal": {
                "thought": "She is more frightened than angry",
                "emotion_now": "hurt",
                "goal_update": "keep Arya close",
                "what_i_noticed": "Arya is ready to run",
            },
            "external": {
                "dialogue": "Arya, wait.",
                "physical_action": "reaches out",
                "tone": "soft",
            },
            "held_back": "accusing her",
        }
        resolution_end = {
            "resolved": True,
            "resolution_type": "secondary",
            "scene_outcome": "They part without agreement.",
            "continue": False,
        }
        client = build_client(
            [
                json.dumps(setup),
                json.dumps(beat_arya),
                json.dumps(beat_sansa),
            ]
        )
        simulator = EventSimulator(client)
        seed = SimulationSeed(
            seed_id="spot_1",
            seed_type="spatial_collision",
            participants=["arya", "sansa"],
            location="courtyard",
            description="A tense reunion",
            salience=0.9,
        )

        result = simulator.simulate_spotlight(
            seed=seed,
            snapshots=[
                make_snapshot("arya", "Arya", "courtyard", "escape"),
                make_snapshot("sansa", "Sansa", "courtyard", "keep peace"),
            ],
            narrative_phase="rising_action",
            tension_level=0.8,
            relevant_threads=["family fracture"],
            voice_samples_by_agent={"arya": ["short, sharp"], "sansa": ["soft, formal"]},
            world_entities_by_agent={
                "arya": [
                    {
                        "entity_id": "ent_letter",
                        "name": "The Letter",
                        "belief": "proof of betrayal",
                    }
                ],
                "sansa": [],
            },
            max_beats=2,
            use_unified=False,
        )

        self.assertEqual(len(result.transcript), 2)
        self.assertEqual(result.transcript[0].external["dialogue"], "Do not follow me.")
        self.assertEqual(result.private_state_by_agent["arya"][0]["thought"], "I cannot trust her")
        transport = client.transport
        sansa_prompt = transport.prompts[2]
        self.assertNotIn('"thought": "I cannot trust her"', sansa_prompt.user)
        self.assertIn('"dialogue": "Do not follow me."', sansa_prompt.user)
        arya_prompt = transport.prompts[1]
        # Entity system disabled — world entities no longer appear in beat prompts.
        self.assertNotIn('"name": "The Letter"', arya_prompt.user)

    def test_state_update_prompt_uses_agent_perspective(self) -> None:
        snapshot = make_snapshot("arya", "Arya", "courtyard", "escape")
        prompt = build_state_update_prompt(
            snapshot=snapshot,
            event_outcome_from_agent_perspective="Sansa reached for her arm and Arya pulled away.",
            new_knowledge=["Sansa saw the gate."],
            language_guidance="- Primary language: English\n- Author style: lean and severe",
        )

        self.assertEqual(prompt.metadata["prompt_name"], "p2_7_state_update")
        self.assertIn("Sansa reached for her arm", prompt.user)
        self.assertIn("Author style: lean and severe", prompt.user)


if __name__ == "__main__":
    unittest.main()
