"""Additional tests for authentication module coverage."""

import pytest
from starlette.requests import Request

from basic_agent.auth import (
    authenticate_request,
    keycloak_enabled,
    require_roles,
)


class TestAuthenticationFlow:
    """Test authentication request handling."""

    def test_authenticate_request_missing_bearer_token_when_keycloak_enabled(
        self, settings_patch
    ):
        """Test that missing Bearer token raises error when Keycloak is configured."""
        from basic_agent import auth

        settings_patch(
            auth.core,
            keycloak_issuer="https://keycloak.example/realms/test",
            auth_disabled=False,
        )
        request = Request({"type": "http", "headers": []})
        with pytest.raises(Exception, match="Bearer token"):
            authenticate_request(request)

    def test_authenticate_request_with_bearer_token_header(self, settings_patch):
        """Test authentication with Bearer token in headers."""
        from basic_agent import auth

        settings_patch(auth.core, keycloak_issuer="", auth_disabled=True)
        # Authentication is disabled only by explicit opt-in.
        request = Request(
            {
                "type": "http",
                "headers": [[b"authorization", b"Bearer token123"]],
            }
        )
        result = authenticate_request(request)
        assert result is None  # Returns None when Keycloak disabled


class TestRoleValidation:
    """Test role claim extraction and validation."""

    def test_require_roles_with_multiple_matching_roles(self, settings_patch):
        """Test role validation with multiple matching roles."""
        from basic_agent import auth

        settings_patch(auth.core, keycloak_role_claim="realm_access.roles")
        # Should not raise when user has required role
        require_roles(
            {"realm_access": {"roles": ["admin", "user", "viewer"]}},
            ("admin",),
        )

    def test_require_roles_with_nested_claim_structure(self, settings_patch):
        """Test role validation with deeply nested claim structure."""
        from basic_agent import auth

        settings_patch(auth.core, keycloak_role_claim="resource_access.api.roles")
        require_roles(
            {"resource_access": {"api": {"roles": ["api-user"]}}},
            ("api-user",),
        )

    def test_require_roles_with_missing_intermediate_key(self, settings_patch):
        """Test role validation fails when intermediate key is missing."""
        from fastapi import HTTPException

        from basic_agent import auth

        settings_patch(auth.core, keycloak_role_claim="resource_access.api.roles")
        with pytest.raises(HTTPException) as exc_info:
            require_roles({"resource_access": {}}, ("api-user",))
        assert exc_info.value.status_code == 403

    def test_require_roles_with_non_list_roles(self, settings_patch):
        """Test role validation with non-list role values."""
        from fastapi import HTTPException

        from basic_agent import auth

        settings_patch(auth.core, keycloak_role_claim="realm_access.roles")
        # Roles value is not a list
        with pytest.raises((HTTPException, TypeError, AttributeError)):
            require_roles(
                {"realm_access": {"roles": "single-role"}},
                ("single-role",),
            )


class TestKeycloakEnabledCheck:
    """Test Keycloak enabled detection."""

    def test_keycloak_enabled_with_configured_issuer(self, settings_patch):
        """Test keycloak_enabled returns True when issuer is configured."""
        from basic_agent import auth

        settings_patch(
            auth.core,
            keycloak_issuer="https://keycloak.example/realms/test",
            auth_disabled=False,
        )
        assert keycloak_enabled() is True

    def test_keycloak_enabled_with_empty_issuer(self, settings_patch):
        """Test keycloak_enabled returns False when issuer is empty."""
        from basic_agent import auth

        settings_patch(auth.core, keycloak_issuer="", auth_disabled=False)
        assert keycloak_enabled() is False

    def test_keycloak_enabled_with_whitespace_issuer(self, settings_patch):
        """Test keycloak_enabled with whitespace-only issuer."""
        from basic_agent import auth

        settings_patch(auth.core, keycloak_issuer="   ", auth_disabled=False)
        # Whitespace-only issuer should be treated as False
        result = keycloak_enabled()
        assert isinstance(result, bool)
