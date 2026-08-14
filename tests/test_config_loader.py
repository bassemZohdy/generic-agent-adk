"""Tests for configuration loader."""

import logging
import os
import pytest
import tempfile
from pathlib import Path

from basic_agent.config_loader import (
    AgentConfig,
    ExecutionConfig,
    InstructionsConfig,
    ModelConfig,
    ToolsConfig,
    apply_env_overrides,
    load_config_from_env,
    load_config_from_yaml,
)
from basic_agent.strategies.base import RoleConfig

_ALL_CONFIG_ENV_VARS = (
    "AGENT_USE_CASE",
    "AGENT_PATTERN",
    "ADK_MODEL",
    "AGENT_INSTRUCTION",
    "AGENT_TOOLS",
    "AGENT_MAX_ITERATIONS",
    "AGENT_SPECIALISTS",
    "AGENT_PATTERN_MAX_ITERATIONS",
    "AGENT_PATTERN_SPECIALISTS",
    "AGENT_PATTERN_REQUIRE_APPROVAL",
    "AGENT_CONFIG_FILE",
)


def test_load_config_from_yaml_direct_agent(tmp_path):
    config_file = tmp_path / "agent.yaml"
    config_file.write_text("""
agent:
  type: DIRECT
  name: test_agent
  description: Test agent

model:
  provider: google
  name: gemini-2.0-flash

instructions:
  value: "Test instruction"

tools:
  enabled:
    - knowledge
    - search

execution:
  max_iterations: 3

output:
  schema: GenericAgentResponse
  key: last_response

state:
  enabled: true
""")

    config = load_config_from_yaml(config_file)

    assert config.type == "DIRECT"
    assert config.name == "test_agent"
    assert config.model.name == "gemini-2.0-flash"
    assert config.instructions.value == "Test instruction"
    assert "knowledge" in config.tools.enabled
    assert config.execution.max_iterations == 3


def test_load_config_from_yaml_router_agent(tmp_path):
    config_file = tmp_path / "agent.yaml"
    config_file.write_text("""
agent:
  type: ROUTER
  description: Router agent

model:
  provider: google
  name: gemini-2.0-flash

instructions:
  value: "Route to specialist"

tools:
  enabled:
    - knowledge

execution:
  max_iterations: 3
  specialists:
    - research
    - solution
    - risk

state:
  enabled: true
""")

    config = load_config_from_yaml(config_file)

    assert config.type == "ROUTER"
    assert config.execution.specialists == ["research", "solution", "risk"]


def test_load_config_from_yaml_loop_agent(tmp_path):
    config_file = tmp_path / "agent.yaml"
    config_file.write_text("""
agent:
  type: LOOP
  description: Loop agent

model:
  provider: google
  name: gemini-2.0-flash

instructions:
  value: "Iterate"

tools:
  enabled: []

execution:
  max_iterations: 5

state:
  enabled: true
""")

    config = load_config_from_yaml(config_file)

    assert config.type == "EVALUATOR_OPTIMIZER"  # loop alias -> refine_until_good
    assert config.use_case == "refine_until_good"
    assert config.execution.max_iterations == 5


def test_load_config_substitutes_environment_variables(tmp_path, monkeypatch):
    monkeypatch.setenv("TEST_MODEL", "custom-model")
    monkeypatch.setenv("TEST_INSTRUCTION", "Custom instruction")

    config_file = tmp_path / "agent.yaml"
    config_file.write_text("""
agent:
  type: DIRECT

model:
  provider: google
  name: "${TEST_MODEL}"

instructions:
  value: "${TEST_INSTRUCTION}"

tools:
  enabled: []

state:
  enabled: true
""")

    config = load_config_from_yaml(config_file)

    assert config.model.name == "custom-model"
    assert config.instructions.value == "Custom instruction"


