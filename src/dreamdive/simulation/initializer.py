from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Callable, List, Optional, Protocol, Sequence

from dreamdive.schemas import (
    BatchedUnifiedInitPayload,
    CharacterIdentity,
    CharacterSnapshot,
    EpisodicMemory,
    GoalSeedPayload,
    GoalStackSnapshot,
    JSONValue,
    RelationshipLogEntry,
    ReplayKey,
    SnapshotInference,
    StateChangeLogEntry,
    UnifiedInitPayload,
)
from dreamdive.simulation.bootstrap import SnapshotBootstrapper
from dreamdive.simulation.prompts import (
    build_batched_unified_init_prompt,
    build_goal_seed_prompt,
    build_snapshot_inference_prompt,
    build_unified_init_prompt,
)
from dreamdive.simulation.state_normalization import normalize_current_state


@dataclass
class SnapshotInitializationInput:
    identity: CharacterIdentity
    replay_key: ReplayKey
    text_excerpt: str
    event_summary_up_to_t: List[str]
    nearby_characters: List[str]
    state_entries: Sequence[StateChangeLogEntry]
    memories: Sequence[EpisodicMemory]
    relationships: Sequence[RelationshipLogEntry]
    goal_hints: Optional[List[str]] = None
    language_guidance: str = ""
    default_state: Optional[dict[str, JSONValue]] = None


