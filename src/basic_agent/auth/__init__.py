"""Authentication: JWT validation + Traefik forward-auth gateway."""

from .core import (
    authenticate_request,
    authenticate_websocket,
    authenticate_websocket_token,
    keycloak_enabled,
    require_roles,
    roles_from_claims,
    token_from_request,
    websocket_auth_subprotocol,
)
from .gateway import app

__all__ = [
    "authenticate_request",
    "authenticate_websocket",
    "authenticate_websocket_token",
    "keycloak_enabled",
    "require_roles",
    "roles_from_claims",
    "token_from_request",
    "websocket_auth_subprotocol",
    "app",
]
