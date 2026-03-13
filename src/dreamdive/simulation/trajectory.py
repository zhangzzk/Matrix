from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Callable, Dict, List, Sequence

from dreamdive.schemas import (
    AgentContextPacket,
    BatchedTrajectoryProjectionPayload,
    CharacterSnapshot,
    TrajectoryProjectionPayload,
)
from dreamdive.simulation.context import ContextAssembler
from dreamdive.simulation.prompts import (
    build_batched_trajectory_projection_prompt,
    build_trajectory_projection_prompt,
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

        projections: Dict[str, TrajectoryProjectionPayload] = {}
        for start in range(0, len(snapshots), self.batch_size):
            batch = snapshots[start : start + self.batch_size]
            if progress_callback is not None:
                progress_callback(start + 1, start + len(batch), len(snapshots))
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
            payload = asyncio.run(
                self.llm_client.call_json(prompt, BatchedTrajectoryProjectionPayload)
            )
            projections.update(dict(payload.projections))
        return projections

    def _estimate_horizon(self, snapshot: CharacterSnapshot, tick_minutes: int) -> str:
        horizon_ticks = 4
        if snapshot.inferred_state is not None:
            confidence = snapshot.inferred_state.emotional_state.confidence
            if confidence >= 0.8 and snapshot.inferred_state.immediate_tension:
                horizon_ticks = 2
            elif confidence <= 0.4:
                horizon_ticks = 5
        horizon_ticks = min(self.max_horizon_ticks, max(1, horizon_ticks))
        horizon_minutes = int(horizon_ticks * tick_minutes * self.horizon_multiplier)
        return f"{horizon_ticks} ticks (~{horizon_minutes} minutes)"
