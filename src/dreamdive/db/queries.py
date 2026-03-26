from __future__ import annotations

from collections.abc import Sequence
from typing import Optional

from dreamdive.db.models import (
    EntityRepresentationRecord,
    EpisodicMemoryRecord,
    EventLogRecord,
    GoalStackRecord,
    RelationshipLogRecord,
    StateChangeLogRecord,
    WorldSnapshotRecord,
)
import numpy as np
from dreamdive.memory.retrieval import (
    _HAS_NUMPY,
    batch_cosine_similarity,
    build_entity_semantic_text,
    build_memory_semantic_text,
    cosine_similarity,
    embed_text,
)
from dreamdive.schemas import (
    Goal,
    GoalStackSnapshot,
    EpisodicMemory,
    RelationshipLogEntry,
    ReplayKey,
    StateChangeLogEntry,
    SubjectiveEntityRepresentation,
    WorldSnapshot,
)


class StateChangeLogRepository:
    def __init__(self, store: InMemoryStore) -> None:
        self.store = store

    def append(self, entry: StateChangeLogEntry) -> StateChangeLogRecord:
        record = StateChangeLogRecord(
            id=len(self.store.state_change_log) + 1,
            character_id=entry.character_id,
            dimension=entry.dimension,
            tick=entry.replay_key.tick,
            timeline_index=entry.replay_key.timeline_index,
            event_sequence=entry.replay_key.event_sequence,
            event_id=entry.event_id,
            from_value=entry.from_value,
            to_value=entry.to_value,
            trigger=entry.trigger,
            emotional_tag=entry.emotional_tag,
            pinned=entry.pinned,
        )
        self.store.state_change_log.append(record)
        return record

    def list_until(
        self,
        character_id: str,
        dimension: str,
        timeline_index: int,
    ) -> Sequence[StateChangeLogRecord]:
        rows = [
            row
            for row in self.store.state_change_log
            if row.character_id == character_id
            and row.dimension == dimension
            and row.timeline_index <= timeline_index
        ]
        return sorted(rows, key=lambda row: (row.timeline_index, row.event_sequence, row.id))

    def list_for_character(
        self,
        character_id: str,
        timeline_index: int,
    ) -> Sequence[StateChangeLogEntry]:
        rows = [
            row
            for row in self.store.state_change_log
            if row.character_id == character_id and row.timeline_index <= timeline_index
        ]
        rows = sorted(rows, key=lambda row: (row.timeline_index, row.event_sequence, row.id))
        return [
            StateChangeLogEntry(
                character_id=row.character_id,
                dimension=row.dimension,
                replay_key=ReplayKey(
                    tick=row.tick,
                    timeline_index=row.timeline_index,
                    event_sequence=row.event_sequence,
                ),
                event_id=row.event_id,
                from_value=row.from_value,
                to_value=row.to_value,
                trigger=row.trigger,
                emotional_tag=row.emotional_tag,
                pinned=row.pinned,
            )
            for row in rows
        ]


