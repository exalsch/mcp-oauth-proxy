# tests/test_provider_login_routes.py
import json
import time
from urllib.parse import urlparse, parse_qs

import httpx
import pytest
from starlette.applications import Starlette
from mcp.server.auth.provider import AuthorizationParams
from mcp.shared.auth import OAuthClientInformationFull
from pydantic import AnyUrl

from mcp_oauth_proxy.config import Settings
from mcp_oauth_proxy.storage import Storage
from mcp_oauth_proxy.secret_gate import SecretGate, hash_secret
from mcp_oauth_proxy.provider import SecretOAuthProvider


def make(tmp_path, secret="s3cret"):
    settings = Settings(public_url="https://mcp.example.tld", access_secret_hash=hash_secret(secret),
                        login_max_attempts=3, login_lockout_seconds=60)
    storage = Storage(str(tmp_path / "p.db"))
    gate = SecretGate(hash_secret(secret), 3, 60, now=lambda: 0.0)
    provider = SecretOAuthProvider(settings, storage, gate)
    app = Starlette(routes=[r for r in provider.get_routes("/mcp") if r.path == "/login"])
    transport = httpx.ASGITransport(app=app)
    client = httpx.AsyncClient(transport=transport, base_url="https://mcp.example.tld")
    return provider, storage, client


async def _seed_txn(provider, storage):
    client_info = OAuthClientInformationFull(
        client_id="c1", redirect_uris=[AnyUrl("https://claude.ai/cb")],
        token_endpoint_auth_method="none")
    # Register the client (mirrors real DCR flow) so provider.get_client("c1")
    # resolves later — without this, load_authorization_code would be handed
    # client=None and AttributeError before it ever reaches our assertions.
    await provider.register_client(client_info)
    params = AuthorizationParams(state="st8", scopes=[], code_challenge="chal",
                                 redirect_uri=AnyUrl("https://claude.ai/cb"),
                                 redirect_uri_provided_explicitly=True)
    url = await provider.authorize(client_info, params)
    return parse_qs(urlparse(url).query)["txn"][0]


async def test_login_get_renders_form(tmp_path):
    provider, storage, client = make(tmp_path)
    txn = await _seed_txn(provider, storage)
    resp = await client.get(f"/login?txn={txn}")
    assert resp.status_code == 200
    assert 'name="secret"' in resp.text
    assert txn in resp.text


async def test_login_post_wrong_secret_reprompts(tmp_path):
    provider, storage, client = make(tmp_path)
    txn = await _seed_txn(provider, storage)
    resp = await client.post("/login", data={"txn": txn, "secret": "wrong"})
    assert resp.status_code == 401
    assert 'name="secret"' in resp.text


async def test_login_post_correct_secret_redirects_with_code(tmp_path):
    provider, storage, client = make(tmp_path)
    txn = await _seed_txn(provider, storage)
    resp = await client.post("/login", data={"txn": txn, "secret": "s3cret"},
                             follow_redirects=False)
    assert resp.status_code in (302, 303, 307)
    loc = resp.headers["location"]
    q = parse_qs(urlparse(loc).query)
    assert loc.startswith("https://claude.ai/cb")
    assert q["state"][0] == "st8"
    code = q["code"][0]
    # the code was persisted and carries the challenge
    row = storage.pop_auth_code(code)
    assert row is not None and "chal" in row[1]


async def test_login_post_lockout_returns_429(tmp_path):
    provider, storage, client = make(tmp_path)
    txn = await _seed_txn(provider, storage)
    for _ in range(3):
        await client.post("/login", data={"txn": txn, "secret": "wrong"})
    resp = await client.post("/login", data={"txn": txn, "secret": "s3cret"})
    assert resp.status_code == 429


