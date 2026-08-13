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
        rt = context.runtime

        num_workers = 2  # Default
        if context.extra_config and "workers" in context.extra_config:
            num_workers = context.extra_config["workers"]

        # Create worker agents
        workers = [
            Agent(
                name=f"supervisor_worker_{i}",
                model=rt.model,
                description=f"Worker {i}",
                instruction=rt.instruction,
                tools=rt.tools or [],
            )
            for i in range(num_workers)
        ]

        agent = LlmAgent(
            name=f"{context.agent_type.lower()}_agent",
            model=rt.model,
            description=rt.description,
            instruction=rt.instruction,
            tools=rt.tools or [],
            sub_agents=workers,
        )

        return agent
