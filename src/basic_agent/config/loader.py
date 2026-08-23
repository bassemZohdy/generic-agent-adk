"""Load and validate externalized agent configurations."""

from __future__ import annotations

import dataclasses
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from ..policies.synthesis import SYNTHESIZER_INSTRUCTION, SYNTHESIZER_OUTPUT_KEY
from ..runtime import RoleConfig
from ..util import split_csv
from .graph import GraphEdgeSpec, GraphNodeSpec, GraphSpec, RetrySpec
from .sugar import (
    LoopSugar,
    ParallelSugar,
    SequenceSugar,
    expand_sugar,
)

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

    # ``None`` means the tools section omitted ``enabled``; an empty list is an
    # intentional request for no tools.
    enabled: list[str] | None = None
    mcp: ToolsMcpConfig | None = None
    openapi: ToolsOpenApiConfig | None = None
    skills: ToolsSkillsConfig | None = None


@dataclass
class ToolsMcpConfig:
    """MCP tools configuration."""

    enabled: bool | None = None
    tools: list[str] = field(default_factory=list)
    prefix: str = "mcp_"


@dataclass
class ToolsOpenApiConfig:
    """OpenAPI tools configuration."""

    enabled: bool | None = None
    url: str = ""
    path: str = "/status"
    title: str = "Service API"
    prefix: str = "api_"


@dataclass
class ToolsSkillsConfig:
    """Skills tools configuration."""

    enabled: bool | None = None
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
    code_execution: ExecutionCodeExecutionConfig | None = None


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
class ApprovalPolicyConfig:
    """Approval policy configuration (ADR-005 §4; TODO D1)."""

    enabled: bool = False
    gated_tools: list[str] = field(default_factory=list)
    gated_prefixes: list[str] = field(default_factory=list)


@dataclass
class SynthesisPolicyConfig:
    """Synthesis policy configuration (ADR-005 §4; TODO D2).

    ``instruction``/``output_key`` default to the canonical synthesizer
    contract (same instruction and state behavior as the multi_perspective
    use case).
    """

    enabled: bool = False
    instruction: str = SYNTHESIZER_INSTRUCTION
    output_key: str = SYNTHESIZER_OUTPUT_KEY


@dataclass
class PoliciesConfig:
    """Cross-cutting policies; each section is optional."""

    approval: ApprovalPolicyConfig | None = None
    synthesis: SynthesisPolicyConfig | None = None


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
    graph: GraphSpec | None = None
    policies: PoliciesConfig | None = None

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
        if self.graph is not None:
            self.graph.validate()


def _split_names(raw: str) -> list[str]:
    """Split a comma-separated env value into stripped, non-empty names.

    Delegates to :func:`_util.split_csv`; kept as a local alias so callers
    in this module read naturally without an extra import line.
    """
    return split_csv(raw)


