"""Multi-perspective use case: independent takes, aggregated."""

from __future__ import annotations

import logging
from dataclasses import replace

from google.adk.agents import SequentialAgent

from ..strategies import AgentStrategyContext, ParallelStrategy, RoleConfig
from .base import BaseUseCaseAgent

logger = logging.getLogger(__name__)


class MultiPerspectiveAgent(BaseUseCaseAgent):
    """Gathers several independent takes and aggregates them at the end."""

    use_case = "multi_perspective"
    title = "Multi-Perspective"
    when_to_use = (
        "You want several independent takes on the same question compared or combined."
    )
    aliases = ()
    strategy = ParallelStrategy()

    def compose(self, runtime):
        """Run parallel workers, then ask a dedicated node to synthesize them."""
        resolved = self.resolve_runtime(runtime)
        parallel = self.strategy.build(
            AgentStrategyContext(
                agent_type=self.strategy.agent_type,
                runtime=resolved,
                extra_config=dict(resolved.extra_config),
            )
        )
        synthesizer = self.strategy.llm(
            replace(resolved, output_key=resolved.output_key or "last_response"),
            name="perspective_synthesizer",
            description="Synthesize independent perspectives",
            role=RoleConfig(
                instruction=(
                    "Read the perspective outputs in session state, compare where "
                    "they agree or differ, and produce one balanced final answer."
                )
            ),
        )
        return SequentialAgent(
            name="multi_perspective_agent",
            description=resolved.description,
            sub_agents=[parallel, synthesizer],
        )

    def after_run(self, callback_context) -> None:
        """Collect ``perspective_*`` state entries into an aggregated list.

        Runs once after all branches finished and wrote their indexed
        ``perspective_<index>`` output keys.
        """
        try:
            state = callback_context.state
            keys = sorted(
                (key for key in state if key.startswith("perspective_")),
                key=lambda key: (
                    int(key.split("_", 1)[1])
                    if key.split("_", 1)[1].isdigit()
                    else 2**63
                ),
            )
            values = [state[key] for key in keys]
            state["aggregated_perspectives"] = values
        except Exception:
            logger.debug("Unable to aggregate multi-perspective state", exc_info=True)
