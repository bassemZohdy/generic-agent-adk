from pathlib import Path

from basic_agent.config.defaults import APP_VERSION, ENABLED_TOOLS, MODEL

ROOT = Path(__file__).parents[1]


def test_documented_defaults_match_runtime_defaults():
    env_example = (ROOT / ".env.example").read_text(encoding="utf-8")
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert f"APP_VERSION={APP_VERSION}" in env_example
    assert f"APP_VERSION:-{APP_VERSION}" in compose
    assert f"ADK_MODEL={MODEL}" in env_example
    assert f"ADK_MODEL:-{MODEL}" in compose
    assert ENABLED_TOOLS in env_example
    assert ENABLED_TOOLS in compose
    assert ENABLED_TOOLS in readme
