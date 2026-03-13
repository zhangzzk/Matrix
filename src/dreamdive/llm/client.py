from __future__ import annotations

import asyncio
import json
import re
from typing import Any, Optional, Protocol, TypeVar

from pydantic import BaseModel, ValidationError

from dreamdive.config import LLMProfileSettings, SimulationSettings, get_settings
from dreamdive.debug import DebugSession
from dreamdive.ingestion.models import (
    AccumulatedExtraction,
    EntityExtractionPayload,
    MetaLayerRecord,
    StructuralScanPayload,
)
from dreamdive.schemas import (
    AgentBeatPayload,
    BackgroundEventPayload,
    BatchedTrajectoryProjectionPayload,
    GoalSeedPayload,
    GoalCollisionBatchPayload,
    NarrativeArcUpdatePayload,
    PromptRequest,
    ResolutionCheckPayload,
    SceneSetupPayload,
    SnapshotInference,
    StateUpdatePayload,
    TrajectoryProjectionPayload,
)

TModel = TypeVar("TModel", bound=BaseModel)


class LLMTransport(Protocol):
    async def complete(self, profile: LLMProfileSettings, prompt: PromptRequest) -> str:
        ...


class StructuredLLMClient:
    def __init__(
        self,
        *,
        transport: LLMTransport,
        profiles: Optional[list[LLMProfileSettings]] = None,
        primary: Optional[LLMProfileSettings] = None,
        fallback: Optional[LLMProfileSettings] = None,
        additional_profiles: Optional[list[LLMProfileSettings]] = None,
        retry_attempts: int = 2,
        retry_delay_seconds: float = 1.0,
        debug_session: Optional[DebugSession] = None,
        issue_records: Optional[list[dict[str, Any]]] = None,
        success_records: Optional[list[dict[str, Any]]] = None,
    ) -> None:
        if profiles is not None and any(
            item is not None for item in [primary, fallback, additional_profiles]
        ):
            raise ValueError("Pass either profiles or primary/fallback, not both")

        if profiles is None:
            assembled_profiles = [
                profile
                for profile in [primary, fallback, *(additional_profiles or [])]
                if profile is not None
            ]
        else:
            assembled_profiles = [profile for profile in profiles if profile is not None]

        if not assembled_profiles:
            raise ValueError("At least one LLM profile must be configured")

        self.profiles = _dedupe_profiles(assembled_profiles)
        self.transport = transport
        self.retry_attempts = retry_attempts
        self.retry_delay_seconds = retry_delay_seconds
        self.debug_session = debug_session
        self.issue_records = list(issue_records or [])
        self.success_records = list(success_records or [])

    @property
    def primary(self) -> LLMProfileSettings:
        return self.profiles[0]

    @property
    def fallback(self) -> Optional[LLMProfileSettings]:
        if len(self.profiles) < 2:
            return None
        return self.profiles[1]

    @classmethod
    def from_settings(
        cls,
        transport: LLMTransport,
        settings: Optional[SimulationSettings] = None,
    ) -> "StructuredLLMClient":
        active_settings = settings or get_settings()
        return cls(
            profiles=active_settings.active_llm_profiles(),
            transport=transport,
            retry_attempts=active_settings.llm_retry_attempts,
            retry_delay_seconds=active_settings.llm_retry_delay_seconds,
        )

    async def call_json(self, prompt: PromptRequest, schema: type[TModel]) -> TModel:
        last_error: Optional[Exception] = None
        attempted_profiles: list[str] = []
        for profile in self.profiles:
            if profile.name not in attempted_profiles:
                attempted_profiles.append(profile.name)
            active_prompt = prompt
            for attempt in range(self.retry_attempts):
                attempt_id = None
                if self.debug_session is not None:
                    attempt_id = self.debug_session.start_llm_attempt(
                        profile_name=profile.name,
                        prompt_name=str(prompt.metadata.get("prompt_name", "prompt")),
                        schema_name=schema.__name__,
                        attempt_index=attempt + 1,
                        prompt_payload=active_prompt.model_dump(mode="json"),
                    )
                try:
                    raw = await self.transport.complete(profile, active_prompt)
                except Exception as exc:
                    last_error = exc
                    self._record_issue(
                        profile_name=profile.name,
                        prompt=active_prompt,
                        schema=schema,
                        attempt_index=attempt + 1,
                        stage="transport",
                        error=exc,
                    )
                    if self.debug_session is not None and attempt_id is not None:
                        self.debug_session.finish_llm_attempt(
                            attempt_id,
                            error_message=str(exc),
                        )
                    await asyncio.sleep(self.retry_delay_seconds)
                    continue

                try:
                    parsed = self._parse_json(raw, schema, active_prompt)
                    self._record_success(
                        profile_name=profile.name,
                        prompt=active_prompt,
                        schema=schema,
                        attempt_index=attempt + 1,
                    )
                    if self.debug_session is not None and attempt_id is not None:
                        self.debug_session.finish_llm_attempt(
                            attempt_id,
                            raw_response=raw,
                            parsed_payload=parsed.model_dump(mode="json"),
                        )
                    return parsed
                except (json.JSONDecodeError, ValidationError, ValueError) as exc:
                    last_error = exc
                    self._record_issue(
                        profile_name=profile.name,
                        prompt=active_prompt,
                        schema=schema,
                        attempt_index=attempt + 1,
                        stage="validation",
                        error=exc,
                        raw_response=raw,
                    )
                    if self.debug_session is not None and attempt_id is not None:
                        self.debug_session.finish_llm_attempt(
                            attempt_id,
                            raw_response=raw,
                            error_message=str(exc),
                        )
                    if attempt < self.retry_attempts - 1:
                        active_prompt = self._build_correction_prompt(
                            original_prompt=prompt,
                            invalid_response=raw,
                            schema=schema,
                            error=exc,
                        )
                    await asyncio.sleep(self.retry_delay_seconds)
        prompt_name = str(prompt.metadata.get("prompt_name", "prompt"))
        self._record_terminal_issue(
            prompt=prompt,
            schema=schema,
            attempted_profiles=attempted_profiles,
            error=last_error,
        )
        if isinstance(last_error, (json.JSONDecodeError, ValidationError, ValueError)):
            raise RuntimeError(
                f"LLM response for {prompt_name} ({schema.__name__}) could not be validated. "
                f"Last error: {last_error}"
            ) from last_error
        raise RuntimeError(
            f"LLM request for {prompt_name} ({schema.__name__}) failed. "
            f"Last error: {last_error}"
        ) from last_error

    def drain_issue_records(self) -> list[dict[str, Any]]:
        drained = list(self.issue_records)
        self.issue_records.clear()
        return drained

    def provider_usage_summary(self) -> dict[str, Any]:
        counts: dict[str, int] = {}
        for item in self.success_records:
            profile_name = str(item.get("profile_name", "") or "").strip()
            if not profile_name:
                continue
            counts[profile_name] = counts.get(profile_name, 0) + 1
        ordered_profiles = [
            profile.name
            for profile in self.profiles
            if counts.get(profile.name, 0) > 0
        ]
        for profile_name in counts:
            if profile_name not in ordered_profiles:
                ordered_profiles.append(profile_name)
        return {
            "ordered_profiles": ordered_profiles,
            "counts": counts,
            "total_calls": sum(counts.values()),
        }

    @staticmethod
    def _parse_json(raw: str, schema: type[TModel], prompt: PromptRequest) -> TModel:
        clean = raw.strip()
        if not clean:
            raise ValueError("LLM returned empty response body")
        last_error: json.JSONDecodeError | None = None
        for candidate in _json_candidates(clean):
            try:
                data = json.loads(candidate)
                break
            except json.JSONDecodeError as exc:
                last_error = exc
        else:
            raise last_error or json.JSONDecodeError("Expecting value", clean, 0)
        normalized = _normalize_payload_for_schema(data, schema)
        _validate_language_expectations(normalized, schema, prompt)
        return schema.model_validate(normalized)

    @staticmethod
    def _build_correction_prompt(
        *,
        original_prompt: PromptRequest,
        invalid_response: str,
        schema: type[TModel],
        error: Exception,
    ) -> PromptRequest:
        schema_json = json.dumps(schema.model_json_schema(), sort_keys=True)
        previous_response = invalid_response if invalid_response.strip() else "[EMPTY RESPONSE]"
        return PromptRequest(
            system=original_prompt.system,
            user=(
                f"{original_prompt.user}\n\n"
                "Your previous response was invalid JSON or did not match the schema.\n"
                f"Validation error: {error}\n"
                f"Previous response: {previous_response}\n"
                f"Return valid JSON matching this schema: {schema_json}"
            ),
            max_tokens=original_prompt.max_tokens,
            stream=original_prompt.stream,
            metadata=dict(original_prompt.metadata),
        )

    def _record_issue(
        self,
        *,
        profile_name: str,
        prompt: PromptRequest,
        schema: type[BaseModel],
        attempt_index: int,
        stage: str,
        error: Exception,
        raw_response: str | None = None,
        severity: str = "warning",
    ) -> None:
        metadata = dict(prompt.metadata)
        preview = (raw_response or "").strip()
        self.issue_records.append(
            {
                "profile_name": profile_name,
                "prompt_name": str(metadata.get("prompt_name", "prompt")),
                "schema_name": schema.__name__,
                "character_id": str(metadata.get("character_id", "")),
                "seed_id": str(metadata.get("seed_id", "")),
                "chapter_id": str(metadata.get("chapter_id", "")),
                "attempt_index": attempt_index,
                "stage": stage,
                "severity": severity,
                "error_type": error.__class__.__name__,
                "error_message": str(error),
                "response_was_empty": raw_response is not None and not preview,
                "response_preview": preview[:280],
            }
        )

    def _record_terminal_issue(
        self,
        *,
        prompt: PromptRequest,
        schema: type[BaseModel],
        attempted_profiles: list[str],
        error: Exception | None,
    ) -> None:
        if error is None:
            return
        metadata = dict(prompt.metadata)
        self.issue_records.append(
            {
                "profile_name": attempted_profiles[-1] if attempted_profiles else "",
                "profiles_tried": list(attempted_profiles),
                "prompt_name": str(metadata.get("prompt_name", "prompt")),
                "schema_name": schema.__name__,
                "character_id": str(metadata.get("character_id", "")),
                "seed_id": str(metadata.get("seed_id", "")),
                "chapter_id": str(metadata.get("chapter_id", "")),
                "attempt_index": self.retry_attempts,
                "stage": "exhausted",
                "severity": "critical",
                "error_type": error.__class__.__name__,
                "error_message": str(error),
                "response_was_empty": False,
                "response_preview": "",
            }
        )

    def _record_success(
        self,
        *,
        profile_name: str,
        prompt: PromptRequest,
        schema: type[BaseModel],
        attempt_index: int,
    ) -> None:
        metadata = dict(prompt.metadata)
        self.success_records.append(
            {
                "profile_name": profile_name,
                "prompt_name": str(metadata.get("prompt_name", "prompt")),
                "schema_name": schema.__name__,
                "character_id": str(metadata.get("character_id", "")),
                "seed_id": str(metadata.get("seed_id", "")),
                "chapter_id": str(metadata.get("chapter_id", "")),
                "attempt_index": attempt_index,
            }
        )


