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
from basic_agent.auth import keycloak_enabled
from basic_agent.auth_gateway import app as auth_gateway_app
from basic_agent.autoconfig import ProviderConfigurationError, discover_capabilities
from basic_agent.config import load_settings
from basic_agent.evaluation import EVAL_CONFIG, EVAL_SET, build_eval_command
from basic_agent.live_server import LIVE_MODEL, app
from basic_agent.service_api import get_service_status
from basic_agent.telemetry import tracer


def test_root_agent_is_generic_and_configuration_driven():
    assert isinstance(root_agent, GenericAgent)
    assert root_agent.output_schema is GenericAgentResponse
    assert root_agent.output_key == "last_response"
    assert root_agent.state_schema is AgentState
    assert root_agent.sub_agents == []
    assert root_agent.before_agent_callback is not None
    assert root_agent.after_agent_callback is not None


def test_generic_plugin_and_runtime_contracts():
    assert GenericAgentPlugin().name
    runtime = inspect_runtime()
    assert '"agent": "basic_agent"' in runtime
    assert tracer is not None


def test_generic_knowledge_source_is_safe_when_unconfigured():
    assert "No external knowledge" in retrieve_knowledge("anything")


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


def test_capabilities_fall_back_to_in_memory_without_configuration():
    capabilities = discover_capabilities({})
    assert {name: provider.strategy for name, provider in capabilities.items()} == {
        "storage": "in_memory",
        "messaging": "in_memory",
        "caching": "in_memory",
        "search": "in_memory",
        "logging": "in_memory",
    }


def test_detected_malformed_provider_fails_without_silent_fallback():
    try:
        discover_capabilities({"MESSAGING_URL": "not-a-url"})
    except ProviderConfigurationError as error:
        assert "messaging" in str(error)
    else:
        raise AssertionError("Malformed detected configuration was accepted")


def test_live_api_reuses_generic_root_agent():
    routes = {route.path for route in app.routes}
    assert routes >= {"/healthz", "/live"}
    assert LIVE_MODEL


def test_keycloak_and_forward_auth_surfaces_exist():
    assert keycloak_enabled() is False
    assert {route.path for route in auth_gateway_app.routes} >= {"/healthz", "/verify"}


def test_evaluation_entry_point_targets_dataset_and_config():
    command = build_eval_command(detailed=True)
    assert command[1:2] == ["eval"]
    assert str(EVAL_SET) in command
    assert any(str(EVAL_CONFIG) in argument for argument in command)
    assert "--print_detailed_results" in command
