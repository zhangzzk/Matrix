import unittest

from dreamdive.simulation.world_events import (
    ScheduledWorldEvent,
    WorldEventCascade,
    WorldEventScheduler,
)


class WorldEventSchedulerTests(unittest.TestCase):
    def test_scheduler_reports_delta_to_next_pending_event(self) -> None:
        scheduler = WorldEventScheduler(
            [
                ScheduledWorldEvent(
                    event_id="evt_far",
                    trigger_timeline_index=180,
                    description="A distant rumor starts moving.",
                    affected_agents=["arya"],
                    urgency="low",
                ),
                ScheduledWorldEvent(
                    event_id="evt_near",
                    trigger_timeline_index=125,
                    description="A messenger is almost here.",
                    affected_agents=["sansa"],
                    urgency="medium",
                ),
            ]
        )

        self.assertEqual(scheduler.next_trigger_delta(100), 25)
        self.assertEqual(scheduler.next_trigger_delta(130), 0)

    def test_scheduler_emits_due_events_and_enqueues_cascades(self) -> None:
        scheduler = WorldEventScheduler(
            [
                ScheduledWorldEvent(
                    event_id="evt_news",
                    trigger_timeline_index=110,
                    description="News arrives from the capital.",
                    affected_agents=["arya"],
                    urgency="high",
                    location="courtyard",
                    cascades=[
                        WorldEventCascade(
                            description="The rumor reaches the kitchens.",
                            affected_agents=["sansa"],
                            delay_minutes=15,
                            urgency="medium",
                            location="kitchens",
                        )
                    ],
                )
            ]
        )

        due = scheduler.consume_due_events(current_timeline_index=100, dt_minutes=15)

        self.assertEqual(len(due), 1)
        self.assertEqual(due[0].seed_id, "evt_news")
        self.assertEqual(scheduler.fired_event_ids, ["evt_news"])
        self.assertEqual(len(scheduler.pending_events), 1)
        self.assertEqual(scheduler.pending_events[0].event_id, "evt_news_cascade_01")

    def test_scheduler_ignores_future_events(self) -> None:
        scheduler = WorldEventScheduler(
            [
                ScheduledWorldEvent(
                    event_id="evt_future",
                    trigger_timeline_index=300,
                    description="A ship finally docks.",
                    affected_agents=["arya"],
                    urgency="low",
                )
            ]
        )

        due = scheduler.consume_due_events(current_timeline_index=100, dt_minutes=30)

        self.assertEqual(due, [])
        self.assertEqual(len(scheduler.pending_events), 1)


if __name__ == "__main__":
    unittest.main()
