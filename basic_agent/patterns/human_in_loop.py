"""Proposal → human approval → completion pattern."""

from google.adk.agents import SequentialAgent

from ..config import settings
from .common import worker

approval_policy = (
    "Approval is mandatory before proceeding."
    if settings.pattern_require_approval
    else "Request approval for irreversible actions and explain if approval is not required."
)

agent = SequentialAgent(
    name="human_in_loop_pattern_agent",
    description="Prepare a proposal, request human approval, and complete the approved action.",
    sub_agents=[
        worker(
            "proposal_agent",
            "Prepare a proposed action for the user's request. Clearly identify impact, reversibility, and risks.",
            output_key="proposal",
        ),
        worker(
            "approval_agent",
            f"Review {{proposal}}. {approval_policy} Call the approval tool before any irreversible action. Do not proceed until confirmation is available.",
            output_key="approval_result",
        ),
        worker(
            "completion_agent",
            "Using {proposal} and {approval_result}, complete only an approved action. If approval is absent or rejected, explain what remains pending.",
        ),
    ],
)
