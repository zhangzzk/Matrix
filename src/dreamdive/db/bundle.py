from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from dreamdive.config import SimulationSettings
from dreamdive.db.postgres import (
    ensure_postgres_driver,
    PostgresEntityRepresentationRepository,
    MissingPostgresDriverError,
    PostgresConnectionFactory,
    PostgresEpisodicMemoryRepository,
    PostgresEventLogRepository,
    PostgresGoalStackRepository,
    PostgresRelationshipRepository,
    PostgresStateChangeLogRepository,
    PostgresWorldSnapshotRepository,
)
from dreamdive.db.queries import (
    EntityRepresentationRepository,
    EpisodicMemoryRepository,
    EventLogRepository,
    GoalStackRepository,
    RelationshipRepository,
    StateChangeLogRepository,
    WorldSnapshotRepository,
)
from dreamdive.db.session import InMemoryStore


@dataclass
class RepositoryBundle:
    backend_name: str
    state_repo: object
    goal_repo: object
    relationship_repo: object
    memory_repo: object
    entity_repo: object
    world_snapshot_repo: object
    event_log_repo: object
    store: Optional[InMemoryStore] = None


def build_in_memory_bundle(store: Optional[InMemoryStore] = None) -> RepositoryBundle:
    memory_store = store or InMemoryStore()
    return RepositoryBundle(
        backend_name="session",
        state_repo=StateChangeLogRepository(memory_store),
        goal_repo=GoalStackRepository(memory_store),
        relationship_repo=RelationshipRepository(memory_store),
        memory_repo=EpisodicMemoryRepository(memory_store),
        entity_repo=EntityRepresentationRepository(memory_store),
        world_snapshot_repo=WorldSnapshotRepository(memory_store),
        event_log_repo=EventLogRepository(memory_store),
        store=memory_store,
    )


def build_postgres_bundle(settings: SimulationSettings) -> RepositoryBundle:
    ensure_postgres_driver()
    connection_factory = PostgresConnectionFactory(settings.database_url)
    return RepositoryBundle(
        backend_name="postgres",
        state_repo=PostgresStateChangeLogRepository(connection_factory),
        goal_repo=PostgresGoalStackRepository(connection_factory),
        relationship_repo=PostgresRelationshipRepository(connection_factory),
        memory_repo=PostgresEpisodicMemoryRepository(connection_factory),
        entity_repo=PostgresEntityRepresentationRepository(connection_factory),
        world_snapshot_repo=PostgresWorldSnapshotRepository(connection_factory),
        event_log_repo=PostgresEventLogRepository(connection_factory),
        store=None,
    )


def build_repository_bundle(settings: SimulationSettings) -> RepositoryBundle:
    backend = settings.persistence_backend.strip().lower()
    if backend == "session":
        return build_in_memory_bundle()
    if backend == "postgres":
        return build_postgres_bundle(settings)
    raise ValueError(f"Unsupported DREAMDIVE_PERSISTENCE_BACKEND: {settings.persistence_backend}")


def postgres_backend_available(settings: SimulationSettings) -> bool:
    try:
        ensure_postgres_driver()
    except MissingPostgresDriverError:
        return False
    return True
