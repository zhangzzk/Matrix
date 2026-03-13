from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence

from dreamdive.config import SimulationSettings
from dreamdive.debug import DebugSession
from dreamdive.db.replay import StateReplay, replay_sort_key
from dreamdive.language_guidance import build_language_guidance
from dreamdive.db.bundle import (
    RepositoryBundle,
    build_in_memory_bundle,
    build_repository_bundle,
)
from dreamdive.db.session import InMemoryStore
from dreamdive.ingestion.extractor import ArtifactStore, ChapterSource
from dreamdive.ingestion.models import AccumulatedExtraction, CharacterExtractionRecord
from dreamdive.ingestion.source_loader import load_chapters
from dreamdive.memory.retrieval import (
    build_entity_semantic_text,
    build_memory_semantic_text,
    embed_text,
    rank_memories,
)
from dreamdive.schemas import (
    CharacterIdentity,
    EpisodicMemory,
    GoalStackSnapshot,
    Goal,
    NarrativeArcState,
    RelationshipLogEntry,
    ReplayKey,
    StateChangeLogEntry,
    SubjectiveEntityRepresentation,
    WorldSnapshot,
)
from dreamdive.simulation.event_simulator import EventSimulator
from dreamdive.simulation.goal_collision import GoalCollisionDetector
from dreamdive.simulation.initializer import SnapshotInitializationInput, SnapshotInitializer
from dreamdive.simulation.background_runner import BackgroundMaintenanceRunner
from dreamdive.simulation.background_queue_backend import SessionBackgroundQueueBackend
from dreamdive.simulation.session import AgentRuntimeState, SimulationSessionState
from dreamdive.simulation.state_updater import EventStateUpdater
from dreamdive.simulation.state_normalization import normalize_current_state
from dreamdive.simulation.tick_runner import AgentRuntime, SimulationTickRunner
from dreamdive.simulation.trajectory import TrajectoryProjector
from dreamdive.simulation.language_validation import require_language_guidance
from dreamdive.simulation.world_events import ScheduledWorldEvent, WorldEventScheduler
from dreamdive.simulation.world_manager import WorldManager
from dreamdive.simulation.seed_detector import SeedDetector


def build_world_manager(settings: SimulationSettings) -> WorldManager:
    return WorldManager(
        spotlight_min_minutes=settings.tick_spotlight_min_minutes,
        spotlight_max_minutes=settings.tick_spotlight_max_minutes,
        foreground_min_minutes=settings.tick_foreground_min_minutes,
        foreground_max_minutes=settings.tick_foreground_max_minutes,
        background_min_minutes=settings.tick_background_min_minutes,
        background_max_minutes=settings.tick_background_max_minutes,
        spotlight_threshold=settings.salience_spotlight_threshold,
        foreground_threshold=settings.salience_foreground_threshold,
    )


def load_accumulated_extraction(workspace_dir: Path, chapter_id: str | None = None) -> AccumulatedExtraction:
    artifact_store = ArtifactStore(workspace_dir / "artifacts")
    if chapter_id is None:
        chapter_dir = artifact_store.base_dir / "chapters"
        if not chapter_dir.exists():
            return AccumulatedExtraction()
        files = sorted(chapter_dir.glob("*.json"))
        if not files:
            return AccumulatedExtraction()
        data = json.loads(files[-1].read_text(encoding="utf-8"))
        accumulated = AccumulatedExtraction.model_validate(data)
        return merge_derived_artifacts(accumulated, artifact_store)

    chapter_dir = artifact_store.base_dir / "chapters"
    target = None
    for path in sorted(chapter_dir.glob("*.json")):
        if path.stem.endswith("_" + chapter_id):
            target = path
            break
    if target is None:
        raise FileNotFoundError(f"No accumulated extraction snapshot found for chapter {chapter_id}")
    data = json.loads(target.read_text(encoding="utf-8"))
    accumulated = AccumulatedExtraction.model_validate(data)
    return merge_derived_artifacts(accumulated, artifact_store)


def merge_derived_artifacts(
    accumulated: AccumulatedExtraction,
    artifact_store: ArtifactStore,
) -> AccumulatedExtraction:
    meta = artifact_store.load_meta_layer()
    entities = artifact_store.load_entity_extraction()
    updates = {}
    if meta is not None:
        updates["meta"] = meta
    if entities is not None:
        updates["entities"] = entities.entities
    if not updates:
        return accumulated
    return accumulated.model_copy(update=updates)


def chapter_lookup(source_path: Path) -> Dict[str, ChapterSource]:
    return {chapter.chapter_id: chapter for chapter in load_chapters(source_path)}


def build_character_identity(record: CharacterExtractionRecord) -> CharacterIdentity:
    personality = record.personality or {}
    identity = record.identity or {}
    return CharacterIdentity(
        character_id=record.id,
        name=record.name,
        background=identity.get("background") or identity.get("role"),
        core_traits=list(personality.get("traits", [])),
        values=list(personality.get("values", [])),
        fears=list(personality.get("fears", [])),
        desires=list(personality.get("desires", [])),
        domain_attributes=dict(identity),
    )


def voice_samples_for_character(
    accumulated: AccumulatedExtraction,
    character_id: str,
    *,
    limit: int = 3,
) -> List[str]:
    for voice in accumulated.meta.character_voices:
        if voice.character_id != character_id:
            continue
        samples = [
            (
                f"Register: {voice.vocabulary_register}; "
                f"Patterns: {', '.join(voice.speech_patterns)}; "
                f"Never says: {voice.what_they_never_say}"
            ).strip()
        ]
        samples.extend(sample.text for sample in voice.sample_dialogues if sample.text)
        return [sample for sample in samples if sample][:limit]
    return []


