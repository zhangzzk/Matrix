from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Dict, Iterable, Optional, Set

from dreamdive.schemas import CharacterSnapshot, NarrativeArcState
from dreamdive.simulation.seeds import SimulationSeed
from dreamdive.simulation.world_events import ScheduledWorldEvent


@dataclass
class LocationThreadPlan:
    thread_id: str
    location: str
    seeds: list[SimulationSeed] = field(default_factory=list)
    participants: list[str] = field(default_factory=list)
    max_salience: float = 0.0
    is_bridge: bool = False


class WorldManager:
    def __init__(
        self,
        *,
        spotlight_min_minutes: int = 1,
        spotlight_max_minutes: int = 30,
        foreground_min_minutes: int = 60,
        foreground_max_minutes: int = 480,
        background_min_minutes: int = 1440,
        background_max_minutes: int = 10080,
        spotlight_threshold: float = 0.8,
        foreground_threshold: float = 0.4,
        activation_threshold: float = 0.45,
        batched_projection_threshold: float = 0.7,
        tick_recovery_ticks: int = 2,
        salience_carryover_decay: float = 0.75,
    ) -> None:
        self.spotlight_min_minutes = spotlight_min_minutes
        self.spotlight_max_minutes = spotlight_max_minutes
        self.foreground_min_minutes = foreground_min_minutes
        self.foreground_max_minutes = foreground_max_minutes
        self.background_min_minutes = background_min_minutes
        self.background_max_minutes = background_max_minutes
        self.spotlight_threshold = spotlight_threshold
        self.foreground_threshold = foreground_threshold
        self.activation_threshold = activation_threshold
        self.batched_projection_threshold = batched_projection_threshold
        self.tick_recovery_ticks = max(0, tick_recovery_ticks)
        self.salience_carryover_decay = max(0.0, min(1.0, salience_carryover_decay))

    def compute_tick_size(
        self,
        seeds: Iterable[SimulationSeed],
        arc_state: NarrativeArcState,
        *,
        cooldown_ticks_remaining: int = 0,
        prior_max_salience: float = 0.0,
    ) -> int:
        max_salience = max((seed.salience for seed in seeds), default=0.0)
        carryover_salience = (
            max(0.0, min(1.0, prior_max_salience)) * self.salience_carryover_decay
        )
        adjusted_salience = max(
            max_salience,
            arc_state.tension_level * 0.8,
            carryover_salience,
        )
        tick_minutes = self._tick_minutes_from_salience(adjusted_salience)

        if arc_state.approaching_climax:
            tick_minutes = min(self.background_min_minutes, tick_minutes)

        if cooldown_ticks_remaining > 0 and max_salience < self.foreground_threshold:
            return min(
                self.foreground_max_minutes,
                max(self.foreground_min_minutes, tick_minutes),
            )
        return tick_minutes

    def _tick_minutes_from_salience(self, salience: float) -> int:
        min_tick = max(1, self.spotlight_min_minutes)
        max_tick = max(min_tick, self.background_max_minutes)
        clamped_salience = max(0.0, min(1.0, salience))
        raw_minutes = max_tick * ((min_tick / max_tick) ** clamped_salience)
        snapped = self._snap_tick_minutes(raw_minutes)
        return min(max_tick, max(min_tick, snapped))

    def _snap_tick_minutes(self, raw_minutes: float) -> int:
        if raw_minutes <= self.spotlight_max_minutes:
            step = 1
        elif raw_minutes <= self.foreground_max_minutes:
            step = 5
        elif raw_minutes <= self.background_min_minutes:
            step = 15
        else:
            step = 60
        return max(step, int(step * round(raw_minutes / step)))

    def next_tick_cooldown(
        self,
        *,
        current_cooldown_ticks: int,
        observed_max_salience: float,
    ) -> int:
        if observed_max_salience >= self.spotlight_threshold:
            return self.tick_recovery_ticks
        return max(0, current_cooldown_ticks - 1)

    def classify_mode(self, salience: float) -> str:
        if salience >= self.spotlight_threshold:
            return "spotlight"
        if salience >= self.foreground_threshold:
            return "foreground"
        return "background"

    def compute_activation_scores(
        self,
        snapshots: Iterable[CharacterSnapshot],
        *,
        current_timeline_index: int,
    ) -> dict[str, float]:
        snapshot_list = list(snapshots)
        location_counts = Counter(
            str(snapshot.current_state.get("location") or "").strip()
            for snapshot in snapshot_list
            if str(snapshot.current_state.get("location") or "").strip()
        )
        crowded_locations = {
            location
            for location, count in location_counts.items()
            if count > 1
        }
        return {
            snapshot.identity.character_id: self.compute_activation_score(
                snapshot,
                current_timeline_index=current_timeline_index,
                crowded_locations=crowded_locations,
            )
            for snapshot in snapshot_list
        }

    def compute_activation_score(
        self,
        snapshot: CharacterSnapshot,
        *,
        current_timeline_index: int,
        crowded_locations: Optional[Set[str]] = None,
    ) -> float:
        score = 0.0
        if snapshot.goals:
            top_goal = sorted(snapshot.goals, key=lambda goal: goal.priority)[0]
            score += 0.2
            horizon = str(getattr(top_goal.time_horizon, "value", top_goal.time_horizon)).strip().lower()
            if "immediate" in horizon:
                score += 0.2
            elif "today" in horizon:
                score += 0.15
            elif "this_week" in horizon:
                score += 0.1
            else:
                score += 0.05

        if snapshot.inferred_state is not None:
            score += max(0.0, min(1.0, snapshot.inferred_state.emotional_state.confidence)) * 0.25
            if snapshot.inferred_state.immediate_tension:
                score += 0.15
            if snapshot.inferred_state.unspoken_subtext:
                score += 0.05
        elif snapshot.current_state.get("emotional_state"):
            score += 0.15

        last_involved_gap = max(0, current_timeline_index - snapshot.replay_key.timeline_index)
        score += min(0.15, last_involved_gap / 480.0)

        location = str(snapshot.current_state.get("location") or "").strip()
        if location and crowded_locations and location in crowded_locations:
            score += 0.2

        return min(1.0, score)

    def select_active_agents(
        self,
        snapshots: Iterable[CharacterSnapshot],
        *,
        current_timeline_index: int,
        threshold: Optional[float] = None,
    ) -> dict[str, float]:
        activation_scores = self.compute_activation_scores(
            snapshots,
            current_timeline_index=current_timeline_index,
        )
        cutoff = self.activation_threshold if threshold is None else threshold
        return {
            character_id: score
            for character_id, score in activation_scores.items()
            if score >= cutoff
        }

    def partition_projection_agents(
        self,
        activation_scores: dict[str, float],
    ) -> tuple[list[str], list[str]]:
        high_priority = []
        low_priority = []
        for character_id, score in activation_scores.items():
            if score >= self.batched_projection_threshold:
                high_priority.append(character_id)
            else:
                low_priority.append(character_id)
        return high_priority, low_priority

    def identify_woken_agents(
        self,
        snapshots: Iterable[CharacterSnapshot],
        *,
        participants: Iterable[str],
        location: str,
        salience: float,
        social_trust_threshold: float = 0.25,
    ) -> Dict[str, str]:
        participant_ids = {participant for participant in participants if participant}
        if not participant_ids and not location:
            return {}

        snapshot_list = list(snapshots)
        wake_reasons: Dict[str, str] = {}
        normalized_location = location.strip().lower()

        for snapshot in snapshot_list:
            character_id = snapshot.identity.character_id
            if character_id in participant_ids:
                wake_reasons[character_id] = "event_participant"
                continue
            snapshot_location = str(snapshot.current_state.get("location") or "").strip().lower()
            if normalized_location and snapshot_location and snapshot_location == normalized_location:
                wake_reasons[character_id] = "same_location"

        if salience < self.foreground_threshold:
            return wake_reasons

        snapshot_by_id = {
            snapshot.identity.character_id: snapshot
            for snapshot in snapshot_list
        }
        for snapshot in snapshot_list:
            character_id = snapshot.identity.character_id
            if character_id in wake_reasons:
                continue
            for participant_id in participant_ids:
                participant_snapshot = snapshot_by_id.get(participant_id)
                if self._has_social_connection(
                    source=snapshot,
                    target_id=participant_id,
                    reverse_source=participant_snapshot,
                    reverse_target_id=character_id,
                    trust_threshold=social_trust_threshold,
                ):
                    wake_reasons[character_id] = "social_graph"
                    break

        return wake_reasons

    def build_location_threads(
        self,
        seeds: Iterable[SimulationSeed],
    ) -> list[LocationThreadPlan]:
        grouped: Dict[str, list[SimulationSeed]] = {}
        for seed in seeds:
            location = str(seed.location or "").strip()
            location_key = location or "__bridge__"
            grouped.setdefault(location_key, []).append(seed)

        threads: list[LocationThreadPlan] = []
        for location_key, items in grouped.items():
            ordered = sorted(
                items,
                key=lambda seed: (seed.salience, seed.urgency, seed.novelty),
                reverse=True,
            )
            participants = sorted(
                {
                    participant
                    for seed in ordered
                    for participant in seed.participants
                    if participant
                }
            )
            threads.append(
                LocationThreadPlan(
                    thread_id=location_key,
                    location="" if location_key == "__bridge__" else location_key,
                    seeds=ordered,
                    participants=participants,
                    max_salience=max((seed.salience for seed in ordered), default=0.0),
                    is_bridge=location_key == "__bridge__",
                )
            )

        return sorted(
            threads,
            key=lambda thread: (thread.max_salience, not thread.is_bridge, thread.thread_id),
            reverse=True,
        )

    def interleave_location_threads(
        self,
        threads: Iterable[LocationThreadPlan],
    ) -> list[SimulationSeed]:
        queues = [list(thread.seeds) for thread in threads]
        interleaved: list[SimulationSeed] = []
        while any(queues):
            for queue in queues:
                if not queue:
                    continue
                interleaved.append(queue.pop(0))
        return interleaved

    def plan_bridge_events(
        self,
        snapshots: Iterable[CharacterSnapshot],
        *,
        source_event_id: str,
        participants: Iterable[str],
        source_location: str,
        salience: float,
        outcome_summary: str,
        replay_timeline_index: int,
        language_guidance: str = "",
    ) -> list[ScheduledWorldEvent]:
        if salience < self.foreground_threshold or not source_location.strip():
            return []

        wake_reasons = self.identify_woken_agents(
            snapshots,
            participants=participants,
            location=source_location,
            salience=salience,
        )
        participant_ids = {participant for participant in participants if participant}
        source_location_normalized = source_location.strip().lower()
        bridge_events: list[ScheduledWorldEvent] = []

        for snapshot in snapshots:
            character_id = snapshot.identity.character_id
            if wake_reasons.get(character_id) != "social_graph":
                continue
            if character_id in participant_ids:
                continue
            target_location = str(snapshot.current_state.get("location") or "").strip()
            if not target_location or target_location.lower() == source_location_normalized:
                continue
            bridge_events.append(
                ScheduledWorldEvent(
                    event_id=f"{source_event_id}_bridge_{character_id}",
                    trigger_timeline_index=replay_timeline_index + self._bridge_delay_minutes(salience),
                    description=self._bridge_description(
                        target_name=snapshot.identity.name,
                        outcome_summary=outcome_summary,
                        salience=salience,
                        language_guidance=language_guidance,
                    ),
                    affected_agents=[character_id],
                    urgency=self._bridge_urgency(salience),
                    location=target_location,
                )
            )

        return bridge_events

    @staticmethod
    def _bridge_delay_minutes(salience: float) -> int:
        if salience >= 0.8:
            return 15
        if salience >= 0.6:
            return 30
        return 60

    @staticmethod
    def _bridge_urgency(salience: float) -> str:
        if salience >= 0.8:
            return "high"
        if salience >= 0.6:
            return "medium"
        return "low"

    @staticmethod
    def _bridge_description(
        *,
        target_name: str,
        outcome_summary: str,
        salience: float,
        language_guidance: str = "",
    ) -> str:
        if WorldManager._prefers_chinese_bridge_text(
            language_guidance=language_guidance,
            target_name=target_name,
            outcome_summary=outcome_summary,
        ):
            if salience >= 0.8:
                return f"消息传到{target_name}耳中：{outcome_summary}"
            return f"风声传到{target_name}耳中：{outcome_summary}"
        if salience >= 0.8:
            return f"News reaches {target_name}: {outcome_summary}"
        return f"Rumor reaches {target_name}: {outcome_summary}"

    @staticmethod
    def _prefers_chinese_bridge_text(
        *,
        language_guidance: str,
        target_name: str,
        outcome_summary: str,
    ) -> bool:
        if "中文" in language_guidance:
            return True
        return any(
            WorldManager._contains_cjk(text)
            for text in (target_name, outcome_summary)
        )

    @staticmethod
    def _contains_cjk(text: str) -> bool:
        return any("\u4e00" <= char <= "\u9fff" for char in text)

    @staticmethod
    def _has_social_connection(
        *,
        source: CharacterSnapshot,
        target_id: str,
        reverse_source: Optional[CharacterSnapshot],
        reverse_target_id: str,
        trust_threshold: float,
    ) -> bool:
        for relation in source.relationships:
            if relation.to_character_id != target_id:
                continue
            if abs(relation.trust_value) >= trust_threshold:
                return True
            if relation.sentiment_shift or relation.reason:
                return True

        if reverse_source is None:
            return False

        for relation in reverse_source.relationships:
            if relation.to_character_id != reverse_target_id:
                continue
            if abs(relation.trust_value) >= trust_threshold:
                return True
            if relation.sentiment_shift or relation.reason:
                return True
        return False
