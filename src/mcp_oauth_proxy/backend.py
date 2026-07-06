from __future__ import annotations

import os

from fastmcp.client.transports import StdioTransport

from .config import Settings

# Only these host env vars are forwarded to the backend child process.
_FORWARDED_HOST_ENV = ("PATH", "HOME", "SYSTEMROOT", "TEMP", "TMP")


def build_backend_transport(settings: Settings) -> StdioTransport:
    child_env: dict[str, str] = {
        key: os.environ[key] for key in _FORWARDED_HOST_ENV if key in os.environ
    }
    child_env.update(settings.backend_env)
    return StdioTransport(
        command=settings.backend_command,
        args=settings.backend_args,
        env=child_env,
        keep_alive=True,
    )