def subjective_entities_for_character(
    accumulated: AccumulatedExtraction,
    character_id: str,
    *,
    limit: int = 5,
) -> List[SubjectiveEntityRepresentation]:
    relevant: List[SubjectiveEntityRepresentation] = []
    for entity in accumulated.entities:
        for representation in entity.agent_representations:
            if representation.agent_id != character_id:
                continue
            item = SubjectiveEntityRepresentation(
                agent_id=character_id,
                entity_id=entity.entity_id,
                name=entity.name,
                type=entity.type,
                narrative_role=entity.narrative_role,
                objective_facts=list(entity.objective_facts),
                belief=representation.belief,
                emotional_charge=representation.emotional_charge,
                goal_relevance=representation.goal_relevance,
                misunderstanding=representation.misunderstanding,
                confidence=representation.confidence,
            )
            item = item.model_copy(
                update={
                    "semantic_text": build_entity_semantic_text(item.model_dump(mode="json")),
                }
            )
            item = item.model_copy(
                update={"semantic_embedding": embed_text(item.semantic_text)}
            )
            relevant.append(item)
            break
    return relevant[:limit]


def writing_style_note(accumulated: AccumulatedExtraction) -> str:
    style = accumulated.meta.writing_style
    parts = [
        style.prose_description,
        style.sentence_rhythm,
        style.dialogue_narration_balance,
    ]
    return "; ".join(part for part in parts if part)


def build_state_entries(record: CharacterExtractionRecord, replay_key: ReplayKey) -> List[StateChangeLogEntry]:
    state = record.current_state
    entries: List[StateChangeLogEntry] = []
    if state.location:
        entries.append(
            StateChangeLogEntry(
                character_id=record.id,
                dimension="location",
                replay_key=replay_key,
                to_value=state.location,
            )
        )
    if state.emotional_state:
        entries.append(
            StateChangeLogEntry(
                character_id=record.id,
                dimension="emotional_state",
                replay_key=replay_key,
                to_value=state.emotional_state,
            )
        )
    if state.physical_state:
        entries.append(
            StateChangeLogEntry(
                character_id=record.id,
                dimension="physical_state",
                replay_key=replay_key,
                to_value=state.physical_state,
            )
        )
    return entries


def build_relationship_entries(
    record: CharacterExtractionRecord,
    replay_key: ReplayKey,
) -> List[RelationshipLogEntry]:
    entries: List[RelationshipLogEntry] = []
    for relation in record.relationships:
        entries.append(
            RelationshipLogEntry(
                from_character_id=record.id,
                to_character_id=relation.target_id,
                replay_key=replay_key,
                trust_delta=0.0,
                trust_value=relation.trust or 0.0,
                sentiment_shift=relation.sentiment or "",
                reason=relation.shared_history_summary or "",
            )
        )
    return entries


def chapter_event_summaries(
    accumulated: AccumulatedExtraction,
    character_id: str,
    limit: int = 5,
) -> List[str]:
    summaries = [
        event.summary
        for event in accumulated.events
        if character_id in event.participants or not event.participants
    ]
    return summaries[-limit:]


def build_initial_memories(
    accumulated: AccumulatedExtraction,
    record: CharacterExtractionRecord,
    replay_key: ReplayKey,
) -> List[EpisodicMemory]:
    seeded: List[EpisodicMemory] = []
    seen_summaries: set[str] = set()
    for summary in list(record.memory_seeds) + chapter_event_summaries(accumulated, record.id, limit=5):
        cleaned = summary.strip()
        if not cleaned or cleaned in seen_summaries:
            continue
        seen_summaries.add(cleaned)
        seeded.append(
            EpisodicMemory(
                character_id=record.id,
                replay_key=replay_key,
                summary=cleaned,
                location=record.current_state.location,
                salience=0.45,
                pinned=False,
                embedding=embed_text(
                    build_memory_semantic_text(
                        EpisodicMemory(
                            character_id=record.id,
                            replay_key=replay_key,
                            summary=cleaned,
                            location=record.current_state.location,
                            salience=0.45,
                            pinned=False,
                        )
                    )
                ),
            )
        )
    return seeded


def schedule_events_from_extraction(
    accumulated: AccumulatedExtraction,
    *,
    start_timeline_index: int,
) -> List[ScheduledWorldEvent]:
    scheduled: List[ScheduledWorldEvent] = []
    for index, event in enumerate(accumulated.events):
        if not event.participants:
            continue
        scheduled.append(
            ScheduledWorldEvent(
                event_id=event.id or f"world_evt_{index + 1:03d}",
                trigger_timeline_index=start_timeline_index + ((index + 1) * 60),
                description=event.summary,
                affected_agents=list(event.participants),
                urgency="low",
                location=event.location or "",
            )
        )
    return scheduled