def _positive_int(value: Any, name: str) -> int:
    """Validate a positive integer from YAML or environment input."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(  # noqa: TRY004 - preserve actionable config error type
            f"{name} must be an integer >= 1; got {value!r}"
        )
    if value < 1:
        raise ValueError(f"{name} must be an integer >= 1; got {value!r}")
    return value


_CONFIG_KEYS = {
    "agent",
    "model",
    "instructions",
    "tools",
    "execution",
    "output",
    "state",
    "roles",
    "graph",
    "policies",
}


def _mapping(value: Any, name: str) -> dict:
    if not isinstance(value, dict):
        raise ValueError(  # noqa: TRY004 - preserve actionable config error type
            f"{name} must be a mapping; got {type(value).__name__}"
        )
    return value


def _keys(value: dict, allowed: set[str], name: str) -> None:
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise ValueError(f"Unknown {name} field(s): {', '.join(unknown)}")


def _string(value: Any, name: str, *, allow_empty: bool = True) -> str:
    if not isinstance(value, str):
        raise ValueError(  # noqa: TRY004 - preserve actionable config error type
            f"{name} must be a string; got {type(value).__name__}"
        )
    if not allow_empty and not value.strip():
        raise ValueError(f"{name} must not be empty")
    return value


def _boolean(value: Any, name: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(  # noqa: TRY004 - preserve actionable config error type
            f"{name} must be a boolean; got {type(value).__name__}"
        )
    return value


def _string_list(value: Any, name: str) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"{name} must be a list of strings")
    return [item.strip() for item in value if item.strip()]


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
            paths.extend(
                _unresolved_substitution_paths(
                    value, f"{path}.{key}" if path else str(key)
                )
            )
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
        raise ValueError(  # noqa: TRY004 - preserve actionable config error type
            f"Configuration must be a YAML object, not {type(raw_data)}"
        )

    # Apply environment variable substitutions
    raw_data = _process_dict_substitutions(raw_data)
    unresolved = _unresolved_substitution_paths(raw_data)
    if unresolved:
        raise ValueError(
            "Unresolved environment substitution(s) in YAML: " + ", ".join(unresolved)
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
    specialists = (
        _split_names(specialists_raw) if specialists_raw else list(settings.specialists)
    )

    config = AgentConfig(
        use_case=use_case,
        name="",
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
            schema="GenericAgentResponse"
            if settings.enable_structured_output
            else None,
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
    if tool_names is not None:
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


def _parse_code_execution_config(
    execution_data: dict,
) -> ExecutionCodeExecutionConfig | None:
    """Parse the ``execution.code_execution`` mapping; None when absent."""
    data = execution_data.get("code_execution")
    if data is None:
        return None
    data = _mapping(data, "execution.code_execution")
    _keys(
        data,
        {
            "strategy",
            "docker_host",
            "docker_image",
            "vertex_resource",
            "agent_engine_resource",
            "gke_kubeconfig_path",
            "gke_kubeconfig_context",
        },
        "execution.code_execution",
    )
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
        if value is None:
            value = ""
        _string(value, f"execution.code_execution.{name}")
    return ExecutionCodeExecutionConfig(
        strategy=data.get("strategy", ""),
        docker_host=data.get("docker_host", ""),
        docker_image=data.get("docker_image", ""),
        vertex_resource=data.get("vertex_resource", ""),
        agent_engine_resource=data.get("agent_engine_resource", ""),
        gke_kubeconfig_path=data.get("gke_kubeconfig_path", ""),
        gke_kubeconfig_context=data.get("gke_kubeconfig_context", ""),
    )


_GRAPH_NODE_KEYS = {
    "name",
    "kind",
    "role",
    "retry",
    "timeout",
    "input_schema",
    "output_schema",
    "state_schema",
    "output_key",
    "options",
    "graph",
}
_GRAPH_EDGE_KEYS = {"from", "to", "route"}
_GRAPH_RETRY_KEYS = {
    "max_attempts",
    "initial_delay",
    "max_delay",
    "backoff_factor",
    "jitter",
}
_GRAPH_ROLE_KEYS = {"instruction", "model", "tools"}


def _parse_float(value: Any, name: str) -> float:
    """Validate a positive float from YAML input."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(  # noqa: TRY004 - preserve actionable config error type
            f"{name} must be a number; got {value!r}"
        )
    return float(value)


def _parse_graph_retry(data: dict, path: str) -> RetrySpec:
    """Parse a graph node ``retry`` mapping (field-aligned with RetryConfig)."""
    data = _mapping(data, f"{path}.retry")
    _keys(data, _GRAPH_RETRY_KEYS, f"{path}.retry")
    for name in ("max_attempts",):
        if data.get(name) is not None:
            _positive_int(data[name], f"{path}.retry.{name}")
    for name in ("initial_delay", "max_delay", "backoff_factor", "jitter"):
        if data.get(name) is not None:
            _parse_float(data[name], f"{path}.retry.{name}")
    return RetrySpec(
        max_attempts=data.get("max_attempts"),
        initial_delay=data.get("initial_delay"),
        max_delay=data.get("max_delay"),
        backoff_factor=data.get("backoff_factor"),
        jitter=data.get("jitter"),
    )


def _parse_graph_role(data: dict, path: str) -> RoleConfig:
    """Parse a graph node ``role`` mapping into a RoleConfig."""
    _keys(data, _GRAPH_ROLE_KEYS, f"{path}.role")
    for name in ("instruction", "model"):
        if data.get(name) is not None:
            _string(data[name], f"{path}.role.{name}")
    role_tools = None
    if "tools" in data and data["tools"] is not None:
        role_tools = _string_list(data["tools"], f"{path}.role.tools")
    return RoleConfig(
        instruction=data.get("instruction"),
        model=data.get("model"),
        tools=role_tools,
    )


