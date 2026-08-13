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
        rt = context.runtime

        agent = Agent(
            name=f"{context.agent_type.lower()}_agent",
            model=rt.model,
            description=rt.description,
            instruction=rt.instruction,
            tools=rt.tools or [],
            code_executor=rt.code_executor,
            state_schema=rt.state_schema,
            output_schema=rt.output_schema,
            output_key=rt.output_key,
            before_agent_callback=rt.before_agent_callback,
            after_agent_callback=rt.after_agent_callback,
        )

        return agent
