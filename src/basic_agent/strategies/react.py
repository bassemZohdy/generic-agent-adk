"""REACT strategy: LlmAgent with iterative tool use."""

from google.adk.agents import Agent

from .base import AgentStrategy, AgentStrategyContext


class ReactStrategy(AgentStrategy):
    """Agent with iterative tool use (REACT pattern).

    LlmAgent with tools enabled allows for reasoning + action loops where the
    agent observes tool outputs and continues reasoning.
    """

    @property
    def agent_type(self) -> str:
        return "REACT"

    def build(self, context: AgentStrategyContext) -> Agent:
        """Build a REACT-mode agent with tool looping.

        Args:
            context: Runtime configuration.

        Returns:
            An LlmAgent configured for iterative tool use.
        """
        return self.llm(context.runtime, name=f"{context.agent_type.lower()}_agent")
