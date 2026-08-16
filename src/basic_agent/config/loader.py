"""Load and validate externalized agent configurations."""

from __future__ import annotations

import dataclasses
import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from ..strategies.base import RoleConfig
from ..util import split_csv

logger = logging.getLogger(__name__)


@dataclass
class ModelConfig:
    """Model configuration."""

    provider: str
    name: str
    api_key: str | None = None
    base_url: str | None = None


@dataclass
class InstructionsConfig:
    """Instructions configuration."""

    value: str = ""
    file: str | None = None


@dataclass
class ToolsConfig:
    """Tools configuration."""

    enabled: list[str] = field(default_factory=list)
    mcp: ToolsMcpConfig | None = None
    openapi: ToolsOpenApiConfig | None = None
    skills: ToolsSkillsConfig | None = None


@dataclass
class ToolsMcpConfig:
    """MCP tools configuration."""

    enabled: bool = False
    tools: list[str] = field(default_factory=list)
    prefix: str = "mcp_"


@dataclass
class ToolsOpenApiConfig:
    """OpenAPI tools configuration."""

    enabled: bool = False
    url: str = ""
    path: str = "/status"
    title: str = "Service API"
    prefix: str = "api_"


@dataclass
class ToolsSkillsConfig:
    """Skills tools configuration."""

    enabled: bool = False
    dir: str = ""
    prefix: str = ""


@dataclass
class ExecutionConfig:
    """Execution configuration."""

    max_iterations: int = 3
    require_approval: bool = False
    steps: int | None = None
    workers: int | None = None
    specialists: list[str] = field(default_factory=list)
    code_execution: "ExecutionCodeExecutionConfig | None" = None


@dataclass
class ExecutionCodeExecutionConfig:
    """Code-execution sandbox configuration (ADR-004).

    Strategy names and semantics live in ``basic_agent.code_execution``;
    these fields are pure transport until the resolver consumes them (P6).
    """

    strategy: str = ""
    docker_host: str = ""
    docker_image: str = ""
    vertex_resource: str = ""
    agent_engine_resource: str = ""
    gke_kubeconfig_path: str = ""
    gke_kubeconfig_context: str = ""


@dataclass
class OutputConfig:
    """Output configuration."""

    schema: str | None = None
    key: str | None = None


@dataclass
class StateConfig:
    """State configuration."""

    enabled: bool = True


@dataclass
class AgentConfig:
    """Complete agent configuration."""

    use_case: str
    name: str = ""
    description: str = ""
    model: ModelConfig | None = None
    instructions: InstructionsConfig | None = None
    tools: ToolsConfig | None = None
    execution: ExecutionConfig | None = None
    output: OutputConfig | None = None
    state: StateConfig | None = None
    roles: dict[str, RoleConfig] = field(default_factory=dict)

    def validate(self) -> None:
        """Validate structural configuration requirements.

        Type-specific constraints (e.g., expert_dispatch needs specialists) are
        owned by the corresponding strategy's validate().

        Raises:
            ValueError: If configuration is invalid.
        """
        if not self.use_case:
            raise ValueError("agent.use_case is required")
        if self.execution:
            _positive_int(self.execution.max_iterations, "execution.max_iterations")
            for key in ("steps", "workers"):
                value = getattr(self.execution, key)
                if value is not None:
                    _positive_int(value, f"execution.{key}")


def _split_names(raw: str) -> list[str]:
    """Split a comma-separated env value into stripped, non-empty names.

    Delegates to :func:`_util.split_csv`; kept as a local alias so callers
    in this module read naturally without an extra import line.
    """
    return split_csv(raw)


