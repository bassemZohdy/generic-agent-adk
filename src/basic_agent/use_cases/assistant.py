"""Assistant use case: one-shot Q&A, tool-use when tools are enabled."""

from __future__ import annotations

from ..strategies import DirectStrategy
from .base import BaseUseCaseAgent


class AssistantAgent(BaseUseCaseAgent):
    """Answers questions directly; searches and investigates when tools are enabled.

    Merged with the former ``research_assistant`` use case (kept as an alias):
    with no tools the agent answers in one shot; with tools enabled the ADK
    reasoning loop iterates over them — same builder either way.
    """

    use_case = "assistant"
    title = "Assistant"
    when_to_use = "You want questions answered directly, with optional tool-based search and investigation."
    aliases = ("generic", "direct", "react", "research_assistant")
    interfaces = ("rest", "web", "cli", "live")
    strategy = DirectStrategy()
