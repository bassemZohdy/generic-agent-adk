"""Shared test doubles for the docker SDK module graph.

Imported by test modules as a plain sibling module (pytest's rootdir mode
puts ``tests/`` on ``sys.path``). One canonical implementation of the fake
docker client/container — kept here so ``test_code_execution.py`` and
``test_runtime_wiring.py`` exercise the same shape.
"""

from __future__ import annotations

import sys
import types
from collections.abc import Callable


class FakeExecResult:
    """Stand-in for docker's ExecResult tuple-ish object."""

    def __init__(self, exit_code=0, output=(b"", b"")):
        self.exit_code = exit_code
        self.output = output


class FakeContainer:
    """Container recording lifecycle calls; dispatches configurable execs."""

    def __init__(self, client):
        self._client = client
        self.id = f"fake-container-{len(client.run_calls) - 1}"

    def exec_run(self, cmd, demux=False, stream=False):
        cmd = list(cmd)
        if cmd == ["which", "python3"]:
            # ADK's _verify_python_installation() requires exit 0 here.
            if self._client.python_missing:
                return FakeExecResult(1, (b"", b"python3 missing\n"))
            return FakeExecResult(0, (b"/usr/local/bin/python3\n", b""))
        if self._client.exec_handler is not None:
            return self._client.exec_handler(cmd)
        return FakeExecResult(0, (b"ok\n", b""))

    def stop(self):
        self._client.stop_calls.append(self.id)

    def kill(self):
        self._client.kill_calls.append(self.id)

    def remove(self, force=False):
        self._client.remove_calls.append(self.id)


class FakeDockerClient:
    """DockerClient/from_env stand-in recording everything the code does."""

    def __init__(self):
        self.constructor_kwargs: list[dict] = []
        self.run_calls: list[dict] = []
        self.stop_calls: list[str] = []
        self.kill_calls: list[str] = []
        self.remove_calls: list[str] = []
        self.ping_raises: Exception | None = None
        self.python_missing = False
        self.exec_handler: Callable[[list[str]], FakeExecResult] | None = None

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
                return FakeContainer(client)

        return _Containers()


def install_fake_docker(monkeypatch, client: FakeDockerClient) -> types.ModuleType:
    """Install a docker module graph ADK's lazy import chain can live with."""
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


def install_fake_kubernetes(monkeypatch) -> None:
    """Minimal kubernetes module graph for gke_code_executor's imports."""
    k8s = types.ModuleType("kubernetes")
    client_mod = types.ModuleType("kubernetes.client")
    exceptions_mod = types.ModuleType("kubernetes.client.exceptions")
    config_mod = types.ModuleType("kubernetes.config")
    watch_mod = types.ModuleType("kubernetes.watch")
    exceptions_mod.ApiException = type("ApiException", (Exception,), {})
    watch_mod.Watch = type("Watch", (), {})
    client_mod.exceptions = exceptions_mod
    k8s.client = client_mod
    k8s.config = config_mod
    k8s.watch = watch_mod
    for name, module in (
        ("kubernetes", k8s),
        ("kubernetes.client", client_mod),
        ("kubernetes.client.exceptions", exceptions_mod),
        ("kubernetes.config", config_mod),
        ("kubernetes.watch", watch_mod),
    ):
        monkeypatch.setitem(sys.modules, name, module)
