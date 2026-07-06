from __future__ import annotations

import json
import secrets
import time

from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationCode,
    AuthorizationParams,
    RefreshToken,
    construct_redirect_uri,
)
from mcp.server.auth.settings import ClientRegistrationOptions, RevocationOptions
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken
from fastmcp.server.auth.auth import OAuthProvider
from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse, Response
from starlette.routing import Route

from .config import Settings
from .login_ui import render_login_page
from .secret_gate import LockedOut, SecretGate
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
    def _login_url(self, txn_id: str) -> str:
        return f"{self._settings.public_url}/login?txn={txn_id}"

    def _txn_payload(self, client: OAuthClientInformationFull, params: AuthorizationParams) -> dict:
        return {
            "client_id": client.client_id,
            "redirect_uri": str(params.redirect_uri),
            "redirect_uri_provided_explicitly": params.redirect_uri_provided_explicitly,
            "scopes": params.scopes or [],
            "state": params.state,
            "code_challenge": params.code_challenge,
        }

    async def authorize(self, client: OAuthClientInformationFull, params: AuthorizationParams) -> str:
        txn_id = secrets.token_urlsafe(32)
        payload = json.dumps(self._txn_payload(client, params))
        self._storage.save_txn(txn_id, payload, time.time() + self._settings.auth_code_ttl)
        return self._login_url(txn_id)

    def get_routes(self, mcp_path: str | None = None) -> list[Route]:
        routes = super().get_routes(mcp_path)
        routes.append(Route("/login", self._login_get, methods=["GET"]))
        routes.append(Route("/login", self._login_post, methods=["POST"]))
        return routes

    async def _login_get(self, request: Request) -> HTMLResponse:
        txn_id = request.query_params.get("txn", "")
        return HTMLResponse(render_login_page(txn_id))

    async def _login_post(self, request: Request) -> Response:
        form = await request.form()
        txn_id = str(form.get("txn", ""))
        secret = str(form.get("secret", ""))
        client_key = request.client.host if request.client else "unknown"

        try:
            ok = self._gate.verify(client_key, secret)
        except LockedOut as exc:
            return HTMLResponse(
                render_login_page(txn_id, error=f"Too many attempts. Try again in {exc.retry_after}s."),
                status_code=429,
            )
        if not ok:
            return HTMLResponse(
                render_login_page(txn_id, error="Incorrect secret."),
                status_code=401,
            )

        payload_raw = self._storage.pop_txn(txn_id)
        if payload_raw is None:
            return HTMLResponse(
                render_login_page(txn_id, error="Session expired. Restart the connection from Claude."),
                status_code=400,
            )
        payload = json.loads(payload_raw)

        code = secrets.token_urlsafe(32)
        code_payload = {
            "redirect_uri": payload["redirect_uri"],
            "redirect_uri_provided_explicitly": payload["redirect_uri_provided_explicitly"],
            "scopes": payload["scopes"],
            "code_challenge": payload["code_challenge"],
        }
        self._storage.save_auth_code(
            code, payload["client_id"], json.dumps(code_payload),
            time.time() + self._settings.auth_code_ttl,
        )
        redirect = construct_redirect_uri(payload["redirect_uri"], code=code, state=payload["state"])
        return RedirectResponse(url=redirect, status_code=302)

    async def load_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: str
    ) -> AuthorizationCode | None:
        row = self._storage.pop_auth_code(authorization_code)
        if row is None:
            return None
        client_id, data_raw = row
        if client_id != client.client_id:
            return None
        data = json.loads(data_raw)
        return AuthorizationCode(
            code=authorization_code,
            client_id=client_id,
            redirect_uri=data["redirect_uri"],
            redirect_uri_provided_explicitly=data["redirect_uri_provided_explicitly"],
            scopes=data["scopes"],
            expires_at=time.time() + self._settings.auth_code_ttl,
            code_challenge=data["code_challenge"],
        )

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
