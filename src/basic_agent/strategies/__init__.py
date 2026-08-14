"""Agent strategy registry and implementations.

This module provides a strategy/registry pattern for building different types
of agents from a shared configuration. New strategies can be registered without
modifying the core runtime.
"""

from .base import AgentStrategy, AgentStrategyContext, RoleConfig, RuntimeContext
from .registry import AgentStrategyRegistry, get_default_registry
from .direct import DirectStrategy
from .react import ReactStrategy
from .sequential import SequentialAgentStrategy
from .parallel import ParallelAgentStrategy
from .loop import LoopAgentStrategy
from .router import RouterStrategy
from .supervisor import SupervisorStrategy
from .planner_executor import PlannerExecutorStrategy
from .evaluator_optimizer import EvaluatorOptimizerStrategy
from .human_in_loop import HumanInLoopStrategy

__all__ = [
    "AgentStrategy",
    "AgentStrategyContext",
    "RoleConfig",
    "RuntimeContext",
    "AgentStrategyRegistry",
    "get_default_registry",
    "DirectStrategy",
    "ReactStrategy",
    "SequentialAgentStrategy",
    "ParallelAgentStrategy",
    "LoopAgentStrategy",
    "RouterStrategy",
    "SupervisorStrategy",
    "PlannerExecutorStrategy",
    "EvaluatorOptimizerStrategy",
    "HumanInLoopStrategy",
]
