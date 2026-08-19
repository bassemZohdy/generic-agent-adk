"""Expert dispatch use case: route question types to specialists."""

from __future__ import annotations

from typing import ClassVar

from ..strategies import RouterStrategy
from .base import BaseUseCaseAgent


class ExpertDispatchAgent(BaseUseCaseAgent):
    """Routes each request to the best-matching specialist agent."""

    use_case = "expert_dispatch"
    title = "Expert Dispatch"
    when_to_use = "You want each incoming question routed to the right specialist out of a fixed roster."
    aliases = ()
    defaults: ClassVar[dict] = {"specialists": ("research", "solution", "risk")}
    strategy = RouterStrategy()
