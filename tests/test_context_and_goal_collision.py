import json
import unittest

from dreamdive.config import LLMProfileSettings
from dreamdive.llm.client import StructuredLLMClient
from dreamdive.memory.retrieval import embed_text
from dreamdive.schemas import (
    CharacterIdentity,
    CharacterSnapshot,
    EpisodicMemory,
    Goal,
    RelationshipLogEntry,
    ReplayKey,
    SnapshotInference,
)
from dreamdive.simulation.context import ContextAssembler
from dreamdive.simulation.goal_collision import GoalCollisionDetector


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


def make_snapshot(character_id, name, location, target_id):
    return CharacterSnapshot(
        identity=CharacterIdentity(
            character_id=character_id,
            name=name,
            fears=["failure"],
            values=["duty"],
            desires=["win"],
        ),
        replay_key=ReplayKey(tick="chapter_05", timeline_index=5),
        current_state={"location": location, "emotional_state": "tense"},
        goals=[
            Goal(
                priority=1,
                goal="secure the letter",
                motivation="survival",
                obstacle="rival claim",
                time_horizon="immediate",
                emotional_charge="urgent",
                abandon_condition="letter is gone",
            )
        ],
        working_memory=[
            EpisodicMemory(
                character_id=character_id,
                replay_key=ReplayKey(tick="chapter_04", timeline_index=4),
                summary="A critical warning arrived.",
                salience=0.8,
                semantic_score=0.7,
                pinned=True,
            )
        ],
        relationships=[
            RelationshipLogEntry(
                from_character_id=character_id,
                to_character_id=target_id,
                replay_key=ReplayKey(tick="chapter_04", timeline_index=4),
                trust_value=-0.2,
                trust_delta=-0.1,
                sentiment_shift="suspicion",
                reason="competing interests",
            )
        ],
        inferred_state=SnapshotInference.model_validate(
            {
                "emotional_state": {
                    "dominant": "tense",
                    "secondary": ["focused"],
                    "confidence": 0.8,
                },
                "immediate_tension": "Get there first",
                "unspoken_subtext": "The rival cannot be trusted",
                "physical_state": {
                    "energy": 0.8,
                    "injuries_or_constraints": "",
                    "location": location,
                    "current_activity": "moving",
                },
                "knowledge_state": {
                    "new_knowledge": [],
                    "active_misbeliefs": [],
                },
            }
        ),
    )


