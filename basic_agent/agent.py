"""Generic configuration-driven Google ADK agent."""

from __future__ import annotations

import json
from pathlib import Path
import re
import sys
import logging
from typing import Any

from google.adk.agents import Agent
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
from .telemetry import invocation_attributes, tracer

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

root_agent = GenericAgent(
    name=settings.app_name,
    model=settings.model,
    description=settings.agent_description,
    instruction=settings.agent_instruction,
    tools=tools,
    code_executor=BuiltInCodeExecutor() if settings.enable_code_execution else None,
    state_schema=AgentState,
    before_agent_callback=lambda context: logger.info(
        "Agent started: %s", context.invocation_id
    ),
    after_agent_callback=lambda context: logger.info(
        "Agent completed: %s", context.invocation_id
    ),
    output_schema=GenericAgentResponse if settings.enable_structured_output else None,
    output_key="last_response",
)

# Pattern modules import the shared tools above, so selection occurs only after
# the generic agent and tool graph have been constructed.
generic_root_agent = root_agent
from .patterns import selected_pattern_agent  # noqa: E402

if selected_pattern_agent is not None:
    root_agent = selected_pattern_agent