def test_load_config_uses_default_for_missing_env_vars(tmp_path):
    config_file = tmp_path / "agent.yaml"
    config_file.write_text("""
agent:
  type: DIRECT

model:
  provider: google
  name: "${MISSING_VAR:default-model}"

instructions:
  value: "Default"

tools:
  enabled: []

state:
  enabled: true
""")

    config = load_config_from_yaml(config_file)

    assert config.model.name == "default-model"


def test_config_validation_rejects_invalid_agent_type():
    config = AgentConfig(type="", description="")

    with pytest.raises(ValueError, match="type is required"):
        config.validate()


def test_config_validation_is_structural_only():
    """Type-specific checks moved to strategies; the loader only checks structure.

    ROUTER without specialists, HUMAN_IN_LOOP without approval, and LOOP with
    max_iterations=0 all load structurally. The equivalent errors are raised
    by each strategy's validate() (covered in tests/test_strategies.py).
    """
    configs = [
        AgentConfig(type="ROUTER", description="Test", execution=ExecutionConfig(specialists=[])),
        AgentConfig(
            type="HUMAN_IN_LOOP", description="Test", execution=ExecutionConfig(require_approval=False)
        ),
        AgentConfig(type="LOOP", description="Test", execution=ExecutionConfig(max_iterations=0)),
    ]

    for config in configs:
        config.validate()  # should not raise


def test_load_config_file_not_found():
    with pytest.raises(FileNotFoundError):
        load_config_from_yaml("/nonexistent/path/config.yaml")


def test_load_config_invalid_yaml(tmp_path):
    config_file = tmp_path / "agent.yaml"
    config_file.write_text("@@@ invalid yaml @@@ [unclosed bracket")

    with pytest.raises(ValueError, match="Invalid YAML"):
        load_config_from_yaml(config_file)


def test_load_config_with_mcp_configuration(tmp_path):
    config_file = tmp_path / "agent.yaml"
    config_file.write_text("""
agent:
  type: REACT
  description: MCP agent

model:
  provider: google
  name: gemini-2.0-flash

instructions:
  value: "Use MCP tools"

tools:
  enabled:
    - knowledge
    - mcp
  mcp:
    enabled: true
    tools:
      - get_status
      - list_items
    prefix: "mcp_"

state:
  enabled: true
""")

    config = load_config_from_yaml(config_file)

    assert config.tools.mcp is not None
    assert config.tools.mcp.enabled
    assert "get_status" in config.tools.mcp.tools


def test_load_config_with_openapi_configuration(tmp_path):
    config_file = tmp_path / "agent.yaml"
    config_file.write_text("""
agent:
  type: REACT

model:
  provider: google
  name: gemini-2.0-flash

instructions:
  value: "Use OpenAPI"

tools:
  enabled:
    - openapi
  openapi:
    enabled: true
    url: "http://api.example.com"
    path: "/v1/status"
    title: "Example API"
    prefix: "api_"

state:
  enabled: true
""")

    config = load_config_from_yaml(config_file)

    assert config.tools.openapi is not None
    assert config.tools.openapi.enabled
    assert config.tools.openapi.url == "http://api.example.com"


def test_use_case_key_is_primary(tmp_path):
    config_file = tmp_path / "agent.yaml"
    config_file.write_text("""
agent:
  use_case: expert_dispatch
  description: Experts
""")

    config = load_config_from_yaml(config_file)

    assert config.use_case == "expert_dispatch"
    assert config.type == "ROUTER"


def test_type_alias_resolves_to_use_case(tmp_path):
    config_file = tmp_path / "agent.yaml"
    config_file.write_text("""
agent:
  type: SEQUENTIAL
""")

    config = load_config_from_yaml(config_file)

    assert config.use_case == "pipeline"
    assert config.type == "SEQUENTIAL"


def test_use_case_wins_over_deprecated_type(tmp_path, caplog):
    config_file = tmp_path / "agent.yaml"
    config_file.write_text("""
agent:
  use_case: pipeline
  type: ROUTER
""")

    config = load_config_from_yaml(config_file)

    assert config.use_case == "pipeline"
    assert config.type == "SEQUENTIAL"
    assert "deprecated" in caplog.text