def restore_bundle_from_session(
    bundle: RepositoryBundle,
    session: SimulationSessionState,
) -> None:
    append_only_log = session.append_only_log or {}
    suppressed = {
        agent_id: set(event_ids)
        for agent_id, event_ids in dict(session.metadata.get("suppressed_memory_ids_by_agent", {})).items()
    }

    for item in append_only_log.get("state_changes", []):
        bundle.state_repo.append(StateChangeLogEntry.model_validate(item))
    for item in append_only_log.get("goal_stacks", []):
        bundle.goal_repo.append(GoalStackSnapshot.model_validate(item))
    for item in append_only_log.get("relationships", []):
        bundle.relationship_repo.append(RelationshipLogEntry.model_validate(item))
    for item in append_only_log.get("episodic_memories", []):
        memory = EpisodicMemory.model_validate(item)
        if memory.event_id and memory.event_id in suppressed.get(memory.character_id, set()):
            continue
        bundle.memory_repo.append(memory)
    for item in append_only_log.get("entity_representations", []):
        bundle.entity_repo.append(SubjectiveEntityRepresentation.model_validate(item))
    for item in append_only_log.get("world_snapshots", []):
        bundle.world_snapshot_repo.append(WorldSnapshot.model_validate(item))
    for item in append_only_log.get("event_log", []):
        replay_key = ReplayKey(
            tick=item["tick"],
            timeline_index=item["timeline_index"],
            event_sequence=item.get("event_sequence", 0),
        )
        bundle.event_log_repo.append(
            event_id=item["event_id"],
            replay_key=replay_key,
            seed_type=item["seed_type"],
            location=item.get("location", ""),
            participants=item.get("participants", []),
            description=item.get("description", ""),
            salience=item.get("salience", 0.0),
            outcome_summary=item.get("outcome_summary", ""),
            resolution_mode=item.get("resolution_mode", ""),
        )


def restore_store_from_session(
    store: InMemoryStore,
    session: SimulationSessionState,
) -> None:
    restore_bundle_from_session(build_in_memory_bundle(store), session)


def build_runtime_bundle(
    *,
    session: SimulationSessionState,
    settings: Optional[SimulationSettings] = None,
) -> RepositoryBundle:
    active_settings = settings or SimulationSettings()
    bundle = build_repository_bundle(active_settings)
    restore_bundle_from_session(bundle, session)
    return bundle


def serialize_store(store: InMemoryStore) -> Dict[str, List[dict]]:
    return {
        "state_changes": [
            StateChangeLogEntry(
                character_id=record.character_id,
                dimension=record.dimension,
                replay_key=ReplayKey(
                    tick=record.tick,
                    timeline_index=record.timeline_index,
                    event_sequence=record.event_sequence,
                ),
                event_id=record.event_id,
                from_value=record.from_value,
                to_value=record.to_value,
                trigger=record.trigger,
                emotional_tag=record.emotional_tag,
                pinned=record.pinned,
            ).model_dump(mode="json")
            for record in store.state_change_log
        ],
        "goal_stacks": [
            GoalStackSnapshot(
                character_id=record.character_id,
                replay_key=ReplayKey(
                    tick=record.tick,
                    timeline_index=record.timeline_index,
                    event_sequence=record.event_sequence,
                ),
                goals=[Goal.model_validate(goal) for goal in record.goals],
                actively_avoiding=record.actively_avoiding,
                most_uncertain_relationship=record.most_uncertain_relationship,
            ).model_dump(mode="json")
            for record in store.goal_stack
        ],
        "relationships": [
            RelationshipLogEntry(
                from_character_id=record.from_character_id,
                to_character_id=record.to_character_id,
                replay_key=ReplayKey(
                    tick=record.tick,
                    timeline_index=record.timeline_index,
                    event_sequence=record.event_sequence,
                ),
                event_id=record.event_id,
                trust_delta=record.trust_delta,
                trust_value=record.trust_value,
                sentiment_shift=record.sentiment_shift,
                reason=record.reason,
                pinned=record.pinned,
            ).model_dump(mode="json")
            for record in store.relationship_log
        ],
        "episodic_memories": [
            EpisodicMemory(
                character_id=record.character_id,
                replay_key=ReplayKey(
                    tick=record.tick,
                    timeline_index=record.timeline_index,
                    event_sequence=record.event_sequence,
                ),
                event_id=record.event_id,
                participants=list(record.participants),
                location=record.location,
                summary=record.summary,
                emotional_tag=record.emotional_tag,
                salience=record.salience,
                pinned=record.pinned,
                compressed=record.compressed,
            ).model_dump(mode="json")
            for record in store.episodic_memory
        ],
        "entity_representations": [
            SubjectiveEntityRepresentation(
                agent_id=record.agent_id,
                entity_id=record.entity_id,
                name=record.name,
                type=record.type,
                narrative_role=record.narrative_role,
                objective_facts=list(record.objective_facts),
                belief=record.belief,
                emotional_charge=record.emotional_charge,
                goal_relevance=record.goal_relevance,
                misunderstanding=record.misunderstanding,
                confidence=record.confidence,
                semantic_text=record.semantic_text,
                semantic_embedding=list(record.semantic_embedding) if record.semantic_embedding is not None else None,
            ).model_dump(mode="json")
            for record in store.entity_representations
        ],
        "world_snapshots": [
            WorldSnapshot(
                replay_key=ReplayKey(
                    tick=record.tick,
                    timeline_index=record.timeline_index,
                    event_sequence=record.event_sequence,
                ),
                agent_locations=dict(record.agent_locations),
                narrative_arc=NarrativeArcState.model_validate(record.narrative_arc),
                unresolved_threads=list(record.unresolved_threads),
                next_tick_size_minutes=record.next_tick_size_minutes,
            ).model_dump(mode="json")
            for record in store.world_snapshot
        ],
        "event_log": [
            {
                "event_id": record.event_id,
                "tick": record.tick,
                "timeline_index": record.timeline_index,
                "seed_type": record.seed_type,
                "location": record.location,
                "participants": list(record.participants),
                "description": record.description,
                "salience": record.salience,
                "outcome_summary": record.outcome_summary,
                "resolution_mode": record.resolution_mode,
            }
            for record in store.event_log
        ],
    }


