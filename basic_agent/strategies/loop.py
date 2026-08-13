"""LOOP strategy: LoopAgent pattern."""

from google.adk.agents import Agent, LoopAgent

from .base import AgentStrategy, AgentStrategyContext


class LoopAgentStrategy(AgentStrategy):
    """Repeated execution with loop control.

    Iterates an agent up to a configured maximum.
    """

    @property
    def agent_type(self) -> str:
        return "LOOP"

    def validate(self, context: AgentStrategyContext) -> None:
        """Ensure max_iterations is set and valid."""
        if context.runtime.max_iterations < 1:
            raise ValueError("max_iterations must be at least 1 for LOOP strategy")

    def build(self, context: AgentStrategyContext) -> Agent:
        """Build a LOOP-mode agent.

        Args:
            context: Runtime configuration with max_iterations.

        Returns:
            A LoopAgent iterating up to the configured limit.
        """
        self.validate(context)
        rt = context.runtime

        worker = Agent(
            name="loop_worker",
            model=rt.model,
            description="Loop worker agent",
            instruction=rt.instruction,
            tools=rt.tools or [],
            code_executor=rt.code_executor,
        )

        agent = LoopAgent(
            name=f"{context.agent_type.lower()}_agent",
            description=rt.description,
            sub_agents=[worker],
            max_iterations=rt.max_iterations,
        )

        return agent