def test_roles_section_parses_role_configs(tmp_path):
    config_file = tmp_path / "agent.yaml"
    config_file.write_text("""
agent:
  use_case: expert_dispatch

roles:
  research:
    instruction: Research deeply
    model: gemini-pro
    tools:
      - knowledge
      - search
  risk:
    instruction: Assess risk
""")

    config = load_config_from_yaml(config_file)

    assert set(config.roles) == {"research", "risk"}
    assert isinstance(config.roles["research"], RoleConfig)
    assert config.roles["research"].instruction == "Research deeply"
    assert config.roles["research"].model == "gemini-pro"
    assert config.roles["research"].tools == ["knowledge", "search"]
    assert config.roles["risk"].model is None


def test_env_builder_use_case_primary(monkeypatch):
    monkeypatch.delenv("AGENT_PATTERN", raising=False)
    monkeypatch.setenv("AGENT_USE_CASE", "expert_dispatch")

    config = load_config_from_env()

    assert config.use_case == "expert_dispatch"
    assert config.type == "ROUTER"


def test_env_builder_deprecated_pattern_fallback(monkeypatch, caplog):
    monkeypatch.delenv("AGENT_USE_CASE", raising=False)
    monkeypatch.setenv("AGENT_PATTERN", "sequential")

    config = load_config_from_env()

    assert config.use_case == "pipeline"
    assert config.type == "SEQUENTIAL"
    assert "deprecated" in caplog.text


def test_env_builder_defaults(monkeypatch):
    for var in _ALL_CONFIG_ENV_VARS:
        monkeypatch.delenv(var, raising=False)

    config = load_config_from_env()

    assert config.use_case == "assistant"
    assert config.type == "DIRECT"
    assert config.execution.max_iterations == 3
    assert config.execution.require_approval is False
    assert config.execution.specialists == ["research", "solution", "risk"]


def test_env_builder_execution_overrides(monkeypatch):
    for var in _ALL_CONFIG_ENV_VARS:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("AGENT_MAX_ITERATIONS", "7")
    monkeypatch.setenv("AGENT_SPECIALISTS", "alpha, beta")
    monkeypatch.setenv("AGENT_PATTERN_REQUIRE_APPROVAL", "true")

    config = load_config_from_env()

    assert config.execution.max_iterations == 7
    assert config.execution.specialists == ["alpha", "beta"]
    assert config.execution.require_approval is True


def test_env_builder_deprecated_execution_fallbacks(monkeypatch, caplog):
    for var in _ALL_CONFIG_ENV_VARS:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("AGENT_PATTERN_MAX_ITERATIONS", "9")
    monkeypatch.setenv("AGENT_PATTERN_SPECIALISTS", "x, y")

    config = load_config_from_env()

    assert config.execution.max_iterations == 9
    assert config.execution.specialists == ["x", "y"]
    assert "deprecated" in caplog.text


@pytest.fixture
def base_config():
    return AgentConfig(
        type="DIRECT",
        use_case="assistant",
        model=ModelConfig(provider="google", name="yaml-model"),
        instructions=InstructionsConfig(value="yaml instruction"),
        tools=ToolsConfig(enabled=["runtime"]),
        execution=ExecutionConfig(max_iterations=3, specialists=["x"]),
    )


