"""SUPERVISOR strategy: coordinating multiple agents."""

from google.adk.agents import Agent, LlmAgent

from .base import AgentStrategy, AgentStrategyContext, RoleConfig


class SupervisorStrategy(AgentStrategy):
    """Supervisor coordinating multiple worker agents.

    Supervisor delegates work to workers and aggregates results.
    """

    @property
    def agent_type(self) -> str:
        return "SUPERVISOR"

    def build(self, context: AgentStrategyContext) -> Agent:
        """Build a SUPERVISOR-mode agent.

        Each worker gets a distinct default instruction identifying its place
        on the team (worker N of count), overridable per-index via
        ``rt.roles["worker_{i}"]`` — the same override mechanism
        ``RouterStrategy`` uses for named specialists.

        Args:
            context: Runtime configuration.

        Returns:
            An LlmAgent supervising multiple distinctly-briefed sub-agents.
        """
        rt = context.runtime
        count = self.positive_count(context, "workers", 2)

        workers = []
        for i in range(count):
            config = rt.roles.get(f"worker_{i}", RoleConfig())
            workers.append(
                self.llm(
                    rt,
                    name=f"supervisor_worker_{i}",
                    role=RoleConfig(
                        instruction=config.instruction
                        or (
                            f"You are worker {i} of {count} on this team. Handle "
                            "the portion of the coordinator's request assigned to "
                            "you, then report your result back."
                        ),
                        model=config.model,
                        tools=config.tools,
                    ),
                    description=f"Worker {i}",
                )
            )

        return self.llm(
            rt,
            name=f"{context.agent_type.lower()}_agent",
            description=rt.description,
            sub_agents=workers,
        )
