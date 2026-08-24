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
        "ADK_API_CONTAINER_PORT",
        "LIVE_API_PORT",
        "LIVE_API_CONTAINER_PORT",
        "KEYCLOAK_PORT",
        "KEYCLOAK_CONTAINER_PORT",
        "AGENT_SERVICE_API_PORT",
        "AGENT_SERVICE_API_CONTAINER_PORT",
        "AUTH_GATEWAY_CONTAINER_PORT",
        "GRAFANA_PORT",
        "OTLP_GRPC_PORT",
        "OTLP_HTTP_PORT",
    ):
        assert variable in configuration
        assert variable in env_example
    assert "Container variable" in configuration
    assert "environment-driven" in architecture


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


#: Package entries intentionally absent from ARCHITECTURE.md's module map
#: (dunder init plus build artifacts).
_MODULE_MAP_SKIP = {"__init__.py", "__pycache__"}


def _architecture_module_map_entries() -> list[str]:
    """Extract documented module names from ARCHITECTURE.md's module map."""
    architecture = (ROOT / "docs/ARCHITECTURE.md").read_text(encoding="utf-8")
    section = architecture.split("## Module map (`src/basic_agent/`)")[1]
    section = section.split("\n## ")[0]
    names = []
    for line in section.splitlines():
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) < 2 or set(cells[0]) <= {"-", " ", ":"}:
            continue  # header separator row
        name = cells[0].strip("`").rstrip("/")
        if name == "Module / Package":  # header row
            continue
        names.append(name)
    return names


def test_module_map_documents_every_top_level_package_entry():
    """Every src/basic_agent/ entry appears in the module map (G02).

    Guards against the class of drift where the map keeps describing deleted
    modules (e.g. the removed strategies/ layer) or new top-level modules
    land undocumented.
    """
    package_dir = ROOT / "src" / "basic_agent"
    on_disk = {
        entry.name
        for entry in package_dir.iterdir()
        if entry.name not in _MODULE_MAP_SKIP and not entry.name.startswith(".")
    }
    documented = set(_architecture_module_map_entries())

    missing_from_docs = sorted(on_disk - documented)
    assert not missing_from_docs, (
        f"src/basic_agent/ entries missing from ARCHITECTURE.md's module "
        f"map: {missing_from_docs}"
    )


def test_module_map_names_only_modules_that_exist_on_disk():
    """No documented row may reference a deleted/moved module (G02)."""
    package_dir = ROOT / "src" / "basic_agent"
    on_disk = {entry.name for entry in package_dir.iterdir()}

    stale = [
        name
        for name in _architecture_module_map_entries()
        if name and name not in on_disk
    ]
    assert not stale, (
        f"ARCHITECTURE.md module map documents entries that no longer exist "
        f"in src/basic_agent/: {stale}"
    )
