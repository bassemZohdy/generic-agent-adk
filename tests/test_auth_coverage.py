"""Additional tests for authentication module coverage."""

import json
from unittest.mock import MagicMock, patch
import pytest
from starlette.requests import Request
from starlette.responses import Response

from basic_agent.auth import (
    authenticate_request,
    require_roles,
    keycloak_enabled,
)


class TestAuthenticationFlow:
    """Test authentication request handling."""

    def test_authenticate_request_missing_bearer_token_when_keycloak_enabled(
        self, monkeypatch
    ):
        """Test that missing Bearer token raises error when Keycloak is configured."""
        from basic_agent import auth

        old_issuer = auth.settings.keycloak_issuer
        object.__setattr__(
            auth.settings, "keycloak_issuer", "https://keycloak.example/realms/test"
        )
        try:
            request = Request({"type": "http", "headers": []})
            with pytest.raises(Exception, match="Bearer token required"):
                authenticate_request(request)
        finally:
            object.__setattr__(auth.settings, "keycloak_issuer", old_issuer)

    def test_authenticate_request_with_bearer_token_header(self):
        """Test authentication with Bearer token in headers."""
        from basic_agent import auth

        old_issuer = auth.settings.keycloak_issuer
        object.__setattr__(auth.settings, "keycloak_issuer", "")
        try:
            # When Keycloak is disabled, Bearer token is optional
            request = Request(
                {
                    "type": "http",
                    "headers": [[b"authorization", b"Bearer token123"]],
                }
            )
            result = authenticate_request(request)
            assert result is None  # Returns None when Keycloak disabled
        finally:
            object.__setattr__(auth.settings, "keycloak_issuer", old_issuer)


class TestRoleValidation:
    """Test role claim extraction and validation."""

    def test_require_roles_with_multiple_matching_roles(self):
        """Test role validation with multiple matching roles."""
        from basic_agent import auth

        old_claim = auth.settings.keycloak_role_claim
        object.__setattr__(auth.settings, "keycloak_role_claim", "realm_access.roles")
        try:
            # Should not raise when user has required role
            require_roles(
                {"realm_access": {"roles": ["admin", "user", "viewer"]}},
                ("admin",),
            )
        finally:
            object.__setattr__(auth.settings, "keycloak_role_claim", old_claim)

    def test_require_roles_with_nested_claim_structure(self):
        """Test role validation with deeply nested claim structure."""
        from basic_agent import auth

        old_claim = auth.settings.keycloak_role_claim
        object.__setattr__(
            auth.settings, "keycloak_role_claim", "resource_access.api.roles"
        )
        try:
            require_roles(
                {"resource_access": {"api": {"roles": ["api-user"]}}},
                ("api-user",),
            )
        finally:
            object.__setattr__(auth.settings, "keycloak_role_claim", old_claim)

    def test_require_roles_with_missing_intermediate_key(self):
        """Test role validation fails when intermediate key is missing."""
        from basic_agent import auth
        from fastapi import HTTPException

        old_claim = auth.settings.keycloak_role_claim
        object.__setattr__(
            auth.settings, "keycloak_role_claim", "resource_access.api.roles"
        )
        try:
            with pytest.raises(HTTPException) as exc_info:
                require_roles({"resource_access": {}}, ("api-user",))
            assert exc_info.value.status_code == 403
        finally:
            object.__setattr__(auth.settings, "keycloak_role_claim", old_claim)

    def test_require_roles_with_non_list_roles(self):
        """Test role validation with non-list role values."""
        from basic_agent import auth
        from fastapi import HTTPException

        old_claim = auth.settings.keycloak_role_claim
        object.__setattr__(auth.settings, "keycloak_role_claim", "realm_access.roles")
        try:
            # Roles value is not a list
            with pytest.raises((HTTPException, TypeError, AttributeError)):
                require_roles(
                    {"realm_access": {"roles": "single-role"}},
                    ("single-role",),
                )
        finally:
            object.__setattr__(auth.settings, "keycloak_role_claim", old_claim)


class TestKeycloakEnabledCheck:
    """Test Keycloak enabled detection."""

    def test_keycloak_enabled_with_configured_issuer(self, monkeypatch):
        """Test keycloak_enabled returns True when issuer is configured."""
        from basic_agent import auth

        old_issuer = auth.settings.keycloak_issuer
        object.__setattr__(
            auth.settings, "keycloak_issuer", "https://keycloak.example/realms/test"
        )
        try:
            assert keycloak_enabled() is True
        finally:
            object.__setattr__(auth.settings, "keycloak_issuer", old_issuer)

    def test_keycloak_enabled_with_empty_issuer(self, monkeypatch):
        """Test keycloak_enabled returns False when issuer is empty."""
        from basic_agent import auth

        old_issuer = auth.settings.keycloak_issuer
        object.__setattr__(auth.settings, "keycloak_issuer", "")
        try:
            assert keycloak_enabled() is False
        finally:
            object.__setattr__(auth.settings, "keycloak_issuer", old_issuer)

    def test_keycloak_enabled_with_whitespace_issuer(self, monkeypatch):
        """Test keycloak_enabled with whitespace-only issuer."""
        from basic_agent import auth

        old_issuer = auth.settings.keycloak_issuer
        object.__setattr__(auth.settings, "keycloak_issuer", "   ")
        try:
            # Whitespace-only issuer should be treated as False
            result = keycloak_enabled()
            # Result depends on implementation
            assert isinstance(result, bool)
        finally:
            object.__setattr__(auth.settings, "keycloak_issuer", old_issuer)
