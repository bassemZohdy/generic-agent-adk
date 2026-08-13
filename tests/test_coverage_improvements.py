"""Additional tests to improve code coverage.

Tests for edge cases, error conditions, and previously untested code paths.
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest
from starlette.requests import Request
from fastapi import HTTPException

from basic_agent.agent import retrieve_knowledge, inspect_runtime, request_approval
from basic_agent.config import settings, load_settings
from basic_agent.service_api import get_service_status
from basic_agent.auth import require_roles, authenticate_request, keycloak_enabled
from basic_agent.telemetry import invocation_attributes


class TestRetrieveKnowledge:
    """Test knowledge retrieval with various configurations."""

    def test_retrieve_knowledge_with_no_query_matches(self, tmp_path):
        """Test knowledge retrieval when query doesn't match any entries."""
        knowledge_file = tmp_path / "knowledge.json"
        knowledge_file.write_text(
            '[{"title":"Python","content":"Python is a language"}]',
            encoding="utf-8",
        )

        from basic_agent import agent

        old_file = agent.settings.knowledge_file
        object.__setattr__(agent.settings, "knowledge_file", str(knowledge_file))
        try:
            result = retrieve_knowledge("Java programming")
            assert "Python" in result
        finally:
            object.__setattr__(agent.settings, "knowledge_file", old_file)

    def test_retrieve_knowledge_with_text_file(self, tmp_path):
        """Test knowledge retrieval from a plain text file."""
        knowledge_file = tmp_path / "knowledge.txt"
        knowledge_file.write_text("This is knowledge content", encoding="utf-8")

        from basic_agent import agent

        old_file = agent.settings.knowledge_file
        object.__setattr__(agent.settings, "knowledge_file", str(knowledge_file))
        try:
            result = retrieve_knowledge("knowledge")
            assert "This is knowledge content" in result
        finally:
            object.__setattr__(agent.settings, "knowledge_file", old_file)

    def test_retrieve_knowledge_with_invalid_json(self, tmp_path):
        """Test knowledge retrieval with malformed JSON raises error."""
        knowledge_file = tmp_path / "knowledge.json"
        knowledge_file.write_text("{ invalid json }", encoding="utf-8")

        from basic_agent import agent
        import json

        old_file = agent.settings.knowledge_file
        object.__setattr__(agent.settings, "knowledge_file", str(knowledge_file))
        try:
            # Should raise JSONDecodeError when JSON is invalid
            with pytest.raises(json.JSONDecodeError):
                retrieve_knowledge("test")
        finally:
            object.__setattr__(agent.settings, "knowledge_file", old_file)

    def test_retrieve_knowledge_respects_result_limit(self, tmp_path):
        """Test knowledge retrieval respects the result limit."""
        knowledge_file = tmp_path / "knowledge.json"
        knowledge_file.write_text(
            json.dumps([
                {"title": f"Item{i}", "content": f"content{i}"}
                for i in range(10)
            ]),
            encoding="utf-8",
        )

        from basic_agent import agent

        old_file = agent.settings.knowledge_file
        old_limit = agent.settings.knowledge_result_limit
        object.__setattr__(agent.settings, "knowledge_file", str(knowledge_file))
        object.__setattr__(agent.settings, "knowledge_result_limit", 2)
        try:
            result = retrieve_knowledge("content")
            # Should only return 2 results
            lines = result.strip().split("\n")
            result_count = len([l for l in lines if l.startswith("[")])
            assert result_count <= 2
        finally:
            object.__setattr__(agent.settings, "knowledge_file", old_file)
            object.__setattr__(agent.settings, "knowledge_result_limit", old_limit)


