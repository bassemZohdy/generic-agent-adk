"""Research assistant use case: investigates with tools."""

from __future__ import annotations

from .base import BaseUseCaseAgent
from ..strategies import ReactStrategy


class ResearchAssistantAgent(BaseUseCaseAgent):
    """Tool-using agent that searches and investigates to answer questions."""

    use_case = "research_assistant"
    title = "Research Assistant"
    when_to_use = "You want the agent to search, read, and investigate with tools before answering."
    aliases = ("react",)
    strategy = ReactStrategy()
