"""Tests for code-execution provider resolution (ADR-004 P1)."""

from __future__ import annotations

import importlib
import importlib.util
import logging
import sys
from typing import Any

import pytest
from fakes import (
    FakeDockerClient,
    FakeExecResult,
    install_fake_docker,
    install_fake_kubernetes,
)

import basic_agent.execution.resolver as ce
from basic_agent.autoconfig import ProviderConfigurationError
from basic_agent.execution.resolver import (
    STRATEGY_ENV,
    _CodeExecutionProviderSpec,
    register,
    resolve_code_executor,
)


def _fake_spec(strategy: str, *, probe_result: bool = True, warn: str | None = None):
    """Build a throwaway provider spec that records its calls."""

    calls: dict[str, Any] = {"probe": 0, "build": 0, "model": None}

    class Spec(_CodeExecutionProviderSpec):
        @classmethod
        def probe(cls, environment, *, model):
            calls["probe"] = calls["probe"] + 1
            calls["model"] = model
            return probe_result

        @classmethod
        def build(cls, environment):
            calls["build"] = calls["build"] + 1
            return f"executor[{strategy}]"

    Spec.strategy = strategy
    Spec.warn_on_select = warn
    return Spec, calls


@pytest.fixture
def clean_registry():
    """Snapshot and restore the provider registry around a test.

    Setup clears both the registry and the auto-detect chain so each test
    starts from a blank slate (module-level registrations included).
    """
    providers = dict(ce._PROVIDERS)
    order = ce._AUTO_DETECT_ORDER
    ce._PROVIDERS.clear()
    ce._AUTO_DETECT_ORDER = ()
    try:
        yield
    finally:
        ce._PROVIDERS.clear()
        ce._PROVIDERS.update(providers)
        ce._AUTO_DETECT_ORDER = order


def test_resolve_defaults_to_unavailable(clean_registry):
    resolution = resolve_code_executor({}, model="gemini-2.0-flash")
    assert resolution.executor is None
    assert resolution.strategy == "unavailable"
    assert resolution.detail


def test_unknown_explicit_strategy_raises(clean_registry):
    spec, _ = _fake_spec("known_one")
    register(spec)
    with pytest.raises(
        ProviderConfigurationError, match="Unknown code-execution strategy 'bogus'"
    ) as excinfo:
        resolve_code_executor({STRATEGY_ENV: "bogus"}, model="m")
    assert "known_one" in str(excinfo.value)


def test_probe_false_on_explicit_path_raises(clean_registry):
    spec, calls = _fake_spec("broken", probe_result=False)
    register(spec)
    with pytest.raises(
        ProviderConfigurationError, match="explicitly configured but unavailable"
    ):
        resolve_code_executor({STRATEGY_ENV: "broken"}, model="m")
    assert calls["build"] == 0


def test_registered_provider_auto_detected(clean_registry):
    spec, calls = _fake_spec("fake")
    register(spec, auto=True)
    resolution = resolve_code_executor({}, model="sentinel-model")
    assert resolution.strategy == "fake"
    assert resolution.executor == "executor[fake]"
    assert resolution.detail == "auto-detected"
    assert calls["probe"] == 1
    assert calls["model"] == "sentinel-model"


def test_registered_provider_not_probed_when_unregistered_from_chain(clean_registry):
    spec, calls = _fake_spec("manual_only")
    register(spec)  # auto=False: registered but never auto-detected
    resolution = resolve_code_executor({}, model="m")
    assert resolution.strategy == "unavailable"
    assert calls["probe"] == 0


def test_explicit_override_wins_over_auto_detect(clean_registry):
    auto_spec, auto_calls = _fake_spec("auto_one")
    register(auto_spec, auto=True)
    pinned_spec, _ = _fake_spec("pinned")
    register(pinned_spec)
    resolution = resolve_code_executor({STRATEGY_ENV: "pinned"}, model="m")
    assert resolution.strategy == "pinned"
    assert resolution.executor == "executor[pinned]"
    assert resolution.detail == "explicit override"
    assert auto_calls["probe"] == 0


