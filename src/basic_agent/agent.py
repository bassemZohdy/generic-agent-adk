"""Generic configuration-driven Google ADK agent."""

from __future__ import annotations

import json
from pathlib import Path
import os
import re
import sys
import logging
from typing import Any

from google.adk.agents import Agent, BaseAgent
from google.adk.code_executors import BuiltInCodeExecutor
from google.adk.plugins import BasePlugin
from google.adk.tools import google_search
from google.adk.tools.mcp_tool import McpToolset, StdioConnectionParams
from google.adk.tools.openapi_tool import OpenAPIToolset
from google.adk.tools.tool_context import ToolContext
from mcp import StdioServerParameters
from pydantic import BaseModel, Field

from .autoconfig import CapabilityProvider, discover_capabilities
from .config import settings
from .config_loader import (
    AgentConfig,
    apply_env_overrides,
    load_config_from_env,
    load_config_from_yaml,
    log_config_provenance,
)
from .strategies.base import RuntimeContext
from .telemetry import invocation_attributes, tracer
from .use_cases import get_default_registry

logger = logging.getLogger(__name__)


class GenericAgentResponse(BaseModel):
    """Stable response envelope shared by all configured agent use cases."""

    answer: str = Field(description="The direct answer to the user's request.")
    confidence: float = Field(description="Confidence from 0.0 to 1.0.")
    evidence: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    next_steps: list[str] = Field(default_factory=list)


class AgentState(BaseModel):
    """Generic state contract; custom state keys remain available in ADK state."""

    last_response: Any = None


class GenericAgent(Agent):
    """Configurable root agent with no domain-specific workflow assumptions."""

    domain: str = "generic"


class GenericAgentPlugin(BasePlugin):
    """Runtime observability and capability discovery plugin."""

    def __init__(self) -> None:
        super().__init__(name=settings.plugin_name)
        self.capabilities: dict[str, CapabilityProvider] = discover_capabilities()
        self._spans: dict[str, Any] = {}

    async def before_run_callback(self, *, invocation_context):
        if not self.capabilities:
            self.capabilities = discover_capabilities()
        span = tracer.start_span(
            f"{settings.app_name}.invocation",
            attributes=invocation_attributes(invocation_context),
        )
        span.set_attribute(
            "adk.capabilities",
            ",".join(
                f"{name}:{provider.strategy}"
                for name, provider in self.capabilities.items()
            ),
        )
        self._spans[invocation_context.invocation_id] = span
        logger.info("Agent invocation started: %s", invocation_context.invocation_id)

    async def after_run_callback(self, *, invocation_context) -> None:
        if span := self._spans.pop(invocation_context.invocation_id, None):
            span.end()
        logger.info("Agent invocation completed: %s", invocation_context.invocation_id)


def _knowledge_entries() -> list[dict[str, str]]:
    if not settings.knowledge_file:
        return []
    path = Path(settings.knowledge_file).expanduser()
    if not path.exists():
        return []
    if path.suffix.lower() == ".json":
        content = json.loads(path.read_text(encoding="utf-8"))
        return content if isinstance(content, list) else []
    return [{"title": path.name, "content": path.read_text(encoding="utf-8")}]


def retrieve_knowledge(query: str) -> str:
    """Retrieve relevant passages from the externally configured knowledge file."""
    entries = _knowledge_entries()
    if not entries:
        return "No external knowledge source is configured."
    terms = set(re.findall(r"[a-z0-9]+", query.lower()))

    def score(entry: dict[str, str]) -> int:
        words = set(re.findall(r"[a-z0-9]+", json.dumps(entry).lower()))
        return len(terms & words)

    ranked = sorted(entries, key=score, reverse=True)
    matches = [entry for entry in ranked if score(entry)] or ranked[:1]
    return "\n\n".join(
        f"[{entry.get('title', 'knowledge')}] {entry.get('content', '')}"
        for entry in matches[: settings.knowledge_result_limit]
    )


def inspect_runtime() -> str:
    """Return the active external configuration and detected capability strategies."""
    return json.dumps(
        {
            "agent": settings.app_name,
            "model": settings.model,
            "enabled_tools": settings.enabled_tools,
            "capabilities": {
                name: provider.strategy
                for name, provider in discover_capabilities().items()
            },
        }
    )


def request_approval(action: str, tool_context: ToolContext) -> str:
    """Require configured human confirmation before an irreversible action."""
    if not tool_context.tool_confirmation:
        tool_context.request_confirmation(
            hint=f"Confirm this action: {action}", payload={"action": action}
        )
        return "Confirmation requested before continuing."
    return "Action confirmed." if tool_context.tool_confirmation.confirmed else "Action rejected."


def api_headers(_context) -> dict[str, str]:
    return {"x-api-key": settings.service_api_key} if settings.service_api_key else {}


MCP_SERVER_PATH = Path(__file__).with_name("mcp_server.py")
project_mcp_toolset = McpToolset(
    connection_params=StdioConnectionParams(
        server_params=StdioServerParameters(
            command=sys.executable, args=[str(MCP_SERVER_PATH)]
        )
    ),
    tool_filter=settings.mcp_tools or None,
    tool_name_prefix=settings.mcp_tool_prefix,
)