def _positive_int(value: Any, name: str) -> int:
    """Validate a positive integer from YAML or environment input."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an integer >= 1; got {value!r}")
    if value < 1:
        raise ValueError(f"{name} must be an integer >= 1; got {value!r}")
    return value


def _env_positive_int(raw: str, name: str) -> int:
    try:
        value = int(raw.strip())
    except ValueError as error:
        raise ValueError(f"{name} must be an integer >= 1; got {raw!r}") from error
    return _positive_int(value, name)


def _resolve_use_case_key(raw: str) -> str:
    """Resolve a use-case key to its canonical form.

    Unresolvable values pass through so the use-case registry raises the
    authoritative error at build time.
    """
    from ..use_cases.registry import get_default_registry

    registry = get_default_registry()
    if registry.has(raw):
        canonical, _ = registry.resolve(raw)
        return canonical
    return raw.strip().lower()


def _substitute_env_vars(value: str) -> str:
    """Substitute environment variables in a string.

    Supports ${VAR_NAME} and ${VAR_NAME:default} syntax.

    Args:
        value: String with potential substitutions.

    Returns:
        String with environment variables replaced.
    """
    import re

    def replace_var(match):
        var_ref = match.group(1)
        if ":" in var_ref:
            var_name, default = var_ref.split(":", 1)
        else:
            var_name, default = var_ref, None

        result = os.getenv(var_name.strip())
        if result is None:
            if default is None:
                logger.warning("Environment variable %s not found", var_name)
                return match.group(0)
            return default
        return result

    return re.sub(r"\$\{([^}]+)\}", replace_var, value)


def _process_dict_substitutions(obj: Any) -> Any:
    """Recursively process environment variable substitutions in data structures.

    Args:
        obj: The object to process.

    Returns:
        The object with substitutions applied.
    """
    if isinstance(obj, dict):
        return {k: _process_dict_substitutions(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_process_dict_substitutions(item) for item in obj]
    elif isinstance(obj, str):
        return _substitute_env_vars(obj)
    return obj


def _unresolved_substitution_paths(obj: Any, path: str = "") -> list[str]:
    """Return YAML field paths that still contain an unresolved placeholder."""
    if isinstance(obj, dict):
        paths: list[str] = []
        for key, value in obj.items():
            paths.extend(_unresolved_substitution_paths(value, f"{path}.{key}" if path else str(key)))
        return paths
    if isinstance(obj, list):
        paths = []
        for index, value in enumerate(obj):
            paths.extend(_unresolved_substitution_paths(value, f"{path}[{index}]"))
        return paths
    if isinstance(obj, str) and "${" in obj:
        return [path]
    return []


def load_config_from_yaml(path: str | Path) -> AgentConfig:
    """Load agent configuration from a YAML file.

    Args:
        path: Path to the YAML configuration file.

    Returns:
        Parsed and validated AgentConfig.

    Raises:
        FileNotFoundError: If file doesn't exist.
        ValueError: If YAML is invalid or configuration is invalid.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Configuration file not found: {path}")

    logger.info("Loading configuration from %s", path)

    try:
        raw_data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        raise ValueError(f"Invalid YAML in {path}: {e}") from e

    if not isinstance(raw_data, dict):
        raise ValueError(f"Configuration must be a YAML object, not {type(raw_data)}")

    # Apply environment variable substitutions
    raw_data = _process_dict_substitutions(raw_data)
    unresolved = _unresolved_substitution_paths(raw_data)
    if unresolved:
        raise ValueError(
            "Unresolved environment substitution(s) in YAML: "
            + ", ".join(unresolved)
        )

    # Parse into dataclasses
    config = _parse_agent_config(raw_data)
    config.validate()

    logger.info("Configuration loaded: use_case=%s", config.use_case)
    return config


def load_config_from_env() -> AgentConfig:
    """Load agent configuration from environment variables (no config file).

    Env vars are read at call time; ``settings`` supplies the defaults. The
    returned AgentConfig has the same shape as the YAML path.

    Returns:
        AgentConfig populated from environment.
    """
    from .settings import settings

    use_case_raw = os.environ.get("AGENT_USE_CASE", "").strip()
    if not use_case_raw:
        use_case_raw = "assistant"
    use_case = _resolve_use_case_key(use_case_raw)

    max_iterations_raw = os.environ.get("AGENT_MAX_ITERATIONS")
    max_iterations = (
        _env_positive_int(max_iterations_raw, "AGENT_MAX_ITERATIONS")
        if max_iterations_raw
        else settings.max_iterations
    )

    specialists_raw = os.environ.get("AGENT_SPECIALISTS")
    specialists = _split_names(specialists_raw) if specialists_raw else list(settings.specialists)

    config = AgentConfig(
        use_case=use_case,
        name=settings.app_name,
        description=settings.agent_description,
        model=ModelConfig(
            provider="google",
            name=settings.model,
        ),
        instructions=InstructionsConfig(value=settings.agent_instruction),
        tools=ToolsConfig(
            enabled=list(settings.enabled_tools),
            mcp=ToolsMcpConfig(
                enabled=settings.enable_mcp,
                tools=list(settings.mcp_tools),
                prefix=settings.mcp_tool_prefix,
            ),
        ),
        execution=ExecutionConfig(
            max_iterations=_positive_int(max_iterations, "execution.max_iterations"),
            specialists=specialists,
            code_execution=ExecutionCodeExecutionConfig(
                strategy=settings.code_execution_strategy,
                docker_host=settings.code_execution_docker_host,
                docker_image=settings.code_execution_docker_image,
                vertex_resource=settings.code_execution_vertex_resource,
                agent_engine_resource=settings.code_execution_agent_engine_resource,
                gke_kubeconfig_path=settings.code_execution_gke_kubeconfig_path,
                gke_kubeconfig_context=settings.code_execution_gke_kubeconfig_context,
            ),
        ),
        output=OutputConfig(
            schema="GenericAgentResponse" if settings.enable_structured_output else None,
            key="last_response",
        ),
        state=StateConfig(enabled=True),
    )

    config.validate()
    return config


