import json
import unittest

from dreamdive.config import LLMProfileSettings
from dreamdive.db.queries import (
    EntityRepresentationRepository,
    EpisodicMemoryRepository,
    EventLogRepository,
    GoalStackRepository,
    RelationshipRepository,
    StateChangeLogRepository,
    WorldSnapshotRepository,
)
from dreamdive.db.session import InMemoryStore
from dreamdive.llm.client import StructuredLLMClient
from dreamdive.schemas import (
    CharacterIdentity,
    CharacterSnapshot,
    EpisodicMemory,
    Goal,
    NarrativeArcState,
    ReplayKey,
    RelationshipLogEntry,
    SnapshotInference,
    SubjectiveEntityRepresentation,
    TrajectoryProjectionPayload,
)
from dreamdive.simulation.event_simulator import EventSimulator
from dreamdive.simulation.goal_collision import GoalCollisionDetector
from dreamdive.simulation.seed_detector import SeedDetector
from dreamdive.simulation.seeds import SimulationSeed
from dreamdive.simulation.state_updater import EventStateUpdater
from dreamdive.simulation.tick_runner import AgentRuntime, SimulationTickRunner
from dreamdive.simulation.trajectory import TrajectoryProjector
from dreamdive.simulation.world_events import ScheduledWorldEvent, WorldEventScheduler
from dreamdive.simulation.world_manager import WorldManager


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


def make_snapshot():
    return CharacterSnapshot(
        identity=CharacterIdentity(
            character_id="arya",
            name="Arya Stark",
            fears=["being captured"],
            values=["family"],
            desires=["survive"],
        ),
        replay_key=ReplayKey(tick="chapter_02", timeline_index=2),
        current_state={"location": "courtyard"},
        goals=[
            Goal(
                priority=1,
                goal="stay hidden",
                motivation="survival",
                obstacle="guards nearby",
                time_horizon="immediate",
                emotional_charge="fear",
                abandon_condition="safe shelter found",
            )
        ],
        working_memory=[],
        relationships=[],
        inferred_state=SnapshotInference.model_validate(
            {
                "emotional_state": {
                    "dominant": "fear",
                    "secondary": ["resolve"],
                    "confidence": 0.4,
                },
                "immediate_tension": "",
                "unspoken_subtext": "",
                "physical_state": {
                    "energy": 0.7,
                    "injuries_or_constraints": "",
                    "location": "courtyard",
                    "current_activity": "hiding",
                },
                "knowledge_state": {
                    "new_knowledge": [],
                    "active_misbeliefs": [],
                },
            }
        ),
    )


class FailingEventSimulator:
    def simulate_background(self, **_kwargs):
        raise RuntimeError("synthetic scene failure")


class StaticTrajectoryProjector:
    def __init__(
        self,
        projections,
        *,
        fail_batch=False,
        fail_individual_ids=None,
    ):
        self.projections = projections
        self.fail_batch = fail_batch
        self.fail_individual_ids = set(fail_individual_ids or [])

    def project(self, *, snapshot, **_kwargs):
        character_id = snapshot.identity.character_id
        if character_id in self.fail_individual_ids:
            raise RuntimeError(f"synthetic projection failure for {character_id}")
        return self.projections[character_id]

    def project_many(self, *, snapshots, **_kwargs):
        if self.fail_batch:
            raise RuntimeError("synthetic batch projection failure")
        return {
            snapshot.identity.character_id: self.projections[snapshot.identity.character_id]
            for snapshot in snapshots
            if snapshot.identity.character_id in self.projections
        }


class FailingGoalCollisionDetector:
    def detect_goal_collisions(self, **_kwargs):
        raise RuntimeError("synthetic goal collision failure")


class AppendRecorder:
    def __init__(self, label, inner, calls):
        self.label = label
        self.inner = inner
        self.calls = calls

    def append(self, *args, **kwargs):
        self.calls.append(self.label)
        return self.inner.append(*args, **kwargs)

    def __getattr__(self, name):
        return getattr(self.inner, name)


class FlakyAppendProxy:
    def __init__(self, inner, failures_before_success):
        self.inner = inner
        self.failures_before_success = failures_before_success
        self.attempts = 0

    def append(self, *args, **kwargs):
        self.attempts += 1
        if self.attempts <= self.failures_before_success:
            raise RuntimeError("temporary write failure")
        return self.inner.append(*args, **kwargs)

    def __getattr__(self, name):
        return getattr(self.inner, name)


class TrackingMemoryRepository(EpisodicMemoryRepository):
    def __init__(self, store):
        super().__init__(store)
        self.search_calls = 0
        self.pinned_calls = 0

    def search_semantic_for_character(self, *args, **kwargs):
        self.search_calls += 1
        return super().search_semantic_for_character(*args, **kwargs)

    def list_pinned_for_character(self, *args, **kwargs):
        self.pinned_calls += 1
        return super().list_pinned_for_character(*args, **kwargs)


class TrackingEntityRepository(EntityRepresentationRepository):
    def __init__(self, store):
        super().__init__(store)
        self.search_calls = 0

    def search_for_agent(self, *args, **kwargs):
        self.search_calls += 1
        return super().search_for_agent(*args, **kwargs)


