"""SEQUENTIAL strategy: SequentialAgent pattern."""

from google.adk.agents import Agent, SequentialAgent

from .base import AgentStrategy, AgentStrategyContext, RoleConfig


class SequentialStrategy(AgentStrategy):
    """Sequential execution of ordered agents.

    Runs multiple agents in sequence, passing outputs forward.
    """

    @property
    def agent_type(self) -> str:
        return "SEQUENTIAL"

    def build(self, context: AgentStrategyContext) -> Agent:
        """Build a SEQUENTIAL-mode agent.

        Each step gets a distinct default instruction identifying its place
        in the pipeline (step N of count), overridable per-index via
        ``rt.roles["step_{i}"]`` — the same override mechanism
        ``RouterStrategy``/``SupervisorStrategy`` use.

        Args:
            context: Runtime configuration.

        Returns:
            A SequentialAgent orchestrating multiple distinctly-briefed steps.
        """
        rt = context.runtime
        count = self.positive_count(context, "steps", 2)

        steps = []
        for i in range(count):
            config = rt.roles.get(f"step_{i}", RoleConfig())
            steps.append(
                self.llm(
                    rt,
                    name=f"sequential_step_{i}",
                    role=RoleConfig(
                        instruction=config.instruction
                        or (
                            f"You are step {i} of {count} in this pipeline. Perform "
                            "your stage of the overall task, building on the output "
                            "of any previous steps, then hand off your result."
                        ),
                        model=config.model,
                        tools=config.tools,
                    ),
                    description=f"Sequential step {i}",
                )
            )

        return SequentialAgent(
            name=f"{context.agent_type.lower()}_agent",
            description=rt.description,
            sub_agents=steps,
        )
