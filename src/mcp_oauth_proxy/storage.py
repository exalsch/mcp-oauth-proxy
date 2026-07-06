from __future__ import annotations

import os
import sqlite3
import time
from collections.abc import Callable

_SCHEMA = """
CREATE TABLE IF NOT EXISTS clients (client_id TEXT PRIMARY KEY, data TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS txns (txn_id TEXT PRIMARY KEY, data TEXT NOT NULL, expires_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS auth_codes (code TEXT PRIMARY KEY, client_id TEXT NOT NULL, data TEXT NOT NULL, expires_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS access_tokens (token TEXT PRIMARY KEY, client_id TEXT NOT NULL, scopes TEXT NOT NULL, expires_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS refresh_tokens (token TEXT PRIMARY KEY, client_id TEXT NOT NULL, scopes TEXT NOT NULL, expires_at REAL);
CREATE TABLE IF NOT EXISTS singletons (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""


class Storage:
    def __init__(self, db_path: str) -> None:
        if db_path != ":memory:":
            parent = os.path.dirname(db_path)
            if parent:
                os.makedirs(parent, exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self.init_schema()

    def init_schema(self) -> None:
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    # clients
    def upsert_client(self, client_id: str, data: str) -> None:
        self._conn.execute(
            "INSERT INTO clients(client_id, data) VALUES(?, ?) "
            "ON CONFLICT(client_id) DO UPDATE SET data=excluded.data",
            (client_id, data),
        )
        self._conn.commit()

    def get_client(self, client_id: str) -> str | None:
        row = self._conn.execute(
            "SELECT data FROM clients WHERE client_id=?", (client_id,)
        ).fetchone()
        return row[0] if row else None

    # txns (pending authorize params) — delete on read
    def save_txn(self, txn_id: str, data: str, expires_at: float) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO txns(txn_id, data, expires_at) VALUES(?, ?, ?)",
            (txn_id, data, expires_at),
        )
        self._conn.commit()

    def pop_txn(self, txn_id: str) -> str | None:
        row = self._conn.execute(
            "SELECT data, expires_at FROM txns WHERE txn_id=?", (txn_id,)
        ).fetchone()
        self._conn.execute("DELETE FROM txns WHERE txn_id=?", (txn_id,))
        self._conn.commit()
        if not row or row[1] < time.time():
            return None
        return row[0]

    # auth codes — delete on read
    def save_auth_code(self, code: str, client_id: str, data: str, expires_at: float) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO auth_codes(code, client_id, data, expires_at) VALUES(?, ?, ?, ?)",
            (code, client_id, data, expires_at),
        )
        self._conn.commit()

    def pop_auth_code(self, code: str) -> tuple[str, str] | None:
        row = self._conn.execute(
            "SELECT client_id, data, expires_at FROM auth_codes WHERE code=?", (code,)
        ).fetchone()
        self._conn.execute("DELETE FROM auth_codes WHERE code=?", (code,))
        self._conn.commit()
        if not row or row[2] < time.time():
            return None
        return (row[0], row[1])

    # access tokens
    def save_access_token(self, token: str, client_id: str, scopes: str, expires_at: float) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO access_tokens(token, client_id, scopes, expires_at) VALUES(?, ?, ?, ?)",
            (token, client_id, scopes, expires_at),
        )
        self._conn.commit()

    def get_access_token(self, token: str) -> tuple[str, str, float] | None:
        row = self._conn.execute(
            "SELECT client_id, scopes, expires_at FROM access_tokens WHERE token=?", (token,)
        ).fetchone()
        return (row[0], row[1], row[2]) if row else None

    def delete_access_token(self, token: str) -> None:
        self._conn.execute("DELETE FROM access_tokens WHERE token=?", (token,))
        self._conn.commit()

    # refresh tokens
    def save_refresh_token(self, token: str, client_id: str, scopes: str, expires_at: float | None) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO refresh_tokens(token, client_id, scopes, expires_at) VALUES(?, ?, ?, ?)",
            (token, client_id, scopes, expires_at),
        )
        self._conn.commit()

    def get_refresh_token(self, token: str) -> tuple[str, str, float | None] | None:
        row = self._conn.execute(
            "SELECT client_id, scopes, expires_at FROM refresh_tokens WHERE token=?", (token,)
        ).fetchone()
        return (row[0], row[1], row[2]) if row else None

    def delete_refresh_token(self, token: str) -> None:
        self._conn.execute("DELETE FROM refresh_tokens WHERE token=?", (token,))
        self._conn.commit()

    # singletons (e.g. persistent salt)
    def get_or_create_singleton(self, key: str, factory: Callable[[], str]) -> str:
        row = self._conn.execute(
            "SELECT value FROM singletons WHERE key=?", (key,)
        ).fetchone()
        if row:
            return row[0]
        value = factory()
        self._conn.execute("INSERT INTO singletons(key, value) VALUES(?, ?)", (key, value))
        self._conn.commit()
        return value
