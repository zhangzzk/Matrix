from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Callable, Dict, List, Sequence

from dreamdive.schemas import (
    AgentContextPacket,
    BatchedTrajectoryProjectionPayload,
    CharacterSnapshot,
    GoalCollisionBatchPayload,
    PromptRequest,
    TrajectoryProjectionPayload,
    UnifiedProjectionPayload,
)
from dreamdive.simulation.context import ContextAssembler
from dreamdive.simulation.prompts import (
    build_batched_trajectory_projection_prompt,
    build_trajectory_projection_prompt,
    build_unified_projection_and_collision_prompt,
)


@dataclass
class TrajectoryProjector:
    llm_client: object
    horizon_multiplier: float = 4.0
    max_horizon_ticks: int = 50
    batch_size: int = 5
    context_assembler: ContextAssembler = ContextAssembler()

    def project(
        self,
        *,
        snapshot: CharacterSnapshot,
        current_time: str,
        tick_minutes: int,
        context_packet=None,
        language_guidance: str = "",
    ) -> TrajectoryProjectionPayload:
        horizon = self._estimate_horizon(snapshot, tick_minutes)
        packet = context_packet or self.context_assembler.assemble(
            snapshot=snapshot,
            scene_description="trajectory projection",
            scene_participants=[],
            time_label=current_time,
        )
        prompt = build_trajectory_projection_prompt(
            context_packet=packet,
            current_time=current_time,
            horizon=horizon,
            language_guidance=language_guidance,
        )
        return asyncio.run(
            self.llm_client.call_json(prompt, TrajectoryProjectionPayload)
        )

    def project_many(
        self,
        *,
        snapshots: Sequence[CharacterSnapshot],
        current_time: str,
        tick_minutes: int,
        context_packets: Dict[str, AgentContextPacket],
        language_guidance: str = "",
        progress_callback: Callable[[int, int, int], None] | None = None,
    ) -> Dict[str, TrajectoryProjectionPayload]:
        if not snapshots:
            return {}
        if len(snapshots) == 1:
            snapshot = snapshots[0]
            character_id = snapshot.identity.character_id
            if progress_callback is not None:
                progress_callback(1, 1, 1)
            return {
                character_id: self.project(
                    snapshot=snapshot,
                    current_time=current_time,
                    tick_minutes=tick_minutes,
                    context_packet=context_packets.get(character_id),
                    language_guidance=language_guidance,
                )
            }

        # Build all batch requests upfront.
        batches: List[tuple[int, List[CharacterSnapshot], PromptRequest]] = []
        for start in range(0, len(snapshots), self.batch_size):
            batch = snapshots[start : start + self.batch_size]
            requests: List[dict] = []
            for snapshot in batch:
                character_id = snapshot.identity.character_id
                packet = context_packets.get(character_id) or self.context_assembler.assemble(
                    snapshot=snapshot,
                    scene_description="trajectory projection",
                    scene_participants=[],
                    time_label=current_time,
                )
                requests.append(
                    {
                        "character_id": character_id,
                        "context": packet.model_dump(mode="json"),
                        "planning_horizon": self._estimate_horizon(snapshot, tick_minutes),
                    }
                )
            prompt = build_batched_trajectory_projection_prompt(
                requests=requests,
                current_time=current_time,
                language_guidance=language_guidance,
            )
            batches.append((start, batch, prompt))

        # Run batches concurrently using threads.
        projections: Dict[str, TrajectoryProjectionPayload] = {}

        def _run_batch(
            prompt: PromptRequest,
            client_clone,
        ) -> Dict[str, TrajectoryProjectionPayload]:
            payload = asyncio.run(
                client_clone.call_json(prompt, BatchedTrajectoryProjectionPayload)
            )
            return dict(payload.projections)

        with ThreadPoolExecutor(max_workers=min(len(batches), 4)) as executor:
            futures = {}
            for start, batch, prompt in batches:
                clone = self.llm_client.clone()
                future = executor.submit(_run_batch, prompt, clone)
                futures[future] = (start, batch, clone)

            for future in as_completed(futures):
                start, batch, clone = futures[future]
                if progress_callback is not None:
                    progress_callback(start + 1, start + len(batch), len(snapshots))
                self.llm_client.merge_records(clone)
                projections.update(future.result())

        return projections

    def project_and_detect_collisions(
        self,
        *,
        snapshots: Sequence[CharacterSnapshot],
        current_time: str,
        tick_minutes: int,
        context_packets: Dict[str, AgentContextPacket],
        world_state_summary: Dict[str, object],
        tension_level: float,
        language_guidance: str = "",
    ) -> tuple[Dict[str, TrajectoryProjectionPayload], GoalCollisionBatchPayload]:
        """Project trajectories and detect goal collisions in a single LLM call.

        Returns a tuple of (trajectories_dict, collision_payload) so that
        downstream code can consume them without changes.
        """
        if not snapshots:
            return {}, GoalCollisionBatchPayload()

        agent_contexts = []
        for snapshot in snapshots:
            character_id = snapshot.identity.character_id
            packet = context_packets.get(character_id) or self.context_assembler.assemble(
                snapshot=snapshot,
                scene_description="trajectory projection",
                scene_participants=[],
                time_label=current_time,
            )
            horizon = self._estimate_horizon(snapshot, tick_minutes)
            agent_contexts.append(
                {
                    "identity": packet.identity,
                    "current_state": packet.current_state,
                    "working_memory": packet.working_memory,
                    "relationships": packet.relationship_context,
                    "planning_horizon": horizon,
                }
            )

        prompt = build_unified_projection_and_collision_prompt(
            agent_contexts=agent_contexts,
            current_time=current_time,
            tension_level=tension_level,
            world_state_summary=world_state_summary,
            language_guidance=language_guidance,
        )

        payload = asyncio.run(
            self.llm_client.call_json(prompt, UnifiedProjectionPayload)
        )

        trajectories = dict(payload.trajectories)
        collision_payload = GoalCollisionBatchPayload(
            goal_tensions=payload.goal_tensions,
            solo_seeds=payload.solo_seeds,
            world_events=payload.world_events,
        )
        return trajectories, collision_payload

    def _estimate_horizon(self, snapshot: CharacterSnapshot, tick_minutes: int) -> str:
        horizon_ticks = 4
        if snapshot.inferred_state is not None:
            if snapshot.inferred_state.immediate_tension:
                horizon_ticks = 2
        horizon_ticks = min(self.max_horizon_ticks, max(1, horizon_ticks))
        horizon_minutes = int(horizon_ticks * tick_minutes * self.horizon_multiplier)
        return f"{horizon_ticks} ticks (~{horizon_minutes} minutes)"
