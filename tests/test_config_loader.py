"""Tests for configuration loader."""

import logging

import pytest

from basic_agent.config.loader import (
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
    "AGENT_CONFIG_FILE",
    "AGENT_USE_CASE",
    "ADK_MODEL",
    "AGENT_INSTRUCTION",
    "AGENT_TOOLS",
    "AGENT_MAX_ITERATIONS",
    "AGENT_SPECIALISTS",
)


def test_load_config_from_yaml_assistant_agent(tmp_path):
    config_file = tmp_path / "agent.yaml"
    config_file.write_text("""
agent:
  use_case: assistant
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

    assert config.use_case == "assistant"
    assert config.name == "test_agent"
    assert config.model.name == "gemini-2.0-flash"
    assert config.instructions.value == "Test instruction"
    assert "knowledge" in config.tools.enabled
    assert config.execution.max_iterations == 3


def test_load_config_from_yaml_expert_dispatch_agent(tmp_path):
    config_file = tmp_path / "agent.yaml"
    config_file.write_text("""
agent:
  use_case: expert_dispatch
  description: Expert dispatch agent

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

    assert config.use_case == "expert_dispatch"
    assert config.execution.specialists == ["research", "solution", "risk"]


def test_load_config_from_yaml_refine_agent(tmp_path):
    config_file = tmp_path / "agent.yaml"
    config_file.write_text("""
agent:
  use_case: refine_until_good
  description: Refine agent

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

    assert config.use_case == "refine_until_good"
    assert config.execution.max_iterations == 5


def test_load_config_substitutes_environment_variables(tmp_path, monkeypatch):
    monkeypatch.setenv("TEST_MODEL", "custom-model")
    monkeypatch.setenv("TEST_INSTRUCTION", "Custom instruction")

    config_file = tmp_path / "agent.yaml"
    config_file.write_text("""
agent:
  use_case: assistant

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
  use_case: assistant

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


def test_config_validation_rejects_missing_use_case():
    config = AgentConfig(use_case="", description="")

    with pytest.raises(ValueError, match="use_case is required"):
        config.validate()


def test_config_validation_is_structural_and_numeric():
    """The loader leaves use-case semantics to strategies but rejects bad counts."""
    configs = [
        AgentConfig(
            use_case="expert_dispatch",
            description="Test",
            execution=ExecutionConfig(specialists=[]),
        ),
        AgentConfig(
            use_case="approval_gate",
            description="Test",
            execution=ExecutionConfig(require_approval=False),
        ),
        AgentConfig(
            use_case="refine_until_good",
            description="Test",
            execution=ExecutionConfig(max_iterations=1),
        ),
    ]

    for config in configs:
        config.validate()  # strategy-specific checks still happen at build time

    with pytest.raises(ValueError, match="execution.max_iterations"):
        AgentConfig(
            use_case="refine_until_good",
            description="Test",
            execution=ExecutionConfig(max_iterations=0),
        ).validate()


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
  use_case: assistant
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
  use_case: assistant

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


def test_load_config_rejects_legacy_type_key(tmp_path):
    config_file = tmp_path / "agent.yaml"
    config_file.write_text("""
agent:
  type: DIRECT

model:
  provider: google
  name: gemini-2.0-flash

instructions:
  value: "Test"

tools:
  enabled: []

state:
  enabled: true
""")

    with pytest.raises(ValueError, match="Unknown agent field"):
        load_config_from_yaml(config_file)


@pytest.mark.parametrize(
    ("section", "value", "message"),
    [
        ("model", "[]", "model must be a mapping"),
        ("instructions", "[]", "instructions must be a mapping"),
        ("tools", "[]", "tools must be a mapping"),
        ("execution", "[]", "execution must be a mapping"),
        ("output", "[]", "output must be a mapping"),
        ("state", "[]", "state must be a mapping"),
        ("roles", "[]", "roles must be a mapping"),
    ],
)
def test_load_config_rejects_wrong_section_types(tmp_path, section, value, message):
    config_file = tmp_path / "agent.yaml"
    config_file.write_text(f"agent:\n  use_case: assistant\n{section}: {value}\n")

    with pytest.raises(ValueError, match=message):
        load_config_from_yaml(config_file)


def test_load_config_rejects_wrong_nested_section_types(tmp_path):
    config_file = tmp_path / "agent.yaml"
    config_file.write_text(
        """
agent:
  use_case: assistant
tools:
  mcp: []
execution:
  code_execution: []
"""
    )

    with pytest.raises(ValueError, match="tools.mcp must be a mapping"):
        load_config_from_yaml(config_file)


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
    monkeypatch.setenv("AGENT_USE_CASE", "expert_dispatch")

    config = load_config_from_env()

    assert config.use_case == "expert_dispatch"


def test_env_builder_defaults(monkeypatch):
    for var in _ALL_CONFIG_ENV_VARS:
        monkeypatch.delenv(var, raising=False)

    config = load_config_from_env()

    assert config.use_case == "assistant"
    assert config.execution.max_iterations == 3
    assert config.execution.specialists == ["research", "solution", "risk"]


def test_env_builder_execution_overrides(monkeypatch):
    for var in _ALL_CONFIG_ENV_VARS:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("AGENT_MAX_ITERATIONS", "7")
    monkeypatch.setenv("AGENT_SPECIALISTS", "alpha, beta")

    config = load_config_from_env()

    assert config.execution.max_iterations == 7
    assert config.execution.specialists == ["alpha", "beta"]


@pytest.fixture
def base_config():
    return AgentConfig(
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
        assert result.use_case == expected_value
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


def test_apply_env_overrides_respects_explicit_empty_tools(monkeypatch, base_config):
    for var in _ALL_CONFIG_ENV_VARS:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("AGENT_TOOLS", "")

    assert apply_env_overrides(base_config).tools.enabled == []


def test_apply_env_overrides_creates_missing_subconfigs(monkeypatch):
    for var in _ALL_CONFIG_ENV_VARS:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("ADK_MODEL", "env-model")
    monkeypatch.setenv("AGENT_INSTRUCTION", "env instruction")
    monkeypatch.setenv("AGENT_TOOLS", "knowledge")
    monkeypatch.setenv("AGENT_MAX_ITERATIONS", "5")
    monkeypatch.setenv("AGENT_SPECIALISTS", "a")

    result = apply_env_overrides(AgentConfig(use_case="assistant"))

    assert result.model.name == "env-model"
    assert result.instructions.value == "env instruction"
    assert result.tools.enabled == ["knowledge"]
    assert result.execution.max_iterations == 5
    assert result.execution.specialists == ["a"]


def test_apply_env_overrides_ignores_deprecated_pattern_vars(monkeypatch, base_config):
    for var in _ALL_CONFIG_ENV_VARS:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("AGENT_PATTERN", "sequential")
    monkeypatch.setenv("AGENT_PATTERN_MAX_ITERATIONS", "9")
    monkeypatch.setenv("AGENT_PATTERN_SPECIALISTS", "x, y")

    result = apply_env_overrides(base_config)

    assert result.use_case == "assistant"
    assert result.execution.max_iterations == 3
    assert result.execution.specialists == ["x"]


def test_specialists_roles_mismatch_raises(monkeypatch):
    for var in _ALL_CONFIG_ENV_VARS:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("AGENT_SPECIALISTS", "research,legal")
    config = AgentConfig(
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
        use_case="expert_dispatch",
        roles={"research": RoleConfig(), "risk": RoleConfig()},
    )

    result = apply_env_overrides(config)

    assert set(result.execution.specialists) == {"research", "risk"}


def test_provenance_log_line(monkeypatch, base_config, caplog):
    caplog.set_level(logging.INFO, logger="basic_agent.config.loader")
    for var in _ALL_CONFIG_ENV_VARS:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("ADK_MODEL", "env-model")

    apply_env_overrides(base_config, config_path="/tmp/agent.yaml")

    assert (
        "config: yaml=/tmp/agent.yaml, use_case=assistant, env overrides: ADK_MODEL"
        in caplog.text
    )


# ── P5: execution.code_execution plumbing ────────────────────────────────────


def test_load_config_with_code_execution_configuration(tmp_path):
    config_file = tmp_path / "agent.yaml"
    config_file.write_text("""
agent:
  use_case: assistant

model:
  provider: google
  name: gemini-2.0-flash

execution:
  max_iterations: 4
  code_execution:
    strategy: docker_container
    docker_host: tcp://code-exec-socket-proxy:2375
    docker_image: python:3.13-slim
    vertex_resource: projects/p/locations/us-central1/extensions/e
    agent_engine_resource: projects/p/locations/us-central1/reasoningEngines/r
    gke_kubeconfig_path: /etc/sandbox/kubeconfig
    gke_kubeconfig_context: sandbox-ctx
""")
    config = load_config_from_yaml(config_file)

    ce = config.execution.code_execution
    assert ce is not None
    assert ce.strategy == "docker_container"
    assert ce.docker_host == "tcp://code-exec-socket-proxy:2375"
    assert ce.docker_image == "python:3.13-slim"
    assert ce.vertex_resource == "projects/p/locations/us-central1/extensions/e"
    assert (
        ce.agent_engine_resource
        == "projects/p/locations/us-central1/reasoningEngines/r"
    )
    assert ce.gke_kubeconfig_path == "/etc/sandbox/kubeconfig"
    assert ce.gke_kubeconfig_context == "sandbox-ctx"


def test_yaml_execution_without_code_execution_keeps_none(tmp_path):
    config_file = tmp_path / "agent.yaml"
    config_file.write_text("""
agent:
  use_case: assistant

model:
  provider: google
  name: gemini-2.0-flash

execution:
  max_iterations: 3
""")
    config = load_config_from_yaml(config_file)

    assert config.execution.code_execution is None


def test_env_builder_code_execution_defaults(monkeypatch):
    from basic_agent.config.loader import ExecutionCodeExecutionConfig

    config = load_config_from_env()

    ce = config.execution.code_execution
    assert isinstance(ce, ExecutionCodeExecutionConfig)
    assert ce.strategy == ""
    assert ce.docker_host == ""
    assert ce.docker_image == ""
    assert ce.vertex_resource == ""
    assert ce.agent_engine_resource == ""
    assert ce.gke_kubeconfig_path == ""
    assert ce.gke_kubeconfig_context == ""


def test_env_builder_code_execution_from_settings(settings_patch):
    import sys

    settings_mod = sys.modules["basic_agent.config.settings"]

    settings_patch(
        settings_mod,
        code_execution_strategy="gemini_built_in",
        code_execution_docker_host="tcp://proxy:2375",
        code_execution_docker_image="python:3.13-alpine",
        code_execution_vertex_resource="projects/p/locations/l/extensions/x",
        code_execution_agent_engine_resource="projects/p/locations/l/reasoningEngines/y",
        code_execution_gke_kubeconfig_path="/kube/config",
        code_execution_gke_kubeconfig_context="ctx-1",
    )

    config = load_config_from_env()

    ce = config.execution.code_execution
    assert ce.strategy == "gemini_built_in"
    assert ce.docker_host == "tcp://proxy:2375"
    assert ce.docker_image == "python:3.13-alpine"
    assert ce.vertex_resource == "projects/p/locations/l/extensions/x"
    assert ce.agent_engine_resource == "projects/p/locations/l/reasoningEngines/y"
    assert ce.gke_kubeconfig_path == "/kube/config"
    assert ce.gke_kubeconfig_context == "ctx-1"
