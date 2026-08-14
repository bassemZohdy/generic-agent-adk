"""Integration tests for the agent.py runtime config pipeline (T3.1)."""

from __future__ import annotations

import logging

import pytest
from google.adk.agents import LlmAgent

from basic_agent import agent as agent_module
from basic_agent.agent import resolve_agent_config

_CONFIG_ENV_VARS = (
    "AGENT_CONFIG_FILE",
    "AGENT_USE_CASE",
    "AGENT_PATTERN",
    "ADK_MODEL",
)


def test_yaml_file_is_loaded_and_env_overrides_apply(tmp_path, monkeypatch, caplog):
    config_file = tmp_path / "agent.yaml"
    config_file.write_text(
        """
agent:
  use_case: pipeline
  description: From YAML
model:
  provider: google
  name: yaml-model
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("AGENT_CONFIG_FILE", str(config_file))
    monkeypatch.setenv("ADK_MODEL", "env-model")
    caplog.set_level(logging.INFO, logger="basic_agent.config_loader")

    config = resolve_agent_config()

    assert config.use_case == "pipeline"
    assert config.description == "From YAML"
    assert config.model.name == "env-model"  # env wins over YAML
    assert "config: yaml=" in caplog.text
    assert "env overrides: ADK_MODEL" in caplog.text


def test_missing_explicit_config_file_fails_fast(monkeypatch):
    monkeypatch.setenv("AGENT_CONFIG_FILE", "/nonexistent/agent.yaml")

    with pytest.raises(FileNotFoundError):
        resolve_agent_config()


def test_env_only_use_case_flows_specialists_into_built_agent(monkeypatch):
    for var in _CONFIG_ENV_VARS:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("AGENT_USE_CASE", "expert_dispatch")

    config = resolve_agent_config()
    assert config.use_case == "expert_dispatch"

    built = agent_module._build_root_agent(config, "env")
    assert len(built.sub_agents) == 3
    assert {sub.name for sub in built.sub_agents} == {
        "router_specialist_research",
        "router_specialist_solution",
        "router_specialist_risk",
    }
    assert len({sub.instruction for sub in built.sub_agents}) == 3


def test_default_resolution_builds_assistant(monkeypatch):
    for var in _CONFIG_ENV_VARS:
        monkeypatch.delenv(var, raising=False)

    config = resolve_agent_config()
    assert config.use_case == "assistant"

    built = agent_module._build_root_agent(config, "env")
    assert isinstance(built, LlmAgent)
    assert built.name == "direct_agent"
    assert built.before_agent_callback is not None
    assert built.after_agent_callback is not None