def _dedupe_profiles(profiles: list[LLMProfileSettings]) -> list[LLMProfileSettings]:
    deduped: list[LLMProfileSettings] = []
    seen: set[tuple[str, str, str]] = set()
    for profile in profiles:
        key = (profile.name, profile.base_url, profile.model)
        if key in seen:
            continue
        deduped.append(profile)
        seen.add(key)
    return deduped


def _json_candidates(raw: str) -> list[str]:
    candidates: list[str] = []

    def _add(candidate: str) -> None:
        normalized = candidate.strip()
        if normalized and normalized not in candidates:
            candidates.append(normalized)

    _add(raw)
    if raw.startswith("```"):
        stripped = raw.removeprefix("```json").removeprefix("```").strip()
        if stripped.endswith("```"):
            stripped = stripped[:-3].strip()
        _add(stripped)

    for match in re.finditer(r"```(?:json)?\s*(.*?)```", raw, flags=re.IGNORECASE | re.DOTALL):
        _add(match.group(1))

    first_object = raw.find("{")
    last_object = raw.rfind("}")
    if first_object != -1 and last_object > first_object:
        _add(raw[first_object : last_object + 1])

    first_array = raw.find("[")
    last_array = raw.rfind("]")
    if first_array != -1 and last_array > first_array:
        _add(raw[first_array : last_array + 1])

    return candidates




def _normalize_payload_for_schema(data: Any, schema: type[BaseModel]) -> Any:
    if schema is StructuralScanPayload:
        return _normalize_structural_scan_payload(data)
    if schema is AccumulatedExtraction:
        return _normalize_accumulated_extraction_payload(data)
    if schema is MetaLayerRecord:
        return _normalize_meta_layer_payload(data)
    if schema is EntityExtractionPayload:
        return _normalize_entity_extraction_payload(data)
    if schema is SnapshotInference:
        return _normalize_snapshot_inference_payload(data)
    if schema is GoalSeedPayload:
        return _normalize_goal_seed_payload(data)
    if schema is TrajectoryProjectionPayload:
        return _normalize_trajectory_projection_payload(data)
    if schema is BatchedTrajectoryProjectionPayload:
        return _normalize_batched_trajectory_projection_payload(data)
    if schema is GoalCollisionBatchPayload:
        return _normalize_goal_collision_batch_payload(data)
    if schema is BackgroundEventPayload:
        return _normalize_background_event_payload(data)
    if schema is SceneSetupPayload:
        return _normalize_scene_setup_payload(data)
    if schema is AgentBeatPayload:
        return _normalize_agent_beat_payload(data)
    if schema is ResolutionCheckPayload:
        return _normalize_resolution_check_payload(data)
    if schema is StateUpdatePayload:
        return _normalize_state_update_payload(data)
    if schema is NarrativeArcUpdatePayload:
        return _normalize_narrative_arc_update_payload(data)
    return data


def _normalize_trajectory_projection_payload(data: Any) -> Any:
    if not isinstance(data, dict):
        return data
    normalized = dict(data)
    if "greatest_fear_this_horizon" not in normalized and "greatest_fear" in normalized:
        normalized["greatest_fear_this_horizon"] = normalized.get("greatest_fear", "")
    contingencies = normalized.get("contingencies", [])
    if isinstance(contingencies, list):
        normalized["contingencies"] = [
            _normalize_contingency(item)
            for item in contingencies
        ]
    return normalized


def _normalize_structural_scan_payload(data: Any) -> Any:
    if not isinstance(data, dict):
        return data
    normalized = dict(data)
    world = normalized.get("world", {})
    timeline = normalized.get("timeline_skeleton", normalized.get("timeline", {}))
    normalized["world"] = _normalize_world_skeleton(world)
    normalized["cast_list"] = [
        _normalize_cast_member(item, index)
        for index, item in enumerate(
            _ensure_list(normalized.get("cast_list", normalized.get("characters", [])))
        )
    ]
    normalized["timeline_skeleton"] = _normalize_timeline_skeleton(timeline)
    normalized["domain_systems"] = [
        _normalize_domain_system(item)
        for item in _ensure_list(normalized.get("domain_systems", normalized.get("systems", [])))
    ]
    return normalized


def _normalize_accumulated_extraction_payload(data: Any) -> Any:
    if not isinstance(data, dict):
        return data
    normalized = dict(data)
    normalized["characters"] = [
        _normalize_character_extraction_record(item, index)
        for index, item in enumerate(
            _ensure_list(normalized.get("characters", normalized.get("cast", [])))
        )
    ]
    normalized["world"] = _normalize_world_extraction_record(normalized.get("world", {}))
    normalized["events"] = [
        _normalize_event_extraction_record(item, index)
        for index, item in enumerate(
            _ensure_list(normalized.get("events", normalized.get("chapter_events", [])))
        )
    ]
    normalized["entities"] = [
        _normalize_entity_record(item, index)
        for index, item in enumerate(_ensure_list(normalized.get("entities", [])))
    ]
    normalized["meta"] = _normalize_meta_layer_payload(
        normalized.get("meta", normalized.get("meta_layer", {}))
    )
    return normalized


