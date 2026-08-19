"""Agent strategy registry and implementations.

This module provides a strategy/registry pattern for building different types
of agents from a shared configuration. New strategies can be registered without
modifying the core runtime.
"""

from .base import AgentStrategy, AgentStrategyContext, RoleConfig, RuntimeContext
from .direct import DirectStrategy
from .evaluator_optimizer import EvaluatorOptimizerStrategy
from .human_in_loop import HumanInLoopStrategy
from .loop import LoopStrategy
from .parallel import ParallelStrategy
from .planner_executor import PlannerExecutorStrategy
from .registry import AgentStrategyRegistry, get_default_registry
from .router import RouterStrategy
from .sequential import SequentialStrategy
from .supervisor import SupervisorStrategy

__all__ = [
    "AgentStrategy",
    "AgentStrategyContext",
    "AgentStrategyRegistry",
    "DirectStrategy",
    "EvaluatorOptimizerStrategy",
    "HumanInLoopStrategy",
    "LoopStrategy",
    "ParallelStrategy",
    "PlannerExecutorStrategy",
    "RoleConfig",
    "RouterStrategy",
    "RuntimeContext",
    "SequentialStrategy",
    "SupervisorStrategy",
    "get_default_registry",
]
