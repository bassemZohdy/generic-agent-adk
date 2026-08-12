"""A small, runnable Google ADK agent."""

import os

from google.adk.agents import Agent


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


root_agent = Agent(
    name="basic_agent",
    model=os.getenv("ADK_MODEL", "gemini-3.6-flash"),
    description="A concise, helpful starter agent built with Google ADK.",
    instruction=(
        "You are a helpful starter agent. Answer clearly and briefly. "
        "If the user asks about this project, use get_project_info when useful."
    ),
    tools=[get_project_info],
)