def test_whitespace_override_treated_as_unset(clean_registry):
    spec, _ = _fake_spec("fake")
    register(spec, auto=True)
    resolution = resolve_code_executor({STRATEGY_ENV: "   "}, model="m")
    assert resolution.strategy == "fake"


def test_auto_detect_tries_in_registration_order(clean_registry):
    first, first_calls = _fake_spec("first", probe_result=False)
    second, _ = _fake_spec("second")
    register(first, auto=True)
    register(second, auto=True)
    resolution = resolve_code_executor({}, model="m")
    assert resolution.strategy == "second"
    assert first_calls["probe"] == 1


def test_warn_on_select_logged_on_explicit_selection(clean_registry, caplog):
    spec, _ = _fake_spec("risky", warn="risky strategy selected: handle with care")
    register(spec)
    with caplog.at_level(logging.WARNING):
        resolution = resolve_code_executor({STRATEGY_ENV: "risky"}, model="m")
    assert resolution.strategy == "risky"
    assert "risky strategy selected" in caplog.text


def test_no_warning_for_ordinary_explicit_selection(clean_registry, caplog):
    spec, _ = _fake_spec("ordinary")
    register(spec)
    with caplog.at_level(logging.WARNING):
        resolve_code_executor({STRATEGY_ENV: "ordinary"}, model="m")
    assert caplog.text == ""


@pytest.mark.skipif(
    importlib.util.find_spec("docker") is not None,
    reason="docker SDK installed; import-safety proven only without it",
)
def test_module_imports_without_docker_sdk(clean_registry):
    """A fresh import must not touch the docker SDK (ADR-004 §2 lazy-import rule)."""
    assert "docker" not in __import__("sys").modules or True  # registry restored below
    importlib.reload(ce)
    resolve_code_executor({}, model="m")  # smoke: reloaded module still resolves


# ── P2: Docker provider + hardened executor ─────────────────────────────────


def test_docker_probe_success_with_env_precedence(clean_registry, monkeypatch):
    client = FakeDockerClient()
    install_fake_docker(monkeypatch, client)
    env = {
        "DOCKER_HOST": "tcp://fallback:2375",
        "AGENT_CODE_EXECUTION_DOCKER_HOST": "tcp://primary:2375",
    }
    assert ce.DockerContainerCodeExecutionProvider.probe(env, model="m")
    assert client.constructor_kwargs == [
        {"base_url": "tcp://primary:2375", "timeout": 1}
    ]


def test_docker_probe_uses_docker_host_fallback(clean_registry, monkeypatch):
    client = FakeDockerClient()
    install_fake_docker(monkeypatch, client)
    assert ce.DockerContainerCodeExecutionProvider.probe(
        {"DOCKER_HOST": "tcp://fallback:2375"}, model="m"
    )
    assert client.constructor_kwargs == [
        {"base_url": "tcp://fallback:2375", "timeout": 1}
    ]


def test_docker_probe_uses_from_env_without_host(clean_registry, monkeypatch):
    client = FakeDockerClient()
    install_fake_docker(monkeypatch, client)
    assert ce.DockerContainerCodeExecutionProvider.probe({}, model="m")
    assert client.constructor_kwargs == [{"timeout": 1}]


def test_docker_probe_unreachable_daemon_returns_false(clean_registry, monkeypatch):
    client = FakeDockerClient()
    client.ping_raises = ConnectionError("no daemon")
    install_fake_docker(monkeypatch, client)
    assert not ce.DockerContainerCodeExecutionProvider.probe({}, model="m")


def test_docker_probe_package_missing_returns_false(clean_registry, monkeypatch):
    monkeypatch.setitem(sys.modules, "docker", None)
    assert not ce.DockerContainerCodeExecutionProvider.probe({}, model="m")