class TestInspectRuntime:
    """Test runtime inspection."""

    def test_inspect_runtime_returns_valid_json(self):
        """Test that inspect_runtime returns valid JSON."""
        result = inspect_runtime()
        data = json.loads(result)
        assert "agent" in data
        assert "model" in data
        assert "enabled_tools" in data
        assert "capabilities" in data

    def test_inspect_runtime_contains_configured_values(self):
        """Test that inspect_runtime contains configured values."""
        result = inspect_runtime()
        data = json.loads(result)
        assert data["agent"] == settings.app_name
        assert data["model"] == settings.model
        assert set(data["enabled_tools"]) == set(settings.enabled_tools)


class TestRequestApproval:
    """Test approval request functionality."""

    def test_request_approval_without_confirmation(self):
        """Test approval request without prior confirmation."""
        mock_context = MagicMock()
        mock_context.tool_confirmation = None

        result = request_approval("test action", mock_context)

        assert "Confirmation requested" in result
        mock_context.request_confirmation.assert_called_once()

    def test_request_approval_with_confirmed(self):
        """Test approval request with confirmed action."""
        mock_context = MagicMock()
        mock_confirmation = MagicMock()
        mock_confirmation.confirmed = True
        mock_context.tool_confirmation = mock_confirmation

        result = request_approval("test action", mock_context)

        assert "Action confirmed" in result

    def test_request_approval_with_rejected(self):
        """Test approval request with rejected action."""
        mock_context = MagicMock()
        mock_confirmation = MagicMock()
        mock_confirmation.confirmed = False
        mock_context.tool_confirmation = mock_confirmation

        result = request_approval("test action", mock_context)

        assert "Action rejected" in result


class TestGetServiceStatus:
    """Test service status endpoint."""

    def test_service_status_structure(self):
        """Test that service status has expected structure."""
        status = get_service_status()

        assert "service" in status
        assert "environment" in status
        assert "status" in status
        assert "version" in status

    def test_service_status_has_values(self):
        """Test that service status contains non-empty values."""
        status = get_service_status()

        assert status["service"]  # Should have service name
        assert status["status"] == "healthy"  # Should be healthy
        assert status["version"]  # Should have version


class TestRequireRoles:
    """Test role requirement validation."""

    def test_require_roles_with_matching_roles(self, monkeypatch):
        """Test role validation with matching roles."""
        from basic_agent import auth

        old_claim = auth.settings.keycloak_role_claim
        object.__setattr__(auth.settings, "keycloak_role_claim", "realm_access.roles")
        try:
            # Should not raise
            require_roles(
                {"realm_access": {"roles": ["admin", "user"]}},
                ("admin",),
            )
        finally:
            object.__setattr__(auth.settings, "keycloak_role_claim", old_claim)

    def test_require_roles_with_missing_roles(self, monkeypatch):
        """Test role validation fails with missing required roles."""
        from basic_agent import auth

        old_claim = auth.settings.keycloak_role_claim
        object.__setattr__(auth.settings, "keycloak_role_claim", "realm_access.roles")
        try:
            with pytest.raises(HTTPException) as exc_info:
                require_roles(
                    {"realm_access": {"roles": ["user"]}},
                    ("admin",),
                )
            assert exc_info.value.status_code == 403
        finally:
            object.__setattr__(auth.settings, "keycloak_role_claim", old_claim)

    def test_require_roles_with_missing_claim_path(self):
        """Test role validation with missing claim path."""
        from basic_agent import auth

        old_claim = auth.settings.keycloak_role_claim
        object.__setattr__(auth.settings, "keycloak_role_claim", "nonexistent.path")
        try:
            with pytest.raises(HTTPException) as exc_info:
                require_roles({"realm_access": {"roles": ["user"]}}, ("user",))
            assert exc_info.value.status_code == 403
        finally:
            object.__setattr__(auth.settings, "keycloak_role_claim", old_claim)

    def test_require_roles_with_empty_required_roles(self):
        """Test role validation with empty required roles."""
        from basic_agent import auth

        old_claim = auth.settings.keycloak_role_claim
        object.__setattr__(auth.settings, "keycloak_role_claim", "realm_access.roles")
        try:
            # Should not raise when no roles required
            require_roles({"realm_access": {"roles": []}}, ())
        finally:
            object.__setattr__(auth.settings, "keycloak_role_claim", old_claim)


