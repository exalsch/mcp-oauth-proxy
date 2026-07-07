from __future__ import annotations

import logging
from urllib.parse import urlsplit

import fastmcp
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


def _public_host(public_url: str) -> str | None:
    return urlsplit(public_url).hostname or None


def _public_origin(public_url: str) -> str | None:
    parts = urlsplit(public_url)
    if not parts.scheme or not parts.netloc:
        return None
    return f"{parts.scheme}://{parts.netloc}"


def run() -> None:
    logging.basicConfig(level=logging.INFO)
    settings = load_settings()
    app = build_app(settings)
    # The MCP streamable-HTTP transport guards Host and Origin headers
    # (DNS-rebinding protection), trusting only localhost by default. Behind a
    # TLS-terminating reverse proxy neither matches: the Host is the public
    # domain (else 421 Misdirected Request), and the browser Origin is the
    # public https:// URL while the container only sees the plaintext http://
    # request scheme (else 403 Forbidden Origin). Trust both explicitly from
    # the configured public URL.
    public_host = _public_host(settings.public_url)
    if public_host:
        fastmcp.settings.http_allowed_hosts = [public_host, f"{public_host}:*"]
    public_origin = _public_origin(settings.public_url)
    if public_origin:
        fastmcp.settings.http_allowed_origins = [public_origin]
    logger.info("starting mcp-oauth-proxy on %s:%s", settings.host, settings.port)
    app.run(transport="http", host=settings.host, port=settings.port)
