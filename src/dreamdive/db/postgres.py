from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence

from dreamdive.db.models import (
    EntityRepresentationRecord,
    EpisodicMemoryRecord,
    EventLogRecord,
    GoalStackRecord,
    RelationshipLogRecord,
    StateChangeLogRecord,
    WorldSnapshotRecord,
)
from dreamdive.memory.retrieval import (
    build_entity_semantic_text,
    build_memory_semantic_text,
    embed_text,
)
from dreamdive.schemas import (
    EpisodicMemory,
    Goal,
    GoalStackSnapshot,
    RelationshipLogEntry,
    ReplayKey,
    StateChangeLogEntry,
    SubjectiveEntityRepresentation,
    WorldSnapshot,
)


class MissingPostgresDriverError(RuntimeError):
    pass


def ensure_postgres_driver() -> None:
    try:
        import psycopg  # type: ignore  # noqa: F401
    except ImportError as exc:
        raise MissingPostgresDriverError(
            "psycopg is not installed. Install it to use the PostgreSQL repositories."
        ) from exc


def normalize_database_url(database_url: str) -> str:
    return database_url.replace("postgresql+psycopg://", "postgresql://", 1)


def default_postgres_connector(database_url: str):
    ensure_postgres_driver()
    import psycopg  # type: ignore

    return psycopg.connect(normalize_database_url(database_url))


def _row_to_mapping(cursor: Any, row: Any) -> Dict[str, Any]:
    if row is None:
        return {}
    if isinstance(row, Mapping):
        return dict(row)
    columns = [item[0] for item in getattr(cursor, "description", [])]
    return dict(zip(columns, row))


def _json_dumps(value: Any) -> str:
    return json.dumps(value, sort_keys=True)


def _json_load(value: Any) -> Any:
    if isinstance(value, str):
        return json.loads(value)
    return value


def _stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _vector_literal(values: Sequence[float]) -> str:
    return "[" + ",".join(f"{float(value):.12f}" for value in values) + "]"


def state_change_idempotency_key(entry: StateChangeLogEntry) -> str:
    return "|".join(
        [
            "state",
            entry.character_id,
            entry.dimension,
            str(entry.replay_key.timeline_index),
            str(entry.replay_key.event_sequence),
            entry.event_id or "",
            _stable_json(entry.to_value),
        ]
    )


def goal_stack_idempotency_key(snapshot: GoalStackSnapshot) -> str:
    return "|".join(
        [
            "goal",
            snapshot.character_id,
            str(snapshot.replay_key.timeline_index),
            str(snapshot.replay_key.event_sequence),
            _stable_json([goal.model_dump(mode="json") for goal in snapshot.goals]),
        ]
    )


def relationship_idempotency_key(entry: RelationshipLogEntry) -> str:
    return "|".join(
        [
            "relationship",
            entry.from_character_id,
            entry.to_character_id,
            str(entry.replay_key.timeline_index),
            str(entry.replay_key.event_sequence),
            entry.event_id or "",
            str(entry.trust_value),
            entry.sentiment_shift,
        ]
    )


def episodic_memory_idempotency_key(memory: EpisodicMemory) -> str:
    return "|".join(
        [
            "memory",
            memory.character_id,
            str(memory.replay_key.timeline_index),
            str(memory.replay_key.event_sequence),
            memory.event_id or "",
            memory.summary,
        ]
    )


def world_snapshot_idempotency_key(snapshot: WorldSnapshot) -> str:
    return "|".join(
        [
            "world_snapshot",
            str(snapshot.replay_key.timeline_index),
            str(snapshot.replay_key.event_sequence),
        ]
    )


def _goal_stack_from_row(row: Mapping[str, Any]) -> GoalStackSnapshot:
    return GoalStackSnapshot(
        character_id=str(row["character_id"]),
        replay_key=ReplayKey(
            tick=str(row["tick"]),
            timeline_index=int(row["timeline_index"]),
            event_sequence=int(row["event_sequence"]),
        ),
        goals=[Goal.model_validate(goal) for goal in _json_load(row["goals"])],
        actively_avoiding=row.get("actively_avoiding"),
        most_uncertain_relationship=row.get("most_uncertain_relationship"),
    )


@dataclass
class PostgresConnectionFactory:
    database_url: str
    connector: Callable[[str], Any] = default_postgres_connector

    def __call__(self):
        return self.connector(self.database_url)


