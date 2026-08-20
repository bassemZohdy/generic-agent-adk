#!/bin/sh
set -eu

app_image="${1:?usage: $0 APP_IMAGE}"
docker_socket="${DOCKER_SOCKET:-/var/run/docker.sock}"

if [ ! -S "$docker_socket" ]; then
  echo "Docker socket is required for the sandbox runtime smoke test: $docker_socket" >&2
  exit 1
fi

# This is an ephemeral CI/local verification container. It mounts the host
# socket only for the duration of the test, creates one hardened child
# sandbox, executes a harmless snippet, inspects the resulting Docker
# HostConfig, and explicitly removes the child in a finally block.
docker run --rm --user 0 \
  -v "$docker_socket:/var/run/docker.sock" \
  -e DOCKER_HOST=unix:///var/run/docker.sock \
  "$app_image" python - <<'PY'
from types import SimpleNamespace

from basic_agent.execution.resolver import (
    DEFAULT_SANDBOX_IMAGE,
    DOCKER_HOST_ENV,
    DockerContainerCodeExecutionProvider,
)

executor = DockerContainerCodeExecutionProvider.build(
    {
        DOCKER_HOST_ENV: "unix:///var/run/docker.sock",
        "AGENT_CODE_EXECUTION_DOCKER_IMAGE": DEFAULT_SANDBOX_IMAGE,
    }
)
try:
    result = executor.execute_code(None, SimpleNamespace(code="print('sandbox-ok')"))
    assert "sandbox-ok" in result.stdout, result

    container = executor._container
    container.reload()
    host_config = container.attrs["HostConfig"]
    config = container.attrs["Config"]
    assert host_config["Memory"] == 512 * 1024 * 1024
    assert host_config["NanoCpus"] == 1_000_000_000
    assert host_config["PidsLimit"] == 128
    assert host_config["ReadonlyRootfs"] is True
    assert host_config["CapDrop"] == ["ALL"]
    assert "no-new-privileges" in host_config["SecurityOpt"]
    assert config["NetworkDisabled"] is True
    assert config["User"] == "65532:65532"
    assert config["WorkingDir"] == "/tmp"
    print("sandbox runtime verification passed")
finally:
    executor._cleanup_container()
PY