class GoalStackRepository:
    def __init__(self, store: InMemoryStore) -> None:
        self.store = store

    def append(self, snapshot: GoalStackSnapshot) -> GoalStackRecord:
        record = GoalStackRecord(
            id=len(self.store.goal_stack) + 1,
            character_id=snapshot.character_id,
            tick=snapshot.replay_key.tick,
            timeline_index=snapshot.replay_key.timeline_index,
            event_sequence=snapshot.replay_key.event_sequence,
            goals=[goal.model_dump(mode="json") for goal in snapshot.goals],
            actively_avoiding=snapshot.actively_avoiding,
            most_uncertain_relationship=snapshot.most_uncertain_relationship,
        )
        self.store.goal_stack.append(record)
        return record

    def latest_at_or_before(
        self,
        character_id: str,
        timeline_index: int,
    ) -> Optional[GoalStackSnapshot]:
        rows = [
            row
            for row in self.store.goal_stack
            if row.character_id == character_id and row.timeline_index <= timeline_index
        ]
        if not rows:
            return None

        record = max(rows, key=lambda row: (row.timeline_index, row.event_sequence, row.id))
        return GoalStackSnapshot(
            character_id=record.character_id,
            replay_key=ReplayKey(
                tick=record.tick,
                timeline_index=record.timeline_index,
                event_sequence=record.event_sequence,
            ),
            goals=[Goal.model_validate(goal) for goal in record.goals],
            actively_avoiding=record.actively_avoiding,
            most_uncertain_relationship=record.most_uncertain_relationship,
        )

    def list_for_character(
        self,
        character_id: str,
        timeline_index: int,
    ) -> Sequence[GoalStackSnapshot]:
        rows = [
            row
            for row in self.store.goal_stack
            if row.character_id == character_id and row.timeline_index <= timeline_index
        ]
        rows = sorted(rows, key=lambda row: (row.timeline_index, row.event_sequence, row.id))
        return [
            GoalStackSnapshot(
                character_id=row.character_id,
                replay_key=ReplayKey(
                    tick=row.tick,
                    timeline_index=row.timeline_index,
                    event_sequence=row.event_sequence,
                ),
                goals=[Goal.model_validate(goal) for goal in row.goals],
                actively_avoiding=row.actively_avoiding,
                most_uncertain_relationship=row.most_uncertain_relationship,
            )
            for row in rows
        ]


class RelationshipRepository:
    def __init__(self, store: InMemoryStore) -> None:
        self.store = store

    def append(self, entry: RelationshipLogEntry) -> RelationshipLogRecord:
        record = RelationshipLogRecord(
            id=len(self.store.relationship_log) + 1,
            from_character_id=entry.from_character_id,
            to_character_id=entry.to_character_id,
            tick=entry.replay_key.tick,
            timeline_index=entry.replay_key.timeline_index,
            event_sequence=entry.replay_key.event_sequence,
            event_id=entry.event_id,
            summary=entry.summary,
            reason=entry.reason,
            pinned=entry.pinned,
        )
        self.store.relationship_log.append(record)
        return record

    def latest_for_participants(
        self,
        from_character_id: str,
        to_character_ids: Sequence[str],
        timeline_index: int,
    ) -> Sequence[RelationshipLogRecord]:
        latest_by_target: dict[str, RelationshipLogRecord] = {}
        for row in self.store.relationship_log:
            if (
                row.from_character_id != from_character_id
                or row.to_character_id not in to_character_ids
                or row.timeline_index > timeline_index
            ):
                continue

            incumbent = latest_by_target.get(row.to_character_id)
            if incumbent is None or (
                row.timeline_index,
                row.event_sequence,
                row.id,
            ) > (incumbent.timeline_index, incumbent.event_sequence, incumbent.id):
                latest_by_target[row.to_character_id] = row
        return list(latest_by_target.values())

    def list_from_character(
        self,
        from_character_id: str,
        timeline_index: int,
    ) -> Sequence[RelationshipLogEntry]:
        rows = [
            row
            for row in self.store.relationship_log
            if row.from_character_id == from_character_id and row.timeline_index <= timeline_index
        ]
        rows = sorted(rows, key=lambda row: (row.timeline_index, row.event_sequence, row.id))
        return [
            RelationshipLogEntry(
                from_character_id=row.from_character_id,
                to_character_id=row.to_character_id,
                replay_key=ReplayKey(
                    tick=row.tick,
                    timeline_index=row.timeline_index,
                    event_sequence=row.event_sequence,
                ),
                event_id=row.event_id,
                summary=row.summary,
                reason=row.reason,
                pinned=row.pinned,
            )
            for row in rows
        ]


