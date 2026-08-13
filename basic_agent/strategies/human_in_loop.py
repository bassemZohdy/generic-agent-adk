"""HUMAN_IN_LOOP strategy: propose, approve, complete."""

from google.adk.agents import Agent, SequentialAgent

from .base import AgentStrategy, AgentStrategyContext


class HumanInLoopStrategy(AgentStrategy):
    """Human-in-the-loop pattern: propose, require approval, complete."""

    @property
    def agent_type(self) -> str:
        return "HUMAN_IN_LOOP"

    def validate(self, context: AgentStrategyContext) -> None:
        """Ensure approval is required."""
        if not context.runtime.require_approval:
            raise ValueError(
                "HUMAN_IN_LOOP strategy requires require_approval=True"
            )

    def build(self, context: AgentStrategyContext) -> Agent:
        """Build a HUMAN_IN_LOOP-mode agent.

        Args:
            context: Runtime configuration with require_approval=True.

        Returns:
            A SequentialAgent handling proposal and completion with approval gate.
        """
        self.validate(context)
        rt = context.runtime

        proposer = Agent(
            name="human_in_loop_proposer",
            model=rt.model,
            description="Propose a solution",
            instruction="Propose a clear, actionable solution for the user's request.",
            tools=rt.tools or [],
        )

        completer = Agent(
            name="human_in_loop_completer",
            model=rt.model,
            description="Complete the approved action",
            instruction="Complete the user-approved action.",
            tools=rt.tools or [],
        )

        agent = SequentialAgent(
            name=f"{context.agent_type.lower()}_agent",
            description=rt.description,
            sub_agents=[proposer, completer],
        )

        return agent
