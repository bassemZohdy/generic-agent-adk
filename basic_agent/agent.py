"""Release-readiness coordinator built with Google ADK."""

import json
import os
from pathlib import Path
import re
import sys
import logging
from typing import Any

from google.adk.agents import Agent, LoopAgent, ParallelAgent, SequentialAgent
from google.adk.agents.context import Context
from google.adk.code_executors import BuiltInCodeExecutor
from google.adk.tools import google_search
from google.adk.tools.mcp_tool import McpToolset, StdioConnectionParams
from google.adk.tools.openapi_tool import OpenAPIToolset
from google.adk.tools.tool_context import ToolContext
from google.adk.plugins import BasePlugin
from mcp import StdioServerParameters
from pydantic import BaseModel, Field

from .autoconfig import CapabilityProvider, discover_capabilities
from .telemetry import invocation_attributes, tracer

logger = logging.getLogger(__name__)


class ReleaseReadinessPlugin(BasePlugin):
    """Global plugin for release-assessment observability."""

    def __init__(self) -> None:
        super().__init__(name="release_readiness_plugin")
        self.capabilities: dict[str, CapabilityProvider] = discover_capabilities()
        self._spans: dict[str, Any] = {}

    async def before_run_callback(self, *, invocation_context):
        if not self.capabilities:
            self.capabilities = discover_capabilities()
        span = tracer.start_span(
            "adk.release_readiness.invocation",
            attributes=invocation_attributes(invocation_context),
        )
        span.set_attribute("adk.capabilities", ",".join(
            f"{name}:{provider.strategy}"
            for name, provider in self.capabilities.items()
        ))
        self._spans[invocation_context.invocation_id] = span
        logger.info("Release plugin started invocation %s", invocation_context.invocation_id)

    async def after_run_callback(self, *, invocation_context) -> None:
        if span := self._spans.pop(invocation_context.invocation_id, None):
            span.end()
        logger.info("Release plugin completed invocation %s", invocation_context.invocation_id)


class ReleaseReadinessReport(BaseModel):
    """Structured output for the release-readiness use case."""

    answer: str = Field(description="A concise release-readiness conclusion.")
    recommendation: str = Field(
        description="One of: ready, ready_with_conditions, or not_ready."
    )
    confidence: float = Field(description="Confidence from 0.0 to 1.0.")
    risks: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    next_steps: list[str] = Field(default_factory=list)


class ReleaseReadinessAgent(Agent):
    """Domain-specific specialization of the existing root ADK agent."""

    domain: str = "release_readiness"


class ReleaseWorkflowState(BaseModel):
    """Typed state contract shared by the release workflow."""

    release_requirements: Any = None
    external_findings: Any = None
    test_metrics: Any = None
    service_status: Any = None
    api_status: Any = None
    release_draft: Any = None
    release_review: Any = None
    last_response: Any = None


def on_release_workflow_start(context: Context) -> None:
    """Record the start of a release assessment for ADK diagnostics."""
    logger.info("Starting release-readiness assessment: %s", context.invocation_id)


async def on_release_workflow_complete(context: Context) -> None:
    """Record completion of a release assessment for ADK diagnostics."""
    logger.info("Completed release-readiness assessment: %s", context.invocation_id)
    await context.add_session_to_memory()


def request_release_approval(
    recommendation: str,
    tool_context: ToolContext,
) -> str:
    """Request human confirmation before recording a release decision."""
    allowed = {"ready", "ready_with_conditions", "not_ready"}
    if recommendation not in allowed:
        return f"Invalid recommendation. Choose one of: {', '.join(sorted(allowed))}."
    if not tool_context.tool_confirmation:
        tool_context.request_confirmation(
            hint="Confirm recording this release recommendation.",
            payload={"recommendation": recommendation},
        )
        return "Confirmation requested before recording the release recommendation."
    if not tool_context.tool_confirmation.confirmed:
        return "Release recommendation was not confirmed."
    return f"Release recommendation recorded: {recommendation}."


