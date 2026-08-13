"""Bounded draft-and-critique loop pattern."""

from google.adk.agents import LoopAgent

from .common import worker

agent = LoopAgent(
    name="loop_pattern_agent",
    description="Iteratively improve an answer through critique and revision.",
    max_iterations=3,
    sub_agents=[
        worker(
            "loop_drafter",
            "Draft the best answer you can for the user's request. Preserve useful prior state when revising.",
            output_key="loop_draft",
        ),
        worker(
            "loop_critic",
            "Critique {loop_draft} for correctness, completeness, and clarity. Provide concrete revisions.",
            output_key="loop_critique",
        ),
    ],
)