class PostgresRepositoryBase:
    def __init__(self, connection_factory: Callable[[], Any]) -> None:
        self.connection_factory = connection_factory

    def _execute_returning_one(self, sql: str, params: Sequence[Any]) -> Dict[str, Any]:
        with self.connection_factory() as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql, params)
                row = _row_to_mapping(cursor, cursor.fetchone())
            conn.commit()
        return row

    def _execute_fetch_all(self, sql: str, params: Sequence[Any]) -> List[Dict[str, Any]]:
        with self.connection_factory() as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql, params)
                rows = cursor.fetchall()
                return [_row_to_mapping(cursor, row) for row in rows]

    def _execute_fetch_one(self, sql: str, params: Sequence[Any]) -> Optional[Dict[str, Any]]:
        with self.connection_factory() as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql, params)
                row = cursor.fetchone()
                if row is None:
                    return None
                return _row_to_mapping(cursor, row)


class PostgresStateChangeLogRepository(PostgresRepositoryBase):
    def append(self, entry: StateChangeLogEntry) -> StateChangeLogRecord:
        row = self._execute_returning_one(
            """
            INSERT INTO state_change_log (
                idempotency_key, character_id, dimension, tick, timeline_index, event_sequence,
                event_id, from_value, to_value, trigger, emotional_tag, pinned
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s, %s, %s)
            ON CONFLICT (idempotency_key) DO UPDATE SET
                event_id = EXCLUDED.event_id,
                from_value = EXCLUDED.from_value,
                to_value = EXCLUDED.to_value,
                trigger = EXCLUDED.trigger,
                emotional_tag = EXCLUDED.emotional_tag,
                pinned = EXCLUDED.pinned
            RETURNING id, character_id, dimension, tick, timeline_index, event_sequence,
                      event_id, from_value, to_value, trigger, emotional_tag, pinned
            """,
            (
                state_change_idempotency_key(entry),
                entry.character_id,
                entry.dimension,
                entry.replay_key.tick,
                entry.replay_key.timeline_index,
                entry.replay_key.event_sequence,
                entry.event_id,
                _json_dumps(entry.from_value),
                _json_dumps(entry.to_value),
                entry.trigger,
                entry.emotional_tag,
                entry.pinned,
            ),
        )
        return StateChangeLogRecord(
            id=int(row["id"]),
            character_id=str(row["character_id"]),
            dimension=str(row["dimension"]),
            tick=str(row["tick"]),
            timeline_index=int(row["timeline_index"]),
            event_sequence=int(row["event_sequence"]),
            event_id=row.get("event_id"),
            from_value=_json_load(row.get("from_value")),
            to_value=_json_load(row["to_value"]),
            trigger=row.get("trigger"),
            emotional_tag=row.get("emotional_tag"),
            pinned=bool(row["pinned"]),
        )

    def list_until(
        self,
        character_id: str,
        dimension: str,
        timeline_index: int,
    ) -> Sequence[StateChangeLogRecord]:
        rows = self._execute_fetch_all(
            """
            SELECT id, character_id, dimension, tick, timeline_index, event_sequence,
                   event_id, from_value, to_value, trigger, emotional_tag, pinned
            FROM state_change_log
            WHERE character_id = %s
              AND dimension = %s
              AND timeline_index <= %s
            ORDER BY timeline_index ASC, event_sequence ASC, id ASC
            """,
            (character_id, dimension, timeline_index),
        )
        return [
            StateChangeLogRecord(
                id=int(row["id"]),
                character_id=str(row["character_id"]),
                dimension=str(row["dimension"]),
                tick=str(row["tick"]),
                timeline_index=int(row["timeline_index"]),
                event_sequence=int(row["event_sequence"]),
                event_id=row.get("event_id"),
                from_value=_json_load(row.get("from_value")),
                to_value=_json_load(row["to_value"]),
                trigger=row.get("trigger"),
                emotional_tag=row.get("emotional_tag"),
                pinned=bool(row["pinned"]),
            )
            for row in rows
        ]

    def list_for_character(
        self,
        character_id: str,
        timeline_index: int,
    ) -> Sequence[StateChangeLogEntry]:
        rows = self._execute_fetch_all(
            """
            SELECT character_id, dimension, tick, timeline_index, event_sequence,
                   event_id, from_value, to_value, trigger, emotional_tag, pinned
            FROM state_change_log
            WHERE character_id = %s
              AND timeline_index <= %s
            ORDER BY timeline_index ASC, event_sequence ASC, id ASC
            """,
            (character_id, timeline_index),
        )
        return [
            StateChangeLogEntry(
                character_id=str(row["character_id"]),
                dimension=str(row["dimension"]),
                replay_key=ReplayKey(
                    tick=str(row["tick"]),
                    timeline_index=int(row["timeline_index"]),
                    event_sequence=int(row["event_sequence"]),
                ),
                event_id=row.get("event_id"),
                from_value=_json_load(row.get("from_value")),
                to_value=_json_load(row["to_value"]),
                trigger=row.get("trigger"),
                emotional_tag=row.get("emotional_tag"),
                pinned=bool(row["pinned"]),
            )
            for row in rows
        ]