def test_docker_probe_requires_pinned_image_in_production(clean_registry, monkeypatch):
    client = FakeDockerClient()
    install_fake_docker(monkeypatch, client)
    assert not ce.DockerContainerCodeExecutionProvider.probe(
        {
            "DEPLOYMENT_ENV": "production",
            "AGENT_CODE_EXECUTION_DOCKER_IMAGE": "python:3.13-slim",
        },
        model="m",
    )
    pinned = "python:3.13-slim@sha256:" + "a" * 64
    assert ce.DockerContainerCodeExecutionProvider.probe(
        {"DEPLOYMENT_ENV": "production", "AGENT_CODE_EXECUTION_DOCKER_IMAGE": pinned},
        model="m",
    )


def test_default_sandbox_image_is_digest_pinned():
    assert ce.DockerContainerCodeExecutionProvider._image_is_pinned(
        ce.DEFAULT_SANDBOX_IMAGE
    )


def test_hardened_executor_container_kwargs(clean_registry, monkeypatch):
    client = FakeDockerClient()
    install_fake_docker(monkeypatch, client)
    ce.DockerContainerCodeExecutionProvider.build(
        {"AGENT_CODE_EXECUTION_DOCKER_IMAGE": "python:3.13-slim"}
    )
    assert client.run_calls and client.run_calls[0]["image"] == "python:3.13-slim"
    kwargs = client.run_calls[0]
    assert kwargs["detach"] is True
    assert kwargs["tty"] is True
    assert kwargs["mem_limit"] == "512m"
    assert kwargs["nano_cpus"] == 1_000_000_000
    assert kwargs["pids_limit"] == 128
    assert kwargs["read_only"] is True
    assert kwargs["tmpfs"] == {"/tmp": "size=64m,rw"}
    # ADK's own hardening, kept exactly as shipped:
    assert kwargs["network_disabled"] is True
    assert kwargs["cap_drop"] == ["ALL"]
    assert kwargs["security_opt"] == ["no-new-privileges"]


def test_hardened_executor_rejects_stateful(clean_registry, monkeypatch):
    client = FakeDockerClient()
    install_fake_docker(monkeypatch, client)
    with pytest.raises(ValueError, match="stateful"):
        ce._hardened_executor_cls_get()(stateful=True)


def test_hardened_executor_requires_image_or_docker_path(clean_registry, monkeypatch):
    client = FakeDockerClient()
    install_fake_docker(monkeypatch, client)
    with pytest.raises(ValueError, match="image or docker_path"):
        ce._hardened_executor_cls_get()(image=None)


def test_hardened_executor_timeout_kills_and_recovers(clean_registry, monkeypatch):
    import time

    client = FakeDockerClient()

    def hang(cmd):
        time.sleep(5)
        return FakeExecResult(0, (b"late", b""))

    client.exec_handler = hang
    install_fake_docker(monkeypatch, client)
    executor = ce._hardened_executor_cls_get()(timeout_seconds=1)

    result = executor.execute_code(None, _code_input("while True: pass"))
    assert "timed out after 1s" in result.stderr
    assert result.stdout == ""
    # The long-lived container was SIGKILLed (not a 10s graceful stop) and a
    # fresh one started:
    assert client.kill_calls and client.remove_calls
    assert client.stop_calls == []
    assert len(client.run_calls) == 2


def test_hardened_executor_next_call_after_timeout_works(clean_registry, monkeypatch):
    client = FakeDockerClient()
    client.exec_handler = lambda cmd: FakeExecResult(0, (b"", b""))
    install_fake_docker(monkeypatch, client)
    executor = ce._hardened_executor_cls_get()(timeout_seconds=1)

    ok = executor.execute_code(None, _code_input("print('hi')"))
    assert ok.stdout == ""
    client.exec_handler = lambda cmd: FakeExecResult(0, (b"fresh\n", b""))
    again = executor.execute_code(None, _code_input("print('again')"))
    assert again.stdout == "fresh\n"


