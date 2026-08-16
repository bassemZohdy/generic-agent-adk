"""End-to-end tests for the /status endpoint's auth wiring in service_api.py."""

from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient
import pytest

from basic_agent import auth, service_api


@pytest.fixture
def client():
    return TestClient(service_api.app)


def _patch_both(settings_patch, **changes):
    """Keep basic_agent.auth.settings and basic_agent.service_api.settings in sync."""
    settings_patch(auth, **changes)
    return settings_patch(service_api, **changes)


class TestStatusEndpointAuthDisabled:
    def test_auth_disabled_returns_status_without_credentials(self, settings_patch, client):
        _patch_both(settings_patch, auth_disabled=True, keycloak_issuer="")
        response = client.get("/status")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"


class TestStatusEndpointMisconfigured:
    def test_missing_issuer_returns_503(self, settings_patch, client):
        _patch_both(settings_patch, auth_disabled=False, keycloak_issuer="")
        response = client.get("/status")
        assert response.status_code == 503


class TestStatusEndpointNoCredentials:
    def test_no_bearer_or_api_key_returns_401(self, settings_patch, client):
        _patch_both(
            settings_patch,
            auth_disabled=False,
            keycloak_issuer="https://keycloak.example/realms/test",
            service_api_key="",
        )
        response = client.get("/status")
        assert response.status_code == 401


class TestStatusEndpointApiKey:
    def test_valid_service_api_key_returns_status(self, settings_patch, client):
        _patch_both(
            settings_patch,
            auth_disabled=False,
            keycloak_issuer="https://keycloak.example/realms/test",
            service_api_key="s3cret",
            service_api_roles=("agent-user",),
        )
        response = client.get("/status", headers={"x-api-key": "s3cret"})
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"

    def test_wrong_service_api_key_returns_401(self, settings_patch, client):
        _patch_both(
            settings_patch,
            auth_disabled=False,
            keycloak_issuer="https://keycloak.example/realms/test",
            service_api_key="s3cret",
        )
        response = client.get("/status", headers={"x-api-key": "wrong-key"})
        assert response.status_code == 401


class TestStatusEndpointBearerToken:
    def test_valid_bearer_token_with_required_role_returns_status(
        self, settings_patch, client
    ):
        _patch_both(
            settings_patch,
            auth_disabled=False,
            keycloak_issuer="https://keycloak.example/realms/test",
            keycloak_role_claim="realm_access.roles",
            service_api_roles=("agent-user",),
        )
        claims = {"sub": "user-1", "realm_access": {"roles": ["agent-user"]}}
        with patch("basic_agent.auth._decode", return_value=claims):
            response = client.get(
                "/status", headers={"authorization": "Bearer valid-token"}
            )
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"

    def test_bearer_token_missing_required_role_returns_403(self, settings_patch, client):
        _patch_both(
            settings_patch,
            auth_disabled=False,
            keycloak_issuer="https://keycloak.example/realms/test",
            keycloak_role_claim="realm_access.roles",
            service_api_roles=("agent-user",),
        )
        claims = {"sub": "user-1", "realm_access": {"roles": ["someone-else"]}}
        with patch("basic_agent.auth._decode", return_value=claims):
            response = client.get(
                "/status", headers={"authorization": "Bearer valid-token"}
            )
        assert response.status_code == 403
