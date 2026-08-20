"""Keep operator-facing documentation aligned with runtime catalogs and defaults."""

from pathlib import Path

from basic_agent.use_cases.registry import UseCaseRegistry, _register_builtins

ROOT = Path(__file__).parents[1]


def test_readme_documents_every_builtin_use_case_and_interface():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    registry = UseCaseRegistry()
    _register_builtins(registry)

    entries = registry.list_use_cases()
    assert len(entries) == 8
    for entry in entries:
        assert f"| `{entry['key']}` |" in readme
    assert "REST, Web, CLI" in readme
    assert "REST, Web, CLI, Live" in readme
    assert "no built-in" in readme


def test_docs_use_current_model_example_and_provider_catalog_links():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    env_example = (ROOT / ".env.example").read_text(encoding="utf-8")

    assert "openai/gpt-5.6" in readme
    assert "openai/gpt-5.6" in env_example
    assert "openai/gpt-4o" not in readme
    assert "anthropic/claude-sonnet-5" not in readme
    assert "developers.openai.com/api/docs/models" in readme
    assert "docs.litellm.ai/docs/providers" in readme


def test_port_documentation_exposes_host_overrides_and_internal_contracts():
    configuration = (ROOT / "docs/CONFIGURATION.md").read_text(encoding="utf-8")
    architecture = (ROOT / "docs/ARCHITECTURE.md").read_text(encoding="utf-8")
    env_example = (ROOT / ".env.example").read_text(encoding="utf-8")

    for variable in (
        "ADK_API_PORT",
        "LIVE_API_PORT",
        "KEYCLOAK_PORT",
        "AGENT_SERVICE_API_PORT",
        "GRAFANA_PORT",
        "OTLP_GRPC_PORT",
        "OTLP_HTTP_PORT",
    ):
        assert variable in configuration
        assert variable in env_example
    assert "Internal container port" in configuration
    assert "stable container listener contracts" in architecture


def test_sandbox_documentation_covers_activation_configuration_and_verification():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    configuration = (ROOT / "docs/CONFIGURATION.md").read_text(encoding="utf-8")

    for text in (readme, configuration):
        assert "AGENT_TOOLS" in text
        assert "AGENT_CODE_EXECUTION_STRATEGY" in text
        assert "AGENT_CODE_EXECUTION_DOCKER_IMAGE" in text
    assert "code-exec" in readme
    assert "unsafe_local" in readme
    assert "read-only root filesystem" in readme
    assert "scripts/verify-sandbox-runtime.sh" in readme