class ContextAndGoalCollisionTests(unittest.TestCase):
    def test_context_assembler_filters_relationships_to_scene_participants(self) -> None:
        snapshot = make_snapshot("arya", "Arya", "yard", "sansa")
        assembler = ContextAssembler()

        packet = assembler.assemble(
            snapshot=snapshot,
            scene_description="A tense meeting in the yard",
            scene_participants=["sansa"],
            time_label="day_1_noon",
        )

        self.assertEqual(packet.identity["character_id"], "arya")
        self.assertEqual(packet.relationship_context[0]["target_id"], "sansa")
        self.assertEqual(packet.working_memory, ["A critical warning arrived."])

    def test_context_assembler_retrieves_scene_relevant_memories_from_pool(self) -> None:
        snapshot = make_snapshot("arya", "Arya", "yard", "sansa")
        assembler = ContextAssembler()
        memory_pool = snapshot.working_memory + [
            EpisodicMemory(
                character_id="arya",
                replay_key=ReplayKey(tick="chapter_03", timeline_index=3),
                summary="Sansa hid the letter in the yard wall.",
                participants=["sansa"],
                location="yard",
                salience=0.4,
                pinned=False,
            ),
            EpisodicMemory(
                character_id="arya",
                replay_key=ReplayKey(tick="chapter_02", timeline_index=2),
                summary="A cook burned the bread in the kitchen.",
                participants=["cook"],
                location="kitchen",
                salience=0.7,
                pinned=False,
            ),
        ]

        packet = assembler.assemble(
            snapshot=snapshot,
            scene_description="Arya searches the yard for Sansa's missing letter",
            scene_participants=["sansa"],
            time_label="day_1_noon",
            episodic_memories=memory_pool,
            max_memories=2,
        )

        self.assertIn("Sansa hid the letter in the yard wall.", packet.working_memory)
        self.assertNotIn("A cook burned the bread in the kitchen.", packet.working_memory)

    def test_context_assembler_uses_memory_embeddings_for_relevance(self) -> None:
        snapshot = make_snapshot("arya", "Arya", "yard", "sansa")

        packet = ContextAssembler().assemble(
            snapshot=snapshot,
            scene_description="Arya searches the yard for Sansa's missing letter",
            scene_participants=["sansa"],
            time_label="day_1_noon",
            episodic_memories=[
                EpisodicMemory(
                    character_id="arya",
                    replay_key=ReplayKey(tick="chapter_03", timeline_index=3),
                    summary="A vague unease lingered all afternoon.",
                    participants=["sansa"],
                    location="yard",
                    salience=0.35,
                    pinned=False,
                    embedding=embed_text("yard sansa letter hidden wall search"),
                ),
                EpisodicMemory(
                    character_id="arya",
                    replay_key=ReplayKey(tick="chapter_02", timeline_index=2),
                    summary="The kitchen smelled like smoke and bread.",
                    participants=["cook"],
                    location="kitchen",
                    salience=0.7,
                    pinned=False,
                    embedding=embed_text("kitchen bread smoke cook"),
                ),
            ],
            max_memories=1,
        )

        self.assertEqual(
            packet.working_memory,
            ["A vague unease lingered all afternoon."],
        )

    def test_context_assembler_keeps_pinned_memory_even_when_limit_is_one(self) -> None:
        snapshot = make_snapshot("arya", "Arya", "yard", "sansa")
        snapshot = snapshot.model_copy(
            update={
                "working_memory": [
                    EpisodicMemory(
                        character_id="arya",
                        replay_key=ReplayKey(tick="chapter_04", timeline_index=4),
                        summary="A critical warning arrived.",
                        salience=0.8,
                        semantic_score=0.1,
                        pinned=True,
                    ),
                    EpisodicMemory(
                        character_id="arya",
                        replay_key=ReplayKey(tick="chapter_05", timeline_index=5),
                        summary="Sansa hid the letter in the yard wall.",
                        participants=["sansa"],
                        location="yard",
                        salience=0.4,
                        pinned=False,
                    ),
                ]
            }
        )

        packet = ContextAssembler().assemble(
            snapshot=snapshot,
            scene_description="Arya searches the yard for Sansa's missing letter",
            scene_participants=["sansa"],
            time_label="day_1_noon",
            max_memories=1,
        )

        self.assertEqual(
            packet.working_memory,
            ["A critical warning arrived.", "Sansa hid the letter in the yard wall."],
        )

    def test_context_assembler_truncates_goals_and_filters_world_entities(self) -> None:
        snapshot = make_snapshot("arya", "Arya", "yard", "sansa").model_copy(
            update={
                "goals": [
                    Goal(
                        priority=1,
                        goal="secure the letter",
                        motivation="survival",
                        obstacle="sansa",
                        time_horizon="immediate",
                        emotional_charge="urgent",
                        abandon_condition="letter is gone",
                    ),
                    Goal(
                        priority=2,
                        goal="reach the gate",
                        motivation="escape",
                        obstacle="guards",
                        time_horizon="today",
                        emotional_charge="tense",
                        abandon_condition="the yard is sealed",
                    ),
                    Goal(
                        priority=3,
                        goal="find gendry",
                        motivation="alliance",
                        obstacle="distance",
                        time_horizon="today",
                        emotional_charge="hope",
                        abandon_condition="he already fled",
                    ),
                    Goal(
                        priority=4,
                        goal="sleep",
                        motivation="rest",
                        obstacle="danger",
                        time_horizon="today",
                        emotional_charge="exhausted",
                        abandon_condition="danger passes",
                    ),
                ]
            }
        )

        packet = ContextAssembler().assemble(
            snapshot=snapshot,
            scene_description="Arya studies the gate and plots an escape route.",
            scene_participants=["sansa"],
            time_label="day_1_noon",
            world_entities=[
                {
                    "entity_id": "ent_gate",
                    "name": "The Gate",
                    "type": "place",
                    "narrative_role": "escape route",
                    "belief": "the only way out",
                    "goal_relevance": "reach it unseen",
                    "emotional_charge": "fear",
                },
                {
                    "entity_id": "ent_kitchen",
                    "name": "The Kitchen",
                    "type": "place",
                    "narrative_role": "background",
                    "belief": "smells like bread",
                    "goal_relevance": "none",
                    "emotional_charge": "",
                },
            ],
        )

        self.assertEqual(len(packet.current_state["active_goals"]), 3)
        self.assertEqual(packet.current_state["active_goals"][0]["goal"], "secure the letter")
        self.assertEqual(packet.current_state["active_goals"][-1]["goal"], "find gendry")
        self.assertEqual([entity["entity_id"] for entity in packet.world_entities], ["ent_gate"])

    def test_context_assembler_uses_entity_embeddings_without_leaking_internal_fields(self) -> None:
        snapshot = make_snapshot("arya", "Arya", "yard", "sansa")

        packet = ContextAssembler().assemble(
            snapshot=snapshot,
            scene_description="Arya studies the gate and plots an escape route.",
            scene_participants=["sansa"],
            time_label="day_1_noon",
            world_entities=[
                {
                    "entity_id": "ent_hidden_exit",
                    "name": "Object Alpha",
                    "type": "artifact",
                    "narrative_role": "unknown",
                    "belief": "unclear",
                    "goal_relevance": "none",
                    "emotional_charge": "",
                    "semantic_text": "gate escape route unseen guards",
                    "semantic_embedding": embed_text("gate escape route unseen guards"),
                },
                {
                    "entity_id": "ent_kitchen",
                    "name": "Object Beta",
                    "type": "room",
                    "narrative_role": "background",
                    "belief": "bread and soot",
                    "goal_relevance": "none",
                    "emotional_charge": "",
                    "semantic_text": "kitchen oven bread smoke",
                    "semantic_embedding": embed_text("kitchen oven bread smoke"),
                },
            ],
        )

        self.assertEqual([entity["entity_id"] for entity in packet.world_entities], ["ent_hidden_exit"])
        self.assertNotIn("semantic_embedding", packet.world_entities[0])
        self.assertNotIn("semantic_text", packet.world_entities[0])

    def test_goal_collision_detector_parses_batched_tensions(self) -> None:
        response = {
            "goal_tensions": [
                {
                    "tension_id": "col_001",
                    "type": "goal",
                    "agents": ["arya", "sansa"],
                    "location": "yard",
                    "description": "Both are moving toward the same letter for opposite reasons.",
                    "information_asymmetry": {"arya": "knows it's hidden", "sansa": "does not"},
                    "stakes": {"arya": "survival", "sansa": "family standing"},
                    "emergence_probability": 0.9,
                    "salience_factors": ["proximity", "information_asymmetry"],
                }
            ],
            "solo_seeds": [],
            "world_events": [],
        }
        client = build_client([json.dumps(response)])
        detector = GoalCollisionDetector(client)
        snapshots = [
            make_snapshot("arya", "Arya", "yard", "sansa"),
            make_snapshot("sansa", "Sansa", "yard", "arya"),
        ]
        contexts = {
            snapshot.identity.character_id: ContextAssembler().assemble(
                snapshot=snapshot,
                scene_description="tick planning",
                scene_participants=[],
                time_label="day_1_noon",
            )
            for snapshot in snapshots
        }
        trajectories = {
            "arya": {
                "primary_intention": "secure the letter",
                "motivation": "survival",
                "immediate_next_action": "reach the tower first",
                "contingencies": [],
                "greatest_fear_this_horizon": "being caught",
                "abandon_condition": "letter destroyed",
                "held_back_impulse": "attack immediately",
                "projection_horizon": "4 ticks",
            },
            "sansa": {
                "primary_intention": "secure the letter",
                "motivation": "family duty",
                "immediate_next_action": "ask the steward for access",
                "contingencies": [],
                "greatest_fear_this_horizon": "being too late",
                "abandon_condition": "proof disappears",
                "held_back_impulse": "accuse Arya",
                "projection_horizon": "4 ticks",
            },
        }
        trajectories = {
            key: type("Trajectory", (), value)()  # simple attribute object for the detector
            for key, value in trajectories.items()
        }

        payload = detector.detect_goal_collisions(
            current_time="day_1_noon",
            snapshots=snapshots,
            trajectories=trajectories,
            contexts=contexts,
            world_state_summary={"locations": {"arya": "yard", "sansa": "yard"}},
            tension_level=0.6,
        )

        self.assertEqual(payload.goal_tensions[0].tension_id, "col_001")
        self.assertEqual(client.transport.prompts[0].metadata["prompt_name"], "p2_4_goal_collision_detection")
        seeds = detector.tensions_to_seeds(payload)
        self.assertEqual(seeds[0].seed_id, "col_001")
        self.assertEqual(seeds[0].participants, ["arya", "sansa"])


if __name__ == "__main__":
    unittest.main()
