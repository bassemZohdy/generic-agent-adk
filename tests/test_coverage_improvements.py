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
from basic_agent.interfaces.service import get_service_status
from basic_agent.auth import require_roles, authenticate_request, keycloak_enabled
from basic_agent.telemetry import invocation_attributes


class TestRetrieveKnowledge:
    """Test knowledge retrieval with various configurations."""

    def test_retrieve_knowledge_with_no_query_matches(self, tmp_path, settings_patch):
        """Test knowledge retrieval when query doesn't match any entries."""
        knowledge_file = tmp_path / "knowledge.json"
        knowledge_file.write_text(
            '[{"title":"Python","content":"Python is a language"}]',
            encoding="utf-8",
        )

        from basic_agent import knowledge as knowledge_mod

        settings_patch(knowledge_mod, knowledge_file=str(knowledge_file))
        result = retrieve_knowledge("Java programming")
        assert "Python" in result

    def test_retrieve_knowledge_with_text_file(self, tmp_path, settings_patch):
        """Test knowledge retrieval from a plain text file."""
        knowledge_file = tmp_path / "knowledge.txt"
        knowledge_file.write_text("This is knowledge content", encoding="utf-8")

        from basic_agent import knowledge as knowledge_mod

        settings_patch(knowledge_mod, knowledge_file=str(knowledge_file))
        result = retrieve_knowledge("knowledge")
        assert "This is knowledge content" in result

    def test_retrieve_knowledge_with_invalid_json(self, tmp_path, settings_patch):
        """Test knowledge retrieval with malformed JSON raises error."""
        knowledge_file = tmp_path / "knowledge.json"
        knowledge_file.write_text("{ invalid json }", encoding="utf-8")

        from basic_agent import knowledge as knowledge_mod
        import json

        settings_patch(knowledge_mod, knowledge_file=str(knowledge_file))
        # Should raise JSONDecodeError when JSON is invalid
        with pytest.raises(json.JSONDecodeError):
            retrieve_knowledge("test")

    def test_retrieve_knowledge_respects_result_limit(self, tmp_path, settings_patch):
        """Test knowledge retrieval respects the result limit."""
        knowledge_file = tmp_path / "knowledge.json"
        knowledge_file.write_text(
            json.dumps([
                {"title": f"Item{i}", "content": f"content{i}"}
                for i in range(10)
            ]),
            encoding="utf-8",
        )

        from basic_agent import knowledge as knowledge_mod

        settings_patch(
            knowledge_mod,
            knowledge_file=str(knowledge_file),
            knowledge_result_limit=2,
        )
        result = retrieve_knowledge("content")
        # Should only return 2 results
        lines = result.strip().split("\n")
        result_count = len([l for l in lines if l.startswith("[")])
        assert result_count <= 2


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

    def test_require_roles_with_matching_roles(self, settings_patch):
        """Test role validation with matching roles."""
        from basic_agent import auth

        settings_patch(auth.core, keycloak_role_claim="realm_access.roles")
        # Should not raise
        require_roles(
            {"realm_access": {"roles": ["admin", "user"]}},
            ("admin",),
        )

    def test_require_roles_with_missing_roles(self, settings_patch):
        """Test role validation fails with missing required roles."""
        from basic_agent import auth

        settings_patch(auth.core, keycloak_role_claim="realm_access.roles")
        with pytest.raises(HTTPException) as exc_info:
            require_roles(
                {"realm_access": {"roles": ["user"]}},
                ("admin",),
            )
        assert exc_info.value.status_code == 403

    def test_require_roles_with_missing_claim_path(self, settings_patch):
        """Test role validation with missing claim path."""
        from basic_agent import auth

        settings_patch(auth.core, keycloak_role_claim="nonexistent.path")
        with pytest.raises(HTTPException) as exc_info:
            require_roles({"realm_access": {"roles": ["user"]}}, ("user",))
        assert exc_info.value.status_code == 403

    def test_require_roles_with_empty_required_roles(self, settings_patch):
        """Test role validation with empty required roles."""
        from basic_agent import auth

        settings_patch(auth.core, keycloak_role_claim="realm_access.roles")
        # Should not raise when no roles required
        require_roles({"realm_access": {"roles": []}}, ())


class TestAuthenticateRequest:
    """Test request authentication."""

    def test_authenticate_request_when_keycloak_disabled(self, settings_patch):
        """Test authentication returns None when Keycloak is not configured."""
        from basic_agent import auth

        settings_patch(auth.core, keycloak_issuer="", auth_disabled=True)
        request = Request({"type": "http", "headers": []})
        result = authenticate_request(request)
        assert result is None

    def test_keycloak_enabled_false_when_not_configured(self, settings_patch):
        """Test keycloak_enabled returns False when not configured."""
        from basic_agent import auth

        settings_patch(auth.core, keycloak_issuer="", auth_disabled=True)
        assert keycloak_enabled() is False


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

    def test_load_settings_min_max_iterations(self, monkeypatch):
        """Test max iterations validation."""
        monkeypatch.setenv("AGENT_MAX_ITERATIONS", "0")

        with pytest.raises(ValueError, match="MAX_ITERATIONS"):
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