def serialize_runtime_history(
    bundle: RepositoryBundle,
    *,
    agent_ids: Sequence[str],
    timeline_index: int,
) -> Dict[str, List[dict]]:
    state_changes = []
    goal_stacks = []
    relationships = []
    episodic_memories = []
    entity_representations = []

    for agent_id in sorted(agent_ids):
        state_changes.extend(
            entry.model_dump(mode="json")
            for entry in bundle.state_repo.list_for_character(agent_id, timeline_index)
        )
        goal_stacks.extend(
            snapshot.model_dump(mode="json")
            for snapshot in bundle.goal_repo.list_for_character(agent_id, timeline_index)
        )
        relationships.extend(
            entry.model_dump(mode="json")
            for entry in bundle.relationship_repo.list_from_character(agent_id, timeline_index)
        )
        episodic_memories.extend(
            memory.model_dump(mode="json")
            for memory in bundle.memory_repo.list_for_character(
                agent_id,
                timeline_index=timeline_index,
            )
        )
        entity_representations.extend(
            entity.model_dump(mode="json")
            for entity in bundle.entity_repo.list_for_agent(agent_id)
        )

    return {
        "state_changes": state_changes,
        "goal_stacks": goal_stacks,
        "relationships": relationships,
        "episodic_memories": episodic_memories,
        "entity_representations": entity_representations,
        "world_snapshots": [
            snapshot.model_dump(mode="json")
            for snapshot in bundle.world_snapshot_repo.list_until(timeline_index)
        ],
        "event_log": [
            {
                "event_id": record.event_id,
                "tick": record.tick,
                "timeline_index": record.timeline_index,
                "seed_type": record.seed_type,
                "location": record.location,
                "participants": list(record.participants),
                "description": record.description,
                "salience": record.salience,
                "outcome_summary": record.outcome_summary,
                "resolution_mode": record.resolution_mode,
            }
            for record in bundle.event_log_repo.list_until(timeline_index)
        ],
    }


def _empty_append_only_log() -> Dict[str, List[dict]]:
    return {
        "state_changes": [],
        "goal_stacks": [],
        "relationships": [],
        "episodic_memories": [],
        "entity_representations": [],
        "world_snapshots": [],
        "event_log": [],
        "scheduled_world_events": [],
        "maintenance_log": [],
        "llm_issues": [],
    }


def _drain_llm_issues(llm_client) -> List[dict]:
    drain = getattr(llm_client, "drain_issue_records", None)
    if callable(drain):
        return list(drain())
    return []


def _stamp_llm_issues(
    issues: Sequence[dict],
    *,
    tick_label: str,
    timeline_index: int,
    phase: str,
) -> List[dict]:
    stamped: List[dict] = []
    for issue in issues:
        stamped.append(
            {
                **dict(issue),
                "tick_label": tick_label,
                "timeline_index": timeline_index,
                "phase": phase,
            }
        )
    return stamped


def _llm_issue_metadata(
    *,
    prior_issues: Sequence[dict],
    new_issues: Sequence[dict],
) -> Dict[str, object]:
    combined = [*prior_issues, *new_issues]
    critical_total = sum(1 for issue in combined if str(issue.get("severity", "")) == "critical")
    critical_new = sum(1 for issue in new_issues if str(issue.get("severity", "")) == "critical")
    return {
        "llm_issue_count": len(combined),
        "last_tick_llm_issue_count": len(new_issues),
        "critical_llm_issue_count": critical_total,
        "last_tick_critical_llm_issue_count": critical_new,
        "recent_llm_issues": combined[-5:],
    }


