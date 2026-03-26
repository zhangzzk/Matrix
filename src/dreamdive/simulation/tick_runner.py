from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor, as_completed
import datetime
import logging
import time
from dataclasses import dataclass, field
from typing import Callable, Counter, Dict, Iterable, List, Optional

from dreamdive.db.queries import (
    EntityRepresentationRepository,
    EpisodicMemoryRepository,
    EventLogRepository,
    GoalStackRepository,
    RelationshipRepository,
    StateChangeLogRepository,
    WorldSnapshotRepository,
)
from dreamdive.memory.retrieval import build_memory_query_text, embed_text
from dreamdive.schemas import (
    AgentContextPacket,
    CharacterSnapshot,
    EpisodicMemory,
    GoalCollisionBatchPayload,
    NarrativeArcState,
    ReplayKey,
    TrajectoryProjectionPayload,
    WorldSnapshot,
)
from dreamdive.simulation.background_jobs import BackgroundJob, BackgroundJobPlanner
from dreamdive.simulation.context import ContextAssembler
from dreamdive.simulation.event_simulator import EventSimulator, SpotlightResult
from dreamdive.simulation.goal_collision import GoalCollisionDetector
from dreamdive.simulation.memory_writer import MemoryWriter
from dreamdive.simulation.salience import rank_seeds
from dreamdive.simulation.seed_detector import SeedDetector
from dreamdive.simulation.seeds import SimulationSeed
from dreamdive.simulation.state_updater import EventStateUpdater, StateUpdateResult
from dreamdive.simulation.state_normalization import normalize_current_state
from dreamdive.simulation.trajectory import TrajectoryProjector
from dreamdive.simulation.world_events import WorldEventScheduler
from dreamdive.simulation.world_manager import WorldManager


@dataclass
class AgentRuntime:
    snapshot: CharacterSnapshot
    needs_reprojection: bool = True
    trajectory: Optional[TrajectoryProjectionPayload] = None
    voice_samples: List[str] = field(default_factory=list)
    world_entities: List[Dict[str, object]] = field(default_factory=list)


@dataclass
class TickEventFailure:
    event_id: str
    seed_id: str
    seed_type: str
    stage: str
    error_message: str


@dataclass
class PreparedAgentUpdate:
    runtime: AgentRuntime
    update: StateUpdateResult
    memory: EpisodicMemory


@dataclass
class TickExecutionResult:
    replay_key: ReplayKey
    tick_minutes: int
    ranked_seeds: List[SimulationSeed]
    agent_runtimes: Dict[str, AgentRuntime]
    world_snapshot: WorldSnapshot
    scheduled_jobs: List[BackgroundJob]
    active_agent_scores: Dict[str, float] = field(default_factory=dict)
    location_threads: List[Dict[str, object]] = field(default_factory=list)
    bridge_events: List[Dict[str, object]] = field(default_factory=list)
    woken_agents: Dict[str, str] = field(default_factory=dict)
    event_failures: List[TickEventFailure] = field(default_factory=list)
    tick_cooldown_remaining: int = 0
    max_observed_salience: float = 0.0