class WorldSnapshotRepository:
    def __init__(self, store: InMemoryStore) -> None:
        self.store = store

    def append(self, snapshot: WorldSnapshot) -> WorldSnapshotRecord:
        record = WorldSnapshotRecord(
            id=len(self.store.world_snapshot) + 1,
            tick=snapshot.replay_key.tick,
            timeline_index=snapshot.replay_key.timeline_index,
            event_sequence=snapshot.replay_key.event_sequence,
            agent_locations=snapshot.agent_locations,
            narrative_arc=snapshot.narrative_arc.model_dump(mode="json"),
            unresolved_threads=snapshot.unresolved_threads,
            next_tick_size_minutes=snapshot.next_tick_size_minutes,
        )
        self.store.world_snapshot.append(record)
        return record

    def list_until(self, timeline_index: int) -> Sequence[WorldSnapshot]:
        rows = [
            row
            for row in self.store.world_snapshot
            if row.timeline_index <= timeline_index
        ]
        rows = sorted(rows, key=lambda row: (row.timeline_index, row.event_sequence, row.id))
        return [
            WorldSnapshot(
                replay_key=ReplayKey(
                    tick=row.tick,
                    timeline_index=row.timeline_index,
                    event_sequence=row.event_sequence,
                ),
                agent_locations=dict(row.agent_locations),
                narrative_arc=row.narrative_arc,
                unresolved_threads=list(row.unresolved_threads),
                next_tick_size_minutes=row.next_tick_size_minutes,
            )
            for row in rows
        ]


class EntityRepresentationRepository:
    def __init__(self, store: InMemoryStore) -> None:
        self.store = store

    def append(self, representation: SubjectiveEntityRepresentation) -> EntityRepresentationRecord:
        semantic_text = representation.semantic_text or build_entity_semantic_text(
            representation.model_dump(mode="json")
        )
        semantic_embedding = representation.semantic_embedding or embed_text(semantic_text)
        record = EntityRepresentationRecord(
            id=len(self.store.entity_representations) + 1,
            agent_id=representation.agent_id,
            entity_id=representation.entity_id,
            name=representation.name,
            type=representation.type,
            narrative_role=representation.narrative_role,
            objective_facts=list(representation.objective_facts),
            belief=representation.belief,
            emotional_charge=representation.emotional_charge,
            goal_relevance=representation.goal_relevance,
            misunderstanding=representation.misunderstanding,
            confidence=representation.confidence,
            semantic_text=semantic_text,
            semantic_embedding=semantic_embedding,
        )
        self.store.entity_representations = [
            row
            for row in self.store.entity_representations
            if not (row.agent_id == representation.agent_id and row.entity_id == representation.entity_id)
        ]
        self.store.entity_representations.append(record)
        
        # Update index
        agent_id = representation.agent_id
        if agent_id not in self.store.entity_representations_by_agent:
            self.store.entity_representations_by_agent[agent_id] = []
        self.store.entity_representations_by_agent[agent_id] = [
            row for row in self.store.entity_representations_by_agent[agent_id]
            if row.entity_id != representation.entity_id
        ]
        self.store.entity_representations_by_agent[agent_id].append(record)
        
        return record

    def list_for_agent(self, agent_id: str) -> Sequence[SubjectiveEntityRepresentation]:
        rows = self.store.entity_representations_by_agent.get(agent_id, [])
        rows = sorted(rows, key=lambda row: (row.name, row.entity_id, row.id))
        return [
            SubjectiveEntityRepresentation(
                agent_id=row.agent_id,
                entity_id=row.entity_id,
                name=row.name,
                type=row.type,
                narrative_role=row.narrative_role,
                objective_facts=list(row.objective_facts),
                belief=row.belief,
                emotional_charge=row.emotional_charge,
                goal_relevance=row.goal_relevance,
                misunderstanding=row.misunderstanding,
                confidence=row.confidence,
                semantic_text=row.semantic_text,
                semantic_embedding=list(row.semantic_embedding) if row.semantic_embedding is not None else None,
            )
            for row in rows
        ]

    def search_for_agent(
        self,
        agent_id: str,
        *,
        query_embedding: Sequence[float],
        limit: int,
    ) -> Sequence[SubjectiveEntityRepresentation]:
        scored: list[tuple[float, EntityRepresentationRecord]] = []
        rows = self.store.entity_representations_by_agent.get(agent_id, [])
        if not rows:
            return []
            
        embeddings = []
        for record in rows:
            if _HAS_NUMPY:
                # Use internal cache to avoid re-converting Python lists to numpy arrays
                np_emb = getattr(record, "_np_embedding", None)
                if np_emb is None:
                    raw_emb = record.semantic_embedding or embed_text(
                        record.semantic_text or build_entity_semantic_text(_record_to_dict(record))
                    )
                    np_emb = np.asarray(raw_emb, dtype=np.float32)
                    setattr(record, "_np_embedding", np_emb)
                embeddings.append(np_emb)
            else:
                embeddings.append(
                    record.semantic_embedding or embed_text(
                        record.semantic_text or build_entity_semantic_text(_record_to_dict(record))
                    )
                )
            
        scores = batch_cosine_similarity(query_embedding, embeddings)
        for i, score in enumerate(scores):
            scored.append((score, rows[i]))
            
        ranked = sorted(
            scored,
            key=lambda item: (item[0], item[1].goal_relevance, item[1].name),
            reverse=True,
        )
        results = []
        for score, record in ranked[: max(0, limit)]:
            results.append(
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
                )
            )
        return results


