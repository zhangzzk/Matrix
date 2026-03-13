from __future__ import annotations

from typing import Any, Dict

from dreamdive.schemas import JSONValue, SnapshotInference


def normalize_current_state(
    current_state: Dict[str, JSONValue] | None,
    inferred_state: SnapshotInference | None = None,
) -> Dict[str, JSONValue]:
    state: Dict[str, JSONValue] = dict(current_state or {})

    emotional = state.get("emotional_state")
    if isinstance(emotional, dict):
        state["emotional_state"] = (
            str(
                emotional.get("dominant_now")
                or emotional.get("dominant")
                or emotional.get("label")
                or ""
            ).strip()
        )
    elif not str(emotional or "").strip() and inferred_state is not None:
        state["emotional_state"] = inferred_state.emotional_state.dominant

    physical = state.get("physical_state")
    if isinstance(physical, dict):
        state["physical_state"] = (
            str(
                physical.get("current_activity")
                or physical.get("injuries_or_constraints")
                or physical.get("location")
                or ""
            ).strip()
        )
    elif not str(physical or "").strip() and inferred_state is not None:
        physical_summary = (
            inferred_state.physical_state.current_activity
            or inferred_state.physical_state.injuries_or_constraints
        ).strip()
        if physical_summary:
            state["physical_state"] = physical_summary

    if not str(state.get("location") or "").strip() and inferred_state is not None:
        inferred_location = inferred_state.physical_state.location.strip()
        if inferred_location:
            state["location"] = inferred_location

    if not str(state.get("current_activity") or "").strip() and inferred_state is not None:
        current_activity = inferred_state.physical_state.current_activity.strip()
        if current_activity:
            state["current_activity"] = current_activity

    if "knowledge_state" not in state and inferred_state is not None:
        if inferred_state.knowledge_state.new_knowledge:
            state["knowledge_state"] = list(inferred_state.knowledge_state.new_knowledge)

    if not str(state.get("immediate_tension") or "").strip() and inferred_state is not None:
        if inferred_state.immediate_tension.strip():
            state["immediate_tension"] = inferred_state.immediate_tension

    if not str(state.get("unspoken_subtext") or "").strip() and inferred_state is not None:
        if inferred_state.unspoken_subtext.strip():
            state["unspoken_subtext"] = inferred_state.unspoken_subtext

    return state


def normalize_simple_state_value(value: Any) -> Any:
    if isinstance(value, dict):
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
    return value
