from __future__ import annotations

import time

from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationCode,
    AuthorizationParams,
    RefreshToken,
)
from mcp.server.auth.settings import ClientRegistrationOptions, RevocationOptions
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken
from fastmcp.server.auth.auth import OAuthProvider

from .config import Settings
from .secret_gate import SecretGate
from .storage import Storage


class SecretOAuthProvider(OAuthProvider):
    def __init__(self, settings: Settings, storage: Storage, gate: SecretGate) -> None:
        super().__init__(
            base_url=settings.public_url,
            resource_base_url=None,
            client_registration_options=ClientRegistrationOptions(enabled=True),
            revocation_options=RevocationOptions(enabled=True),
            required_scopes=None,
        )
        self._settings = settings
        self._storage = storage
        self._gate = gate

    # --- client registration (DCR) ---
    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        raw = self._storage.get_client(client_id)
        if raw is None:
            return None
        return OAuthClientInformationFull.model_validate_json(raw)

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        if client_info.client_id is None:
            raise ValueError("client_id is required for registration")
        self._storage.upsert_client(client_info.client_id, client_info.model_dump_json())

    # --- token verification ---
    async def verify_token(self, token: str) -> AccessToken | None:
        return await self.load_access_token(token)

    async def load_access_token(self, token: str) -> AccessToken | None:
        row = self._storage.get_access_token(token)
        if row is None:
            return None
        client_id, scopes, expires_at = row
        if expires_at < time.time():
            self._storage.delete_access_token(token)
            return None
        return AccessToken(
            token=token,
            client_id=client_id,
            scopes=scopes.split() if scopes else [],
            expires_at=int(expires_at),
        )

    # --- implemented in Tasks 6-8 ---
    async def authorize(self, client: OAuthClientInformationFull, params: AuthorizationParams) -> str:
        raise NotImplementedError  # Task 6

    async def load_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: str
    ) -> AuthorizationCode | None:
        raise NotImplementedError  # Task 7

    async def exchange_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: AuthorizationCode
    ) -> OAuthToken:
        raise NotImplementedError  # Task 8

    async def load_refresh_token(
        self, client: OAuthClientInformationFull, refresh_token: str
    ) -> RefreshToken | None:
        raise NotImplementedError  # Task 8

    async def exchange_refresh_token(
        self,
        client: OAuthClientInformationFull,
        refresh_token: RefreshToken,
        scopes: list[str],
    ) -> OAuthToken:
        raise NotImplementedError  # Task 8

    async def revoke_token(self, token: AccessToken | RefreshToken) -> None:
        raise NotImplementedError  # Task 8
