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
3. Generate the access-secret hash and paste into `.env`. **Double every `$` in the
   hash to `$$`** — docker compose interpolates `$` in `env_file` values and would
   otherwise mangle the argon2 hash (boot still succeeds, but every login 401s):
   ```
   docker compose run --rm proxy mcp-oauth-proxy-hash 'choose-a-strong-secret'
   ```
   Then confirm the container receives the intact hash:
   `docker compose run --rm -T proxy sh -c 'printf %s "$MCP_PROXY_ACCESS_SECRET_HASH"'`
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

1. claude.ai → Settings → Connectors → **Add custom connector**.
2. **URL:** `https://mcp.example.tld/mcp` — the `/mcp` transport path is required;
   the bare origin returns 404 and will not connect.
3. **Leave "OAuth client ID" and "OAuth client secret" blank.** The proxy supports
   Dynamic Client Registration, so Claude registers itself automatically at
   `/register`; those fields are only for servers that need a hand-created client.
   Your access secret is **not** an OAuth credential — do not put it here.
4. Click **Add**. Claude redirects to the proxy's own login page ("Enter your access
   secret"). Type the secret once — this is the only place it goes.
5. The OAuth exchange completes and the tools appear. The same login works across
   web, desktop, and mobile.

### If the connector seems stuck

- **You land on an "Open Claude Desktop" page, nothing happens, and the button still
  says Connect:** that page is claude.ai's web→desktop handoff — a `claude://` deep
  link. If Desktop isn't installed (or the browser blocked the launch) it stalls,
  **but the OAuth exchange has usually already succeeded**. Close the page and check
  Settings → Connectors: the connector is likely already connected and the tools work
  in a fresh chat.
- To skip the handoff entirely, add the connector from inside the app you actually
  want to use it in (e.g. Claude Desktop → Settings → Connectors).
- Confirm server-side success in the container logs — a completed flow logs:
  `POST /login → 302`, `POST /token → 200`, `POST /mcp → 200`, then
  `Processing request of type ListToolsRequest`. If you see those, the connection is
  live regardless of what the browser tab shows.

## Multiple backends (optional)

To serve more than one MCP server behind this single connector:

1. Copy `servers.example.json` to `servers.json`, listing each server under
   `mcpServers` with its `command`/`args`/`env` (for Obsidian, the same
   `OBSIDIAN_*` values you'd otherwise put in `.env`).
2. Mount it and point the proxy at it — in `docker-compose.yml`:
   ```yaml
   volumes:
     - proxy-data:/data
     - ./servers.json:/data/servers.json:ro
   ```
   and in `.env`: `MCP_SERVERS_CONFIG=/data/servers.json`.
3. `docker compose up -d`. With more than one server, tools appear namespaced by
   server key (`obsidian_...`, `github_...`); a single-server file stays
   unprefixed. `MCP_SERVERS_CONFIG` overrides the single `MCP_BACKEND_*` vars.

## Troubleshooting

- **Every login 401s (but boot was fine):** the argon2 hash in `.env` had un-doubled
  `$`; compose mangled it. Re-check step 3 — double every `$` to `$$` and verify the
  delivered value equals the true hash.
- **401 loop:** clock skew or `MCP_PROXY_PUBLIC_URL` mismatch with the real host.
  It must equal the exact HTTPS URL Caddy serves, no trailing slash.
- **`421 Misdirected Request` on every proxied request:** the MCP streamable-HTTP
  transport allowlists Host headers (DNS-rebinding protection) to localhost by
  default. The app auto-trusts the `MCP_PROXY_PUBLIC_URL` host, so this only bites
  if that var is wrong/empty or you front it with a *different* hostname — add extras
  via `FASTMCP_HTTP_ALLOWED_HOSTS=["other.host"]`.
- **`403 Forbidden Origin` at the login page:** same guard, Origin side. It trusts a
  browser `Origin` only if it matches the request scheme the container sees — but a
  TLS-terminating proxy forwards plaintext http, so the `https://` Origin is rejected.
  The app auto-trusts the `MCP_PROXY_PUBLIC_URL` origin; if you front it with another
  origin add it via `FASTMCP_HTTP_ALLOWED_ORIGINS=["https://other.host"]`.
- **Caddy in a container can't reach `127.0.0.1:8000`:** that loopback is the *Caddy*
  container, not the host. Put the proxy and Caddy on a shared docker network and
  `reverse_proxy <proxy-container-name>:8000` instead of `127.0.0.1:8000`. After an
  atomic-rename edit to a single-file-bind-mounted Caddyfile, `restart` Caddy (a
  `reload` may read a stale inode).
- **Tools connect but never used by the model:** known claude.ai web quirk; retry
  from a fresh chat or the desktop app. Validate independently with MCP Inspector.
- **`vault unreachable` tool errors:** home VM/Obsidian down or Tailscale offline.
- **Re-login after redeploy:** ensure the `proxy-data` volume is mounted (SQLite
  persistence). Losing it drops registered clients + tokens.
- **Login lockout after failed attempts:** the `/login` page locks a client for
  ~5 min after 5 wrong secrets. The lockout keys on the client IP from
  `X-Forwarded-For`, so ensure Caddy forwards it (it does by default). Adjust with
  `MCP_PROXY_LOGIN_MAX_ATTEMPTS` / `MCP_PROXY_LOGIN_LOCKOUT_SECONDS`.
