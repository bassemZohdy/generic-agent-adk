"""Planner → executor → verifier pattern."""

from google.adk.agents import SequentialAgent

from .common import worker

agent = SequentialAgent(
    name="planner_executor_pattern_agent",
    description="Create a plan, execute it, and verify the result.",
    sub_agents=[
        worker(
            "planner",
            "Break the user's request into an ordered, actionable plan. Include assumptions and acceptance criteria.",
            output_key="plan",
        ),
        worker(
            "executor",
            "Execute the plan in {plan}. Use configured tools where appropriate and record what was completed.",
            output_key="execution_result",
        ),
        worker(
            "verifier",
            "Verify {execution_result} against {plan} and return the final result, gaps, risks, and next steps.",
        ),
    ],
)
