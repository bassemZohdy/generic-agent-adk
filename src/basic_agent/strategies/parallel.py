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
        self.validate(context)
        rt = context.runtime
        num_workers = self.positive_count(context, "workers", 2)

        workers = [
            self.llm(rt, name=f"parallel_worker_{i}", description=f"Parallel worker {i}")
            for i in range(num_workers)
        ]

        return ParallelAgent(
            name=f"{context.agent_type.lower()}_agent",
            description=rt.description,
            sub_agents=workers,
        )

    def validate(self, context: AgentStrategyContext) -> None:
        self.positive_count(context, "workers", 2)
