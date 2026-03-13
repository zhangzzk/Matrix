from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

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

        for runtime in agent_runtimes:
            character_id = runtime.snapshot.identity.character_id
            if character_id not in active_agent_ids:
                continue
            query_text = build_memory_query_text(
                scene_description="tick planning",
                scene_participants=[],
                location=str(runtime.snapshot.current_state.get("location", "")),
                current_state=dict(runtime.snapshot.current_state),
            )
            context_packet = self.context_assembler.assemble(
                snapshot=runtime.snapshot,
                scene_description="tick planning",
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
            )
            contexts[character_id] = context_packet
            runtime.world_entities = list(context_packet.world_entities)

        high_priority_targets = [
            runtime
            for runtime in agent_runtimes
            if runtime.snapshot.identity.character_id in high_priority_agent_ids
            and (runtime.needs_reprojection or runtime.trajectory is None)
        ]
        high_priority_batch_threshold = max(
            5,
            int(getattr(self.trajectory_projector, "batch_size", 5)),
        )
        self._project_targets(
            targets=high_priority_targets,
            contexts=contexts,
            current_tick_label=current_tick_label,
            tick_minutes=tick_minutes,
            language_guidance=language_guidance,
            event_failures=event_failures,
            batch_threshold=high_priority_batch_threshold,
            progress_callback=progress_callback,
            group_label="high-priority",
        )

        low_priority_targets = [
            runtime
            for runtime in agent_runtimes
            if runtime.snapshot.identity.character_id in low_priority_agent_ids
            and (runtime.needs_reprojection or runtime.trajectory is None)
        ]
        self._project_targets(
            targets=low_priority_targets,
            contexts=contexts,
            current_tick_label=current_tick_label,
            tick_minutes=tick_minutes,
            language_guidance=language_guidance,
            event_failures=event_failures,
            batch_threshold=1,
            progress_callback=progress_callback,
            group_label="low-priority",
        )

        active_snapshots = [
            runtime.snapshot
            for runtime in agent_runtimes
            if runtime.snapshot.identity.character_id in active_agent_ids
        ]
        self._emit_progress(
            progress_callback,
            stage="seed_detection",
            message="detecting collisions and narrative seeds",
            active_agents=len(active_snapshots),
        )
        detected = []
        detected.extend(self.seed_detector.detect_spatial_collisions(snapshots))
        try:
            collision_batch = self.seed_detector.detect_goal_collisions(
                current_time=current_tick_label,
                snapshots=active_snapshots,
                trajectories={
                    runtime.snapshot.identity.character_id: runtime.trajectory
                    for runtime in agent_runtimes
                    if runtime.snapshot.identity.character_id in active_agent_ids
                    and runtime.trajectory is not None
                },
                contexts={
                    character_id: context
                    for character_id, context in contexts.items()
                    if character_id in active_agent_ids
                },
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
        except Exception as exc:
            collision_batch = GoalCollisionBatchPayload()
            event_failures.append(
                TickEventFailure(
                    event_id="",
                    seed_id="goal_collision_detection",
                    seed_type="goal_collision",
                    stage="goal_collision_detection",
                    error_message=str(exc),
                )
            )
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
                if mode == "background":
                    outcome = self.event_simulator.simulate_background(
                        seed=seed,
                        snapshots=participants,
                        current_time=current_tick_label,
                        writing_style_note=writing_style_note,
                        language_guidance=language_guidance,
                    )
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
                    outcome = self.event_simulator.simulate_spotlight(
                        seed=seed,
                        snapshots=participants,
                        narrative_phase=arc_state.current_phase,
                        tension_level=arc_state.tension_level,
                        relevant_threads=arc_state.unresolved_threads,
                        voice_samples_by_agent={
                            runtime.snapshot.identity.character_id: runtime.voice_samples
                            for runtime in agent_runtimes
                        },
                        world_entities_by_agent={
                            runtime.snapshot.identity.character_id: runtime.world_entities
                            for runtime in agent_runtimes
                        },
                        max_beats=8 if mode == "spotlight" else 4,
                        language_guidance=language_guidance,
                    )
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
        if self.entity_repo is None:
            return list(fallback_entities)
        candidates = self.entity_repo.search_for_agent(
            character_id,
            query_embedding=embed_text(query_text),
            limit=limit,
        )
        if candidates:
            return [entity.model_dump(mode="json") for entity in candidates]
        return list(fallback_entities)

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
        prepared: List[PreparedAgentUpdate] = []
        for agent_outcome in outcome.outcomes:
            runtime = runtime_by_id.get(agent_outcome.agent_id)
            if runtime is None:
                continue
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
                    ),
                )
            )
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
        prepared: List[PreparedAgentUpdate] = []
        for agent_id, runtime in runtime_by_id.items():
            if agent_id not in outcome.private_state_by_agent:
                continue
            private_bits = outcome.private_state_by_agent[agent_id]
            perspective = public_summary
            if private_bits:
                perspective = (
                    f"{public_summary} Internal shift: {private_bits[-1].get('goal_update', '')}"
                ).strip()
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
