import base64
import hashlib
import sys
from urllib.parse import urlparse, parse_qs

import httpx
import pytest

from mcp_oauth_proxy.config import Settings
from mcp_oauth_proxy.secret_gate import hash_secret
from mcp_oauth_proxy.app import build_app


def _pkce():
    verifier = base64.urlsafe_b64encode(b"a" * 40).rstrip(b"=").decode()
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()
    ).rstrip(b"=").decode()
    return verifier, challenge


@pytest.fixture
def app_client(tmp_path):
    settings = Settings(
        public_url="http://localhost",
        access_secret_hash=hash_secret("s3cret"),
        db_path=str(tmp_path / "app.db"),
        backend_command=sys.executable,
        backend_args=["tests/dummy_server.py"],
        backend_env={},
    )
    app = build_app(settings)
    asgi = app.http_app()
    transport = httpx.ASGITransport(app=asgi)
    client = httpx.AsyncClient(transport=transport, base_url="http://localhost")
    return client, asgi


async def test_metadata_advertises_oauth(app_client):
    client, asgi = app_client
    async with client:
        async with asgi.router.lifespan_context(asgi):
            resp = await client.get("/.well-known/oauth-authorization-server")
            assert resp.status_code == 200
            meta = resp.json()
            assert "authorization_endpoint" in meta
            assert "token_endpoint" in meta
            assert "registration_endpoint" in meta


async def test_full_oauth_then_tools_list(app_client):
    client, asgi = app_client
    verifier, challenge = _pkce()
    async with client:
        async with asgi.router.lifespan_context(asgi):
            # 1. Dynamic client registration
            reg = await client.post("/register", json={
                "redirect_uris": ["http://localhost:9999/cb"],
                "token_endpoint_auth_method": "none",
                "grant_types": ["authorization_code", "refresh_token"],
                "response_types": ["code"],
            })
            assert reg.status_code in (200, 201), reg.text
            client_id = reg.json()["client_id"]

            # 2. Authorize -> redirect to /login
            auth = await client.get("/authorize", params={
                "response_type": "code", "client_id": client_id,
                "redirect_uri": "http://localhost:9999/cb",
                "code_challenge": challenge, "code_challenge_method": "S256",
                "state": "st8",
            }, follow_redirects=False)
            assert auth.status_code in (302, 303, 307)
            txn = parse_qs(urlparse(auth.headers["location"]).query)["txn"][0]

            # 3. Submit secret at /login -> redirect back with code
            login = await client.post("/login",
                data={"txn": txn, "secret": "s3cret"}, follow_redirects=False)
            assert login.status_code == 302, login.text
            code = parse_qs(urlparse(login.headers["location"]).query)["code"][0]

            # 4. Exchange code for token (PKCE)
            tok = await client.post("/token", data={
                "grant_type": "authorization_code", "code": code,
                "redirect_uri": "http://localhost:9999/cb",
                "client_id": client_id, "code_verifier": verifier,
            })
            assert tok.status_code == 200, tok.text
            access_token = tok.json()["access_token"]

            # 5. Call the MCP endpoint tools/list with the bearer token
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
            }
            init = await client.post("/mcp", headers=headers, json={
                "jsonrpc": "2.0", "id": 1, "method": "initialize",
                "params": {"protocolVersion": "2025-06-18",
                           "capabilities": {}, "clientInfo": {"name": "t", "version": "1"}},
            })
            assert init.status_code == 200, init.text
            # session id returned in header for streamable-http
            session_id = init.headers.get("mcp-session-id")
            if session_id:
                headers["mcp-session-id"] = session_id
            await client.post("/mcp", headers=headers, json={
                "jsonrpc": "2.0", "method": "notifications/initialized"})
            listed = await client.post("/mcp", headers=headers, json={
                "jsonrpc": "2.0", "id": 2, "method": "tools/list"})
            assert listed.status_code == 200, listed.text
            body = listed.text
            assert "echo" in body


async def test_mcp_without_token_is_401(app_client):
    client, asgi = app_client
    async with client:
        async with asgi.router.lifespan_context(asgi):
            resp = await client.post("/mcp", json={
                "jsonrpc": "2.0", "id": 1, "method": "tools/list"},
                headers={"Accept": "application/json, text/event-stream",
                         "Content-Type": "application/json"})
            assert resp.status_code == 401
