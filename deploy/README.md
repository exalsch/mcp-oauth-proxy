# Deploying mcp-oauth-proxy

End state: `https://mcp.example.tld/mcp` is a claude.ai custom connector that reaches
your Obsidian vault. (The bare origin `https://mcp.example.tld` is the OAuth base —
`MCP_PROXY_PUBLIC_URL` and the `/.well-known/` metadata live there — but the connector
URL you paste into claude.ai must include the `/mcp` transport path.) Traffic path:

    claude.ai → Caddy (TLS) → proxy container (:8000) → uvx mcp-obsidian
              → Tailscale → home VM Obsidian Local REST API (:27124)

## 1. Home VM — headless Obsidian + REST API

1. Install Tailscale on the home VM; note its tailnet IP (e.g. `100.64.0.2`).
2. `docker compose -f home-vm-obsidian-compose.yml up -d`
3. Open `http://<home-vm>:3000`, finish Obsidian setup, open the synced vault.
4. Install the **Local REST API** community plugin. Copy its API key.
5. Confirm HTTPS API: `curl -k https://100.64.0.2:27124/ -H "Authorization: Bearer <KEY>"`.

## 2. VPS — proxy + Caddy + Tailscale

1. Install Tailscale on the VPS; `tailscale up`. Confirm it can reach the home VM:
   `curl -k https://100.64.0.2:27124/ -H "Authorization: Bearer <KEY>"`.
2. Clone this repo. `cp .env.example .env`.
3. Generate the access-secret hash and paste into `.env`:
   `docker compose run --rm proxy mcp-oauth-proxy-hash 'choose-a-strong-secret'`
4. Fill `.env`: `MCP_PROXY_PUBLIC_URL`, `MCP_BACKEND_ENV_OBSIDIAN_API_KEY`,
   `MCP_BACKEND_ENV_OBSIDIAN_HOST=100.64.0.2`.
5. `docker compose up -d --build`.
6. Add the Caddy site block from `Caddyfile.example` to your Caddyfile; reload Caddy.

## 3. Verify before connecting Claude

- `curl https://mcp.example.tld/.well-known/oauth-authorization-server` returns JSON
  with `authorization_endpoint`, `token_endpoint`, `registration_endpoint`.
- Run MCP Inspector against `https://mcp.example.tld/mcp`; complete the OAuth login
  (enter your access secret) and confirm the `obsidian_*` tools list.

## 4. Connect the custom connector in claude.ai

1. claude.ai → Settings → Connectors → Add custom connector.
2. URL: `https://mcp.example.tld/mcp` — the `/mcp` transport path is required; the
   bare origin returns 404 and will not connect.
3. Claude opens the login page — enter your access secret once.
4. Tools appear. Works on web, desktop, and mobile with the same login.

## Troubleshooting

- **401 loop:** clock skew or `MCP_PROXY_PUBLIC_URL` mismatch with the real host.
  It must equal the exact HTTPS URL Caddy serves, no trailing slash.
- **Tools connect but never used by the model:** known claude.ai web quirk; retry
  from a fresh chat or the desktop app. Validate independently with MCP Inspector.
- **`vault unreachable` tool errors:** home VM/Obsidian down or Tailscale offline.
- **Re-login after redeploy:** ensure the `proxy-data` volume is mounted (SQLite
  persistence). Losing it drops registered clients + tokens.