class SimulationTickRunner:
    def __init__(
        self,
        *,
        world_manager: WorldManager,
        seed_detector: SeedDetector,
        trajectory_projector: TrajectoryProjector,
        event_simulator: EventSimulator,
        state_updater: EventStateUpdater,
        state_repo: StateChangeLogRepository,
        goal_repo: GoalStackRepository,
        relationship_repo: RelationshipRepository,
        memory_repo: EpisodicMemoryRepository,
        entity_repo: Optional[EntityRepresentationRepository] = None,
        world_snapshot_repo: WorldSnapshotRepository,
        event_log_repo: EventLogRepository,
        context_assembler: Optional[ContextAssembler] = None,
        memory_writer: Optional[MemoryWriter] = None,
        world_event_scheduler: Optional[WorldEventScheduler] = None,
        background_job_planner: Optional[BackgroundJobPlanner] = None,
        retrieved_memory_candidates: int = 20,
        max_spotlight_beats: int = 8,
        max_foreground_beats: int = 4,
        write_retry_attempts: int = 3,
        write_retry_base_delay_seconds: float = 0.05,
        sleep_fn: Optional[Callable[[float], None]] = None,
    ) -> None:
        self.world_manager = world_manager
        self.seed_detector = seed_detector
        self.trajectory_projector = trajectory_projector
        self.event_simulator = event_simulator
        self.state_updater = state_updater
        self.state_repo = state_repo
        self.goal_repo = goal_repo
        self.relationship_repo = relationship_repo
        self.memory_repo = memory_repo
        self.entity_repo = entity_repo
        self.world_snapshot_repo = world_snapshot_repo
        self.event_log_repo = event_log_repo
        self.context_assembler = context_assembler or ContextAssembler()
        self.memory_writer = memory_writer or MemoryWriter()
        self.world_event_scheduler = world_event_scheduler
        self.background_job_planner = background_job_planner or BackgroundJobPlanner()
        self.retrieved_memory_candidates = max(1, retrieved_memory_candidates)
        self.max_spotlight_beats = max(1, max_spotlight_beats)
        self.max_foreground_beats = max(1, max_foreground_beats)
        self.write_retry_attempts = max(1, write_retry_attempts)
        self.write_retry_base_delay_seconds = max(0.0, write_retry_base_delay_seconds)
        self.sleep_fn = sleep_fn or time.sleep

    def run_tick(
        self,
        *,
        current_tick_label: str,
        current_timeline_index: int,
        current_tick_count: int = 0,
        agent_runtimes: List[AgentRuntime],
        arc_state: NarrativeArcState,
        world_seeds: Optional[List[SimulationSeed]] = None,
        writing_style_note: str = "",
        language_guidance: str = "",
        cooldown_ticks_remaining: int = 0,
        prior_max_salience: float = 0.0,
        progress_callback: Optional[Callable[[Dict[str, object]], None]] = None,
    ) -> TickExecutionResult:
        snapshots = [runtime.snapshot for runtime in agent_runtimes]
        preliminary_detected = self.seed_detector.detect_spatial_collisions(snapshots)
        if world_seeds:
            preliminary_detected.extend(world_seeds)
        preliminary_ranked = rank_seeds(preliminary_detected, narrative_tension=arc_state.tension_level)
        tick_minutes = self.world_manager.compute_tick_size(
            preliminary_ranked,
            arc_state,
            cooldown_ticks_remaining=cooldown_ticks_remaining,
            prior_max_salience=prior_max_salience,
        )
        if self.world_event_scheduler is not None:
            next_event_delta = self.world_event_scheduler.next_trigger_delta(current_timeline_index)
            if next_event_delta is not None:
                tick_minutes = self._clamp_tick_to_next_event(
                    tick_minutes=tick_minutes,
                    next_event_delta=next_event_delta,
                )
        replay_key = ReplayKey(
            tick=current_tick_label,
            timeline_index=current_timeline_index + tick_minutes,
        )
        runtime_by_id = {
            runtime.snapshot.identity.character_id: runtime
            for runtime in agent_runtimes
        }
        contexts: Dict[str, AgentContextPacket] = {}
        active_agent_scores = self.world_manager.select_active_agents(
            [runtime.snapshot for runtime in agent_runtimes],
            current_timeline_index=current_timeline_index,
        )
        active_agent_ids = set(active_agent_scores.keys())
        high_priority_agent_ids, low_priority_agent_ids = self.world_manager.partition_projection_agents(
            active_agent_scores
        )
        event_failures: List[TickEventFailure] = []
        self._emit_progress(
            progress_callback,
            stage="context",
            message=(
                f"assembling context for {len(active_agent_ids)} active agent"
                f"{'s' if len(active_agent_ids) != 1 else ''}"
            ),
            active_agents=len(active_agent_ids),
            high_priority_agents=len(high_priority_agent_ids),
            low_priority_agents=len(low_priority_agent_ids),
        )
        self._emit_progress(progress_callback, stage="assembly", message=f"assembling context for {len(active_agent_ids)} active agents")

        t0 = time.time()
        contexts: Dict[str, AgentContextPacket] = {}

        def _assemble_agent_context(runtime) -> tuple[str, AgentContextPacket, list[Dict[str, object]]]:
            character_id = runtime.snapshot.identity.character_id
            query_text = build_memory_query_text(
                scene_description="trajectory projection",
                scene_participants=[],
                location=str(runtime.snapshot.current_state.get("location", "")),
                current_state=runtime.snapshot.current_state,
            )
            # Recent chronological memories for temporal continuity
            recent_memories = self.memory_repo.list_recent_for_character(
                character_id,
                limit=5,
                timeline_index=current_timeline_index,
            )
            recent_event_summaries = [m.summary for m in recent_memories]
            context_packet = self.context_assembler.assemble(
                snapshot=runtime.snapshot,
                scene_description="trajectory projection",
                scene_participants=[],
                time_label=current_tick_label,
                world_entities=self._entity_candidates_for_context(
                    character_id=character_id,
                    query_text=query_text,
                    fallback_entities=runtime.world_entities,
                ),
                episodic_memories=self._memory_candidates_for_context(
                    character_id=character_id,
                    current_timeline_index=current_timeline_index,
                    query_text=query_text,
                ),
                recent_events=recent_event_summaries,
            )
            return character_id, context_packet, list(context_packet.world_entities)

        active_runtimes = [r for r in agent_runtimes if r.snapshot.identity.character_id in active_agent_ids]
        with ThreadPoolExecutor(max_workers=max(1, min(len(active_runtimes), 8))) as executor:
            future_to_char = {executor.submit(_assemble_agent_context, r): r for r in active_runtimes}
            for future in as_completed(future_to_char):
                try:
                    character_id, context_packet, new_entities = future.result()
                    contexts[character_id] = context_packet
                    runtime_by_id[character_id].world_entities = new_entities
                except Exception:
                    pass
        
        self._emit_progress(progress_callback, stage="projection", message=f"starting unified projection + collision detection for {len(active_agent_ids)} agents")

        active_snapshots = [
            runtime.snapshot
            for runtime in agent_runtimes
            if runtime.snapshot.identity.character_id in active_agent_ids
        ]
        try:
            unified_trajectories, collision_batch = self.trajectory_projector.project_and_detect_collisions(
                snapshots=active_snapshots,
                current_time=current_tick_label,
                tick_minutes=tick_minutes,
                context_packets=contexts,
                world_state_summary={
                    "locations": {
                        runtime.snapshot.identity.character_id: runtime.snapshot.current_state.get("location", "")
                        for runtime in agent_runtimes
                    },
                    "unresolved_threads": arc_state.unresolved_threads,
                },
                tension_level=arc_state.tension_level,
                language_guidance=language_guidance,
            )
            for runtime in agent_runtimes:
                character_id = runtime.snapshot.identity.character_id
                trajectory = unified_trajectories.get(character_id)
                if trajectory is not None:
                    runtime.trajectory = trajectory
                    runtime.needs_reprojection = False
        except Exception as exc:
            collision_batch = GoalCollisionBatchPayload()
            event_failures.append(
                TickEventFailure(
                    event_id="",
                    seed_id="unified_projection_and_collision",
                    seed_type="unified_projection",
                    stage="unified_projection_and_collision",
                    error_message=str(exc),
                )
            )

        self._emit_progress(
            progress_callback,
            stage="seed_detection",
            message="detecting collisions and narrative seeds",
            active_agents=len(active_snapshots),
        )
        detected = []
        detected.extend(self.seed_detector.detect_spatial_collisions(snapshots))
        detected.extend(GoalCollisionDetector.tensions_to_seeds(collision_batch))
        llm_solo_ids = {
            seed.participants[0]
            for seed in detected
            if seed.seed_type == "solo" and seed.participants
        }
        detected.extend(
            [
                seed
                for seed in self.seed_detector.detect_solo_seeds(active_snapshots)
                if not seed.participants or seed.participants[0] not in llm_solo_ids
            ]
        )
        if self.world_event_scheduler is not None:
            detected.extend(
                self.world_event_scheduler.consume_due_events(
                    current_timeline_index=current_timeline_index,
                    dt_minutes=tick_minutes,
                )
            )
        if world_seeds:
            detected.extend(world_seeds)
        ranked = rank_seeds(detected, narrative_tension=arc_state.tension_level)
        ranked = self.world_manager.filter_below_minimum_salience(ranked)
        location_threads = self.world_manager.build_location_threads(ranked)
        queued_seeds = self.world_manager.interleave_location_threads(location_threads)
        self._emit_progress(
            progress_callback,
            stage="event_simulation",
            message=(
                f"simulating {len(queued_seeds)} queued event"
                f"{'s' if len(queued_seeds) != 1 else ''}"
            ),
            queued_events=len(queued_seeds),
        )
        max_observed_salience = max((seed.salience for seed in ranked), default=0.0)
        next_tick_cooldown = self.world_manager.next_tick_cooldown(
            current_cooldown_ticks=cooldown_ticks_remaining,
            observed_max_salience=max_observed_salience,
        )

        bridge_events: List[Dict[str, object]] = []
        woken_agents: Dict[str, str] = {}
        
        # Pre-compute events concurrently
        precomputed_outcomes = {}
        simulation_tasks = []
        for index, seed in list(enumerate(queued_seeds)):
            mode = self.world_manager.classify_mode(seed.salience)
            participants = [
                runtime_by_id[agent_id].snapshot
                for agent_id in seed.participants
                if agent_id in runtime_by_id
            ]
            simulation_tasks.append((index, seed, participants, mode))
        
        if simulation_tasks:
            self._emit_progress(
                progress_callback,
                stage="event_simulation",
                message=f"simulating {len(simulation_tasks)} events concurrently",
                active_agents=len(simulation_tasks)
            )
            def _compute_event(task_seed, task_participants, client_clone, mode):
                clone_sim = EventSimulator(
                    llm_client=client_clone,
                    context_assembler=self.event_simulator.context_assembler,
                )
                if mode == "background":
                    return clone_sim.simulate_background(
                        seed=task_seed,
                        snapshots=task_participants,
                        current_time=current_tick_label,
                        writing_style_note=writing_style_note,
                        language_guidance=language_guidance,
                    )
                else:
                    return clone_sim.simulate_spotlight(
                        seed=task_seed,
                        snapshots=task_participants,
                        narrative_phase=arc_state.current_phase,
                        tension_level=arc_state.tension_level,
                        relevant_threads=arc_state.unresolved_threads,
                        voice_samples_by_agent={
                            runtime.snapshot.identity.character_id: runtime.voice_samples
                            for runtime in agent_runtimes
                        },
                        world_entities_by_agent={},  # Entity system disabled.
                        max_beats=self.max_spotlight_beats if mode == "spotlight" else self.max_foreground_beats,
                        language_guidance=language_guidance,
                    )

            with ThreadPoolExecutor(max_workers=min(len(simulation_tasks), 10)) as executor:
                futures_list = []
                for index, task_seed, task_participants, task_mode in simulation_tasks:
                    clone = self.event_simulator.llm_client.clone()
                    futures_list.append(
                        (executor.submit(_compute_event, task_seed, task_participants, clone, task_mode), index, task_seed, clone)
                    )

                for future, index, task_seed, clone in futures_list:
                    self.event_simulator.llm_client.merge_records(clone)
                    try:
                        precomputed_outcomes[task_seed.seed_id] = future.result()
                    except Exception as exc:
                        print(f"DEBUG EVENT FAILED: {task_seed.seed_id} - {exc}")
                        precomputed_outcomes[task_seed.seed_id] = exc
        
        for index, seed in enumerate(queued_seeds):
            self._emit_progress(
                progress_callback,
                stage="event_simulation",
                message=(
                    f"event {index + 1}/{len(queued_seeds)}"
                    f" · {seed.seed_type}"
                    f" · {seed.location or 'unplaced'}"
                ),
                event_index=index + 1,
                event_total=len(queued_seeds),
                seed_type=seed.seed_type,
                location=seed.location,
            )
            event_id = f"evt_{replay_key.timeline_index}_{index + 1:03d}"
            participants = [
                runtime_by_id[agent_id].snapshot
                for agent_id in seed.participants
                if agent_id in runtime_by_id
            ]
            mode = self.world_manager.classify_mode(seed.salience)
            outcome_summary = ""
            preparation_stage = "event_simulation"

            try:
                precomputed = precomputed_outcomes.get(seed.seed_id)
                if isinstance(precomputed, Exception):
                    raise precomputed
                outcome = precomputed

                if mode == "background":
                    outcome_summary = outcome.narrative_summary
                    preparation_stage = "state_update"
                    prepared_updates = self._prepare_background_outcome(
                        event_id=event_id,
                        replay_key=replay_key,
                        seed=seed,
                        outcome=outcome,
                        runtime_by_id=runtime_by_id,
                        language_guidance=language_guidance,
                    )
                else:
                    outcome_summary = outcome.resolution.scene_outcome
                    preparation_stage = "state_update"
                    prepared_updates = self._prepare_spotlight_outcome(
                        event_id=event_id,
                        replay_key=replay_key,
                        seed=seed,
                        outcome=outcome,
                        runtime_by_id=runtime_by_id,
                        language_guidance=language_guidance,
                    )
            except Exception as exc:
                event_failures.append(
                    TickEventFailure(
                        event_id=event_id,
                        seed_id=seed.seed_id,
                        seed_type=seed.seed_type,
                        stage=preparation_stage,
                        error_message=str(exc),
                    )
                )
                continue

            self._commit_prepared_updates(prepared_updates)
            self._write_with_retry(
                lambda: self.event_log_repo.append(
                    event_id=event_id,
                    replay_key=replay_key,
                    seed_type=seed.seed_type,
                    location=seed.location,
                    participants=seed.participants,
                    description=seed.description,
                    salience=seed.salience,
                    outcome_summary=outcome_summary,
                    resolution_mode=mode,
                )
            )
            if self.world_event_scheduler is not None:
                planned_bridge_events = self.world_manager.plan_bridge_events(
                    [runtime.snapshot for runtime in agent_runtimes],
                    source_event_id=event_id,
                    participants=seed.participants,
                    source_location=seed.location,
                    salience=seed.salience,
                    outcome_summary=outcome_summary,
                    replay_timeline_index=replay_key.timeline_index,
                    language_guidance=language_guidance,
                )
                for bridge_event in planned_bridge_events:
                    self.world_event_scheduler.schedule(bridge_event)
                    bridge_events.append(
                        {
                            "event_id": bridge_event.event_id,
                            "trigger_timeline_index": bridge_event.trigger_timeline_index,
                            "location": bridge_event.location,
                            "affected_agents": list(bridge_event.affected_agents),
                            "urgency": bridge_event.urgency,
                        }
                    )
            wake_reasons = self.world_manager.identify_woken_agents(
                [runtime.snapshot for runtime in agent_runtimes],
                participants=seed.participants,
                location=seed.location,
                salience=seed.salience,
            )
            for character_id, reason in wake_reasons.items():
                runtime = runtime_by_id.get(character_id)
                if runtime is None:
                    continue
                if character_id not in seed.participants:
                    runtime.needs_reprojection = True
                    runtime.trajectory = None
                woken_agents[character_id] = reason

        self._emit_progress(
            progress_callback,
            stage="finalizing",
            message="writing world snapshot and scheduling maintenance",
        )
        world_snapshot = WorldSnapshot(
            replay_key=replay_key,
            agent_locations={
                runtime.snapshot.identity.character_id: str(
                    runtime.snapshot.current_state.get("location", "")
                )
                for runtime in agent_runtimes
            },
            narrative_arc=arc_state,
            unresolved_threads=arc_state.unresolved_threads,
            next_tick_size_minutes=tick_minutes,
        )
        self._write_with_retry(lambda: self.world_snapshot_repo.append(world_snapshot))
        scheduled_jobs = self.background_job_planner.plan_all(
            agent_ids=[runtime.snapshot.identity.character_id for runtime in agent_runtimes],
            current_tick_count=current_tick_count + 1,
        )

        return TickExecutionResult(
            replay_key=replay_key,
            tick_minutes=tick_minutes,
            ranked_seeds=queued_seeds,
            agent_runtimes=runtime_by_id,
            world_snapshot=world_snapshot,
            scheduled_jobs=scheduled_jobs,
            active_agent_scores=active_agent_scores,
            location_threads=[
                {
                    "thread_id": thread.thread_id,
                    "location": thread.location,
                    "participant_count": len(thread.participants),
                    "seed_count": len(thread.seeds),
                    "max_salience": thread.max_salience,
                    "is_bridge": thread.is_bridge,
                }
                for thread in location_threads
            ],
            bridge_events=bridge_events,
            woken_agents=woken_agents,
            event_failures=event_failures,
            tick_cooldown_remaining=next_tick_cooldown,
            max_observed_salience=max_observed_salience,
        )

    def _project_targets(
        self,
        *,
        targets: List[AgentRuntime],
        contexts: Dict[str, AgentContextPacket],
        current_tick_label: str,
        tick_minutes: int,
        language_guidance: str,
        event_failures: List[TickEventFailure],
        batch_threshold: int,
        progress_callback: Optional[Callable[[Dict[str, object]], None]],
        group_label: str,
    ) -> None:
        if not targets:
            return

        unresolved_targets = list(targets)
        if len(unresolved_targets) > batch_threshold:
            try:
                batched = self.trajectory_projector.project_many(
                    snapshots=[runtime.snapshot for runtime in unresolved_targets],
                    current_time=current_tick_label,
                    tick_minutes=tick_minutes,
                    context_packets=contexts,
                    language_guidance=language_guidance,
                    progress_callback=lambda start, end, total: self._emit_progress(
                        progress_callback,
                        stage="projection",
                        message=f"projecting {group_label} agents {start}-{end}/{total}",
                        group=group_label,
                        projected_start=start,
                        projected_end=end,
                        projected_total=total,
                    ),
                )
            except Exception:
                batched = {}
            else:
                for runtime in unresolved_targets:
                    character_id = runtime.snapshot.identity.character_id
                    trajectory = batched.get(character_id)
                    if trajectory is None:
                        continue
                    runtime.trajectory = trajectory
                    runtime.needs_reprojection = False

            unresolved_targets = [
                runtime
                for runtime in unresolved_targets
                if runtime.needs_reprojection or runtime.trajectory is None
            ]

        for runtime in unresolved_targets:
            character_id = runtime.snapshot.identity.character_id
            self._emit_progress(
                progress_callback,
                stage="projection",
                message=f"projecting {group_label} agent {character_id}",
                group=group_label,
                character_id=character_id,
            )
            try:
                runtime.trajectory = self.trajectory_projector.project(
                    snapshot=runtime.snapshot,
                    current_time=current_tick_label,
                    tick_minutes=tick_minutes,
                    context_packet=contexts[character_id],
                    language_guidance=language_guidance,
                )
                runtime.needs_reprojection = False
            except Exception as exc:
                runtime.trajectory = None
                runtime.needs_reprojection = True
                event_failures.append(
                    self._runtime_failure(
                        stage="trajectory_projection",
                        character_id=character_id,
                        error_message=str(exc),
                    )
                )

    @staticmethod
    def _emit_progress(
        progress_callback: Optional[Callable[[Dict[str, object]], None]],
        **event: object,
    ) -> None:
        if progress_callback is None:
            return
        try:
            progress_callback(event)
        except Exception:
            return

    @staticmethod
    def _runtime_failure(
        *,
        stage: str,
        character_id: str,
        error_message: str,
    ) -> TickEventFailure:
        return TickEventFailure(
            event_id="",
            seed_id=character_id,
            seed_type="agent_runtime",
            stage=stage,
            error_message=error_message,
        )

    def _clamp_tick_to_next_event(
        self,
        *,
        tick_minutes: int,
        next_event_delta: int,
    ) -> int:
        if next_event_delta <= 0:
            return min(tick_minutes, self.world_manager.spotlight_min_minutes)
        tick_floor = min(tick_minutes, self.world_manager.spotlight_min_minutes)
        return max(tick_floor, min(tick_minutes, next_event_delta))

    def _memory_candidates_for_context(
        self,
        *,
        character_id: str,
        current_timeline_index: int,
        query_text: str,
    ) -> List[EpisodicMemory]:
        query_embedding = embed_text(query_text)
        candidates = list(
            self.memory_repo.search_semantic_for_character(
                character_id,
                query_embedding=query_embedding,
                limit=self.retrieved_memory_candidates,
                timeline_index=current_timeline_index,
            )
        )
        pinned = list(
            self.memory_repo.list_pinned_for_character(
                character_id,
                timeline_index=current_timeline_index,
            )
        )
        merged: List[EpisodicMemory] = []
        seen_keys = set()
        for memory in [*pinned, *candidates]:
            key = (
                memory.event_id or "",
                memory.replay_key.timeline_index,
                memory.summary,
            )
            if key in seen_keys:
                continue
            merged.append(memory)
            seen_keys.add(key)
        return merged

    def _entity_candidates_for_context(
        self,
        *,
        character_id: str,
        query_text: str,
        fallback_entities: List[Dict[str, object]],
        limit: int = 5,
    ) -> List[Dict[str, object]]:
        # Entity system disabled — return empty list immediately.
        return []

    def _prepare_background_outcome(
        self,
        *,
        event_id: str,
        replay_key: ReplayKey,
        seed: SimulationSeed,
        outcome,
        runtime_by_id: Dict[str, AgentRuntime],
        language_guidance: str = "",
    ) -> List[PreparedAgentUpdate]:
        valid_outcomes = [
            ao for ao in outcome.outcomes if ao.agent_id in runtime_by_id
        ]
        if len(valid_outcomes) <= 1:
            # Single agent — no parallelization needed.
            prepared: List[PreparedAgentUpdate] = []
            for agent_outcome in valid_outcomes:
                runtime = runtime_by_id[agent_outcome.agent_id]
                update = self.state_updater.update_after_event(
                    snapshot=runtime.snapshot,
                    event_id=event_id,
                    replay_key=replay_key,
                    event_outcome_from_agent_perspective=outcome.narrative_summary,
                    new_knowledge=[agent_outcome.new_knowledge] if agent_outcome.new_knowledge else [],
                    language_guidance=language_guidance,
                )
                prepared.append(
                    PreparedAgentUpdate(
                        runtime=runtime,
                        update=update,
                        memory=self.memory_writer.build_memory(
                            character_id=runtime.snapshot.identity.character_id,
                            replay_key=replay_key,
                            event_id=event_id,
                            participants=seed.participants,
                            location=seed.location,
                            summary=outcome.narrative_summary,
                            emotional_tag=update.raw_update.emotional_delta.dominant_now,
                            salience=seed.salience,
                            pinned=modeled_pinned(seed),
                        ),
                    )
                )
            return prepared

        # Multiple agents — parallelize state updates (each is an independent LLM call).
        def _update_agent(agent_outcome, client_clone):
            runtime = runtime_by_id[agent_outcome.agent_id]
            updater = EventStateUpdater(client_clone)
            update = updater.update_after_event(
                snapshot=runtime.snapshot,
                event_id=event_id,
                replay_key=replay_key,
                event_outcome_from_agent_perspective=outcome.narrative_summary,
                new_knowledge=[agent_outcome.new_knowledge] if agent_outcome.new_knowledge else [],
                language_guidance=language_guidance,
            )
            return PreparedAgentUpdate(
                runtime=runtime,
                update=update,
                memory=self.memory_writer.build_memory(
                    character_id=runtime.snapshot.identity.character_id,
                    replay_key=replay_key,
                    event_id=event_id,
                    participants=seed.participants,
                    location=seed.location,
                    summary=outcome.narrative_summary,
                    emotional_tag=update.raw_update.emotional_delta.dominant_now,
                    salience=seed.salience,
                    pinned=modeled_pinned(seed),
                ),
            )

        prepared = []
        with ThreadPoolExecutor(max_workers=min(len(valid_outcomes), 8)) as pool:
            futures = []
            for agent_outcome in valid_outcomes:
                clone = self.state_updater.llm_client.clone()
                futures.append((pool.submit(_update_agent, agent_outcome, clone), clone))
            for future, clone in futures:
                self.state_updater.llm_client.merge_records(clone)
                prepared.append(future.result())
        return prepared

    def _prepare_spotlight_outcome(
        self,
        *,
        event_id: str,
        replay_key: ReplayKey,
        seed: SimulationSeed,
        outcome: SpotlightResult,
        runtime_by_id: Dict[str, AgentRuntime],
        language_guidance: str = "",
    ) -> List[PreparedAgentUpdate]:
        public_summary = " ".join(
            turn.external.get("dialogue", "") or turn.external.get("physical_action", "")
            for turn in outcome.transcript
        ).strip() or outcome.resolution.scene_outcome

        participating_agents = [
            (agent_id, runtime)
            for agent_id, runtime in runtime_by_id.items()
            if agent_id in outcome.private_state_by_agent
        ]

        def _build_perspective(agent_id):
            private_bits = outcome.private_state_by_agent[agent_id]
            if private_bits:
                return (
                    f"{public_summary} Internal shift: {private_bits[-1].get('goal_update', '')}"
                ).strip()
            return public_summary

        if len(participating_agents) <= 1:
            prepared: List[PreparedAgentUpdate] = []
            for agent_id, runtime in participating_agents:
                perspective = _build_perspective(agent_id)
                update = self.state_updater.update_after_event(
                    snapshot=runtime.snapshot,
                    event_id=event_id,
                    replay_key=replay_key,
                    event_outcome_from_agent_perspective=perspective,
                    new_knowledge=[],
                    language_guidance=language_guidance,
                )
                prepared.append(
                    PreparedAgentUpdate(
                        runtime=runtime,
                        update=update,
                        memory=self.memory_writer.build_memory(
                            character_id=agent_id,
                            replay_key=replay_key,
                            event_id=event_id,
                            participants=seed.participants,
                            location=seed.location,
                            summary=perspective,
                            emotional_tag=update.raw_update.emotional_delta.dominant_now,
                            salience=seed.salience,
                            pinned=modeled_pinned(seed),
                        ),
                    )
                )
            return prepared

        # Multiple agents — parallelize state updates.
        def _update_agent(agent_id, runtime, client_clone):
            perspective = _build_perspective(agent_id)
            updater = EventStateUpdater(client_clone)
            update = updater.update_after_event(
                snapshot=runtime.snapshot,
                event_id=event_id,
                replay_key=replay_key,
                event_outcome_from_agent_perspective=perspective,
                new_knowledge=[],
                language_guidance=language_guidance,
            )
            return PreparedAgentUpdate(
                runtime=runtime,
                update=update,
                memory=self.memory_writer.build_memory(
                    character_id=agent_id,
                    replay_key=replay_key,
                    event_id=event_id,
                    participants=seed.participants,
                    location=seed.location,
                    summary=perspective,
                    emotional_tag=update.raw_update.emotional_delta.dominant_now,
                    salience=seed.salience,
                    pinned=modeled_pinned(seed),
                ),
            )

        prepared = []
        with ThreadPoolExecutor(max_workers=min(len(participating_agents), 8)) as pool:
            futures = []
            for agent_id, runtime in participating_agents:
                clone = self.state_updater.llm_client.clone()
                futures.append((pool.submit(_update_agent, agent_id, runtime, clone), clone))
            for future, clone in futures:
                self.state_updater.llm_client.merge_records(clone)
                prepared.append(future.result())
        return prepared

    def _commit_prepared_updates(self, prepared_updates: List[PreparedAgentUpdate]) -> None:
        for prepared in prepared_updates:
            self._persist_update(
                runtime=prepared.runtime,
                update=prepared.update,
                memory=prepared.memory,
            )

    def _write_with_retry(self, operation):
        last_error = None
        for attempt in range(self.write_retry_attempts):
            try:
                return operation()
            except Exception as exc:
                last_error = exc
                if attempt >= self.write_retry_attempts - 1:
                    raise
                delay = self.write_retry_base_delay_seconds * (2 ** attempt)
                if delay > 0:
                    self.sleep_fn(delay)
        raise RuntimeError("Write operation failed") from last_error

    def _persist_update(
        self,
        *,
        runtime: AgentRuntime,
        update: StateUpdateResult,
        memory: EpisodicMemory,
    ) -> None:
        for entry in update.state_changes:
            self._write_with_retry(lambda entry=entry: self.state_repo.append(entry))
        self._write_with_retry(lambda: self.goal_repo.append(update.goal_stack))
        self._write_with_retry(lambda: self.memory_repo.append(memory))
        for entry in update.relationship_changes:
            self._write_with_retry(lambda entry=entry: self.relationship_repo.append(entry))

        runtime.needs_reprojection = update.needs_reprojection
        if update.needs_reprojection:
            runtime.trajectory = None

        new_state = dict(runtime.snapshot.current_state)
        for entry in update.state_changes:
            new_state[entry.dimension] = entry.to_value
        new_state = normalize_current_state(new_state, None)
        runtime.snapshot = runtime.snapshot.model_copy(
            update={
                "replay_key": update.goal_stack.replay_key,
                "current_state": new_state,
                "goals": update.goal_stack.goals,
                "inferred_state": None,
            }
        )


def modeled_pinned(seed: SimulationSeed) -> bool:
    return seed.salience >= 0.8