def initialize_session(
    *,
    source_path: Path,
    workspace_dir: Path,
    chapter_id: str,
    tick_label: str,
    timeline_index: int,
    llm_client,
    character_ids: Sequence[str] | None = None,
    debug_session: DebugSession | None = None,
) -> SimulationSessionState:
    _drain_llm_issues(llm_client)
    accumulated = load_accumulated_extraction(workspace_dir, chapter_id=chapter_id)
    chapters = chapter_lookup(source_path)
    if chapter_id not in chapters:
        raise KeyError(f"Chapter {chapter_id} not found in source manuscript")
    chapter = chapters[chapter_id]
    requested_ids = set(character_ids or [])
    selected_records = [
        record
        for record in accumulated.characters
        if not requested_ids or record.id in requested_ids
    ]
    initializer = SnapshotInitializer(llm_client)
    replay_key = ReplayKey(tick=tick_label, timeline_index=timeline_index)
    agents: Dict[str, AgentRuntimeState] = {}
    initial_append_only_log: Dict[str, List[dict]] = _empty_append_only_log()
    language_guidance = require_language_guidance(
        build_language_guidance(accumulated.meta),
        context="session initialization",
    )
    scheduled_events = [
        asdict(event)
        for event in schedule_events_from_extraction(
            accumulated,
            start_timeline_index=timeline_index,
        )
    ]
    if debug_session is not None:
        debug_session.event(
            "session.initialize.start",
            chapter_id=chapter_id,
            requested_character_count=len(character_ids or []),
            selected_character_count=len(selected_records),
            scheduled_world_event_count=len(scheduled_events),
        )

    for record in selected_records:
        identity = build_character_identity(record)
        state_entries = build_state_entries(record, replay_key)
        relationships = build_relationship_entries(record, replay_key)
        memories = build_initial_memories(accumulated, record, replay_key)
        voice_samples = voice_samples_for_character(accumulated, record.id)
        world_entities = subjective_entities_for_character(accumulated, record.id)
        snapshot = initializer.initialize(
            SnapshotInitializationInput(
                identity=identity,
                replay_key=replay_key,
                text_excerpt=chapter.text[:4000],
                event_summary_up_to_t=chapter_event_summaries(accumulated, record.id),
                nearby_characters=[relation.target_id for relation in record.relationships],
                goal_hints=list(record.current_state.goal_stack),
                language_guidance=language_guidance,
                state_entries=state_entries,
                memories=memories,
                relationships=relationships,
                default_state={"location": record.current_state.location or ""},
            )
        )
        agents[record.id] = AgentRuntimeState(
            snapshot=snapshot,
            needs_reprojection=True,
            voice_samples=voice_samples,
            world_entities=[entity.model_dump(mode="json") for entity in world_entities],
        )
        initial_append_only_log["state_changes"].extend(
            entry.model_dump(mode="json") for entry in state_entries
        )
        initial_append_only_log["relationships"].extend(
            entry.model_dump(mode="json") for entry in relationships
        )
        initial_append_only_log["episodic_memories"].extend(
            memory.model_dump(mode="json") for memory in memories
        )
        initial_append_only_log["entity_representations"].extend(
            entity.model_dump(mode="json") for entity in world_entities
        )
        initial_append_only_log["goal_stacks"].append(
            GoalStackSnapshot(
                character_id=record.id,
                replay_key=replay_key,
                goals=snapshot.goals,
            ).model_dump(mode="json")
        )
    initialization_llm_issues = _stamp_llm_issues(
        _drain_llm_issues(llm_client),
        tick_label=tick_label,
        timeline_index=timeline_index,
        phase="initialization",
    )
    initial_append_only_log["llm_issues"] = initialization_llm_issues
    session = SimulationSessionState(
        source_path=str(source_path),
        current_tick_label=tick_label,
        current_timeline_index=timeline_index,
        arc_state=_derive_initial_arc(accumulated),
        agents=agents,
        pending_world_events=scheduled_events,
        pending_background_jobs=[],
        append_only_log={
            **initial_append_only_log,
            "scheduled_world_events": scheduled_events,
        },
        metadata={
            "chapter_id": chapter_id,
            "chapter_title": chapter.title or chapter_id,
            "chapter_order_index": chapter.order_index,
            "chapter_count": len(chapters),
            "writing_style_note": writing_style_note(accumulated),
            "language_context": accumulated.meta.language_context.model_dump(mode="json"),
            "language_guidance": language_guidance,
            "tick_count": 0,
            "story_context": accumulated.world.setting or Path(source_path).stem,
            "authorial_intent": accumulated.meta.authorial.central_thesis.get("value", ""),
            "central_tension": ", ".join(theme.name for theme in accumulated.meta.authorial.themes[:2]),
            "last_arc_update_timeline_index": timeline_index,
            "last_arc_update_tick_count": 0,
            "suppressed_memory_ids_by_agent": {},
            "initial_arc_state": _derive_initial_arc(accumulated).model_dump(mode="json"),
            **_llm_issue_metadata(prior_issues=[], new_issues=initialization_llm_issues),
        },
    )
    if debug_session is not None:
        debug_session.event(
            "session.initialize.done",
            agent_count=len(session.agents),
            initial_memory_count=len(session.append_only_log.get("episodic_memories", [])),
            initial_entity_count=len(session.append_only_log.get("entity_representations", [])),
        )
    return session


def _derive_initial_arc(accumulated: AccumulatedExtraction) -> NarrativeArcState:
    tension = min(1.0, 0.2 + (0.05 * len(accumulated.events)))
    unresolved = [event.id for event in accumulated.events[-3:] if event.id]
    phase = "setup" if len(accumulated.events) < 3 else "rising_action"

    return NarrativeArcState(
        current_phase=phase,
        tension_level=tension,
        unresolved_threads=unresolved,
        approaching_climax=tension >= 0.7,
    )