PROJECT_KNOWLEDGE = (
    {
        "title": "Local development",
        "content": (
            "Run uv sync, configure GOOGLE_API_KEY in .env, and start the web "
            "interface with uv run adk web."
        ),
    },
    {
        "title": "Docker deployment",
        "content": (
            "Run docker compose up --build to start the ADK Web UI on port 8000. "
            "ADK_PORT changes the host port."
        ),
    },
    {
        "title": "Release readiness criteria",
        "content": (
            "A release is ready when automated tests pass, no blocking risks "
            "are identified, required documentation is present, and the live "
            "service status is healthy. A release with non-blocking risks is "
            "ready with conditions."
        ),
    },
)


def retrieve_project_knowledge(query: str) -> str:
    """Retrieve the most relevant release/runbook passages for a query."""
    query_terms = set(re.findall(r"[a-z0-9]+", query.lower()))

    def score(entry: dict[str, str]) -> int:
        words = set(re.findall(r"[a-z0-9]+", f"{entry['title']} {entry['content']}".lower()))
        return len(query_terms & words)

    ranked = sorted(PROJECT_KNOWLEDGE, key=score, reverse=True)
    matches = [entry for entry in ranked if score(entry)] or ranked[:1]
    return "\n\n".join(
        f"[{entry['title']}] {entry['content']}" for entry in matches[:2]
    )


def get_release_metrics() -> str:
    """Return deterministic sample CI metrics for local release analysis."""
    return json.dumps(
        {
            "total_tests": 120,
            "passed_tests": 118,
            "failed_tests": 2,
            "critical_failures": 0,
            "coverage_percent": 87.5,
        }
    )


def release_api_headers(_context) -> dict[str, str]:
    """Provide the optional API key to the OpenAPI release service."""
    api_key = os.getenv("RELEASE_API_KEY")
    return {"x-api-key": api_key} if api_key else {}


MCP_SERVER_PATH = Path(__file__).with_name("mcp_server.py")
project_mcp_toolset = McpToolset(
    connection_params=StdioConnectionParams(
        server_params=StdioServerParameters(
            command=sys.executable,
            args=[str(MCP_SERVER_PATH)],
        ),
    ),
    tool_filter=["get_release_status"],
    tool_name_prefix="release_mcp_",
)

release_api_toolset = OpenAPIToolset(
    spec_dict={
        "openapi": "3.0.3",
        "info": {"title": "Release Status API", "version": "0.1.0"},
        "servers": [
            {"url": os.getenv("RELEASE_API_URL", "http://127.0.0.1:8001")}
        ],
        "paths": {
            "/release/status": {
                "get": {
                    "operationId": "getReleaseStatus",
                    "summary": "Get current release service status",
                    "responses": {
                        "200": {
                            "description": "Current service status",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "additionalProperties": {"type": "string"},
                                    }
                                }
                            },
                        }
                    },
                }
            }
        },
        "components": {
            "securitySchemes": {
                "releaseApiKey": {
                    "type": "apiKey",
                    "in": "header",
                    "name": "x-api-key",
                }
            }
        },
    },
    header_provider=release_api_headers,
    tool_name_prefix="release_api_",
)

application_integration_toolset = None
if os.getenv("GCP_INTEGRATION") and os.getenv("GOOGLE_CLOUD_PROJECT"):
    from google.adk.tools.application_integration_tool import (
        ApplicationIntegrationToolset,
    )

    application_integration_toolset = ApplicationIntegrationToolset(
        project=os.environ["GOOGLE_CLOUD_PROJECT"],
        location=os.getenv("GCP_LOCATION", "us-central1"),
        integration=os.environ["GCP_INTEGRATION"],
        triggers=os.getenv("GCP_INTEGRATION_TRIGGERS", "").split(",") or None,
        tool_name_prefix="release_integration_",
        tool_instructions=(
            "Use this integration only for release operations explicitly "
            "requested by the user."
        ),
    )


release_knowledge_agent = Agent(
    name="release_knowledge_agent",
    model=os.getenv("ADK_MODEL", "gemini-3.6-flash"),
    description="Retrieves release requirements and project runbook evidence.",
    instruction=(
        "Retrieve the release readiness criteria and relevant project runbook "
        "passages. Return the evidence without inventing requirements."
    ),
    tools=[retrieve_project_knowledge],
    output_key="release_requirements",
)


release_research_agent = Agent(
    name="release_research_agent",
    model=os.getenv("ADK_MODEL", "gemini-3.6-flash"),
    description="Checks current external release and dependency information.",
    instruction=(
        "Use Google Search to check current release risks, dependency advisories, "
        "or relevant compatibility information. Distinguish facts from assumptions."
    ),
    tools=[google_search],
    output_key="external_findings",
)


