import unittest

from dreamdive.schemas import (
    CharacterIdentity,
    EpisodicMemory,
    Goal,
    GoalStackSnapshot,
    RelationshipLogEntry,
    ReplayKey,
    StateChangeLogEntry,
    TimeHorizon,
)
from dreamdive.simulation.bootstrap import SnapshotBootstrapper


class SnapshotBootstrapperTests(unittest.TestCase):
    def test_snapshot_bootstrap_builds_current_state_and_ranks_memory(self) -> None:
        bootstrapper = SnapshotBootstrapper()
        replay_key = ReplayKey(tick="chapter_10", timeline_index=10)
        identity = CharacterIdentity(character_id="ned", name="Ned Stark")
        state_entries = [
            StateChangeLogEntry(
                character_id="ned",
                dimension="location",
                replay_key=ReplayKey(tick="chapter_07", timeline_index=7),
                to_value="great_hall",
            ),
            StateChangeLogEntry(
                character_id="ned",
                dimension="emotional_state",
                replay_key=ReplayKey(tick="chapter_09", timeline_index=9),
                to_value={"dominant": "concern"},
            ),
        ]
        goal_stack = GoalStackSnapshot(
            character_id="ned",
            replay_key=replay_key,
            goals=[
                Goal(
                    priority=1,
                    goal="protect Robert's legitimacy inquiry",
                    motivation="duty",
                    obstacle="court intrigue",
                    time_horizon=TimeHorizon.THIS_WEEK,
                    emotional_charge="uneasy resolve",
                    abandon_condition="proof inquiry is false",
                )
            ],
        )
        memories = [
            EpisodicMemory(
                character_id="ned",
                replay_key=ReplayKey(tick="chapter_09", timeline_index=9),
                summary="Pinned confrontation",
                salience=0.8,
                pinned=True,
            ),
            EpisodicMemory(
                character_id="ned",
                replay_key=ReplayKey(tick="chapter_10", timeline_index=10),
                summary="Recent clue",
                salience=0.7,
                semantic_score=0.9,
            ),
        ]
        relationships = [
            RelationshipLogEntry(
                from_character_id="ned",
                to_character_id="cersei",
                replay_key=replay_key,
                trust_value=0.1,
                trust_delta=-0.2,
                sentiment_shift="wary respect -> suspicion",
                reason="contradictory story",
            )
        ]

        snapshot = bootstrapper.build_snapshot(
            identity=identity,
            replay_key=replay_key,
            state_entries=state_entries,
            goal_stack=goal_stack,
            memories=memories,
            relationships=relationships,
            default_state={"location": "winterfell"},
        )

        self.assertEqual(snapshot.current_state["location"], "great_hall")
        self.assertEqual(snapshot.current_state["emotional_state"], "concern")
        self.assertEqual(snapshot.goals[0].goal, "protect Robert's legitimacy inquiry")
        self.assertEqual(
            [memory.summary for memory in snapshot.working_memory],
            ["Pinned confrontation", "Recent clue"],
        )


if __name__ == "__main__":
    unittest.main()
