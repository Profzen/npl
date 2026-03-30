import hashlib
import os
import secrets
import sqlite3
import time
from threading import Lock
from typing import Any

from app.config import WORKSPACE_ROOT


_AUTH_DB_PATH = os.path.join(WORKSPACE_ROOT, "backend_auth.sqlite3")
_LOCK = Lock()
_SESSION_TTL_SECONDS = 12 * 60 * 60

_DEFAULT_ADMIN_USERNAME = "admin"
_DEFAULT_ADMIN_PASSWORD = "Admin@123"


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(_AUTH_DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def _hash_password(password: str, salt: str) -> str:
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        bytes.fromhex(salt),
        120_000,
    )
    return digest.hex()


def _build_password_hash(password: str) -> tuple[str, str]:
    salt = secrets.token_bytes(16).hex()
    return _hash_password(password, salt), salt


def _is_valid_username(username: str) -> bool:
    return 3 <= len(username) <= 64 and username.replace("_", "").replace("-", "").isalnum()


def _cleanup_expired_sessions(conn: sqlite3.Connection) -> None:
    conn.execute("DELETE FROM sessions WHERE expires_at <= ?", (int(time.time()),))


def init_auth_db() -> None:
    with _LOCK:
        conn = _connect()
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    password_salt TEXT NOT NULL,
                    is_admin INTEGER NOT NULL DEFAULT 0,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    token TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    expires_at INTEGER NOT NULL,
                    created_at INTEGER NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(id)
                )
                """
            )

            now = int(time.time())
            admin = conn.execute(
                "SELECT id FROM users WHERE username = ?", (_DEFAULT_ADMIN_USERNAME,)
            ).fetchone()
            if admin is None:
                password_hash, salt = _build_password_hash(_DEFAULT_ADMIN_PASSWORD)
                conn.execute(
                    """
                    INSERT INTO users (username, password_hash, password_salt, is_admin, is_active, created_at, updated_at)
                    VALUES (?, ?, ?, 1, 1, ?, ?)
                    """,
                    (_DEFAULT_ADMIN_USERNAME, password_hash, salt, now, now),
                )
            conn.commit()
        finally:
            conn.close()


def ensure_default_admin_access(login_username: str, login_password: str) -> None:
    init_auth_db()

    if login_username.strip() != _DEFAULT_ADMIN_USERNAME or login_password != _DEFAULT_ADMIN_PASSWORD:
        return

    password_hash, salt = _build_password_hash(_DEFAULT_ADMIN_PASSWORD)
    now = int(time.time())

    with _LOCK:
        conn = _connect()
        try:
            conn.execute(
                """
                UPDATE users
                SET password_hash = ?, password_salt = ?, is_admin = 1, is_active = 1, updated_at = ?
                WHERE username = ?
                """,
                (password_hash, salt, now, _DEFAULT_ADMIN_USERNAME),
            )
            conn.commit()
        finally:
            conn.close()


def authenticate_user(username: str, password: str) -> dict[str, Any] | None:
    name = username.strip()
    with _LOCK:
        conn = _connect()
        try:
            row = conn.execute(
                "SELECT id, username, password_hash, password_salt, is_admin, is_active FROM users WHERE username = ?",
                (name,),
            ).fetchone()
            if row is None:
                return None
            expected = _hash_password(password, row["password_salt"])
            if expected != row["password_hash"]:
                return None
            if int(row["is_active"]) != 1:
                return None
            return {
                "id": int(row["id"]),
                "username": str(row["username"]),
                "is_admin": bool(row["is_admin"]),
                "is_active": bool(row["is_active"]),
            }
        finally:
            conn.close()


def create_session(user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    now = int(time.time())
    expires_at = now + _SESSION_TTL_SECONDS
    with _LOCK:
        conn = _connect()
        try:
            _cleanup_expired_sessions(conn)
            conn.execute(
                "INSERT INTO sessions (token, user_id, expires_at, created_at) VALUES (?, ?, ?, ?)",
                (token, user_id, expires_at, now),
            )
            conn.commit()
        finally:
            conn.close()
    return token


def revoke_session(token: str) -> None:
    with _LOCK:
        conn = _connect()
        try:
            conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
            conn.commit()
        finally:
            conn.close()


def get_user_by_token(token: str) -> dict[str, Any] | None:
    if not token:
        return None
    now = int(time.time())
    with _LOCK:
        conn = _connect()
        try:
            _cleanup_expired_sessions(conn)
            row = conn.execute(
                """
                SELECT u.id, u.username, u.is_admin, u.is_active
                FROM sessions s
                JOIN users u ON u.id = s.user_id
                WHERE s.token = ? AND s.expires_at > ?
                """,
                (token, now),
            ).fetchone()
            conn.commit()
            if row is None:
                return None
            if int(row["is_active"]) != 1:
                return None
            return {
                "id": int(row["id"]),
                "username": str(row["username"]),
                "is_admin": bool(row["is_admin"]),
                "is_active": bool(row["is_active"]),
            }
        finally:
            conn.close()


def list_users() -> list[dict[str, Any]]:
    with _LOCK:
        conn = _connect()
        try:
            rows = conn.execute(
                """
                SELECT id, username, is_admin, is_active, created_at
                FROM users
                ORDER BY is_admin DESC, username ASC
                """
            ).fetchall()
            return [
                {
                    "id": int(r["id"]),
                    "username": str(r["username"]),
                    "is_admin": bool(r["is_admin"]),
                    "is_active": bool(r["is_active"]),
                    "created_at": int(r["created_at"]),
                }
                for r in rows
            ]
        finally:
            conn.close()


def create_user(username: str, password: str, is_admin: bool) -> dict[str, Any]:
    clean_username = username.strip()
    clean_password = password.strip()

    if not _is_valid_username(clean_username):
        raise ValueError("Nom utilisateur invalide (3-64 caracteres alphanumeriques, '_' ou '-')")
    if len(clean_password) < 6:
        raise ValueError("Mot de passe trop court (minimum 6 caracteres)")

    password_hash, salt = _build_password_hash(clean_password)
    now = int(time.time())

    with _LOCK:
        conn = _connect()
        try:
            existing = conn.execute("SELECT id FROM users WHERE username = ?", (clean_username,)).fetchone()
            if existing is not None:
                raise ValueError("Ce nom utilisateur existe deja")

            conn.execute(
                """
                INSERT INTO users (username, password_hash, password_salt, is_admin, is_active, created_at, updated_at)
                VALUES (?, ?, ?, ?, 1, ?, ?)
                """,
                (clean_username, password_hash, salt, 1 if is_admin else 0, now, now),
            )
            conn.commit()

            created = conn.execute(
                "SELECT id, username, is_admin, is_active, created_at FROM users WHERE username = ?",
                (clean_username,),
            ).fetchone()
            return {
                "id": int(created["id"]),
                "username": str(created["username"]),
                "is_admin": bool(created["is_admin"]),
                "is_active": bool(created["is_active"]),
                "created_at": int(created["created_at"]),
            }
        finally:
            conn.close()


def set_user_active(user_id: int, is_active: bool) -> dict[str, Any] | None:
    now = int(time.time())
    with _LOCK:
        conn = _connect()
        try:
            row = conn.execute("SELECT id, username FROM users WHERE id = ?", (user_id,)).fetchone()
            if row is None:
                return None

            conn.execute(
                "UPDATE users SET is_active = ?, updated_at = ? WHERE id = ?",
                (1 if is_active else 0, now, user_id),
            )
            if not is_active:
                conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
            conn.commit()

            updated = conn.execute(
                "SELECT id, username, is_admin, is_active, created_at FROM users WHERE id = ?",
                (user_id,),
            ).fetchone()
            return {
                "id": int(updated["id"]),
                "username": str(updated["username"]),
                "is_admin": bool(updated["is_admin"]),
                "is_active": bool(updated["is_active"]),
                "created_at": int(updated["created_at"]),
            }
        finally:
            conn.close()


def delete_user(user_id: int) -> bool:
    with _LOCK:
        conn = _connect()
        try:
            row = conn.execute("SELECT id FROM users WHERE id = ?", (user_id,)).fetchone()
            if row is None:
                return False
            conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
            conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
            conn.commit()
            return True
        finally:
            conn.close()


def default_admin_credentials() -> tuple[str, str]:
    return _DEFAULT_ADMIN_USERNAME, _DEFAULT_ADMIN_PASSWORD
