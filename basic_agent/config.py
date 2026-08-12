"""Externalized runtime settings for the application and authorization policy."""

from __future__ import annotations

from dataclasses import dataclass
import os


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _roles(name: str, default: str) -> tuple[str, ...]:
    return tuple(role for role in (_env(name, default).split(",")) if role)


@dataclass(frozen=True)
class Settings:
    app_name: str
    app_version: str
    deployment: str
    model: str
    live_model: str
    release_api_url: str
    release_api_key: str
    keycloak_issuer: str
    keycloak_jwks_url: str
    keycloak_audience: str
    keycloak_role_claim: str
    keycloak_required_roles: tuple[str, ...]
    release_api_roles: tuple[str, ...]
    live_api_roles: tuple[str, ...]


def load_settings() -> Settings:
    app_name = _env("APP_NAME", "basic_agent")
    issuer = _env("KEYCLOAK_ISSUER")
    return Settings(
        app_name=app_name,
        app_version=_env("APP_VERSION", "0.1.0"),
        deployment=_env("DEPLOYMENT_ENV", "docker-compose"),
        model=_env("ADK_MODEL", "gemini-3.6-flash"),
        live_model=_env("LIVE_ADK_MODEL", "gemini-3.1-flash-live-preview"),
        release_api_url=_env("RELEASE_API_URL", "http://127.0.0.1:8001"),
        release_api_key=_env("RELEASE_API_KEY"),
        keycloak_issuer=issuer,
        keycloak_jwks_url=_env(
            "KEYCLOAK_JWKS_URL",
            f"{issuer.rstrip('/')}/protocol/openid-connect/certs" if issuer else "",
        ),
        keycloak_audience=_env("KEYCLOAK_AUDIENCE"),
        keycloak_role_claim=_env("KEYCLOAK_ROLE_CLAIM", "realm_access.roles"),
        keycloak_required_roles=_roles("KEYCLOAK_REQUIRED_ROLES", "release-reader"),
        release_api_roles=_roles("RELEASE_API_ROLES", "release-reader"),
        live_api_roles=_roles("LIVE_API_ROLES", "release-reader"),
    )


settings = load_settings()
