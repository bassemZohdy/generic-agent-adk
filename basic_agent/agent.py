"""A small, runnable Google ADK agent."""

import os

from google.adk.agents import Agent
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


root_agent = Agent(
    name="basic_agent",
    model=os.getenv("ADK_MODEL", "gemini-3.6-flash"),
    description="A concise, helpful starter agent built with Google ADK.",
    instruction=(
        "You are a helpful starter agent. Answer clearly and briefly. "
        "Delegate repository-specific questions to project_guide_agent. "
        "Return only the structured response described by the response schema."
    ),
    tools=[get_project_info],
    sub_agents=[project_guide_agent],
    output_schema=AgentResponse,
    output_key="last_response",
)
