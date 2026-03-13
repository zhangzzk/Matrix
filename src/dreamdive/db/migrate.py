from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

from dreamdive.db.postgres import PostgresConnectionFactory


DEFAULT_MIGRATION_PATH = Path(__file__).resolve().parents[3] / "migrations" / "0001_initial_schema.sql"


class PostgresMigrationRunner:
    def __init__(
        self,
        connection_factory: Callable[[], object],
        *,
        migration_path: Optional[Path] = None,
    ) -> None:
        self.connection_factory = connection_factory
        self.migration_path = migration_path or DEFAULT_MIGRATION_PATH

    def load_sql(self) -> str:
        return self.migration_path.read_text(encoding="utf-8")

    def apply(self) -> str:
        sql = self.load_sql()
        with self.connection_factory() as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql)
            conn.commit()
        return sql


def build_migration_runner(database_url: str) -> PostgresMigrationRunner:
    return PostgresMigrationRunner(PostgresConnectionFactory(database_url))