openapi_toolset = OpenAPIToolset(
    spec_dict={
        "openapi": "3.0.3",
        "info": {"title": settings.openapi_title, "version": settings.app_version},
        "servers": [{"url": settings.service_api_url}],
        "paths": {
            settings.openapi_path: {
                "get": {
                    "operationId": "getConfiguredServiceStatus",
                    "summary": "Get configured service status",
                    "responses": {"200": {"description": "Service status"}},
                }
            }
        },
    },
    header_provider=api_headers,
    tool_name_prefix=settings.openapi_tool_prefix,
)

tools: list[Any] = [inspect_runtime, request_approval]
if settings.enable_knowledge:
    tools.append(retrieve_knowledge)
if settings.enable_search:
    tools.append(google_search)
if settings.enable_mcp:
    tools.append(project_mcp_toolset)
if settings.enable_openapi:
    tools.append(openapi_toolset)

application_integration_toolset = None
if settings.enable_application_integration and settings.gcp_project and settings.gcp_integration:
    from google.adk.tools.application_integration_tool import ApplicationIntegrationToolset

    application_integration_toolset = ApplicationIntegrationToolset(
        project=settings.gcp_project,
        location=settings.gcp_location,
        integration=settings.gcp_integration,
        triggers=settings.gcp_triggers or None,
        tool_name_prefix=settings.application_tool_prefix,
        tool_instructions=settings.application_tool_instructions,
    )
    tools.append(application_integration_toolset)

DEFAULT_CONFIG_FILE = "/app/config/agent.yaml"

#: Fixed config tool names -> constructed tool objects (functions by name).
_TOOL_NAME_MAP: dict[str, Any] = {
    "mcp": project_mcp_toolset,
    "openapi": openapi_toolset,
    "runtime": inspect_runtime,
    "approval": request_approval,
    "knowledge": retrieve_knowledge,
    "search": google_search,
}
if application_integration_toolset is not None:
    _TOOL_NAME_MAP["application_integration"] = application_integration_toolset

# Capability flags (and unconstructed optional toolsets) are not tools.
_SILENT_TOOL_NAMES = {"code_execution", "structured_output"}
if application_integration_toolset is None:
    _SILENT_TOOL_NAMES.add("application_integration")


def _active_config_path() -> str | None:
    """Return the YAML config path to use, or None for the env-only path."""
    path = os.environ.get("AGENT_CONFIG_FILE")
    if path:
        return path
    return DEFAULT_CONFIG_FILE if os.path.exists(DEFAULT_CONFIG_FILE) else None


def resolve_agent_config() -> AgentConfig:
    """Resolve the runtime agent config: YAML file when available, else env only.

    ``AGENT_CONFIG_FILE`` wins; ``/app/config/agent.yaml`` is auto-detected.
    An explicitly configured but missing file raises FileNotFoundError rather
    than silently falling back to env.
    """
    path = _active_config_path()
    if path is not None:
        return apply_env_overrides(load_config_from_yaml(path), config_path=path)
    config = load_config_from_env()
    log_config_provenance(None, (), config.use_case or "assistant")
    return config


def _build_runtime_context(config: AgentConfig) -> RuntimeContext:
    """Build the shared RuntimeContext from the resolved config."""
    configured = (
        list(config.tools.enabled)
        if config.tools and config.tools.enabled
        else list(settings.enabled_tools)
    )
    runtime_tools: list[Any] = []
    for name in configured:
        if name in _SILENT_TOOL_NAMES:
            continue
        tool = _TOOL_NAME_MAP.get(name)
        if tool is None:
            logger.warning("Unknown tool %r in config; skipping", name)
            continue
        runtime_tools.append(tool)

    execution = config.execution
    return RuntimeContext(
        model=(config.model.name if config.model else "") or settings.model,
        instruction=(config.instructions.value if config.instructions else "")
        or settings.agent_instruction,
        tools=runtime_tools,
        description=config.description or settings.agent_description,
        code_executor=BuiltInCodeExecutor() if "code_execution" in configured else None,
        state_schema=AgentState,
        output_schema=GenericAgentResponse if "structured_output" in configured else None,
        output_key="last_response",
        before_agent_callback=lambda context: logger.info(
            "Agent started: %s", context.invocation_id
        ),
        after_agent_callback=lambda context: logger.info(
            "Agent completed: %s", context.invocation_id
        ),
        max_iterations=execution.max_iterations if execution else 3,
        require_approval=execution.require_approval if execution else False,
        specialists=tuple(execution.specialists) if execution else (),
        roles=dict(config.roles),
    )


def _build_root_agent(config: AgentConfig, source: str) -> BaseAgent:
    """Resolve the configured use case and build the root ADK agent tree."""
    runtime = _build_runtime_context(config)
    canonical, use_case_agent = get_default_registry().resolve(
        config.use_case or "assistant"
    )
    logger.info("resolved use_case=%s (source: %s)", canonical, source)
    return use_case_agent.build(runtime)


_config = resolve_agent_config()
root_agent = _build_root_agent(_config, "yaml" if _active_config_path() else "env")

# Back-compat alias: anything importing the generic root keeps working.
generic_root_agent = root_agent
