import unittest

from dreamdive.event_window_selector import (
    calculate_chapter_boundaries_from_session,
    select_chapter_window_from_session,
)
from dreamdive.schemas import NarrativeArcState
from dreamdive.simulation.session import SimulationSessionState
from dreamdive.user_config import UserMeta


def _replay_key(timeline_index: int, event_sequence: int = 0) -> dict:
    return {
        "tick": "001",
        "timeline_index": timeline_index,
        "event_sequence": event_sequence,
    }


class EventWindowSelectorTests(unittest.TestCase):
    def test_select_chapter_window_from_session_deduplicates_and_enriches_events(self) -> None:
        session = SimulationSessionState(
            source_path="resources/demo.txt",
            current_tick_label="001",
            current_timeline_index=12,
            arc_state=NarrativeArcState(
                current_phase="rising_action",
                tension_level=0.6,
                unresolved_threads=["trust fracture"],
                approaching_climax=False,
            ),
            append_only_log={
                "episodic_memories": [
                    {
                        "character_id": "char_a",
                        "replay_key": _replay_key(5, 1),
                        "event_id": "evt_1",
                        "participants": ["char_a", "char_b"],
                        "location": "library",
                        "summary": "They clash in the library.",
                        "salience": 0.82,
                    },
                    {
                        "character_id": "char_b",
                        "replay_key": _replay_key(5, 1),
                        "event_id": "evt_1",
                        "participants": ["char_b"],
                        "location": "",
                        "summary": "Duplicate memory for the same event.",
                        "salience": 0.61,
                    },
                ],
                "state_changes": [
                    {
                        "character_id": "char_a",
                        "dimension": "resolve",
                        "replay_key": _replay_key(5, 1),
                        "event_id": "evt_1",
                        "to_value": "shaken",
                    },
                    {
                        "character_id": "char_b",
                        "dimension": "trust",
                        "replay_key": _replay_key(5, 1),
                        "event_id": "evt_1",
                        "to_value": 0.2,
                    },
                ],
                "event_log": [
                    {
                        "event_id": "evt_1",
                        "tick": "001",
                        "timeline_index": 5,
                        "seed_type": "spotlight",
                        "location": "library",
                        "participants": ["char_a", "char_b"],
                        "description": "The confrontation unfolds across a tense dialogue beat.",
                        "salience": 0.82,
                        "outcome_summary": "They leave the library more distrustful than before.",
                        "resolution_mode": "partial",
                    }
                ],
            },
        )

        window = select_chapter_window_from_session(
            session,
            start_tick_index=0,
            end_tick_index=10,
            user_meta=UserMeta(),
        )

        self.assertEqual(window.tick_range, "tick_0000-tick_0010")
        self.assertEqual(len(window.events), 1)
        event = window.events[0]
        self.assertEqual(event.event_id, "evt_1")
        self.assertEqual(event.summary, "They leave the library more distrustful than before.")
        self.assertEqual(
            event.scene_transcript,
            "The confrontation unfolds across a tense dialogue beat.",
        )
        self.assertEqual(event.participants, ["char_a", "char_b"])
        self.assertEqual(event.state_changes["char_a"]["resolve"], "shaken")
        self.assertEqual(event.state_changes["char_b"]["trust"], 0.2)
        self.assertEqual(window.high_salience_events, ["evt_1"])

    def test_select_chapter_window_from_session_prioritizes_focus_character_events(self) -> None:
        session = SimulationSessionState(
            source_path="resources/demo.txt",
            current_tick_label="001",
            current_timeline_index=12,
            arc_state=NarrativeArcState(
                current_phase="rising_action",
                tension_level=0.4,
                unresolved_threads=[],
                approaching_climax=False,
            ),
            append_only_log={
                "episodic_memories": [
                    {
                        "character_id": "observer",
                        "replay_key": _replay_key(2, 1),
                        "event_id": "evt_other",
                        "participants": ["observer"],
                        "location": "quad",
                        "summary": "A minor observation.",
                        "salience": 0.7,
                    },
                    {
                        "character_id": "focus_char",
                        "replay_key": _replay_key(3, 2),
                        "event_id": "evt_focus",
                        "participants": ["focus_char"],
                        "location": "bridge",
                        "summary": "The focus character makes a decision.",
                        "salience": 0.5,
                    },
                ],
                "state_changes": [],
                "event_log": [
                    {
                        "event_id": "evt_other",
                        "tick": "001",
                        "timeline_index": 2,
                        "seed_type": "background",
                        "location": "quad",
                        "participants": ["observer"],
                        "description": "Observer scene.",
                        "salience": 0.7,
                        "outcome_summary": "Observer notices a clue.",
                        "resolution_mode": "resolved",
                    },
                    {
                        "event_id": "evt_focus",
                        "tick": "001",
                        "timeline_index": 3,
                        "seed_type": "spotlight",
                        "location": "bridge",
                        "participants": ["focus_char"],
                        "description": "Focus character scene.",
                        "salience": 0.5,
                        "outcome_summary": "Focus character chooses to act.",
                        "resolution_mode": "resolved",
                    },
                ],
            },
        )

        window = select_chapter_window_from_session(
            session,
            start_tick_index=0,
            end_tick_index=10,
            user_meta=UserMeta(focus_characters=["focus_char"]),
        )

        self.assertEqual([event.event_id for event in window.events], ["evt_focus", "evt_other"])

    def test_calculate_chapter_boundaries_from_session_breaks_on_strong_narrative_shift(self) -> None:
        session = SimulationSessionState(
            source_path="resources/demo.txt",
            current_tick_label="001",
            current_timeline_index=40,
            arc_state=NarrativeArcState(
                current_phase="rising_action",
                tension_level=0.7,
                unresolved_threads=["betrayal"],
                approaching_climax=False,
            ),
            append_only_log={
                "event_log": [
                    {
                        "event_id": "evt_1",
                        "tick": "001",
                        "timeline_index": 2,
                        "seed_type": "background",
                        "location": "dormitory",
                        "participants": ["char_a"],
                        "description": "Quiet preparation.",
                        "salience": 0.35,
                        "outcome_summary": "The protagonist prepares in silence.",
                        "resolution_mode": "background",
                    },
                    {
                        "event_id": "evt_2",
                        "tick": "001",
                        "timeline_index": 6,
                        "seed_type": "spotlight",
                        "location": "dormitory",
                        "participants": ["char_a", "char_b"],
                        "description": "A confrontation erupts.",
                        "salience": 0.91,
                        "outcome_summary": "The confrontation changes the relationship.",
                        "resolution_mode": "spotlight",
                    },
                    {
                        "event_id": "evt_3",
                        "tick": "001",
                        "timeline_index": 24,
                        "seed_type": "background",
                        "location": "riverbank",
                        "participants": ["char_c"],
                        "description": "A distant thread begins.",
                        "salience": 0.38,
                        "outcome_summary": "Another thread opens far away.",
                        "resolution_mode": "background",
                    },
                    {
                        "event_id": "evt_4",
                        "tick": "001",
                        "timeline_index": 31,
                        "seed_type": "foreground",
                        "location": "riverbank",
                        "participants": ["char_c", "char_d"],
                        "description": "The new thread escalates.",
                        "salience": 0.8,
                        "outcome_summary": "The new thread becomes dangerous.",
                        "resolution_mode": "foreground",
                    },
                ]
            },
        )

        boundaries = calculate_chapter_boundaries_from_session(
            session,
            start_tick_index=0,
            end_tick_index=39,
            user_meta=UserMeta(),
            default_ticks_per_chapter=0,
        )

        self.assertEqual(len(boundaries), 2)
        self.assertEqual(boundaries[0][0], 0)
        self.assertLess(boundaries[0][1], boundaries[1][0])
        self.assertGreaterEqual(boundaries[0][1], 10)
        self.assertLessEqual(boundaries[0][1], 20)
        self.assertEqual(boundaries[-1][1], 39)


if __name__ == "__main__":
    unittest.main()
