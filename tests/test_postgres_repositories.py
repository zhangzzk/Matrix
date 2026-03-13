import unittest

from dreamdive.db.postgres import (
    PostgresEntityRepresentationRepository,
    PostgresEpisodicMemoryRepository,
    PostgresEventLogRepository,
    PostgresGoalStackRepository,
    PostgresStateChangeLogRepository,
    PostgresWorldSnapshotRepository,
    goal_stack_idempotency_key,
    normalize_database_url,
    state_change_idempotency_key,
    world_snapshot_idempotency_key,
)
from dreamdive.schemas import (
    EpisodicMemory,
    Goal,
    GoalStackSnapshot,
    NarrativeArcState,
    ReplayKey,
    StateChangeLogEntry,
    SubjectiveEntityRepresentation,
    WorldSnapshot,
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
        rows = self.current.get("all", [])
        sample = row or (rows[0] if rows else {})
        if isinstance(sample, dict):
            self.description = [(key,) for key in sample.keys()]

    def fetchone(self):
        return self.current.get("one")

    def fetchall(self):
        return self.current.get("all", [])


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


class PostgresRepositoryTests(unittest.TestCase):
    def test_normalize_database_url_strips_sqlalchemy_driver_suffix(self) -> None:
        self.assertEqual(
            normalize_database_url("postgresql+psycopg://dreamdive:pw@localhost/db"),
            "postgresql://dreamdive:pw@localhost/db",
        )

    def test_state_change_append_uses_insert_and_maps_returning_row(self) -> None:
        factory = FakeConnectionFactory(
            [
                {
                    "one": {
                        "id": 7,
                        "character_id": "arya",
                        "dimension": "location",
                        "tick": "t1",
                        "timeline_index": 10,
                        "event_sequence": 0,
                        "event_id": "evt_1",
                        "from_value": '"yard"',
                        "to_value": '"crypt"',
                        "trigger": "heard a bell",
                        "emotional_tag": "fear",
                        "pinned": False,
                    }
                }
            ]
        )
        repo = PostgresStateChangeLogRepository(factory)

        record = repo.append(
            StateChangeLogEntry(
                character_id="arya",
                dimension="location",
                replay_key=ReplayKey(tick="t1", timeline_index=10),
                event_id="evt_1",
                from_value="yard",
                to_value="crypt",
                trigger="heard a bell",
                emotional_tag="fear",
            )
        )

        self.assertEqual(record.id, 7)
        self.assertEqual(record.to_value, "crypt")
        self.assertIn("INSERT INTO state_change_log", factory.executed[0][0])
        self.assertIn("ON CONFLICT (idempotency_key) DO UPDATE", factory.executed[0][0])
        self.assertEqual(
            factory.executed[0][1][0],
            state_change_idempotency_key(
                StateChangeLogEntry(
                    character_id="arya",
                    dimension="location",
                    replay_key=ReplayKey(tick="t1", timeline_index=10),
                    event_id="evt_1",
                    from_value="yard",
                    to_value="crypt",
                    trigger="heard a bell",
                    emotional_tag="fear",
                )
            ),
        )
        self.assertEqual(factory.connections[0].commits, 1)

    def test_goal_stack_latest_at_or_before_maps_goals_from_json(self) -> None:
        factory = FakeConnectionFactory(
            [
                {
                    "one": {
                        "id": 1,
                        "character_id": "arya",
                        "tick": "t2",
                        "timeline_index": 20,
                        "event_sequence": 1,
                        "goals": [
                            {
                                "priority": 1,
                                "goal": "escape",
                                "motivation": "survival",
                                "obstacle": "guards",
                                "time_horizon": "immediate",
                                "emotional_charge": "urgent",
                                "abandon_condition": "caught",
                            }
                        ],
                        "actively_avoiding": "the courtyard",
                        "most_uncertain_relationship": "sansa",
                    }
                }
            ]
        )
        repo = PostgresGoalStackRepository(factory)

        snapshot = repo.latest_at_or_before("arya", 20)

        self.assertIsNotNone(snapshot)
        self.assertEqual(snapshot.goals[0].goal, "escape")
        self.assertEqual(snapshot.actively_avoiding, "the courtyard")
        self.assertIn("ORDER BY timeline_index DESC", factory.executed[0][0])

    def test_goal_stack_append_uses_idempotency_key(self) -> None:
        factory = FakeConnectionFactory(
            [
                {
                    "one": {
                        "id": 3,
                        "character_id": "arya",
                        "tick": "t2",
                        "timeline_index": 20,
                        "event_sequence": 0,
                        "goals": [],
                        "actively_avoiding": None,
                        "most_uncertain_relationship": None,
                    }
                }
            ]
        )
        repo = PostgresGoalStackRepository(factory)
        snapshot = GoalStackSnapshot(
            character_id="arya",
            replay_key=ReplayKey(tick="t2", timeline_index=20),
            goals=[],
        )

        repo.append(snapshot)

        self.assertIn("ON CONFLICT (idempotency_key) DO UPDATE", factory.executed[0][0])
        self.assertEqual(factory.executed[0][1][0], goal_stack_idempotency_key(snapshot))

    def test_memory_list_for_character_orders_results_and_builds_models(self) -> None:
        factory = FakeConnectionFactory(
            [
                {
                    "all": [
                        {
                            "character_id": "arya",
                            "tick": "t1",
                            "timeline_index": 10,
                            "event_sequence": 0,
                            "event_id": "evt_1",
                            "participants": ["arya"],
                            "location": "yard",
                            "summary": "She hid in the yard.",
                            "emotional_tag": "fear",
                            "salience": 0.4,
                            "pinned": False,
                            "compressed": False,
                        },
                        {
                            "character_id": "arya",
                            "tick": "t2",
                            "timeline_index": 20,
                            "event_sequence": 0,
                            "event_id": "evt_2",
                            "participants": ["arya", "sansa"],
                            "location": "crypt",
                            "summary": "She found a safer path.",
                            "emotional_tag": "focus",
                            "salience": 0.6,
                            "pinned": True,
                            "compressed": False,
                        },
                    ]
                }
            ]
        )
        repo = PostgresEpisodicMemoryRepository(factory)

        memories = repo.list_for_character("arya", timeline_index=20)

        self.assertEqual([memory.event_id for memory in memories], ["evt_1", "evt_2"])
        self.assertTrue(memories[1].pinned)
        self.assertIn("timeline_index <= %s", factory.executed[0][0])

    def test_memory_search_semantic_for_character_uses_pgvector_ordering(self) -> None:
        factory = FakeConnectionFactory(
            [
                {
                    "all": [
                        {
                            "character_id": "arya",
                            "tick": "t2",
                            "timeline_index": 20,
                            "event_sequence": 0,
                            "event_id": "evt_2",
                            "participants": ["arya", "sansa"],
                            "location": "yard",
                            "summary": "She found the hidden letter.",
                            "emotional_tag": "focus",
                            "salience": 0.7,
                            "pinned": False,
                            "compressed": False,
                            "embedding": [0.2, 0.3],
                            "semantic_score": 0.88,
                        }
                    ]
                }
            ]
        )
        repo = PostgresEpisodicMemoryRepository(factory)

        results = repo.search_semantic_for_character(
            "arya",
            query_embedding=[0.2, 0.3],
            limit=5,
            timeline_index=20,
        )

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].event_id, "evt_2")
        self.assertAlmostEqual(results[0].semantic_score or 0.0, 0.88)
        self.assertIn("embedding <=> %s::vector", factory.executed[0][0])
        self.assertIn("ORDER BY embedding <=> %s::vector ASC", factory.executed[0][0])

    def test_entity_representation_search_for_agent_uses_entity_embedding(self) -> None:
        factory = FakeConnectionFactory(
            [
                {
                    "all": [
                        {
                            "id": 1,
                            "entity_id": "ent_gate",
                            "agent_id": "arya",
                            "meaning": "the only exit",
                            "emotional_charge": "fear",
                            "goal_relevance": "reach it unseen",
                            "misunderstanding": "",
                            "confidence": "EXPLICIT",
                            "name": "The Gate",
                            "type": "place",
                            "narrative_role": "constraint",
                            "objective_facts": ["north wall"],
                            "embedding": [0.1, 0.2],
                        }
                    ]
                }
            ]
        )
        repo = PostgresEntityRepresentationRepository(factory)

        results = repo.search_for_agent(
            "arya",
            query_embedding=[0.1, 0.2],
            limit=3,
        )

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].entity_id, "ent_gate")
        self.assertIn("JOIN entity e ON e.id = er.entity_id", factory.executed[0][0])
        self.assertIn("e.embedding <=> %s::vector ASC", factory.executed[0][0])

    def test_state_change_list_for_character_reads_full_character_history(self) -> None:
        factory = FakeConnectionFactory(
            [
                {
                    "all": [
                        {
                            "character_id": "arya",
                            "dimension": "location",
                            "tick": "t1",
                            "timeline_index": 10,
                            "event_sequence": 0,
                            "event_id": "evt_1",
                            "from_value": '"yard"',
                            "to_value": '"crypt"',
                            "trigger": "bell",
                            "emotional_tag": "fear",
                            "pinned": False,
                        },
                        {
                            "character_id": "arya",
                            "dimension": "emotional_state",
                            "tick": "t1",
                            "timeline_index": 10,
                            "event_sequence": 1,
                            "event_id": "evt_1",
                            "from_value": '"fear"',
                            "to_value": '"resolve"',
                            "trigger": "bell",
                            "emotional_tag": "resolve",
                            "pinned": False,
                        },
                    ]
                }
            ]
        )
        repo = PostgresStateChangeLogRepository(factory)

        entries = repo.list_for_character("arya", 10)

        self.assertEqual([entry.dimension for entry in entries], ["location", "emotional_state"])
        self.assertIn("WHERE character_id = %s", factory.executed[0][0])

    def test_world_snapshot_append_uses_idempotent_upsert(self) -> None:
        factory = FakeConnectionFactory(
            [
                {
                    "one": {
                        "id": 5,
                        "tick": "t4",
                        "timeline_index": 40,
                        "event_sequence": 0,
                        "agent_locations": {"arya": "gate"},
                        "narrative_arc": {
                            "current_phase": "crisis",
                            "tension_level": 0.8,
                            "unresolved_threads": ["evt_world"],
                            "approaching_climax": True,
                        },
                        "unresolved_threads": ["evt_world"],
                        "next_tick_size_minutes": 30,
                    }
                }
            ]
        )
        repo = PostgresWorldSnapshotRepository(factory)
        snapshot = WorldSnapshot(
            replay_key=ReplayKey(tick="t4", timeline_index=40),
            agent_locations={"arya": "gate"},
            narrative_arc=NarrativeArcState(
                current_phase="crisis",
                tension_level=0.8,
                unresolved_threads=["evt_world"],
                approaching_climax=True,
            ),
            unresolved_threads=["evt_world"],
            next_tick_size_minutes=30,
        )

        record = repo.append(snapshot)

        self.assertEqual(record.timeline_index, 40)
        self.assertIn("ON CONFLICT (idempotency_key) DO UPDATE", factory.executed[0][0])
        self.assertEqual(factory.executed[0][1][0], world_snapshot_idempotency_key(snapshot))

    def test_event_log_append_uses_upsert_on_event_id(self) -> None:
        factory = FakeConnectionFactory(
            [
                {
                    "one": {
                        "id": 11,
                        "event_id": "evt_world",
                        "tick": "t3",
                        "timeline_index": 30,
                        "seed_type": "world",
                        "location": "gate",
                        "participants": ["arya"],
                        "description": "The gate closes.",
                        "salience": 0.8,
                        "outcome_summary": "Pressure spikes.",
                        "resolution_mode": "background",
                    }
                }
            ]
        )
        repo = PostgresEventLogRepository(factory)

        record = repo.append(
            event_id="evt_world",
            replay_key=ReplayKey(tick="t3", timeline_index=30),
            seed_type="world",
            location="gate",
            participants=["arya"],
            description="The gate closes.",
            salience=0.8,
            outcome_summary="Pressure spikes.",
            resolution_mode="background",
        )

        self.assertEqual(record.event_id, "evt_world")
        self.assertIn("ON CONFLICT (event_id) DO UPDATE", factory.executed[0][0])

    def test_event_log_list_until_returns_ordered_records(self) -> None:
        factory = FakeConnectionFactory(
            [
                {
                    "all": [
                        {
                            "id": 4,
                            "event_id": "evt_1",
                            "tick": "t1",
                            "timeline_index": 10,
                            "seed_type": "solo",
                            "location": "yard",
                            "participants": ["arya"],
                            "description": "She hides.",
                            "salience": 0.3,
                            "outcome_summary": "No one notices.",
                            "resolution_mode": "background",
                        },
                        {
                            "id": 5,
                            "event_id": "evt_2",
                            "tick": "t2",
                            "timeline_index": 20,
                            "seed_type": "world",
                            "location": "gate",
                            "participants": ["arya"],
                            "description": "The bells ring.",
                            "salience": 0.7,
                            "outcome_summary": "Urgency rises.",
                            "resolution_mode": "foreground",
                        },
                    ]
                }
            ]
        )
        repo = PostgresEventLogRepository(factory)

        records = repo.list_until(20)

        self.assertEqual([record.event_id for record in records], ["evt_1", "evt_2"])
        self.assertIn("WHERE timeline_index <= %s", factory.executed[0][0])


if __name__ == "__main__":
    unittest.main()
