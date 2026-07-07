from __future__ import annotations

import hashlib
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

# Writes trigger an opportunistic sweep of expired rows at most this often, so
# abandoned transactions / auth codes / expired tokens cannot accumulate without
# bound (a cheap, unauthenticated disk-exhaustion vector otherwise).
_SWEEP_INTERVAL = 60.0


def _hash(value: str) -> str:
    """Hash a bearer-capability string for storage at rest.

    Access tokens, refresh tokens, auth codes, and transaction ids are
    high-entropy secrets whose *value* is the credential. We persist only their
    SHA-256 so that reading the database file (backup leak, volume exposure,
    host compromise) does not hand out directly usable credentials. Lookups hash
    the presented value and compare; the raw secret never touches disk.
    """
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class Storage:
    def __init__(self, db_path: str) -> None:
        if db_path != ":memory:":
            parent = os.path.dirname(db_path)
            if parent:
                os.makedirs(parent, exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self.init_schema()
        # Purge rows that expired while the process was down, then let writes
        # sweep periodically (see _maybe_sweep).
        self.delete_expired()
        self._last_sweep = time.monotonic()

    def init_schema(self) -> None:
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    # expiry housekeeping
    def delete_expired(self, now: float | None = None) -> None:
        now = time.time() if now is None else now
        c = self._conn
        c.execute("DELETE FROM txns WHERE expires_at < ?", (now,))
        c.execute("DELETE FROM auth_codes WHERE expires_at < ?", (now,))
        c.execute("DELETE FROM access_tokens WHERE expires_at < ?", (now,))
        c.execute(
            "DELETE FROM refresh_tokens WHERE expires_at IS NOT NULL AND expires_at < ?",
            (now,),
        )
        self._conn.commit()

    def _maybe_sweep(self) -> None:
        now = time.monotonic()
        if now - self._last_sweep < _SWEEP_INTERVAL:
            return
        self._last_sweep = now
        self.delete_expired()

    # clients — client_id is a public identifier (not a secret), stored as-is
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
            (_hash(txn_id), data, expires_at),
        )
        self._conn.commit()
        self._maybe_sweep()

    def get_txn(self, txn_id: str) -> str | None:
        """Read a pending transaction without consuming it (used to render the
        login/consent page). Returns None if missing or expired."""
        row = self._conn.execute(
            "SELECT data, expires_at FROM txns WHERE txn_id=?", (_hash(txn_id),)
        ).fetchone()
        if not row or row[1] < time.time():
            return None
        return row[0]

    def pop_txn(self, txn_id: str) -> str | None:
        row = self._conn.execute(
            "DELETE FROM txns WHERE txn_id=? RETURNING data, expires_at", (_hash(txn_id),)
        ).fetchone()
        self._conn.commit()
        if not row or row[1] < time.time():
            return None
        return row[0]

    # auth codes — delete on read
    def save_auth_code(self, code: str, client_id: str, data: str, expires_at: float) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO auth_codes(code, client_id, data, expires_at) VALUES(?, ?, ?, ?)",
            (_hash(code), client_id, data, expires_at),
        )
        self._conn.commit()
        self._maybe_sweep()

    def pop_auth_code(self, code: str) -> tuple[str, str] | None:
        row = self._conn.execute(
            "DELETE FROM auth_codes WHERE code=? RETURNING client_id, data, expires_at", (_hash(code),)
        ).fetchone()
        self._conn.commit()
        if not row or row[2] < time.time():
            return None
        return (row[0], row[1])

    # access tokens
    def save_access_token(self, token: str, client_id: str, scopes: str, expires_at: float) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO access_tokens(token, client_id, scopes, expires_at) VALUES(?, ?, ?, ?)",
            (_hash(token), client_id, scopes, expires_at),
        )
        self._conn.commit()
        self._maybe_sweep()

    def get_access_token(self, token: str) -> tuple[str, str, float] | None:
        row = self._conn.execute(
            "SELECT client_id, scopes, expires_at FROM access_tokens WHERE token=?", (_hash(token),)
        ).fetchone()
        return (row[0], row[1], row[2]) if row else None

    def delete_access_token(self, token: str) -> None:
        self._conn.execute("DELETE FROM access_tokens WHERE token=?", (_hash(token),))
        self._conn.commit()

    # refresh tokens
    def save_refresh_token(self, token: str, client_id: str, scopes: str, expires_at: float | None) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO refresh_tokens(token, client_id, scopes, expires_at) VALUES(?, ?, ?, ?)",
            (_hash(token), client_id, scopes, expires_at),
        )
        self._conn.commit()
        self._maybe_sweep()

    def get_refresh_token(self, token: str) -> tuple[str, str, float | None] | None:
        row = self._conn.execute(
            "SELECT client_id, scopes, expires_at FROM refresh_tokens WHERE token=?", (_hash(token),)
        ).fetchone()
        return (row[0], row[1], row[2]) if row else None

    def delete_refresh_token(self, token: str) -> None:
        self._conn.execute("DELETE FROM refresh_tokens WHERE token=?", (_hash(token),))
        self._conn.commit()

    # singletons (e.g. persistent salt)
    def get_or_create_singleton(self, key: str, factory: Callable[[], str]) -> str:
        row = self._conn.execute(
            "SELECT value FROM singletons WHERE key=?", (key,)
        ).fetchone()
        if row:
            return row[0]
        value = factory()
        self._conn.execute(
            "INSERT OR IGNORE INTO singletons(key, value) VALUES(?, ?)", (key, value)
        )
        self._conn.commit()
        winner = self._conn.execute(
            "SELECT value FROM singletons WHERE key=?", (key,)
        ).fetchone()
        return winner[0]