def run_session_tick(
    session: SimulationSessionState,
    llm_client,
    *,
    debug_session: DebugSession | None = None,
    settings: Optional[SimulationSettings] = None,
    on_progress: Callable[[dict[str, object]], None] | None = None,
) -> SimulationSessionState:
    active_settings = settings or SimulationSettings()
    _drain_llm_issues(llm_client)
    normalized_agents = {
        agent_id: agent.model_copy(
            update={
                "snapshot": agent.snapshot.model_copy(
                    update={
                        "current_state": normalize_current_state(
                            agent.snapshot.current_state,
                            agent.snapshot.inferred_state,
                        )
                    }
                )
            }
        )
        for agent_id, agent in session.agents.items()
    }
    session = session.model_copy(update={"agents": normalized_agents})
    language_guidance = require_language_guidance(
        str(session.metadata.get("language_guidance", "")),
        context="simulation tick",
    )
    if debug_session is not None:
        debug_session.event(
            "tick.start",
            tick_label=session.current_tick_label,
            timeline_index=session.current_timeline_index,
            agent_count=len(session.agents),
            pending_world_events=len(session.pending_world_events),
            pending_background_jobs=len(session.pending_background_jobs),
        )
    bundle = build_runtime_bundle(session=session, settings=active_settings)
    scheduler = WorldEventScheduler(
        [ScheduledWorldEvent(**item) for item in session.pending_world_events]
    )
    runner = SimulationTickRunner(
        world_manager=build_world_manager(active_settings),
        seed_detector=SeedDetector(GoalCollisionDetector(llm_client)),
        trajectory_projector=TrajectoryProjector(llm_client),
        event_simulator=EventSimulator(llm_client),
        state_updater=EventStateUpdater(llm_client),
        state_repo=bundle.state_repo,
        goal_repo=bundle.goal_repo,
        relationship_repo=bundle.relationship_repo,
        memory_repo=bundle.memory_repo,
        entity_repo=bundle.entity_repo,
        world_snapshot_repo=bundle.world_snapshot_repo,
        event_log_repo=bundle.event_log_repo,
        world_event_scheduler=scheduler,
        retrieved_memory_candidates=active_settings.retrieved_memory_candidates,
    )
    runtimes = [
        AgentRuntime(
            snapshot=agent.snapshot,
            needs_reprojection=agent.needs_reprojection,
            trajectory=agent.trajectory,
            voice_samples=agent.voice_samples,
            world_entities=agent.world_entities,
        )
        for agent in session.agents.values()
    ]
    result = runner.run_tick(
        current_tick_label=session.current_tick_label,
        current_timeline_index=session.current_timeline_index,
        current_tick_count=int(session.metadata.get("tick_count", 0) or 0),
        agent_runtimes=runtimes,
        arc_state=session.arc_state,
        writing_style_note=str(session.metadata.get("writing_style_note", "")),
        language_guidance=language_guidance,
        cooldown_ticks_remaining=int(session.metadata.get("tick_cooldown_remaining", 0)),
        prior_max_salience=float(session.metadata.get("max_observed_salience", 0.0) or 0.0),
        progress_callback=on_progress,
    )
    append_only_log = {
        **_empty_append_only_log(),
        **serialize_runtime_history(
            bundle,
            agent_ids=tuple(session.agents.keys()),
            timeline_index=result.replay_key.timeline_index,
        ),
    }
    prior_scheduled = list((session.append_only_log or {}).get("scheduled_world_events", []))
    seen_schedule_ids = {item.get("event_id") for item in prior_scheduled}
    new_schedule_entries = [
        asdict(event)
        for event in scheduler.pending_events
        if event.event_id not in seen_schedule_ids
    ]
    append_only_log["scheduled_world_events"] = prior_scheduled + new_schedule_entries
    append_only_log["maintenance_log"] = list((session.append_only_log or {}).get("maintenance_log", []))
    prior_llm_issues = list((session.append_only_log or {}).get("llm_issues", []))
    tick_llm_issues = _stamp_llm_issues(
        _drain_llm_issues(llm_client),
        tick_label=result.replay_key.tick,
        timeline_index=result.replay_key.timeline_index,
        phase="tick",
    )
    append_only_log["llm_issues"] = prior_llm_issues + tick_llm_issues
    background_queue = SessionBackgroundQueueBackend(session.pending_background_jobs)
    scheduled_job_records = background_queue.enqueue_many(result.scheduled_jobs)

    updated = SimulationSessionState(
        source_path=session.source_path,
        current_tick_label=result.replay_key.tick,
        current_timeline_index=result.replay_key.timeline_index,
        arc_state=session.arc_state,
        agents={
            agent_id: AgentRuntimeState(
                snapshot=runtime.snapshot,
                needs_reprojection=runtime.needs_reprojection,
                trajectory=runtime.trajectory,
                voice_samples=runtime.voice_samples,
                world_entities=runtime.world_entities,
            )
            for agent_id, runtime in result.agent_runtimes.items()
        },
        pending_world_events=[
            asdict(event)
            for event in scheduler.pending_events
        ],
        pending_background_jobs=background_queue.snapshot(),
        append_only_log=append_only_log,
        metadata={
            **session.metadata,
            "language_guidance": language_guidance,
            "tick_count": int(session.metadata.get("tick_count", 0) or 0) + 1,
            "last_tick_minutes": result.tick_minutes,
            "tick_cooldown_remaining": result.tick_cooldown_remaining,
            "max_observed_salience": result.max_observed_salience,
            "scheduled_jobs": [job.to_record() for job in scheduled_job_records],
            "active_agent_scores": dict(result.active_agent_scores),
            "location_threads": list(result.location_threads),
            "bridge_events": list(result.bridge_events),
            "woken_agents": dict(result.woken_agents),
            "recent_event_failures": [failure.__dict__ for failure in result.event_failures],
            "background_queue_depth": background_queue.queued_count(),
            **_llm_issue_metadata(prior_issues=prior_llm_issues, new_issues=tick_llm_issues),
        },
    )
    updated = BackgroundMaintenanceRunner(
        llm_client,
        debug_session=debug_session,
    ).run_due_jobs(
        updated,
        job_types={"arc_update"},
    )
    if debug_session is not None:
        debug_session.event(
            "tick.done",
            next_timeline_index=updated.current_timeline_index,
            tick_minutes=result.tick_minutes,
            ranked_seed_count=len(result.ranked_seeds),
            event_failure_count=len(result.event_failures),
            background_queue_depth=background_queue.queued_count(),
        )
    return updated


def advance_session(
    session: SimulationSessionState,
    llm_client,
    *,
    ticks: int,
    debug_session: DebugSession | None = None,
    settings: Optional[SimulationSettings] = None,
    on_tick: Callable[[SimulationSessionState, int], None] | None = None,
    on_progress: Callable[[int, dict[str, object]], None] | None = None,
) -> SimulationSessionState:
    updated = session
    for index in range(max(0, ticks)):
        updated = run_session_tick(
            updated,
            llm_client,
            debug_session=debug_session,
            settings=settings,
            on_progress=(
                (lambda event, tick_ordinal=index + 1: on_progress(tick_ordinal, event))
                if on_progress is not None
                else None
            ),
        )
        if on_tick is not None:
            on_tick(updated, index + 1)
    return updated


