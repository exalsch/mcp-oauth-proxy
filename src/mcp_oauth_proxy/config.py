from __future__ import annotations

import os
import shlex
from collections.abc import Mapping
from dataclasses import dataclass, field
from urllib.parse import urlsplit

_BACKEND_ENV_PREFIX = "MCP_BACKEND_ENV_"
_LOOPBACK_HOSTS = ("localhost", "127.0.0.1", "::1")


@dataclass(frozen=True)
class Settings:
    public_url: str
    access_secret_hash: str
    host: str = "0.0.0.0"
    port: int = 8000
    db_path: str = "data/proxy.db"
    backend_command: str = "uvx"
    backend_args: list[str] = field(default_factory=lambda: ["mcp-obsidian"])
    backend_env: dict[str, str] = field(default_factory=dict)
    servers_config_path: str | None = None
    access_token_ttl: int = 3600
    refresh_token_ttl: int = 2592000
    auth_code_ttl: int = 300
    login_max_attempts: int = 5
    login_lockout_seconds: int = 300
    # Number of trusted reverse proxies in front of the app. The real client IP
    # (used to key the login rate limiter) is taken this many entries from the
    # right of X-Forwarded-For — entries further left are client-supplied and
    # untrusted. Default 1 (a single Caddy/nginx hop). Set 0 if the app is
    # exposed directly with no proxy.
    trusted_proxies: int = 1


def _require(environ: Mapping[str, str], key: str) -> str:
    value = environ.get(key)
    if not value:
        raise ValueError(f"{key} environment variable is required")
    return value


def _validate_public_url(url: str) -> None:
    # OAuth 2.1 requires the authorization server and redirect endpoints to use
    # TLS; a plaintext public URL would expose codes/tokens in transit. Allow
    # http only for loopback (local development / MCP Inspector).
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    if parts.scheme != "https" and host not in _LOOPBACK_HOSTS:
        raise ValueError(
            "MCP_PROXY_PUBLIC_URL must use https (OAuth 2.1 requires TLS); "
            "http is allowed only for localhost/127.0.0.1"
        )


def load_settings(environ: Mapping[str, str] | None = None) -> Settings:
    environ = environ if environ is not None else os.environ

    public_url = _require(environ, "MCP_PROXY_PUBLIC_URL").rstrip("/")
    _validate_public_url(public_url)
    access_secret_hash = _require(environ, "MCP_PROXY_ACCESS_SECRET_HASH")

    raw_args = environ.get("MCP_BACKEND_ARGS")
    backend_args = shlex.split(raw_args) if raw_args else ["mcp-obsidian"]

    backend_env = {
        key[len(_BACKEND_ENV_PREFIX):]: val
        for key, val in environ.items()
        if key.startswith(_BACKEND_ENV_PREFIX)
    }

    return Settings(
        public_url=public_url,
        access_secret_hash=access_secret_hash,
        host=environ.get("MCP_PROXY_HOST", "0.0.0.0"),
        port=int(environ.get("MCP_PROXY_PORT", "8000")),
        db_path=environ.get("MCP_PROXY_DB_PATH", "data/proxy.db"),
        backend_command=environ.get("MCP_BACKEND_COMMAND", "uvx"),
        backend_args=backend_args,
        backend_env=backend_env,
        servers_config_path=environ.get("MCP_SERVERS_CONFIG"),
        access_token_ttl=int(environ.get("MCP_PROXY_ACCESS_TOKEN_TTL", "3600")),
        refresh_token_ttl=int(environ.get("MCP_PROXY_REFRESH_TOKEN_TTL", "2592000")),
        auth_code_ttl=int(environ.get("MCP_PROXY_AUTH_CODE_TTL", "300")),
        login_max_attempts=int(environ.get("MCP_PROXY_LOGIN_MAX_ATTEMPTS", "5")),
        login_lockout_seconds=int(environ.get("MCP_PROXY_LOGIN_LOCKOUT_SECONDS", "300")),
        trusted_proxies=int(environ.get("MCP_PROXY_TRUSTED_PROXIES", "1")),
    )
