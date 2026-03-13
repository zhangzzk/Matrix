import unittest
from unittest.mock import patch

from dreamdive.config import SimulationSettings
from dreamdive.db.bundle import (
    build_in_memory_bundle,
    build_repository_bundle,
    postgres_backend_available,
)
from dreamdive.db.postgres import MissingPostgresDriverError
from dreamdive.schemas import Goal, NarrativeArcState, ReplayKey
from dreamdive.simulation.session import AgentRuntimeState, SimulationSessionState
from dreamdive.simulation.workflow import build_runtime_bundle, serialize_runtime_history
from dreamdive.schemas import CharacterIdentity, CharacterSnapshot


def make_session() -> SimulationSessionState:
    return SimulationSessionState(
        source_path="novel.md",
        current_tick_label="t1",
        current_timeline_index=10,
        arc_state=NarrativeArcState(
            current_phase="setup",
            tension_level=0.2,
            unresolved_threads=[],
            approaching_climax=False,
        ),
        agents={
            "arya": AgentRuntimeState(
                snapshot=CharacterSnapshot(
                    identity=CharacterIdentity(character_id="arya", name="Arya"),
                    replay_key=ReplayKey(tick="t1", timeline_index=10),
                    current_state={"location": "yard"},
                    goals=[
                        Goal(
                            priority=1,
                            goal="hide",
                            motivation="survival",
                            obstacle="guards",
                            time_horizon="immediate",
                            emotional_charge="fear",
                            abandon_condition="safe route opens",
                        )
                    ],
                    working_memory=[],
                    relationships=[],
                )
            )
        },
        append_only_log={
            "state_changes": [
                {
                    "character_id": "arya",
                    "dimension": "location",
                    "replay_key": {"tick": "t1", "timeline_index": 10, "event_sequence": 0},
                    "to_value": "yard",
                }
            ],
            "goal_stacks": [
                {
                    "character_id": "arya",
                    "replay_key": {"tick": "t1", "timeline_index": 10, "event_sequence": 0},
                    "goals": [
                        {
                            "priority": 1,
                            "goal": "hide",
                            "motivation": "survival",
                            "obstacle": "guards",
                            "time_horizon": "immediate",
                            "emotional_charge": "fear",
                            "abandon_condition": "safe route opens",
                        }
                    ],
                }
            ],
            "relationships": [],
            "episodic_memories": [],
            "entity_representations": [
                {
                    "agent_id": "arya",
                    "entity_id": "ent_gate",
                    "name": "The Gate",
                    "type": "place",
                    "narrative_role": "constraint",
                    "objective_facts": ["north wall"],
                    "belief": "the only exit",
                    "emotional_charge": "fear",
                    "goal_relevance": "reach it unseen",
                    "misunderstanding": "",
                    "confidence": "EXPLICIT",
                    "semantic_text": "gate exit north wall fear",
                    "semantic_embedding": [0.1, 0.2, 0.3],
                }
            ],
            "world_snapshots": [
                {
                    "replay_key": {"tick": "t1", "timeline_index": 10, "event_sequence": 0},
                    "agent_locations": {"arya": "yard"},
                    "narrative_arc": {
                        "current_phase": "setup",
                        "tension_level": 0.2,
                        "unresolved_threads": [],
                        "approaching_climax": False,
                    },
                    "unresolved_threads": [],
                    "next_tick_size_minutes": 30,
                }
            ],
            "event_log": [
                {
                    "event_id": "evt_1",
                    "tick": "t1",
                    "timeline_index": 10,
                    "seed_type": "solo",
                    "location": "yard",
                    "participants": ["arya"],
                    "description": "Arya ducks behind a cart.",
                    "salience": 0.4,
                    "outcome_summary": "She remains hidden.",
                    "resolution_mode": "background",
                }
            ],
            "scheduled_world_events": [],
            "maintenance_log": [],
        },
    )


class RepositoryBundleTests(unittest.TestCase):
    def test_build_in_memory_bundle_returns_store_backed_repositories(self) -> None:
        bundle = build_in_memory_bundle()

        self.assertEqual(bundle.backend_name, "session")
        self.assertIsNotNone(bundle.store)

    def test_build_repository_bundle_supports_session_backend(self) -> None:
        settings = SimulationSettings(persistence_backend="session")

        bundle = build_repository_bundle(settings)

        self.assertEqual(bundle.backend_name, "session")
        self.assertIsNotNone(bundle.store)

    def test_build_repository_bundle_raises_without_psycopg_for_postgres(self) -> None:
        settings = SimulationSettings(persistence_backend="postgres")

        with self.assertRaises(MissingPostgresDriverError):
            build_repository_bundle(settings)

    def test_postgres_backend_available_reports_false_without_driver(self) -> None:
        self.assertFalse(postgres_backend_available(SimulationSettings(persistence_backend="postgres")))

    def test_build_runtime_bundle_restores_session_log_into_store(self) -> None:
        bundle = build_runtime_bundle(session=make_session())

        self.assertIsNotNone(bundle.store)
        self.assertEqual(bundle.backend_name, "session")
        self.assertEqual(bundle.store.state_change_log[0].to_value, "yard")
        self.assertEqual(bundle.store.entity_representations[0].entity_id, "ent_gate")

    def test_serialize_runtime_history_reads_from_bundle_repositories(self) -> None:
        bundle = build_runtime_bundle(session=make_session())

        history = serialize_runtime_history(
            bundle,
            agent_ids=("arya",),
            timeline_index=10,
        )

        self.assertEqual(len(history["state_changes"]), 1)
        self.assertEqual(len(history["goal_stacks"]), 1)
        self.assertEqual(len(history["entity_representations"]), 1)
        self.assertEqual(len(history["world_snapshots"]), 1)
        self.assertEqual(history["event_log"][0]["event_id"], "evt_1")

    def test_build_runtime_bundle_restores_history_into_selected_bundle(self) -> None:
        with patch(
            "dreamdive.simulation.workflow.build_repository_bundle",
            return_value=build_in_memory_bundle(),
        ):
            bundle = build_runtime_bundle(
                session=make_session(),
                settings=SimulationSettings(persistence_backend="postgres"),
            )

        self.assertIsNotNone(bundle.store)
        self.assertEqual(bundle.store.event_log[0].event_id, "evt_1")


if __name__ == "__main__":
    unittest.main()