def session_report(session: SimulationSessionState) -> Dict[str, object]:
    return {
        "source_path": session.source_path,
        "current_tick_label": session.current_tick_label,
        "current_timeline_index": session.current_timeline_index,
        "agent_count": len(session.agents),
        "pending_world_events": len(session.pending_world_events),
        "pending_background_jobs": len(session.pending_background_jobs),
        "log_counts": {
            key: len(value)
            for key, value in sorted((session.append_only_log or {}).items())
        },
        "agents": {
            agent_id: {
                "location": runtime.snapshot.current_state.get("location", ""),
                "top_goal": runtime.snapshot.goals[0].goal if runtime.snapshot.goals else "",
                "needs_reprojection": runtime.needs_reprojection,
            }
            for agent_id, runtime in sorted(session.agents.items())
        },
        "metadata": dict(session.metadata),
    }


def branch_session(
    session: SimulationSessionState,
    *,
    timeline_index: Optional[int] = None,
    before_event_id: Optional[str] = None,
    tick_label: Optional[str] = None,
) -> SimulationSessionState:
    target_timeline, derived_tick_label = _resolve_branch_target(
        session,
        timeline_index=timeline_index,
        before_event_id=before_event_id,
    )
    branch_tick_label = tick_label or derived_tick_label
    branch_log = _filter_append_only_log(session, target_timeline)
    suppressed = _suppressed_memory_ids_at_timeline(session, target_timeline)
    arc_state = _arc_state_at_timeline(session, target_timeline)

    branched_agents: Dict[str, AgentRuntimeState] = {}
    for agent_id, runtime in session.agents.items():
        branched_agents[agent_id] = _reconstruct_agent_runtime(
            runtime=runtime,
            append_only_log=branch_log,
            suppressed_memory_ids=suppressed.get(agent_id, set()),
            replay_key=ReplayKey(tick=branch_tick_label, timeline_index=target_timeline),
        )

    metadata = {
        **session.metadata,
        "suppressed_memory_ids_by_agent": {
            agent_id: sorted(suppressed.get(agent_id, set()))
            for agent_id in session.agents.keys()
        },
        "tick_count": len(branch_log.get("world_snapshots", [])),
        "last_tick_minutes": (
            int(branch_log.get("world_snapshots", [])[-1].get("next_tick_size_minutes", 0))
            if branch_log.get("world_snapshots")
            else 0
        ),
        "last_arc_update_timeline_index": min(
            int(session.metadata.get("last_arc_update_timeline_index", 0)),
            target_timeline,
        ),
        "last_arc_update_tick_count": min(
            int(session.metadata.get("last_arc_update_tick_count", 0) or 0),
            len(branch_log.get("world_snapshots", [])),
        ),
        "branch_origin_timeline_index": session.current_timeline_index,
        "branched_from_timeline_index": target_timeline,
    }

    return SimulationSessionState(
        source_path=session.source_path,
        current_tick_label=branch_tick_label,
        current_timeline_index=target_timeline,
        arc_state=arc_state,
        agents=branched_agents,
        pending_world_events=_pending_world_events_at_timeline(session, target_timeline),
        pending_background_jobs=[],
        append_only_log=branch_log,
        metadata=metadata,
    )


def _resolve_branch_target(
    session: SimulationSessionState,
    *,
    timeline_index: Optional[int],
    before_event_id: Optional[str],
) -> tuple[int, str]:
    if timeline_index is not None:
        tick_label = _latest_tick_label_at_or_before(session, timeline_index) or session.current_tick_label
        return max(0, timeline_index), tick_label

    if before_event_id is None:
        raise ValueError("Provide either timeline_index or before_event_id when branching")

    event_entries = list((session.append_only_log or {}).get("event_log", []))
    target_event = next(
        (item for item in event_entries if item.get("event_id") == before_event_id),
        None,
    )
    if target_event is None:
        raise KeyError(f"Event {before_event_id} not found in append-only log")

    event_timeline = int(target_event.get("timeline_index", 0))
    prior_snapshots = [
        item
        for item in (session.append_only_log or {}).get("world_snapshots", [])
        if int(item["replay_key"]["timeline_index"]) < event_timeline
    ]
    if prior_snapshots:
        snapshot = max(prior_snapshots, key=lambda item: int(item["replay_key"]["timeline_index"]))
        return int(snapshot["replay_key"]["timeline_index"]), str(snapshot["replay_key"]["tick"])
    return 0, str(session.metadata.get("chapter_id", session.current_tick_label))


def _latest_tick_label_at_or_before(session: SimulationSessionState, timeline_index: int) -> Optional[str]:
    snapshots = [
        item
        for item in (session.append_only_log or {}).get("world_snapshots", [])
        if int(item["replay_key"]["timeline_index"]) <= timeline_index
    ]
    if snapshots:
        latest = max(snapshots, key=lambda item: int(item["replay_key"]["timeline_index"]))
        return str(latest["replay_key"]["tick"])
    return None


