from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Protocol, Sequence, Set

from dreamdive.simulation.background_jobs import BackgroundJob, BackgroundJobQueue


class BackgroundQueueBackend(Protocol):
    def enqueue_many(self, jobs: Iterable[BackgroundJob | dict]) -> List[BackgroundJob]:
        ...

    def claim_due_jobs(
        self,
        *,
        current_timeline_index: int,
        current_tick_count: int | None = None,
        limit: int | None = None,
        job_types: Set[str] | None = None,
    ) -> List[BackgroundJob]:
        ...

    def acknowledge(self, job_id: str) -> None:
        ...

    def fail(self, job_id: str, error_message: str, *, requeue: bool = True) -> None:
        ...

    def queued_count(self) -> int:
        ...

    def snapshot(self) -> List[dict]:
        ...


class SessionBackgroundQueueBackend:
    def __init__(self, jobs: Sequence[BackgroundJob | dict] | None = None) -> None:
        self._queue = BackgroundJobQueue(jobs)

    def enqueue_many(self, jobs: Iterable[BackgroundJob | dict]) -> List[BackgroundJob]:
        return self._queue.enqueue_many(jobs)

    def claim_due_jobs(
        self,
        *,
        current_timeline_index: int,
        current_tick_count: int | None = None,
        limit: int | None = None,
        job_types: Set[str] | None = None,
    ) -> List[BackgroundJob]:
        return self._queue.claim_due_jobs(
            current_timeline_index=current_timeline_index,
            current_tick_count=current_tick_count,
            limit=limit,
            job_types=job_types,
        )

    def acknowledge(self, job_id: str) -> None:
        self._queue.acknowledge(job_id)

    def fail(self, job_id: str, error_message: str, *, requeue: bool = True) -> None:
        self._queue.fail(job_id, error_message, requeue=requeue)

    def queued_count(self) -> int:
        return self._queue.queued_count()

    def snapshot(self) -> List[dict]:
        return self._queue.serialize()


@dataclass(frozen=True)
class PgBossDispatchMessage:
    queue_name: str
    singleton_key: str
    payload: dict
    start_after_timeline_index: int


class PgBossJobCodec:
    def __init__(self, *, queue_name: str = "dreamdive-background") -> None:
        self.queue_name = queue_name

    def encode(self, job: BackgroundJob | dict) -> PgBossDispatchMessage:
        item = job if isinstance(job, BackgroundJob) else BackgroundJob.from_record(job)
        record = item.to_record()
        return PgBossDispatchMessage(
            queue_name=self.queue_name,
            singleton_key=item.queue_key(),
            payload=record,
            start_after_timeline_index=item.run_after_timeline_index,
        )

    def encode_many(self, jobs: Iterable[BackgroundJob | dict]) -> List[PgBossDispatchMessage]:
        return [self.encode(job) for job in jobs]

    def decode(self, message: PgBossDispatchMessage | dict) -> BackgroundJob:
        if isinstance(message, dict):
            dispatch = PgBossDispatchMessage(
                queue_name=str(message.get("queue_name", self.queue_name)),
                singleton_key=str(message.get("singleton_key", "")),
                payload=dict(message.get("payload", {})),
                start_after_timeline_index=int(message.get("start_after_timeline_index", 0)),
            )
        else:
            dispatch = message
        record = {
            **dispatch.payload,
            "job_id": dispatch.singleton_key or dispatch.payload.get("job_id", ""),
            "run_after_timeline_index": dispatch.start_after_timeline_index,
        }
        return BackgroundJob.from_record(record)
