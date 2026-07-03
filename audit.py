"""Append-only audit log (SQLite, stdlib only).

Every stage of a run is written here as it happens, so the timeline is
reconstructable after the fact — the production-readiness "observability" story.
One file, zero infra: `rescueops_audit.db` in the repo root.

Contract (see README):
  init_db() -> None                                  # idempotent
  log_event(run_id, stage, payload: dict) -> None    # append one row
  get_run(run_id) -> list[dict]                       # ordered by insertion time
"""
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

_DB_PATH = Path(__file__).parent / "rescueops_audit.db"


def _connect() -> sqlite3.Connection:
    # A fresh connection per call keeps this safe across Streamlit's threads.
    conn = sqlite3.connect(_DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Create tables if they don't exist. Safe to call multiple times."""
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS events (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id    TEXT NOT NULL,
                stage     TEXT NOT NULL,
                payload   TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_events_run_id ON events(run_id)")


def log_event(run_id: str, stage: str, payload: dict) -> None:
    """Append one event row. `stage` is one of: triage, diagnosis, remediation,
    approval, verification, postmortem. `payload` is the artifact dict."""
    init_db()
    created_at = datetime.now(timezone.utc).isoformat()
    payload_json = json.dumps(payload, default=str)
    with _connect() as conn:
        conn.execute(
            "INSERT INTO events (run_id, stage, payload, created_at) VALUES (?, ?, ?, ?)",
            (run_id, stage, payload_json, created_at),
        )


def get_run(run_id: str) -> list[dict]:
    """Return all event rows for a run_id, ordered by insertion time."""
    init_db()
    with _connect() as conn:
        rows = conn.execute(
            "SELECT run_id, stage, payload, created_at FROM events "
            "WHERE run_id = ? ORDER BY id ASC",
            (run_id,),
        ).fetchall()
    return [
        {
            "run_id": r["run_id"],
            "stage": r["stage"],
            "payload": json.loads(r["payload"]),
            "created_at": r["created_at"],
        }
        for r in rows
    ]