class SnapshotInitializer:
    def __init__(
        self,
        llm_client,
        bootstrapper: Optional[SnapshotBootstrapper] = None,
    ) -> None:
        self.llm_client = llm_client
        self.bootstrapper = bootstrapper or SnapshotBootstrapper()

    def initialize(
        self,
        payload: SnapshotInitializationInput,
        *,
        progress_callback: Callable[[dict[str, object]], None] | None = None,
    ) -> CharacterSnapshot:
        goal_hints = list(payload.goal_hints or [])
        base_snapshot = self.bootstrapper.build_snapshot(
            identity=payload.identity,
            replay_key=payload.replay_key,
            state_entries=payload.state_entries,
            goal_stack=None,
            memories=payload.memories,
            relationships=payload.relationships,
            default_state=payload.default_state,
        )
        inference_prompt = build_snapshot_inference_prompt(
            identity=payload.identity,
            text_excerpt=payload.text_excerpt,
            event_summary_up_to_t=payload.event_summary_up_to_t,
            location=str(base_snapshot.current_state.get("location", "")),
            nearby_characters=payload.nearby_characters,
            language_guidance=payload.language_guidance,
        )
        self._emit_progress(
            progress_callback,
            stage="snapshot_inference",
            character_id=payload.identity.character_id,
            character_name=payload.identity.name,
        )
        try:
            inferred_state = asyncio.run(
                self.llm_client.call_json(inference_prompt, SnapshotInference)
            )
        except Exception:
            self._emit_progress(
                progress_callback,
                stage="snapshot_inference_fallback",
                character_id=payload.identity.character_id,
                character_name=payload.identity.name,
            )
            inferred_state = self._fallback_snapshot_inference(
                snapshot=base_snapshot,
                payload=payload,
            )

        goal_prompt = build_goal_seed_prompt(
            identity=payload.identity,
            inferred_state=inferred_state,
            recent_events=payload.event_summary_up_to_t,
            relationships=list(payload.relationships),
            language_guidance=payload.language_guidance,
        )
        self._emit_progress(
            progress_callback,
            stage="goal_seeding",
            character_id=payload.identity.character_id,
            character_name=payload.identity.name,
        )
        try:
            goal_seed = asyncio.run(self.llm_client.call_json(goal_prompt, GoalSeedPayload))
        except Exception:
            self._emit_progress(
                progress_callback,
                stage="goal_seeding_fallback",
                character_id=payload.identity.character_id,
                character_name=payload.identity.name,
            )
            goal_seed = self._fallback_goal_seed(
                payload=payload,
                inferred_state=inferred_state,
                goal_hints=goal_hints,
            )
        goal_stack = GoalStackSnapshot(
            character_id=payload.identity.character_id,
            replay_key=payload.replay_key,
            goals=goal_seed.goal_stack,
            actively_avoiding=goal_seed.actively_avoiding,
            most_uncertain_relationship=goal_seed.most_uncertain_relationship,
        )
        snapshot = self.bootstrapper.build_snapshot(
            identity=payload.identity,
            replay_key=payload.replay_key,
            state_entries=payload.state_entries,
            goal_stack=goal_stack,
            memories=payload.memories,
            relationships=payload.relationships,
            inferred_state=inferred_state,
            default_state=payload.default_state,
        )
        return snapshot.model_copy(
            update={
                "current_state": normalize_current_state(
                    snapshot.current_state,
                    inferred_state,
                )
            }
        )

    def initialize_unified(
        self,
        payload: SnapshotInitializationInput,
        *,
        progress_callback: Callable[[dict[str, object]], None] | None = None,
    ) -> CharacterSnapshot:
        """Initialize a character with a single LLM call (snapshot inference + goal seeding).

        Falls back to the two-call ``initialize()`` path if the unified call fails.
        """
        goal_hints = list(payload.goal_hints or [])
        base_snapshot = self.bootstrapper.build_snapshot(
            identity=payload.identity,
            replay_key=payload.replay_key,
            state_entries=payload.state_entries,
            goal_stack=None,
            memories=payload.memories,
            relationships=payload.relationships,
            default_state=payload.default_state,
        )
        location = str(base_snapshot.current_state.get("location", ""))

        unified_prompt = build_unified_init_prompt(
            identity=payload.identity,
            text_excerpt=payload.text_excerpt,
            event_summary_up_to_t=payload.event_summary_up_to_t,
            location=location,
            nearby_characters=payload.nearby_characters,
            relationships=list(payload.relationships),
            language_guidance=payload.language_guidance,
        )

        self._emit_progress(
            progress_callback,
            stage="unified_init",
            character_id=payload.identity.character_id,
            character_name=payload.identity.name,
        )

        try:
            unified = asyncio.run(
                self.llm_client.call_json(unified_prompt, UnifiedInitPayload)
            )
            inferred_state = unified.to_snapshot_inference()
            goal_seed = unified.to_goal_seed()
        except Exception:
            self._emit_progress(
                progress_callback,
                stage="unified_init_fallback",
                character_id=payload.identity.character_id,
                character_name=payload.identity.name,
            )
            # Fall back to two-call path
            return self.initialize(payload, progress_callback=progress_callback)

        goal_stack = GoalStackSnapshot(
            character_id=payload.identity.character_id,
            replay_key=payload.replay_key,
            goals=goal_seed.goal_stack,
            actively_avoiding=goal_seed.actively_avoiding,
            most_uncertain_relationship=goal_seed.most_uncertain_relationship,
        )
        snapshot = self.bootstrapper.build_snapshot(
            identity=payload.identity,
            replay_key=payload.replay_key,
            state_entries=payload.state_entries,
            goal_stack=goal_stack,
            memories=payload.memories,
            relationships=payload.relationships,
            inferred_state=inferred_state,
            default_state=payload.default_state,
        )
        return snapshot.model_copy(
            update={
                "current_state": normalize_current_state(
                    snapshot.current_state,
                    inferred_state,
                )
            }
        )

    def initialize_batch(
        self,
        payloads: List[SnapshotInitializationInput],
        *,
        progress_callback: Callable[[dict[str, object]], None] | None = None,
    ) -> List[CharacterSnapshot]:
        """Initialize multiple characters in a single batched LLM call.

        If the batched call fails, falls back to per-character ``initialize_unified()``
        calls. If a character is missing from the batch result, that character is
        initialized individually via ``initialize_unified()``.
        """
        if not payloads:
            return []

        # Build base snapshots to extract locations
        base_snapshots = {}
        for payload in payloads:
            base_snapshots[payload.identity.character_id] = self.bootstrapper.build_snapshot(
                identity=payload.identity,
                replay_key=payload.replay_key,
                state_entries=payload.state_entries,
                goal_stack=None,
                memories=payload.memories,
                relationships=payload.relationships,
                default_state=payload.default_state,
            )

        character_blocks = []
        for payload in payloads:
            base = base_snapshots[payload.identity.character_id]
            location = str(base.current_state.get("location", ""))
            relationship_summary = [
                {
                    "target_id": item.to_character_id,
                    "summary": item.summary,
                    "reason": item.reason,
                }
                for item in payload.relationships
            ]
            character_blocks.append({
                "character_id": payload.identity.character_id,
                "identity": payload.identity.model_dump(mode="json"),
                "text_excerpt": payload.text_excerpt,
                "event_summary": payload.event_summary_up_to_t,
                "location": location,
                "nearby_characters": payload.nearby_characters,
                "relationships": relationship_summary,
            })

        self._emit_progress(
            progress_callback,
            stage="batched_unified_init",
            character_count=len(payloads),
        )

        batch_prompt = build_batched_unified_init_prompt(
            character_blocks=character_blocks,
            language_guidance=payloads[0].language_guidance if payloads else "",
        )

        try:
            batch_result = asyncio.run(
                self.llm_client.call_json(batch_prompt, BatchedUnifiedInitPayload)
            )
        except Exception:
            self._emit_progress(
                progress_callback,
                stage="batched_unified_init_fallback",
                character_count=len(payloads),
            )
            # Fall back to per-character unified calls
            return [
                self.initialize_unified(p, progress_callback=progress_callback)
                for p in payloads
            ]

        # Assemble snapshots from batch result, falling back per-character on missing keys
        results: List[CharacterSnapshot] = []
        for payload in payloads:
            cid = payload.identity.character_id
            unified = batch_result.characters.get(cid)
            if unified is None:
                results.append(
                    self.initialize_unified(payload, progress_callback=progress_callback)
                )
                continue

            inferred_state = unified.to_snapshot_inference()
            goal_seed = unified.to_goal_seed()
            goal_stack = GoalStackSnapshot(
                character_id=cid,
                replay_key=payload.replay_key,
                goals=goal_seed.goal_stack,
                actively_avoiding=goal_seed.actively_avoiding,
                most_uncertain_relationship=goal_seed.most_uncertain_relationship,
            )
            snapshot = self.bootstrapper.build_snapshot(
                identity=payload.identity,
                replay_key=payload.replay_key,
                state_entries=payload.state_entries,
                goal_stack=goal_stack,
                memories=payload.memories,
                relationships=payload.relationships,
                inferred_state=inferred_state,
                default_state=payload.default_state,
            )
            results.append(
                snapshot.model_copy(
                    update={
                        "current_state": normalize_current_state(
                            snapshot.current_state,
                            inferred_state,
                        )
                    }
                )
            )
        return results

    @staticmethod
    def _emit_progress(
        progress_callback: Callable[[dict[str, object]], None] | None,
        **event: object,
    ) -> None:
        if progress_callback is None:
            return
        progress_callback(event)

    @staticmethod
    def _fallback_snapshot_inference(
        *,
        snapshot: CharacterSnapshot,
        payload: SnapshotInitializationInput,
    ) -> SnapshotInference:
        current_state = dict(snapshot.current_state or {})
        dominant = str(current_state.get("emotional_state", "") or "").strip()
        if not dominant:
            dominant = SnapshotInitializer._localized_default(
                payload.language_guidance,
                zh="情绪未明但保持警觉",
                en="emotionally uncertain but alert",
            )
        latest_event = next(
            (item.strip() for item in reversed(payload.event_summary_up_to_t) if item.strip()),
            "",
        )
        immediate_tension = latest_event or SnapshotInitializer._localized_default(
            payload.language_guidance,
            zh="局势仍不明朗，需要先稳住局面",
            en="the situation is still unclear and needs stabilizing",
        )
        desire_or_fear = next(
            (
                item.strip()
                for item in [
                    *(payload.identity.desires or []),
                    *(payload.identity.fears or []),
                    *(payload.identity.values or []),
                ]
                if str(item).strip()
            ),
            "",
        )
        unspoken_subtext = desire_or_fear or SnapshotInitializer._localized_default(
            payload.language_guidance,
            zh="不愿暴露真实想法",
            en="does not want to reveal their real thoughts",
        )
        physical_state = str(current_state.get("physical_state", "") or "").strip()
        location = str(current_state.get("location", "") or "").strip()
        return SnapshotInference(
            emotional_summary=dominant,
            immediate_tension=immediate_tension,
            unspoken_subtext=unspoken_subtext,
            physical_status=physical_state,
            location=location,
            knowledge=[latest_event] if latest_event else [],
        )

    @staticmethod
    def _fallback_goal_seed(
        *,
        payload: SnapshotInitializationInput,
        inferred_state: SnapshotInference,
        goal_hints: List[str],
    ) -> GoalSeedPayload:
        goal_text = next(
            (
                item.strip()
                for item in [
                    *goal_hints,
                    *(payload.identity.desires or []),
                ]
                if str(item).strip()
            ),
            SnapshotInitializer._localized_default(
                payload.language_guidance,
                zh="先稳住局面",
                en="stabilize the situation first",
            ),
        )
        motivation = next(
            (
                item.strip()
                for item in [
                    *(payload.identity.desires or []),
                    *(payload.identity.values or []),
                    inferred_state.immediate_tension,
                ]
                if str(item).strip()
            ),
            SnapshotInitializer._localized_default(
                payload.language_guidance,
                zh="避免局势进一步恶化",
                en="prevent the situation from getting worse",
            ),
        )
        obstacle = inferred_state.immediate_tension or SnapshotInitializer._localized_default(
            payload.language_guidance,
            zh="局势不明",
            en="the situation remains unclear",
        )
        actively_avoiding = next(
            (
                item.strip()
                for item in [
                    *(payload.identity.fears or []),
                    inferred_state.unspoken_subtext,
                ]
                if str(item).strip()
            ),
            "",
        )
        most_uncertain_relationship = next(
            (item.strip() for item in payload.nearby_characters if str(item).strip()),
            "",
        )
        return GoalSeedPayload.model_validate(
            {
                "goal_stack": [
                    {
                        "priority": 1,
                        "description": f"{goal_text}; {motivation}; {inferred_state.emotional_summary}".strip("; "),
                        "challenge": obstacle,
                        "time_horizon": "immediate" if inferred_state.immediate_tension else "today",
                    }
                ],
                "actively_avoiding": actively_avoiding,
                "most_uncertain_relationship": most_uncertain_relationship,
            }
        )

    @staticmethod
    def _localized_default(language_guidance: str, *, zh: str, en: str) -> str:
        lowered = str(language_guidance or "").lower()
        if "chinese" in lowered or "中文" in language_guidance or "简体" in language_guidance or "繁体" in language_guidance:
            return zh
        return en