class EventLogRepository:
    def __init__(self, store: InMemoryStore) -> None:
        self.store = store

    def append(
        self,
        *,
        event_id: str,
        replay_key: ReplayKey,
        seed_type: str,
        location: str,
        participants: Sequence[str],
        description: str,
        salience: float,
        outcome_summary: str,
        resolution_mode: str,
    ) -> EventLogRecord:
        record = EventLogRecord(
            id=len(self.store.event_log) + 1,
            event_id=event_id,
            tick=replay_key.tick,
            timeline_index=replay_key.timeline_index,
            seed_type=seed_type,
            location=location,
            participants=list(participants),
            description=description,
            salience=salience,
            outcome_summary=outcome_summary,
            resolution_mode=resolution_mode,
        )
        self.store.event_log.append(record)
        return record

    def list_until(self, timeline_index: int) -> Sequence[EventLogRecord]:
        rows = [
            row
            for row in self.store.event_log
            if row.timeline_index <= timeline_index
        ]
        return sorted(rows, key=lambda row: (row.timeline_index, row.id))


class EpisodicMemoryRepository:
    def __init__(self, store: InMemoryStore) -> None:
        self.store = store

    def append(self, memory: EpisodicMemory) -> EpisodicMemoryRecord:
        embedding = memory.embedding or embed_text(build_memory_semantic_text(memory))
        record = EpisodicMemoryRecord(
            id=len(self.store.episodic_memory) + 1,
            character_id=memory.character_id,
            tick=memory.replay_key.tick,
            timeline_index=memory.replay_key.timeline_index,
            event_sequence=memory.replay_key.event_sequence,
            event_id=memory.event_id,
            participants=memory.participants,
            location=memory.location,
            summary=memory.summary,
            emotional_tag=memory.emotional_tag,
            salience=memory.salience,
            pinned=memory.pinned,
            compressed=memory.compressed,
            embedding=embedding,
        )
        self.store.episodic_memory.append(record)
        
        # Update index
        char_id = memory.character_id
        if char_id not in self.store.episodic_memory_by_char:
            self.store.episodic_memory_by_char[char_id] = []
        self.store.episodic_memory_by_char[char_id].append(record)
        
        return record

    def list_for_character(
        self,
        character_id: str,
        *,
        timeline_index: Optional[int] = None,
    ) -> Sequence[EpisodicMemory]:
        rows = [
            row
            for row in self.store.episodic_memory_by_char.get(character_id, [])
            if timeline_index is None or row.timeline_index <= timeline_index
        ]
        rows = sorted(rows, key=lambda row: (row.timeline_index, row.event_sequence, row.id))
        return [
            EpisodicMemory(
                character_id=row.character_id,
                replay_key=ReplayKey(
                    tick=row.tick,
                    timeline_index=row.timeline_index,
                    event_sequence=row.event_sequence,
                ),
                event_id=row.event_id,
                participants=list(row.participants),
                location=row.location,
                summary=row.summary,
                emotional_tag=row.emotional_tag,
                salience=row.salience,
                pinned=row.pinned,
                compressed=row.compressed,
                embedding=list(row.embedding) if row.embedding is not None else None,
            )
            for row in rows
        ]

    def list_recent_for_character(
        self,
        character_id: str,
        *,
        limit: int = 5,
        timeline_index: Optional[int] = None,
    ) -> Sequence[EpisodicMemory]:
        """Return the most recent memories for a character, ordered chronologically."""
        all_memories = self.list_for_character(character_id, timeline_index=timeline_index)
        # list_for_character already sorts ascending; take the last N
        return list(all_memories[-limit:]) if all_memories else []

    def list_pinned_for_character(
        self,
        character_id: str,
        *,
        timeline_index: Optional[int] = None,
    ) -> Sequence[EpisodicMemory]:
        return [
            memory
            for memory in self.list_for_character(character_id, timeline_index=timeline_index)
            if memory.pinned
        ]

    def search_semantic_for_character(
        self,
        character_id: str,
        *,
        query_embedding: Sequence[float],
        limit: int,
        timeline_index: Optional[int] = None,
        include_compressed: bool = False,
    ) -> Sequence[EpisodicMemory]:
        rows = self.store.episodic_memory_by_char.get(character_id, [])
        candidates_rows = []
        embeddings = []
        for record in rows:
            if timeline_index is not None and record.timeline_index > timeline_index:
                continue
            if record.compressed and not include_compressed:
                continue
            candidates_rows.append(record)
            
            if _HAS_NUMPY:
                # Use internal cache to avoid re-converting Python lists to numpy arrays
                np_emb = getattr(record, "_np_embedding", None)
                if np_emb is None:
                    raw_emb = record.embedding or embed_text(build_memory_semantic_text(_record_to_memory(record)))
                    np_emb = np.asarray(raw_emb, dtype=np.float32)
                    setattr(record, "_np_embedding", np_emb)
                embeddings.append(np_emb)
            else:
                embeddings.append(
                    record.embedding or embed_text(build_memory_semantic_text(_record_to_memory(record)))
                )
            
        if not candidates_rows:
            return []
            
        scores = batch_cosine_similarity(query_embedding, embeddings)
        scored = [(score, record) for score, record in zip(scores, candidates_rows)]
            
        ranked = sorted(
            scored,
            key=lambda item: (
                item[0],
                item[1].timeline_index,
                item[1].event_sequence,
            ),
            reverse=True,
        )
        
        results = []
        for score, record in ranked[: max(0, limit)]:
            results.append(
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
                    embedding=list(record.embedding) if record.embedding is not None else None,
                    semantic_score=score,
                )
            )
        return results


def _record_to_dict(record: EntityRepresentationRecord) -> dict:
    return {
        "name": record.name,
        "type": record.type,
        "narrative_role": record.narrative_role,
        "objective_facts": record.objective_facts,
        "belief": record.belief,
        "emotional_charge": record.emotional_charge,
        "goal_relevance": record.goal_relevance,
        "misunderstanding": record.misunderstanding,
        "semantic_text": record.semantic_text,
    }


def _record_to_memory(record: EpisodicMemoryRecord) -> EpisodicMemory:
    return EpisodicMemory(
        character_id=record.character_id,
        replay_key=ReplayKey(
            tick=record.tick,
            timeline_index=record.timeline_index,
            event_sequence=record.event_sequence,
        ),
        event_id=record.event_id,
        participants=record.participants,
        location=record.location,
        summary=record.summary,
        emotional_tag=record.emotional_tag,
        salience=record.salience,
        pinned=record.pinned,
        compressed=record.compressed,
    )
