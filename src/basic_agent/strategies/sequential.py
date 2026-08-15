"""SEQUENTIAL strategy: SequentialAgent pattern."""

from google.adk.agents import Agent, SequentialAgent

from .base import AgentStrategy, AgentStrategyContext


class SequentialAgentStrategy(AgentStrategy):
    """Sequential execution of ordered agents.

    Runs multiple agents in sequence, passing outputs forward.
    """

    @property
    def agent_type(self) -> str:
        return "SEQUENTIAL"

    def build(self, context: AgentStrategyContext) -> Agent:
        """Build a SEQUENTIAL-mode agent.

        Args:
            context: Runtime configuration.

        Returns:
            A SequentialAgent orchestrating multiple child agents.
        """
        self.validate(context)
        rt = context.runtime
        num_steps = self.positive_count(context, "steps", 2)

        workers = [
            self.llm(rt, name=f"sequential_step_{i}", description=f"Sequential step {i}")
            for i in range(num_steps)
        ]

        return SequentialAgent(
            name=f"{context.agent_type.lower()}_agent",
            description=rt.description,
            sub_agents=workers,
        )

    def validate(self, context: AgentStrategyContext) -> None:
        self.positive_count(context, "steps", 2)
