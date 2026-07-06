from __future__ import annotations

import logging

from fastmcp.server import create_proxy
from fastmcp.server.providers.proxy import FastMCPProxy

from .backend import build_backend_config
from .config import Settings, load_settings
from .provider import SecretOAuthProvider
from .secret_gate import SecretGate
from .storage import Storage

logger = logging.getLogger("mcp-oauth-proxy")


def build_app(settings: Settings) -> FastMCPProxy:
    storage = Storage(settings.db_path)
    gate = SecretGate(
        secret_hash=settings.access_secret_hash,
        max_attempts=settings.login_max_attempts,
        lockout_seconds=settings.login_lockout_seconds,
    )
    provider = SecretOAuthProvider(settings, storage, gate)
    backend = build_backend_config(settings)
    proxy = create_proxy(
        backend,
        name="mcp-oauth-proxy",
        auth=provider,
    )
    return proxy


def run() -> None:
    logging.basicConfig(level=logging.INFO)
    settings = load_settings()
    app = build_app(settings)
    logger.info("starting mcp-oauth-proxy on %s:%s", settings.host, settings.port)
    app.run(transport="http", host=settings.host, port=settings.port)
