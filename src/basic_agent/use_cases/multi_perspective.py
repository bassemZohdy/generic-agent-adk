"""Multi-perspective use case: independent takes, aggregated."""

from __future__ import annotations

import logging

from .base import BaseUseCaseAgent
from ..strategies import ParallelStrategy


logger = logging.getLogger(__name__)


class MultiPerspectiveAgent(BaseUseCaseAgent):
    """Gathers several independent takes and aggregates them at the end."""

    use_case = "multi_perspective"
    title = "Multi-Perspective"
    when_to_use = "You want several independent takes on the same question compared or combined."
    aliases = ()
    strategy = ParallelStrategy()

    def after_run(self, callback_context) -> None:
        """Collect ``perspective_*`` state entries into an aggregated list.

        Runs as the root ParallelAgent's after_agent_callback, so it fires once
        after all branches finished and wrote their ``perspective_<name>``
        output keys.
        """
        try:
            state = callback_context.state
            values = [
                state[key] for key in list(state.keys()) if key.startswith("perspective_")
            ]
            state["aggregated_perspectives"] = values
        except Exception:  # noqa: BLE001 - tolerate fake/simple contexts
            logger.debug("Unable to aggregate multi-perspective state", exc_info=True)
