"""Database helpers for append-only simulation state."""

from dreamdive.db.bundle import (
    RepositoryBundle,
    build_in_memory_bundle,
    build_postgres_bundle,
    build_repository_bundle,
    postgres_backend_available,
)
from dreamdive.db.postgres import (
    MissingPostgresDriverError,
    PostgresConnectionFactory,
    PostgresEpisodicMemoryRepository,
    PostgresEventLogRepository,
    PostgresGoalStackRepository,
    PostgresRelationshipRepository,
    PostgresStateChangeLogRepository,
    PostgresWorldSnapshotRepository,
    normalize_database_url,
)

__all__ = [
    "RepositoryBundle",
    "MissingPostgresDriverError",
    "PostgresConnectionFactory",
    "PostgresEpisodicMemoryRepository",
    "PostgresEventLogRepository",
    "PostgresGoalStackRepository",
    "PostgresRelationshipRepository",
    "PostgresStateChangeLogRepository",
    "PostgresWorldSnapshotRepository",
    "build_in_memory_bundle",
    "build_postgres_bundle",
    "build_repository_bundle",
    "normalize_database_url",
    "postgres_backend_available",
]
