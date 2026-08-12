"""Release-readiness coordinator built with Google ADK."""

import json
import os
from pathlib import Path
import re
import sys

from google.adk.agents import Agent, LoopAgent, ParallelAgent, SequentialAgent
from google.adk.code_executors import BuiltInCodeExecutor
from google.adk.tools import google_search
from google.adk.tools.mcp_tool import McpToolset, StdioConnectionParams
from mcp import StdioServerParameters
from pydantic import BaseModel, Field


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
    tools=[project_mcp_toolset],
    output_key="service_status",
)


release_evidence_workflow = ParallelAgent(
    name="release_evidence_workflow",
    description="Gathers release evidence from docs, web, metrics, and operations.",
    sub_agents=[
        release_knowledge_agent,
        release_research_agent,
        release_metrics_agent,
        release_operations_agent,
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


root_agent = Agent(
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
    output_schema=ReleaseReadinessReport,
    output_key="last_response",
)
