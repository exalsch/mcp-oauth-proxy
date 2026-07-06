import pytest
from mcp.shared.auth import OAuthClientInformationFull
from mcp.server.auth.provider import AccessToken
from pydantic import AnyUrl

from mcp_oauth_proxy.config import Settings
from mcp_oauth_proxy.storage import Storage
from mcp_oauth_proxy.secret_gate import SecretGate, hash_secret
from mcp_oauth_proxy.provider import SecretOAuthProvider


def make_provider(tmp_path):
    settings = Settings(public_url="https://mcp.example.tld", access_secret_hash=hash_secret("s3cret"))
    storage = Storage(str(tmp_path / "p.db"))
    gate = SecretGate(hash_secret("s3cret"), max_attempts=5, lockout_seconds=60, now=lambda: 0.0)
    return SecretOAuthProvider(settings, storage, gate), storage


def _client(client_id="c1"):
    return OAuthClientInformationFull(
        client_id=client_id,
        redirect_uris=[AnyUrl("https://claude.ai/api/mcp/auth_callback")],
        token_endpoint_auth_method="none",
    )


async def test_register_and_get_client(tmp_path):
    provider, _ = make_provider(tmp_path)
    assert await provider.get_client("c1") is None
    await provider.register_client(_client("c1"))
    got = await provider.get_client("c1")
    assert got is not None
    assert got.client_id == "c1"
    assert str(got.redirect_uris[0]) == "https://claude.ai/api/mcp/auth_callback"


async def test_verify_token_unknown_returns_none(tmp_path):
    provider, _ = make_provider(tmp_path)
    assert await provider.verify_token("nope") is None


async def test_load_access_token_returns_and_expires(tmp_path):
    import time
    provider, storage = make_provider(tmp_path)
    storage.save_access_token("at1", "c1", "read", time.time() + 100)
    got = await provider.load_access_token("at1")
    assert isinstance(got, AccessToken)
    assert got.client_id == "c1" and got.scopes == ["read"]
    # expired token is rejected and cleaned up
    storage.save_access_token("at2", "c1", "", time.time() - 1)
    assert await provider.load_access_token("at2") is None
    assert storage.get_access_token("at2") is None
