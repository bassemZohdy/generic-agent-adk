"""Refine-until-good use case: evaluator/optimizer quality loop."""

from __future__ import annotations

from .base import BaseUseCaseAgent
from ..strategies import EvaluatorOptimizerStrategy


class RefineUntilGoodAgent(BaseUseCaseAgent):
    """Improves output iteratively until it clears a quality bar."""

    use_case = "refine_until_good"
    title = "Refine Until Good"
    when_to_use = "You want the agent to critique and improve its own output until it meets a quality bar."
    aliases = ()
    defaults = {"max_iterations": 5}
    strategy = EvaluatorOptimizerStrategy()
