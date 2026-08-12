"""A small, runnable Google ADK agent."""

import os
from pathlib import Path
import re
import sys
import json

from google.adk.agents import Agent, LoopAgent, ParallelAgent, SequentialAgent
from google.adk.code_executors import BuiltInCodeExecutor
from google.adk.tools.mcp_tool import McpToolset, StdioConnectionParams
from google.adk.tools import google_search
from mcp import StdioServerParameters
from pydantic import BaseModel, Field


class AgentResponse(BaseModel):
    """Stable response contract returned by the agent."""

    answer: str = Field(description="The concise answer for the user.")
    used_project_tool: bool = Field(
        description="Whether get_project_info was used to answer the request."
    )


class ReleaseReadinessReport(BaseModel):
    """Structured output for the unified release-readiness use case."""

    answer: str = Field(description="A concise release-readiness conclusion.")
    recommendation: str = Field(
        description="One of: ready, ready_with_conditions, or not_ready."
    )
    confidence: float = Field(description="Confidence from 0.0 to 1.0.")
    risks: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    next_steps: list[str] = Field(default_factory=list)


def get_project_info(topic: str) -> str:
    """Return a short description of this starter project for a requested topic.

    Use this tool when the user asks what this project contains or how to get
    started. It is intentionally local and deterministic so the starter works
    without any external service beyond the model provider.
    """
    topics = {
        "purpose": "This is a minimal Google ADK agent starter project.",
        "run": "Run `adk web` from the project root, then select basic_agent.",
        "structure": "The agent is defined in basic_agent/agent.py and exported as root_agent.",
    }
    normalized_topic = topic.strip().lower()
    return topics.get(
        normalized_topic,
        "Available topics are: purpose, run, and structure.",
    )


