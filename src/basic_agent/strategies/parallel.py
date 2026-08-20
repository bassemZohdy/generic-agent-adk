"""PARALLEL strategy: ParallelAgent pattern."""

from dataclasses import replace

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
        count = self.positive_count(context, "workers", 2)
        workers = []
        for index in range(count):
            worker_runtime = replace(context.runtime, output_key=f"perspective_{index}")
            workers.append(
                self.llm(
                    worker_runtime,
                    name=f"parallel_worker_{index}",
                    description=f"Parallel worker {index}",
                )
            )

        return ParallelAgent(
            name=f"{context.agent_type.lower()}_agent",
            description=context.runtime.description,
            sub_agents=workers,
        )
