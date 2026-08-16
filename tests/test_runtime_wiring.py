"""Integration tests for the agent.py runtime config pipeline (T3.1)."""

from __future__ import annotations

import logging

import pytest
from google.adk.agents import LlmAgent
from google.adk.models.lite_llm import LiteLlm

from basic_agent import agent as agent_module
from basic_agent.agent import resolve_agent_config
from fakes import FakeDockerClient, install_fake_docker

_CONFIG_ENV_VARS = (
    "AGENT_CONFIG_FILE",
    "AGENT_USE_CASE",
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


def test_yaml_litellm_provider_builds_litellm_root_agent(tmp_path, monkeypatch):
    config_file = tmp_path / "agent.yaml"
    config_file.write_text(
        """
agent:
  use_case: assistant
model:
  provider: openai
  name: gpt-4o
  api_key: "${OPENAI_API_KEY:sk-test}"
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("AGENT_CONFIG_FILE", str(config_file))
    monkeypatch.delenv("ADK_MODEL", raising=False)

    config = resolve_agent_config()
    built = agent_module._build_root_agent(config, "yaml")

    assert isinstance(built, LlmAgent)
    assert isinstance(built.model, LiteLlm)
    assert built.model.model == "openai/gpt-4o"


def test_yaml_skills_tool_loads_configured_skill_directory(tmp_path, monkeypatch):
    skills_root = tmp_path / "skills"
    skill_dir = skills_root / "demo-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: demo-skill\ndescription: A demo skill for tests.\n---\n\nFollow these steps.",
        encoding="utf-8",
    )
    config_file = tmp_path / "agent.yaml"
    config_file.write_text(
        f"""
agent:
  use_case: assistant
tools:
  enabled: [skills]
  skills:
    dir: "{skills_root}"
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("AGENT_CONFIG_FILE", str(config_file))

    config = resolve_agent_config()
    runtime = agent_module._build_runtime_context(config)

    from google.adk.tools.skill_toolset import SkillToolset

    skill_toolsets = [t for t in runtime.tools if isinstance(t, SkillToolset)]
    assert len(skill_toolsets) == 1
    assert [s.name for s in skill_toolsets[0].skills] == ["demo-skill"]


# ── P6: code-execution resolution wired into _build_runtime_context ─────────

import asyncio
import json
import sys
import types
from types import SimpleNamespace

from basic_agent.autoconfig import ProviderConfigurationError
from basic_agent.code_execution import CodeExecutionResolution
from basic_agent.config_loader import (
    AgentConfig,
    ExecutionConfig,
    ExecutionCodeExecutionConfig,
    InstructionsConfig,
    ModelConfig,
    ToolsConfig,
)

_CODE_EXEC_ENV_VARS = (
    "AGENT_CODE_EXECUTION_STRATEGY",
    "AGENT_CODE_EXECUTION_DOCKER_HOST",
    "AGENT_CODE_EXECUTION_DOCKER_IMAGE",
    "AGENT_CODE_EXECUTION_VERTEX_RESOURCE",
    "AGENT_CODE_EXECUTION_AGENT_ENGINE_RESOURCE",
    "AGENT_CODE_EXECUTION_GKE_KUBECONFIG_PATH",
    "AGENT_CODE_EXECUTION_GKE_KUBECONFIG_CONTEXT",
)


def _ce_config(model_name: str = "gemini-3.6-flash", tools=("code_execution",),
               code_execution: ExecutionCodeExecutionConfig | None = None):
    return AgentConfig(
        use_case="assistant",
        model=ModelConfig(provider="google", name=model_name),
        instructions=InstructionsConfig(value="Operator instruction."),
        tools=ToolsConfig(enabled=list(tools)),
        execution=ExecutionConfig(code_execution=code_execution),
    )


@pytest.fixture
def clean_code_exec_env(monkeypatch):
    for var in _CODE_EXEC_ENV_VARS:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(agent_module, "_code_execution_resolution", None)


def test_runtime_context_resolves_docker_strategy(monkeypatch, clean_code_exec_env):
    client = install_fake_docker(monkeypatch, FakeDockerClient())
    runtime = agent_module._build_runtime_context(_ce_config())

    assert runtime.code_execution_strategy == "docker_container"
    assert runtime.code_executor is not None
    assert "isolated sandbox (`docker_container`)" in runtime.instruction


def test_runtime_context_unavailable_tells_the_model(monkeypatch, clean_code_exec_env):
    monkeypatch.setitem(sys.modules, "docker", None)
    runtime = agent_module._build_runtime_context(
        _ce_config(model_name="gemini-1.5-flash")
    )

    assert runtime.code_execution_strategy == "unavailable"
    assert runtime.code_executor is None
    assert "do not claim to execute code" in runtime.instruction


def test_runtime_context_falls_back_to_gemini_builtin(monkeypatch, clean_code_exec_env):
    from google.adk.code_executors import BuiltInCodeExecutor

    monkeypatch.setitem(sys.modules, "docker", None)
    runtime = agent_module._build_runtime_context(_ce_config())

    assert runtime.code_execution_strategy == "gemini_built_in"
    assert isinstance(runtime.code_executor, BuiltInCodeExecutor)
    assert "isolated sandbox (`gemini_built_in`)" in runtime.instruction


def test_runtime_context_explicit_override_from_env(monkeypatch, clean_code_exec_env):
    monkeypatch.setitem(sys.modules, "docker", None)
    monkeypatch.setenv("AGENT_CODE_EXECUTION_STRATEGY", "unsafe_local")
    runtime = agent_module._build_runtime_context(_ce_config())

    assert runtime.code_execution_strategy == "unsafe_local"
    assert "IN-PROCESS" in runtime.instruction and "NO isolation" in runtime.instruction


def test_runtime_context_broken_override_raises(monkeypatch, clean_code_exec_env):
    monkeypatch.setitem(sys.modules, "docker", None)
    monkeypatch.setenv("AGENT_CODE_EXECUTION_STRATEGY", "docker_container")
    with pytest.raises(ProviderConfigurationError, match="docker_container"):
        agent_module._build_runtime_context(_ce_config())


def test_runtime_context_yaml_overlay_reaches_resolver(monkeypatch, clean_code_exec_env):
    monkeypatch.setitem(sys.modules, "docker", None)
    runtime = agent_module._build_runtime_context(
        _ce_config(
            code_execution=ExecutionCodeExecutionConfig(strategy="gemini_built_in")
        )
    )

    assert runtime.code_execution_strategy == "gemini_built_in"


def test_runtime_context_without_tool_skips_resolution(monkeypatch, clean_code_exec_env):
    client = FakeDockerClient()
    install_fake_docker(monkeypatch, client)
    runtime = agent_module._build_runtime_context(
        _ce_config(tools=("knowledge",), model_name="gemini-2.0-flash")
    )

    assert runtime.code_execution_strategy is None
    assert runtime.code_executor is None
    assert "sandbox" not in runtime.instruction
    assert client.constructor_kwargs == []


def test_inspect_runtime_reports_code_execution_strategy(monkeypatch, clean_code_exec_env):
    monkeypatch.setattr(
        agent_module,
        "_code_execution_resolution",
        CodeExecutionResolution(executor=None, strategy="unavailable", detail="test"),
    )
    payload = json.loads(agent_module.inspect_runtime())
    assert payload["capabilities"]["code_execution"] == "unavailable"

    monkeypatch.setattr(agent_module, "_code_execution_resolution", None)
    payload = json.loads(agent_module.inspect_runtime())
    assert "code_execution" not in payload["capabilities"]


def test_plugin_span_carries_code_execution_strategy(monkeypatch, clean_code_exec_env):
    class _RecordingSpan:
        def __init__(self, attributes):
            self.attributes = dict(attributes)

        def set_attribute(self, key, value):
            self.attributes[key] = value

        def end(self):
            pass

    spans: list[_RecordingSpan] = []

    class _RecordingTracer:
        def start_span(self, name, attributes=None):
            span = _RecordingSpan(attributes or {})
            spans.append(span)
            return span

    monkeypatch.setattr(agent_module, "tracer", _RecordingTracer())
    plugin = agent_module.GenericAgentPlugin()
    monkeypatch.setattr(
        agent_module,
        "_code_execution_resolution",
        CodeExecutionResolution(executor=object(), strategy="docker_container", detail="t"),
    )
    context = SimpleNamespace(invocation_id="inv-1", app_name="basic_agent")

    asyncio.run(plugin.before_run_callback(invocation_context=context))

    attr = spans[0].attributes.get("adk.capabilities", "")
    assert "code_execution:docker_container" in attr
    plugin._spans.clear()


def test_yaml_code_execution_overlay_reaches_docker_client(monkeypatch, clean_code_exec_env):
    """docker_host + docker_image from execution.code_execution flow through
    the resolver into the DockerClient constructor and containers.run."""
    client = FakeDockerClient()
    install_fake_docker(monkeypatch, client)
    runtime = agent_module._build_runtime_context(
        _ce_config(
            code_execution=ExecutionCodeExecutionConfig(
                docker_host="tcp://from-yaml:2375",
                docker_image="python:3.13-alpine",
            )
        )
    )

    assert runtime.code_execution_strategy == "docker_container"
    # Two client constructions by design: probe (timeout=1) then build
    # (executor default) — both must carry the YAML-configured host.
    assert client.constructor_kwargs == [
        {"base_url": "tcp://from-yaml:2375", "timeout": 1},
        {"base_url": "tcp://from-yaml:2375"},
    ]
    assert client.run_calls[0]["image"] == "python:3.13-alpine"


def test_yaml_strategy_is_overridden_by_env(monkeypatch, clean_code_exec_env):
    """Env var wins over YAML when both pin a strategy (overlay ordering)."""
    monkeypatch.setitem(sys.modules, "docker", None)
    monkeypatch.setenv("AGENT_CODE_EXECUTION_STRATEGY", "gemini_built_in")
    runtime = agent_module._build_runtime_context(
        _ce_config(
            model_name="gemini-2.0-flash",
            code_execution=ExecutionCodeExecutionConfig(strategy="docker_container"),
        )
    )
    assert runtime.code_execution_strategy == "gemini_built_in"


def test_rebuild_without_tool_resets_resolution_stash(monkeypatch, clean_code_exec_env):
    """A second build without code_execution must not leak the previous
    resolution into inspect_runtime()/spans."""
    install_fake_docker(monkeypatch, FakeDockerClient())
    with_res = agent_module._build_runtime_context(_ce_config())
    assert with_res.code_execution_strategy == "docker_container"
    assert "code_execution" in json.loads(agent_module.inspect_runtime())["capabilities"]

    without_res = agent_module._build_runtime_context(
        _ce_config(tools=("knowledge",), model_name="gemini-2.0-flash")
    )
    assert without_res.code_execution_strategy is None
    assert agent_module._code_execution_resolution is None
    assert "code_execution" not in json.loads(agent_module.inspect_runtime())["capabilities"]