def _filter_append_only_log(
    session: SimulationSessionState,
    timeline_index: int,
) -> Dict[str, List[dict]]:
    source = {**_empty_append_only_log(), **(session.append_only_log or {})}
    return {
        "state_changes": [
            item
            for item in source["state_changes"]
            if int(item["replay_key"]["timeline_index"]) <= timeline_index
        ],
        "goal_stacks": [
            item
            for item in source["goal_stacks"]
            if int(item["replay_key"]["timeline_index"]) <= timeline_index
        ],
        "relationships": [
            item
            for item in source["relationships"]
            if int(item["replay_key"]["timeline_index"]) <= timeline_index
        ],
        "episodic_memories": [
            item
            for item in source["episodic_memories"]
            if int(item["replay_key"]["timeline_index"]) <= timeline_index
        ],
        "entity_representations": list(source["entity_representations"]),
        "world_snapshots": [
            item
            for item in source["world_snapshots"]
            if int(item["replay_key"]["timeline_index"]) <= timeline_index
        ],
        "event_log": [
            item
            for item in source["event_log"]
            if int(item["timeline_index"]) <= timeline_index
        ],
        "scheduled_world_events": list(source["scheduled_world_events"]),
        "maintenance_log": [
            item
            for item in source["maintenance_log"]
            if int(item.get("timeline_index", 0)) <= timeline_index
        ],
    }


def _suppressed_memory_ids_at_timeline(
    session: SimulationSessionState,
    timeline_index: int,
) -> Dict[str, set[str]]:
    suppressed: Dict[str, set[str]] = {}
    for item in (session.append_only_log or {}).get("maintenance_log", []):
        if item.get("job_type") != "memory_compression":
            continue
        if int(item.get("timeline_index", 0)) > timeline_index:
            continue
        target_id = str(item.get("target_id", ""))
        suppressed.setdefault(target_id, set()).update(item.get("suppressed_event_ids", []))
    return suppressed


def _arc_state_at_timeline(
    session: SimulationSessionState,
    timeline_index: int,
) -> NarrativeArcState:
    snapshots = [
        WorldSnapshot.model_validate(item)
        for item in (session.append_only_log or {}).get("world_snapshots", [])
        if int(item["replay_key"]["timeline_index"]) <= timeline_index
    ]
    if snapshots:
        latest = max(snapshots, key=lambda item: item.replay_key.timeline_index)
        return latest.narrative_arc

    maintenance_updates = [
        item
        for item in (session.append_only_log or {}).get("maintenance_log", [])
        if item.get("job_type") == "arc_update"
        and int(item.get("timeline_index", 0)) <= timeline_index
    ]
    if maintenance_updates:
        latest = max(maintenance_updates, key=lambda item: int(item.get("timeline_index", 0)))
        return NarrativeArcState.model_validate(latest["arc_state"])

    initial = session.metadata.get("initial_arc_state")
    if initial:
        return NarrativeArcState.model_validate(initial)
    return session.arc_state


def _pending_world_events_at_timeline(
    session: SimulationSessionState,
    timeline_index: int,
) -> List[dict]:
    fired_event_ids = {
        item.get("event_id")
        for item in (session.append_only_log or {}).get("event_log", [])
        if int(item.get("timeline_index", 0)) <= timeline_index
    }
    pending: List[dict] = []
    for item in (session.append_only_log or {}).get("scheduled_world_events", []):
        event_id = item.get("event_id")
        if event_id in fired_event_ids:
            continue
        if int(item.get("trigger_timeline_index", 0)) <= timeline_index:
            continue
        pending.append(dict(item))
    return sorted(pending, key=lambda item: (int(item.get("trigger_timeline_index", 0)), str(item.get("event_id", ""))))


def _reconstruct_agent_runtime(
    *,
    runtime: AgentRuntimeState,
    append_only_log: Dict[str, List[dict]],
    suppressed_memory_ids: set[str],
    replay_key: ReplayKey,
) -> AgentRuntimeState:
    agent_id = runtime.snapshot.identity.character_id
    state_entries = [
        StateChangeLogEntry.model_validate(item)
        for item in append_only_log.get("state_changes", [])
        if item.get("character_id") == agent_id
    ]
    replay = StateReplay()
    current_state = replay.replay_character_state(
        state_entries,
        agent_id,
        replay_key.timeline_index,
    )

    goal_snapshots = [
        GoalStackSnapshot.model_validate(item)
        for item in append_only_log.get("goal_stacks", [])
        if item.get("character_id") == agent_id
    ]
    if goal_snapshots:
        latest_goal_stack = max(goal_snapshots, key=lambda item: replay_sort_key(item.replay_key))
        goals = latest_goal_stack.goals
    else:
        goals = list(runtime.snapshot.goals)

    latest_relationships: Dict[str, RelationshipLogEntry] = {}
    for item in append_only_log.get("relationships", []):
        if item.get("from_character_id") != agent_id:
            continue
        relationship = RelationshipLogEntry.model_validate(item)
        incumbent = latest_relationships.get(relationship.to_character_id)
        if incumbent is None or replay_sort_key(relationship.replay_key) > replay_sort_key(incumbent.replay_key):
            latest_relationships[relationship.to_character_id] = relationship

    memories = [
        EpisodicMemory.model_validate(item)
        for item in append_only_log.get("episodic_memories", [])
        if item.get("character_id") == agent_id
        and item.get("event_id") not in suppressed_memory_ids
    ]
    snapshot = runtime.snapshot.model_copy(
        update={
            "replay_key": replay_key,
            "current_state": normalize_current_state(
                current_state,
                runtime.snapshot.inferred_state,
            ),
            "goals": goals,
            "working_memory": rank_memories(memories, max_results=5),
            "relationships": list(latest_relationships.values()),
        }
    )
    return AgentRuntimeState(
        snapshot=snapshot,
        needs_reprojection=True,
        trajectory=None,
        voice_samples=list(runtime.voice_samples),
        world_entities=[
            entity.model_dump(mode="json")
            for entity in [
                SubjectiveEntityRepresentation.model_validate(item)
                for item in append_only_log.get("entity_representations", [])
                if item.get("agent_id") == agent_id
            ]
        ],
    )
