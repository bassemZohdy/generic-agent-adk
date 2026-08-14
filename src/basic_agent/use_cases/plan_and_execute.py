"""Plan-and-execute use case: plan first, then execute."""

from __future__ import annotations

from .base import BaseUseCaseAgent
from ..strategies import PlannerExecutorStrategy


class PlanAndExecuteAgent(BaseUseCaseAgent):
    """Splits a big task into a plan, then executes the plan."""

    use_case = "plan_and_execute"
    title = "Plan and Execute"
    when_to_use = "You want large tasks split into a plan first and executed step by step afterwards."
    aliases = ("planner_executor", "plan_execute")
    strategy = PlannerExecutorStrategy()