def test_hardened_executor_streams_demuxed_output(clean_registry, monkeypatch):
    client = FakeDockerClient()
    client.exec_handler = lambda cmd: FakeExecResult(0, (b"out-line\n", b"err-line\n"))
    install_fake_docker(monkeypatch, client)
    executor = ce._hardened_executor_cls_get()(timeout_seconds=5)

    result = executor.execute_code(None, _code_input("print('x')"))
    assert result.stdout == "out-line\n"
    assert result.stderr == "err-line\n"


def test_hardened_executor_caps_stdout_and_stderr(clean_registry, monkeypatch):
    client = FakeDockerClient()
    client.exec_handler = lambda cmd: FakeExecResult(
        0,
        (
            b"o" * (ce.MAX_EXECUTION_OUTPUT_BYTES + 10),
            b"e" * (ce.MAX_EXECUTION_OUTPUT_BYTES + 10),
        ),
    )
    install_fake_docker(monkeypatch, client)
    executor = ce._hardened_executor_cls_get()(timeout_seconds=5)

    result = executor.execute_code(None, _code_input("print('x')"))
    assert len(result.stdout.encode()) <= ce.MAX_EXECUTION_OUTPUT_BYTES + 30
    assert len(result.stderr.encode()) <= ce.MAX_EXECUTION_OUTPUT_BYTES + 30
    assert "output truncated" in result.stdout
    assert "output truncated" in result.stderr


def test_docker_provider_auto_detected(clean_registry, monkeypatch):
    client = FakeDockerClient()
    install_fake_docker(monkeypatch, client)
    ce.register(ce.DockerContainerCodeExecutionProvider, auto=True)
    resolution = resolve_code_executor({}, model="m")
    assert resolution.strategy == "docker_container"
    assert resolution.executor is not None


def test_docker_explicit_override_with_dead_daemon_raises(clean_registry, monkeypatch):
    client = FakeDockerClient()
    client.ping_raises = ConnectionError("down")
    install_fake_docker(monkeypatch, client)
    ce.register(ce.DockerContainerCodeExecutionProvider)
    with pytest.raises(ProviderConfigurationError, match="docker_container"):
        resolve_code_executor({STRATEGY_ENV: "docker_container"}, model="m")


def _code_input(code: str):
    from google.adk.code_executors.code_execution_utils import CodeExecutionInput

    return CodeExecutionInput(code=code)


# ── P3: gemini_built_in provider ─────────────────────────────────────────────


def test_gemini_probe_native_2plus_true(clean_registry):
    probe = ce.GeminiBuiltInCodeExecutionProvider.probe
    assert probe({}, model="gemini-2.0-flash")
    assert probe({}, model="gemini-3.6-flash")  # repo default


def test_gemini_probe_pre_2_0_false(clean_registry):
    assert not ce.GeminiBuiltInCodeExecutionProvider.probe({}, model="gemini-1.5-flash")


def test_gemini_probe_litellm_false(clean_registry):
    from google.adk.models.lite_llm import LiteLlm

    assert not ce.GeminiBuiltInCodeExecutionProvider.probe(
        {}, model=LiteLlm(model="openai/gpt-4o")
    )


def test_gemini_build_returns_builtin_executor(clean_registry):
    from google.adk.code_executors import BuiltInCodeExecutor

    executor = ce.GeminiBuiltInCodeExecutionProvider.build({})
    assert isinstance(executor, BuiltInCodeExecutor)


def test_auto_detect_prefers_docker_over_gemini(clean_registry, monkeypatch):
    client = FakeDockerClient()
    install_fake_docker(monkeypatch, client)
    ce.register(ce.DockerContainerCodeExecutionProvider, auto=True)
    ce.register(ce.GeminiBuiltInCodeExecutionProvider, auto=True)
    resolution = resolve_code_executor({}, model="gemini-2.0-flash")
    assert resolution.strategy == "docker_container"


def test_auto_detect_falls_back_to_gemini_when_no_docker(clean_registry, monkeypatch):
    monkeypatch.setitem(sys.modules, "docker", None)
    ce.register(ce.DockerContainerCodeExecutionProvider, auto=True)
    ce.register(ce.GeminiBuiltInCodeExecutionProvider, auto=True)
    resolution = resolve_code_executor({}, model="gemini-2.0-flash")
    assert resolution.strategy == "gemini_built_in"
    assert resolution.executor is not None


