"""A small, runnable Google ADK agent."""

import os

from google.adk.agents import Agent, SequentialAgent
from pydantic import BaseModel, Field


class AgentResponse(BaseModel):
    """Stable response contract returned by the agent."""

    answer: str = Field(description="The concise answer for the user.")
    used_project_tool: bool = Field(
        description="Whether get_project_info was used to answer the request."
    )


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


root_agent = Agent(
    name="basic_agent",
    model=os.getenv("ADK_MODEL", "gemini-3.6-flash"),
    description="A concise, helpful starter agent built with Google ADK.",
    instruction=(
        "You are a helpful starter agent. Answer clearly and briefly. "
        "Delegate repository-specific questions to project_guide_agent. "
        "For a complete project overview, delegate to "
        "project_overview_workflow. "
        "Return only the structured response described by the response schema."
    ),
    tools=[get_project_info],
    sub_agents=[project_guide_agent, project_overview_workflow],
    output_schema=AgentResponse,
    output_key="last_response",
)
