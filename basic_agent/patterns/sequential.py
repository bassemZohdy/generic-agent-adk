"""Sequential research, analysis, and review pattern."""

from google.adk.agents import SequentialAgent

from .common import worker

agent = SequentialAgent(
    name="sequential_pattern_agent",
    description="Research, analyze, and review a request in sequence.",
    sub_agents=[
        worker(
            "sequential_researcher",
            "Research the user's request. Capture relevant facts, assumptions, and evidence.",
            output_key="sequential_research",
        ),
        worker(
            "sequential_analyst",
            "Analyze the research stored in {sequential_research}. Produce a concise solution and identify risks.",
            output_key="sequential_analysis",
        ),
        worker(
            "sequential_reviewer",
            "Review {sequential_analysis} against {sequential_research}. Return the final answer with evidence, risks, and next steps.",
        ),
    ],
)
