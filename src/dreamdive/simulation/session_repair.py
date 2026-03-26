from __future__ import annotations

import re
from typing import Dict, List

from dreamdive.simulation.background_jobs import BackgroundJob
from dreamdive.simulation.session import AgentRuntimeState, SimulationSessionState
from dreamdive.simulation.state_normalization import (
    normalize_current_state,
    normalize_simple_state_value,
)


_REPLAY_NORMALIZED_DIMENSIONS = {"emotional_state", "physical_state"}
_LEGACY_TICK_JOBS = {"arc_update", "memory_compression"}
# Legacy bridge description patterns (kept for session migration).
_BRIDGE_DESCRIPTION_PATTERN_EN = re.compile(
    r"^(?:Rumor reaches|News reaches) .+?: (?P<summary>.+)$"
)
_BRIDGE_DESCRIPTION_PATTERN_ZH = re.compile(
    r"^(?:消息传到|风声传到).+?耳中[：:]\s*(?P<summary>.+)$"
)


def repair_session_state(session: SimulationSessionState) -> SimulationSessionState:
    append_only_log = dict(session.append_only_log or {})
    world_snapshots = list(append_only_log.get("world_snapshots", []))
    state_changes = [
        _normalize_state_change_record(record)
        for record in append_only_log.get("state_changes", [])
    ]
    append_only_log["state_changes"] = state_changes

    normalized_agents: Dict[str, AgentRuntimeState] = {}
    for agent_id, runtime in session.agents.items():
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

    metadata = dict(session.metadata or {})
    language_guidance = str(metadata.get("language_guidance", ""))
    append_only_log["scheduled_world_events"] = [
        _normalize_bridge_event_record(record, language_guidance=language_guidance)
        for record in append_only_log.get("scheduled_world_events", [])
    ]
    pending_world_events = [
        _normalize_bridge_event_record(record, language_guidance=language_guidance)
        for record in session.pending_world_events
    ]
    stored_tick_count = int(metadata.get("tick_count", 0) or 0)
    derived_tick_count = len(world_snapshots)
    tick_count = max(stored_tick_count, derived_tick_count)
    metadata["tick_count"] = tick_count

    if not int(metadata.get("last_tick_minutes", 0) or 0):
        metadata["last_tick_minutes"] = int(
            (world_snapshots[-1].get("next_tick_size_minutes", 0) if world_snapshots else 0)
            or 0
        )

    if "last_arc_update_tick_count" in metadata:
        metadata["last_arc_update_tick_count"] = min(
            tick_count,
            max(0, int(metadata.get("last_arc_update_tick_count", 0) or 0)),
        )
    else:
        metadata["last_arc_update_tick_count"] = tick_count

    repaired_jobs, repaired_count = _repair_pending_background_jobs(
        session.pending_background_jobs,
        tick_count=tick_count,
    )
    metadata["background_queue_depth"] = sum(
        1 for job in repaired_jobs if str(job.get("status", "queued")) == "queued"
    )
    if repaired_count:
        metadata["repaired_legacy_background_jobs"] = (
            int(metadata.get("repaired_legacy_background_jobs", 0) or 0) + repaired_count
        )

    return session.model_copy(
        update={
            "agents": normalized_agents,
            "append_only_log": append_only_log,
            "pending_world_events": pending_world_events,
            "pending_background_jobs": repaired_jobs,
            "metadata": metadata,
        }
    )


def _normalize_state_change_record(record: dict) -> dict:
    normalized = dict(record)
    dimension = str(normalized.get("dimension", ""))
    if dimension not in _REPLAY_NORMALIZED_DIMENSIONS:
        return normalized
    normalized["from_value"] = normalize_simple_state_value(normalized.get("from_value"))
    normalized["to_value"] = normalize_simple_state_value(normalized.get("to_value"))
    return normalized


def _repair_pending_background_jobs(
    jobs: List[dict],
    *,
    tick_count: int,
) -> tuple[List[dict], int]:
    repaired: Dict[str, BackgroundJob] = {}
    repaired_count = 0
    needs_arc_refresh = False

    for record in jobs or []:
        if not isinstance(record, dict):
            continue
        job_type = str(record.get("job_type", ""))
        if "schedule_basis" not in record and job_type in _LEGACY_TICK_JOBS:
            repaired_count += 1
            if job_type == "arc_update":
                needs_arc_refresh = True
            continue
        job = BackgroundJob.from_record(record)
        existing = repaired.get(job.queue_key())
        if existing is None:
            repaired[job.queue_key()] = job
            continue
        existing.run_after_timeline_index = min(
            existing.run_after_timeline_index,
            job.run_after_timeline_index,
        )
        if existing.status == "failed" and job.status == "queued":
            existing.status = "queued"

    if needs_arc_refresh and not any(job.job_type == "arc_update" for job in repaired.values()):
        arc_job = BackgroundJob(
            job_type="arc_update",
            target_id="world",
            run_after_timeline_index=tick_count,
            reason="repaired legacy arc update schedule",
            schedule_basis="tick_count",
        )
        repaired[arc_job.queue_key()] = arc_job

    return [job.to_record() for job in repaired.values()], repaired_count


def _normalize_bridge_event_record(
    record: dict,
    *,
    language_guidance: str,
) -> dict:
    """Strip legacy per-character wrapper from bridge descriptions.

    Old format: "风声传到XXX耳中：actual summary" or "Rumor reaches XXX: actual summary"
    New format: just the summary itself.
    """
    normalized = dict(record)
    description = str(normalized.get("description", ""))
    for pattern in (_BRIDGE_DESCRIPTION_PATTERN_EN, _BRIDGE_DESCRIPTION_PATTERN_ZH):
        match = pattern.match(description)
        if match:
            normalized["description"] = match.group("summary").strip()
            break
    return normalized
