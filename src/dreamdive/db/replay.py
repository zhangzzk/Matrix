from __future__ import annotations

from collections import defaultdict
from typing import Dict, Iterable, Optional, TypeVar

from dreamdive.schemas import JSONValue, ReplayKey, StateChangeLogEntry

TEntry = TypeVar("TEntry", bound=StateChangeLogEntry)


def replay_sort_key(replay_key: ReplayKey) -> tuple[int, int]:
    return replay_key.timeline_index, replay_key.event_sequence


def _normalize_dimension_value(dimension: str, value: JSONValue) -> JSONValue:
    if dimension not in {"emotional_state", "physical_state"} or not isinstance(value, dict):
        return value
    return (
        str(
            value.get("dominant_now")
            or value.get("dominant")
            or value.get("current_activity")
            or value.get("injuries_or_constraints")
            or value.get("location")
            or ""
        ).strip()
    )


class StateReplay:
    """Deterministic replay over append-only state logs."""

    def __init__(self, default_values: Optional[Dict[str, JSONValue]] = None) -> None:
        self.default_values = default_values or {}

    def get_value_at_tick(
        self,
        entries: Iterable[StateChangeLogEntry],
        character_id: str,
        dimension: str,
        timeline_index: int,
    ) -> JSONValue:
        relevant_entries = [
            entry
            for entry in entries
            if entry.character_id == character_id
            and entry.dimension == dimension
            and entry.replay_key.timeline_index <= timeline_index
        ]
        if not relevant_entries:
            return self.default_values.get(dimension)

        latest = max(relevant_entries, key=lambda item: replay_sort_key(item.replay_key))
        return _normalize_dimension_value(dimension, latest.to_value)

    def replay_character_state(
        self,
        entries: Iterable[StateChangeLogEntry],
        character_id: str,
        timeline_index: int,
    ) -> dict[str, JSONValue]:
        state = dict(self.default_values)
        grouped: dict[str, list[StateChangeLogEntry]] = defaultdict(list)
        for entry in entries:
            if (
                entry.character_id == character_id
                and entry.replay_key.timeline_index <= timeline_index
            ):
                grouped[entry.dimension].append(entry)

        for dimension, dimension_entries in grouped.items():
            latest = max(
                dimension_entries,
                key=lambda item: replay_sort_key(item.replay_key),
            )
            state[dimension] = _normalize_dimension_value(dimension, latest.to_value)

        return state