def _normalize_meta_layer_payload(data: Any) -> Any:
    if not isinstance(data, dict):
        return data
    normalized = dict(data)
    authorial = normalized.get("authorial", {})
    if not isinstance(authorial, dict):
        authorial = {}
    central_thesis = authorial.get("central_thesis", {})
    if isinstance(central_thesis, str):
        central_thesis = {"summary": central_thesis}
    beliefs_about = authorial.get("beliefs_about", {})
    if isinstance(beliefs_about, str):
        beliefs_about = {"summary": beliefs_about}
    authorial["central_thesis"] = central_thesis if isinstance(central_thesis, dict) else {}
    authorial["beliefs_about"] = beliefs_about if isinstance(beliefs_about, dict) else {}
    authorial["themes"] = [
        _normalize_theme_record(item)
        for item in _ensure_list(authorial.get("themes", []))
    ]
    authorial["symbolic_motifs"] = _string_list(authorial.get("symbolic_motifs", []))
    normalized["authorial"] = authorial

    writing_style = normalized.get("writing_style", {})
    if not isinstance(writing_style, dict):
        writing_style = {}
    writing_style["stylistic_signatures"] = _string_list(
        writing_style.get("stylistic_signatures", [])
    )
    writing_style["sample_passages"] = [
        _normalize_sample_passage(item)
        for item in _ensure_list(writing_style.get("sample_passages", []))
    ]
    normalized["writing_style"] = writing_style

    language_context = normalized.get("language_context", {})
    if not isinstance(language_context, dict):
        language_context = {}
    for key in ("figurative_patterns", "multilingual_features", "translation_notes"):
        language_context[key] = _string_list(language_context.get(key, []))
    normalized["language_context"] = language_context

    normalized["character_voices"] = [
        _normalize_character_voice_record(item, index)
        for index, item in enumerate(
            _ensure_list(normalized.get("character_voices", normalized.get("voices", [])))
        )
    ]

    real_world_context = normalized.get("real_world_context", {})
    if not isinstance(real_world_context, dict):
        real_world_context = {}
    real_world_context["unspeakable_constraints"] = _string_list(
        real_world_context.get("unspeakable_constraints", [])
    )
    normalized["real_world_context"] = real_world_context
    return normalized


def _normalize_entity_extraction_payload(data: Any) -> Any:
    if not isinstance(data, dict):
        return data
    normalized = dict(data)
    normalized["entities"] = [
        _normalize_entity_record(item, index)
        for index, item in enumerate(
            _ensure_list(normalized.get("entities", normalized.get("entity_list", [])))
        )
    ]
    return normalized


def _normalize_snapshot_inference_payload(data: Any) -> Any:
    if not isinstance(data, dict):
        return data
    normalized = dict(data)

    emotional_state = normalized.get(
        "emotional_state",
        normalized.get("psychological_state", normalized.get("emotion", {})),
    )
    normalized["emotional_state"] = _normalize_emotional_state_payload(emotional_state)

    normalized["immediate_tension"] = str(
        normalized.get("immediate_tension")
        or normalized.get("tension")
        or normalized.get("main_tension")
        or normalized.get("pressure")
        or ""
    )
    normalized["unspoken_subtext"] = str(
        normalized.get("unspoken_subtext")
        or normalized.get("subtext")
        or normalized.get("hidden_feeling")
        or normalized.get("what_they_wont_say")
        or ""
    )

    physical_state = normalized.get("physical_state", normalized.get("body_state", {}))
    normalized["physical_state"] = _normalize_physical_state_payload(physical_state)

    knowledge_state = normalized.get("knowledge_state", normalized.get("cognitive_state", {}))
    normalized["knowledge_state"] = _normalize_knowledge_state_payload(knowledge_state)
    return normalized


def _normalize_goal_seed_payload(data: Any) -> Any:
    if not isinstance(data, dict):
        return data
    normalized = dict(data)
    goal_stack = normalized.get("goal_stack", normalized.get("goals", []))
    if isinstance(goal_stack, dict):
        goal_stack = list(goal_stack.values())
    normalized["goal_stack"] = [
        _normalize_goal_seed_goal(item, index)
        for index, item in enumerate(_ensure_list(goal_stack))
    ]
    normalized["actively_avoiding"] = str(
        normalized.get("actively_avoiding")
        or normalized.get("avoiding")
        or normalized.get("what_they_are_avoiding")
        or ""
    )
    normalized["most_uncertain_relationship"] = str(
        normalized.get("most_uncertain_relationship")
        or normalized.get("uncertain_relationship")
        or normalized.get("relationship_uncertainty")
        or ""
    )
    return normalized


