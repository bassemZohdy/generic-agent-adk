"""Tests for configuration loader."""

import os
import pytest
import tempfile
from pathlib import Path

from basic_agent.config_loader import (
    AgentConfig,
    ExecutionConfig,
    load_config_from_yaml,
    ModelConfig,
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

    assert config.type == "LOOP"
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


def test_config_validation_rejects_router_without_specialists():
    config = AgentConfig(
        type="ROUTER",
        description="Test",
        execution=ExecutionConfig(specialists=[]),
    )

    with pytest.raises(ValueError, match="ROUTER"):
        config.validate()


def test_config_validation_rejects_human_in_loop_without_approval():
    config = AgentConfig(
        type="HUMAN_IN_LOOP",
        description="Test",
        execution=ExecutionConfig(require_approval=False),
    )

    with pytest.raises(ValueError, match="HUMAN_IN_LOOP"):
        config.validate()


def test_config_validation_rejects_loop_with_zero_iterations():
    config = AgentConfig(
        type="LOOP",
        description="Test",
        execution=ExecutionConfig(max_iterations=0),
    )

    with pytest.raises(ValueError, match="max_iterations"):
        config.validate()


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
