"""PLANNER_EXECUTOR strategy: plan then execute."""

from google.adk.agents import Agent, SequentialAgent

from .base import AgentStrategy, AgentStrategyContext


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

        planner = Agent(
            name="planner_agent",
            model=rt.model,
            description="Create a detailed plan",
            instruction="Create a step-by-step plan to address the request.",
            tools=rt.tools or [],
        )

        executor = Agent(
            name="executor_agent",
            model=rt.model,
            description="Execute the plan",
            instruction="Execute the plan step by step.",
            tools=rt.tools or [],
        )

        agent = SequentialAgent(
            name=f"{context.agent_type.lower()}_agent",
            description=rt.description,
            sub_agents=[planner, executor],
        )

        return agent
