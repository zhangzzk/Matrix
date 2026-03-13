from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Optional

from dreamdive.schemas import CharacterSnapshot, GoalCollisionBatchPayload, TrajectoryProjectionPayload
from dreamdive.simulation.goal_collision import GoalCollisionDetector
from dreamdive.simulation.seeds import SimulationSeed


class SeedDetector:
    def __init__(self, goal_collision_detector: Optional[GoalCollisionDetector] = None) -> None:
        self.goal_collision_detector = goal_collision_detector

    def detect_spatial_collisions(
        self,
        snapshots: List[CharacterSnapshot],
    ) -> List[SimulationSeed]:
        grouped: dict[str, List[CharacterSnapshot]] = defaultdict(list)
        for snapshot in snapshots:
            location = str(snapshot.current_state.get("location") or "").strip()
            if location:
                grouped[location].append(snapshot)

        seeds: List[SimulationSeed] = []
        for location, present in grouped.items():
            if len(present) < 2:
                continue
            participants = [snapshot.identity.character_id for snapshot in present]
            description = "Agents converge at {}: {}".format(
                location,
                ", ".join(snapshot.identity.name for snapshot in present),
            )
            seeds.append(
                SimulationSeed(
                    seed_id="spatial_{}_{}".format(location, "_".join(sorted(participants))),
                    seed_type="spatial_collision",
                    participants=participants,
                    location=location,
                    description=description,
                    urgency=0.5,
                    conflict=self._estimate_group_conflict(present),
                    emotional_charge=self._estimate_group_emotion(present),
                    novelty=min(1.0, 0.2 * len(participants)),
                )
            )
        return seeds

    def detect_solo_seeds(
        self,
        snapshots: List[CharacterSnapshot],
        *,
        threshold: float = 0.6,
    ) -> List[SimulationSeed]:
        seeds: List[SimulationSeed] = []
        for snapshot in snapshots:
            activation = self._estimate_activation(snapshot)
            if activation < threshold:
                continue
            character_id = snapshot.identity.character_id
            top_goal = snapshot.goals[0].goal if snapshot.goals else "act on internal tension"
            seeds.append(
                SimulationSeed(
                    seed_id="solo_{}_{}".format(character_id, snapshot.replay_key.timeline_index),
                    seed_type="solo",
                    participants=[character_id],
                    location=str(snapshot.current_state.get("location") or ""),
                    description="{} pushes toward '{}'".format(
                        snapshot.identity.name,
                        top_goal,
                    ),
                    urgency=activation,
                    conflict=0.2,
                    emotional_charge=activation,
                    world_importance=0.1,
                    novelty=0.3,
                )
            )
        return seeds

    def detect_goal_collisions(
        self,
        *,
        current_time: str,
        snapshots: List[CharacterSnapshot],
        trajectories: Dict[str, TrajectoryProjectionPayload],
        contexts: Dict[str, object],
        world_state_summary: Dict[str, object],
        tension_level: float,
        language_guidance: str = "",
    ) -> GoalCollisionBatchPayload:
        if self.goal_collision_detector is None:
            return GoalCollisionBatchPayload()
        return self.goal_collision_detector.detect_goal_collisions(
            current_time=current_time,
            snapshots=snapshots,
            trajectories=trajectories,
            contexts=contexts,
            world_state_summary=world_state_summary,
            tension_level=tension_level,
            language_guidance=language_guidance,
        )

    @staticmethod
    def _estimate_group_conflict(snapshots: List[CharacterSnapshot]) -> float:
        if not snapshots:
            return 0.0
        relationship_tensions = []
        for snapshot in snapshots:
            for relationship in snapshot.relationships:
                relationship_tensions.append(abs(relationship.trust_delta))
        if not relationship_tensions:
            return 0.4
        return min(1.0, sum(relationship_tensions) / len(relationship_tensions) + 0.3)

    @staticmethod
    def _estimate_group_emotion(snapshots: List[CharacterSnapshot]) -> float:
        emotional_states = 0.0
        for snapshot in snapshots:
            if snapshot.inferred_state is not None:
                emotional_states += snapshot.inferred_state.emotional_state.confidence
            elif snapshot.current_state.get("emotional_state"):
                emotional_states += 0.4
        return min(1.0, emotional_states / max(1, len(snapshots)))

    @staticmethod
    def _estimate_activation(snapshot: CharacterSnapshot) -> float:
        score = 0.0
        if snapshot.goals:
            score += 0.35
        if snapshot.inferred_state is not None:
            score += max(0.0, min(1.0, snapshot.inferred_state.emotional_state.confidence)) * 0.35
            if snapshot.inferred_state.immediate_tension:
                score += 0.2
            if snapshot.inferred_state.unspoken_subtext:
                score += 0.1
        elif snapshot.current_state.get("emotional_state"):
            score += 0.2
        return min(1.0, score)
