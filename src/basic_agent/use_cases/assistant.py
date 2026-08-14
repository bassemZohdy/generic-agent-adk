"""Assistant use case: simple one-shot Q&A."""

from __future__ import annotations

from ..strategies import DirectStrategy
from .base import BaseUseCaseAgent


class AssistantAgent(BaseUseCaseAgent):
    """Direct assistant that answers a question in one shot."""

    use_case = "assistant"
    title = "Assistant"
    when_to_use = "You want simple one-shot answers or conversations with no multi-step orchestration."
    aliases = ("generic", "direct")
    strategy = DirectStrategy()