def log_config_provenance(
    config_path: str | None,
    overridden_keys: list[str] | tuple[str, ...],
    resolved_use_case: str,
) -> None:
    """Log the single-line config provenance summary shared by both load paths."""
    logger.info(
        "config: yaml=%s, use_case=%s, env overrides: %s",
        config_path or "none",
        resolved_use_case,
        ", ".join(overridden_keys) if overridden_keys else "none",
    )


def apply_env_overrides(
    config: AgentConfig, *, config_path: str | None = None
) -> AgentConfig:
    """Apply the documented env vars onto a YAML-loaded config.

    Only explicitly set, non-empty values apply. Returns a new AgentConfig;
    nothing shared is mutated.

    Args:
        config: The YAML-loaded configuration.
        config_path: Provenance path logged in the summary line.

    Returns:
        A new AgentConfig with overrides applied.

    Raises:
        ValueError: If overridden specialists don't match non-empty roles keys.
    """
    overridden: list[str] = []

    use_case_raw = os.environ.get("AGENT_USE_CASE")
    if use_case_raw and use_case_raw.strip():
        canonical = _resolve_use_case_key(use_case_raw)
        config = dataclasses.replace(config, use_case=canonical)
        overridden.append("AGENT_USE_CASE")

    model_name = os.environ.get("ADK_MODEL")
    if model_name and model_name.strip():
        model = config.model or ModelConfig(provider="google", name="")
        config = dataclasses.replace(
            config, model=dataclasses.replace(model, name=model_name.strip())
        )
        overridden.append("ADK_MODEL")

    instruction = os.environ.get("AGENT_INSTRUCTION")
    if instruction and instruction.strip():
        instructions = config.instructions or InstructionsConfig()
        config = dataclasses.replace(
            config,
            instructions=dataclasses.replace(instructions, value=instruction.strip()),
        )
        overridden.append("AGENT_INSTRUCTION")

    tool_names = os.environ.get("AGENT_TOOLS")
    if tool_names and tool_names.strip():
        tools = config.tools or ToolsConfig()
        config = dataclasses.replace(
            config, tools=dataclasses.replace(tools, enabled=_split_names(tool_names))
        )
        overridden.append("AGENT_TOOLS")

    max_iterations_raw = os.environ.get("AGENT_MAX_ITERATIONS")
    if max_iterations_raw and max_iterations_raw.strip():
        execution = config.execution or ExecutionConfig()
        config = dataclasses.replace(
            config,
            execution=dataclasses.replace(
                execution,
                max_iterations=_env_positive_int(
                    max_iterations_raw, "AGENT_MAX_ITERATIONS"
                ),
            ),
        )
        overridden.append("AGENT_MAX_ITERATIONS")

    specialists_raw = os.environ.get("AGENT_SPECIALISTS")
    if specialists_raw and specialists_raw.strip():
        names = _split_names(specialists_raw)
        if config.roles and not set(names).issubset(config.roles):
            raise ValueError(
                f"AGENT_SPECIALISTS contains unknown role(s) "
                f"{sorted(set(names) - set(config.roles))}; available roles: "
                f"{sorted(config.roles)}"
            )
        execution = config.execution or ExecutionConfig()
        config = dataclasses.replace(
            config, execution=dataclasses.replace(execution, specialists=names)
        )
        overridden.append("AGENT_SPECIALISTS")

    config.validate()
    log_config_provenance(config_path, overridden, config.use_case or "assistant")
    return config


