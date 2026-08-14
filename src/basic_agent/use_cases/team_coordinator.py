"""Team coordinator use case: supervisor delegating to workers."""

from __future__ import annotations

from .base import BaseUseCaseAgent
from ..strategies import SupervisorStrategy


class TeamCoordinatorAgent(BaseUseCaseAgent):
    """Supervisor agent that decomposes work and delegates to workers."""

    use_case = "team_coordinator"
    title = "Team Coordinator"
    when_to_use = "You want complex work decomposed and delegated to worker agents by a coordinator."
    aliases = ("supervisor",)
    strategy = SupervisorStrategy()
