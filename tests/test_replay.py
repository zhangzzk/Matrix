import unittest

from dreamdive.db.replay import StateReplay
from dreamdive.schemas import ReplayKey, StateChangeLogEntry


class StateReplayTests(unittest.TestCase):
    def test_get_value_at_tick_uses_default_when_dimension_has_no_entries(self) -> None:
        replay = StateReplay(default_values={"honor": 0.5})

        actual = replay.get_value_at_tick([], "jaime", "honor", timeline_index=5)

        self.assertEqual(actual, 0.5)

    def test_get_value_at_tick_uses_latest_entry_at_or_before_target(self) -> None:
        replay = StateReplay(default_values={"honor": 0.0})
        entries = [
            StateChangeLogEntry(
                character_id="jaime",
                dimension="honor",
                replay_key=ReplayKey(tick="chapter_01", timeline_index=1),
                from_value=0.0,
                to_value=0.2,
            ),
            StateChangeLogEntry(
                character_id="jaime",
                dimension="honor",
                replay_key=ReplayKey(tick="chapter_44", timeline_index=44),
                from_value=0.2,
                to_value=0.5,
            ),
        ]

        actual = replay.get_value_at_tick(entries, "jaime", "honor", timeline_index=20)

        self.assertEqual(actual, 0.2)

    def test_replay_character_state_orders_same_tick_by_event_sequence(self) -> None:
        replay = StateReplay(default_values={"location": "winterfell"})
        entries = [
            StateChangeLogEntry(
                character_id="arya",
                dimension="location",
                replay_key=ReplayKey(
                    tick="day_003_morning",
                    timeline_index=3,
                    event_sequence=0,
                ),
                from_value="winterfell",
                to_value="courtyard",
            ),
            StateChangeLogEntry(
                character_id="arya",
                dimension="location",
                replay_key=ReplayKey(
                    tick="day_003_morning",
                    timeline_index=3,
                    event_sequence=2,
                ),
                from_value="courtyard",
                to_value="crypt",
            ),
            StateChangeLogEntry(
                character_id="arya",
                dimension="emotional_state",
                replay_key=ReplayKey(
                    tick="day_003_morning",
                    timeline_index=3,
                    event_sequence=1,
                ),
                to_value={"dominant": "fear"},
            ),
        ]

        actual = replay.replay_character_state(entries, "arya", timeline_index=3)

        self.assertEqual(actual["location"], "crypt")
        self.assertEqual(actual["emotional_state"], "fear")


if __name__ == "__main__":
    unittest.main()
