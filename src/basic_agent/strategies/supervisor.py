"""SUPERVISOR strategy: coordinating multiple agents."""

from google.adk.agents import Agent, LlmAgent

from .base import AgentStrategy, AgentStrategyContext


class SupervisorStrategy(AgentStrategy):
    """Supervisor coordinating multiple worker agents.

    Supervisor delegates work to workers and aggregates results.
    """

    @property
    def agent_type(self) -> str:
        return "SUPERVISOR"

    def build(self, context: AgentStrategyContext) -> Agent:
        """Build a SUPERVISOR-mode agent.

        Args:
            context: Runtime configuration.

        Returns:
            An LlmAgent supervising multiple sub-agents.
        """
        self.validate(context)
        rt = context.runtime
        num_workers = self.positive_count(context, "workers", 2)

        workers = [
            self.llm(rt, name=f"supervisor_worker_{i}", description=f"Worker {i}")
            for i in range(num_workers)
        ]

        return self.llm(
            rt,
            name=f"{context.agent_type.lower()}_agent",
            description=rt.description,
            sub_agents=workers,
        )

    def validate(self, context: AgentStrategyContext) -> None:
        self.positive_count(context, "workers", 2)
