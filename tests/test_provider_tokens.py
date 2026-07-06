# tests/test_provider_tokens.py
import time

from mcp.server.auth.provider import AuthorizationCode, RefreshToken
from mcp.shared.auth import OAuthClientInformationFull
from pydantic import AnyUrl

from mcp_oauth_proxy.config import Settings
from mcp_oauth_proxy.storage import Storage
from mcp_oauth_proxy.secret_gate import SecretGate, hash_secret
from mcp_oauth_proxy.provider import SecretOAuthProvider


def make(tmp_path):
    settings = Settings(public_url="https://mcp.example.tld", access_secret_hash=hash_secret("s"),
                        access_token_ttl=3600, refresh_token_ttl=1000)
    storage = Storage(str(tmp_path / "p.db"))
    gate = SecretGate(hash_secret("s"), 5, 60, now=lambda: 0.0)
    return SecretOAuthProvider(settings, storage, gate), storage


def _client():
    return OAuthClientInformationFull(
        client_id="c1", redirect_uris=[AnyUrl("https://claude.ai/cb")],
        token_endpoint_auth_method="none")


def _authcode(scopes=None):
    return AuthorizationCode(
        code="code1", client_id="c1", redirect_uri=AnyUrl("https://claude.ai/cb"),
        redirect_uri_provided_explicitly=True, scopes=scopes or [],
        expires_at=time.time() + 300, code_challenge="chal")


async def test_exchange_authorization_code_issues_tokens(tmp_path):
    provider, storage = make(tmp_path)
    token = await provider.exchange_authorization_code(_client(), _authcode(["read"]))
    assert token.token_type == "Bearer"
    assert token.expires_in == 3600
    assert token.refresh_token is not None
    # access token verifies
    verified = await provider.verify_token(token.access_token)
    assert verified is not None and verified.client_id == "c1"


async def test_refresh_rotates_tokens(tmp_path):
    provider, storage = make(tmp_path)
    first = await provider.exchange_authorization_code(_client(), _authcode(["read"]))
    rt_obj = await provider.load_refresh_token(_client(), first.refresh_token)
    assert isinstance(rt_obj, RefreshToken)
    second = await provider.exchange_refresh_token(_client(), rt_obj, [])
    assert second.access_token != first.access_token
    assert second.refresh_token != first.refresh_token
    # old refresh token no longer valid (rotated)
    assert await provider.load_refresh_token(_client(), first.refresh_token) is None


async def test_revoke_access_token(tmp_path):
    provider, storage = make(tmp_path)
    token = await provider.exchange_authorization_code(_client(), _authcode())
    at = await provider.verify_token(token.access_token)
    await provider.revoke_token(at)
    assert await provider.verify_token(token.access_token) is None