release_metrics_agent = Agent(
    name="release_metrics_agent",
    model=os.getenv("ADK_MODEL", "gemini-3.6-flash"),
    description="Analyzes CI metrics using code execution.",
    instruction=(
        "Retrieve the CI metrics, calculate the pass rate, and identify blocking "
        "test risks using code execution. Return the calculations and conclusion."
    ),
    tools=[get_release_metrics],
    code_executor=BuiltInCodeExecutor(),
    output_key="test_metrics",
)


release_operations_agent = Agent(
    name="release_operations_agent",
    model=os.getenv("ADK_MODEL", "gemini-3.6-flash"),
    description="Checks live service health through MCP.",
    instruction=(
        "Use the MCP release-status tool to check service health, deployed version, "
        "and environment. Return the observed status without guessing."
    ),
    tools=[
        project_mcp_toolset,
        request_release_approval,
        *([application_integration_toolset] if application_integration_toolset else []),
    ],
    output_key="service_status",
)


release_api_agent = Agent(
    name="release_api_agent",
    model=os.getenv("ADK_MODEL", "gemini-3.6-flash"),
    description="Checks release status through a documented OpenAPI service.",
    instruction=(
        "Call the OpenAPI release-status operation to retrieve the current "
        "service status. Return the observed API response without guessing."
    ),
    tools=[release_api_toolset],
    output_key="api_status",
)


release_evidence_workflow = ParallelAgent(
    name="release_evidence_workflow",
    description="Gathers release evidence from docs, web, metrics, and operations.",
    sub_agents=[
        release_knowledge_agent,
        release_research_agent,
        release_metrics_agent,
        release_operations_agent,
        release_api_agent,
    ],
)


release_synthesis_agent = Agent(
    name="release_synthesis_agent",
    model=os.getenv("ADK_MODEL", "gemini-3.6-flash"),
    description="Synthesizes release evidence into a recommendation.",
    instruction=(
        "Combine {release_requirements}, {external_findings}, {test_metrics}, "
        "and {service_status}. Produce a recommendation with risks, evidence, "
        "confidence, and next steps. Use recommendation values ready, "
        "ready_with_conditions, or not_ready."
    ),
    output_key="release_draft",
)


release_review_agent = Agent(
    name="release_review_agent",
    model=os.getenv("ADK_MODEL", "gemini-3.6-flash"),
    description="Critiques a release-readiness recommendation.",
    instruction=(
        "Review {release_draft} for unsupported claims, missing evidence, and "
        "incorrect readiness conclusions. List only concrete corrections."
    ),
    output_key="release_review",
)


release_refinement_agent = Agent(
    name="release_refinement_agent",
    model=os.getenv("ADK_MODEL", "gemini-3.6-flash"),
    description="Refines a release recommendation after critique.",
    instruction=(
        "Use {release_draft} and {release_review} to produce a corrected, concise "
        "release recommendation. Preserve evidence and resolve unsupported claims."
    ),
    output_key="release_draft",
)


release_review_loop = LoopAgent(
    name="release_review_loop",
    description="Reviews and refines the release recommendation twice.",
    sub_agents=[release_review_agent, release_refinement_agent],
    max_iterations=2,
)


release_readiness_workflow = SequentialAgent(
    name="release_readiness_workflow",
    description="Runs the complete release-readiness assessment.",
    sub_agents=[
        release_evidence_workflow,
        release_synthesis_agent,
        release_review_loop,
    ],
)


root_agent = ReleaseReadinessAgent(
    name="basic_agent",
    model=os.getenv("ADK_MODEL", "gemini-3.6-flash"),
    description="A release-readiness coordinator built with Google ADK.",
    instruction=(
        "You are a release-readiness coordinator. For questions about whether "
        "a project or version is ready to release, delegate to "
        "release_readiness_workflow. For other questions, explain that this "
        "agent is focused on release readiness. Return only the structured "
        "response described by the response schema."
    ),
    sub_agents=[release_readiness_workflow],
    state_schema=ReleaseWorkflowState,
    before_agent_callback=on_release_workflow_start,
    after_agent_callback=on_release_workflow_complete,
    output_schema=ReleaseReadinessReport,
    output_key="last_response",
)
