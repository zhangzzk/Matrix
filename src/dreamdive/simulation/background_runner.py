from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Set

from dreamdive.debug import DebugSession
from dreamdive.memory.prompts import (
    build_arc_update_prompt,
    build_memory_compression_prompt,
)
from dreamdive.schemas import (
    EpisodicMemory,
    MemoryCompressionPayload,
    NarrativeArcState,
    NarrativeArcUpdatePayload,
    ReplayKey,
)
from dreamdive.simulation.background_queue_backend import (
    BackgroundQueueBackend,
    SessionBackgroundQueueBackend,
)
from dreamdive.simulation.language_validation import require_language_guidance
from dreamdive.simulation.session import SimulationSessionState
from dreamdive.simulation.state_normalization import normalize_current_state


def _drain_llm_issues(llm_client) -> List[dict]:
    drain = getattr(llm_client, "drain_issue_records", None)
    if callable(drain):
        return list(drain())
    return []


def _stamp_llm_issues(
    issues: List[dict],
    *,
    tick_label: str,
    timeline_index: int,
    phase: str,
) -> List[dict]:
    return [
        {
            **dict(issue),
            "tick_label": tick_label,
            "timeline_index": timeline_index,
            "phase": phase,
        }
        for issue in issues
    ]


class BackgroundMaintenanceRunner:
    def __init__(
        self,
        llm_client,
        *,
        compression_age_threshold: int = 15,
        high_salience_threshold: float = 0.7,
        discard_threshold: float = 0.2,
        debug_session: DebugSession | None = None,
        max_workers: int = 4,
    ) -> None:
        self.llm_client = llm_client
        self.compression_age_threshold = compression_age_threshold
        self.high_salience_threshold = high_salience_threshold
        self.discard_threshold = discard_threshold
        self.debug_session = debug_session
        self.max_workers = max(1, max_workers)

    def run_due_jobs(
        self,
        session: SimulationSessionState,
        *,
        max_jobs: int | None = None,
        queue_backend: BackgroundQueueBackend | None = None,
        job_types: Set[str] | None = None,
    ) -> SimulationSessionState:
        _drain_llm_issues(self.llm_client)
        updated = session.model_copy(deep=True)
        normalized_agents = {}
        for agent_id, runtime in updated.agents.items():
            normalized_agents[agent_id] = runtime.model_copy(
                update={
                    "snapshot": runtime.snapshot.model_copy(
                        update={
                            "current_state": normalize_current_state(
                                runtime.snapshot.current_state,
                                runtime.snapshot.inferred_state,
                            )
                        }
                    )
                }
            )
        updated = updated.model_copy(update={"agents": normalized_agents})
        queue = queue_backend or SessionBackgroundQueueBackend(updated.pending_background_jobs)
        recent_errors = []
        claimed_jobs = queue.claim_due_jobs(
            current_timeline_index=updated.current_timeline_index,
            current_tick_count=int(updated.metadata.get("tick_count", 0) or 0),
            limit=max_jobs,
            job_types=job_types,
        )
        if self.debug_session is not None:
            self.debug_session.event(
                "background.claimed",
                timeline_index=updated.current_timeline_index,
                claimed_job_count=len(claimed_jobs),
                queue_depth_before=queue.queued_count() + len(claimed_jobs),
            )
        # Partition jobs: memory_compression jobs (per-character, independent) vs arc_update (shared state).
        compression_jobs = [j for j in claimed_jobs if j.job_type == "memory_compression"]
        arc_jobs = [j for j in claimed_jobs if j.job_type == "arc_update"]
        other_jobs = [j for j in claimed_jobs if j.job_type not in ("memory_compression", "arc_update")]

        # Run memory compression jobs in parallel — each targets a different character.
        if len(compression_jobs) > 1 and self.max_workers > 1:
            def _run_compression(job, client_clone, session_snapshot):
                runner = BackgroundMaintenanceRunner(
                    client_clone,
                    compression_age_threshold=self.compression_age_threshold,
                    high_salience_threshold=self.high_salience_threshold,
                    discard_threshold=self.discard_threshold,
                    max_workers=1,
                )
                return runner._run_memory_compression(session_snapshot, job.target_id)

            with ThreadPoolExecutor(max_workers=min(len(compression_jobs), self.max_workers)) as executor:
                future_to_job = {}
                clones = []
                for job in compression_jobs:
                    clone = self.llm_client.clone()
                    clones.append((job, clone))
                    future_to_job[executor.submit(
                        _run_compression, job, clone, updated,
                    )] = (job, clone)

                for future in as_completed(future_to_job):
                    job, clone = future_to_job[future]
                    self.llm_client.merge_records(clone)
                    try:
                        result = future.result()
                        # Merge the memory changes from this compression into updated session.
                        updated = self._merge_compression_result(updated, result, job.target_id)
                        queue.acknowledge(job.queue_key())
                        if self.debug_session is not None:
                            self.debug_session.event(
                                "background.job.done",
                                job_id=job.queue_key(),
                                job_type=job.job_type,
                                target_id=job.target_id,
                            )
                    except Exception as exc:
                        queue.fail(job.queue_key(), str(exc), requeue=True)
                        recent_errors.append(
                            {
                                "job_id": job.queue_key(),
                                "job_type": job.job_type,
                                "target_id": job.target_id,
                                "error": str(exc),
                                "attempts": job.attempts,
                            }
                        )
                        if self.debug_session is not None:
                            self.debug_session.event(
                                "background.job.failed",
                                job_id=job.queue_key(),
                                job_type=job.job_type,
                                target_id=job.target_id,
                                error=str(exc),
                            )
        else:
            for job in compression_jobs:
                try:
                    updated = self._run_memory_compression(updated, job.target_id)
                    queue.acknowledge(job.queue_key())
                    if self.debug_session is not None:
                        self.debug_session.event(
                            "background.job.done",
                            job_id=job.queue_key(),
                            job_type=job.job_type,
                            target_id=job.target_id,
                        )
                except Exception as exc:
                    queue.fail(job.queue_key(), str(exc), requeue=True)
                    recent_errors.append(
                        {
                            "job_id": job.queue_key(),
                            "job_type": job.job_type,
                            "target_id": job.target_id,
                            "error": str(exc),
                            "attempts": job.attempts,
                        }
                    )
                    if self.debug_session is not None:
                        self.debug_session.event(
                            "background.job.failed",
                            job_id=job.queue_key(),
                            job_type=job.job_type,
                            target_id=job.target_id,
                            error=str(exc),
                        )

        # Arc updates and other jobs run sequentially (they touch shared state).
        for job in [*arc_jobs, *other_jobs]:
            try:
                if job.job_type == "arc_update":
                    updated = self._run_arc_update(updated)
                queue.acknowledge(job.queue_key())
                if self.debug_session is not None:
                    self.debug_session.event(
                        "background.job.done",
                        job_id=job.queue_key(),
                        job_type=job.job_type,
                        target_id=job.target_id,
                    )
            except Exception as exc:
                queue.fail(job.queue_key(), str(exc), requeue=True)
                recent_errors.append(
                    {
                        "job_id": job.queue_key(),
                        "job_type": job.job_type,
                        "target_id": job.target_id,
                        "error": str(exc),
                        "attempts": job.attempts,
                    }
                )
                if self.debug_session is not None:
                    self.debug_session.event(
                        "background.job.failed",
                        job_id=job.queue_key(),
                        job_type=job.job_type,
                        target_id=job.target_id,
                        error=str(exc),
                    )

        prior_llm_issues = list((updated.append_only_log or {}).get("llm_issues", []))
        background_llm_issues = _stamp_llm_issues(
            _drain_llm_issues(self.llm_client),
            tick_label=updated.current_tick_label,
            timeline_index=updated.current_timeline_index,
            phase="background",
        )
        append_only_log = dict(updated.append_only_log or {})
        append_only_log["llm_issues"] = prior_llm_issues + background_llm_issues
        metadata = {
            **updated.metadata,
            "recent_background_job_errors": recent_errors,
            "background_queue_depth": queue.queued_count(),
            "llm_issue_count": len(prior_llm_issues) + len(background_llm_issues),
            "last_background_llm_issue_count": len(background_llm_issues),
            "critical_llm_issue_count": sum(
                1
                for issue in [*prior_llm_issues, *background_llm_issues]
                if str(issue.get("severity", "")) == "critical"
            ),
            "last_background_critical_llm_issue_count": sum(
                1
                for issue in background_llm_issues
                if str(issue.get("severity", "")) == "critical"
            ),
            "recent_llm_issues": (prior_llm_issues + background_llm_issues)[-5:],
        }
        return updated.model_copy(
            update={
                "pending_background_jobs": queue.snapshot(),
                "append_only_log": append_only_log,
                "metadata": metadata,
            }
        )

    @staticmethod
    def _merge_compression_result(
        target: SimulationSessionState,
        source: SimulationSessionState,
        character_id: str,
    ) -> SimulationSessionState:
        """Merge memory compression results for a single character back into the target session."""
        source_log = dict(source.append_only_log or {})
        target_log = dict(target.append_only_log or {})

        # Merge episodic memories: keep target's base, add new compressed entries from source.
        target_event_ids = {
            item.get("event_id") for item in target_log.get("episodic_memories", [])
        }
        merged_memories = list(target_log.get("episodic_memories", []))
        for item in source_log.get("episodic_memories", []):
            if item.get("event_id") not in target_event_ids:
                merged_memories.append(item)
        target_log["episodic_memories"] = merged_memories

        # Merge maintenance log entries from source.
        target_maintenance = list(target_log.get("maintenance_log", []))
        source_maintenance = list(source_log.get("maintenance_log", []))
        existing_count = len(target_maintenance)
        if len(source_maintenance) > existing_count:
            target_maintenance.extend(source_maintenance[existing_count:])
        target_log["maintenance_log"] = target_maintenance

        # Merge suppressed memory IDs for this character.
        target_meta = dict(target.metadata)
        source_meta = dict(source.metadata)
        target_suppressed = dict(target_meta.get("suppressed_memory_ids_by_agent", {}))
        source_suppressed = dict(source_meta.get("suppressed_memory_ids_by_agent", {}))
        if character_id in source_suppressed:
            target_suppressed[character_id] = source_suppressed[character_id]
        target_meta["suppressed_memory_ids_by_agent"] = target_suppressed

        return target.model_copy(
            update={
                "append_only_log": target_log,
                "metadata": target_meta,
            }
        )

    def _run_memory_compression(
        self,
        session: SimulationSessionState,
        character_id: str,
    ) -> SimulationSessionState:
        runtime = session.agents.get(character_id)
        if runtime is None:
            return session

        suppressed_by_agent = {
            agent_id: list(event_ids)
            for agent_id, event_ids in dict(
                session.metadata.get("suppressed_memory_ids_by_agent", {})
            ).items()
        }
        suppressed = set(suppressed_by_agent.get(character_id, []))
        memories = [
            EpisodicMemory.model_validate(item)
            for item in session.append_only_log.get("episodic_memories", [])
            if item.get("character_id") == character_id
            and item.get("event_id") not in suppressed
        ]
        old_entries = [
            memory
            for memory in memories
            if not memory.pinned
            and not memory.compressed
            and (session.current_timeline_index - memory.replay_key.timeline_index)
            >= self.compression_age_threshold
        ]
        if not old_entries:
            return session

        pinned_entries = [memory for memory in memories if memory.pinned]
        identity = runtime.snapshot.identity
        language_guidance = require_language_guidance(
            str(session.metadata.get("language_guidance", "")),
            context="memory compression",
        )
        prompt = build_memory_compression_prompt(
            character_name=identity.name,
            primary_drive=identity.desires[0] if identity.desires else "",
            values=identity.values,
            top_concerns=[goal.description for goal in runtime.snapshot.goals[:3]],
            episodic_entries=old_entries,
            pinned_entries=pinned_entries,
            age_threshold=self.compression_age_threshold,
            high_salience_threshold=self.high_salience_threshold,
            discard_threshold=self.discard_threshold,
            language_guidance=language_guidance,
        )
        response = asyncio.run(
            self.llm_client.call_json(prompt, MemoryCompressionPayload)
        )

        memory_index = {memory.event_id or "": memory for memory in memories}
        append_only_log = dict(session.append_only_log)
        episodic_log = list(append_only_log.get("episodic_memories", []))
        next_entries = list(episodic_log)
        maintenance_log = list(append_only_log.get("maintenance_log", []))

        compressed_event_ids: List[str] = []
        for index, summary in enumerate(response.compressed_summaries):
            source_memories = [
                memory_index[event_id]
                for event_id in summary.source_event_ids
                if event_id in memory_index
            ]
            participants = sorted(
                {
                    participant
                    for memory in source_memories
                    for participant in memory.participants
                }
            )
            location = source_memories[-1].location if source_memories else ""
            compressed_memory = EpisodicMemory(
                character_id=character_id,
                replay_key=ReplayKey(
                    tick=session.current_tick_label,
                    timeline_index=session.current_timeline_index,
                ),
                event_id="compressed_{}_{}_{}".format(
                    character_id,
                    session.current_timeline_index,
                    index + 1,
                ),
                participants=participants,
                location=location,
                summary=summary.summary,
                emotional_tag=summary.emotional_tone,
                salience=max(
                    [memory.salience for memory in source_memories] or [0.35]
                ),
                compressed=True,
            )
            next_entries.append(compressed_memory.model_dump(mode="json"))
            compressed_event_ids.append(compressed_memory.event_id or "")
            suppressed.update(summary.source_event_ids)

        suppressed.update(response.discarded_event_ids)
        suppressed_by_agent[character_id] = sorted(suppressed)
        append_only_log["episodic_memories"] = next_entries
        maintenance_log.append(
            {
                "job_type": "memory_compression",
                "target_id": character_id,
                "timeline_index": session.current_timeline_index,
                "suppressed_event_ids": sorted(
                    set(response.discarded_event_ids).union(
                        {
                            event_id
                            for summary in response.compressed_summaries
                            for event_id in summary.source_event_ids
                        }
                    )
                ),
                "compressed_event_ids": compressed_event_ids,
            }
        )
        append_only_log["maintenance_log"] = maintenance_log
        metadata = {
            **session.metadata,
            "suppressed_memory_ids_by_agent": suppressed_by_agent,
        }
        return session.model_copy(update={"append_only_log": append_only_log, "metadata": metadata})

    def _run_arc_update(self, session: SimulationSessionState) -> SimulationSessionState:
        last_update = int(session.metadata.get("last_arc_update_timeline_index", 0))
        last_tick_count = int(session.metadata.get("last_arc_update_tick_count", 0) or 0)
        current_tick_count = int(session.metadata.get("tick_count", 0) or 0)
        recent_events = [
            item
            for item in session.append_only_log.get("event_log", [])
            if int(item.get("timeline_index", 0)) > last_update
        ]
        if not recent_events:
            metadata = {
                **session.metadata,
                "last_arc_update_timeline_index": session.current_timeline_index,
                "last_arc_update_tick_count": current_tick_count,
            }
            return session.model_copy(update={"metadata": metadata})

        agent_state_summary = [
            {
                "agent_id": agent_id,
                "goal": runtime.snapshot.goals[0].description if runtime.snapshot.goals else "",
                "emotional_state": runtime.snapshot.current_state.get("emotional_state", ""),
                "location": runtime.snapshot.current_state.get("location", ""),
                "needs_reprojection": runtime.needs_reprojection,
            }
            for agent_id, runtime in sorted(session.agents.items())
        ]
        language_guidance = require_language_guidance(
            str(session.metadata.get("language_guidance", "")),
            context="arc update",
        )
        prompt = build_arc_update_prompt(
            story_context=str(session.metadata.get("story_context", session.source_path)),
            authorial_intent=str(session.metadata.get("authorial_intent", "")),
            central_tension=str(session.metadata.get("central_tension", "")),
            current_arc_state=session.arc_state,
            ticks_elapsed=max(0, current_tick_count - last_tick_count),
            recent_event_log=recent_events,
            agent_state_summary=agent_state_summary,
            language_guidance=language_guidance,
        )
        response = asyncio.run(
            self.llm_client.call_json(prompt, NarrativeArcUpdatePayload)
        )

        unresolved_threads = [
            (thread.description or thread.thread_id)
            for thread in response.unresolved_threads
            if (thread.description or thread.thread_id)
        ]
        arc_state = NarrativeArcState(
            current_phase=response.phase,
            tension_level=response.tension_level,
            unresolved_threads=unresolved_threads,
            approaching_climax=(
                response.phase in {"crisis", "climax"}
                or response.tension_level >= 0.75
            ),
        )

        pending_world_events = list(session.pending_world_events)
        scheduled_world_events = list((session.append_only_log or {}).get("scheduled_world_events", []))
        maintenance_log = list((session.append_only_log or {}).get("maintenance_log", []))
        injected_event_ids: List[str] = []
        if response.narrative_drift.drifting and response.narrative_drift.suggested_correction:
            affected = []
            for node in response.approaching_nodes:
                affected.extend(node.agents_involved)
            affected = sorted(set(affected)) or sorted(session.agents.keys())
            drift_event = {
                "event_id": "arc_drift_{}".format(session.current_timeline_index),
                "trigger_timeline_index": session.current_timeline_index + 60,
                "description": response.narrative_drift.suggested_correction,
                "affected_agents": affected,
                "urgency": "medium",
                "location": "",
                "cascades": [],
            }
            pending_world_events.append(drift_event)
            if drift_event["event_id"] not in {item.get("event_id") for item in scheduled_world_events}:
                scheduled_world_events.append(drift_event)
                injected_event_ids.append(str(drift_event["event_id"]))
        maintenance_log.append(
            {
                "job_type": "arc_update",
                "target_id": "world",
                "timeline_index": session.current_timeline_index,
                "arc_state": arc_state.model_dump(mode="json"),
                "injected_world_event_ids": injected_event_ids,
            }
        )

        metadata = {
            **session.metadata,
            "last_arc_update_timeline_index": session.current_timeline_index,
            "last_arc_update_tick_count": current_tick_count,
            "last_arc_update_reason": response.tension_reason,
        }
        return session.model_copy(
            update={
                "arc_state": arc_state,
                "pending_world_events": pending_world_events,
                "append_only_log": {
                    **session.append_only_log,
                    "scheduled_world_events": scheduled_world_events,
                    "maintenance_log": maintenance_log,
                },
                "metadata": metadata,
            }
        )
