"""PLANNER_EXECUTOR strategy: plan then execute."""

from google.adk.agents import Agent, SequentialAgent

from .base import AgentStrategy, AgentStrategyContext, RoleConfig


class PlannerExecutorStrategy(AgentStrategy):
    """Plan-then-execute pattern: plan, execute, verify."""

    @property
    def agent_type(self) -> str:
        return "PLAN_EXECUTE"

    def build(self, context: AgentStrategyContext) -> Agent:
        """Build a PLAN_EXECUTE-mode agent.

        Args:
            context: Runtime configuration.

        Returns:
            A SequentialAgent running planner and executor in sequence.
        """
        rt = context.runtime

        planner = self.llm(
            rt,
            name="planner_agent",
            description="Create a detailed plan",
            role=RoleConfig(instruction="Create a step-by-step plan to address the request."),
        )

        executor = self.llm(
            rt,
            name="executor_agent",
            description="Execute the plan",
            role=RoleConfig(instruction="Execute the plan step by step."),
        )

        return SequentialAgent(
            name=f"{context.agent_type.lower()}_agent",
            description=rt.description,
            sub_agents=[planner, executor],
        )
