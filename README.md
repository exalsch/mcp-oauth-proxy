# mcp-oauth-proxy

Wrap any local **stdio** MCP server with an **OAuth 2.1** front end so it can be added as a **claude.ai custom connector** (web, mobile, desktop).

claude.ai's custom connectors speak remote MCP over HTTPS and authenticate with OAuth 2.1 (Dynamic Client Registration + PKCE) — there is **no static bearer-token field**. This proxy supplies that OAuth layer and bridges to a stdio backend.

## Status

🚧 Scaffolding. See [`docs/superpowers/specs/2026-07-06-mcp-oauth-proxy-design.md`](docs/superpowers/specs/2026-07-06-mcp-oauth-proxy-design.md) for the design.

## First use case

Expose [`mcp-obsidian`](https://github.com/MarkusPfundstein/mcp-obsidian) — make an Obsidian vault available to Claude everywhere. Backend is configurable, so the proxy works for any stdio MCP server.

## Architecture (short)

```
claude.ai → Caddy (TLS) → mcp-oauth-proxy (OAuth 2.1 + FastMCP proxy) → stdio backend → (tailscale) → Obsidian REST API
```