class PostgresGoalStackRepository(PostgresRepositoryBase):
    def append(self, snapshot: GoalStackSnapshot) -> GoalStackRecord:
        row = self._execute_returning_one(
            """
            INSERT INTO goal_stack (
                idempotency_key, character_id, tick, timeline_index, event_sequence,
                goals, actively_avoiding, most_uncertain_relationship
            ) VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s, %s)
            ON CONFLICT (idempotency_key) DO UPDATE SET
                goals = EXCLUDED.goals,
                actively_avoiding = EXCLUDED.actively_avoiding,
                most_uncertain_relationship = EXCLUDED.most_uncertain_relationship
            RETURNING id, character_id, tick, timeline_index, event_sequence,
                      goals, actively_avoiding, most_uncertain_relationship
            """,
            (
                goal_stack_idempotency_key(snapshot),
                snapshot.character_id,
                snapshot.replay_key.tick,
                snapshot.replay_key.timeline_index,
                snapshot.replay_key.event_sequence,
                _json_dumps([goal.model_dump(mode="json") for goal in snapshot.goals]),
                snapshot.actively_avoiding,
                snapshot.most_uncertain_relationship,
            ),
        )
        return GoalStackRecord(
            id=int(row["id"]),
            character_id=str(row["character_id"]),
            tick=str(row["tick"]),
            timeline_index=int(row["timeline_index"]),
            event_sequence=int(row["event_sequence"]),
            goals=_json_load(row["goals"]),
            actively_avoiding=row.get("actively_avoiding"),
            most_uncertain_relationship=row.get("most_uncertain_relationship"),
        )

    def latest_at_or_before(
        self,
        character_id: str,
        timeline_index: int,
    ) -> Optional[GoalStackSnapshot]:
        row = self._execute_fetch_one(
            """
            SELECT id, character_id, tick, timeline_index, event_sequence,
                   goals, actively_avoiding, most_uncertain_relationship
            FROM goal_stack
            WHERE character_id = %s
              AND timeline_index <= %s
            ORDER BY timeline_index DESC, event_sequence DESC, id DESC
            LIMIT 1
            """,
            (character_id, timeline_index),
        )
        if row is None:
            return None
        return _goal_stack_from_row(row)

    def list_for_character(
        self,
        character_id: str,
        timeline_index: int,
    ) -> Sequence[GoalStackSnapshot]:
        rows = self._execute_fetch_all(
            """
            SELECT character_id, tick, timeline_index, event_sequence,
                   goals, actively_avoiding, most_uncertain_relationship
            FROM goal_stack
            WHERE character_id = %s
              AND timeline_index <= %s
            ORDER BY timeline_index ASC, event_sequence ASC, id ASC
            """,
            (character_id, timeline_index),
        )
        return [_goal_stack_from_row(row) for row in rows]


