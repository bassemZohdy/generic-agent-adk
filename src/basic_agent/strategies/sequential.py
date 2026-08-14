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
        rt = context.runtime

        num_steps = 2  # Default
        if context.extra_config and "steps" in context.extra_config:
            num_steps = context.extra_config["steps"]

        workers = [
            self.llm(rt, name=f"sequential_step_{i}", description=f"Sequential step {i}")
            for i in range(num_steps)
        ]

        return SequentialAgent(
            name=f"{context.agent_type.lower()}_agent",
            description=rt.description,
            sub_agents=workers,
        )
