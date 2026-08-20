"""ROUTER strategy: specialist routing pattern."""

from google.adk.agents import LlmAgent

from .base import AgentStrategy, AgentStrategyContext, RoleConfig


class RouterStrategy(AgentStrategy):
    """Route requests to specialist agents.

    Main router agent selects the best specialist for each request.
    """

    @property
    def agent_type(self) -> str:
        return "ROUTER"

    def validate(self, context: AgentStrategyContext) -> None:
        """Ensure specialists are configured."""
        if not context.runtime.specialists:
            raise ValueError(
                "ROUTER strategy requires at least one specialist in config"
            )

    def build(self, context: AgentStrategyContext) -> LlmAgent:
        """Build a ROUTER-mode agent.

        Args:
            context: Runtime configuration with specialists.

        Returns:
            An LlmAgent that routes to configured specialists.
        """
        self.validate(context)
        rt = context.runtime

        # Create specialist sub-agents. Per-role config from rt.roles overrides
        # instruction/model/tools; roles without an instruction get a generated
        # per-specialist prompt (never the router's own instruction).
        specialists = []
        for name in rt.specialists:
            config = rt.roles.get(name, RoleConfig())
            specialists.append(
                self.llm(
                    rt,
                    name=f"router_specialist_{name}",
                    role=RoleConfig(
                        instruction=config.instruction
                        or f"You are the {name} specialist. Handle requests in your domain.",
                        model=config.model,
                        tools=config.tools,
                    ),
                    description=f"Specialist: {name}",
                )
            )

        return self.llm(
            rt,
            name=f"{context.agent_type.lower()}_agent",
            description=rt.description,
            role=RoleConfig(
                instruction=(
                    f"Route the request to the best specialist. "
                    f"Available specialists: {', '.join(rt.specialists)}"
                ),
            ),
            sub_agents=specialists,
        )
