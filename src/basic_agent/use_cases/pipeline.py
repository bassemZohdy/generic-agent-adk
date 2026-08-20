"""Pipeline use case: fixed sequential steps."""

from __future__ import annotations

from ..strategies import SequentialStrategy
from .base import BaseUseCaseAgent


class PipelineAgent(BaseUseCaseAgent):
    """Runs fixed steps in order, e.g. fetch, analyze, then summarize."""

    use_case = "pipeline"
    title = "Pipeline"
    when_to_use = "You want fixed steps always executed in the same order, like fetch, analyze, summarize."
    aliases = ()
    strategy = SequentialStrategy()