def _parse_graph_edge(data: Any, path: str) -> GraphEdgeSpec:
    """Parse one graph edge mapping (``{from, to, route}``)."""
    edge = _mapping(data, path)
    _keys(edge, _GRAPH_EDGE_KEYS, path)
    source = _string(edge.get("from", ""), f"{path}.from", allow_empty=False)
    target_raw = edge.get("to")
    target: str | list[str]
    if isinstance(target_raw, list):
        target = _string_list(target_raw, f"{path}.to")
        if not target:
            raise ValueError(f"{path}.to must not be an empty list")
    else:
        target = _string(target_raw, f"{path}.to", allow_empty=False)
    route = edge.get("route")
    return GraphEdgeSpec(source=source, target=target, route=route)


def _parse_graph_node(data: Any, path: str) -> GraphNodeSpec:
    """Parse one graph node mapping."""
    node = _mapping(data, path)
    _keys(node, _GRAPH_NODE_KEYS, path)
    name = _string(node.get("name", ""), f"{path}.name", allow_empty=False)
    kind = _string(node.get("kind", ""), f"{path}.kind", allow_empty=False)

    role = None
    if node.get("role") is not None:
        role = _parse_graph_role(_mapping(node["role"], f"{path}.role"), path)

    retry = (
        _parse_graph_retry(_mapping(node["retry"], f"{path}.retry"), path)
        if node.get("retry") is not None
        else None
    )

    timeout = None
    if node.get("timeout") is not None:
        timeout = _parse_float(node["timeout"], f"{path}.timeout")
        if timeout <= 0:
            raise ValueError(
                f"{path}.timeout must be a positive number; got {timeout!r}"
            )

    for schema_name in ("input_schema", "output_schema", "state_schema"):
        if node.get(schema_name) is not None:
            _string(node[schema_name], f"{path}.{schema_name}")
    output_key = None
    if node.get("output_key") is not None:
        output_key = _string(node["output_key"], f"{path}.output_key")

    options: dict[str, Any] = {}
    if node.get("options") is not None:
        options = dict(_mapping(node["options"], f"{path}.options"))

    nested = None
    if node.get("graph") is not None:
        nested = _parse_graph_spec(node["graph"], f"{path}.graph")

    return GraphNodeSpec(
        name=name,
        kind=kind,
        role=role,
        retry=retry,
        timeout=timeout,
        input_schema=node.get("input_schema"),
        output_schema=node.get("output_schema"),
        state_schema=node.get("state_schema"),
        output_key=output_key,
        options=options,
        graph=nested,
    )


def _parse_loop_mapping(data: Any, path: str) -> LoopSugar:
    """Parse a ``loop`` mapping into a LoopSugar."""
    loop = _mapping(data, path)
    _keys(loop, {"body", "max_iterations"}, path)
    body = _string(loop.get("body", ""), f"{path}.body", allow_empty=False)
    max_iterations = _positive_int(loop.get("max_iterations"), f"{path}.max_iterations")
    return LoopSugar(body=body, max_iterations=max_iterations)


def _parse_sugar_item(data: Any, path: str) -> str | ParallelSugar | LoopSugar:
    """Parse one sequence item: a node name or a nested sugar form."""
    if isinstance(data, str):
        if not data.strip():
            raise ValueError(f"{path} must not be empty")
        return data.strip()
    if isinstance(data, dict):
        _keys(data, {"parallel", "loop", "name"}, path)
        present = [key for key in ("parallel", "loop") if data.get(key) is not None]
        if len(present) > 1:
            raise ValueError(
                f"{path}: exactly one of 'parallel' or 'loop' may be set; got both"
            )
        name = None
        if data.get("name") is not None:
            name = _string(data["name"], f"{path}.name")
        if "parallel" in data:
            names = _string_list(data["parallel"], f"{path}.parallel")
            if len(names) < 2:
                raise ValueError(f"{path}.parallel must have at least two names")
            return ParallelSugar(items=names, name=name)
        if "loop" in data:
            loop = _parse_loop_mapping(data["loop"], f"{path}.loop")
            if name is not None:
                loop.name = name
            return loop
        raise ValueError(
            f"{path} must be a node name or a nested sugar form ('parallel' or 'loop')"
        )
    raise ValueError(
        f"{path} must be a node name string or a sugar mapping; "
        f"got {type(data).__name__}"
    )


