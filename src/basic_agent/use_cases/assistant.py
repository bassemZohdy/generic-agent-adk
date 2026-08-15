"""Assistant use case: one-shot Q&A, tool-use when tools are enabled."""

from __future__ import annotations

from ..strategies import DirectStrategy
from .base import BaseUseCaseAgent


class AssistantAgent(BaseUseCaseAgent):
    """Answers questions directly; searches and investigates when tools are enabled."""

    use_case = "assistant"
    title = "Assistant"
    when_to_use = "You want questions answered directly, with optional tool-based search and investigation."
    aliases = ()
    interfaces = ("rest", "web", "cli", "live")
    strategy = DirectStrategy()