async def test_load_authorization_code_roundtrip(tmp_path):
    provider, storage, client = make(tmp_path)
    txn = await _seed_txn(provider, storage)
    resp = await client.post("/login", data={"txn": txn, "secret": "s3cret"},
                             follow_redirects=False)
    code = parse_qs(urlparse(resp.headers["location"]).query)["code"][0]
    client_info = await provider.get_client("c1")
    ac = await provider.load_authorization_code(client_info, code)
    assert ac is not None
    assert ac.code == code
    assert ac.code_challenge == "chal"
    # expiry is the real issuance expiry (not recomputed at read time), in the future and within ttl
    assert ac.expires_at is not None
    assert ac.expires_at <= time.time() + 300
    assert str(ac.redirect_uri) == "https://claude.ai/cb"
    # single use
    assert await provider.load_authorization_code(client_info, code) is None


async def test_login_post_missing_txn_returns_400(tmp_path):
    provider, storage, client = make(tmp_path)
    # never seeded / already-consumed txn id
    resp = await client.post("/login", data={"txn": "bogus-txn-id", "secret": "s3cret"})
    assert resp.status_code == 400
    assert "Session expired" in resp.text


async def test_load_authorization_code_wrong_client_returns_none(tmp_path):
    provider, storage, client = make(tmp_path)
    txn = await _seed_txn(provider, storage)
    resp = await client.post("/login", data={"txn": txn, "secret": "s3cret"},
                             follow_redirects=False)
    code = parse_qs(urlparse(resp.headers["location"]).query)["code"][0]
    other_client = OAuthClientInformationFull(
        client_id="other", redirect_uris=[AnyUrl("https://claude.ai/cb")],
        token_endpoint_auth_method="none")
    assert await provider.load_authorization_code(other_client, code) is None


async def test_lockout_is_per_forwarded_client(tmp_path):
    provider, storage, client = make(tmp_path)
    txn = await _seed_txn(provider, storage)
    # exhaust attempts for one forwarded client IP
    for _ in range(3):
        await client.post("/login", data={"txn": txn, "secret": "wrong"},
                          headers={"X-Forwarded-For": "1.2.3.4"})
    # that forwarded IP is now locked out
    locked = await client.post("/login", data={"txn": txn, "secret": "wrong"},
                               headers={"X-Forwarded-For": "1.2.3.4"})
    assert locked.status_code == 429
    # a DIFFERENT forwarded IP is NOT globally locked (independent bucket)
    other = await client.post("/login", data={"txn": txn, "secret": "wrong"},
                              headers={"X-Forwarded-For": "5.6.7.8"})
    assert other.status_code == 401


async def test_spoofed_left_xff_does_not_bypass_lockout(tmp_path):
    # With one trusted proxy (default), the real client is the RIGHT-most XFF
    # entry the proxy appended. An attacker rotating the spoofable left entry
    # must NOT get a fresh rate-limit bucket each request.
    provider, storage, client = make(tmp_path)
    txn = await _seed_txn(provider, storage)
    for i in range(3):
        await client.post("/login", data={"txn": txn, "secret": "wrong"},
                          headers={"X-Forwarded-For": f"9.9.9.{i}, 1.2.3.4"})
    locked = await client.post("/login", data={"txn": txn, "secret": "wrong"},
                               headers={"X-Forwarded-For": "9.9.9.250, 1.2.3.4"})
    assert locked.status_code == 429   # keyed on the real 1.2.3.4, still locked


async def test_login_get_shows_consent_destination(tmp_path):
    # The operator must be able to see who is being authorized and where the
    # code will be sent, to refuse an attacker-initiated (phished) transaction.
    provider, storage, client = make(tmp_path)
    txn = await _seed_txn(provider, storage)
    resp = await client.get(f"/login?txn={txn}")
    assert resp.status_code == 200
    assert "https://claude.ai/cb" in resp.text
    assert "redirected to" in resp.text.lower()


async def test_login_get_consent_peek_does_not_consume_txn(tmp_path):
    # Rendering the consent panel peeks the txn; it must remain usable for POST.
    provider, storage, client = make(tmp_path)
    txn = await _seed_txn(provider, storage)
    await client.get(f"/login?txn={txn}")
    resp = await client.post("/login", data={"txn": txn, "secret": "s3cret"},
                             follow_redirects=False)
    assert resp.status_code in (302, 303, 307)
