import unittest

from dreamdive.simulation.background_jobs import BackgroundJob
from dreamdive.simulation.background_queue_backend import (
    PgBossDispatchMessage,
    PgBossJobCodec,
    SessionBackgroundQueueBackend,
)


class BackgroundQueueBackendTests(unittest.TestCase):
    def test_session_backend_claims_acknowledges_and_snapshots_jobs(self) -> None:
        backend = SessionBackgroundQueueBackend(
            [
                {
                    "job_type": "memory_compression",
                    "target_id": "arya",
                    "run_after_timeline_index": 30,
                    "reason": "due",
                },
                {
                    "job_type": "arc_update",
                    "target_id": "world",
                    "run_after_timeline_index": 40,
                    "reason": "interval",
                },
            ]
        )

        claimed = backend.claim_due_jobs(current_timeline_index=30, limit=1)

        self.assertEqual(len(claimed), 1)
        self.assertEqual(claimed[0].job_type, "memory_compression")
        self.assertEqual(claimed[0].attempts, 1)
        self.assertEqual(backend.queued_count(), 1)

        backend.acknowledge(claimed[0].queue_key())
        snapshot = backend.snapshot()

        self.assertEqual(len(snapshot), 1)
        self.assertEqual(snapshot[0]["job_type"], "arc_update")

    def test_pgboss_codec_roundtrips_job_identity(self) -> None:
        codec = PgBossJobCodec(queue_name="dreamdive-maintenance")
        job = BackgroundJob(
            job_type="arc_update",
            target_id="world",
            run_after_timeline_index=80,
            reason="interval reached",
        )

        dispatch = codec.encode(job)

        self.assertEqual(
            dispatch,
            PgBossDispatchMessage(
                queue_name="dreamdive-maintenance",
                singleton_key="arc_update:world:80",
                payload={
                    "job_id": "arc_update:world:80",
                    "job_type": "arc_update",
                    "target_id": "world",
                    "run_after_timeline_index": 80,
                    "reason": "interval reached",
                    "schedule_basis": "timeline_index",
                    "status": "queued",
                    "attempts": 0,
                    "last_error": "",
                },
                start_after_timeline_index=80,
            ),
        )

        restored = codec.decode(dispatch)

        self.assertEqual(restored.queue_key(), "arc_update:world:80")
        self.assertEqual(restored.job_type, "arc_update")
        self.assertEqual(restored.target_id, "world")
        self.assertEqual(restored.run_after_timeline_index, 80)


if __name__ == "__main__":
    unittest.main()