def _normalize_emotional_state_payload(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        return {
            "dominant": value,
            "secondary": [],
            "confidence": 0.5,
        }
    payload = dict(value) if isinstance(value, dict) else {}
    dominant = (
        payload.get("dominant")
        or payload.get("dominant_emotion")
        or payload.get("primary_emotion")
        or payload.get("summary")
        or payload.get("state")
        or ""
    )
    secondary = payload.get("secondary", payload.get("secondary_emotions", []))
    if isinstance(secondary, str):
        secondary = [secondary]
    confidence = _coerce_float(
        payload.get("confidence", payload.get("certainty"))
    )
    return {
        "dominant": str(dominant),
        "secondary": _string_list(secondary),
        "confidence": confidence if confidence is not None else 0.5,
    }


def _normalize_physical_state_payload(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        return {
            "energy": 0.5,
            "injuries_or_constraints": value,
            "location": "",
            "current_activity": "",
        }
    payload = dict(value) if isinstance(value, dict) else {}
    energy = _coerce_float(payload.get("energy", payload.get("stamina")))
    return {
        "energy": energy if energy is not None else 0.5,
        "injuries_or_constraints": str(
            payload.get("injuries_or_constraints")
            or payload.get("constraints")
            or payload.get("bodily_condition")
            or payload.get("state")
            or ""
        ),
        "location": str(payload.get("location") or payload.get("place") or ""),
        "current_activity": str(
            payload.get("current_activity")
            or payload.get("activity")
            or payload.get("doing")
            or ""
        ),
    }


def _normalize_knowledge_state_payload(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        return {
            "new_knowledge": [value] if value.strip() else [],
            "active_misbeliefs": [],
        }
    payload = dict(value) if isinstance(value, dict) else {}
    new_knowledge = payload.get(
        "new_knowledge",
        payload.get("known_now", payload.get("realizations", [])),
    )
    active_misbeliefs = payload.get(
        "active_misbeliefs",
        payload.get("misbeliefs", payload.get("false_assumptions", [])),
    )
    if isinstance(new_knowledge, str):
        new_knowledge = [new_knowledge]
    if isinstance(active_misbeliefs, str):
        active_misbeliefs = [active_misbeliefs]
    return {
        "new_knowledge": _string_list(new_knowledge),
        "active_misbeliefs": _string_list(active_misbeliefs),
    }


def _normalize_goal_seed_goal(item: Any, index: int) -> dict[str, Any]:
    if not isinstance(item, dict):
        text = str(item).strip()
        return {
            "priority": index + 1,
            "goal": text,
            "motivation": "",
            "obstacle": "",
            "time_horizon": "today",
            "emotional_charge": "",
            "abandon_condition": "",
        }
    priority = _coerce_int(item.get("priority"))
    return {
        "priority": priority if priority is not None and priority >= 1 else index + 1,
        "goal": str(
            item.get("goal")
            or item.get("action")
            or item.get("actionable_goal")
            or item.get("intent")
            or item.get("objective")
            or ""
        ),
        "motivation": str(
            item.get("motivation")
            or item.get("why")
            or item.get("reason")
            or item.get("drive")
            or ""
        ),
        "obstacle": str(
            item.get("obstacle")
            or item.get("risk")
            or item.get("constraint")
            or item.get("friction")
            or ""
        ),
        "time_horizon": _normalize_time_horizon_value(
            item.get("time_horizon", item.get("horizon"))
        ),
        "emotional_charge": str(
            item.get("emotional_charge")
            or item.get("emotion")
            or item.get("stakes")
            or item.get("affect")
            or ""
        ),
        "abandon_condition": str(
            item.get("abandon_condition")
            or item.get("failure_condition")
            or item.get("stop_when")
            or item.get("reconsider_when")
            or ""
        ),
    }


def _normalize_time_horizon_value(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in {"immediate", "right_now", "now"}:
        return "immediate"
    if normalized in {"today", "tonight", "this_day"}:
        return "today"
    if normalized in {"this_week", "week", "soon"}:
        return "this_week"
    if normalized in {"longer", "long_term", "later"}:
        return "longer"
    return "today"


def _normalize_batched_trajectory_projection_payload(data: Any) -> Any:
    if not isinstance(data, dict):
        return data
    normalized = dict(data)
    projections = normalized.get("projections", {})
    if isinstance(projections, dict):
        normalized["projections"] = {
            character_id: _normalize_trajectory_projection_payload(payload)
            for character_id, payload in projections.items()
        }
    return normalized


def _normalize_goal_collision_batch_payload(data: Any) -> Any:
    if not isinstance(data, dict):
        return data
    normalized = dict(data)
    goal_tensions = normalized.get("goal_tensions", normalized.get("tensions", []))
    solo_seeds = normalized.get("solo_seeds", [])
    world_events = normalized.get("world_events", normalized.get("events", []))
    normalized["goal_tensions"] = [
        _normalize_goal_tension_record(item, index)
        for index, item in enumerate(goal_tensions)
    ]
    normalized["solo_seeds"] = [
        _normalize_solo_seed_suggestion(item)
        for item in solo_seeds
    ]
    normalized["world_events"] = [
        _normalize_world_event_suggestion(item)
        for item in world_events
    ]
    return normalized


def _normalize_background_event_payload(data: Any) -> Any:
    if not isinstance(data, dict):
        return data
    normalized = dict(data)
    if "narrative_summary" not in normalized:
        normalized["narrative_summary"] = (
            normalized.get("summary")
            or normalized.get("scene_outcome")
            or normalized.get("description")
            or ""
        )
    outcomes = normalized.get("outcomes", [])
    if isinstance(outcomes, dict):
        outcomes = list(outcomes.values())
    normalized["outcomes"] = [
        _normalize_background_agent_outcome(item, index)
        for index, item in enumerate(outcomes)
    ]
    relationship_deltas = normalized.get("relationship_deltas", [])
    if isinstance(relationship_deltas, dict):
        relationship_deltas = [
            {
                "from_id": key,
                "to_id": "",
                "change": value if isinstance(value, str) else json.dumps(value, ensure_ascii=False),
            }
            for key, value in relationship_deltas.items()
        ]
    normalized["relationship_deltas"] = relationship_deltas
    normalized.setdefault("unexpected", normalized.get("twist", ""))
    return normalized


def _normalize_scene_setup_payload(data: Any) -> Any:
    if not isinstance(data, dict):
        return data
    normalized = dict(data)
    if "scene_opening" not in normalized:
        normalized["scene_opening"] = normalized.get("opening", "")
    if "resolution_conditions" not in normalized:
        resolution = normalized.get("resolution", {})
        if not isinstance(resolution, dict):
            resolution = {}
        normalized["resolution_conditions"] = {
            "primary": resolution.get("primary", ""),
            "secondary": resolution.get("secondary", ""),
            "forced_exit": resolution.get("forced_exit", ""),
        }
    if "agent_perceptions" not in normalized:
        normalized["agent_perceptions"] = normalized.get("perceptions", {})
    if "tension_signature" not in normalized:
        normalized["tension_signature"] = normalized.get("tension", "")
    return normalized


def _normalize_agent_beat_payload(data: Any) -> Any:
    if not isinstance(data, dict):
        return data
    normalized = dict(data)
    internal = normalized.get("internal", {})
    external = normalized.get("external", {})
    if not isinstance(internal, dict):
        internal = {}
    if not isinstance(external, dict):
        external = {}
    if not internal and any(key in normalized for key in ("thought", "emotion_now", "goal_update", "what_i_noticed")):
        internal = {
            "thought": normalized.get("thought", ""),
            "emotion_now": normalized.get("emotion_now", ""),
            "goal_update": normalized.get("goal_update", ""),
            "what_i_noticed": normalized.get("what_i_noticed", ""),
        }
    if not external and any(key in normalized for key in ("dialogue", "physical_action", "tone")):
        external = {
            "dialogue": normalized.get("dialogue", ""),
            "physical_action": normalized.get("physical_action", ""),
            "tone": normalized.get("tone", ""),
        }
    normalized["internal"] = internal
    normalized["external"] = external
    normalized.setdefault("held_back", normalized.get("held_back_impulse", ""))
    return normalized


def _normalize_resolution_check_payload(data: Any) -> Any:
    if not isinstance(data, dict):
        return data
    normalized = dict(data)
    resolved = normalized.get("resolved")
    if resolved is None:
        resolved = normalized.get("resolution_met")
    if resolved is None:
        resolved = normalized.get("condition_met")
    if resolved is None:
        resolved = False
    normalized["resolved"] = bool(resolved)
    if "resolution_type" not in normalized:
        normalized["resolution_type"] = "primary" if normalized["resolved"] else "continue"
    normalized.setdefault(
        "scene_outcome",
        normalized.get("outcome") or normalized.get("summary") or "",
    )
    if "continue" not in normalized and "continue_scene" not in normalized:
        normalized["continue"] = not normalized["resolved"]
    return normalized


def _normalize_state_update_payload(data: Any) -> Any:
    if not isinstance(data, dict):
        return data
    normalized = dict(data)
    emotional_delta = normalized.get("emotional_delta", {})
    if not isinstance(emotional_delta, dict):
        emotional_delta = {}
    normalized["emotional_delta"] = {
        "dominant_now": (
            emotional_delta.get("dominant_now")
            or emotional_delta.get("to")
            or emotional_delta.get("dominant")
            or ""
        ),
        "underneath": emotional_delta.get("underneath") or emotional_delta.get("from") or "",
        "shift_reason": (
            emotional_delta.get("shift_reason")
            or emotional_delta.get("reason")
            or emotional_delta.get("note")
            or emotional_delta.get("reasoning")
            or ""
        ),
    }

    goal_stack_update = normalized.get("goal_stack_update", {})
    if not isinstance(goal_stack_update, dict):
        goal_stack_update = {}
    resolved_goal = goal_stack_update.get("resolved_goal")
    if resolved_goal is None:
        resolved_goal = _first_string(goal_stack_update.get("remove")) or _first_string(goal_stack_update.get("pop"))
    new_goal = goal_stack_update.get("new_goal")
    if new_goal is None:
        candidate = goal_stack_update.get("current_primary_goal")
        if isinstance(candidate, dict) and candidate.get("goal"):
            new_goal = candidate
    if "top_goal_status" in goal_stack_update:
        top_goal_status = goal_stack_update["top_goal_status"]
    elif new_goal is not None:
        top_goal_status = "shifted"
    elif resolved_goal:
        top_goal_status = "resolved"
    else:
        top_goal_status = "advanced"
    if "top_goal_still_priority" in goal_stack_update:
        top_goal_still_priority = bool(goal_stack_update["top_goal_still_priority"])
    else:
        top_goal_still_priority = new_goal is None
    normalized["goal_stack_update"] = {
        "top_goal_status": top_goal_status,
        "top_goal_still_priority": top_goal_still_priority,
        "new_goal": new_goal if isinstance(new_goal, dict) else None,
        "resolved_goal": resolved_goal,
    }

    relationship_updates = normalized.get("relationship_updates", [])
    if isinstance(relationship_updates, dict):
        relationship_updates = [
            _normalize_state_update_relationship_payload(target_id, payload)
            for target_id, payload in relationship_updates.items()
        ]
    elif isinstance(relationship_updates, list):
        relationship_updates = [
            _normalize_state_update_relationship_payload("", payload)
            for payload in relationship_updates
        ]
    else:
        relationship_updates = []
    normalized["relationship_updates"] = relationship_updates

    reprojection_decision = normalized.get("reprojection_decision", {})
    if not isinstance(reprojection_decision, dict):
        reprojection_decision = {}
    if "needs_reprojection" not in normalized:
        normalized["needs_reprojection"] = bool(
            reprojection_decision.get("recalculate")
            or reprojection_decision.get("invalidate_previous_trajectories")
            or reprojection_decision.get("new_trajectory")
        )
    if "reprojection_reason" not in normalized:
        normalized["reprojection_reason"] = (
            reprojection_decision.get("reasoning")
            or reprojection_decision.get("new_trajectory")
            or ""
        )
    return normalized


def _normalize_narrative_arc_update_payload(data: Any) -> Any:
    if not isinstance(data, dict):
        return data
    normalized = dict(data)
    assessment = normalized.get("narrative_assessment", {})
    if not isinstance(assessment, dict):
        assessment = {}

    for key in (
        "phase",
        "phase_changed",
        "phase_change_reason",
        "tension_level",
        "tension_delta",
        "tension_reason",
    ):
        if key not in normalized and key in assessment:
            normalized[key] = assessment.get(key)

    if "phase_change_reason" not in normalized:
        normalized["phase_change_reason"] = (
            assessment.get("phase_reason")
            or assessment.get("reason")
            or normalized.get("phase_reason")
            or ""
        )
    if "tension_reason" not in normalized:
        normalized["tension_reason"] = (
            assessment.get("tension_reason")
            or assessment.get("reason")
            or normalized.get("reason")
            or ""
        )

    unresolved_threads = (
        normalized.get("unresolved_threads")
        or assessment.get("unresolved_threads")
        or normalized.get("threads")
        or []
    )
    approaching_nodes = (
        normalized.get("approaching_nodes")
        or assessment.get("approaching_nodes")
        or normalized.get("next_nodes")
        or []
    )
    normalized["unresolved_threads"] = [
        _normalize_narrative_thread_payload(item, index)
        for index, item in enumerate(unresolved_threads)
    ]
    normalized["approaching_nodes"] = [
        _normalize_approaching_node_payload(item)
        for item in approaching_nodes
    ]

    narrative_drift = normalized.get("narrative_drift", {})
    if not isinstance(narrative_drift, dict):
        narrative_drift = {}
    normalized["narrative_drift"] = {
        "drifting": bool(
            narrative_drift.get("drifting")
            or narrative_drift.get("needs_correction")
            or False
        ),
        "drift_description": str(
            narrative_drift.get("drift_description")
            or narrative_drift.get("description")
            or ""
        ),
        "suggested_correction": str(
            narrative_drift.get("suggested_correction")
            or narrative_drift.get("correction")
            or ""
        ),
    }
    return normalized


def _normalize_contingency(item: Any) -> dict[str, str]:
    if isinstance(item, dict):
        return {
            "trigger": str(item.get("trigger") or item.get("condition") or item.get("if") or ""),
            "response": str(item.get("response") or item.get("action") or item.get("then") or ""),
        }
    if not isinstance(item, str):
        return {"trigger": "", "response": ""}
    text = item.strip()
    lower = text.lower()
    if lower.startswith("if ") and ", " in text:
        trigger, response = text.split(", ", 1)
        return {"trigger": trigger.strip(), "response": response.strip()}
    if ": " in text:
        trigger, response = text.split(": ", 1)
        return {"trigger": trigger.strip(), "response": response.strip()}
    return {"trigger": text, "response": ""}


def _normalize_goal_tension_record(item: Any, index: int) -> dict[str, Any]:
    if not isinstance(item, dict):
        return {
            "tension_id": f"tension_{index + 1:03d}",
            "type": "goal",
            "agents": [],
            "location": "",
            "description": str(item),
            "information_asymmetry": {},
            "stakes": {},
            "emergence_probability": 0.5,
            "salience_factors": [],
        }
    emergence_probability = item.get("emergence_probability")
    if emergence_probability is None:
        emergence_probability = item.get("severity", 0.5)
    try:
        emergence_probability = float(emergence_probability)
    except (TypeError, ValueError):
        emergence_probability = 0.5
    return {
        "tension_id": str(item.get("tension_id") or item.get("id") or f"tension_{index + 1:03d}"),
        "type": str(item.get("type") or item.get("tension_type") or "goal"),
        "agents": list(item.get("agents") or item.get("participants") or item.get("involved_agents") or []),
        "location": str(item.get("location") or ""),
        "description": str(item.get("description") or item.get("summary") or ""),
        "information_asymmetry": item.get("information_asymmetry") if isinstance(item.get("information_asymmetry"), dict) else {},
        "stakes": item.get("stakes") if isinstance(item.get("stakes"), dict) else {},
        "emergence_probability": max(0.0, min(1.0, emergence_probability)),
        "salience_factors": list(item.get("salience_factors") or []),
    }


def _normalize_solo_seed_suggestion(item: Any) -> dict[str, str]:
    if not isinstance(item, dict):
        return {"agent_id": "", "trigger": "", "description": str(item)}
    return {
        "agent_id": str(item.get("agent_id") or item.get("character_id") or ""),
        "trigger": str(item.get("trigger") or item.get("seed_type") or ""),
        "description": str(item.get("description") or item.get("seed") or ""),
    }


def _normalize_world_event_suggestion(item: Any) -> dict[str, Any]:
    if not isinstance(item, dict):
        return {"description": str(item), "affected_agents": [], "urgency": ""}
    return {
        "description": str(item.get("description") or item.get("event_name") or ""),
        "affected_agents": list(item.get("affected_agents") or item.get("agents") or []),
        "urgency": str(item.get("urgency") or item.get("impact") or ""),
    }


def _ensure_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, dict):
        return list(value.values())
    return [value]


def _string_list(value: Any) -> list[str]:
    values = _ensure_list(value)
    strings = [str(item).strip() for item in values if str(item).strip()]
    return strings


def _coerce_float(value: Any, default: float | None = None) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _coerce_int(value: Any, default: int | None = None) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _normalize_world_skeleton(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        return {
            "setting": value,
            "time_period": None,
            "rules_and_constraints": [],
            "factions": [],
            "key_locations": [],
        }
    world = dict(value) if isinstance(value, dict) else {}
    world["rules_and_constraints"] = _string_list(world.get("rules_and_constraints", []))
    world["factions"] = [
        _normalize_faction_record(item)
        for item in _ensure_list(world.get("factions", []))
    ]
    world["key_locations"] = [
        _normalize_location_record(item)
        for item in _ensure_list(
            world.get("key_locations", world.get("locations", []))
        )
    ]
    return world


def _normalize_faction_record(item: Any) -> dict[str, Any]:
    if isinstance(item, str):
        return {"name": item, "goal": None, "relationships": {}}
    if not isinstance(item, dict):
        return {"name": str(item), "goal": None, "relationships": {}}
    relationships = item.get("relationships", {})
    if not isinstance(relationships, dict):
        relationships = {}
    return {
        "name": str(item.get("name") or item.get("id") or ""),
        "goal": item.get("goal"),
        "relationships": {str(key): str(value) for key, value in relationships.items()},
    }


def _normalize_location_record(item: Any) -> dict[str, Any]:
    if isinstance(item, str):
        return {"name": item, "description": None, "narrative_significance": None}
    if not isinstance(item, dict):
        return {
            "name": str(item),
            "description": None,
            "narrative_significance": None,
        }
    return {
        "name": str(item.get("name") or item.get("id") or ""),
        "description": item.get("description"),
        "narrative_significance": item.get(
            "narrative_significance",
            item.get("significance"),
        ),
    }


def _normalize_cast_member(item: Any, index: int) -> dict[str, Any]:
    if not isinstance(item, dict):
        name = str(item)
        return {
            "id": f"char_{index + 1:03d}",
            "name": name,
            "aliases": [],
            "role": None,
            "first_appearance": None,
            "tier": 2,
        }
    tier = int(_coerce_float(item.get("tier"), 2) or 2)
    return {
        "id": str(item.get("id") or item.get("character_id") or f"char_{index + 1:03d}"),
        "name": str(item.get("name") or item.get("display_name") or item.get("id") or ""),
        "aliases": _string_list(item.get("aliases", item.get("alias", []))),
        "role": item.get("role"),
        "first_appearance": item.get("first_appearance", item.get("first_appears")),
        "tier": max(1, min(3, tier)),
    }


def _normalize_timeline_skeleton(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        return {
            "story_start": value,
            "pre_story_events": [],
            "known_future_events": [],
        }
    timeline = dict(value) if isinstance(value, dict) else {}
    timeline["pre_story_events"] = _string_list(timeline.get("pre_story_events", []))
    timeline["known_future_events"] = _string_list(
        timeline.get("known_future_events", [])
    )
    return timeline


def _normalize_domain_system(item: Any) -> dict[str, Any]:
    if isinstance(item, str):
        return {"name": item, "description": None, "scale": None}
    if not isinstance(item, dict):
        return {"name": str(item), "description": None, "scale": None}
    return {
        "name": str(item.get("name") or item.get("id") or ""),
        "description": item.get("description"),
        "scale": item.get("scale"),
    }


def _normalize_world_extraction_record(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        return {
            "setting": value,
            "time_period": None,
            "locations": [],
            "rules_and_constraints": [],
            "factions": [],
        }
    world = dict(value) if isinstance(value, dict) else {}
    world["locations"] = [
        item.get("name", "") if isinstance(item, dict) else str(item)
        for item in _ensure_list(world.get("locations", []))
        if (item.get("name", "") if isinstance(item, dict) else str(item)).strip()
    ]
    world["rules_and_constraints"] = _string_list(world.get("rules_and_constraints", []))
    world["factions"] = [
        item.get("name", "") if isinstance(item, dict) else str(item)
        for item in _ensure_list(world.get("factions", []))
        if (item.get("name", "") if isinstance(item, dict) else str(item)).strip()
    ]
    return world


def _normalize_character_extraction_record(item: Any, index: int) -> dict[str, Any]:
    if not isinstance(item, dict):
        name = str(item)
        return {
            "id": f"char_{index + 1:03d}",
            "name": name,
            "aliases": [],
            "identity": {},
            "personality": {},
            "current_state": {},
            "relationships": [],
            "memory_seeds": [],
        }
    identity = item.get("identity", {})
    if isinstance(identity, str):
        identity = {"summary": identity}
    personality = item.get("personality", {})
    if isinstance(personality, str):
        personality = {"summary": personality}
    return {
        "id": str(item.get("id") or item.get("character_id") or f"char_{index + 1:03d}"),
        "name": str(item.get("name") or item.get("display_name") or item.get("id") or ""),
        "aliases": _string_list(item.get("aliases", item.get("alias", []))),
        "identity": identity if isinstance(identity, dict) else {},
        "personality": personality if isinstance(personality, dict) else {},
        "current_state": _normalize_character_current_state(item.get("current_state", {})),
        "relationships": [
            _normalize_character_relationship_state(rel)
            for rel in _ensure_list(item.get("relationships", []))
        ],
        "memory_seeds": _string_list(item.get("memory_seeds", [])),
    }


def _normalize_character_current_state(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        return {
            "emotional_state": value,
            "physical_state": None,
            "location": None,
            "goal_stack": [],
        }
    state = dict(value) if isinstance(value, dict) else {}
    goal_stack = state.get("goal_stack", state.get("goals", []))
    if isinstance(goal_stack, dict):
        goal_stack = list(goal_stack.values())
    state["goal_stack"] = [
        item.get("goal", "") if isinstance(item, dict) else str(item)
        for item in _ensure_list(goal_stack)
        if (item.get("goal", "") if isinstance(item, dict) else str(item)).strip()
    ]
    return state


def _normalize_character_relationship_state(item: Any) -> dict[str, Any]:
    if isinstance(item, str):
        return {
            "target_id": item,
            "type": None,
            "trust": None,
            "sentiment": None,
            "shared_history_summary": None,
        }
    if not isinstance(item, dict):
        return {
            "target_id": str(item),
            "type": None,
            "trust": None,
            "sentiment": None,
            "shared_history_summary": None,
        }
    return {
        "target_id": str(
            item.get("target_id")
            or item.get("target")
            or item.get("character_id")
            or item.get("name")
            or ""
        ),
        "type": item.get("type", item.get("relation")),
        "trust": _coerce_float(item.get("trust")),
        "sentiment": item.get("sentiment", item.get("sentiment_shift")),
        "shared_history_summary": item.get(
            "shared_history_summary",
            item.get("reason", item.get("summary")),
        ),
    }


def _normalize_event_extraction_record(item: Any, index: int) -> dict[str, Any]:
    if not isinstance(item, dict):
        return {
            "id": f"evt_{index + 1:03d}",
            "time": None,
            "location": None,
            "participants": [],
            "summary": str(item),
            "consequences": [],
            "participant_knowledge": {},
        }
    participant_knowledge = item.get("participant_knowledge", {})
    if not isinstance(participant_knowledge, dict):
        participant_knowledge = {"summary": str(participant_knowledge)}
    return {
        "id": str(item.get("id") or item.get("event_id") or f"evt_{index + 1:03d}"),
        "time": item.get("time"),
        "location": item.get("location"),
        "participants": _string_list(item.get("participants", item.get("affected_agents", []))),
        "summary": str(item.get("summary") or item.get("description") or ""),
        "consequences": _string_list(item.get("consequences", item.get("effects", []))),
        "participant_knowledge": participant_knowledge,
    }


def _normalize_theme_record(item: Any) -> dict[str, Any]:
    if isinstance(item, str):
        return {"name": item, "description": "", "confidence": ""}
    if not isinstance(item, dict):
        return {"name": str(item), "description": "", "confidence": ""}
    return {
        "name": str(item.get("name") or item.get("theme") or ""),
        "description": str(item.get("description") or item.get("summary") or ""),
        "confidence": str(item.get("confidence") or ""),
    }


def _normalize_sample_passage(item: Any) -> dict[str, Any]:
    if isinstance(item, str):
        return {"text": item, "why_representative": ""}
    if not isinstance(item, dict):
        return {"text": str(item), "why_representative": ""}
    return {
        "text": str(item.get("text") or item.get("passage") or ""),
        "why_representative": str(
            item.get("why_representative") or item.get("reason") or ""
        ),
    }


def _normalize_character_voice_record(item: Any, index: int) -> dict[str, Any]:
    if not isinstance(item, dict):
        return {
            "character_id": f"character_{index + 1:03d}",
            "vocabulary_register": "",
            "speech_patterns": [],
            "rhetorical_tendencies": "",
            "gravitates_toward": [],
            "what_they_never_say": "",
            "emotional_register": "",
            "sample_dialogues": [],
        }
    return {
        "character_id": str(
            item.get("character_id") or item.get("character") or item.get("name") or f"character_{index + 1:03d}"
        ),
        "vocabulary_register": str(item.get("vocabulary_register") or ""),
        "speech_patterns": _string_list(item.get("speech_patterns", [])),
        "rhetorical_tendencies": str(item.get("rhetorical_tendencies") or ""),
        "gravitates_toward": _string_list(item.get("gravitates_toward", [])),
        "what_they_never_say": str(item.get("what_they_never_say") or ""),
        "emotional_register": str(item.get("emotional_register") or ""),
        "sample_dialogues": [
            _normalize_sample_passage(sample)
            for sample in _ensure_list(item.get("sample_dialogues", []))
        ],
    }


def _normalize_entity_record(item: Any, index: int) -> dict[str, Any]:
    if not isinstance(item, dict):
        return {
            "entity_id": f"entity_{index + 1:03d}",
            "name": str(item),
            "type": "concept",
            "objective_facts": [],
            "narrative_role": "",
            "absent_figure_details": {},
            "concept_details": {},
            "agent_representations": [],
        }
    absent_figure_details = item.get("absent_figure_details", {})
    if not isinstance(absent_figure_details, dict):
        absent_figure_details = {"reason_absent": str(absent_figure_details)}
    concept_details = item.get("concept_details", {})
    if not isinstance(concept_details, dict):
        concept_details = {"authorial_stance": str(concept_details)}
    concept_details["definitions_by_character"] = (
        concept_details.get("definitions_by_character", {})
        if isinstance(concept_details.get("definitions_by_character", {}), dict)
        else {}
    )
    concept_details["who_weaponizes"] = _string_list(
        concept_details.get("who_weaponizes", [])
    )
    concept_details["who_is_bound_by"] = _string_list(
        concept_details.get("who_is_bound_by", [])
    )
    return {
        "entity_id": str(item.get("entity_id") or item.get("id") or f"entity_{index + 1:03d}"),
        "name": str(item.get("name") or item.get("entity_id") or ""),
        "type": str(item.get("type") or "concept"),
        "objective_facts": _string_list(item.get("objective_facts", item.get("facts", []))),
        "narrative_role": str(item.get("narrative_role") or item.get("role") or ""),
        "absent_figure_details": absent_figure_details,
        "concept_details": concept_details,
        "agent_representations": [
            _normalize_entity_representation(rep)
            for rep in _ensure_list(
                item.get("agent_representations", item.get("representations", []))
            )
        ],
    }


def _normalize_entity_representation(item: Any) -> dict[str, Any]:
    if not isinstance(item, dict):
        return {
            "agent_id": "",
            "belief": str(item),
            "emotional_charge": "",
            "goal_relevance": "",
            "misunderstanding": "",
            "confidence": "",
        }
    return {
        "agent_id": str(item.get("agent_id") or item.get("character_id") or item.get("name") or ""),
        "belief": str(item.get("belief") or ""),
        "emotional_charge": str(item.get("emotional_charge") or ""),
        "goal_relevance": str(item.get("goal_relevance") or ""),
        "misunderstanding": str(item.get("misunderstanding") or ""),
        "confidence": str(item.get("confidence") or ""),
    }


def _normalize_narrative_thread_payload(item: Any, index: int) -> dict[str, Any]:
    if isinstance(item, str):
        description = item.strip()
        return {
            "thread_id": description or f"thread_{index + 1:03d}",
            "description": description,
            "agents_involved": [],
            "urgency": "",
            "resolution_condition": "",
        }
    if not isinstance(item, dict):
        return {
            "thread_id": f"thread_{index + 1:03d}",
            "description": str(item),
            "agents_involved": [],
            "urgency": "",
            "resolution_condition": "",
        }
    return {
        "thread_id": str(
            item.get("thread_id")
            or item.get("id")
            or item.get("description")
            or f"thread_{index + 1:03d}"
        ),
        "description": str(
            item.get("description")
            or item.get("summary")
            or item.get("thread_id")
            or ""
        ),
        "agents_involved": list(item.get("agents_involved") or item.get("participants") or []),
        "urgency": str(item.get("urgency") or ""),
        "resolution_condition": str(
            item.get("resolution_condition")
            or item.get("exit_condition")
            or ""
        ),
    }


def _normalize_approaching_node_payload(item: Any) -> dict[str, Any]:
    if isinstance(item, str):
        return {
            "description": item.strip(),
            "agents_involved": [],
            "estimated_ticks_away": 0,
            "estimated_salience": 0.0,
        }
    if not isinstance(item, dict):
        return {
            "description": str(item),
            "agents_involved": [],
            "estimated_ticks_away": 0,
            "estimated_salience": 0.0,
        }
    return {
        "description": str(item.get("description") or item.get("summary") or ""),
        "agents_involved": list(item.get("agents_involved") or item.get("participants") or []),
        "estimated_ticks_away": int(
            round(_coerce_float(item.get("estimated_ticks_away") or item.get("ticks_away"), default=0.0))
        ),
        "estimated_salience": max(
            0.0,
            min(1.0, _coerce_float(item.get("estimated_salience") or item.get("salience"), default=0.0)),
        ),
    }


def _normalize_background_agent_outcome(item: Any, index: int) -> dict[str, str]:
    if not isinstance(item, dict):
        return {
            "agent_id": f"agent_{index + 1:03d}",
            "goal_status": "",
            "new_knowledge": "",
            "emotional_delta": str(item),
        }
    return {
        "agent_id": str(item.get("agent_id") or item.get("character_id") or f"agent_{index + 1:03d}"),
        "goal_status": str(item.get("goal_status") or item.get("status") or ""),
        "new_knowledge": str(item.get("new_knowledge") or ""),
        "emotional_delta": str(item.get("emotional_delta") or item.get("emotion") or ""),
    }


def _normalize_state_update_relationship_payload(target_id: str, payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        payload = {}
    return {
        "target_id": str(payload.get("target_id") or payload.get("target") or target_id),
        "trust_delta": _coerce_float(payload.get("trust_delta"), default=0.0),
        "sentiment_shift": str(payload.get("sentiment_shift") or payload.get("status") or payload.get("change") or ""),
        "pinned": bool(payload.get("pinned", False)),
        "pin_reason": str(payload.get("pin_reason") or payload.get("note") or payload.get("reasoning") or ""),
    }


def _first_string(value: Any) -> str | None:
    if isinstance(value, list):
        for item in value:
            if isinstance(item, str) and item.strip():
                return item
    if isinstance(value, str) and value.strip():
        return value
    return None


_PRIMARY_LANGUAGE_RE = re.compile(r"Primary language:\s*(.+)")
_CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
_LATIN_WORD_RE = re.compile(r"[A-Za-z]{2,}")


def _validate_language_expectations(
    data: Any,
    schema: type[BaseModel],
    prompt: PromptRequest,
) -> None:
    primary_language = _extract_primary_language(prompt.user)
    if not _requires_cjk_output(primary_language):
        return
    offenders = [
        value
        for value in _collect_language_sensitive_strings(data, schema)
        if _looks_like_english_when_cjk_expected(value)
    ]
    if offenders:
        raise ValueError(
            "Free-text fields must stay in the source language "
            f"({primary_language}); found likely English text: {offenders[0][:120]}"
        )


def _extract_primary_language(prompt_user: str) -> str:
    match = _PRIMARY_LANGUAGE_RE.search(prompt_user)
    if not match:
        return ""
    return match.group(1).strip()


def _requires_cjk_output(primary_language: str) -> bool:
    lowered = primary_language.lower()
    return (
        "chinese" in lowered
        or "中文" in primary_language
        or "简体" in primary_language
        or "繁体" in primary_language
    )


def _looks_like_english_when_cjk_expected(text: str) -> bool:
    cleaned = str(text or "").strip()
    if not cleaned:
        return False
    if _CJK_RE.search(cleaned):
        return False
    latin_words = _LATIN_WORD_RE.findall(cleaned)
    if len(latin_words) >= 2 and sum(len(word) for word in latin_words) >= 10:
        return True
    if "_" in cleaned and sum(len(word) for word in latin_words) >= 8:
        return True
    return False


def _collect_language_sensitive_strings(data: Any, schema: type[BaseModel]) -> list[str]:
    if not isinstance(data, dict):
        return []
    if schema is StructuralScanPayload:
        return _strings_from_structural_scan_payload(data)
    if schema is AccumulatedExtraction:
        return _strings_from_accumulated_extraction_payload(data)
    if schema is TrajectoryProjectionPayload:
        return _strings_from_trajectory_payload(data)
    if schema is BatchedTrajectoryProjectionPayload:
        projections = data.get("projections", {})
        strings: list[str] = []
        if isinstance(projections, dict):
            for payload in projections.values():
                if isinstance(payload, dict):
                    strings.extend(_strings_from_trajectory_payload(payload))
        return strings
    if schema is GoalCollisionBatchPayload:
        return _strings_from_goal_collision_payload(data)
    if schema is BackgroundEventPayload:
        return _strings_from_background_event_payload(data)
    if schema is SceneSetupPayload:
        return _strings_from_scene_setup_payload(data)
    if schema is AgentBeatPayload:
        return _strings_from_agent_beat_payload(data)
    if schema is StateUpdatePayload:
        return _strings_from_state_update_payload(data)
    if schema is NarrativeArcUpdatePayload:
        return _strings_from_arc_update_payload(data)
    return []


def _strings_from_structural_scan_payload(data: dict[str, Any]) -> list[str]:
    strings: list[str] = []
    world = data.get("world", {})
    if isinstance(world, dict):
        strings.extend(
            [
                str(world.get("setting", "")),
                str(world.get("time_period", "")),
            ]
        )
        strings.extend(_string_list(world.get("rules_and_constraints", [])))
        for item in world.get("factions", []):
            if not isinstance(item, dict):
                continue
            strings.extend(
                [
                    str(item.get("name", "")),
                    str(item.get("goal", "")),
                ]
            )
            relationships = item.get("relationships", {})
            if isinstance(relationships, dict):
                strings.extend(str(value) for value in relationships.values())
        for item in world.get("key_locations", []):
            if not isinstance(item, dict):
                continue
            strings.extend(
                [
                    str(item.get("name", "")),
                    str(item.get("description", "")),
                    str(item.get("narrative_significance", "")),
                ]
            )
    for item in data.get("cast_list", []):
        if not isinstance(item, dict):
            continue
        strings.extend(
            [
                str(item.get("name", "")),
                str(item.get("role", "")),
                str(item.get("first_appearance", "")),
            ]
        )
        strings.extend(_string_list(item.get("aliases", [])))
    timeline = data.get("timeline_skeleton", {})
    if isinstance(timeline, dict):
        strings.append(str(timeline.get("story_start", "")))
        strings.extend(_string_list(timeline.get("pre_story_events", [])))
        strings.extend(_string_list(timeline.get("known_future_events", [])))
    for item in data.get("domain_systems", []):
        if not isinstance(item, dict):
            continue
        strings.extend(
            [
                str(item.get("name", "")),
                str(item.get("description", "")),
                str(item.get("scale", "")),
            ]
        )
    return strings


def _strings_from_accumulated_extraction_payload(data: dict[str, Any]) -> list[str]:
    strings: list[str] = []
    for item in data.get("characters", []):
        if not isinstance(item, dict):
            continue
        strings.append(str(item.get("name", "")))
        strings.extend(_string_list(item.get("aliases", [])))
        strings.extend(_string_values(item.get("identity", {})))
        strings.extend(_string_values(item.get("personality", {})))
        state = item.get("current_state", {})
        if isinstance(state, dict):
            strings.extend(
                [
                    str(state.get("emotional_state", "")),
                    str(state.get("physical_state", "")),
                    str(state.get("location", "")),
                ]
            )
            strings.extend(_string_list(state.get("goal_stack", [])))
        for relationship in item.get("relationships", []):
            if not isinstance(relationship, dict):
                continue
            strings.extend(
                [
                    str(relationship.get("type", "")),
                    str(relationship.get("sentiment", "")),
                    str(relationship.get("shared_history_summary", "")),
                ]
            )
        strings.extend(_string_list(item.get("memory_seeds", [])))
    world = data.get("world", {})
    if isinstance(world, dict):
        strings.extend(
            [
                str(world.get("setting", "")),
                str(world.get("time_period", "")),
            ]
        )
        strings.extend(_string_list(world.get("locations", [])))
        strings.extend(_string_list(world.get("rules_and_constraints", [])))
        strings.extend(_string_list(world.get("factions", [])))
    for item in data.get("events", []):
        if not isinstance(item, dict):
            continue
        strings.extend(
            [
                str(item.get("time", "")),
                str(item.get("location", "")),
                str(item.get("summary", "")),
            ]
        )
        strings.extend(_string_list(item.get("consequences", [])))
        strings.extend(_string_values(item.get("participant_knowledge", {})))
    for item in data.get("entities", []):
        if not isinstance(item, dict):
            continue
        strings.extend(
            [
                str(item.get("name", "")),
                str(item.get("narrative_role", "")),
            ]
        )
        strings.extend(_string_list(item.get("objective_facts", [])))
        absent = item.get("absent_figure_details", {})
        if isinstance(absent, dict):
            strings.extend(
                [
                    str(absent.get("reason_absent", "")),
                    str(absent.get("counterfactual", "")),
                ]
            )
        concept = item.get("concept_details", {})
        if isinstance(concept, dict):
            strings.extend(_string_values(concept.get("definitions_by_character", {})))
            strings.append(str(concept.get("authorial_stance", "")))
        for representation in item.get("agent_representations", []):
            if not isinstance(representation, dict):
                continue
            strings.extend(
                [
                    str(representation.get("belief", "")),
                    str(representation.get("emotional_charge", "")),
                    str(representation.get("goal_relevance", "")),
                    str(representation.get("misunderstanding", "")),
                ]
            )
    return strings


def _string_values(value: Any) -> list[str]:
    strings: list[str] = []
    if isinstance(value, dict):
        for item in value.values():
            strings.extend(_string_values(item))
        return strings
    if isinstance(value, list):
        for item in value:
            strings.extend(_string_values(item))
        return strings
    if isinstance(value, str):
        strings.append(value)
    return strings


def _strings_from_trajectory_payload(data: dict[str, Any]) -> list[str]:
    strings = [
        str(data.get("primary_intention", "")),
        str(data.get("motivation", "")),
        str(data.get("immediate_next_action", "")),
        str(data.get("greatest_fear_this_horizon", "")),
        str(data.get("abandon_condition", "")),
        str(data.get("held_back_impulse", "")),
    ]
    contingencies = data.get("contingencies", [])
    if isinstance(contingencies, list):
        for item in contingencies:
            if not isinstance(item, dict):
                continue
            strings.append(str(item.get("trigger", "")))
            strings.append(str(item.get("response", "")))
    return strings


def _strings_from_goal_collision_payload(data: dict[str, Any]) -> list[str]:
    strings: list[str] = []
    for item in data.get("goal_tensions", []):
        if not isinstance(item, dict):
            continue
        strings.extend(
            [
                str(item.get("location", "")),
                str(item.get("description", "")),
            ]
        )
        info = item.get("information_asymmetry", {})
        if isinstance(info, dict):
            strings.extend(str(value) for value in info.values())
        stakes = item.get("stakes", {})
        if isinstance(stakes, dict):
            strings.extend(str(value) for value in stakes.values())
        factors = item.get("salience_factors", [])
        if isinstance(factors, list):
            strings.extend(str(value) for value in factors)
    for item in data.get("solo_seeds", []):
        if not isinstance(item, dict):
            continue
        strings.extend([str(item.get("trigger", "")), str(item.get("description", ""))])
    for item in data.get("world_events", []):
        if not isinstance(item, dict):
            continue
        strings.append(str(item.get("description", "")))
    return strings


def _strings_from_background_event_payload(data: dict[str, Any]) -> list[str]:
    strings = [str(data.get("narrative_summary", "")), str(data.get("unexpected", ""))]
    for item in data.get("outcomes", []):
        if not isinstance(item, dict):
            continue
        strings.extend(
            [
                str(item.get("new_knowledge", "")),
                str(item.get("emotional_delta", "")),
            ]
        )
    for item in data.get("relationship_deltas", []):
        if isinstance(item, dict):
            strings.append(str(item.get("change", "")))
    return strings


def _strings_from_scene_setup_payload(data: dict[str, Any]) -> list[str]:
    strings = [
        str(data.get("scene_opening", "")),
        str(data.get("tension_signature", "")),
    ]
    resolution = data.get("resolution_conditions", {})
    if isinstance(resolution, dict):
        strings.extend(str(value) for value in resolution.values())
    perceptions = data.get("agent_perceptions", {})
    if isinstance(perceptions, dict):
        strings.extend(str(value) for value in perceptions.values())
    return strings


def _strings_from_agent_beat_payload(data: dict[str, Any]) -> list[str]:
    strings = [str(data.get("held_back", ""))]
    for section_key in ("internal", "external"):
        section = data.get(section_key, {})
        if isinstance(section, dict):
            strings.extend(str(value) for value in section.values())
    return strings


def _strings_from_state_update_payload(data: dict[str, Any]) -> list[str]:
    strings: list[str] = []
    emotional = data.get("emotional_delta", {})
    if isinstance(emotional, dict):
        strings.extend(str(value) for value in emotional.values())
    goal_stack_update = data.get("goal_stack_update", {})
    if isinstance(goal_stack_update, dict):
        new_goal = goal_stack_update.get("new_goal")
        if isinstance(new_goal, dict):
            strings.extend(
                [
                    str(new_goal.get("goal", "")),
                    str(new_goal.get("motivation", "")),
                    str(new_goal.get("obstacle", "")),
                    str(new_goal.get("emotional_charge", "")),
                    str(new_goal.get("abandon_condition", "")),
                ]
            )
        strings.append(str(goal_stack_update.get("resolved_goal", "")))
    for item in data.get("relationship_updates", []):
        if not isinstance(item, dict):
            continue
        strings.extend(
            [
                str(item.get("sentiment_shift", "")),
                str(item.get("pin_reason", "")),
            ]
        )
    strings.append(str(data.get("reprojection_reason", "")))
    return strings


def _strings_from_arc_update_payload(data: dict[str, Any]) -> list[str]:
    strings = [
        str(data.get("phase_change_reason", "")),
        str(data.get("tension_reason", "")),
    ]
    for item in data.get("unresolved_threads", []):
        if not isinstance(item, dict):
            continue
        strings.extend(
            [
                str(item.get("description", "")),
                str(item.get("resolution_condition", "")),
            ]
        )
    for item in data.get("approaching_nodes", []):
        if isinstance(item, dict):
            strings.append(str(item.get("description", "")))
    drift = data.get("narrative_drift", {})
    if isinstance(drift, dict):
        strings.extend(
            [
                str(drift.get("drift_description", "")),
                str(drift.get("suggested_correction", "")),
            ]
        )
    return strings
