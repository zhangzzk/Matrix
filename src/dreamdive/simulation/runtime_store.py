from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Mapping, Optional

from dreamdive.config import SimulationSettings, get_settings
from dreamdive.db.postgres import (
    PostgresConnectionFactory,
    ensure_postgres_driver,
)
from dreamdive.simulation.session_repair import repair_session_state
from dreamdive.simulation.session import SimulationSessionState


class SimulationRuntimeStore:
    def __init__(self, workspace_dir: Path, *, session_id: str = "default") -> None:
        self.workspace_dir = workspace_dir
        self.session_id = session_id
        filename = "simulation_session.json"
        if session_id != "default":
            filename = f"simulation_session.{session_id}.json"
        self.path = workspace_dir / filename

    def load(self) -> SimulationSessionState:
        data = json.loads(self.path.read_text(encoding="utf-8"))
        return repair_session_state(SimulationSessionState.model_validate(data))

    def save(self, session: SimulationSessionState) -> None:
        self.workspace_dir.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(session.model_dump(mode="json"), indent=2, sort_keys=True, ensure_ascii=False),
            encoding="utf-8",
        )

    def exists(self) -> bool:
        return self.path.exists()


def _row_to_mapping(cursor: Any, row: Any) -> dict:
    if row is None:
        return {}
    if isinstance(row, Mapping):
        return dict(row)
    columns = [item[0] for item in getattr(cursor, "description", [])]
    return dict(zip(columns, row))


class PostgresSimulationRuntimeStore:
    def __init__(
        self,
        connection_factory: Callable[[], Any],
        *,
        session_id: str = "default",
    ) -> None:
        self.connection_factory = connection_factory
        self.session_id = session_id

    def load(self) -> SimulationSessionState:
        with self.connection_factory() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT session_payload
                    FROM simulation_session
                    WHERE session_id = %s
                    """,
                    (self.session_id,),
                )
                row = cursor.fetchone()
        if row is None:
            raise FileNotFoundError(f"Simulation session '{self.session_id}' not found")
        payload = _row_to_mapping(cursor, row).get("session_payload")
        data = json.loads(payload) if isinstance(payload, str) else payload
        return repair_session_state(SimulationSessionState.model_validate(data))

    def save(self, session: SimulationSessionState) -> None:
        payload = json.dumps(session.model_dump(mode="json"), sort_keys=True, ensure_ascii=False)
        with self.connection_factory() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO simulation_session (
                        session_id, source_path, current_tick_label, current_timeline_index, session_payload
                    ) VALUES (%s, %s, %s, %s, %s::jsonb)
                    ON CONFLICT (session_id) DO UPDATE SET
                        source_path = EXCLUDED.source_path,
                        current_tick_label = EXCLUDED.current_tick_label,
                        current_timeline_index = EXCLUDED.current_timeline_index,
                        session_payload = EXCLUDED.session_payload,
                        updated_at = NOW()
                    """,
                    (
                        self.session_id,
                        session.source_path,
                        session.current_tick_label,
                        session.current_timeline_index,
                        payload,
                    ),
                )
            conn.commit()

    def exists(self) -> bool:
        with self.connection_factory() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT session_id
                    FROM simulation_session
                    WHERE session_id = %s
                    """,
                    (self.session_id,),
                )
                return cursor.fetchone() is not None


def build_runtime_store(
    workspace_dir: Path,
    *,
    settings: Optional[SimulationSettings] = None,
    session_id: str = "default",
    connection_factory: Optional[Callable[[], Any]] = None,
):
    active_settings = settings or get_settings()
    backend = active_settings.persistence_backend.strip().lower()
    if backend == "postgres":
        factory = connection_factory
        if factory is None:
            ensure_postgres_driver()
            factory = PostgresConnectionFactory(active_settings.database_url)
        return PostgresSimulationRuntimeStore(factory, session_id=session_id)
    return SimulationRuntimeStore(workspace_dir, session_id=session_id)