def _parse_sugar_form(
    data: dict, path: str, nodes: list[GraphNodeSpec]
) -> SequenceSugar | ParallelSugar | LoopSugar:
    """Parse exactly one top-level sugar form referencing named nodes."""
    present = [
        key for key in ("sequence", "parallel", "loop") if data.get(key) is not None
    ]
    if len(present) != 1:
        raise ValueError(
            f"{path}: exactly one of 'sequence', 'parallel', 'loop' must be "
            f"provided; got {present or 'none'}"
        )
    key = present[0]
    if not isinstance(nodes, list):
        raise ValueError(  # noqa: TRY004 - preserve actionable config error type
            f"{path}.nodes must be a list"
        )
    if key == "sequence":
        items = data["sequence"]
        if not isinstance(items, list) or not items:
            raise ValueError(f"{path}.sequence must be a non-empty list of node names")
        return SequenceSugar(
            items=[
                _parse_sugar_item(item, f"{path}.sequence[{index}]")
                for index, item in enumerate(items)
            ]
        )
    if key == "parallel":
        names = _string_list(data["parallel"], f"{path}.parallel")
        if len(names) < 2:
            raise ValueError(f"{path}.parallel must have at least two names")
        return ParallelSugar(items=names)
    return _parse_loop_mapping(data["loop"], f"{path}.loop")


def _parse_graph_spec(data: Any, path: str = "graph") -> GraphSpec:
    """Parse a recursive graph spec mapping (``nodes`` + ``edges``)."""
    spec = _mapping(data, path)
    _keys(spec, {"nodes", "edges", "sequence", "parallel", "loop"}, path)

    nodes_data = spec.get("nodes", [])
    if not isinstance(nodes_data, list):
        raise ValueError(  # noqa: TRY004 - preserve actionable config error type
            f"{path}.nodes must be a list; got {type(nodes_data).__name__}"
        )
    nodes = [
        _parse_graph_node(item, f"{path}.nodes[{index}]")
        for index, item in enumerate(nodes_data)
    ]

    edges_data = spec.get("edges", [])
    if not isinstance(edges_data, list):
        raise ValueError(  # noqa: TRY004 - preserve actionable config error type
            f"{path}.edges must be a list; got {type(edges_data).__name__}"
        )

    sugar_keys = ("sequence", "parallel", "loop")
    if any(spec.get(key) is not None for key in sugar_keys):
        if edges_data:
            raise ValueError(
                f"{path}: sugar forms ('sequence'/'parallel'/'loop') cannot "
                "be combined with explicit 'edges'"
            )
        sugar = _parse_sugar_form(spec, path, nodes)
        by_name = {node.name: node for node in nodes}
        parsed = expand_sugar(sugar, by_name)
    else:
        edges = [
            _parse_graph_edge(item, f"{path}.edges[{index}]")
            for index, item in enumerate(edges_data)
        ]
        parsed = GraphSpec(nodes=nodes, edges=edges)

    try:
        parsed.validate()
    except ValueError as error:
        raise ValueError(f"{path}: {error}") from error
    return parsed


_POLICY_KEYS = {"approval", "synthesis"}
_APPROVAL_POLICY_KEYS = {"enabled", "gated_tools", "gated_prefixes"}
_SYNTHESIS_POLICY_KEYS = {"enabled", "instruction", "output_key"}


def _parse_policies(data: Any, path: str = "policies") -> PoliciesConfig | None:
    """Parse the ``policies`` section; None when absent."""
    if data is None:
        return None
    data = _mapping(data, path)
    _keys(data, _POLICY_KEYS, path)

    approval = None
    if data.get("approval") is not None:
        section = _mapping(data["approval"], f"{path}.approval")
        _keys(section, _APPROVAL_POLICY_KEYS, f"{path}.approval")
        if "enabled" in section:
            _boolean(section["enabled"], f"{path}.approval.enabled")
        approval = ApprovalPolicyConfig(
            enabled=section.get("enabled", False),
            gated_tools=_string_list(
                section.get("gated_tools", []), f"{path}.approval.gated_tools"
            ),
            gated_prefixes=_string_list(
                section.get("gated_prefixes", []), f"{path}.approval.gated_prefixes"
            ),
        )

    synthesis = None
    if data.get("synthesis") is not None:
        section = _mapping(data["synthesis"], f"{path}.synthesis")
        _keys(section, _SYNTHESIS_POLICY_KEYS, f"{path}.synthesis")
        if "enabled" in section:
            _boolean(section["enabled"], f"{path}.synthesis.enabled")
        instruction = _string(
            section.get("instruction", SYNTHESIZER_INSTRUCTION),
            f"{path}.synthesis.instruction",
        )
        output_key = _string(
            section.get("output_key", SYNTHESIZER_OUTPUT_KEY),
            f"{path}.synthesis.output_key",
        )
        synthesis = SynthesisPolicyConfig(
            enabled=section.get("enabled", False),
            instruction=instruction,
            output_key=output_key,
        )

    return PoliciesConfig(approval=approval, synthesis=synthesis)


