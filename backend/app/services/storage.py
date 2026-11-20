from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.config import settings


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


class RunRepository:
    """Small SQLite repository for runs, events, and state snapshots."""

    def __init__(self, database_path: str | None = None) -> None:
        self.database_path = Path(database_path or settings.database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._write_lock = threading.Lock()
        self.initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=15)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    @contextmanager
    def _connection(self) -> Any:
        connection = self._connect()
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        with self._connection() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    input_json TEXT NOT NULL,
                    max_rounds INTEGER NOT NULL,
                    current_round INTEGER NOT NULL DEFAULT 0,
                    score INTEGER,
                    result_json TEXT,
                    error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS run_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    agent_id TEXT,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (run_id) REFERENCES runs(id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_run_events_run_id
                ON run_events(run_id, id);

                CREATE TABLE IF NOT EXISTS snapshots (
                    id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    round_number INTEGER NOT NULL,
                    label TEXT NOT NULL,
                    state_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (run_id) REFERENCES runs(id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_snapshots_run_id
                ON snapshots(run_id, round_number);

                CREATE TABLE IF NOT EXISTS agent_definitions (
                    agent_key TEXT PRIMARY KEY,
                    display_name TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS agent_versions (
                    id TEXT PRIMARY KEY,
                    agent_key TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    prompt TEXT NOT NULL,
                    capabilities_json TEXT NOT NULL,
                    tools_json TEXT NOT NULL,
                    priority INTEGER NOT NULL DEFAULT 50,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (agent_key) REFERENCES agent_definitions(agent_key),
                    UNIQUE (agent_key, version)
                );

                CREATE TABLE IF NOT EXISTS workflows (
                    workflow_key TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS workflow_versions (
                    id TEXT PRIMARY KEY,
                    workflow_key TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    definition_json TEXT NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (workflow_key) REFERENCES workflows(workflow_key),
                    UNIQUE (workflow_key, version)
                );
                """
            )
            self._ensure_run_columns(connection)

    @staticmethod
    def _ensure_run_columns(connection: sqlite3.Connection) -> None:
        columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(runs)").fetchall()
        }
        if "workflow_key" not in columns:
            connection.execute(
                "ALTER TABLE runs ADD COLUMN workflow_key TEXT NOT NULL DEFAULT 'extraction-default'"
            )
        if "workflow_version" not in columns:
            connection.execute(
                "ALTER TABLE runs ADD COLUMN workflow_version INTEGER NOT NULL DEFAULT 1"
            )
        if "agent_manifest_json" not in columns:
            connection.execute(
                "ALTER TABLE runs ADD COLUMN agent_manifest_json TEXT NOT NULL DEFAULT '{}'"
            )

    def create_run(
        self,
        input_data: dict[str, Any],
        max_rounds: int,
        *,
        workflow_key: str = "extraction-default",
        workflow_version: int = 1,
        agent_manifest: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        run_id = uuid.uuid4().hex
        now = utc_now()
        with self._write_lock, self._connection() as connection:
            connection.execute(
                """
                INSERT INTO runs (
                    id, status, input_json, max_rounds, current_round,
                    workflow_key, workflow_version, agent_manifest_json,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, 0, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    "queued",
                    json.dumps(input_data, ensure_ascii=False),
                    max_rounds,
                    workflow_key,
                    workflow_version,
                    json.dumps(agent_manifest or {}, ensure_ascii=False),
                    now,
                    now,
                ),
            )
        return self.get_run(run_id)

    def update_run(self, run_id: str, **fields: Any) -> dict[str, Any]:
        allowed = {"status", "current_round", "score", "result_json", "error"}
        unknown = set(fields) - allowed
        if unknown:
            raise ValueError(f"unsupported run fields: {sorted(unknown)}")
        if not fields:
            return self.get_run(run_id)

        assignments = ", ".join(f"{name} = ?" for name in fields)
        values = []
        for value in fields.values():
            values.append(
                json.dumps(value, ensure_ascii=False)
                if isinstance(value, (dict, list))
                else value
            )
        values.extend([utc_now(), run_id])
        with self._write_lock, self._connection() as connection:
            connection.execute(
                f"UPDATE runs SET {assignments}, updated_at = ? WHERE id = ?",
                values,
            )
        return self.get_run(run_id)

    def get_run(self, run_id: str) -> dict[str, Any]:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM runs WHERE id = ?",
                (run_id,),
            ).fetchone()
        if row is None:
            raise KeyError(run_id)
        return self._run_row(row)

    def list_runs(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT * FROM runs ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._run_row(row) for row in rows]

    def append_event(
        self,
        run_id: str,
        event_type: str,
        payload: dict[str, Any],
        agent_id: str | None = None,
    ) -> dict[str, Any]:
        now = utc_now()
        with self._write_lock, self._connection() as connection:
            cursor = connection.execute(
                """
                INSERT INTO run_events (
                    run_id, event_type, agent_id, payload_json, created_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    event_type,
                    agent_id,
                    json.dumps(payload, ensure_ascii=False),
                    now,
                ),
            )
            event_id = int(cursor.lastrowid)
        return {
            "id": event_id,
            "runId": run_id,
            "type": event_type,
            "agentId": agent_id,
            "payload": payload,
            "createdAt": now,
        }

    def get_events(self, run_id: str, after_id: int = 0) -> list[dict[str, Any]]:
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT * FROM run_events
                WHERE run_id = ? AND id > ?
                ORDER BY id ASC
                """,
                (run_id, after_id),
            ).fetchall()
        return [
            {
                "id": row["id"],
                "runId": row["run_id"],
                "type": row["event_type"],
                "agentId": row["agent_id"],
                "payload": json.loads(row["payload_json"]),
                "createdAt": row["created_at"],
            }
            for row in rows
        ]

    def create_snapshot(
        self,
        run_id: str,
        round_number: int,
        label: str,
        state: dict[str, Any],
    ) -> dict[str, Any]:
        snapshot_id = uuid.uuid4().hex
        now = utc_now()
        with self._write_lock, self._connection() as connection:
            connection.execute(
                """
                INSERT INTO snapshots (
                    id, run_id, round_number, label, state_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    snapshot_id,
                    run_id,
                    round_number,
                    label,
                    json.dumps(state, ensure_ascii=False),
                    now,
                ),
            )
        return {
            "id": snapshot_id,
            "runId": run_id,
            "round": round_number,
            "label": label,
            "state": state,
            "createdAt": now,
        }

    def list_snapshots(self, run_id: str) -> list[dict[str, Any]]:
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT * FROM snapshots
                WHERE run_id = ?
                ORDER BY round_number ASC, created_at ASC
                """,
                (run_id,),
            ).fetchall()
        return [
            {
                "id": row["id"],
                "runId": row["run_id"],
                "round": row["round_number"],
                "label": row["label"],
                "state": json.loads(row["state_json"]),
                "createdAt": row["created_at"],
            }
            for row in rows
        ]

    def get_snapshot(self, run_id: str, snapshot_id: str) -> dict[str, Any]:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM snapshots WHERE id = ? AND run_id = ?",
                (snapshot_id, run_id),
            ).fetchone()
        if row is None:
            raise KeyError(snapshot_id)
        return {
            "id": row["id"],
            "runId": row["run_id"],
            "round": row["round_number"],
            "label": row["label"],
            "state": json.loads(row["state_json"]),
            "createdAt": row["created_at"],
        }

    @staticmethod
    def _run_row(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "status": row["status"],
            "input": json.loads(row["input_json"]),
            "maxRounds": row["max_rounds"],
            "currentRound": row["current_round"],
            "workflow": {
                "key": row["workflow_key"],
                "version": row["workflow_version"],
            },
            "agents": json.loads(row["agent_manifest_json"] or "{}"),
            "score": row["score"],
            "result": json.loads(row["result_json"]) if row["result_json"] else None,
            "error": row["error"],
            "createdAt": row["created_at"],
            "updatedAt": row["updated_at"],
        }


run_repository = RunRepository()
