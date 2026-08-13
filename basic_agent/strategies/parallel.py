"""PARALLEL strategy: ParallelAgent pattern."""

from google.adk.agents import Agent, ParallelAgent

from .base import AgentStrategy, AgentStrategyContext


class ParallelAgentStrategy(AgentStrategy):
    """Parallel execution of independent agents.

    Runs multiple agents concurrently and aggregates results.
    """

    @property
    def agent_type(self) -> str:
        return "PARALLEL"

    def build(self, context: AgentStrategyContext) -> Agent:
        """Build a PARALLEL-mode agent.

        Args:
            context: Runtime configuration.

        Returns:
            A ParallelAgent running multiple workers concurrently.
        """
        rt = context.runtime

        num_workers = 2  # Default
        if context.extra_config and "workers" in context.extra_config:
            num_workers = context.extra_config["workers"]

        # Create independent workers
        workers = [
            Agent(
                name=f"parallel_worker_{i}",
                model=rt.model,
                description=f"Parallel worker {i}",
                instruction=rt.instruction,
                tools=rt.tools or [],
                code_executor=rt.code_executor,
            )
            for i in range(num_workers)
        ]

        agent = ParallelAgent(
            name=f"{context.agent_type.lower()}_agent",
            description=rt.description,
            sub_agents=workers,
        )

        return agent
