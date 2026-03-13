import unittest

from dreamdive.db.models import EventLogRecord
from dreamdive.memory.arc_tracker import NarrativeArcTracker
from dreamdive.memory.consolidation import MemoryConsolidator
from dreamdive.schemas import EpisodicMemory, NarrativeArcState, ReplayKey
from dreamdive.simulation.background_jobs import BackgroundJob, BackgroundJobPlanner, BackgroundJobQueue


class BackgroundMaintenanceTests(unittest.TestCase):
    def test_background_job_queue_deduplicates_claims_and_requeues(self) -> None:
        queue = BackgroundJobQueue(
            [
                BackgroundJob(
                    job_type="arc_update",
                    target_id="world",
                    run_after_timeline_index=16,
                    reason="interval",
                )
            ]
        )

        queue.enqueue(
            BackgroundJob(
                job_type="arc_update",
                target_id="world",
                run_after_timeline_index=16,
                reason="duplicate interval",
            )
        )
        queue.enqueue(
            {
                "job_type": "memory_compression",
                "target_id": "arya",
                "run_after_timeline_index": 20,
                "reason": "staggered",
            }
        )

        self.assertEqual(len(queue.serialize()), 2)

        claimed = queue.claim_due_jobs(current_timeline_index=16)

        self.assertEqual(len(claimed), 1)
        self.assertEqual(claimed[0].job_type, "arc_update")
        self.assertEqual(claimed[0].attempts, 1)

        queue.fail(claimed[0].queue_key(), "temporary outage")
        serialized = queue.serialize()
        arc_job = next(item for item in serialized if item["job_type"] == "arc_update")
        self.assertEqual(arc_job["status"], "queued")
        self.assertEqual(arc_job["last_error"], "temporary outage")

        queue.acknowledge(arc_job["job_id"])
        self.assertEqual(len(queue.serialize()), 1)

    def test_memory_consolidator_preserves_pinned_and_compresses_old_mid_salience(self) -> None:
        consolidator = MemoryConsolidator(
            compression_interval_ticks=10,
            high_salience_threshold=0.7,
            discard_threshold=0.2,
        )
        memories = [
            EpisodicMemory(
                character_id="arya",
                replay_key=ReplayKey(tick="t1", timeline_index=1),
                event_id="evt_1",
                participants=["arya"],
                location="yard",
                summary="Pinned oath",
                emotional_tag="resolve",
                salience=0.9,
                pinned=True,
            ),
            EpisodicMemory(
                character_id="arya",
                replay_key=ReplayKey(tick="t2", timeline_index=2),
                event_id="evt_2",
                participants=["arya"],
                location="yard",
                summary="Minor hiding detail",
                emotional_tag="fear",
                salience=0.4,
            ),
            EpisodicMemory(
                character_id="arya",
                replay_key=ReplayKey(tick="t3", timeline_index=3),
                event_id="evt_3",
                participants=["arya"],
                location="yard",
                summary="Another quiet moment",
                emotional_tag="fear",
                salience=0.35,
            ),
        ]

        result = consolidator.consolidate(memories, current_timeline_index=20)

        self.assertEqual(len(result.compressed), 1)
        self.assertTrue(result.compressed[0].compressed)
        self.assertIn("Compressed memory", result.compressed[0].summary)
        self.assertEqual(result.retained[0].summary, "Pinned oath")

    def test_arc_tracker_raises_tension_from_recent_events(self) -> None:
        tracker = NarrativeArcTracker()
        events = [
            EventLogRecord(
                event_id="evt_1",
                tick="t1",
                timeline_index=1,
                seed_type="world",
                location="yard",
                participants=["arya"],
                description="News arrives",
                salience=0.4,
                outcome_summary="quietly spreads",
                resolution_mode="background",
            ),
            EventLogRecord(
                event_id="evt_2",
                tick="t2",
                timeline_index=2,
                seed_type="collision",
                location="hall",
                participants=["arya", "sansa"],
                description="Confrontation",
                salience=0.9,
                outcome_summary="sharp break",
                resolution_mode="spotlight",
            ),
        ]

        arc = tracker.update_from_events(events)

        self.assertGreaterEqual(arc.tension_level, 0.65)
        self.assertIn("evt_2", arc.unresolved_threads)

    def test_background_job_planner_staggers_memory_jobs_and_arc_updates(self) -> None:
        planner = BackgroundJobPlanner(
            compression_interval_ticks=15,
            arc_update_interval_ticks=8,
            stagger_window=5,
        )

        jobs = planner.plan_all(agent_ids=["arya", "sansa"], current_tick_count=16)

        self.assertTrue(any(job.job_type == "arc_update" for job in jobs))
        self.assertTrue(all(job.run_after_timeline_index == 16 for job in jobs))
        self.assertTrue(all(job.schedule_basis == "tick_count" for job in jobs))


if __name__ == "__main__":
    unittest.main()