class TickRunnerTests(unittest.TestCase):
    @staticmethod
    def _make_projection(action: str) -> TrajectoryProjectionPayload:
        return TrajectoryProjectionPayload.model_validate(
            {
                "primary_intention": "stay hidden",
                "motivation": "survival",
                "immediate_next_action": action,
                "contingencies": [],
                "greatest_fear_this_horizon": "being seen",
                "abandon_condition": "safe path opens",
                "held_back_impulse": "run immediately",
                "projection_horizon": "4 ticks (~120 minutes)",
            }
        )

    def test_tick_runner_projects_flagged_agents_and_persists_outputs(self) -> None:
        responses = [
            json.dumps(
                {
                    "primary_intention": "stay hidden",
                    "motivation": "survival",
                    "immediate_next_action": "wait behind the crates",
                    "contingencies": [],
                    "greatest_fear_this_horizon": "being seen",
                    "abandon_condition": "safe path opens",
                    "held_back_impulse": "run immediately",
                    "projection_horizon": "4 ticks (~1920 minutes)",
                }
            ),
            json.dumps(
                {
                    "goal_tensions": [],
                    "solo_seeds": [],
                    "world_events": [],
                }
            ),
            json.dumps(
                {
                    "narrative_summary": "Arya stayed still and learned the guard pattern.",
                    "outcomes": [
                        {
                            "agent_id": "arya",
                            "goal_status": "advanced",
                            "new_knowledge": "The guard circles every five minutes.",
                            "emotional_delta": "fear hardening into patience",
                        }
                    ],
                    "relationship_deltas": [],
                    "unexpected": "",
                }
            ),
            json.dumps(
                {
                    "emotional_delta": {
                        "dominant_now": "focused caution",
                        "underneath": "fear",
                        "shift_reason": "Observation created a tactical opening",
                    },
                    "goal_stack_update": {
                        "top_goal_status": "advanced",
                        "top_goal_still_priority": True,
                        "new_goal": None,
                        "resolved_goal": None,
                    },
                    "relationship_updates": [],
                    "needs_reprojection": False,
                    "reprojection_reason": "",
                }
            ),
        ]
        client = build_client(responses)
        store = InMemoryStore()
        runner = SimulationTickRunner(
            world_manager=WorldManager(),
            seed_detector=SeedDetector(GoalCollisionDetector(client)),
            trajectory_projector=TrajectoryProjector(client),
            event_simulator=EventSimulator(client),
            state_updater=EventStateUpdater(client),
            state_repo=StateChangeLogRepository(store),
            goal_repo=GoalStackRepository(store),
            relationship_repo=RelationshipRepository(store),
            memory_repo=EpisodicMemoryRepository(store),
            world_snapshot_repo=WorldSnapshotRepository(store),
            event_log_repo=EventLogRepository(store),
        )
        runtime = AgentRuntime(snapshot=make_snapshot(), needs_reprojection=True)
        world_seed = SimulationSeed(
            seed_id="world_001",
            seed_type="world",
            participants=["arya"],
            location="courtyard",
            description="A guard patrol shifts direction.",
            urgency=0.1,
            conflict=0.1,
            emotional_charge=0.1,
            novelty=0.1,
        )
        arc_state = NarrativeArcState(
            current_phase="rising_action",
            tension_level=0.1,
            unresolved_threads=["escape"],
            approaching_climax=False,
        )

        result = runner.run_tick(
            current_tick_label="day_001_morning",
            current_timeline_index=100,
            agent_runtimes=[runtime],
            arc_state=arc_state,
            world_seeds=[world_seed],
        )

        self.assertEqual(len(store.state_change_log), 2)
        self.assertEqual(len(store.goal_stack), 1)
        self.assertEqual(len(store.episodic_memory), 1)
        self.assertEqual(len(store.world_snapshot), 1)
        self.assertEqual(len(store.event_log), 1)
        self.assertEqual(result.location_threads[0]["thread_id"], "courtyard")
        self.assertEqual(result.agent_runtimes["arya"].trajectory.immediate_next_action, "wait behind the crates")
        self.assertEqual(
            result.agent_runtimes["arya"].snapshot.current_state["emotional_state"],
            "focused caution",
        )
        self.assertFalse(result.agent_runtimes["arya"].needs_reprojection)
        self.assertEqual(result.ranked_seeds[0].seed_type, "world")
        self.assertIsInstance(result.scheduled_jobs, list)
        self.assertIn("arya", result.active_agent_scores)
        self.assertEqual(result.event_failures, [])
        self.assertTrue(all(not prompt.stream for prompt in client.transport.prompts))

    def test_tick_runner_uses_repository_semantic_memory_candidates_for_context(self) -> None:
        responses = [
            json.dumps(
                {
                    "primary_intention": "stay hidden",
                    "motivation": "survival",
                    "immediate_next_action": "wait behind the crates",
                    "contingencies": [],
                    "greatest_fear_this_horizon": "being seen",
                    "abandon_condition": "safe path opens",
                    "held_back_impulse": "run immediately",
                    "projection_horizon": "4 ticks (~120 minutes)",
                }
            ),
            json.dumps({"goal_tensions": [], "solo_seeds": [], "world_events": []}),
            json.dumps(
                {
                    "narrative_summary": "Arya stayed still and remembered where the letter was hidden.",
                    "outcomes": [
                        {
                            "agent_id": "arya",
                            "goal_status": "advanced",
                            "new_knowledge": "The letter is still in the wall.",
                            "emotional_delta": "fear hardening into patience",
                        }
                    ],
                    "relationship_deltas": [],
                    "unexpected": "",
                }
            ),
            json.dumps(
                {
                    "emotional_delta": {
                        "dominant_now": "focused caution",
                        "underneath": "fear",
                        "shift_reason": "Observation created a tactical opening",
                    },
                    "goal_stack_update": {
                        "top_goal_status": "advanced",
                        "top_goal_still_priority": True,
                        "new_goal": None,
                        "resolved_goal": None,
                    },
                    "relationship_updates": [],
                    "needs_reprojection": False,
                    "reprojection_reason": "",
                }
            ),
        ]
        client = build_client(responses)
        store = InMemoryStore()
        memory_repo = TrackingMemoryRepository(store)
        runner = SimulationTickRunner(
            world_manager=WorldManager(),
            seed_detector=SeedDetector(GoalCollisionDetector(client)),
            trajectory_projector=TrajectoryProjector(client),
            event_simulator=EventSimulator(client),
            state_updater=EventStateUpdater(client),
            state_repo=StateChangeLogRepository(store),
            goal_repo=GoalStackRepository(store),
            relationship_repo=RelationshipRepository(store),
            memory_repo=memory_repo,
            world_snapshot_repo=WorldSnapshotRepository(store),
            event_log_repo=EventLogRepository(store),
        )
        memory_repo.append(
            EpisodicMemory(
                character_id="arya",
                replay_key=ReplayKey(tick="chapter_01", timeline_index=50),
                event_id="evt_memory",
                participants=["arya", "sansa"],
                location="courtyard",
                summary="Arya remembers where Sansa hid the letter in the courtyard wall.",
                emotional_tag="fear",
                salience=0.7,
                pinned=True,
            )
        )

        runner.run_tick(
            current_tick_label="day_001_morning",
            current_timeline_index=100,
            agent_runtimes=[AgentRuntime(snapshot=make_snapshot(), needs_reprojection=True)],
            arc_state=NarrativeArcState(
                current_phase="rising_action",
                tension_level=0.1,
                unresolved_threads=["escape"],
                approaching_climax=False,
            ),
            world_seeds=[
                SimulationSeed(
                    seed_id="world_001",
                    seed_type="world",
                    participants=["arya"],
                    location="courtyard",
                    description="A guard patrol shifts direction.",
                    urgency=0.1,
                    conflict=0.1,
                    emotional_charge=0.1,
                    novelty=0.1,
                )
            ],
        )

        self.assertEqual(memory_repo.search_calls, 1)
        self.assertEqual(memory_repo.pinned_calls, 1)

    def test_tick_runner_uses_repository_entity_candidates_for_context(self) -> None:
        responses = [
            json.dumps(
                {
                    "primary_intention": "stay hidden",
                    "motivation": "survival",
                    "immediate_next_action": "wait behind the crates",
                    "contingencies": [],
                    "greatest_fear_this_horizon": "being seen",
                    "abandon_condition": "safe path opens",
                    "held_back_impulse": "run immediately",
                    "projection_horizon": "4 ticks (~120 minutes)",
                }
            ),
            json.dumps({"goal_tensions": [], "solo_seeds": [], "world_events": []}),
            json.dumps(
                {
                    "narrative_summary": "Arya studies the gate and stays hidden.",
                    "outcomes": [
                        {
                            "agent_id": "arya",
                            "goal_status": "advanced",
                            "new_knowledge": "The gate is still the best route.",
                            "emotional_delta": "fear hardening into patience",
                        }
                    ],
                    "relationship_deltas": [],
                    "unexpected": "",
                }
            ),
            json.dumps(
                {
                    "emotional_delta": {
                        "dominant_now": "focused caution",
                        "underneath": "fear",
                        "shift_reason": "Observation created a tactical opening",
                    },
                    "goal_stack_update": {
                        "top_goal_status": "advanced",
                        "top_goal_still_priority": True,
                        "new_goal": None,
                        "resolved_goal": None,
                    },
                    "relationship_updates": [],
                    "needs_reprojection": False,
                    "reprojection_reason": "",
                }
            ),
        ]
        client = build_client(responses)
        store = InMemoryStore()
        entity_repo = TrackingEntityRepository(store)
        entity_repo.append(
            SubjectiveEntityRepresentation(
                agent_id="arya",
                entity_id="ent_gate",
                name="The Gate",
                type="place",
                narrative_role="constraint",
                objective_facts=["north wall"],
                belief="the only exit",
                emotional_charge="fear",
                goal_relevance="reach it unseen",
                misunderstanding="",
                confidence="EXPLICIT",
            )
        )
        runner = SimulationTickRunner(
            world_manager=WorldManager(),
            seed_detector=SeedDetector(GoalCollisionDetector(client)),
            trajectory_projector=TrajectoryProjector(client),
            event_simulator=EventSimulator(client),
            state_updater=EventStateUpdater(client),
            state_repo=StateChangeLogRepository(store),
            goal_repo=GoalStackRepository(store),
            relationship_repo=RelationshipRepository(store),
            memory_repo=EpisodicMemoryRepository(store),
            entity_repo=entity_repo,
            world_snapshot_repo=WorldSnapshotRepository(store),
            event_log_repo=EventLogRepository(store),
        )

        result = runner.run_tick(
            current_tick_label="day_001_morning",
            current_timeline_index=100,
            agent_runtimes=[AgentRuntime(snapshot=make_snapshot(), needs_reprojection=True)],
            arc_state=NarrativeArcState(
                current_phase="rising_action",
                tension_level=0.1,
                unresolved_threads=["escape"],
                approaching_climax=False,
            ),
            world_seeds=[
                SimulationSeed(
                    seed_id="world_001",
                    seed_type="world",
                    participants=["arya"],
                    location="courtyard",
                    description="A guard patrol shifts direction.",
                    urgency=0.1,
                    conflict=0.1,
                    emotional_charge=0.1,
                    novelty=0.1,
                )
            ],
        )

        self.assertEqual(entity_repo.search_calls, 1)
        self.assertEqual(result.agent_runtimes["arya"].world_entities[0]["entity_id"], "ent_gate")

    def test_tick_runner_consumes_scheduled_world_events(self) -> None:
        responses = [
            json.dumps(
                {
                    "primary_intention": "stay hidden",
                    "motivation": "survival",
                    "immediate_next_action": "wait behind the crates",
                    "contingencies": [],
                    "greatest_fear_this_horizon": "being seen",
                    "abandon_condition": "safe path opens",
                    "held_back_impulse": "run immediately",
                    "projection_horizon": "4 ticks (~1920 minutes)",
                }
            ),
            json.dumps({"goal_tensions": [], "solo_seeds": [], "world_events": []}),
            json.dumps(
                {
                    "narrative_summary": "Word spread that the guard captain had changed the watch.",
                    "outcomes": [
                        {
                            "agent_id": "arya",
                            "goal_status": "advanced",
                            "new_knowledge": "The guard captain changed the watch.",
                            "emotional_delta": "fear sharpened into calculation",
                        }
                    ],
                    "relationship_deltas": [],
                    "unexpected": "",
                }
            ),
            json.dumps(
                {
                    "emotional_delta": {
                        "dominant_now": "sharp focus",
                        "underneath": "fear",
                        "shift_reason": "New information changed the tactical picture",
                    },
                    "goal_stack_update": {
                        "top_goal_status": "advanced",
                        "top_goal_still_priority": True,
                        "new_goal": None,
                        "resolved_goal": None,
                    },
                    "relationship_updates": [],
                    "needs_reprojection": True,
                    "reprojection_reason": "Major new information received",
                }
            ),
        ]
        client = build_client(responses)
        store = InMemoryStore()
        scheduler = WorldEventScheduler(
            [
                ScheduledWorldEvent(
                    event_id="evt_watch_change",
                    trigger_timeline_index=220,
                    description="The guard captain changes the watch pattern.",
                    affected_agents=["arya"],
                    urgency="low",
                    location="courtyard",
                )
            ]
        )
        runner = SimulationTickRunner(
            world_manager=WorldManager(),
            seed_detector=SeedDetector(GoalCollisionDetector(client)),
            trajectory_projector=TrajectoryProjector(client),
            event_simulator=EventSimulator(client),
            state_updater=EventStateUpdater(client),
            state_repo=StateChangeLogRepository(store),
            goal_repo=GoalStackRepository(store),
            relationship_repo=RelationshipRepository(store),
            memory_repo=EpisodicMemoryRepository(store),
            world_snapshot_repo=WorldSnapshotRepository(store),
            event_log_repo=EventLogRepository(store),
            world_event_scheduler=scheduler,
        )

        result = runner.run_tick(
            current_tick_label="day_001_noon",
            current_timeline_index=100,
            agent_runtimes=[AgentRuntime(snapshot=make_snapshot(), needs_reprojection=True)],
            arc_state=NarrativeArcState(
                current_phase="rising_action",
                tension_level=0.2,
                unresolved_threads=["escape"],
                approaching_climax=False,
            ),
        )

        self.assertEqual(len(store.event_log), 1)
        self.assertEqual(result.tick_minutes, 120)
        self.assertEqual(store.event_log[0].event_id, "evt_220_001")
        self.assertEqual(result.ranked_seeds[0].description, "The guard captain changes the watch pattern.")
        self.assertTrue(result.agent_runtimes["arya"].needs_reprojection)
        self.assertEqual(scheduler.fired_event_ids, ["evt_watch_change"])

    def test_tick_runner_only_projects_agents_above_activation_threshold(self) -> None:
        responses = [
            json.dumps(
                {
                    "primary_intention": "stay hidden",
                    "motivation": "survival",
                    "immediate_next_action": "wait behind the crates",
                    "contingencies": [],
                    "greatest_fear_this_horizon": "being seen",
                    "abandon_condition": "safe path opens",
                    "held_back_impulse": "run immediately",
                    "projection_horizon": "4 ticks (~1920 minutes)",
                }
            ),
            json.dumps({"goal_tensions": [], "solo_seeds": [], "world_events": []}),
            json.dumps(
                {
                    "narrative_summary": "Arya stayed still and learned the guard pattern.",
                    "outcomes": [
                        {
                            "agent_id": "arya",
                            "goal_status": "advanced",
                            "new_knowledge": "The guard circles every five minutes.",
                            "emotional_delta": "fear hardening into patience",
                        }
                    ],
                    "relationship_deltas": [],
                    "unexpected": "",
                }
            ),
            json.dumps(
                {
                    "emotional_delta": {
                        "dominant_now": "focused caution",
                        "underneath": "fear",
                        "shift_reason": "Observation created a tactical opening",
                    },
                    "goal_stack_update": {
                        "top_goal_status": "advanced",
                        "top_goal_still_priority": True,
                        "new_goal": None,
                        "resolved_goal": None,
                    },
                    "relationship_updates": [],
                    "needs_reprojection": False,
                    "reprojection_reason": "",
                }
            ),
        ]
        client = build_client(responses)
        store = InMemoryStore()
        runner = SimulationTickRunner(
            world_manager=WorldManager(activation_threshold=0.45),
            seed_detector=SeedDetector(GoalCollisionDetector(client)),
            trajectory_projector=TrajectoryProjector(client),
            event_simulator=EventSimulator(client),
            state_updater=EventStateUpdater(client),
            state_repo=StateChangeLogRepository(store),
            goal_repo=GoalStackRepository(store),
            relationship_repo=RelationshipRepository(store),
            memory_repo=EpisodicMemoryRepository(store),
            world_snapshot_repo=WorldSnapshotRepository(store),
            event_log_repo=EventLogRepository(store),
        )
        inactive_snapshot = CharacterSnapshot(
            identity=CharacterIdentity(character_id="hotpie", name="Hot Pie"),
            replay_key=ReplayKey(tick="chapter_02", timeline_index=2),
            current_state={"location": "kitchen"},
            goals=[],
            working_memory=[],
            relationships=[],
            inferred_state=None,
        )

        result = runner.run_tick(
            current_tick_label="day_001_morning",
            current_timeline_index=100,
            agent_runtimes=[
                AgentRuntime(snapshot=make_snapshot(), needs_reprojection=True),
                AgentRuntime(snapshot=inactive_snapshot, needs_reprojection=True),
            ],
            arc_state=NarrativeArcState(
                current_phase="rising_action",
                tension_level=0.1,
                unresolved_threads=["escape"],
                approaching_climax=False,
            ),
            world_seeds=[
                SimulationSeed(
                    seed_id="world_001",
                    seed_type="world",
                    participants=["arya"],
                    location="courtyard",
                    description="A guard patrol shifts direction.",
                    urgency=0.1,
                    conflict=0.1,
                    emotional_charge=0.1,
                    novelty=0.1,
                )
            ],
            language_guidance="- Primary language: English\n- Dialogue style: terse and tactical",
        )

        self.assertEqual(client.transport.calls, 4)
        self.assertIn("arya", result.active_agent_scores)
        self.assertNotIn("hotpie", result.active_agent_scores)
        self.assertIsNone(result.agent_runtimes["hotpie"].trajectory)

    def test_tick_runner_batches_low_priority_trajectory_projection(self) -> None:
        responses = [
            json.dumps(
                {
                    "projections": {
                        "arya": {
                            "primary_intention": "stay hidden",
                            "motivation": "survival",
                            "immediate_next_action": "wait behind the crates",
                            "contingencies": [],
                            "greatest_fear_this_horizon": "being seen",
                            "abandon_condition": "safe path opens",
                            "held_back_impulse": "run immediately",
                            "projection_horizon": "4 ticks (~1920 minutes)",
                        },
                        "gendry": {
                            "primary_intention": "find a way out",
                            "motivation": "survival",
                            "immediate_next_action": "watch the gate",
                            "contingencies": [],
                            "greatest_fear_this_horizon": "meeting guards",
                            "abandon_condition": "path closes",
                            "held_back_impulse": "bolt now",
                            "projection_horizon": "4 ticks (~1920 minutes)",
                        },
                    }
                }
            ),
            json.dumps({"goal_tensions": [], "solo_seeds": [], "world_events": []}),
            json.dumps(
                {
                    "narrative_summary": "Arya stayed still and learned the guard pattern.",
                    "outcomes": [
                        {
                            "agent_id": "arya",
                            "goal_status": "advanced",
                            "new_knowledge": "The guard circles every five minutes.",
                            "emotional_delta": "fear hardening into patience",
                        }
                    ],
                    "relationship_deltas": [],
                    "unexpected": "",
                }
            ),
            json.dumps(
                {
                    "emotional_delta": {
                        "dominant_now": "focused caution",
                        "underneath": "fear",
                        "shift_reason": "Observation created a tactical opening",
                    },
                    "goal_stack_update": {
                        "top_goal_status": "advanced",
                        "top_goal_still_priority": True,
                        "new_goal": None,
                        "resolved_goal": None,
                    },
                    "relationship_updates": [],
                    "needs_reprojection": False,
                    "reprojection_reason": "",
                }
            ),
        ]
        client = build_client(responses)
        store = InMemoryStore()
        runner = SimulationTickRunner(
            world_manager=WorldManager(
                activation_threshold=0.45,
                batched_projection_threshold=0.7,
            ),
            seed_detector=SeedDetector(GoalCollisionDetector(client)),
            trajectory_projector=TrajectoryProjector(client),
            event_simulator=EventSimulator(client),
            state_updater=EventStateUpdater(client),
            state_repo=StateChangeLogRepository(store),
            goal_repo=GoalStackRepository(store),
            relationship_repo=RelationshipRepository(store),
            memory_repo=EpisodicMemoryRepository(store),
            world_snapshot_repo=WorldSnapshotRepository(store),
            event_log_repo=EventLogRepository(store),
        )
        gendry_snapshot = CharacterSnapshot(
            identity=CharacterIdentity(character_id="gendry", name="Gendry"),
            replay_key=ReplayKey(tick="chapter_02", timeline_index=2),
            current_state={"location": "smithy"},
            goals=[
                Goal(
                    priority=1,
                    goal="find a way out",
                    motivation="survival",
                    obstacle="guards",
                    time_horizon="immediate",
                    emotional_charge="worry",
                    abandon_condition="safe route appears",
                )
            ],
            working_memory=[],
            relationships=[],
            inferred_state=SnapshotInference.model_validate(
                {
                    "emotional_state": {
                        "dominant": "wary",
                        "secondary": [],
                        "confidence": 0.3,
                    },
                    "immediate_tension": "",
                    "unspoken_subtext": "",
                    "physical_state": {
                        "energy": 0.7,
                        "injuries_or_constraints": "",
                        "location": "smithy",
                        "current_activity": "waiting",
                    },
                    "knowledge_state": {
                        "new_knowledge": [],
                        "active_misbeliefs": [],
                    },
                }
            ),
        )

        result = runner.run_tick(
            current_tick_label="day_001_morning",
            current_timeline_index=100,
            agent_runtimes=[
                AgentRuntime(snapshot=make_snapshot(), needs_reprojection=True),
                AgentRuntime(snapshot=gendry_snapshot, needs_reprojection=True),
            ],
            arc_state=NarrativeArcState(
                current_phase="rising_action",
                tension_level=0.1,
                unresolved_threads=["escape"],
                approaching_climax=False,
            ),
            world_seeds=[
                SimulationSeed(
                    seed_id="world_001",
                    seed_type="world",
                    participants=["arya"],
                    location="courtyard",
                    description="A guard patrol shifts direction.",
                    urgency=0.1,
                    conflict=0.1,
                    emotional_charge=0.1,
                    novelty=0.1,
                )
            ],
        )

        self.assertEqual(client.transport.calls, 4)
        self.assertEqual(
            client.transport.prompts[0].metadata["prompt_name"],
            "p2_3_trajectory_projection_batched",
        )
        self.assertEqual(
            result.agent_runtimes["arya"].trajectory.immediate_next_action,
            "wait behind the crates",
        )
        self.assertEqual(
            result.agent_runtimes["gendry"].trajectory.immediate_next_action,
            "watch the gate",
        )

    def test_tick_runner_batches_large_high_priority_projection_sets(self) -> None:
        response_batch_one = {
            "projections": {
                f"char_{index:03d}": {
                    "primary_intention": "hold position",
                    "motivation": "survival",
                    "immediate_next_action": f"observe sector {index}",
                    "contingencies": [],
                    "greatest_fear_this_horizon": "losing control",
                    "abandon_condition": "a safer path appears",
                    "held_back_impulse": "run immediately",
                    "projection_horizon": "2 ticks (~120 minutes)",
                }
                for index in range(1, 6)
            }
        }
        response_batch_two = {
            "projections": {
                "char_006": {
                    "primary_intention": "hold position",
                    "motivation": "survival",
                    "immediate_next_action": "observe sector 6",
                    "contingencies": [],
                    "greatest_fear_this_horizon": "losing control",
                    "abandon_condition": "a safer path appears",
                    "held_back_impulse": "run immediately",
                    "projection_horizon": "2 ticks (~120 minutes)",
                }
            }
        }
        client = build_client([json.dumps(response_batch_one), json.dumps(response_batch_two)])
        store = InMemoryStore()
        runner = SimulationTickRunner(
            world_manager=WorldManager(
                activation_threshold=0.45,
                batched_projection_threshold=0.7,
            ),
            seed_detector=SeedDetector(FailingGoalCollisionDetector()),
            trajectory_projector=TrajectoryProjector(client),
            event_simulator=EventSimulator(client),
            state_updater=EventStateUpdater(client),
            state_repo=StateChangeLogRepository(store),
            goal_repo=GoalStackRepository(store),
            relationship_repo=RelationshipRepository(store),
            memory_repo=EpisodicMemoryRepository(store),
            world_snapshot_repo=WorldSnapshotRepository(store),
            event_log_repo=EventLogRepository(store),
        )

        runtimes = []
        for index in range(1, 7):
            snapshot = make_snapshot().model_copy(deep=True)
            snapshot.identity = snapshot.identity.model_copy(
                update={
                    "character_id": f"char_{index:03d}",
                    "name": f"Agent {index}",
                }
            )
            snapshot.current_state = {"location": f"zone_{index}"}
            snapshot.inferred_state = SnapshotInference.model_validate(
                {
                    "emotional_state": {
                        "dominant": "fear",
                        "secondary": ["resolve"],
                        "confidence": 0.9,
                    },
                    "immediate_tension": "Immediate danger is closing in.",
                    "unspoken_subtext": "They are close to panic.",
                    "physical_state": {
                        "energy": 0.7,
                        "injuries_or_constraints": "",
                        "location": f"zone_{index}",
                        "current_activity": "waiting",
                    },
                    "knowledge_state": {
                        "new_knowledge": [],
                        "active_misbeliefs": [],
                    },
                }
            )
            runtimes.append(AgentRuntime(snapshot=snapshot, needs_reprojection=True))

        progress_events = []

        result = runner.run_tick(
            current_tick_label="snapshot",
            current_timeline_index=0,
            agent_runtimes=runtimes,
            arc_state=NarrativeArcState(
                current_phase="setup",
                tension_level=0.1,
                unresolved_threads=[],
                approaching_climax=False,
            ),
            progress_callback=progress_events.append,
        )

        self.assertEqual(client.transport.calls, 2)
        self.assertTrue(
            all(runtime.trajectory is not None for runtime in result.agent_runtimes.values())
        )
        projection_prompts = [
            prompt.metadata.get("prompt_name")
            for prompt in client.transport.prompts
            if str(prompt.metadata.get("prompt_name", "")).startswith("p2_3_trajectory_projection")
        ]
        self.assertEqual(
            projection_prompts,
            ["p2_3_trajectory_projection_batched", "p2_3_trajectory_projection_batched"],
        )
        self.assertIn(
            "projecting high-priority agents 1-5/6",
            [str(event.get("message", "")) for event in progress_events],
        )

    def test_tick_runner_records_high_priority_projection_failure_and_continues(self) -> None:
        responses = [
            json.dumps(
                {
                    "narrative_summary": "Arya stayed still and learned the guard pattern.",
                    "outcomes": [
                        {
                            "agent_id": "arya",
                            "goal_status": "advanced",
                            "new_knowledge": "The guard circles every five minutes.",
                            "emotional_delta": "fear hardening into patience",
                        }
                    ],
                    "relationship_deltas": [],
                    "unexpected": "",
                }
            ),
            json.dumps(
                {
                    "emotional_delta": {
                        "dominant_now": "focused caution",
                        "underneath": "fear",
                        "shift_reason": "Observation created a tactical opening",
                    },
                    "goal_stack_update": {
                        "top_goal_status": "advanced",
                        "top_goal_still_priority": True,
                        "new_goal": None,
                        "resolved_goal": None,
                    },
                    "relationship_updates": [],
                    "needs_reprojection": False,
                    "reprojection_reason": "",
                }
            ),
        ]
        client = build_client(responses)
        store = InMemoryStore()
        runner = SimulationTickRunner(
            world_manager=WorldManager(batched_projection_threshold=0.6),
            seed_detector=SeedDetector(GoalCollisionDetector(client)),
            trajectory_projector=StaticTrajectoryProjector(
                {"arya": self._make_projection("wait behind the crates")},
                fail_individual_ids={"arya"},
            ),
            event_simulator=EventSimulator(client),
            state_updater=EventStateUpdater(client),
            state_repo=StateChangeLogRepository(store),
            goal_repo=GoalStackRepository(store),
            relationship_repo=RelationshipRepository(store),
            memory_repo=EpisodicMemoryRepository(store),
            world_snapshot_repo=WorldSnapshotRepository(store),
            event_log_repo=EventLogRepository(store),
        )

        result = runner.run_tick(
            current_tick_label="day_001_morning",
            current_timeline_index=100,
            agent_runtimes=[AgentRuntime(snapshot=make_snapshot(), needs_reprojection=True)],
            arc_state=NarrativeArcState(
                current_phase="rising_action",
                tension_level=0.1,
                unresolved_threads=["escape"],
                approaching_climax=False,
            ),
            world_seeds=[
                SimulationSeed(
                    seed_id="world_001",
                    seed_type="world",
                    participants=["arya"],
                    location="courtyard",
                    description="A guard patrol shifts direction.",
                    urgency=0.1,
                    conflict=0.1,
                    emotional_charge=0.1,
                    novelty=0.1,
                )
            ],
        )

        self.assertEqual(len(store.world_snapshot), 1)
        self.assertEqual(len(store.event_log), 1)
        self.assertIsNone(result.agent_runtimes["arya"].trajectory)
        self.assertTrue(
            any(
                failure.stage == "trajectory_projection" and failure.seed_id == "arya"
                for failure in result.event_failures
            )
        )
        self.assertEqual(client.transport.calls, 2)

    def test_tick_runner_falls_back_to_individual_projection_after_batch_failure(self) -> None:
        responses = [
            json.dumps({"goal_tensions": [], "solo_seeds": [], "world_events": []}),
            json.dumps(
                {
                    "narrative_summary": "Arya stayed still and learned the guard pattern.",
                    "outcomes": [
                        {
                            "agent_id": "arya",
                            "goal_status": "advanced",
                            "new_knowledge": "The guard circles every five minutes.",
                            "emotional_delta": "fear hardening into patience",
                        }
                    ],
                    "relationship_deltas": [],
                    "unexpected": "",
                }
            ),
            json.dumps(
                {
                    "emotional_delta": {
                        "dominant_now": "focused caution",
                        "underneath": "fear",
                        "shift_reason": "Observation created a tactical opening",
                    },
                    "goal_stack_update": {
                        "top_goal_status": "advanced",
                        "top_goal_still_priority": True,
                        "new_goal": None,
                        "resolved_goal": None,
                    },
                    "relationship_updates": [],
                    "needs_reprojection": False,
                    "reprojection_reason": "",
                }
            ),
        ]
        client = build_client(responses)
        store = InMemoryStore()
        gendry_snapshot = CharacterSnapshot(
            identity=CharacterIdentity(character_id="gendry", name="Gendry"),
            replay_key=ReplayKey(tick="chapter_02", timeline_index=2),
            current_state={"location": "smithy"},
            goals=[
                Goal(
                    priority=1,
                    goal="find a way out",
                    motivation="survival",
                    obstacle="guards",
                    time_horizon="immediate",
                    emotional_charge="worry",
                    abandon_condition="safe route appears",
                )
            ],
            working_memory=[],
            relationships=[],
            inferred_state=SnapshotInference.model_validate(
                {
                    "emotional_state": {
                        "dominant": "wary",
                        "secondary": [],
                        "confidence": 0.3,
                    },
                    "immediate_tension": "",
                    "unspoken_subtext": "",
                    "physical_state": {
                        "energy": 0.7,
                        "injuries_or_constraints": "",
                        "location": "smithy",
                        "current_activity": "waiting",
                    },
                    "knowledge_state": {
                        "new_knowledge": [],
                        "active_misbeliefs": [],
                    },
                }
            ),
        )
        runner = SimulationTickRunner(
            world_manager=WorldManager(
                activation_threshold=0.45,
                batched_projection_threshold=0.7,
            ),
            seed_detector=SeedDetector(GoalCollisionDetector(client)),
            trajectory_projector=StaticTrajectoryProjector(
                {
                    "arya": self._make_projection("wait behind the crates"),
                    "gendry": self._make_projection("watch the gate"),
                },
                fail_batch=True,
            ),
            event_simulator=EventSimulator(client),
            state_updater=EventStateUpdater(client),
            state_repo=StateChangeLogRepository(store),
            goal_repo=GoalStackRepository(store),
            relationship_repo=RelationshipRepository(store),
            memory_repo=EpisodicMemoryRepository(store),
            world_snapshot_repo=WorldSnapshotRepository(store),
            event_log_repo=EventLogRepository(store),
        )

        result = runner.run_tick(
            current_tick_label="day_001_morning",
            current_timeline_index=100,
            agent_runtimes=[
                AgentRuntime(snapshot=make_snapshot(), needs_reprojection=True),
                AgentRuntime(snapshot=gendry_snapshot, needs_reprojection=True),
            ],
            arc_state=NarrativeArcState(
                current_phase="rising_action",
                tension_level=0.1,
                unresolved_threads=["escape"],
                approaching_climax=False,
            ),
            world_seeds=[
                SimulationSeed(
                    seed_id="world_001",
                    seed_type="world",
                    participants=["arya"],
                    location="courtyard",
                    description="A guard patrol shifts direction.",
                    urgency=0.1,
                    conflict=0.1,
                    emotional_charge=0.1,
                    novelty=0.1,
                )
            ],
        )

        self.assertEqual(result.agent_runtimes["arya"].trajectory.immediate_next_action, "wait behind the crates")
        self.assertEqual(result.agent_runtimes["gendry"].trajectory.immediate_next_action, "watch the gate")
        self.assertEqual(result.event_failures, [])
        self.assertEqual(client.transport.calls, 3)

    def test_tick_runner_records_goal_collision_failure_and_continues(self) -> None:
        responses = [
            json.dumps(
                {
                    "narrative_summary": "Arya stayed still and learned the guard pattern.",
                    "outcomes": [
                        {
                            "agent_id": "arya",
                            "goal_status": "advanced",
                            "new_knowledge": "The guard circles every five minutes.",
                            "emotional_delta": "fear hardening into patience",
                        }
                    ],
                    "relationship_deltas": [],
                    "unexpected": "",
                }
            ),
            json.dumps(
                {
                    "emotional_delta": {
                        "dominant_now": "focused caution",
                        "underneath": "fear",
                        "shift_reason": "Observation created a tactical opening",
                    },
                    "goal_stack_update": {
                        "top_goal_status": "advanced",
                        "top_goal_still_priority": True,
                        "new_goal": None,
                        "resolved_goal": None,
                    },
                    "relationship_updates": [],
                    "needs_reprojection": False,
                    "reprojection_reason": "",
                }
            ),
        ]
        client = build_client(responses)
        store = InMemoryStore()
        runner = SimulationTickRunner(
            world_manager=WorldManager(),
            seed_detector=SeedDetector(FailingGoalCollisionDetector()),
            trajectory_projector=StaticTrajectoryProjector(
                {"arya": self._make_projection("wait behind the crates")}
            ),
            event_simulator=EventSimulator(client),
            state_updater=EventStateUpdater(client),
            state_repo=StateChangeLogRepository(store),
            goal_repo=GoalStackRepository(store),
            relationship_repo=RelationshipRepository(store),
            memory_repo=EpisodicMemoryRepository(store),
            world_snapshot_repo=WorldSnapshotRepository(store),
            event_log_repo=EventLogRepository(store),
        )

        result = runner.run_tick(
            current_tick_label="day_001_morning",
            current_timeline_index=100,
            agent_runtimes=[AgentRuntime(snapshot=make_snapshot(), needs_reprojection=True)],
            arc_state=NarrativeArcState(
                current_phase="rising_action",
                tension_level=0.1,
                unresolved_threads=["escape"],
                approaching_climax=False,
            ),
            world_seeds=[
                SimulationSeed(
                    seed_id="world_001",
                    seed_type="world",
                    participants=["arya"],
                    location="courtyard",
                    description="A guard patrol shifts direction.",
                    urgency=0.1,
                    conflict=0.1,
                    emotional_charge=0.1,
                    novelty=0.1,
                )
            ],
        )

        self.assertEqual(len(store.world_snapshot), 1)
        self.assertEqual(len(store.event_log), 1)
        self.assertTrue(
            any(
                failure.stage == "goal_collision_detection"
                for failure in result.event_failures
            )
        )
        self.assertEqual(client.transport.calls, 2)

    def test_tick_runner_wakes_socially_connected_bystander_after_salient_event(self) -> None:
        responses = [
            json.dumps(
                {
                    "primary_intention": "stay hidden",
                    "motivation": "survival",
                    "immediate_next_action": "wait behind the crates",
                    "contingencies": [],
                    "greatest_fear_this_horizon": "being seen",
                    "abandon_condition": "safe path opens",
                    "held_back_impulse": "run immediately",
                    "projection_horizon": "4 ticks (~1920 minutes)",
                }
            ),
            json.dumps({"goal_tensions": [], "solo_seeds": [], "world_events": []}),
            json.dumps(
                {
                    "scene_opening": "Arya makes a dangerous move in the courtyard.",
                    "resolution_conditions": {
                        "primary": "She escapes immediate danger",
                        "secondary": "She learns something crucial",
                        "forced_exit": "The chance passes",
                    },
                    "agent_perceptions": {"arya": "The patrol is closer than expected."},
                    "tension_signature": "Narrow escape window",
                }
            ),
            json.dumps(
                {
                    "internal": {
                        "thought": "I have to move now.",
                        "emotion_now": "fear",
                        "goal_update": "commit to the risky route",
                        "what_i_noticed": "The patrol is too close for delay.",
                    },
                    "external": {
                        "dialogue": "",
                        "physical_action": "slips between the crates",
                        "tone": "silent",
                    },
                    "held_back": "calling for help",
                }
            ),
            json.dumps(
                {
                    "resolved": True,
                    "resolution_type": "secondary",
                    "scene_outcome": "Arya makes a dangerous move that changes everything.",
                    "continue": False,
                }
            ),
            json.dumps(
                {
                    "emotional_delta": {
                        "dominant_now": "urgent focus",
                        "underneath": "fear",
                        "shift_reason": "The window to act is closing",
                    },
                    "goal_stack_update": {
                        "top_goal_status": "advanced",
                        "top_goal_still_priority": True,
                        "new_goal": None,
                        "resolved_goal": None,
                    },
                    "relationship_updates": [],
                    "needs_reprojection": False,
                    "reprojection_reason": "",
                }
            ),
        ]
        client = build_client(responses)
        store = InMemoryStore()
        runner = SimulationTickRunner(
            world_manager=WorldManager(
                activation_threshold=0.45,
                batched_projection_threshold=0.7,
                foreground_threshold=0.4,
            ),
            seed_detector=SeedDetector(GoalCollisionDetector(client)),
            trajectory_projector=TrajectoryProjector(client),
            event_simulator=EventSimulator(client),
            state_updater=EventStateUpdater(client),
            state_repo=StateChangeLogRepository(store),
            goal_repo=GoalStackRepository(store),
            relationship_repo=RelationshipRepository(store),
            memory_repo=EpisodicMemoryRepository(store),
            world_snapshot_repo=WorldSnapshotRepository(store),
            event_log_repo=EventLogRepository(store),
        )
        gendry_snapshot = CharacterSnapshot(
            identity=CharacterIdentity(character_id="gendry", name="Gendry"),
            replay_key=ReplayKey(tick="chapter_02", timeline_index=2),
            current_state={"location": "smithy"},
            goals=[],
            working_memory=[],
            relationships=[
                RelationshipLogEntry(
                    from_character_id="gendry",
                    to_character_id="arya",
                    replay_key=ReplayKey(tick="chapter_02", timeline_index=2),
                    trust_value=0.6,
                    trust_delta=0.1,
                    sentiment_shift="protective",
                    reason="traveling together",
                )
            ],
            inferred_state=None,
        )

        result = runner.run_tick(
            current_tick_label="day_001_morning",
            current_timeline_index=100,
            agent_runtimes=[
                AgentRuntime(snapshot=make_snapshot(), needs_reprojection=True),
                AgentRuntime(snapshot=gendry_snapshot, needs_reprojection=False),
            ],
            arc_state=NarrativeArcState(
                current_phase="rising_action",
                tension_level=0.1,
                unresolved_threads=["escape"],
                approaching_climax=False,
            ),
            world_seeds=[
                SimulationSeed(
                    seed_id="world_urgent",
                    seed_type="world",
                    participants=["arya"],
                    location="courtyard",
                    description="Arya makes a dangerous move in the courtyard.",
                    urgency=0.9,
                    conflict=0.8,
                    emotional_charge=0.9,
                    world_importance=0.6,
                    novelty=0.6,
                )
            ],
            language_guidance="- Primary language: English\n- Dialogue style: terse and tactical",
        )

        self.assertEqual(result.woken_agents["arya"], "event_participant")
        self.assertEqual(result.woken_agents["gendry"], "social_graph")
        self.assertTrue(result.agent_runtimes["gendry"].needs_reprojection)
        self.assertIsNone(result.agent_runtimes["gendry"].trajectory)

    def test_tick_runner_schedules_bridge_event_for_remote_social_contact(self) -> None:
        responses = [
            json.dumps(
                {
                    "primary_intention": "stay hidden",
                    "motivation": "survival",
                    "immediate_next_action": "wait behind the crates",
                    "contingencies": [],
                    "greatest_fear_this_horizon": "being seen",
                    "abandon_condition": "safe path opens",
                    "held_back_impulse": "run immediately",
                    "projection_horizon": "4 ticks (~1920 minutes)",
                }
            ),
            json.dumps({"goal_tensions": [], "solo_seeds": [], "world_events": []}),
            json.dumps(
                {
                    "scene_opening": "Arya makes a dangerous move in the courtyard.",
                    "resolution_conditions": {
                        "primary": "She escapes immediate danger",
                        "secondary": "She learns something crucial",
                        "forced_exit": "The chance passes",
                    },
                    "agent_perceptions": {"arya": "The patrol is closer than expected."},
                    "tension_signature": "Narrow escape window",
                }
            ),
            json.dumps(
                {
                    "internal": {
                        "thought": "I have to move now.",
                        "emotion_now": "fear",
                        "goal_update": "commit to the risky route",
                        "what_i_noticed": "The patrol is too close for delay.",
                    },
                    "external": {
                        "dialogue": "",
                        "physical_action": "slips between the crates",
                        "tone": "silent",
                    },
                    "held_back": "calling for help",
                }
            ),
            json.dumps(
                {
                    "resolved": True,
                    "resolution_type": "secondary",
                    "scene_outcome": "Arya makes a dangerous move that changes everything.",
                    "continue": False,
                }
            ),
            json.dumps(
                {
                    "emotional_delta": {
                        "dominant_now": "urgent focus",
                        "underneath": "fear",
                        "shift_reason": "The window to act is closing",
                    },
                    "goal_stack_update": {
                        "top_goal_status": "advanced",
                        "top_goal_still_priority": True,
                        "new_goal": None,
                        "resolved_goal": None,
                    },
                    "relationship_updates": [],
                    "needs_reprojection": False,
                    "reprojection_reason": "",
                }
            ),
        ]
        client = build_client(responses)
        store = InMemoryStore()
        scheduler = WorldEventScheduler()
        runner = SimulationTickRunner(
            world_manager=WorldManager(
                activation_threshold=0.45,
                batched_projection_threshold=0.7,
                foreground_threshold=0.4,
            ),
            seed_detector=SeedDetector(GoalCollisionDetector(client)),
            trajectory_projector=TrajectoryProjector(client),
            event_simulator=EventSimulator(client),
            state_updater=EventStateUpdater(client),
            state_repo=StateChangeLogRepository(store),
            goal_repo=GoalStackRepository(store),
            relationship_repo=RelationshipRepository(store),
            memory_repo=EpisodicMemoryRepository(store),
            world_snapshot_repo=WorldSnapshotRepository(store),
            event_log_repo=EventLogRepository(store),
            world_event_scheduler=scheduler,
        )
        gendry_snapshot = CharacterSnapshot(
            identity=CharacterIdentity(character_id="gendry", name="Gendry"),
            replay_key=ReplayKey(tick="chapter_02", timeline_index=2),
            current_state={"location": "smithy"},
            goals=[],
            working_memory=[],
            relationships=[
                RelationshipLogEntry(
                    from_character_id="gendry",
                    to_character_id="arya",
                    replay_key=ReplayKey(tick="chapter_02", timeline_index=2),
                    trust_value=0.6,
                    trust_delta=0.1,
                    sentiment_shift="protective",
                    reason="traveling together",
                )
            ],
            inferred_state=None,
        )

        result = runner.run_tick(
            current_tick_label="day_001_morning",
            current_timeline_index=100,
            agent_runtimes=[
                AgentRuntime(snapshot=make_snapshot(), needs_reprojection=True),
                AgentRuntime(snapshot=gendry_snapshot, needs_reprojection=False),
            ],
            arc_state=NarrativeArcState(
                current_phase="rising_action",
                tension_level=0.1,
                unresolved_threads=["escape"],
                approaching_climax=False,
            ),
            world_seeds=[
                SimulationSeed(
                    seed_id="world_urgent",
                    seed_type="world",
                    participants=["arya"],
                    location="courtyard",
                    description="Arya makes a dangerous move in the courtyard.",
                    urgency=0.9,
                    conflict=0.8,
                    emotional_charge=0.9,
                    world_importance=0.6,
                    novelty=0.6,
                )
            ],
            language_guidance="- Primary language: English\n- Dialogue style: terse and tactical",
        )

        self.assertEqual(len(result.bridge_events), 1)
        self.assertEqual(result.bridge_events[0]["event_id"], "evt_130_001_bridge_gendry")
        self.assertEqual(len(scheduler.pending_events), 1)
        self.assertEqual(scheduler.pending_events[0].location, "smithy")
        self.assertEqual(scheduler.pending_events[0].affected_agents, ["gendry"])
        self.assertIn("Your planning horizon: 5 ticks (~600 minutes)", client.transport.prompts[0].user)
        self.assertIn("Dialogue style: terse and tactical", client.transport.prompts[0].user)

    def test_tick_runner_carries_forward_tick_recovery_after_spotlight_salience(self) -> None:
        responses = [
            json.dumps(
                {
                    "primary_intention": "stay hidden",
                    "motivation": "survival",
                    "immediate_next_action": "wait behind the crates",
                    "contingencies": [],
                    "greatest_fear_this_horizon": "being seen",
                    "abandon_condition": "safe path opens",
                    "held_back_impulse": "run immediately",
                    "projection_horizon": "4 ticks (~20 minutes)",
                }
            ),
            json.dumps({"goal_tensions": [], "solo_seeds": [], "world_events": []}),
            json.dumps(
                {
                    "scene_opening": "Arya bolts for a dangerous gap in the patrol.",
                    "resolution_conditions": {
                        "primary": "She crosses unseen",
                        "secondary": "She spots an opening",
                        "forced_exit": "The patrol closes around her",
                    },
                    "agent_perceptions": {"arya": "Every second matters now."},
                    "tension_signature": "Immediate escape attempt",
                }
            ),
            json.dumps(
                {
                    "internal": {
                        "thought": "Move now or never.",
                        "emotion_now": "fear",
                        "goal_update": "commit to the escape route",
                        "what_i_noticed": "The patrol gap is opening.",
                    },
                    "external": {
                        "dialogue": "",
                        "physical_action": "darts across the open ground",
                        "tone": "silent",
                    },
                    "held_back": "freezing in place",
                }
            ),
            json.dumps(
                {
                    "resolved": True,
                    "resolution_type": "primary",
                    "scene_outcome": "Arya commits to the escape and survives the burst of danger.",
                    "continue": False,
                }
            ),
            json.dumps(
                {
                    "emotional_delta": {
                        "dominant_now": "shaken focus",
                        "underneath": "relief",
                        "shift_reason": "She survived the immediate burst of danger",
                    },
                    "goal_stack_update": {
                        "top_goal_status": "advanced",
                        "top_goal_still_priority": True,
                        "new_goal": None,
                        "resolved_goal": None,
                    },
                    "relationship_updates": [],
                    "needs_reprojection": False,
                    "reprojection_reason": "",
                }
            ),
            json.dumps({"goal_tensions": [], "solo_seeds": [], "world_events": []}),
        ]
        client = build_client(responses)
        store = InMemoryStore()
        runner = SimulationTickRunner(
            world_manager=WorldManager(tick_recovery_ticks=2),
            seed_detector=SeedDetector(GoalCollisionDetector(client)),
            trajectory_projector=TrajectoryProjector(client),
            event_simulator=EventSimulator(client),
            state_updater=EventStateUpdater(client),
            state_repo=StateChangeLogRepository(store),
            goal_repo=GoalStackRepository(store),
            relationship_repo=RelationshipRepository(store),
            memory_repo=EpisodicMemoryRepository(store),
            world_snapshot_repo=WorldSnapshotRepository(store),
            event_log_repo=EventLogRepository(store),
        )
        arc_state = NarrativeArcState(
            current_phase="climax",
            tension_level=1.0,
            unresolved_threads=["escape"],
            approaching_climax=True,
        )

        first = runner.run_tick(
            current_tick_label="day_001_morning",
            current_timeline_index=100,
            agent_runtimes=[AgentRuntime(snapshot=make_snapshot(), needs_reprojection=True)],
            arc_state=arc_state,
            world_seeds=[
                SimulationSeed(
                    seed_id="world_spotlight",
                    seed_type="world",
                    participants=["arya"],
                    location="courtyard",
                    description="Arya bolts for a dangerous gap in the patrol.",
                    urgency=0.9,
                    conflict=0.8,
                    emotional_charge=0.9,
                    world_importance=0.9,
                    novelty=0.9,
                )
            ],
        )

        second = runner.run_tick(
            current_tick_label="day_001_late_morning",
            current_timeline_index=first.replay_key.timeline_index,
            agent_runtimes=list(first.agent_runtimes.values()),
            arc_state=arc_state,
            cooldown_ticks_remaining=first.tick_cooldown_remaining,
        )

        self.assertEqual(first.tick_minutes, 1)
        self.assertEqual(first.tick_cooldown_remaining, 2)
        self.assertGreaterEqual(first.max_observed_salience, 0.8)
        self.assertEqual(second.tick_minutes, 60)
        self.assertEqual(second.tick_cooldown_remaining, 1)

    def test_tick_runner_skips_failed_event_and_keeps_tick_alive(self) -> None:
        responses = [
            json.dumps(
                {
                    "primary_intention": "stay hidden",
                    "motivation": "survival",
                    "immediate_next_action": "wait",
                    "contingencies": [],
                    "greatest_fear_this_horizon": "being seen",
                    "abandon_condition": "safe path opens",
                    "held_back_impulse": "run",
                    "projection_horizon": "4 ticks (~1920 minutes)",
                }
            ),
            json.dumps({"goal_tensions": [], "solo_seeds": [], "world_events": []}),
        ]
        client = build_client(responses)
        store = InMemoryStore()
        runner = SimulationTickRunner(
            world_manager=WorldManager(),
            seed_detector=SeedDetector(GoalCollisionDetector(client)),
            trajectory_projector=TrajectoryProjector(client),
            event_simulator=FailingEventSimulator(),
            state_updater=EventStateUpdater(client),
            state_repo=StateChangeLogRepository(store),
            goal_repo=GoalStackRepository(store),
            relationship_repo=RelationshipRepository(store),
            memory_repo=EpisodicMemoryRepository(store),
            world_snapshot_repo=WorldSnapshotRepository(store),
            event_log_repo=EventLogRepository(store),
        )

        result = runner.run_tick(
            current_tick_label="day_001_morning",
            current_timeline_index=100,
            agent_runtimes=[AgentRuntime(snapshot=make_snapshot(), needs_reprojection=True)],
            arc_state=NarrativeArcState(
                current_phase="rising_action",
                tension_level=0.1,
                unresolved_threads=["escape"],
                approaching_climax=False,
            ),
            world_seeds=[
                SimulationSeed(
                    seed_id="world_001",
                    seed_type="world",
                    participants=["arya"],
                    location="courtyard",
                    description="A guard patrol shifts direction.",
                    urgency=0.1,
                    conflict=0.1,
                    emotional_charge=0.1,
                    novelty=0.1,
                )
            ],
        )

        self.assertEqual(len(store.state_change_log), 0)
        self.assertEqual(len(store.episodic_memory), 0)
        self.assertEqual(len(store.event_log), 0)
        self.assertEqual(len(store.world_snapshot), 1)
        self.assertEqual(len(result.event_failures), 1)
        self.assertEqual(result.event_failures[0].stage, "event_simulation")

    def test_tick_runner_retries_event_log_write_failures(self) -> None:
        responses = [
            json.dumps(
                {
                    "primary_intention": "stay hidden",
                    "motivation": "survival",
                    "immediate_next_action": "wait behind the crates",
                    "contingencies": [],
                    "greatest_fear_this_horizon": "being seen",
                    "abandon_condition": "safe path opens",
                    "held_back_impulse": "run immediately",
                    "projection_horizon": "4 ticks (~1920 minutes)",
                }
            ),
            json.dumps({"goal_tensions": [], "solo_seeds": [], "world_events": []}),
            json.dumps(
                {
                    "narrative_summary": "Arya stayed still and learned the guard pattern.",
                    "outcomes": [
                        {
                            "agent_id": "arya",
                            "goal_status": "advanced",
                            "new_knowledge": "The guard circles every five minutes.",
                            "emotional_delta": "fear hardening into patience",
                        }
                    ],
                    "relationship_deltas": [],
                    "unexpected": "",
                }
            ),
            json.dumps(
                {
                    "emotional_delta": {
                        "dominant_now": "focused caution",
                        "underneath": "fear",
                        "shift_reason": "Observation created a tactical opening",
                    },
                    "goal_stack_update": {
                        "top_goal_status": "advanced",
                        "top_goal_still_priority": True,
                        "new_goal": None,
                        "resolved_goal": None,
                    },
                    "relationship_updates": [],
                    "needs_reprojection": False,
                    "reprojection_reason": "",
                }
            ),
        ]
        client = build_client(responses)
        store = InMemoryStore()
        flaky_event_log = FlakyAppendProxy(EventLogRepository(store), failures_before_success=2)
        runner = SimulationTickRunner(
            world_manager=WorldManager(),
            seed_detector=SeedDetector(GoalCollisionDetector(client)),
            trajectory_projector=TrajectoryProjector(client),
            event_simulator=EventSimulator(client),
            state_updater=EventStateUpdater(client),
            state_repo=StateChangeLogRepository(store),
            goal_repo=GoalStackRepository(store),
            relationship_repo=RelationshipRepository(store),
            memory_repo=EpisodicMemoryRepository(store),
            world_snapshot_repo=WorldSnapshotRepository(store),
            event_log_repo=flaky_event_log,
            write_retry_attempts=3,
            write_retry_base_delay_seconds=0,
        )

        result = runner.run_tick(
            current_tick_label="day_001_morning",
            current_timeline_index=100,
            agent_runtimes=[AgentRuntime(snapshot=make_snapshot(), needs_reprojection=True)],
            arc_state=NarrativeArcState(
                current_phase="rising_action",
                tension_level=0.1,
                unresolved_threads=["escape"],
                approaching_climax=False,
            ),
            world_seeds=[
                SimulationSeed(
                    seed_id="world_001",
                    seed_type="world",
                    participants=["arya"],
                    location="courtyard",
                    description="A guard patrol shifts direction.",
                    urgency=0.1,
                    conflict=0.1,
                    emotional_charge=0.1,
                    novelty=0.1,
                )
            ],
        )

        self.assertEqual(len(store.event_log), 1)
        self.assertEqual(flaky_event_log.attempts, 3)
        self.assertEqual(result.event_failures, [])

    def test_tick_runner_writes_state_before_memory_before_relationships(self) -> None:
        responses = [
            json.dumps(
                {
                    "primary_intention": "stay hidden",
                    "motivation": "survival",
                    "immediate_next_action": "wait behind the crates",
                    "contingencies": [],
                    "greatest_fear_this_horizon": "being seen",
                    "abandon_condition": "safe path opens",
                    "held_back_impulse": "run immediately",
                    "projection_horizon": "4 ticks (~1920 minutes)",
                }
            ),
            json.dumps({"goal_tensions": [], "solo_seeds": [], "world_events": []}),
            json.dumps(
                {
                    "narrative_summary": "Arya watched the patrol and tested Gendry's trust.",
                    "outcomes": [
                        {
                            "agent_id": "arya",
                            "goal_status": "advanced",
                            "new_knowledge": "Gendry is nearby.",
                            "emotional_delta": "fear hardening into focus",
                        }
                    ],
                    "relationship_deltas": [],
                    "unexpected": "",
                }
            ),
            json.dumps(
                {
                    "emotional_delta": {
                        "dominant_now": "focused caution",
                        "underneath": "fear",
                        "shift_reason": "Observation created a tactical opening",
                    },
                    "goal_stack_update": {
                        "top_goal_status": "advanced",
                        "top_goal_still_priority": True,
                        "new_goal": None,
                        "resolved_goal": None,
                    },
                    "relationship_updates": [
                        {
                            "target_id": "gendry",
                            "trust_delta": 0.2,
                            "sentiment_shift": "more trusting",
                            "pinned": False,
                            "pin_reason": "",
                        }
                    ],
                    "needs_reprojection": False,
                    "reprojection_reason": "",
                }
            ),
        ]
        client = build_client(responses)
        store = InMemoryStore()
        calls = []
        runner = SimulationTickRunner(
            world_manager=WorldManager(),
            seed_detector=SeedDetector(GoalCollisionDetector(client)),
            trajectory_projector=TrajectoryProjector(client),
            event_simulator=EventSimulator(client),
            state_updater=EventStateUpdater(client),
            state_repo=AppendRecorder("state", StateChangeLogRepository(store), calls),
            goal_repo=AppendRecorder("goal", GoalStackRepository(store), calls),
            relationship_repo=AppendRecorder("relationship", RelationshipRepository(store), calls),
            memory_repo=AppendRecorder("memory", EpisodicMemoryRepository(store), calls),
            world_snapshot_repo=AppendRecorder("world_snapshot", WorldSnapshotRepository(store), calls),
            event_log_repo=AppendRecorder("event_log", EventLogRepository(store), calls),
        )

        runner.run_tick(
            current_tick_label="day_001_morning",
            current_timeline_index=100,
            agent_runtimes=[AgentRuntime(snapshot=make_snapshot(), needs_reprojection=True)],
            arc_state=NarrativeArcState(
                current_phase="rising_action",
                tension_level=0.1,
                unresolved_threads=["escape"],
                approaching_climax=False,
            ),
            world_seeds=[
                SimulationSeed(
                    seed_id="world_001",
                    seed_type="world",
                    participants=["arya"],
                    location="courtyard",
                    description="A guard patrol shifts direction.",
                    urgency=0.1,
                    conflict=0.1,
                    emotional_charge=0.1,
                    novelty=0.1,
                )
            ],
        )

        self.assertEqual(
            calls,
            ["state", "state", "goal", "memory", "relationship", "event_log", "world_snapshot"],
        )


if __name__ == "__main__":
    unittest.main()
