from pathlib import Path

from basic_agent.config.defaults import (
    API_PORT,
    APP_VERSION,
    ENABLED_TOOLS,
    GRAFANA_PORT,
    IMAGE_NAME,
    KEYCLOAK_PORT,
    LIVE_MODEL,
    LIVE_PORT,
    MODEL,
    SERVICE_API_URL,
)

ROOT = Path(__file__).parents[1]


def test_documented_defaults_match_runtime_defaults():
    env_example = (ROOT / ".env.example").read_text(encoding="utf-8")
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    cloud_run = (ROOT / "deploy/cloudrun/service.yaml").read_text(encoding="utf-8")
    ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")

    assert f"APP_VERSION={APP_VERSION}" in env_example
    assert f"AGENT_SERVICE_API_URL={SERVICE_API_URL}" in env_example
    assert f"APP_VERSION:-{APP_VERSION}" in compose
    assert f"ADK_MODEL={MODEL}" in env_example
    assert f"ADK_MODEL:-{MODEL}" in compose
    assert ENABLED_TOOLS in env_example
    assert ENABLED_TOOLS in compose
    assert ENABLED_TOOLS in readme
    assert f"ADK_API_PORT={API_PORT}" in env_example
    assert f"LIVE_API_PORT={LIVE_PORT}" in env_example
    assert f"KEYCLOAK_PORT={KEYCLOAK_PORT}" in env_example
    assert f"ADK_API_CONTAINER_PORT={API_PORT}" in env_example
    assert f"LIVE_API_CONTAINER_PORT={LIVE_PORT}" in env_example
    assert f"KEYCLOAK_CONTAINER_PORT={KEYCLOAK_PORT}" in env_example
    assert f"GRAFANA_PORT={GRAFANA_PORT}" in env_example
    assert f"LIVE_ADK_MODEL={LIVE_MODEL}" in env_example
    assert f"ADK_API_PORT:-{API_PORT}" in compose
    assert (
        "AGENT_SERVICE_API_URL: http://service-api:${AGENT_SERVICE_API_CONTAINER_PORT:-8001}"
        in compose
    )
    assert f"LIVE_API_PORT:-{LIVE_PORT}" in compose
    assert f"GRAFANA_PORT:-{GRAFANA_PORT}" in compose
    assert "service-api:${AGENT_SERVICE_API_CONTAINER_PORT:-8001}" in compose
    assert "${ADK_API_CONTAINER_PORT:-8002}" in compose
    assert "${LIVE_API_CONTAINER_PORT:-8003}" in compose
    assert "${KEYCLOAK_CONTAINER_PORT:-8080}" in compose
    assert "${AGENT_SERVICE_API_CONTAINER_PORT:-8001}" in compose
    assert "${AUTH_GATEWAY_CONTAINER_PORT:-8010}" in compose
    assert f"containerPort: {API_PORT}" in cloud_run
    assert f"value: {MODEL}" in cloud_run
    assert f"IMAGE_NAME: {IMAGE_NAME.removeprefix('ghcr.io/')}" in ci
    assert f'version = "{APP_VERSION}"' in pyproject
