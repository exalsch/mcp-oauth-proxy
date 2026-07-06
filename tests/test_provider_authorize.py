# tests/test_provider_authorize.py
from urllib.parse import urlparse, parse_qs

from mcp.server.auth.provider import AuthorizationParams
from mcp.shared.auth import OAuthClientInformationFull
from pydantic import AnyUrl

from mcp_oauth_proxy.config import Settings
from mcp_oauth_proxy.storage import Storage
from mcp_oauth_proxy.secret_gate import SecretGate, hash_secret
from mcp_oauth_proxy.provider import SecretOAuthProvider


def make_provider(tmp_path):
    settings = Settings(public_url="https://mcp.example.tld", access_secret_hash=hash_secret("s"))
    storage = Storage(str(tmp_path / "p.db"))
    gate = SecretGate(hash_secret("s"), 5, 60, now=lambda: 0.0)
    return SecretOAuthProvider(settings, storage, gate), storage


def _client():
    return OAuthClientInformationFull(
        client_id="c1",
        redirect_uris=[AnyUrl("https://claude.ai/cb")],
        token_endpoint_auth_method="none",
    )


def _params():
    return AuthorizationParams(
        state="xyz",
        scopes=[],
        code_challenge="abc123challenge",
        redirect_uri=AnyUrl("https://claude.ai/cb"),
        redirect_uri_provided_explicitly=True,
    )


async def test_authorize_redirects_to_login_with_txn(tmp_path):
    provider, storage = make_provider(tmp_path)
    url = await provider.authorize(_client(), _params())
    parsed = urlparse(url)
    assert parsed.path == "/login"
    assert parsed.netloc == "mcp.example.tld"
    txn = parse_qs(parsed.query)["txn"][0]
    # txn was persisted and carries the challenge + redirect
    payload = storage.pop_txn(txn)
    assert payload is not None
    assert "abc123challenge" in payload
    assert "https://claude.ai/cb" in payload