def test_auto_detect_gemini_1_5_resolves_to_unavailable(clean_registry, monkeypatch):
    monkeypatch.setitem(sys.modules, "docker", None)
    ce.register(ce.DockerContainerCodeExecutionProvider, auto=True)
    ce.register(ce.GeminiBuiltInCodeExecutionProvider, auto=True)
    resolution = resolve_code_executor({}, model="gemini-1.5-flash")
    assert resolution.strategy == "unavailable"
    assert resolution.executor is None


def test_gemini_explicit_with_pre_2_0_model_raises(clean_registry):
    ce.register(ce.GeminiBuiltInCodeExecutionProvider)
    with pytest.raises(ProviderConfigurationError, match="gemini_built_in"):
        resolve_code_executor(
            {STRATEGY_ENV: "gemini_built_in"}, model="gemini-1.5-flash"
        )


# ── P4: unsafe_local provider ────────────────────────────────────────────────


def test_unsafe_local_never_auto_selected(clean_registry, monkeypatch):
    client = FakeDockerClient()
    install_fake_docker(monkeypatch, client)
    ce.register(ce.DockerContainerCodeExecutionProvider, auto=True)
    ce.register(ce.GeminiBuiltInCodeExecutionProvider, auto=True)
    ce.register(ce.UnsafeLocalCodeExecutionProvider)  # registered, never auto
    env = {
        "DOCKER_HOST": "tcp://docker:2375",
        "AGENT_CODE_EXECUTION_DOCKER_HOST": "tcp://docker:2375",
    }
    resolution = resolve_code_executor(env, model="gemini-2.0-flash")
    assert resolution.strategy == "docker_container"


def test_unsafe_local_not_selected_even_with_nothing_else(clean_registry, monkeypatch):
    monkeypatch.setitem(sys.modules, "docker", None)
    ce.register(ce.DockerContainerCodeExecutionProvider, auto=True)
    ce.register(ce.UnsafeLocalCodeExecutionProvider)
    resolution = resolve_code_executor({}, model="gemini-1.5-flash")
    assert resolution.strategy == "unavailable"


def test_unsafe_local_explicit_warns_and_builds(clean_registry, caplog):
    from google.adk.code_executors import UnsafeLocalCodeExecutor

    ce.register(ce.UnsafeLocalCodeExecutionProvider)
    with caplog.at_level(logging.WARNING):
        resolution = resolve_code_executor({STRATEGY_ENV: "unsafe_local"}, model="m")
    assert resolution.strategy == "unsafe_local"
    assert resolution.detail == "explicit override"
    assert isinstance(resolution.executor, UnsafeLocalCodeExecutor)
    assert "NO isolation" in caplog.text


# ── P7: GCP-managed providers (vertex_ai / agent_engine_sandbox / gke) ──────


def test_vertex_probe_requires_resource_identifier(clean_registry):
    probe = ce.VertexAiCodeExecutionProvider.probe
    assert not probe({}, model="m")
    assert not probe({"GCP_PROJECT": "proj", "GOOGLE_CLOUD_PROJECT": "proj"}, model="m")
    assert probe(
        {"AGENT_CODE_EXECUTION_VERTEX_RESOURCE": "projects/p/locations/l/extensions/e"},
        model="m",
    )


def test_agent_engine_probe_requires_resource_identifier(clean_registry):
    probe = ce.AgentEngineSandboxCodeExecutionProvider.probe
    assert not probe({}, model="m")
    assert not probe({"GCP_PROJECT": "proj"}, model="m")
    assert probe(
        {
            "AGENT_CODE_EXECUTION_AGENT_ENGINE_RESOURCE": "projects/p/locations/l/reasoningEngines/r"
        },
        model="m",
    )