@pytest.mark.parametrize(
    "env,expected",
    [
        ({"AGENT_USE_CASE": "pipeline"}, ("use_case", "pipeline")),
        ({"ADK_MODEL": "env-model"}, ("model_name", "env-model")),
        ({"AGENT_INSTRUCTION": "env instruction"}, ("instruction", "env instruction")),
        ({"AGENT_TOOLS": "knowledge, search"}, ("tools", ["knowledge", "search"])),
        ({"AGENT_MAX_ITERATIONS": "9"}, ("max_iterations", 9)),
        ({"AGENT_SPECIALISTS": "a,b"}, ("specialists", ["a", "b"])),
    ],
)
def test_apply_env_overrides_applies_only_explicit_vars(
    monkeypatch, base_config, env, expected
):
    for var in _ALL_CONFIG_ENV_VARS:
        monkeypatch.delenv(var, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)

    result = apply_env_overrides(base_config)
    kind, expected_value = expected
    if kind == "use_case":
        assert (result.use_case, result.type) == ("pipeline", "SEQUENTIAL")
    elif kind == "model_name":
        assert result.model.name == expected_value
    elif kind == "instruction":
        assert result.instructions.value == expected_value
    elif kind == "tools":
        assert result.tools.enabled == expected_value
    elif kind == "max_iterations":
        assert result.execution.max_iterations == expected_value
    elif kind == "specialists":
        assert result.execution.specialists == expected_value


def test_apply_env_overrides_noop_when_unset(monkeypatch, base_config):
    for var in _ALL_CONFIG_ENV_VARS:
        monkeypatch.delenv(var, raising=False)

    assert apply_env_overrides(base_config) == base_config


def test_apply_env_overrides_creates_missing_subconfigs(monkeypatch):
    for var in _ALL_CONFIG_ENV_VARS:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("ADK_MODEL", "env-model")
    monkeypatch.setenv("AGENT_INSTRUCTION", "env instruction")
    monkeypatch.setenv("AGENT_TOOLS", "knowledge")
    monkeypatch.setenv("AGENT_MAX_ITERATIONS", "5")
    monkeypatch.setenv("AGENT_SPECIALISTS", "a")

    result = apply_env_overrides(AgentConfig(type="DIRECT"))

    assert result.model.name == "env-model"
    assert result.instructions.value == "env instruction"
    assert result.tools.enabled == ["knowledge"]
    assert result.execution.max_iterations == 5
    assert result.execution.specialists == ["a"]


def test_pattern_overrides_use_case_only_when_use_case_unset(monkeypatch, caplog):
    for var in _ALL_CONFIG_ENV_VARS:
        monkeypatch.delenv(var, raising=False)

    monkeypatch.setenv("AGENT_PATTERN", "sequential")
    result = apply_env_overrides(AgentConfig(type="DIRECT", use_case="assistant"))
    assert result.use_case == "pipeline"
    assert result.type == "SEQUENTIAL"
    assert "deprecated" in caplog.text

    monkeypatch.setenv("AGENT_USE_CASE", "expert_dispatch")
    result = apply_env_overrides(AgentConfig(type="DIRECT", use_case="assistant"))
    assert result.use_case == "expert_dispatch"


def test_specialists_roles_mismatch_raises(monkeypatch):
    for var in _ALL_CONFIG_ENV_VARS:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("AGENT_SPECIALISTS", "research,legal")
    config = AgentConfig(
        type="ROUTER",
        use_case="expert_dispatch",
        roles={"research": RoleConfig(), "risk": RoleConfig()},
    )

    with pytest.raises(ValueError) as error:
        apply_env_overrides(config)

    message = str(error.value)
    assert "legal" in message and "risk" in message


def test_specialists_roles_match_passes(monkeypatch):
    for var in _ALL_CONFIG_ENV_VARS:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("AGENT_SPECIALISTS", "risk,research")
    config = AgentConfig(
        type="ROUTER",
        use_case="expert_dispatch",
        roles={"research": RoleConfig(), "risk": RoleConfig()},
    )

    result = apply_env_overrides(config)

    assert set(result.execution.specialists) == {"research", "risk"}


def test_provenance_log_line(monkeypatch, base_config, caplog):
    caplog.set_level(logging.INFO, logger="basic_agent.config_loader")
    for var in _ALL_CONFIG_ENV_VARS:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("ADK_MODEL", "env-model")

    apply_env_overrides(base_config, config_path="/tmp/agent.yaml")

    assert (
        "config: yaml=/tmp/agent.yaml, use_case=assistant, env overrides: ADK_MODEL"
        in caplog.text
    )
