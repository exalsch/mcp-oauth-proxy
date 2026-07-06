from __future__ import annotations

import json
import os

from .config import Settings

# Only these host env vars are forwarded to each backend child process.
_FORWARDED_HOST_ENV = ("PATH", "HOME", "SYSTEMROOT", "TEMP", "TMP")


def _forwarded_host_env() -> dict[str, str]:
    return {key: os.environ[key] for key in _FORWARDED_HOST_ENV if key in os.environ}


def _load_servers_file(path: str) -> dict[str, dict]:
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path}: invalid JSON ({exc})") from exc
    # Accept either the standard `{"mcpServers": {...}}` wrapper or a bare
    # mapping of server name -> spec.
    servers = data.get("mcpServers", data) if isinstance(data, dict) else None
    if not isinstance(servers, dict) or not servers:
        raise ValueError(f"{path}: expected a non-empty 'mcpServers' object")
    for name, spec in servers.items():
        if not isinstance(spec, dict):
            raise ValueError(f"{path}: server '{name}' must be an object")
    return servers


def build_backend_config(settings: Settings) -> dict:
    """Build a FastMCP ``mcpServers`` config for one or more stdio backends.

    Source of the server list:
    - ``settings.servers_config_path`` (a mounted JSON file), if set — one or
      more named servers. FastMCP namespaces each backend's tools by its config
      key when more than one server is present.
    - otherwise the legacy single-backend ``MCP_BACKEND_*`` settings, mounted as
      one unprefixed server (unchanged behavior).

    For every command-based (stdio) server, the child env is the host allowlist
    plus that server's configured env — the proxy's own secret env is never
    forwarded to a child. Remote (url-based) entries pass through untouched.
    """
    if settings.servers_config_path:
        raw_servers = _load_servers_file(settings.servers_config_path)
    else:
        raw_servers = {
            "obsidian": {
                "command": settings.backend_command,
                "args": settings.backend_args,
                "env": settings.backend_env,
            }
        }

    servers: dict[str, dict] = {}
    for name, spec in raw_servers.items():
        entry = dict(spec)
        if "command" in entry:  # stdio server — we control its child env
            configured_env = entry.get("env", {})
            if not isinstance(configured_env, dict):
                raise ValueError(f"server '{name}': 'env' must be an object")
            child_env = _forwarded_host_env()
            child_env.update(configured_env)
            entry["env"] = child_env
            entry.setdefault("args", [])
            entry.setdefault("keep_alive", True)
        servers[name] = entry

    return {"mcpServers": servers}
