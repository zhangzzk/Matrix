import json
import unittest

from dreamdive.config import LLMProfileSettings
from dreamdive.llm.client import StructuredLLMClient
from dreamdive.schemas import CharacterIdentity, CharacterSnapshot, Goal, NarrativeArcState, ReplayKey
from dreamdive.simulation.background_runner import BackgroundMaintenanceRunner
from dreamdive.simulation.session import AgentRuntimeState, SimulationSessionState


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
            name="Arya",
            values=["family"],
            desires=["survive"],
        ),
        replay_key=ReplayKey(tick="t0", timeline_index=0),
        current_state={"location": "yard", "emotional_state": "fear"},
        goals=[
            Goal(
                priority=1,
                description="escape; survival; urgent",
                challenge="guards; safe route opens",
                time_horizon="immediate",
            )
        ],
        working_memory=[],
        relationships=[],
    )


class BackgroundRunnerTests(unittest.TestCase):
    def test_memory_compression_job_appends_summary_and_suppresses_sources(self) -> None:
        client = build_client(
            [
                json.dumps(
                    {
                        "preserved_full": [],
                        "compressed_summaries": [
                            {
                                "tick_range": "t1-t2",
                                "summary": "Several tense hours hiding near the gate.",
                                "emotional_tone": "fear tightening into focus",
                                "net_relationship_changes": "",
                                "net_goal_changes": "escape remained primary",
                                "source_event_ids": ["evt_1", "evt_2"],
                            }
                        ],
                        "discarded_event_ids": [],
                    }
                )
            ]
        )
        session = SimulationSessionState(
            source_path="novel.md",
            current_tick_label="t3",
            current_timeline_index=30,
            arc_state=NarrativeArcState(
                current_phase="rising_action",
                tension_level=0.5,
                unresolved_threads=[],
                approaching_climax=False,
            ),
            agents={"arya": AgentRuntimeState(snapshot=make_snapshot())},
            pending_background_jobs=[
                {
                    "job_type": "memory_compression",
                    "target_id": "arya",
                    "run_after_timeline_index": 30,
                    "reason": "due",
                }
            ],
            append_only_log={
                "episodic_memories": [
                    {
                        "character_id": "arya",
                        "replay_key": {"tick": "t1", "timeline_index": 1, "event_sequence": 0},
                        "event_id": "evt_1",
                        "participants": ["arya"],
                        "location": "yard",
                        "summary": "She hid by the gate.",
                        "emotional_tag": "fear",
                        "salience": 0.4,
                        "pinned": False,
                        "compressed": False,
                    },
                    {
                        "character_id": "arya",
                        "replay_key": {"tick": "t2", "timeline_index": 2, "event_sequence": 0},
                        "event_id": "evt_2",
                        "participants": ["arya"],
                        "location": "yard",
                        "summary": "She waited for the patrol to pass.",
                        "emotional_tag": "fear",
                        "salience": 0.35,
                        "pinned": False,
                        "compressed": False,
                    },
                ]
            },
            metadata={
                "suppressed_memory_ids_by_agent": {},
                "language_guidance": "- Primary language: English\n- Author style: sparse and tense",
            },
        )

        updated = BackgroundMaintenanceRunner(client).run_due_jobs(session)

        self.assertEqual(updated.pending_background_jobs, [])
        self.assertEqual(len(updated.append_only_log["episodic_memories"]), 3)
        self.assertIn(
            "evt_1",
            updated.metadata["suppressed_memory_ids_by_agent"]["arya"],
        )
        self.assertEqual(updated.metadata["background_queue_depth"], 0)
        self.assertEqual(updated.metadata["recent_background_job_errors"], [])
        self.assertIn("Author style: sparse and tense", client.transport.prompts[0].user)

    def test_arc_update_job_updates_arc_and_schedules_correction_event(self) -> None:
        client = build_client(
            [
                json.dumps(
                    {
                        "phase": "crisis",
                        "phase_changed": True,
                        "phase_change_reason": "threads converged",
                        "tension_level": 0.82,
                        "tension_delta": 0.22,
                        "tension_reason": "multiple confrontations are converging",
                        "unresolved_threads": [
                            {
                                "thread_id": "evt_9",
                                "description": "The gate escape",
                                "agents_involved": ["arya"],
                                "urgency": "high",
                                "resolution_condition": "Arya gets out or is caught",
                            }
                        ],
                        "approaching_nodes": [
                            {
                                "description": "Gate confrontation",
                                "agents_involved": ["arya"],
                                "estimated_ticks_away": 2,
                                "estimated_salience": 0.9,
                            }
                        ],
                        "narrative_drift": {
                            "drifting": True,
                            "drift_description": "Too static",
                            "suggested_correction": "A search party closes the exits.",
                        },
                    }
                )
            ]
        )
        session = SimulationSessionState(
            source_path="novel.md",
            current_tick_label="t5",
            current_timeline_index=80,
            arc_state=NarrativeArcState(
                current_phase="rising_action",
                tension_level=0.6,
                unresolved_threads=["evt_4"],
                approaching_climax=False,
            ),
            agents={"arya": AgentRuntimeState(snapshot=make_snapshot())},
            pending_background_jobs=[
                {
                    "job_type": "arc_update",
                    "target_id": "world",
                    "run_after_timeline_index": 80,
                    "reason": "due",
                }
            ],
            append_only_log={
                "event_log": [
                    {
                        "event_id": "evt_9",
                        "tick": "t5",
                        "timeline_index": 80,
                        "seed_type": "world",
                        "location": "yard",
                        "participants": ["arya"],
                        "description": "News spreads",
                        "salience": 0.8,
                        "outcome_summary": "The search tightened.",
                        "resolution_mode": "background",
                    }
                ]
            },
            metadata={
                "story_context": "Winterfell",
                "authorial_intent": "Pressure reveals character",
                "central_tension": "escape versus duty",
                "language_guidance": "- Primary language: English\n- Dialogue style: tight and tactical",
                "last_arc_update_timeline_index": 70,
                "suppressed_memory_ids_by_agent": {},
            },
        )

        updated = BackgroundMaintenanceRunner(client).run_due_jobs(session)

        self.assertEqual(updated.pending_background_jobs, [])
        self.assertEqual(updated.arc_state.current_phase, "crisis")
        self.assertTrue(updated.arc_state.approaching_climax)
        self.assertEqual(updated.arc_state.unresolved_threads, ["The gate escape"])
        self.assertEqual(updated.pending_world_events[0]["description"], "A search party closes the exits.")
        self.assertEqual(updated.metadata["background_queue_depth"], 0)
        self.assertEqual(updated.metadata["recent_background_job_errors"], [])
        self.assertIn("Dialogue style: tight and tactical", client.transport.prompts[0].user)
        self.assertIn("OUTPUT CONTRACT:", client.transport.prompts[0].user)
        self.assertIn('"phase"', client.transport.prompts[0].user)
        self.assertFalse(client.transport.prompts[0].stream)

    def test_failed_llm_background_job_records_issue_history(self) -> None:
        client = build_client(["{not valid json}"])
        session = SimulationSessionState(
            source_path="novel.md",
            current_tick_label="t3",
            current_timeline_index=30,
            arc_state=NarrativeArcState(
                current_phase="rising_action",
                tension_level=0.5,
                unresolved_threads=[],
                approaching_climax=False,
            ),
            agents={"arya": AgentRuntimeState(snapshot=make_snapshot())},
            pending_background_jobs=[
                {
                    "job_type": "memory_compression",
                    "target_id": "arya",
                    "run_after_timeline_index": 30,
                    "reason": "due",
                }
            ],
            append_only_log={
                "episodic_memories": [
                    {
                        "character_id": "arya",
                        "replay_key": {"tick": "t1", "timeline_index": 1, "event_sequence": 0},
                        "event_id": "evt_1",
                        "participants": ["arya"],
                        "location": "yard",
                        "summary": "She hid by the gate.",
                        "emotional_tag": "fear",
                        "salience": 0.4,
                        "pinned": False,
                        "compressed": False,
                    }
                ]
            },
            metadata={
                "suppressed_memory_ids_by_agent": {},
                "language_guidance": "- Primary language: English\n- Author style: spare and tense",
            },
        )

        updated = BackgroundMaintenanceRunner(client).run_due_jobs(session)

        self.assertEqual(updated.metadata["last_background_llm_issue_count"], 3)
        self.assertEqual(updated.metadata["llm_issue_count"], 3)
        self.assertEqual(updated.metadata["last_background_critical_llm_issue_count"], 1)
        self.assertEqual(updated.metadata["critical_llm_issue_count"], 1)
        self.assertEqual(len(updated.append_only_log["llm_issues"]), 3)
        self.assertEqual(updated.append_only_log["llm_issues"][0]["phase"], "background")
        self.assertEqual(updated.append_only_log["llm_issues"][0]["prompt_name"], "p3_1_memory_compression")
        self.assertEqual(updated.append_only_log["llm_issues"][0]["profile_name"], "moonshot")
        self.assertEqual(updated.append_only_log["llm_issues"][1]["profile_name"], "gemini")
        self.assertEqual(updated.append_only_log["llm_issues"][2]["severity"], "critical")

    def test_failed_due_job_is_requeued_with_error_metadata(self) -> None:
        client = build_client(["{not valid json}"])
        session = SimulationSessionState(
            source_path="novel.md",
            current_tick_label="t3",
            current_timeline_index=30,
            arc_state=NarrativeArcState(
                current_phase="rising_action",
                tension_level=0.5,
                unresolved_threads=[],
                approaching_climax=False,
            ),
            agents={"arya": AgentRuntimeState(snapshot=make_snapshot())},
            pending_background_jobs=[
                {
                    "job_type": "memory_compression",
                    "target_id": "arya",
                    "run_after_timeline_index": 30,
                    "reason": "due",
                }
            ],
            append_only_log={
                "episodic_memories": [
                    {
                        "character_id": "arya",
                        "replay_key": {"tick": "t1", "timeline_index": 1, "event_sequence": 0},
                        "event_id": "evt_1",
                        "participants": ["arya"],
                        "location": "yard",
                        "summary": "She hid by the gate.",
                        "emotional_tag": "fear",
                        "salience": 0.4,
                        "pinned": False,
                        "compressed": False,
                    }
                ]
            },
            metadata={"suppressed_memory_ids_by_agent": {}},
        )

        updated = BackgroundMaintenanceRunner(client).run_due_jobs(session)

        self.assertEqual(len(updated.pending_background_jobs), 1)
        self.assertEqual(updated.pending_background_jobs[0]["status"], "queued")
        self.assertEqual(updated.pending_background_jobs[0]["attempts"], 1)
        self.assertTrue(updated.pending_background_jobs[0]["last_error"])
        self.assertEqual(updated.metadata["background_queue_depth"], 1)
        self.assertEqual(len(updated.metadata["recent_background_job_errors"]), 1)


if __name__ == "__main__":
    unittest.main()
