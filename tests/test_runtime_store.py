import json
import tempfile
import unittest
from pathlib import Path

from dreamdive.config import SimulationSettings
from dreamdive.schemas import (
    CharacterIdentity,
    CharacterSnapshot,
    Goal,
    NarrativeArcState,
    ReplayKey,
    SnapshotInference,
)
from dreamdive.simulation.runtime_store import (
    PostgresSimulationRuntimeStore,
    SimulationRuntimeStore,
    build_runtime_store,
)
from dreamdive.simulation.session import AgentRuntimeState, SimulationSessionState


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
                            description="hide; survival; fear",
                            challenge="guards; safe route opens",
                            time_horizon="immediate",
                        )
                    ],
                    working_memory=[],
                    relationships=[],
                )
            )
        },
        metadata={"note": "checkpoint"},
    )


class FakeCursor:
    def __init__(self, responses, executed):
        self.responses = responses
        self.executed = executed
        self.description = []
        self.current = {}

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params):
        self.executed.append((sql, params))
        self.current = self.responses.pop(0) if self.responses else {}
        row = self.current.get("one")
        if isinstance(row, dict):
            self.description = [(key,) for key in row.keys()]

    def fetchone(self):
        return self.current.get("one")


class FakeConnection:
    def __init__(self, responses, executed):
        self.responses = responses
        self.executed = executed
        self.commits = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def cursor(self):
        return FakeCursor(self.responses, self.executed)

    def commit(self):
        self.commits += 1


class FakeConnectionFactory:
    def __init__(self, responses):
        self.responses = list(responses)
        self.executed = []
        self.connections = []

    def __call__(self):
        connection = FakeConnection(self.responses, self.executed)
        self.connections.append(connection)
        return connection


class RuntimeStoreTests(unittest.TestCase):
    def test_file_runtime_store_uses_session_specific_filename(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            store = SimulationRuntimeStore(workspace, session_id="branch_a")
            session = make_session()

            store.save(session)
            loaded = store.load()

            self.assertTrue(store.exists())
            self.assertEqual(store.path.name, "simulation_session.branch_a.json")
            self.assertEqual(loaded.current_tick_label, "t1")
            self.assertEqual(loaded.metadata["note"], "checkpoint")

    def test_postgres_runtime_store_saves_loads_and_checks_existence(self) -> None:
        session = make_session()
        payload = json.dumps(session.model_dump(mode="json"), sort_keys=True)
        factory = FakeConnectionFactory(
            [
                {},
                {"one": {"session_payload": payload}},
                {"one": {"session_id": "alpha"}},
            ]
        )
        store = PostgresSimulationRuntimeStore(factory, session_id="alpha")

        store.save(session)
        loaded = store.load()
        exists = store.exists()

        self.assertEqual(loaded.source_path, "novel.md")
        self.assertTrue(exists)
        self.assertIn("INSERT INTO simulation_session", factory.executed[0][0])
        self.assertIn("ON CONFLICT (session_id) DO UPDATE", factory.executed[0][0])
        self.assertEqual(factory.executed[0][1][0], "alpha")
        self.assertIn("SELECT session_payload", factory.executed[1][0])
        self.assertEqual(factory.connections[0].commits, 1)

    def test_build_runtime_store_switches_on_persistence_backend(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            file_store = build_runtime_store(
                workspace,
                settings=SimulationSettings(persistence_backend="session"),
                session_id="default",
            )
            postgres_store = build_runtime_store(
                workspace,
                settings=SimulationSettings(persistence_backend="postgres"),
                session_id="remote",
                connection_factory=lambda: None,
            )

            self.assertIsInstance(file_store, SimulationRuntimeStore)
            self.assertIsInstance(postgres_store, PostgresSimulationRuntimeStore)

    def test_runtime_store_repairs_legacy_session_state_on_load(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            store = SimulationRuntimeStore(workspace)
            base_session = make_session()
            session = base_session.model_copy(
                update={
                    "agents": {
                        "arya": base_session.agents["arya"].model_copy(
                            update={
                                "snapshot": base_session.agents["arya"].snapshot.model_copy(
                                    update={
                                        "current_state": {"location": "", "emotional_state": {"dominant": "fear"}},
                                        "inferred_state": SnapshotInference(
                                            emotional_summary="fear",
                                            immediate_tension="guards are near",
                                            unspoken_subtext="",
                                            physical_status="hiding",
                                            location="yard",
                                            knowledge=[],
                                        ),
                                    }
                                )
                            }
                        )
                    },
                    "pending_background_jobs": [
                        {
                            "job_type": "arc_update",
                            "target_id": "world",
                            "run_after_timeline_index": 120,
                            "reason": "legacy interval",
                        }
                    ],
                    "append_only_log": {
                        "state_changes": [
                            {
                                "character_id": "arya",
                                "dimension": "emotional_state",
                                "replay_key": {"tick": "t1", "timeline_index": 10, "event_sequence": 0},
                                "to_value": {"dominant_now": "fear"},
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
                                "next_tick_size_minutes": 60,
                            }
                        ],
                        "scheduled_world_events": [
                            {
                                "event_id": "evt_1_bridge_arya",
                                "trigger_timeline_index": 70,
                                "description": "Rumor reaches 艾莉亚: Guards are closing in.",
                                "affected_agents": ["arya"],
                                "location": "yard",
                                "urgency": "low",
                            }
                        ],
                    },
                    "pending_world_events": [
                        {
                            "event_id": "evt_1_bridge_arya",
                            "trigger_timeline_index": 70,
                            "description": "News reaches 艾莉亚: Guards are closing in.",
                            "affected_agents": ["arya"],
                            "location": "yard",
                            "urgency": "low",
                        }
                    ],
                    "metadata": {"language_guidance": "- Primary language: 中文 (简体)"},
                }
            )

            store.save(session)
            loaded = store.load()

            self.assertEqual(loaded.agents["arya"].snapshot.current_state["location"], "yard")
            self.assertEqual(
                loaded.agents["arya"].snapshot.current_state["emotional_state"],
                "fear",
            )
            self.assertEqual(
                loaded.append_only_log["state_changes"][0]["to_value"],
                "fear",
            )
            self.assertEqual(loaded.pending_background_jobs[0]["schedule_basis"], "tick_count")
            self.assertEqual(loaded.metadata["tick_count"], 1)
            self.assertEqual(loaded.metadata["last_tick_minutes"], 60)
            # Session repair strips legacy per-character wrappers from descriptions
            self.assertEqual(
                loaded.append_only_log["scheduled_world_events"][0]["description"],
                "Guards are closing in.",
            )
            self.assertEqual(
                loaded.pending_world_events[0]["description"],
                "Guards are closing in.",
            )


if __name__ == "__main__":
    unittest.main()