class PostgresRelationshipRepository(PostgresRepositoryBase):
    def append(self, entry: RelationshipLogEntry) -> RelationshipLogRecord:
        row = self._execute_returning_one(
            """
            INSERT INTO relationship_log (
                idempotency_key, from_character_id, to_character_id, tick, timeline_index, event_sequence,
                event_id, trust_delta, trust_value, sentiment_shift, reason, pinned
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (idempotency_key) DO UPDATE SET
                trust_delta = EXCLUDED.trust_delta,
                trust_value = EXCLUDED.trust_value,
                sentiment_shift = EXCLUDED.sentiment_shift,
                reason = EXCLUDED.reason,
                pinned = EXCLUDED.pinned
            RETURNING id, from_character_id, to_character_id, tick, timeline_index,
                      event_sequence, event_id, trust_delta, trust_value,
                      sentiment_shift, reason, pinned
            """,
            (
                relationship_idempotency_key(entry),
                entry.from_character_id,
                entry.to_character_id,
                entry.replay_key.tick,
                entry.replay_key.timeline_index,
                entry.replay_key.event_sequence,
                entry.event_id,
                entry.trust_delta,
                entry.trust_value,
                entry.sentiment_shift,
                entry.reason,
                entry.pinned,
            ),
        )
        return RelationshipLogRecord(
            id=int(row["id"]),
            from_character_id=str(row["from_character_id"]),
            to_character_id=str(row["to_character_id"]),
            tick=str(row["tick"]),
            timeline_index=int(row["timeline_index"]),
            event_sequence=int(row["event_sequence"]),
            event_id=row.get("event_id"),
            trust_delta=float(row["trust_delta"]),
            trust_value=float(row["trust_value"]),
            sentiment_shift=str(row["sentiment_shift"]),
            reason=str(row["reason"]),
            pinned=bool(row["pinned"]),
        )

    def latest_for_participants(
        self,
        from_character_id: str,
        to_character_ids: Sequence[str],
        timeline_index: int,
    ) -> Sequence[RelationshipLogRecord]:
        if not to_character_ids:
            return []
        rows = self._execute_fetch_all(
            """
            SELECT DISTINCT ON (to_character_id)
                   id, from_character_id, to_character_id, tick, timeline_index, event_sequence,
                   event_id, trust_delta, trust_value, sentiment_shift, reason, pinned
            FROM relationship_log
            WHERE from_character_id = %s
              AND to_character_id = ANY(%s)
              AND timeline_index <= %s
            ORDER BY to_character_id, timeline_index DESC, event_sequence DESC, id DESC
            """,
            (from_character_id, list(to_character_ids), timeline_index),
        )
        return [
            RelationshipLogRecord(
                id=int(row["id"]),
                from_character_id=str(row["from_character_id"]),
                to_character_id=str(row["to_character_id"]),
                tick=str(row["tick"]),
                timeline_index=int(row["timeline_index"]),
                event_sequence=int(row["event_sequence"]),
                event_id=row.get("event_id"),
                trust_delta=float(row["trust_delta"]),
                trust_value=float(row["trust_value"]),
                sentiment_shift=str(row["sentiment_shift"]),
                reason=str(row["reason"]),
                pinned=bool(row["pinned"]),
            )
            for row in rows
        ]

    def list_from_character(
        self,
        from_character_id: str,
        timeline_index: int,
    ) -> Sequence[RelationshipLogEntry]:
        rows = self._execute_fetch_all(
            """
            SELECT from_character_id, to_character_id, tick, timeline_index, event_sequence,
                   event_id, trust_delta, trust_value, sentiment_shift, reason, pinned
            FROM relationship_log
            WHERE from_character_id = %s
              AND timeline_index <= %s
            ORDER BY timeline_index ASC, event_sequence ASC, id ASC
            """,
            (from_character_id, timeline_index),
        )
        return [
            RelationshipLogEntry(
                from_character_id=str(row["from_character_id"]),
                to_character_id=str(row["to_character_id"]),
                replay_key=ReplayKey(
                    tick=str(row["tick"]),
                    timeline_index=int(row["timeline_index"]),
                    event_sequence=int(row["event_sequence"]),
                ),
                event_id=row.get("event_id"),
                trust_delta=float(row["trust_delta"]),
                trust_value=float(row["trust_value"]),
                sentiment_shift=str(row["sentiment_shift"]),
                reason=str(row["reason"]),
                pinned=bool(row["pinned"]),
            )
            for row in rows
        ]


