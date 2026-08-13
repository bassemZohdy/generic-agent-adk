"""Specialist-routing pattern."""

from google.adk.agents import LlmAgent

from ..agent import tools
from ..config import settings
from .common import worker

agent = LlmAgent(
    name="router_pattern_agent",
    model=settings.model,
    description="Route a request to the most suitable specialist agent.",
    instruction=(
        "Classify the user's request and transfer it to exactly one specialist. "
        f"Available specialist roles are: {', '.join(settings.pattern_specialists)}. "
        "Do not answer before routing."
    ),
    tools=tools,
    sub_agents=[
        worker(
            "router_research_specialist",
            "Answer the routed research request with evidence and explicit uncertainty.",
        ),
        worker(
            "router_solution_specialist",
            "Answer the routed design or implementation request with concrete steps and trade-offs.",
        ),
        worker(
            "router_risk_specialist",
            "Answer the routed security or operations request with risks and mitigations.",
        ),
    ],
)