def _parse_agent_config(data: dict) -> AgentConfig:
    """Parse raw dictionary into AgentConfig.

    Args:
        data: Raw configuration dictionary.

    Returns:
        Parsed AgentConfig.

    Raises:
        ValueError: If required fields are missing.
    """
    _keys(data, _CONFIG_KEYS, "configuration")
    agent_data = _mapping(data.get("agent", {}), "agent")
    _keys(agent_data, {"use_case", "name", "description"}, "agent")

    use_case_raw = _string(agent_data.get("use_case", ""), "agent.use_case").strip()
    if not use_case_raw:
        raise ValueError("agent.use_case is required")
    use_case = _resolve_use_case_key(use_case_raw)

    model_data = data.get("model", {})
    model_config = None
    if "model" in data and model_data is not None:
        model_data = _mapping(model_data, "model")
        _keys(model_data, {"provider", "name", "api_key", "base_url"}, "model")
        for field_name in ("provider", "name", "api_key", "base_url"):
            if model_data.get(field_name) is not None:
                _string(model_data[field_name], f"model.{field_name}")
        model_config = ModelConfig(
            provider=model_data.get("provider", "google"),
            name=model_data.get("name", ""),
            api_key=model_data.get("api_key"),
            base_url=model_data.get("base_url"),
        )

    instructions_data = data.get("instructions", {})
    instructions_config = None
    if "instructions" in data and instructions_data is not None:
        instructions_data = _mapping(instructions_data, "instructions")
        _keys(instructions_data, {"value", "file"}, "instructions")
        for field_name in ("value", "file"):
            if instructions_data.get(field_name) is not None:
                _string(instructions_data[field_name], f"instructions.{field_name}")
        instructions_config = InstructionsConfig(
            value=instructions_data.get("value", ""),
            file=instructions_data.get("file"),
        )

    tools_data = data.get("tools", {})
    tools_config = None
    if "tools" in data and tools_data is not None:
        tools_data = _mapping(tools_data, "tools")
        _keys(tools_data, {"enabled", "mcp", "openapi", "skills"}, "tools")
        enabled = tools_data.get("enabled")
        if enabled is not None:
            enabled = _string_list(enabled, "tools.enabled")
        mcp_data = tools_data.get("mcp")
        mcp_config = None
        if mcp_data is not None:
            mcp_data = _mapping(mcp_data, "tools.mcp")
            _keys(mcp_data, {"enabled", "tools", "prefix"}, "tools.mcp")
            if "enabled" in mcp_data:
                _boolean(mcp_data["enabled"], "tools.mcp.enabled")
            mcp_tools = _string_list(mcp_data.get("tools", []), "tools.mcp.tools")
            _string(mcp_data.get("prefix", "mcp_"), "tools.mcp.prefix")
            mcp_config = ToolsMcpConfig(
                enabled=mcp_data.get("enabled"),
                tools=mcp_tools,
                prefix=mcp_data.get("prefix", "mcp_"),
            )

        openapi_data = tools_data.get("openapi")
        openapi_config = None
        if openapi_data is not None:
            openapi_data = _mapping(openapi_data, "tools.openapi")
            _keys(
                openapi_data,
                {"enabled", "url", "path", "title", "prefix"},
                "tools.openapi",
            )
            if "enabled" in openapi_data:
                _boolean(openapi_data["enabled"], "tools.openapi.enabled")
            for field_name, default in (
                ("url", ""),
                ("path", "/status"),
                ("title", "Service API"),
                ("prefix", "api_"),
            ):
                _string(
                    openapi_data.get(field_name, default), f"tools.openapi.{field_name}"
                )
            openapi_config = ToolsOpenApiConfig(
                enabled=openapi_data.get("enabled"),
                url=openapi_data.get("url", ""),
                path=openapi_data.get("path", "/status"),
                title=openapi_data.get("title", "Service API"),
                prefix=openapi_data.get("prefix", "api_"),
            )

        skills_data = tools_data.get("skills")
        skills_config = None
        if skills_data is not None:
            skills_data = _mapping(skills_data, "tools.skills")
            _keys(skills_data, {"enabled", "dir", "prefix"}, "tools.skills")
            if "enabled" in skills_data:
                _boolean(skills_data["enabled"], "tools.skills.enabled")
            _string(skills_data.get("dir", ""), "tools.skills.dir")
            _string(skills_data.get("prefix", ""), "tools.skills.prefix")
            skills_config = ToolsSkillsConfig(
                enabled=skills_data.get("enabled"),
                dir=skills_data.get("dir", ""),
                prefix=skills_data.get("prefix", ""),
            )

        tools_config = ToolsConfig(
            enabled=enabled,
            mcp=mcp_config,
            openapi=openapi_config,
            skills=skills_config,
        )

    execution_data = data.get("execution", {})
    execution_config = None
    if "execution" in data and execution_data is not None:
        execution_data = _mapping(execution_data, "execution")
        _keys(
            execution_data,
            {
                "max_iterations",
                "require_approval",
                "steps",
                "workers",
                "specialists",
                "code_execution",
            },
            "execution",
        )
        if "require_approval" in execution_data:
            _boolean(execution_data["require_approval"], "execution.require_approval")
        # Key presence distinguishes "not set" from "explicitly empty": an
        # explicitly empty specialists list is a configuration error (the
        # preset would otherwise silently substitute the default roster).
        specialists: list[str] = []
        if "specialists" in execution_data:
            specialists = _string_list(
                execution_data["specialists"], "execution.specialists"
            )
            if not specialists:
                raise ValueError(
                    "execution.specialists must not be empty; list at least "
                    "one specialist or remove the key to use the default "
                    "roster"
                )
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
            specialists=specialists,
            code_execution=_parse_code_execution_config(execution_data),
        )

    output_data = data.get("output", {})
    output_config = None
    if "output" in data and output_data is not None:
        output_data = _mapping(output_data, "output")
        _keys(output_data, {"schema", "key"}, "output")
        for field_name in ("schema", "key"):
            if output_data.get(field_name) is not None:
                _string(output_data[field_name], f"output.{field_name}")
        output_config = OutputConfig(
            schema=output_data.get("schema"),
            key=output_data.get("key"),
        )

    state_data = data.get("state", {})
    state_config = None
    if "state" in data and state_data is not None:
        state_data = _mapping(state_data, "state")
        _keys(state_data, {"enabled"}, "state")
        _boolean(state_data.get("enabled", True), "state.enabled")
        state_config = StateConfig(enabled=state_data.get("enabled", True))

    roles_data = data.get("roles", {})
    if roles_data is None:
        roles_data = {}
    roles_data = _mapping(roles_data, "roles")
    roles: dict[str, RoleConfig] = {}
    for name, role in roles_data.items():
        role = _mapping(role, f"roles.{name}")
        _keys(role, {"instruction", "model", "tools"}, f"roles.{name}")
        for field_name in ("instruction", "model"):
            if role.get(field_name) is not None:
                _string(role[field_name], f"roles.{name}.{field_name}")
        role_tools = None
        if "tools" in role and role["tools"] is not None:
            role_tools = _string_list(role["tools"], f"roles.{name}.tools")
        roles[str(name)] = RoleConfig(
            instruction=role.get("instruction"),
            model=role.get("model"),
            tools=role_tools,
        )

    graph_config = None
    if data.get("graph") is not None:
        graph_config = _parse_graph_spec(data["graph"])

    policies_config = _parse_policies(data.get("policies"))

    return AgentConfig(
        use_case=use_case,
        name=_string(agent_data.get("name", ""), "agent.name"),
        description=_string(agent_data.get("description", ""), "agent.description"),
        model=model_config,
        instructions=instructions_config,
        tools=tools_config,
        execution=execution_config,
        output=output_config,
        state=state_config,
        roles=roles,
        graph=graph_config,
        policies=policies_config,
    )
