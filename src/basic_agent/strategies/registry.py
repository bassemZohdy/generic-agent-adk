"""Agent strategy registry."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .base import AgentStrategy

logger = logging.getLogger(__name__)


class AgentStrategyRegistry:
    """Registry for agent-building strategies.

    Strategies are registered by type identifier. The registry allows dynamic
    strategy selection and validation without hard-coded conditionals.
    """

    def __init__(self) -> None:
        self._strategies: dict[str, AgentStrategy] = {}

    def register(self, strategy: AgentStrategy) -> None:
        """Register a strategy.

        Args:
            strategy: The strategy instance to register.

        Raises:
            ValueError: If a strategy with the same type is already registered.
        """
        agent_type = strategy.agent_type
        if agent_type in self._strategies:
            raise ValueError(
                f"Strategy for agent type {agent_type!r} is already registered"
            )
        self._strategies[agent_type] = strategy
        logger.debug("Registered strategy for agent type %r", agent_type)

    def get(self, agent_type: str) -> AgentStrategy | None:
        """Retrieve a strategy by type identifier.

        Args:
            agent_type: The agent type to look up.

        Returns:
            The strategy instance, or None if not found.
        """
        return self._strategies.get(agent_type)

    def has(self, agent_type: str) -> bool:
        """Check if a strategy is registered for the given type.

        Args:
            agent_type: The agent type to check.

        Returns:
            True if a strategy is registered, False otherwise.
        """
        return agent_type in self._strategies

    def list_types(self) -> list[str]:
        """Return a sorted list of registered agent types.

        Returns:
            List of agent type identifiers.
        """
        return sorted(self._strategies.keys())


_default_registry: AgentStrategyRegistry | None = None


def get_default_registry() -> AgentStrategyRegistry:
    """Get or create the default strategy registry.

    Lazy-initializes the registry and registers built-in strategies on first call.

    Returns:
        The default global registry.
    """
    global _default_registry

    if _default_registry is None:
        _default_registry = AgentStrategyRegistry()
        _register_builtin_strategies(_default_registry)

    return _default_registry


def _register_builtin_strategies(registry: AgentStrategyRegistry) -> None:
    """Register all built-in strategies to a registry.

    Args:
        registry: The registry to populate.
    """
    # Import here to avoid circular imports
    from .direct import DirectStrategy
    from .evaluator_optimizer import EvaluatorOptimizerStrategy
    from .human_in_loop import HumanInLoopStrategy
    from .loop import LoopStrategy
    from .parallel import ParallelStrategy
    from .planner_executor import PlannerExecutorStrategy
    from .router import RouterStrategy
    from .sequential import SequentialStrategy
    from .supervisor import SupervisorStrategy

    strategies = [
        DirectStrategy(),
        SequentialStrategy(),
        ParallelStrategy(),
        LoopStrategy(),
        RouterStrategy(),
        SupervisorStrategy(),
        PlannerExecutorStrategy(),
        EvaluatorOptimizerStrategy(),
        HumanInLoopStrategy(),
    ]

    for strategy in strategies:
        registry.register(strategy)
