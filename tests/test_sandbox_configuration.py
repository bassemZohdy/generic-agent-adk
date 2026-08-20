"""Regression tests for sandbox image, Compose, and CI wiring."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).parents[1]


def test_compose_code_exec_profile_points_adk_at_scoped_proxy():
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text())
    api = compose["services"]["adk-api"]
    proxy = compose["services"]["code-exec-socket-proxy"]

    assert "code-exec" in api["networks"]
    assert proxy["profiles"] == ["code-exec"]
    assert proxy["environment"]["POST"] == "1"
    assert proxy["environment"]["CONTAINERS"] == "1"
    assert proxy["environment"]["EXEC"] == "1"
    assert api["environment"]["AGENT_CODE_EXECUTION_DOCKER_HOST"] == (
        "${AGENT_CODE_EXECUTION_DOCKER_HOST:-tcp://code-exec-socket-proxy:2375}"
    )


def test_published_image_installs_docker_extra_by_default():
    dockerfile = (ROOT / "Dockerfile").read_text()
    assert "ARG INSTALL_DOCKER_EXTRA=1" in dockerfile
    assert "--no-install-project --extra docker" in dockerfile
    assert "uv sync --frozen --no-dev --extra docker" in dockerfile


def test_ci_runs_real_sandbox_runtime_smoke():
    workflow = (ROOT / ".github/workflows/ci.yml").read_text()
    assert "verify-sandbox-runtime.sh" in workflow


def _fake_scanners(directory: Path, *, trivy_status: int = 0) -> None:
    trivy = directory / "trivy"
    trivy.write_text(
        f'#!/bin/sh\nprintf \'%s\\n\' "$*" > "$SCAN_ARGS"\nexit {trivy_status}\n',
        encoding="utf-8",
    )
    syft = directory / "syft"
    syft.write_text(
        "#!/bin/sh\n"
        'printf \'%s\\n\' "$*" > "$SYFT_ARGS"\n'
        "output=${3#cyclonedx-json=}\n"
        "printf '{}' > \"$output\"\n",
        encoding="utf-8",
    )
    trivy.chmod(0o755)
    syft.chmod(0o755)


def _run_image_verifier(tmp_path: Path, image: str, *, trivy_status: int = 0):
    scanner_dir = tmp_path / "bin"
    scanner_dir.mkdir()
    _fake_scanners(scanner_dir, trivy_status=trivy_status)
    args_file = tmp_path / "trivy.args"
    syft_args = tmp_path / "syft.args"
    output = tmp_path / "sbom.json"
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{scanner_dir}:{env['PATH']}",
            "SCAN_ARGS": str(args_file),
            "SYFT_ARGS": str(syft_args),
            "SYFT_OUTPUT": str(output),
        }
    )
    return (
        subprocess.run(
            ["sh", "scripts/verify-sandbox-image.sh", image],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        ),
        args_file,
        syft_args,
        output,
    )


def test_sandbox_image_verifier_rejects_missing_digest(tmp_path):
    result, _, _, _ = _run_image_verifier(tmp_path, "python:3.13-slim")
    assert result.returncode != 0
    assert "must be pinned by digest" in result.stderr


def test_sandbox_image_verifier_rejects_invalid_digest(tmp_path):
    result, _, _, _ = _run_image_verifier(
        tmp_path, "python:3.13-slim@sha256:not-a-digest"
    )
    assert result.returncode != 0
    assert "not a valid SHA-256" in result.stderr


def test_sandbox_image_verifier_scans_os_and_writes_sbom(tmp_path):
    image = "python:3.13-slim@sha256:" + "a" * 64
    result, args_file, syft_args, output = _run_image_verifier(tmp_path, image)
    assert result.returncode == 0, result.stderr
    assert "--pkg-types os" in args_file.read_text()
    assert "cyclonedx-json=" in syft_args.read_text()
    assert output.exists()
    assert "Sandbox image verification passed" in result.stdout


def test_sandbox_image_verifier_stops_when_trivy_fails(tmp_path):
    image = "python:3.13-slim@sha256:" + "a" * 64
    result, _, syft_args, output = _run_image_verifier(tmp_path, image, trivy_status=1)
    assert result.returncode == 1
    assert not syft_args.exists()
    assert not output.exists()