class PostgresEpisodicMemoryRepository(PostgresRepositoryBase):
    def append(self, memory: EpisodicMemory) -> EpisodicMemoryRecord:
        embedding = memory.embedding or embed_text(build_memory_semantic_text(memory))
        row = self._execute_returning_one(
            """
            INSERT INTO episodic_memory (
                idempotency_key, character_id, tick, timeline_index, event_sequence, event_id,
                participants, location, summary, emotional_tag, salience, pinned,
                compressed, embedding
            ) VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (idempotency_key) DO UPDATE SET
                participants = EXCLUDED.participants,
                location = EXCLUDED.location,
                summary = EXCLUDED.summary,
                emotional_tag = EXCLUDED.emotional_tag,
                salience = EXCLUDED.salience,
                pinned = EXCLUDED.pinned,
                compressed = EXCLUDED.compressed,
                embedding = EXCLUDED.embedding
            RETURNING id, character_id, tick, timeline_index, event_sequence, event_id,
                      participants, location, summary, emotional_tag, salience, pinned,
                      compressed, embedding
            """,
            (
                episodic_memory_idempotency_key(memory),
                memory.character_id,
                memory.replay_key.tick,
                memory.replay_key.timeline_index,
                memory.replay_key.event_sequence,
                memory.event_id,
                _json_dumps(memory.participants),
                memory.location,
                memory.summary,
                memory.emotional_tag,
                memory.salience,
                memory.pinned,
                memory.compressed,
                embedding,
            ),
        )
        return EpisodicMemoryRecord(
            id=int(row["id"]),
            character_id=str(row["character_id"]),
            tick=str(row["tick"]),
            timeline_index=int(row["timeline_index"]),
            event_sequence=int(row["event_sequence"]),
            summary=str(row["summary"]),
            salience=float(row["salience"]),
            event_id=row.get("event_id"),
            participants=list(_json_load(row["participants"])),
            location=row.get("location"),
            emotional_tag=row.get("emotional_tag"),
            pinned=bool(row["pinned"]),
            compressed=bool(row["compressed"]),
            embedding=row.get("embedding"),
        )

    def list_for_character(
        self,
        character_id: str,
        *,
        timeline_index: Optional[int] = None,
    ) -> Sequence[EpisodicMemory]:
        sql = """
            SELECT character_id, tick, timeline_index, event_sequence, event_id,
                   participants, location, summary, emotional_tag, salience, pinned, compressed, embedding
            FROM episodic_memory
            WHERE character_id = %s
        """
        params: List[Any] = [character_id]
        if timeline_index is not None:
            sql += " AND timeline_index <= %s"
            params.append(timeline_index)
        sql += " ORDER BY timeline_index ASC, event_sequence ASC, id ASC"
        rows = self._execute_fetch_all(sql, params)
        return [
            EpisodicMemory(
                character_id=str(row["character_id"]),
                replay_key=ReplayKey(
                    tick=str(row["tick"]),
                    timeline_index=int(row["timeline_index"]),
                    event_sequence=int(row["event_sequence"]),
                ),
                event_id=row.get("event_id"),
                participants=list(_json_load(row["participants"])),
                location=row.get("location"),
                summary=str(row["summary"]),
                emotional_tag=row.get("emotional_tag"),
                salience=float(row["salience"]),
                pinned=bool(row["pinned"]),
                compressed=bool(row["compressed"]),
                embedding=row.get("embedding"),
            )
            for row in rows
        ]

    def list_pinned_for_character(
        self,
        character_id: str,
        *,
        timeline_index: Optional[int] = None,
    ) -> Sequence[EpisodicMemory]:
        sql = """
            SELECT character_id, tick, timeline_index, event_sequence, event_id,
                   participants, location, summary, emotional_tag, salience, pinned, compressed, embedding
            FROM episodic_memory
            WHERE character_id = %s
              AND pinned = TRUE
        """
        params: List[Any] = [character_id]
        if timeline_index is not None:
            sql += " AND timeline_index <= %s"
            params.append(timeline_index)
        sql += " ORDER BY timeline_index ASC, event_sequence ASC, id ASC"
        rows = self._execute_fetch_all(sql, params)
        return [
            EpisodicMemory(
                character_id=str(row["character_id"]),
                replay_key=ReplayKey(
                    tick=str(row["tick"]),
                    timeline_index=int(row["timeline_index"]),
                    event_sequence=int(row["event_sequence"]),
                ),
                event_id=row.get("event_id"),
                participants=list(_json_load(row["participants"])),
                location=row.get("location"),
                summary=str(row["summary"]),
                emotional_tag=row.get("emotional_tag"),
                salience=float(row["salience"]),
                pinned=bool(row["pinned"]),
                compressed=bool(row["compressed"]),
                embedding=row.get("embedding"),
            )
            for row in rows
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
        vector = _vector_literal(query_embedding)
        sql = """
            SELECT character_id, tick, timeline_index, event_sequence, event_id,
                   participants, location, summary, emotional_tag, salience, pinned, compressed, embedding,
                   GREATEST(0.0, 1 - (embedding <=> %s::vector)) AS semantic_score
            FROM episodic_memory
            WHERE character_id = %s
              AND embedding IS NOT NULL
        """
        params: List[Any] = [vector, character_id]
        if not include_compressed:
            sql += " AND compressed = FALSE"
        if timeline_index is not None:
            sql += " AND timeline_index <= %s"
            params.append(timeline_index)
        sql += " ORDER BY embedding <=> %s::vector ASC, timeline_index DESC, event_sequence DESC LIMIT %s"
        params.extend([vector, max(0, limit)])
        rows = self._execute_fetch_all(sql, params)
        return [
            EpisodicMemory(
                character_id=str(row["character_id"]),
                replay_key=ReplayKey(
                    tick=str(row["tick"]),
                    timeline_index=int(row["timeline_index"]),
                    event_sequence=int(row["event_sequence"]),
                ),
                event_id=row.get("event_id"),
                participants=list(_json_load(row["participants"])),
                location=row.get("location"),
                summary=str(row["summary"]),
                emotional_tag=row.get("emotional_tag"),
                salience=float(row["salience"]),
                pinned=bool(row["pinned"]),
                compressed=bool(row["compressed"]),
                semantic_score=float(row.get("semantic_score", 0.0)),
                embedding=row.get("embedding"),
            )
            for row in rows
        ]

class PostgresEntityRepresentationRepository(PostgresRepositoryBase):
    def append(self, representation: SubjectiveEntityRepresentation) -> EntityRepresentationRecord:
        semantic_text = representation.semantic_text or build_entity_semantic_text(
            representation.model_dump(mode="json")
        )
        semantic_embedding = representation.semantic_embedding or embed_text(semantic_text)
        with self.connection_factory() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO entity (id, name, type, objective_facts, narrative_role, embedding)
                    VALUES (%s, %s, %s, %s::jsonb, %s, %s)
                    ON CONFLICT (id) DO UPDATE SET
                        name = EXCLUDED.name,
                        type = EXCLUDED.type,
                        objective_facts = EXCLUDED.objective_facts,
                        narrative_role = EXCLUDED.narrative_role,
                        embedding = EXCLUDED.embedding
                    """,
                    (
                        representation.entity_id,
                        representation.name,
                        representation.type,
                        _json_dumps(representation.objective_facts),
                        representation.narrative_role,
                        semantic_embedding,
                    ),
                )
                cursor.execute(
                    """
                    INSERT INTO entity_representation (
                        entity_id, agent_id, meaning, emotional_charge,
                        goal_relevance, misunderstanding, confidence
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (entity_id, agent_id) DO UPDATE SET
                        meaning = EXCLUDED.meaning,
                        emotional_charge = EXCLUDED.emotional_charge,
                        goal_relevance = EXCLUDED.goal_relevance,
                        misunderstanding = EXCLUDED.misunderstanding,
                        confidence = EXCLUDED.confidence
                    RETURNING id, entity_id, agent_id, meaning, emotional_charge,
                              goal_relevance, misunderstanding, confidence
                    """,
                    (
                        representation.entity_id,
                        representation.agent_id,
                        representation.belief,
                        representation.emotional_charge,
                        representation.goal_relevance,
                        representation.misunderstanding,
                        representation.confidence,
                    ),
                )
                row = _row_to_mapping(cursor, cursor.fetchone())
            conn.commit()
        return EntityRepresentationRecord(
            id=int(row["id"]),
            agent_id=str(row["agent_id"]),
            entity_id=str(row["entity_id"]),
            name=representation.name,
            type=representation.type,
            narrative_role=representation.narrative_role,
            objective_facts=list(representation.objective_facts),
            belief=str(row["meaning"]),
            emotional_charge=str(row["emotional_charge"]),
            goal_relevance=str(row["goal_relevance"]),
            misunderstanding=str(row["misunderstanding"]),
            confidence=str(row["confidence"]),
            semantic_text=semantic_text,
            semantic_embedding=semantic_embedding,
        )

    def list_for_agent(self, agent_id: str) -> Sequence[SubjectiveEntityRepresentation]:
        rows = self._execute_fetch_all(
            """
            SELECT er.id, er.entity_id, er.agent_id, er.meaning, er.emotional_charge,
                   er.goal_relevance, er.misunderstanding, er.confidence,
                   e.name, e.type, e.narrative_role, e.objective_facts, e.embedding
            FROM entity_representation er
            JOIN entity e ON e.id = er.entity_id
            WHERE er.agent_id = %s
            ORDER BY e.name ASC, er.entity_id ASC
            """,
            (agent_id,),
        )
        return [
            SubjectiveEntityRepresentation(
                agent_id=str(row["agent_id"]),
                entity_id=str(row["entity_id"]),
                name=str(row["name"]),
                type=str(row["type"]),
                narrative_role=str(row["narrative_role"]),
                objective_facts=list(_json_load(row["objective_facts"])),
                belief=str(row["meaning"]),
                emotional_charge=str(row["emotional_charge"]),
                goal_relevance=str(row["goal_relevance"]),
                misunderstanding=str(row["misunderstanding"]),
                confidence=str(row["confidence"]),
                semantic_text=build_entity_semantic_text(
                    {
                        "name": row["name"],
                        "type": row["type"],
                        "narrative_role": row["narrative_role"],
                        "belief": row["meaning"],
                        "emotional_charge": row["emotional_charge"],
                        "goal_relevance": row["goal_relevance"],
                        "misunderstanding": row["misunderstanding"],
                    }
                ),
                semantic_embedding=row.get("embedding"),
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
        vector = _vector_literal(query_embedding)
        rows = self._execute_fetch_all(
            """
            SELECT er.id, er.entity_id, er.agent_id, er.meaning, er.emotional_charge,
                   er.goal_relevance, er.misunderstanding, er.confidence,
                   e.name, e.type, e.narrative_role, e.objective_facts, e.embedding
            FROM entity_representation er
            JOIN entity e ON e.id = er.entity_id
            WHERE er.agent_id = %s
              AND e.embedding IS NOT NULL
            ORDER BY e.embedding <=> %s::vector ASC, e.name ASC
            LIMIT %s
            """,
            (agent_id, vector, max(0, limit)),
        )
        return [
            SubjectiveEntityRepresentation(
                agent_id=str(row["agent_id"]),
                entity_id=str(row["entity_id"]),
                name=str(row["name"]),
                type=str(row["type"]),
                narrative_role=str(row["narrative_role"]),
                objective_facts=list(_json_load(row["objective_facts"])),
                belief=str(row["meaning"]),
                emotional_charge=str(row["emotional_charge"]),
                goal_relevance=str(row["goal_relevance"]),
                misunderstanding=str(row["misunderstanding"]),
                confidence=str(row["confidence"]),
                semantic_text=build_entity_semantic_text(
                    {
                        "name": row["name"],
                        "type": row["type"],
                        "narrative_role": row["narrative_role"],
                        "belief": row["meaning"],
                        "emotional_charge": row["emotional_charge"],
                        "goal_relevance": row["goal_relevance"],
                        "misunderstanding": row["misunderstanding"],
                    }
                ),
                semantic_embedding=row.get("embedding"),
            )
            for row in rows
        ]


class PostgresWorldSnapshotRepository(PostgresRepositoryBase):
    def append(self, snapshot: WorldSnapshot) -> WorldSnapshotRecord:
        row = self._execute_returning_one(
            """
            INSERT INTO world_snapshot (
                idempotency_key, tick, timeline_index, event_sequence, agent_locations,
                narrative_arc, unresolved_threads, next_tick_size_minutes
            ) VALUES (%s, %s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb, %s)
            ON CONFLICT (idempotency_key) DO UPDATE SET
                agent_locations = EXCLUDED.agent_locations,
                narrative_arc = EXCLUDED.narrative_arc,
                unresolved_threads = EXCLUDED.unresolved_threads,
                next_tick_size_minutes = EXCLUDED.next_tick_size_minutes
            RETURNING id, tick, timeline_index, event_sequence, agent_locations,
                      narrative_arc, unresolved_threads, next_tick_size_minutes
            """,
            (
                world_snapshot_idempotency_key(snapshot),
                snapshot.replay_key.tick,
                snapshot.replay_key.timeline_index,
                snapshot.replay_key.event_sequence,
                _json_dumps(snapshot.agent_locations),
                _json_dumps(snapshot.narrative_arc.model_dump(mode="json")),
                _json_dumps(snapshot.unresolved_threads),
                snapshot.next_tick_size_minutes,
            ),
        )
        return WorldSnapshotRecord(
            id=int(row["id"]),
            tick=str(row["tick"]),
            timeline_index=int(row["timeline_index"]),
            event_sequence=int(row["event_sequence"]),
            agent_locations=dict(_json_load(row["agent_locations"])),
            narrative_arc=dict(_json_load(row["narrative_arc"])),
            unresolved_threads=list(_json_load(row["unresolved_threads"])),
            next_tick_size_minutes=int(row["next_tick_size_minutes"]),
        )

    def list_until(self, timeline_index: int) -> Sequence[WorldSnapshot]:
        rows = self._execute_fetch_all(
            """
            SELECT tick, timeline_index, event_sequence, agent_locations,
                   narrative_arc, unresolved_threads, next_tick_size_minutes
            FROM world_snapshot
            WHERE timeline_index <= %s
            ORDER BY timeline_index ASC, event_sequence ASC, id ASC
            """,
            (timeline_index,),
        )
        return [
            WorldSnapshot(
                replay_key=ReplayKey(
                    tick=str(row["tick"]),
                    timeline_index=int(row["timeline_index"]),
                    event_sequence=int(row["event_sequence"]),
                ),
                agent_locations=dict(_json_load(row["agent_locations"])),
                narrative_arc=_json_load(row["narrative_arc"]),
                unresolved_threads=list(_json_load(row["unresolved_threads"])),
                next_tick_size_minutes=int(row["next_tick_size_minutes"]),
            )
            for row in rows
        ]


class PostgresEventLogRepository(PostgresRepositoryBase):
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
        row = self._execute_returning_one(
            """
            INSERT INTO event_log (
                event_id, tick, timeline_index, seed_type, location,
                participants, description, salience, outcome_summary, resolution_mode
            ) VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s)
            ON CONFLICT (event_id) DO UPDATE SET
                tick = EXCLUDED.tick,
                timeline_index = EXCLUDED.timeline_index,
                seed_type = EXCLUDED.seed_type,
                location = EXCLUDED.location,
                participants = EXCLUDED.participants,
                description = EXCLUDED.description,
                salience = EXCLUDED.salience,
                outcome_summary = EXCLUDED.outcome_summary,
                resolution_mode = EXCLUDED.resolution_mode
            RETURNING id, event_id, tick, timeline_index, seed_type, location,
                      participants, description, salience, outcome_summary, resolution_mode
            """,
            (
                event_id,
                replay_key.tick,
                replay_key.timeline_index,
                seed_type,
                location,
                _json_dumps(list(participants)),
                description,
                salience,
                outcome_summary,
                resolution_mode,
            ),
        )
        return EventLogRecord(
            id=int(row["id"]),
            event_id=str(row["event_id"]),
            tick=str(row["tick"]),
            timeline_index=int(row["timeline_index"]),
            seed_type=str(row["seed_type"]),
            location=str(row["location"]),
            participants=list(_json_load(row["participants"])),
            description=str(row["description"]),
            salience=float(row["salience"]),
            outcome_summary=str(row["outcome_summary"]),
            resolution_mode=str(row["resolution_mode"]),
        )

    def list_until(self, timeline_index: int) -> Sequence[EventLogRecord]:
        rows = self._execute_fetch_all(
            """
            SELECT id, event_id, tick, timeline_index, seed_type, location,
                   participants, description, salience, outcome_summary, resolution_mode
            FROM event_log
            WHERE timeline_index <= %s
            ORDER BY timeline_index ASC, id ASC
            """,
            (timeline_index,),
        )
        return [
            EventLogRecord(
                id=int(row["id"]),
                event_id=str(row["event_id"]),
                tick=str(row["tick"]),
                timeline_index=int(row["timeline_index"]),
                seed_type=str(row["seed_type"]),
                location=str(row["location"]),
                participants=list(_json_load(row["participants"])),
                description=str(row["description"]),
                salience=float(row["salience"]),
                outcome_summary=str(row["outcome_summary"]),
                resolution_mode=str(row["resolution_mode"]),
            )
            for row in rows
        ]