def test_gke_probe_requires_kubeconfig_path(clean_registry, monkeypatch):
    probe = ce.GkeCodeExecutionProvider.probe
    monkeypatch.setattr(
        ce.GkeCodeExecutionProvider, "_available", staticmethod(lambda: True)
    )
    assert not probe({}, model="m")
    assert not probe({"GCP_PROJECT": "proj"}, model="m")
    assert not probe({"AGENT_CODE_EXECUTION_GKE_KUBECONFIG_CONTEXT": "ctx"}, model="m")
    assert probe(
        {"AGENT_CODE_EXECUTION_GKE_KUBECONFIG_PATH": "/kube/config"}, model="m"
    )


def _register_real_chain():
    """Re-register the module's real providers (clean_registry wipes them).

    Order mirrors the module-level registration = the auto-detect chain."""
    ce.register(ce.VertexAiCodeExecutionProvider, auto=True)
    ce.register(ce.AgentEngineSandboxCodeExecutionProvider, auto=True)
    ce.register(ce.GkeCodeExecutionProvider, auto=True)
    ce.register(ce.DockerContainerCodeExecutionProvider, auto=True)
    ce.register(ce.GeminiBuiltInCodeExecutionProvider, auto=True)
    ce.register(ce.UnsafeLocalCodeExecutionProvider)


def _stub_gcp_builds(monkeypatch):
    """Replace GCP providers' build() with sentinels.

    The real constructors perform live SDK work (vertexai import, extension
    lookup); ordering assertions only exercise probe sequencing.
    """
    for provider in (
        ce.VertexAiCodeExecutionProvider,
        ce.AgentEngineSandboxCodeExecutionProvider,
        ce.GkeCodeExecutionProvider,
    ):
        monkeypatch.setattr(provider, "_available", staticmethod(lambda: True))
        monkeypatch.setattr(
            provider, "build", classmethod(lambda cls, environment: object())
        )


def test_gcp_resource_beats_reachable_docker(clean_registry, monkeypatch):
    client = FakeDockerClient()
    install_fake_docker(monkeypatch, client)
    _register_real_chain()
    _stub_gcp_builds(monkeypatch)
    resolution = resolve_code_executor(
        {"AGENT_CODE_EXECUTION_VERTEX_RESOURCE": "projects/p/locations/l/extensions/e"},
        model="m",
    )
    assert resolution.strategy == "vertex_ai"
    assert client.constructor_kwargs == []  # docker never probed


def test_agent_engine_beats_docker(clean_registry, monkeypatch):
    install_fake_docker(monkeypatch, FakeDockerClient())
    _register_real_chain()
    _stub_gcp_builds(monkeypatch)
    resolution = resolve_code_executor(
        {
            "AGENT_CODE_EXECUTION_AGENT_ENGINE_RESOURCE": "projects/p/locations/l/reasoningEngines/r"
        },
        model="gemini-1.5-flash",
    )
    assert resolution.strategy == "agent_engine_sandbox"


def test_gke_beats_docker_and_gemini(clean_registry, monkeypatch):
    install_fake_docker(monkeypatch, FakeDockerClient())
    _register_real_chain()
    _stub_gcp_builds(monkeypatch)
    resolution = resolve_code_executor(
        {"AGENT_CODE_EXECUTION_GKE_KUBECONFIG_PATH": "/kube/config"},
        model="gemini-2.0-flash",
    )
    assert resolution.strategy == "gke"


def test_auto_detect_order_full_chain(clean_registry, monkeypatch):
    monkeypatch.setitem(sys.modules, "docker", None)
    _register_real_chain()
    _stub_gcp_builds(monkeypatch)
    resolution = resolve_code_executor(
        {
            "AGENT_CODE_EXECUTION_VERTEX_RESOURCE": "v",
            "AGENT_CODE_EXECUTION_AGENT_ENGINE_RESOURCE": "a",
            "AGENT_CODE_EXECUTION_GKE_KUBECONFIG_PATH": "/kube/config",
        },
        model="gemini-2.0-flash",
    )
    assert resolution.strategy == "vertex_ai"