class TestAuthenticateRequest:
    """Test request authentication."""

    def test_authenticate_request_when_keycloak_disabled(self):
        """Test authentication returns None when Keycloak is not configured."""
        from basic_agent import auth

        old_issuer = auth.settings.keycloak_issuer
        object.__setattr__(auth.settings, "keycloak_issuer", "")
        try:
            request = Request({"type": "http", "headers": []})
            result = authenticate_request(request)
            assert result is None
        finally:
            object.__setattr__(auth.settings, "keycloak_issuer", old_issuer)

    def test_keycloak_enabled_false_when_not_configured(self):
        """Test keycloak_enabled returns False when not configured."""
        from basic_agent import auth

        old_issuer = auth.settings.keycloak_issuer
        object.__setattr__(auth.settings, "keycloak_issuer", "")
        try:
            assert keycloak_enabled() is False
        finally:
            object.__setattr__(auth.settings, "keycloak_issuer", old_issuer)


class TestInvocationAttributes:
    """Test invocation attribute generation."""

    def test_invocation_attributes_structure(self):
        """Test that invocation attributes have expected structure."""
        mock_context = MagicMock()
        mock_context.invocation_id = "test-123"
        mock_context.request = MagicMock()
        mock_context.request.body = b'{"input": "test"}'

        attrs = invocation_attributes(mock_context)

        assert isinstance(attrs, dict)
        assert "adk.invocation_id" in attrs


class TestConfigurationEdgeCases:
    """Test configuration edge cases."""

    def test_load_settings_with_empty_env_vars(self, monkeypatch):
        """Test loading settings with empty environment variables."""
        monkeypatch.setenv("AGENT_TOOLS", "")

        config = load_settings()
        assert config.enabled_tools == ()

    def test_load_settings_with_whitespace_tools(self, monkeypatch):
        """Test loading settings strips whitespace from tool names."""
        monkeypatch.setenv("AGENT_TOOLS", "  knowledge  ,  , search  ")

        config = load_settings()
        assert "knowledge" in config.enabled_tools
        assert "search" in config.enabled_tools
        assert len(config.enabled_tools) == 2

    def test_load_settings_with_invalid_pattern(self, monkeypatch):
        """Test loading settings with invalid agent pattern."""
        monkeypatch.setenv("AGENT_PATTERN", "invalid_pattern")

        with pytest.raises(ValueError, match="Invalid AGENT_PATTERN"):
            load_settings()

    def test_load_settings_min_max_iterations(self, monkeypatch):
        """Test max iterations validation."""
        monkeypatch.setenv("AGENT_PATTERN_MAX_ITERATIONS", "0")

        with pytest.raises(ValueError, match="MAX_ITERATIONS"):
            load_settings()

    def test_load_settings_with_invalid_approval_value(self, monkeypatch):
        """Test invalid approval value."""
        monkeypatch.setenv("AGENT_PATTERN_REQUIRE_APPROVAL", "maybe")

        with pytest.raises(ValueError, match="must be true or false"):
            load_settings()

    def test_load_settings_preserves_defaults(self, monkeypatch):
        """Test that unset values use defaults."""
        monkeypatch.delenv("APP_NAME", raising=False)

        config = load_settings()
        assert config.app_name == "basic_agent"

    def test_load_settings_model_defaults(self, monkeypatch):
        """Test model defaults."""
        monkeypatch.delenv("ADK_MODEL", raising=False)

        config = load_settings()
        assert config.model == "gemini-3.6-flash"

    def test_load_settings_live_model_defaults(self, monkeypatch):
        """Test live model defaults."""
        monkeypatch.delenv("LIVE_ADK_MODEL", raising=False)

        config = load_settings()
        assert config.live_model == "gemini-3.1-flash-live-preview"
