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

    def validate(self, context: AgentStrategyContext) -> None:
        """Validate that steps are configured if needed."""
        pass

    def build(self, context: AgentStrategyContext) -> Agent:
        """Build a SEQUENTIAL-mode agent.

        Args:
            context: Runtime configuration.

        Returns:
            A SequentialAgent orchestrating multiple child agents.
        """
        rt = context.runtime

        # Create worker agents for each step
        num_steps = 2  # Default
        if context.extra_config and "steps" in context.extra_config:
            num_steps = context.extra_config["steps"]

        workers = [
            Agent(
                name=f"sequential_step_{i}",
                model=rt.model,
                description=f"Sequential step {i}",
                instruction=rt.instruction,
                tools=rt.tools or [],
                code_executor=rt.code_executor,
            )
            for i in range(num_steps)
        ]

        agent = SequentialAgent(
            name=f"{context.agent_type.lower()}_agent",
            description=rt.description,
            sub_agents=workers,
        )

        return agent