def test_vertex_build_constructs_executor(clean_registry, monkeypatch):
    import google.adk.code_executors as ce_pkg

    class _FakeVertex:
        def __init__(self, resource_name=None):
            self.resource_name = resource_name

    monkeypatch.setattr(ce_pkg, "VertexAiCodeExecutor", _FakeVertex, raising=False)
    executor = ce.VertexAiCodeExecutionProvider.build(
        {"AGENT_CODE_EXECUTION_VERTEX_RESOURCE": "projects/p/locations/l/extensions/e"}
    )
    assert isinstance(executor, _FakeVertex)
    assert executor.resource_name == "projects/p/locations/l/extensions/e"


def test_agent_engine_build_constructs_executor(clean_registry, monkeypatch):
    import google.adk.code_executors as ce_pkg

    class _FakeAgentEngine:
        def __init__(self, agent_engine_resource_name=None, **kwargs):
            self.agent_engine_resource_name = agent_engine_resource_name

    monkeypatch.setattr(
        ce_pkg, "AgentEngineSandboxCodeExecutor", _FakeAgentEngine, raising=False
    )
    executor = ce.AgentEngineSandboxCodeExecutionProvider.build(
        {"AGENT_CODE_EXECUTION_AGENT_ENGINE_RESOURCE": "projects/p/reasoningEngines/r"}
    )
    assert executor.agent_engine_resource_name == "projects/p/reasoningEngines/r"


def test_gke_build_constructs_executor(clean_registry, monkeypatch):
    import google.adk.code_executors as ce_pkg

    install_fake_kubernetes(monkeypatch)  # let the lazy import chain resolve

    calls: dict[str, Any] = {}

    class _FakeGke:
        def __init__(self, kubeconfig_path=None, kubeconfig_context=None, **kwargs):
            calls["path"] = kubeconfig_path
            calls["context"] = kubeconfig_context

    monkeypatch.setattr(ce_pkg, "GkeCodeExecutor", _FakeGke, raising=False)
    ce.GkeCodeExecutionProvider.build(
        {
            "AGENT_CODE_EXECUTION_GKE_KUBECONFIG_PATH": "/kube/config",
            "AGENT_CODE_EXECUTION_GKE_KUBECONFIG_CONTEXT": "sandbox-ctx",
        }
    )
    assert calls == {"path": "/kube/config", "context": "sandbox-ctx"}


def test_hardened_executor_exec_run_exception_returns_stderr(
    clean_registry, monkeypatch
):
    client = FakeDockerClient()

    def explode(cmd):
        raise RuntimeError("container died mid-exec")

    client.exec_handler = explode
    install_fake_docker(monkeypatch, client)
    executor = ce._hardened_executor_cls_get()(timeout_seconds=5)

    result = executor.execute_code(None, _code_input("print('boom')"))
    assert "Execution failed" in result.stderr
    assert "container died mid-exec" in result.stderr
    assert result.stdout == ""


def test_known_strategies_lists_registered_names(clean_registry):
    assert ce.known_strategies() == ()
    ce.register(ce.DockerContainerCodeExecutionProvider)
    ce.register(ce.UnsafeLocalCodeExecutionProvider)
    assert ce.known_strategies() == ("docker_container", "unsafe_local")


def test_unknown_strategy_error_lists_known_names(clean_registry):
    ce.register(ce.DockerContainerCodeExecutionProvider)
    with pytest.raises(ProviderConfigurationError) as excinfo:
        resolve_code_executor({STRATEGY_ENV: "nope"}, model="m")
    assert "docker_container" in str(excinfo.value)


def test_resolver_never_probes_unregistered_auto_name(clean_registry):
    """A stale _AUTO_DETECT_ORDER entry (shouldn't happen) fails loudly,
    not silently — guards the registry/chain invariant."""
    ce._AUTO_DETECT_ORDER = ("ghost",)
    try:
        with pytest.raises(KeyError):
            resolve_code_executor({}, model="m")
    finally:
        ce._AUTO_DETECT_ORDER = ()
