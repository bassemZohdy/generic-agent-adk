"""ROUTER strategy: specialist routing pattern."""

from google.adk.agents import Agent, LlmAgent

from .base import AgentStrategy, AgentStrategyContext


class RouterStrategy(AgentStrategy):
    """Route requests to specialist agents.

    Main router agent selects the best specialist for each request.
    """

    @property
    def agent_type(self) -> str:
        return "ROUTER"

    def validate(self, context: AgentStrategyContext) -> None:
        """Ensure specialists are configured."""
        if not context.runtime.specialists or len(context.runtime.specialists) < 1:
            raise ValueError("ROUTER strategy requires at least one specialist in config")

    def build(self, context: AgentStrategyContext) -> Agent:
        """Build a ROUTER-mode agent.

        Args:
            context: Runtime configuration with specialists.

        Returns:
            An LlmAgent that routes to configured specialists.
        """
        self.validate(context)
        rt = context.runtime

        # Create specialist sub-agents
        specialists = [
            Agent(
                name=f"router_specialist_{specialist}",
                model=rt.model,
                description=f"Specialist: {specialist}",
                instruction=rt.instruction,
                tools=rt.tools or [],
            )
            for specialist in rt.specialists
        ]

        agent = LlmAgent(
            name=f"{context.agent_type.lower()}_agent",
            model=rt.model,
            description=rt.description,
            instruction=(
                f"Route the request to the best specialist. "
                f"Available specialists: {', '.join(rt.specialists)}"
            ),
            tools=rt.tools or [],
            sub_agents=specialists,
        )

        return agent
