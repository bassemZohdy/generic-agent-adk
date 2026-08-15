from basic_agent.agent import (
    AgentState,
    GenericAgent,
    GenericAgentPlugin,
    GenericAgentResponse,
    inspect_runtime,
    request_approval,
    retrieve_knowledge,
    root_agent,
)
from basic_agent.auth import authenticate_request, keycloak_enabled
from basic_agent.auth import require_roles
from basic_agent.auth_gateway import app as auth_gateway_app
from basic_agent.autoconfig import ProviderConfigurationError, discover_capabilities
from basic_agent.config import load_settings
from basic_agent.live_server import LIVE_MODEL, app
from basic_agent.config import AgentPattern
from basic_agent.service_api import get_service_status
from basic_agent.telemetry import tracer
from google.adk.agents import LlmAgent
import pytest
from starlette.requests import Request


def test_root_agent_is_use_case_built():
    assert isinstance(root_agent, LlmAgent)
    assert root_agent.name == "direct_agent"  # assistant use case -> DIRECT strategy
    assert root_agent.output_schema is GenericAgentResponse
    assert root_agent.output_key == "last_response"
    assert root_agent.state_schema is AgentState
    assert root_agent.before_agent_callback is not None
    assert root_agent.after_agent_callback is not None


def test_agent_module_contract_exports():
    from basic_agent import agent

    for name in (
        "GenericAgent",
        "GenericAgentPlugin",
        "GenericAgentResponse",
        "AgentState",
        "root_agent",
        "generic_root_agent",
        "tools",
        "retrieve_knowledge",
        "inspect_runtime",
        "request_approval",
        "project_mcp_toolset",
        "openapi_toolset",
        "resolve_agent_config",
    ):
        assert hasattr(agent, name), name
    assert agent.generic_root_agent is agent.root_agent


def test_agent_pattern_is_externalized_and_validated(monkeypatch):
    monkeypatch.setenv("AGENT_PATTERN", "parallel")
    assert load_settings().agent_pattern is AgentPattern.PARALLEL
    monkeypatch.setenv("AGENT_PATTERN", "unknown")
    with pytest.raises(ValueError, match="Invalid AGENT_PATTERN"):
        load_settings()


def test_pattern_runtime_configuration_is_validated(monkeypatch):
    monkeypatch.setenv("AGENT_PATTERN_MAX_ITERATIONS", "5")
    monkeypatch.setenv("AGENT_PATTERN_REQUIRE_APPROVAL", "true")
    monkeypatch.setenv("AGENT_PATTERN_SPECIALISTS", "research, solution")
    configured = load_settings()
    assert configured.pattern_max_iterations == 5
    assert configured.pattern_require_approval is True
    assert configured.pattern_specialists == ("research", "solution")

    monkeypatch.setenv("AGENT_PATTERN_MAX_ITERATIONS", "0")
    with pytest.raises(ValueError, match="MAX_ITERATIONS"):
        load_settings()


def test_deprecated_agent_pattern_accepts_all_legacy_names(monkeypatch):
    """Every legacy agent.type name validates as AGENT_PATTERN and resolves via the registry."""
    from basic_agent.use_cases.registry import get_default_registry

    legacy = (
        "generic", "direct", "react", "sequential", "parallel", "loop",
        "router", "supervisor", "planner_executor", "plan_execute",
        "evaluator_optimizer", "human_in_loop",
    )
    for value in legacy:
        monkeypatch.setenv("AGENT_PATTERN", value)
        settings = load_settings()
        assert settings.agent_pattern.value == value
        canonical, _ = get_default_registry().resolve(value)
        assert canonical  # resolves to a live use case


def test_generic_plugin_and_runtime_contracts():
    assert GenericAgentPlugin().name
    runtime = inspect_runtime()
    assert '"agent": "basic_agent"' in runtime
    assert tracer is not None


def test_generic_knowledge_source_is_safe_when_unconfigured():
    assert "No external knowledge" in retrieve_knowledge("anything")


def test_external_knowledge_file_is_loaded_and_ranked(tmp_path, monkeypatch):
    knowledge = tmp_path / "knowledge.json"
    knowledge.write_text(
        '[{"title":"Alpha","content":"alpha guidance"},'
        '{"title":"Beta","content":"beta guidance"}]',
        encoding="utf-8",
    )
    monkeypatch.setenv("AGENT_KNOWLEDGE_FILE", str(knowledge))
    monkeypatch.setenv("AGENT_KNOWLEDGE_RESULT_LIMIT", "1")
    from basic_agent import agent

    old_file = agent.settings.knowledge_file
    old_limit = agent.settings.knowledge_result_limit
    object.__setattr__(agent.settings, "knowledge_file", str(knowledge))
    object.__setattr__(agent.settings, "knowledge_result_limit", 1)
    try:
        result = retrieve_knowledge("beta")
    finally:
        object.__setattr__(agent.settings, "knowledge_file", old_file)
        object.__setattr__(agent.settings, "knowledge_result_limit", old_limit)

    assert result.startswith("[Beta]")
    assert "Alpha" not in result


def test_generic_status_payload_is_not_domain_specific():
    status = get_service_status()
    assert status["status"] == "healthy"
    assert "release" not in status["service"]


