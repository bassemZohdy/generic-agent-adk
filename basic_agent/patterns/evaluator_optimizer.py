"""Evaluator → optimizer bounded refinement pattern."""

from google.adk.agents import LoopAgent

from ..config import settings
from .common import worker

agent = LoopAgent(
    name="evaluator_optimizer_pattern_agent",
    description="Generate, evaluate, and improve an answer for a bounded number of iterations.",
    max_iterations=settings.pattern_max_iterations,
    sub_agents=[
        worker(
            "optimizer",
            "Create or improve the answer to the user's request using the prior evaluation when available.",
            output_key="optimized_answer",
        ),
        worker(
            "evaluator",
            "Evaluate {optimized_answer} for correctness, completeness, and configured acceptance criteria. Return precise improvement feedback.",
            output_key="evaluation",
        ),
    ],
)