PROJECT_KNOWLEDGE = (
    {
        "title": "Agent entry point",
        "content": (
            "The root agent is defined in basic_agent/agent.py as root_agent. "
            "The package also contains specialized research, analysis, and "
            "workflow agents."
        ),
    },
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

MCP_SERVER_PATH = Path(__file__).with_name("mcp_server.py")
project_mcp_toolset = McpToolset(
    connection_params=StdioConnectionParams(
        server_params=StdioServerParameters(
            command=sys.executable,
            args=[str(MCP_SERVER_PATH)],
        ),
    ),
    tool_filter=["get_project_status", "get_release_status"],
    tool_name_prefix="project_mcp_",
)


def retrieve_project_knowledge(query: str) -> str:
    """Retrieve the most relevant project knowledge passages for a query."""
    query_terms = set(re.findall(r"[a-z0-9]+", query.lower()))
    ranked = sorted(
        PROJECT_KNOWLEDGE,
        key=lambda entry: len(
            query_terms
            & set(re.findall(r"[a-z0-9]+", f"{entry['title']} {entry['content']}".lower()))
        ),
        reverse=True,
    )
    matches = [entry for entry in ranked if query_terms & set(re.findall(
        r"[a-z0-9]+", f"{entry['title']} {entry['content']}".lower()
    ))]
    if not matches:
        matches = list(ranked[:1])
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


project_guide_agent = Agent(
    name="project_guide_agent",
    model=os.getenv("ADK_MODEL", "gemini-3.6-flash"),
    description="Explains how this ADK starter project is structured and run.",
    instruction=(
        "You are the project guide. Answer questions about this repository's "
        "purpose, structure, setup, and Docker workflow. Keep answers concise "
        "and factual. Return control to the parent when the question is not "
        "about this project."
    ),
    tools=[get_project_info],
)


project_facts_agent = Agent(
    name="project_facts_agent",
    model=os.getenv("ADK_MODEL", "gemini-3.6-flash"),
    description="Collects factual details about this starter project.",
    instruction=(
        "Collect the key facts needed for a project overview: purpose, agent "
        "entry point, local run command, and Docker run command. Keep the "
        "result factual and concise."
    ),
    tools=[get_project_info],
    output_key="project_facts",
)


project_summary_agent = Agent(
    name="project_summary_agent",
    model=os.getenv("ADK_MODEL", "gemini-3.6-flash"),
    description="Summarizes project facts into a concise project overview.",
    instruction=(
        "Using the facts in {project_facts}, write a concise project overview "
        "for the user. Do not invent details."
    ),
    output_key="project_summary",
)


project_overview_workflow = SequentialAgent(
    name="project_overview_workflow",
    description="Collects project facts and then summarizes them.",
    sub_agents=[project_facts_agent, project_summary_agent],
)


project_structure_agent = Agent(
    name="project_structure_agent",
    model=os.getenv("ADK_MODEL", "gemini-3.6-flash"),
    description="Describes the files and components in this starter project.",
    instruction=(
        "Describe the project's source layout and explain the role of the "
        "agent module, tests, Docker files, and dependency files. Keep it "
        "concise and factual."
    ),
    output_key="project_structure",
)


project_runtime_agent = Agent(
    name="project_runtime_agent",
    model=os.getenv("ADK_MODEL", "gemini-3.6-flash"),
    description="Describes how to run this starter project locally and in Docker.",
    instruction=(
        "Describe the local and Docker commands for running this project, "
        "including the web UI port and required environment configuration. "
        "Keep it concise and factual."
    ),
    output_key="project_runtime",
)


project_parallel_workflow = ParallelAgent(
    name="project_parallel_workflow",
    description="Analyzes project structure and runtime setup in parallel.",
    sub_agents=[project_structure_agent, project_runtime_agent],
)


project_review_agent = Agent(
    name="project_review_agent",
    model=os.getenv("ADK_MODEL", "gemini-3.6-flash"),
    description="Reviews the starter project for clarity and completeness.",
    instruction=(
        "Review the user's project question and identify the most important "
        "facts or gaps to address. Keep the review concise."
    ),
    output_key="project_review",
)


project_refinement_agent = Agent(
    name="project_refinement_agent",
    model=os.getenv("ADK_MODEL", "gemini-3.6-flash"),
    description="Refines a project review into actionable guidance.",
    instruction=(
        "Use the current review in {project_review} to produce a clearer, "
        "more actionable version. Preserve factual accuracy and keep it concise."
    ),
    output_key="project_refined_review",
)


project_review_loop = LoopAgent(
    name="project_review_loop",
    description="Iteratively reviews and refines project guidance.",
    sub_agents=[project_review_agent, project_refinement_agent],
    max_iterations=2,
)


research_agent = Agent(
    name="research_agent",
    model=os.getenv("ADK_MODEL", "gemini-3.6-flash"),
    description="Researches current topics using Google Search.",
    instruction=(
        "You are a research assistant. Use Google Search for questions about "
        "current facts, recent changes, or information outside this repository. "
        "Summarize the results clearly and identify uncertainty when sources "
        "disagree."
    ),
    tools=[google_search],
)


analysis_agent = Agent(
    name="analysis_agent",
    model=os.getenv("ADK_MODEL", "gemini-3.6-flash"),
    description="Performs calculations and small data analyses with code execution.",
    instruction=(
        "You are a data analysis assistant. Use code execution for arithmetic, "
        "data transformations, and checks that benefit from precise computation. "
        "Explain the result briefly and do not execute destructive operations."
    ),
    code_executor=BuiltInCodeExecutor(),
)


knowledge_agent = Agent(
    name="knowledge_agent",
    model=os.getenv("ADK_MODEL", "gemini-3.6-flash"),
    description="Answers project questions using retrieved knowledge passages.",
    instruction=(
        "You are a retrieval-augmented knowledge assistant. Retrieve relevant "
        "project passages first, then answer using only those passages. Say "
        "when the knowledge base does not contain the answer."
    ),
    tools=[retrieve_project_knowledge],
)


mcp_agent = Agent(
    name="mcp_agent",
    model=os.getenv("ADK_MODEL", "gemini-3.6-flash"),
    description="Uses a local MCP server to retrieve project status.",
    instruction=(
        "You are an MCP integration assistant. Use the connected MCP tool when "
        "the user asks for the project's live status or MCP integration details."
    ),
    tools=[project_mcp_toolset],
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
        "or relevant compatibility information. If no external check is needed, "
        "say so explicitly and distinguish facts from assumptions."
    ),
    tools=[google_search],
    output_key="external_findings",
)


release_metrics_agent = Agent(
    name="release_metrics_agent",
    model=os.getenv("ADK_MODEL", "gemini-3.6-flash"),
    description="Analyzes CI metrics using code execution.",
    instruction=(
        "Retrieve the CI metrics, calculate the pass rate and identify blocking "
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
        "Combine the evidence from {release_requirements}, {external_findings}, "
        "{test_metrics}, and {service_status}. Produce a release recommendation "
        "with risks, evidence, confidence, and next steps. Use recommendation "
        "values ready, ready_with_conditions, or not_ready."
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
        "this project is ready to release, delegate to "
        "release_readiness_workflow. Answer clearly and briefly for other "
        "questions. "
        "Delegate repository-specific questions to project_guide_agent. "
        "For a complete project overview, delegate to "
        "project_overview_workflow. "
        "For a detailed structure-and-runtime review, delegate to "
        "project_parallel_workflow. "
        "For iterative review and refinement, delegate to project_review_loop. "
        "For current or external information, delegate to research_agent. "
        "For calculations or data analysis, delegate to analysis_agent. "
        "For questions about documented project knowledge, delegate to "
        "knowledge_agent. "
        "For MCP-backed project status, delegate to mcp_agent. "
        "Return only the structured response described by the response schema."
    ),
    tools=[get_project_info],
    sub_agents=[
        project_guide_agent,
        project_overview_workflow,
        project_parallel_workflow,
        project_review_loop,
        research_agent,
        analysis_agent,
        knowledge_agent,
        mcp_agent,
        release_readiness_workflow,
    ],
    output_schema=ReleaseReadinessReport,
    output_key="last_response",
)