def test_runtime_settings_are_externalized(monkeypatch):
    monkeypatch.setenv("APP_NAME", "configured-agent")
    monkeypatch.setenv("ADK_MODEL", "configured-model")
    monkeypatch.setenv("AGENT_TOOLS", "knowledge,approval")
    monkeypatch.setenv("AGENT_SERVICE_API_ROLES", "agent-reader,agent-operator")

    configured = load_settings()
    assert configured.app_name == "configured-agent"
    assert configured.model == "configured-model"
    assert configured.enabled_tools == ("knowledge", "approval")
    assert configured.service_api_roles == ("agent-reader", "agent-operator")


def test_runtime_settings_trim_lists_and_toggle_tools(monkeypatch):
    monkeypatch.setenv("AGENT_TOOLS", " knowledge, ,structured_output ")
    monkeypatch.setenv("AGENT_MCP_TOOLS", " first, second ")

    configured = load_settings()

    assert configured.enabled_tools == ("knowledge", "structured_output")
    assert configured.mcp_tools == ("first", "second")
    assert configured.enable_knowledge is True
    assert configured.enable_search is False
    assert configured.enable_structured_output is True


def test_capabilities_fall_back_to_in_memory_without_configuration():
    capabilities = discover_capabilities({})
    assert {name: provider.strategy for name, provider in capabilities.items()} == {
        "storage": "in_memory",
        "messaging": "in_memory",
        "caching": "in_memory",
        "search": "in_memory",
        "logging": "in_memory",
    }


def test_capabilities_select_each_local_tier():
    capabilities = discover_capabilities(
        {
            "STORAGE_PATH": "./storage",
            "BROKER_URL": "amqp://localhost:5672",
            "CACHE_PATH": "./cache",
            "SEARCH_INDEX_PATH": "./index",
            "LOG_FILE": "./agent.log",
        }
    )

    assert {name: provider.strategy for name, provider in capabilities.items()} == {
        "storage": "local_disk",
        "messaging": "local_broker",
        "caching": "local_disk",
        "search": "local_index",
        "logging": "local_file",
    }


def test_capabilities_prefer_database_over_disk_storage():
    capabilities = discover_capabilities(
        {"DATABASE_URL": "postgresql://db.example/app", "STORAGE_PATH": "./storage"}
    )

    assert capabilities["storage"].strategy == "database"


def test_detected_malformed_provider_fails_without_silent_fallback():
    try:
        discover_capabilities({"MESSAGING_URL": "not-a-url"})
    except ProviderConfigurationError as error:
        assert "messaging" in str(error)
    else:
        raise AssertionError("Malformed detected configuration was accepted")


@pytest.mark.parametrize(
    "environment, capability",
    [
        ({"SEARCH_URL": "https://search.example"}, "search"),
        ({"SEARCH_API_KEY": "secret"}, "search"),
        ({"LOG_ENDPOINT": "https://logs.example"}, "logging"),
        ({"LOG_API_KEY": "secret"}, "logging"),
    ],
)
def test_partial_detected_provider_configuration_fails_fast(environment, capability):
    with pytest.raises(ProviderConfigurationError, match=capability):
        discover_capabilities(environment)


@pytest.mark.parametrize(
    "environment",
    [
        {"STORAGE_PATH": "/"},
        {"CACHE_PATH": "/"},
        {"SEARCH_INDEX_PATH": "/"},
        {"LOG_FILE": "/"},
    ],
)
def test_invalid_local_paths_fail_fast(environment):
    with pytest.raises(ProviderConfigurationError):
        discover_capabilities(environment)


def test_live_api_reuses_generic_root_agent():
    routes = {route.path for route in app.routes}
    assert routes >= {"/healthz", "/live"}
    assert LIVE_MODEL


def test_keycloak_and_forward_auth_surfaces_exist():
    assert keycloak_enabled() is False
    assert {route.path for route in auth_gateway_app.routes} >= {"/healthz", "/verify"}


def test_authentication_is_optional_when_keycloak_is_not_configured():
    request = Request({"type": "http", "headers": []})

    assert authenticate_request(request) is None


def test_authentication_requires_bearer_token_when_keycloak_is_configured():
    from basic_agent import auth

    old_issuer = auth.settings.keycloak_issuer
    object.__setattr__(auth.settings, "keycloak_issuer", "https://keycloak.example/realms/agent")
    try:
        with pytest.raises(Exception, match="Bearer token required"):
            authenticate_request(Request({"type": "http", "headers": []}))
    finally:
        object.__setattr__(auth.settings, "keycloak_issuer", old_issuer)


def test_role_claims_accept_nested_configured_roles(monkeypatch):
    from basic_agent import auth

    old_claim = auth.settings.keycloak_role_claim
    object.__setattr__(auth.settings, "keycloak_role_claim", "resource_access.agent.roles")
    try:
        require_roles(
            {"resource_access": {"agent": {"roles": ["agent-user"]}}},
            ("agent-user",),
        )
    finally:
        object.__setattr__(auth.settings, "keycloak_role_claim", old_claim)


def test_role_claims_reject_missing_role(monkeypatch):
    from basic_agent import auth
    from fastapi import HTTPException

    old_claim = auth.settings.keycloak_role_claim
    object.__setattr__(auth.settings, "keycloak_role_claim", "realm_access.roles")
    try:
        try:
            require_roles({"realm_access": {"roles": ["other"]}}, ("agent-user",))
        except HTTPException as error:
            assert error.status_code == 403
        else:
            raise AssertionError("Missing role was accepted")
    finally:
        object.__setattr__(auth.settings, "keycloak_role_claim", old_claim)


def test_service_status_payload_uses_external_identity():
    status = get_service_status()

    assert set(status) == {"service", "environment", "status", "version"}
    assert status["service"]
