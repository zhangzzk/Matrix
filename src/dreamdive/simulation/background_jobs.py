from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Sequence, Set


@dataclass
class BackgroundJob:
    job_type: str
    target_id: str
    run_after_timeline_index: int
    reason: str
    job_id: str = ""
    schedule_basis: str = "timeline_index"
    status: str = "queued"
    attempts: int = 0
    last_error: str = ""

    def queue_key(self) -> str:
        return self.job_id or "{}:{}:{}".format(
            self.job_type,
            self.target_id,
            self.run_after_timeline_index,
        )

    def to_record(self) -> dict:
        return {
            "job_id": self.queue_key(),
            "job_type": self.job_type,
            "target_id": self.target_id,
            "run_after_timeline_index": self.run_after_timeline_index,
            "reason": self.reason,
            "schedule_basis": self.schedule_basis,
            "status": self.status,
            "attempts": self.attempts,
            "last_error": self.last_error,
        }

    @classmethod
    def from_record(cls, record: dict) -> "BackgroundJob":
        return cls(
            job_id=str(
                record.get("job_id")
                or "{}:{}:{}".format(
                    record.get("job_type", ""),
                    record.get("target_id", ""),
                    int(record.get("run_after_timeline_index", 0)),
                )
            ),
            job_type=str(record.get("job_type", "")),
            target_id=str(record.get("target_id", "")),
            run_after_timeline_index=int(record.get("run_after_timeline_index", 0)),
            reason=str(record.get("reason", "")),
            schedule_basis=str(record.get("schedule_basis", "timeline_index")),
            status=str(record.get("status", "queued")),
            attempts=int(record.get("attempts", 0)),
            last_error=str(record.get("last_error", "")),
        )


class BackgroundJobQueue:
    def __init__(self, jobs: Sequence[BackgroundJob | dict] | None = None) -> None:
        self._jobs = {}
        for job in jobs or []:
            self.enqueue(job)

    def enqueue(self, job: BackgroundJob | dict) -> BackgroundJob:
        item = job if isinstance(job, BackgroundJob) else BackgroundJob.from_record(job)
        key = item.queue_key()
        existing = self._jobs.get(key)
        if existing is None:
            normalized = item if item.job_id else item.from_record(item.to_record())
            self._jobs[key] = normalized
            return normalized

        existing.run_after_timeline_index = min(
            existing.run_after_timeline_index,
            item.run_after_timeline_index,
        )
        if not existing.reason and item.reason:
            existing.reason = item.reason
        if existing.status == "failed":
            existing.status = "queued"
        return existing

    def enqueue_many(self, jobs: Iterable[BackgroundJob | dict]) -> List[BackgroundJob]:
        return [self.enqueue(job) for job in jobs]

    def claim_due_jobs(
        self,
        *,
        current_timeline_index: int,
        current_tick_count: int | None = None,
        limit: int | None = None,
        job_types: Set[str] | None = None,
    ) -> List[BackgroundJob]:
        due = [
            job
            for job in self._ordered_jobs()
            if job.status == "queued"
            and (job_types is None or job.job_type in job_types)
            and self._is_due(
                job,
                current_timeline_index=current_timeline_index,
                current_tick_count=current_tick_count,
            )
        ]
        if limit is not None:
            due = due[: max(0, limit)]
        claimed = []
        for job in due:
            job.status = "running"
            job.attempts += 1
            claimed.append(BackgroundJob.from_record(job.to_record()))
        return claimed

    @staticmethod
    def _is_due(
        job: BackgroundJob,
        *,
        current_timeline_index: int,
        current_tick_count: int | None,
    ) -> bool:
        if job.schedule_basis == "tick_count":
            if current_tick_count is None:
                return False
            return job.run_after_timeline_index <= current_tick_count
        return job.run_after_timeline_index <= current_timeline_index

    def acknowledge(self, job_id: str) -> None:
        self._jobs.pop(job_id, None)

    def fail(self, job_id: str, error_message: str, *, requeue: bool = True) -> None:
        job = self._jobs.get(job_id)
        if job is None:
            return
        job.last_error = error_message
        job.status = "queued" if requeue else "failed"

    def queued_count(self) -> int:
        return sum(1 for job in self._jobs.values() if job.status == "queued")

    def serialize(self) -> List[dict]:
        return [job.to_record() for job in self._ordered_jobs()]

    def _ordered_jobs(self) -> List[BackgroundJob]:
        return sorted(
            self._jobs.values(),
            key=lambda job: (
                job.run_after_timeline_index,
                job.job_type,
                job.target_id,
                job.queue_key(),
            ),
        )


class BackgroundJobPlanner:
    def __init__(
        self,
        *,
        compression_interval_ticks: int = 15,
        arc_update_interval_ticks: int = 8,
        stagger_window: int = 5,
    ) -> None:
        self.compression_interval_ticks = compression_interval_ticks
        self.arc_update_interval_ticks = arc_update_interval_ticks
        self.stagger_window = stagger_window

    def plan_memory_jobs(
        self,
        *,
        agent_ids: List[str],
        current_tick_count: int,
    ) -> List[BackgroundJob]:
        jobs = []
        for agent_id in agent_ids:
            offset = self._stable_offset(agent_id)
            if current_tick_count % self.compression_interval_ticks != offset:
                continue
            jobs.append(
                BackgroundJob(
                    job_type="memory_compression",
                    target_id=agent_id,
                    run_after_timeline_index=current_tick_count,
                    reason="staggered compression window reached",
                    schedule_basis="tick_count",
                )
            )
        return jobs

    def plan_arc_job(self, *, current_tick_count: int) -> List[BackgroundJob]:
        if current_tick_count % self.arc_update_interval_ticks != 0:
            return []
        return [
            BackgroundJob(
                job_type="arc_update",
                target_id="world",
                run_after_timeline_index=current_tick_count,
                reason="arc update interval reached",
                schedule_basis="tick_count",
            )
        ]

    def plan_all(
        self,
        *,
        agent_ids: List[str],
        current_tick_count: int,
    ) -> List[BackgroundJob]:
        return self.plan_memory_jobs(
            agent_ids=agent_ids,
            current_tick_count=current_tick_count,
        ) + self.plan_arc_job(current_tick_count=current_tick_count)

    def _stable_offset(self, agent_id: str) -> int:
        return sum(ord(char) for char in agent_id) % self.stagger_window
