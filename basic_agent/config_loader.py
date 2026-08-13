"""Load and validate externalized agent configurations."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


@dataclass
class ModelConfig:
    """Model configuration."""

    provider: str
    name: str
    api_key: str | None = None


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
class ExecutionConfig:
    """Execution configuration."""

    max_iterations: int = 3
    require_approval: bool = False
    steps: int | None = None
    workers: int | None = None
    specialists: list[str] = field(default_factory=list)


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

    type: str
    name: str = ""
    description: str = ""
    model: ModelConfig | None = None
    instructions: InstructionsConfig | None = None
    tools: ToolsConfig | None = None
    execution: ExecutionConfig | None = None
    output: OutputConfig | None = None
    state: StateConfig | None = None

    def validate(self) -> None:
        """Validate configuration coherence.

        Raises:
            ValueError: If configuration is invalid.
        """
        if not self.type:
            raise ValueError("agent.type is required")

        if self.type == "ROUTER" and (
            not self.execution or not self.execution.specialists
        ):
            raise ValueError("ROUTER agent requires execution.specialists")

        if self.type == "HUMAN_IN_LOOP" and (
            not self.execution or not self.execution.require_approval
        ):
            raise ValueError(
                "HUMAN_IN_LOOP agent requires execution.require_approval=true"
            )

        if self.type in ("LOOP", "EVALUATOR_OPTIMIZER") and (
            not self.execution or self.execution.max_iterations < 1
        ):
            raise ValueError(
                f"{self.type} agent requires execution.max_iterations >= 1"
            )


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

    # Parse into dataclasses
    config = _parse_agent_config(raw_data)
    config.validate()

    logger.info("Configuration loaded: agent_type=%s", config.type)
    return config


def load_config_from_env() -> AgentConfig:
    """Load agent configuration from environment variables.

    For backward compatibility, creates a config from existing ADK env vars.

    Returns:
        AgentConfig populated from environment.
    """
    from .config import settings

    config = AgentConfig(
        type=settings.agent_pattern.value.upper(),
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
            max_iterations=settings.pattern_max_iterations,
            require_approval=settings.pattern_require_approval,
            specialists=list(settings.pattern_specialists),
        ),
        output=OutputConfig(
            schema="GenericAgentResponse" if settings.enable_structured_output else None,
            key="last_response",
        ),
        state=StateConfig(enabled=True),
    )

    config.validate()
    return config


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

    model_data = data.get("model", {})
    model_config = None
    if model_data:
        model_config = ModelConfig(
            provider=model_data.get("provider", "google"),
            name=model_data.get("name", ""),
            api_key=model_data.get("api_key"),
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

        tools_config = ToolsConfig(
            enabled=tools_data.get("enabled", []),
            mcp=mcp_config,
            openapi=openapi_config,
        )

    execution_data = data.get("execution", {})
    execution_config = None
    if execution_data:
        execution_config = ExecutionConfig(
            max_iterations=execution_data.get("max_iterations", 3),
            require_approval=execution_data.get("require_approval", False),
            steps=execution_data.get("steps"),
            workers=execution_data.get("workers"),
            specialists=execution_data.get("specialists", []),
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

    return AgentConfig(
        type=agent_data.get("type", "DIRECT").upper(),
        name=agent_data.get("name", ""),
        description=agent_data.get("description", ""),
        model=model_config,
        instructions=instructions_config,
        tools=tools_config,
        execution=execution_config,
        output=output_config,
        state=state_config,
    )