def _parse_code_execution_config(execution_data: dict) -> "ExecutionCodeExecutionConfig | None":
    """Parse the ``execution.code_execution`` mapping; None when absent."""
    data = execution_data.get("code_execution")
    if not data:
        return None
    fields = (
        "strategy",
        "docker_host",
        "docker_image",
        "vertex_resource",
        "agent_engine_resource",
        "gke_kubeconfig_path",
        "gke_kubeconfig_context",
    )
    for name in fields:
        value = data.get(name, "")
        if value is not None and not isinstance(value, str):
            raise ValueError(
                f"execution.code_execution.{name} must be a string, got {type(value).__name__}"
            )
    return ExecutionCodeExecutionConfig(
        strategy=data.get("strategy", ""),
        docker_host=data.get("docker_host", ""),
        docker_image=data.get("docker_image", ""),
        vertex_resource=data.get("vertex_resource", ""),
        agent_engine_resource=data.get("agent_engine_resource", ""),
        gke_kubeconfig_path=data.get("gke_kubeconfig_path", ""),
        gke_kubeconfig_context=data.get("gke_kubeconfig_context", ""),
    )


def _parse_agent_config(data: dict) -> AgentConfig:
    """Parse raw dictionary into AgentConfig.

    Args:
        data: Raw configuration dictionary.

    Returns:
        Parsed AgentConfig.

    Raises:
        ValueError: If required fields are missing.
    """
    agent_data = data.get("agent", {})
    if not isinstance(agent_data, dict):
        raise ValueError("agent must be a mapping")

    use_case_raw = str(agent_data.get("use_case") or "").strip()
    if not use_case_raw:
        raise ValueError("agent.use_case is required")
    use_case = _resolve_use_case_key(use_case_raw)

    model_data = data.get("model", {})
    model_config = None
    if model_data:
        model_config = ModelConfig(
            provider=model_data.get("provider", "google"),
            name=model_data.get("name", ""),
            api_key=model_data.get("api_key"),
            base_url=model_data.get("base_url"),
        )

    instructions_data = data.get("instructions", {})
    instructions_config = None
    if instructions_data:
        instructions_config = InstructionsConfig(
            value=instructions_data.get("value", ""),
            file=instructions_data.get("file"),
        )

    tools_data = data.get("tools", {})
    tools_config = None
    if tools_data:
        mcp_data = tools_data.get("mcp")
        mcp_config = None
        if mcp_data:
            mcp_config = ToolsMcpConfig(
                enabled=mcp_data.get("enabled", False),
                tools=mcp_data.get("tools", []),
                prefix=mcp_data.get("prefix", "mcp_"),
            )

        openapi_data = tools_data.get("openapi")
        openapi_config = None
        if openapi_data:
            openapi_config = ToolsOpenApiConfig(
                enabled=openapi_data.get("enabled", False),
                url=openapi_data.get("url", ""),
                path=openapi_data.get("path", "/status"),
                title=openapi_data.get("title", "Service API"),
                prefix=openapi_data.get("prefix", "api_"),
            )

        skills_data = tools_data.get("skills")
        skills_config = None
        if skills_data:
            skills_config = ToolsSkillsConfig(
                enabled=skills_data.get("enabled", False),
                dir=skills_data.get("dir", ""),
                prefix=skills_data.get("prefix", ""),
            )

        tools_config = ToolsConfig(
            enabled=tools_data.get("enabled", []),
            mcp=mcp_config,
            openapi=openapi_config,
            skills=skills_config,
        )

    execution_data = data.get("execution", {})
    execution_config = None
    if execution_data:
        execution_config = ExecutionConfig(
            max_iterations=_positive_int(
                execution_data.get("max_iterations", 3),
                "execution.max_iterations",
            ),
            require_approval=execution_data.get("require_approval", False),
            steps=(
                _positive_int(execution_data["steps"], "execution.steps")
                if execution_data.get("steps") is not None
                else None
            ),
            workers=(
                _positive_int(execution_data["workers"], "execution.workers")
                if execution_data.get("workers") is not None
                else None
            ),
            specialists=execution_data.get("specialists", []),
            code_execution=_parse_code_execution_config(execution_data),
        )

    output_data = data.get("output", {})
    output_config = None
    if output_data:
        output_config = OutputConfig(
            schema=output_data.get("schema"),
            key=output_data.get("key"),
        )

    state_data = data.get("state", {})
    state_config = None
    if state_data:
        state_config = StateConfig(enabled=state_data.get("enabled", True))

    roles_data = data.get("roles") or {}
    roles = {
        str(name): RoleConfig(
            instruction=role.get("instruction"),
            model=role.get("model"),
            tools=role.get("tools"),
        )
        for name, role in roles_data.items()
        if isinstance(role, dict)
    }

    return AgentConfig(
        use_case=use_case,
        name=agent_data.get("name", ""),
        description=agent_data.get("description", ""),
        model=model_config,
        instructions=instructions_config,
        tools=tools_config,
        execution=execution_config,
        output=output_config,
        state=state_config,
        roles=roles,
    )
