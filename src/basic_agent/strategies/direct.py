"""DIRECT strategy: single LlmAgent without tool loop."""

from google.adk.agents import Agent

from .base import AgentStrategy, AgentStrategyContext


class DirectStrategy(AgentStrategy):
    """Single configuration-driven agent without agentic tool looping.

    This is the baseline GenericAgent pattern - a one-shot LlmAgent that
    handles the user's request without iterative tool use or delegation.
    """

    @property
    def agent_type(self) -> str:
        return "DIRECT"

    def build(self, context: AgentStrategyContext) -> Agent:
        """Build a direct DIRECT-mode agent.

        Args:
            context: Runtime configuration.

        Returns:
            A single LlmAgent configured with the provided tools, model, and instructions.
        """
        return self.llm(context.runtime, name=f"{context.agent_type.lower()}_agent")
