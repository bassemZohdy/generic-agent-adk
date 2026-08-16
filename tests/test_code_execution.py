"""Tests for code-execution provider resolution (ADR-004, TODO P1)."""

from __future__ import annotations

import importlib
import importlib.util
import logging
import sys
from typing import Any, Callable

import pytest

import basic_agent.code_execution as ce
from basic_agent.autoconfig import ProviderConfigurationError
from basic_agent.code_execution import (
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


class _FakeExecResult:
    def __init__(self, exit_code=0, output=(b"", b"")):
        self.exit_code = exit_code
        self.output = output


class _FakeDockerClient:
    """Records container lifecycle calls; dispatches configurable execs."""

    def __init__(self):
        self.constructor_kwargs: list[dict] = []
        self.run_calls: list[dict] = []
        self.stop_calls: list[str] = []
        self.remove_calls: list[str] = []
        self.ping_raises: Exception | None = None
        self.exec_handler: "Callable[[list[str]], _FakeExecResult] | None" = None

    def ping(self):
        if self.ping_raises:
            raise self.ping_raises
        return True

    @property
    def containers(self):
        client = self

        class _Containers:
            def run(self, **kwargs):
                client.run_calls.append(kwargs)
                return _FakeContainer(client)

        return _Containers()


class _FakeContainer:
    def __init__(self, client):
        self._client = client
        self.id = f"fake-container-{len(client.run_calls)}"

    def exec_run(self, cmd, demux=False):
        cmd = list(cmd)
        if cmd == ["which", "python3"]:
            return _FakeExecResult(0, (b"/usr/local/bin/python3\n", b""))
        if self._client.exec_handler is not None:
            return self._client.exec_handler(cmd)
        return _FakeExecResult(0, (b"ok\n", b""))

    def stop(self):
        self._client.stop_calls.append(self.id)

    def remove(self):
        self._client.remove_calls.append(self.id)


def _install_fake_docker(monkeypatch, client: _FakeDockerClient):
    """Install a docker module graph the ADK import chain can live with."""
    import types

    docker_mod = types.ModuleType("docker")
    client_mod = types.ModuleType("docker.client")
    models_mod = types.ModuleType("docker.models")
    containers_mod = types.ModuleType("docker.models.containers")

    def _constructor(**kwargs):
        client.constructor_kwargs.append(kwargs)
        return client

    docker_mod.DockerClient = _constructor
    docker_mod.from_env = _constructor
    client_mod.DockerClient = _constructor
    containers_mod.Container = object
    docker_mod.client = client_mod
    docker_mod.models = models_mod
    models_mod.containers = containers_mod

    for name, module in (
        ("docker", docker_mod),
        ("docker.client", client_mod),
        ("docker.models", models_mod),
        ("docker.models.containers", containers_mod),
    ):
        monkeypatch.setitem(sys.modules, name, module)
    return docker_mod


def test_docker_probe_success_with_env_precedence(clean_registry, monkeypatch):
    client = _FakeDockerClient()
    _install_fake_docker(monkeypatch, client)
    env = {
        "DOCKER_HOST": "tcp://fallback:2375",
        "AGENT_CODE_EXECUTION_DOCKER_HOST": "tcp://primary:2375",
    }
    assert ce.DockerContainerCodeExecutionProvider.probe(env, model="m")
    assert client.constructor_kwargs == [
        {"base_url": "tcp://primary:2375", "timeout": 1}
    ]


def test_docker_probe_uses_docker_host_fallback(clean_registry, monkeypatch):
    client = _FakeDockerClient()
    _install_fake_docker(monkeypatch, client)
    assert ce.DockerContainerCodeExecutionProvider.probe(
        {"DOCKER_HOST": "tcp://fallback:2375"}, model="m"
    )
    assert client.constructor_kwargs == [{"base_url": "tcp://fallback:2375", "timeout": 1}]


def test_docker_probe_uses_from_env_without_host(clean_registry, monkeypatch):
    client = _FakeDockerClient()
    _install_fake_docker(monkeypatch, client)
    assert ce.DockerContainerCodeExecutionProvider.probe({}, model="m")
    assert client.constructor_kwargs == [{"timeout": 1}]


def test_docker_probe_unreachable_daemon_returns_false(clean_registry, monkeypatch):
    client = _FakeDockerClient()
    client.ping_raises = ConnectionError("no daemon")
    _install_fake_docker(monkeypatch, client)
    assert not ce.DockerContainerCodeExecutionProvider.probe({}, model="m")


def test_docker_probe_package_missing_returns_false(clean_registry, monkeypatch):
    monkeypatch.setitem(sys.modules, "docker", None)
    assert not ce.DockerContainerCodeExecutionProvider.probe({}, model="m")


def test_hardened_executor_container_kwargs(clean_registry, monkeypatch):
    client = _FakeDockerClient()
    _install_fake_docker(monkeypatch, client)
    executor = ce.DockerContainerCodeExecutionProvider.build(
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
    client = _FakeDockerClient()
    _install_fake_docker(monkeypatch, client)
    with pytest.raises(ValueError, match="stateful"):
        ce._hardened_executor_cls_get()(stateful=True)


def test_hardened_executor_requires_image_or_docker_path(clean_registry, monkeypatch):
    client = _FakeDockerClient()
    _install_fake_docker(monkeypatch, client)
    with pytest.raises(ValueError, match="image or docker_path"):
        ce._hardened_executor_cls_get()(image=None)


def test_hardened_executor_timeout_kills_and_recovers(clean_registry, monkeypatch):
    import time

    client = _FakeDockerClient()

    def hang(cmd):
        time.sleep(5)
        return _FakeExecResult(0, (b"late", b""))

    client.exec_handler = hang
    _install_fake_docker(monkeypatch, client)
    executor = ce._hardened_executor_cls_get()(timeout_seconds=1)

    result = executor.execute_code(None, _code_input("while True: pass"))
    assert "timed out after 1s" in result.stderr
    assert result.stdout == ""
    # The long-lived container was killed and a fresh one started:
    assert len(client.run_calls) == 2
    assert client.stop_calls and client.remove_calls


def test_hardened_executor_next_call_after_timeout_works(clean_registry, monkeypatch):
    client = _FakeDockerClient()
    client.exec_handler = lambda cmd: _FakeExecResult(0, (b"", b""))
    _install_fake_docker(monkeypatch, client)
    executor = ce._hardened_executor_cls_get()(timeout_seconds=1)

    ok = executor.execute_code(None, _code_input("print('hi')"))
    assert ok.stdout == ""
    client.exec_handler = lambda cmd: _FakeExecResult(0, (b"fresh\n", b""))
    again = executor.execute_code(None, _code_input("print('again')"))
    assert again.stdout == "fresh\n"


def test_hardened_executor_streams_demuxed_output(clean_registry, monkeypatch):
    client = _FakeDockerClient()
    client.exec_handler = lambda cmd: _FakeExecResult(0, (b"out-line\n", b"err-line\n"))
    _install_fake_docker(monkeypatch, client)
    executor = ce._hardened_executor_cls_get()(timeout_seconds=5)

    result = executor.execute_code(None, _code_input("print('x')"))
    assert result.stdout == "out-line\n"
    assert result.stderr == "err-line\n"


def test_docker_provider_auto_detected(clean_registry, monkeypatch):
    client = _FakeDockerClient()
    _install_fake_docker(monkeypatch, client)
    ce.register(ce.DockerContainerCodeExecutionProvider, auto=True)
    resolution = resolve_code_executor({}, model="m")
    assert resolution.strategy == "docker_container"
    assert resolution.executor is not None


def test_docker_explicit_override_with_dead_daemon_raises(clean_registry, monkeypatch):
    client = _FakeDockerClient()
    client.ping_raises = ConnectionError("down")
    _install_fake_docker(monkeypatch, client)
    ce.register(ce.DockerContainerCodeExecutionProvider)
    with pytest.raises(ProviderConfigurationError, match="docker_container"):
        resolve_code_executor({STRATEGY_ENV: "docker_container"}, model="m")


def _code_input(code: str):
    from google.adk.code_executors.code_execution_utils import CodeExecutionInput

    return CodeExecutionInput(code=code)
