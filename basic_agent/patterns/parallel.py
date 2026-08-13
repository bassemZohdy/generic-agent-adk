"""Parallel independent-perspectives pattern."""

from google.adk.agents import ParallelAgent

from .common import worker

agent = ParallelAgent(
    name="parallel_pattern_agent",
    description="Run independent perspectives concurrently and return their combined results.",
    sub_agents=[
        worker(
            "parallel_fact_checker",
            "Fact-check the user's request independently. State uncertainty explicitly.",
            output_key="parallel_facts",
        ),
        worker(
            "parallel_solution_designer",
            "Design a practical solution to the user's request independently, including trade-offs.",
            output_key="parallel_solution",
        ),
        worker(
            "parallel_risk_reviewer",
            "Identify security, operational, and correctness risks in the user's request.",
            output_key="parallel_risks",
        ),
    ],
)
