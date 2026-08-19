"""Additional tests to improve code coverage.

Tests for edge cases, error conditions, and previously untested code paths.
"""

import json
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from basic_agent.agent import inspect_runtime, request_approval, retrieve_knowledge
from basic_agent.auth import authenticate_request, keycloak_enabled, require_roles
from basic_agent.config import load_settings, settings
from basic_agent.interfaces.service import get_service_status
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
        """Malformed external knowledge fails closed without poisoning the agent."""
        knowledge_file = tmp_path / "knowledge.json"
        knowledge_file.write_text("{ invalid json }", encoding="utf-8")

        from basic_agent import knowledge as knowledge_mod

        settings_patch(knowledge_mod, knowledge_file=str(knowledge_file))
        assert (
            retrieve_knowledge("test") == "No external knowledge source is configured."
        )

    def test_retrieve_knowledge_respects_result_limit(self, tmp_path, settings_patch):
        """Test knowledge retrieval respects the result limit."""
        knowledge_file = tmp_path / "knowledge.json"
        knowledge_file.write_text(
            json.dumps(
                [{"title": f"Item{i}", "content": f"content{i}"} for i in range(10)]
            ),
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
        # Runtime inspection reports the resolved YAML/env build snapshot,
        # which may intentionally differ from import-time Settings defaults.
        assert isinstance(data["model"], str) and data["model"]
        assert isinstance(data["enabled_tools"], list | tuple)


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


class TestAgentCallbacksAndWiring:
    """Test agent callbacks and runtime wiring branches."""

    def test_before_and_after_run_callback_lifecycle(self):
        import asyncio
        from types import SimpleNamespace

        from basic_agent.agent import GenericAgentPlugin

        plugin = GenericAgentPlugin()
        plugin.capabilities = {}
        ctx = SimpleNamespace(invocation_id="test-inv-001", app_name="test-app")

        asyncio.run(plugin.before_run_callback(invocation_context=ctx))
        assert bool(plugin.capabilities)
        assert "test-inv-001" in plugin._spans

        asyncio.run(plugin.after_run_callback(invocation_context=ctx))
        assert "test-inv-001" not in plugin._spans

    def test_after_run_callback_unregistered_span(self):
        import asyncio
        from types import SimpleNamespace

        from basic_agent.agent import GenericAgentPlugin

        plugin = GenericAgentPlugin()
        ctx = SimpleNamespace(invocation_id="missing-inv-id", app_name="test-app")
        # Calling after_run_callback with unknown invocation_id should not fail
        asyncio.run(plugin.after_run_callback(invocation_context=ctx))

    def test_build_runtime_context_rejects_unknown_tool(self):
        from basic_agent.agent import _build_runtime_context
        from basic_agent.config.loader import AgentConfig, ToolsConfig

        config = AgentConfig(
            use_case="assistant",
            name="test_agent",
            tools=ToolsConfig(enabled=["runtime", "unknown_custom_tool_xyz"]),
        )
        with pytest.raises(
            ValueError, match="Unknown tool name.*unknown_custom_tool_xyz"
        ):
            _build_runtime_context(config)


class TestAuthEdgeCases:
    """Test auth token decoding and websocket edge cases."""

    def test_decode_token_missing_sub_raises_error(self, settings_patch, monkeypatch):
        from types import SimpleNamespace

        import jwt
        from cryptography.hazmat.primitives.asymmetric import rsa

        from basic_agent import auth

        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        public_key = private_key.public_key()
        settings_patch(
            auth.core,
            auth_disabled=False,
            keycloak_issuer="https://issuer.example",
            keycloak_jwks_url="https://issuer.example/jwks",
            keycloak_audience="test-aud",
        )

        class FakeJwks:
            def get_signing_key_from_jwt(self, _token):
                return SimpleNamespace(key=public_key)

        monkeypatch.setattr(auth.core, "_jwks_client", lambda _url: FakeJwks())

        token_without_sub = jwt.encode(
            {"iss": "https://issuer.example", "aud": "test-aud"},
            private_key,
            algorithm="RS256",
        )
        with pytest.raises(HTTPException) as exc_info:
            auth.core._decode(token_without_sub)
        assert exc_info.value.status_code == 401

    def test_authenticate_websocket_token_when_auth_disabled(self, settings_patch):
        from basic_agent import auth

        settings_patch(auth.core, auth_disabled=True)
        result = auth.core.authenticate_websocket_token("any-token")
        assert result == {}

    def test_authenticate_websocket_missing_token_raises_401(self, settings_patch):
        from basic_agent import auth

        settings_patch(
            auth.core, auth_disabled=False, keycloak_issuer="https://issuer.example"
        )
        ws = MagicMock()
        ws.headers = {}
        with pytest.raises(HTTPException) as exc_info:
            auth.core.authenticate_websocket(ws)
        assert exc_info.value.status_code == 401

    def test_forwardauth_gateway_healthz(self):
        from basic_agent.auth.gateway import healthz

        assert healthz() == {"status": "ok", "provider": "keycloak"}

    def test_forwardauth_gateway_verify_unconfigured(self, settings_patch):
        from basic_agent import auth
        from basic_agent.auth.gateway import verify

        settings_patch(auth.core, keycloak_issuer="", auth_disabled=False)
        req = Request({"type": "http", "headers": []})
        response = verify(req)
        assert response.status_code == 503


class TestAutoconfigProvidersCoverage:
    """Test autoconfig provider discovery edge cases."""

    def test_provider_spec_base_raises(self):
        from basic_agent.autoconfig import _ProviderSpec

        with pytest.raises(NotImplementedError):
            _ProviderSpec.discover({})

    def test_cloud_storage_invalid_bucket_paths(self):
        from basic_agent.autoconfig import (
            CloudStorageProvider,
            ProviderConfigurationError,
        )

        with pytest.raises(ProviderConfigurationError, match="Invalid storage bucket"):
            CloudStorageProvider.discover({"STORAGE_BUCKET": "bucket/with/slashes"})

        with pytest.raises(ProviderConfigurationError, match="Invalid storage bucket"):
            CloudStorageProvider.discover({"STORAGE_BUCKET": "bucket with spaces"})

        valid = CloudStorageProvider.discover({"STORAGE_BUCKET": "my-valid-bucket"})
        assert valid is not None
        assert valid.strategy == "cloud"

    def test_cloud_messaging_provider(self):
        from basic_agent.autoconfig import CloudMessagingProvider

        provider = CloudMessagingProvider.discover(
            {"MESSAGING_URL": "https://messaging.example.com"}
        )
        assert provider is not None
        assert provider.strategy == "cloud"

    def test_cloud_caching_provider_redis_url(self):
        from basic_agent.autoconfig import CloudCachingProvider

        provider = CloudCachingProvider.discover(
            {"REDIS_URL": "redis://localhost:6379"}
        )
        assert provider is not None
        assert provider.strategy == "cloud"

    def test_cloud_search_provider(self):
        from basic_agent.autoconfig import CloudSearchProvider

        provider = CloudSearchProvider.discover(
            {
                "SEARCH_URL": "https://search.example.com",
                "SEARCH_API_KEY": "test-key",
            }
        )
        assert provider is not None
        assert provider.strategy == "cloud"

    def test_cloud_logging_provider(self):
        from basic_agent.autoconfig import CloudLoggingProvider

        provider = CloudLoggingProvider.discover(
            {
                "LOG_ENDPOINT": "https://logging.example.com",
                "LOG_API_KEY": "test-key",
            }
        )
        assert provider is not None
        assert provider.strategy == "cloud"


class TestConfigLoaderValidationBranches:
    """Test config loader parsing and validation branches."""

    def test_positive_int_validation(self):
        from basic_agent.config.loader import _env_positive_int, _positive_int

        with pytest.raises(ValueError, match="must be an integer >= 1"):
            _positive_int(True, "test")
        with pytest.raises(ValueError, match="must be an integer >= 1"):
            _positive_int("string", "test")
        with pytest.raises(ValueError, match="must be an integer >= 1"):
            _env_positive_int("not-a-number", "test")

    def test_resolve_use_case_key_unregistered(self):
        from basic_agent.config.loader import _resolve_use_case_key

        assert _resolve_use_case_key(" Custom_Case ") == "custom_case"

    def test_substitute_env_vars_missing_no_default(self):
        from basic_agent.config.loader import _substitute_env_vars

        result = _substitute_env_vars("${TOTALLY_UNSET_ENV_VAR_XYZ}")
        assert result == "${TOTALLY_UNSET_ENV_VAR_XYZ}"

    def test_load_config_yaml_non_dict(self, tmp_path):
        from basic_agent.config.loader import load_config_from_yaml

        p = tmp_path / "list_config.yaml"
        p.write_text("- item1\n- item2\n", encoding="utf-8")
        with pytest.raises(ValueError, match="must be a YAML object"):
            load_config_from_yaml(p)

    def test_load_config_yaml_unresolved_env(self, tmp_path):
        from basic_agent.config.loader import load_config_from_yaml

        p = tmp_path / "unresolved.yaml"
        p.write_text(
            "agent:\n  use_case: ${UNRESOLVED_TEST_VAR_123}\n", encoding="utf-8"
        )
        with pytest.raises(ValueError, match="Unresolved environment substitution"):
            load_config_from_yaml(p)

    def test_parse_execution_code_execution_invalid_type(self):
        from basic_agent.config.loader import _parse_code_execution_config

        with pytest.raises(ValueError, match="must be a string"):
            _parse_code_execution_config({"code_execution": {"docker_host": 12345}})

    def test_parse_agent_config_not_dict(self):
        from basic_agent.config.loader import _parse_agent_config

        with pytest.raises(ValueError, match="agent must be a mapping"):
            _parse_agent_config({"agent": "not-a-mapping"})


class TestSettingsValidationErrors:
    """Test Settings parser validation errors."""

    def test_settings_bool_error(self, monkeypatch):
        from basic_agent.config.settings import _bool

        monkeypatch.setenv("TEST_BOOL_VAR", "not-bool")
        with pytest.raises(ValueError, match="must be true or false"):
            _bool("TEST_BOOL_VAR")

    def test_settings_int_error(self, monkeypatch):
        from basic_agent.config.settings import _int

        monkeypatch.setenv("TEST_INT_VAR", "invalid-int")
        with pytest.raises(ValueError, match="must be an integer"):
            _int("TEST_INT_VAR", 5)

    def test_settings_float_error(self, monkeypatch):
        from basic_agent.config.settings import _float

        monkeypatch.setenv("TEST_FLOAT_VAR", "invalid-float")
        with pytest.raises(ValueError, match="must be a number"):
            _float("TEST_FLOAT_VAR", 1.0)

        monkeypatch.setenv("TEST_FLOAT_MIN_VAR", "0.5")
        with pytest.raises(ValueError, match="must be at least 1.0"):
            _float("TEST_FLOAT_MIN_VAR", 1.0, minimum=1.0)


class TestKnowledgeCacheHit:
    """Test knowledge cache behavior."""

    def test_knowledge_cache_hit_and_missing_file(self, tmp_path, settings_patch):
        from basic_agent import knowledge as knowledge_mod

        kfile = tmp_path / "cache_test.json"
        kfile.write_text('[{"title":"Item","content":"Content"}]', encoding="utf-8")
        settings_patch(knowledge_mod, knowledge_file=str(kfile))

        entries_1 = knowledge_mod._knowledge_entries()
        entries_2 = knowledge_mod._knowledge_entries()
        assert entries_1 == entries_2
        assert len(entries_1) == 1

        # Non-existent file resets cache and returns empty list
        settings_patch(
            knowledge_mod, knowledge_file=str(tmp_path / "non_existent_file.json")
        )
        assert knowledge_mod._knowledge_entries() == []


class TestTelemetryOtelConfig:
    """Test OpenTelemetry configuration with endpoint."""

    def test_configure_telemetry_with_endpoint(self, monkeypatch):
        from basic_agent.telemetry import configure_telemetry

        monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")
        tracer = configure_telemetry()
        assert tracer is not None


class TestToolsBuildingBranches:
    """Test tools building branches and edge cases."""

    def test_api_headers_with_service_key(self, settings_patch):
        from basic_agent import tools as tools_mod

        settings_patch(tools_mod, service_api_key="service-secret-key")
        headers = tools_mod.api_headers(None)
        assert headers == {"x-api-key": "service-secret-key"}

    def test_build_skill_toolset_with_non_dir_and_invalid_dir(self, tmp_path):
        from basic_agent.config.loader import (
            AgentConfig,
            ToolsConfig,
            ToolsSkillsConfig,
        )
        from basic_agent.tools import _build_skill_toolset, build_tool

        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        (skills_dir / "regular_file.txt").write_text(
            "not a directory", encoding="utf-8"
        )

        config = AgentConfig(
            use_case="assistant",
            name="test",
            tools=ToolsConfig(skills=ToolsSkillsConfig(dir=str(skills_dir))),
        )
        toolset = _build_skill_toolset(config)
        assert toolset is not None

        config_invalid = AgentConfig(
            use_case="assistant",
            name="test",
            tools=ToolsConfig(
                skills=ToolsSkillsConfig(dir=str(tmp_path / "nonexistent_dir"))
            ),
        )
        toolset_invalid = _build_skill_toolset(config_invalid)
        assert toolset_invalid is not None

        assert build_tool("unknown_tool_type", config) is None

    def test_build_application_integration_toolset(self, settings_patch, monkeypatch):
        from basic_agent import tools as tools_mod

        settings_patch(tools_mod, gcp_project="", gcp_integration="")
        assert tools_mod._build_application_integration_toolset() is None

        settings_patch(
            tools_mod,
            gcp_project="test-project",
            gcp_integration="test-integration",
            gcp_location="us-central1",
        )
        fake_toolset = MagicMock()
        monkeypatch.setattr(
            "google.adk.tools.application_integration_tool.ApplicationIntegrationToolset",
            lambda **kwargs: fake_toolset,
        )
        assert tools_mod._build_application_integration_toolset() is fake_toolset
        assert tools_mod.build_tool("application_integration", None) is fake_toolset


class TestCustomUseCaseRegistryLoaderError:
    """Test custom use cases loading errors."""

    def test_load_custom_use_cases_bad_spec(self, tmp_path):
        from basic_agent.use_cases.registry import load_custom_use_cases

        dummy_file = tmp_path / "dummy.py"
        dummy_file.write_text("# dummy", encoding="utf-8")

        with (
            patch("importlib.util.spec_from_file_location", return_value=None),
            pytest.raises(ValueError, match="Cannot load use-case module"),
        ):
            load_custom_use_cases(str(dummy_file))


class TestResolverDefensiveBranches:
    """Test code execution resolver defensive branches."""

    def test_provider_spec_methods(self):
        from basic_agent.execution.resolver import _CodeExecutionProviderSpec

        with pytest.raises(NotImplementedError):
            _CodeExecutionProviderSpec.probe({}, model="test")
        with pytest.raises(NotImplementedError):
            _CodeExecutionProviderSpec.build({})

    def test_gemini_builtin_import_error(self):
        from basic_agent.execution.resolver import GeminiBuiltInCodeExecutionProvider

        with patch.dict("sys.modules", {"google.adk.utils.model_name_utils": None}):
            assert (
                GeminiBuiltInCodeExecutionProvider.probe({}, model="gemini-2.0-flash")
                is False
            )


class TestRestMiddlewareEdgeCases:
    """Test SubjectBindingMiddleware edge cases."""

    def test_middleware_health_and_version_bypass(self):
        import asyncio

        from starlette.requests import Request
        from starlette.responses import PlainTextResponse

        from basic_agent.interfaces.rest import SubjectBindingMiddleware

        middleware = SubjectBindingMiddleware(app=None)
        req_health = Request({"type": "http", "path": "/health", "headers": []})
        req_version = Request({"type": "http", "path": "/version", "headers": []})

        async def fake_next(req):
            return PlainTextResponse("ok")

        res1 = asyncio.run(middleware.dispatch(req_health, fake_next))
        assert res1.status_code == 200
        res2 = asyncio.run(middleware.dispatch(req_version, fake_next))
        assert res2.status_code == 200

    def test_middleware_auth_disabled_override_user_id(self, settings_patch):
        import asyncio

        from starlette.requests import Request
        from starlette.responses import JSONResponse

        from basic_agent import auth
        from basic_agent.interfaces import rest as rest_mod
        from basic_agent.interfaces.rest import SubjectBindingMiddleware

        settings_patch(auth.core, auth_disabled=True)
        settings_patch(rest_mod, auth_disabled=True)
        middleware = SubjectBindingMiddleware(app=None)

        scope = {
            "type": "http",
            "path": "/run",
            "headers": [(b"content-type", b"application/json")],
        }
        body = b'{"user_id": "other_user"}'

        async def fake_receive():
            return {"type": "http.request", "body": body, "more_body": False}

        req = Request(scope, fake_receive)

        async def fake_next(req):
            return JSONResponse({"status": "ok", "body": json.loads(req._body)})

        res = asyncio.run(middleware.dispatch(req, fake_next))
        assert res.status_code == 200
        data = json.loads(res.body)
        assert data["body"]["user_id"].startswith("anonymous:")
        assert "adk_anonymous_id=" in res.headers["set-cookie"]

    def test_middleware_malformed_json_on_run(self, settings_patch):
        import asyncio

        from starlette.requests import Request
        from starlette.responses import JSONResponse

        from basic_agent import auth
        from basic_agent.interfaces.rest import SubjectBindingMiddleware

        settings_patch(auth.core, auth_disabled=True)
        middleware = SubjectBindingMiddleware(app=None)

        scope = {
            "type": "http",
            "path": "/run",
            "headers": [(b"content-type", b"application/json")],
        }
        body = b"not-json"

        async def fake_receive():
            return {"type": "http.request", "body": body, "more_body": False}

        req = Request(scope, fake_receive)

        async def fake_next(req):
            return JSONResponse({"status": "ok"})

        res = asyncio.run(middleware.dispatch(req, fake_next))
        assert res.status_code == 200

    def test_middleware_auth_exception_handling(self, settings_patch):
        import asyncio

        from starlette.requests import Request

        from basic_agent import auth
        from basic_agent.interfaces.rest import SubjectBindingMiddleware

        settings_patch(
            auth.core, auth_disabled=False, keycloak_issuer="https://issuer.example"
        )
        middleware = SubjectBindingMiddleware(app=None)

        scope = {
            "type": "http",
            "path": "/api/resource",
            "headers": [],
        }
        req = Request(scope)

        async def fake_next(req):
            return None

        res = asyncio.run(middleware.dispatch(req, fake_next))
        assert res.status_code == 401
