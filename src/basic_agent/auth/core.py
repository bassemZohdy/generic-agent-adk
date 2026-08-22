"""Keycloak OIDC bearer-token validation for the application APIs."""

from __future__ import annotations

import secrets
from typing import Any

import jwt
from fastapi import HTTPException, Request, WebSocket
from jwt import PyJWKClient

from ..config.settings import settings

_jwks_clients: dict[str, PyJWKClient] = {}


def keycloak_enabled() -> bool:
    """Return whether bearer-token validation is active.

    An absent issuer is intentionally not treated as an authentication bypass.
    Callers must opt out explicitly with ``AUTH_DISABLED=true``.
    """
    return bool(settings.keycloak_issuer.strip() and not settings.auth_disabled)


def _authentication_required() -> None:
    if settings.auth_disabled:
        return
    if not settings.keycloak_issuer.strip():
        raise HTTPException(
            status_code=503,
            detail=(
                "Keycloak authentication is not configured; set KEYCLOAK_ISSUER "
                "or explicitly set AUTH_DISABLED=true"
            ),
        )


def _jwks_client(url: str) -> PyJWKClient:
    """Return a cached JWKS client with bounded network fetches."""
    client = _jwks_clients.get(url)
    if client is None:
        client = PyJWKClient(
            url,
            cache_keys=True,
            cache_jwk_set=True,
            lifespan=300,
            timeout=settings.keycloak_jwks_timeout,
        )
        _jwks_clients[url] = client
    return client


def _decode(token: str) -> dict[str, Any]:
    issuer = settings.keycloak_issuer
    if not issuer.strip():
        raise HTTPException(
            status_code=503, detail="Keycloak authentication is not configured"
        )
    jwks_url = settings.keycloak_jwks_url
    if not jwks_url:
        raise HTTPException(
            status_code=503, detail="Keycloak JWKS URL is not configured"
        )
    try:
        signing_key = _jwks_client(jwks_url).get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            issuer=issuer,
            audience=settings.keycloak_audience,
            options={"verify_aud": True},
        )
        if not claims.get("sub"):
            raise jwt.InvalidTokenError("Token subject is required")
        return claims
    except (jwt.PyJWTError, ValueError, OSError) as error:
        raise HTTPException(
            status_code=401, detail="Invalid Keycloak access token"
        ) from error


def token_from_request(request: Request) -> str | None:
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    return token.strip() if scheme.lower() == "bearer" and token.strip() else None


def _claim_roles(claims: dict[str, Any]) -> set[str]:
    value: Any = claims
    for part in settings.keycloak_role_claim.split("."):
        value = value.get(part, {}) if isinstance(value, dict) else {}
    return set(value) if isinstance(value, list) else set()


def roles_from_claims(claims: dict[str, Any] | None) -> set[str]:
    """Return the configured role set for audit logging and identity context."""
    return _claim_roles(claims or {})


def require_roles(claims: dict[str, Any], required_roles: tuple[str, ...]) -> None:
    if required_roles and not set(required_roles).intersection(_claim_roles(claims)):
        raise HTTPException(status_code=403, detail="Required Keycloak role is missing")


def _service_key_claims() -> dict[str, Any]:
    """Represent the configured service key as its explicitly granted roles."""
    claims: dict[str, Any] = {
        "sub": "internal-service",
        "auth_method": "api_key",
    }
    value: dict[str, Any] = claims
    parts = settings.keycloak_role_claim.split(".")
    for part in parts[:-1]:
        child: dict[str, Any] = {}
        value[part] = child
        value = child
    value[parts[-1]] = list(settings.service_api_roles)
    return claims


def authenticate_request(
    request: Request,
    *,
    api_key: str | None = None,
    required_roles: tuple[str, ...] = (),
) -> dict[str, Any] | None:
    """Authenticate a bearer token or the explicitly configured service key."""
    _authentication_required()
    if settings.auth_disabled:
        return None

    token = token_from_request(request)
    if token:
        claims = _decode(token)
        require_roles(claims, required_roles)
        return claims

    if (
        settings.service_api_key
        and api_key
        and secrets.compare_digest(api_key, settings.service_api_key)
    ):
        claims = _service_key_claims()
        require_roles(claims, required_roles)
        return claims
    raise HTTPException(
        status_code=401, detail="Bearer token or valid service API key required"
    )


def _websocket_auth_subprotocol(websocket: WebSocket) -> tuple[str, str] | None:
    # Browser clients cannot set Authorization reliably.  Accept a token in a
    # negotiated subprotocol without ever reading it from a URL query string.
    # Supported forms are ``bearer.<token>``, ``authorization.bearer.<token>``,
    # and ``bearer, <token>``.
    #
    # The return value is ``(token, subprotocol_to_echo)`` and the echo name is
    # always the constant ``"bearer"``: reflecting the token (``bearer.<token>``
    # or ``bearer,<token>``) would leak the raw credential in the
    # ``Sec-WebSocket-Protocol`` response header, and per RFC 6455 §4.1 a server
    # may only echo a subprotocol the client actually offered.
    protocols = [
        p.strip()
        for p in websocket.headers.get("sec-websocket-protocol", "").split(",")
        if p.strip()
    ]
    for i, value in enumerate(protocols):
        lowered = value.lower()
        for prefix in ("bearer.", "authorization.bearer."):
            if lowered.startswith(prefix) and value[len(prefix) :].strip():
                return value[len(prefix) :].strip(), "bearer"
        if lowered == "bearer" and i + 1 < len(protocols) and protocols[i + 1]:
            return protocols[i + 1], "bearer"
    return None


def _websocket_header_token(websocket: WebSocket) -> str | None:
    header = websocket.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() == "bearer" and token.strip():
        return token.strip()

    if extracted := _websocket_auth_subprotocol(websocket):
        return extracted[0]
    return None


def websocket_auth_subprotocol(websocket: WebSocket) -> tuple[str, str] | None:
    """Return ``(token, subprotocol_to_echo)`` for the offered auth subprotocol.

    The echo name is the constant ``"bearer"`` and never contains the token, so
    callers can pass it straight to ``websocket.accept(subprotocol=...)``.
    """
    return _websocket_auth_subprotocol(websocket)


def authenticate_websocket_token(token: str) -> dict[str, Any]:
    """Validate a token received in the first WebSocket auth message."""
    _authentication_required()
    if settings.auth_disabled:
        return {}
    if not token.strip():
        raise HTTPException(status_code=401, detail="Bearer token required")
    claims = _decode(token.strip())
    require_roles(claims, settings.live_api_roles)
    return claims


def authenticate_websocket(
    websocket: WebSocket,
    *,
    required_roles: tuple[str, ...] = (),
) -> dict[str, Any] | None:
    """Authenticate a WebSocket header/subprotocol token, never a query token."""
    _authentication_required()
    if settings.auth_disabled:
        return None
    token = _websocket_header_token(websocket)
    if not token:
        raise HTTPException(
            status_code=401,
            detail="Bearer token required in Authorization header, subprotocol, or first message",
        )
    claims = _decode(token)
    require_roles(claims, required_roles)
    return claims
