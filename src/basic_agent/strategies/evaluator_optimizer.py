"""EVALUATOR_OPTIMIZER strategy: generate, evaluate, improve loop."""

from google.adk.agents import Agent, LoopAgent

from .base import AgentStrategy, AgentStrategyContext, RoleConfig


class EvaluatorOptimizerStrategy(AgentStrategy):
    """Generate-evaluate-improve loop pattern.

    Iteratively generates solutions, evaluates them, and improves.
    """

    @property
    def agent_type(self) -> str:
        return "EVALUATOR_OPTIMIZER"

    def validate(self, context: AgentStrategyContext) -> None:
        """Ensure max_iterations is set for this pattern."""
        self.require_min_iterations(context)

    def build(self, context: AgentStrategyContext) -> Agent:
        """Build an EVALUATOR_OPTIMIZER-mode agent.

        Args:
            context: Runtime configuration with max_iterations.

        Returns:
            A LoopAgent iterating generation and evaluation.
        """
        self.validate(context)
        rt = context.runtime

        worker = self.llm(
            rt,
            name="evaluator_optimizer_worker",
            description="Generate and evaluate solutions",
            role=RoleConfig(
                instruction=(
                    "Generate a solution, evaluate it critically, and improve it. "
                    "Repeat until satisfied."
                )
            ),
        )

        return LoopAgent(
            name=f"{context.agent_type.lower()}_agent",
            description=rt.description,
            sub_agents=[worker],
            max_iterations=rt.max_iterations,
        )
