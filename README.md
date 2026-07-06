# mcp-oauth-proxy

Wrap any local **stdio** MCP server with an **OAuth 2.1** front end so it can be added as a **claude.ai custom connector** (web, mobile, desktop).

claude.ai's custom connectors speak remote MCP over HTTPS and authenticate with OAuth 2.1 (Dynamic Client Registration + PKCE) — there is **no static bearer-token field**. This proxy supplies that OAuth layer and bridges to a stdio backend.

## Status

Usable. See [`deploy/README.md`](deploy/README.md) for the full deployment guide (Caddy, Tailscale, headless Obsidian). Design details: [`docs/superpowers/specs/2026-07-06-mcp-oauth-proxy-design.md`](docs/superpowers/specs/2026-07-06-mcp-oauth-proxy-design.md).

## First use case

Expose [`mcp-obsidian`](https://github.com/MarkusPfundstein/mcp-obsidian) — make an Obsidian vault available to Claude everywhere. Backend is configurable, so the proxy works for any stdio MCP server.

## Architecture (short)

```
claude.ai → Caddy (TLS) → mcp-oauth-proxy (OAuth 2.1 + FastMCP proxy) → stdio backend → (tailscale) → Obsidian REST API
```

## Wrapping other MCP servers

The proxy is **backend-agnostic**. To expose a different single stdio MCP server:

1. Set `MCP_BACKEND_COMMAND` and `MCP_BACKEND_ARGS` to invoke your server (defaults: `uvx` and `mcp-obsidian`).
2. Use `MCP_BACKEND_ENV_*` to forward environment variables to the backend (e.g., `MCP_BACKEND_ENV_API_KEY=secret` becomes `API_KEY=secret` in the child process).

Example: to wrap `mcp-github`:
```bash
MCP_BACKEND_COMMAND=uvx
MCP_BACKEND_ARGS=mcp-github
MCP_BACKEND_ENV_GITHUB_TOKEN=ghp_...
```

## Multiple MCP servers behind one connector

Set `MCP_SERVERS_CONFIG` to a mounted JSON file (the Claude-desktop `mcpServers`
shape) to expose several servers through the same connector and login. When set,
it overrides the single `MCP_BACKEND_*` vars. With more than one server, each
backend's tools are **namespaced by its config key** (e.g. `obsidian_...`,
`github_...`); a single-server file stays unprefixed. See
[`deploy/servers.example.json`](deploy/servers.example.json).

```json
{
  "mcpServers": {
    "obsidian": { "command": "uvx", "args": ["mcp-obsidian"], "env": { "OBSIDIAN_API_KEY": "..." } },
    "github":   { "command": "uvx", "args": ["mcp-github"],   "env": { "GITHUB_TOKEN": "..." } }
  }
}
```

Each stdio server's child process receives only a host env allowlist (`PATH`,
etc.) plus its own `env` block — the proxy's secret env is never forwarded.
