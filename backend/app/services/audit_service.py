import os
import sqlite3
import time
from threading import Lock
from typing import Any

from app.config import WORKSPACE_ROOT


_AUDIT_DB_PATH = os.path.join(WORKSPACE_ROOT, "backend_audit.sqlite3")
_LOCK = Lock()


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(_AUDIT_DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_audit_db() -> None:
    with _LOCK:
        conn = _connect()
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS audit_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp INTEGER NOT NULL,
                    username TEXT NOT NULL,
                    action TEXT NOT NULL,
                    question TEXT NOT NULL,
                    sql_text TEXT NOT NULL,
                    result_status TEXT NOT NULL,
                    row_count INTEGER NOT NULL,
                    details TEXT NOT NULL
                )
                """
            )
            conn.commit()
        finally:
            conn.close()


def write_audit_log(
    username: str,
    action: str,
    result_status: str,
    question: str = "",
    sql_text: str = "",
    row_count: int = 0,
    details: str = "",
) -> None:
    with _LOCK:
        conn = _connect()
        try:
            conn.execute(
                """
                INSERT INTO audit_logs (timestamp, username, action, question, sql_text, result_status, row_count, details)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    int(time.time()),
                    username.strip() or "unknown",
                    action.strip() or "unknown",
                    question.strip(),
                    sql_text.strip(),
                    result_status.strip() or "unknown",
                    int(row_count),
                    details.strip(),
                ),
            )
            conn.commit()
        finally:
            conn.close()


def read_audit_logs(limit: int = 300) -> list[dict[str, Any]]:
    safe_limit = min(max(int(limit), 1), 2000)
    with _LOCK:
        conn = _connect()
        try:
            rows = conn.execute(
                """
                SELECT id, timestamp, username, action, question, sql_text, result_status, row_count, details
                FROM audit_logs
                ORDER BY id DESC
                LIMIT ?
                """,
                (safe_limit,),
            ).fetchall()
            return [
                {
                    "id": int(r["id"]),
                    "timestamp": int(r["timestamp"]),
                    "username": str(r["username"]),
                    "action": str(r["action"]),
                    "question": str(r["question"]),
                    "sql_text": str(r["sql_text"]),
                    "result_status": str(r["result_status"]),
                    "row_count": int(r["row_count"]),
                    "details": str(r["details"]),
                }
                for r in rows
            ]
        finally:
            conn.close()
