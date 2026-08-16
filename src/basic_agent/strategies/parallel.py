"""PARALLEL strategy: ParallelAgent pattern."""

from google.adk.agents import Agent, ParallelAgent

from .base import AgentStrategy, AgentStrategyContext


class ParallelStrategy(AgentStrategy):
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
        workers = self.build_worker_pool(
            context, key="workers", name_prefix="parallel_worker", description="Parallel worker"
        )

        return ParallelAgent(
            name=f"{context.agent_type.lower()}_agent",
            description=context.runtime.description,
            sub_agents=workers,
        )
