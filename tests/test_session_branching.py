import unittest

from dreamdive.schemas import CharacterIdentity, CharacterSnapshot, Goal, NarrativeArcState, ReplayKey
from dreamdive.simulation.session import AgentRuntimeState, SimulationSessionState
from dreamdive.simulation.workflow import branch_session


def make_runtime() -> AgentRuntimeState:
    snapshot = CharacterSnapshot(
        identity=CharacterIdentity(
            character_id="arya",
            name="Arya",
            values=["family"],
            desires=["survive"],
        ),
        replay_key=ReplayKey(tick="t2", timeline_index=120),
        current_state={"location": "crypt", "emotional_state": "focused"},
        goals=[
            Goal(
                priority=1,
                description="escape the castle; survival; urgent",
                challenge="closed gates; caught",
                time_horizon="immediate",
            )
        ],
        working_memory=[],
        relationships=[],
    )
    return AgentRuntimeState(
        snapshot=snapshot,
        needs_reprojection=False,
        voice_samples=["Not today."],
        world_entities=[{"entity_id": "ent_gate", "name": "The Gate"}],
    )


class SessionBranchingTests(unittest.TestCase):
    def test_branch_before_event_restores_pending_world_event_and_rolls_back_state(self) -> None:
        session = SimulationSessionState(
            source_path="novel.md",
            current_tick_label="t2",
            current_timeline_index=120,
            arc_state=NarrativeArcState(
                current_phase="crisis",
                tension_level=0.8,
                unresolved_threads=["evt_world"],
                approaching_climax=True,
            ),
            agents={"arya": make_runtime()},
            pending_world_events=[],
            pending_background_jobs=[{"job_type": "arc_update", "target_id": "world", "run_after_timeline_index": 128, "reason": "due"}],
            append_only_log={
                "state_changes": [
                    {
                        "character_id": "arya",
                        "dimension": "location",
                        "replay_key": {"tick": "t0", "timeline_index": 0, "event_sequence": 0},
                        "to_value": "yard",
                    },
                    {
                        "character_id": "arya",
                        "dimension": "location",
                        "replay_key": {"tick": "t1", "timeline_index": 100, "event_sequence": 0},
                        "from_value": "yard",
                        "to_value": "crypt",
                    },
                ],
                "goal_stacks": [
                    {
                        "character_id": "arya",
                        "replay_key": {"tick": "t0", "timeline_index": 0, "event_sequence": 0},
                        "goals": [
                            {
                                "priority": 1,
                                "description": "stay hidden; survival; fear",
                                "challenge": "guards; safe route opens",
                                "time_horizon": "immediate",
                            }
                        ],
                    },
                    {
                        "character_id": "arya",
                        "replay_key": {"tick": "t1", "timeline_index": 100, "event_sequence": 0},
                        "goals": [
                            {
                                "priority": 1,
                                "description": "escape the castle; survival; urgent",
                                "challenge": "closed gates; caught",
                                "time_horizon": "immediate",
                            }
                        ],
                    },
                ],
                "relationships": [],
                "episodic_memories": [
                    {
                        "character_id": "arya",
                        "replay_key": {"tick": "t1", "timeline_index": 90, "event_sequence": 0},
                        "event_id": "evt_memory",
                        "participants": ["arya"],
                        "location": "yard",
                        "summary": "Arya memorized the guard route.",
                        "emotional_tag": "focus",
                        "salience": 0.6,
                        "pinned": False,
                        "compressed": False,
                    }
                ],
                "world_snapshots": [
                    {
                        "replay_key": {"tick": "t1", "timeline_index": 100, "event_sequence": 0},
                        "agent_locations": {"arya": "crypt"},
                        "narrative_arc": {
                            "current_phase": "rising_action",
                            "tension_level": 0.6,
                            "unresolved_threads": ["escape"],
                            "approaching_climax": False,
                        },
                        "unresolved_threads": ["escape"],
                        "next_tick_size_minutes": 60,
                    }
                ],
                "event_log": [
                    {
                        "event_id": "evt_world",
                        "tick": "t2",
                        "timeline_index": 120,
                        "seed_type": "world",
                        "location": "gate",
                        "participants": ["arya"],
                        "description": "The gate starts to close.",
                        "salience": 0.8,
                        "outcome_summary": "Pressure spikes.",
                        "resolution_mode": "background",
                    }
                ],
                "scheduled_world_events": [
                    {
                        "event_id": "evt_world",
                        "trigger_timeline_index": 120,
                        "description": "The gate starts to close.",
                        "affected_agents": ["arya"],
                        "urgency": "medium",
                        "location": "gate",
                        "cascades": [],
                    }
                ],
                "maintenance_log": [
                    {
                        "job_type": "memory_compression",
                        "target_id": "arya",
                        "timeline_index": 120,
                        "suppressed_event_ids": ["evt_memory"],
                        "compressed_event_ids": ["compressed_arya_120_1"],
                    }
                ],
            },
            metadata={
                "chapter_id": "001",
                "initial_arc_state": {
                    "current_phase": "setup",
                    "tension_level": 0.2,
                    "unresolved_threads": [],
                    "approaching_climax": False,
                },
                "suppressed_memory_ids_by_agent": {"arya": ["evt_memory"]},
                "last_arc_update_timeline_index": 120,
            },
        )

        branched = branch_session(session, before_event_id="evt_world")

        self.assertEqual(branched.current_timeline_index, 100)
        self.assertEqual(branched.arc_state.current_phase, "rising_action")
        self.assertEqual(branched.agents["arya"].snapshot.current_state["location"], "crypt")
        self.assertEqual(branched.agents["arya"].snapshot.goals[0].description, "escape the castle; survival; urgent")
        self.assertEqual(branched.pending_world_events[0]["event_id"], "evt_world")
        self.assertEqual(branched.pending_background_jobs, [])
        self.assertEqual(branched.metadata["suppressed_memory_ids_by_agent"].get("arya"), [])
        self.assertEqual(branched.agents["arya"].snapshot.working_memory[0].event_id, "evt_memory")
        self.assertTrue(branched.agents["arya"].needs_reprojection)

    def test_branch_to_explicit_timeline_uses_initial_arc_before_any_snapshot(self) -> None:
        session = SimulationSessionState(
            source_path="novel.md",
            current_tick_label="t3",
            current_timeline_index=200,
            arc_state=NarrativeArcState(
                current_phase="crisis",
                tension_level=0.9,
                unresolved_threads=["evt_x"],
                approaching_climax=True,
            ),
            agents={"arya": make_runtime()},
            append_only_log={
                "state_changes": [
                    {
                        "character_id": "arya",
                        "dimension": "location",
                        "replay_key": {"tick": "t0", "timeline_index": 0, "event_sequence": 0},
                        "to_value": "yard",
                    }
                ],
                "goal_stacks": [],
                "relationships": [],
                "episodic_memories": [],
                "world_snapshots": [],
                "event_log": [],
                "scheduled_world_events": [],
                "maintenance_log": [],
            },
            metadata={
                "initial_arc_state": {
                    "current_phase": "setup",
                    "tension_level": 0.2,
                    "unresolved_threads": [],
                    "approaching_climax": False,
                },
                "suppressed_memory_ids_by_agent": {},
            },
        )

        branched = branch_session(session, timeline_index=0, tick_label="branch_start")

        self.assertEqual(branched.current_tick_label, "branch_start")
        self.assertEqual(branched.arc_state.current_phase, "setup")
        self.assertEqual(branched.agents["arya"].snapshot.current_state["location"], "yard")


if __name__ == "__main__":
    unittest.main()
