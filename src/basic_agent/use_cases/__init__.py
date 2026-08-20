"""Public use-case layer: what users pick, plus runtime behavior via hooks.

Use cases are facades (:class:`BaseUseCaseAgent`) over an internal strategy
that shapes the ADK tree. Metadata (titles, aliases, when-to-use) lives only
here. Dependency is one-way: ``use_cases`` imports ``strategies``, never the
reverse.
"""

from __future__ import annotations

from .approval_gate import ApprovalGateAgent
from .assistant import AssistantAgent
from .base import BaseUseCaseAgent
from .expert_dispatch import ExpertDispatchAgent
from .multi_perspective import MultiPerspectiveAgent
from .pipeline import PipelineAgent
from .plan_and_execute import PlanAndExecuteAgent
from .refine_until_good import RefineUntilGoodAgent
from .registry import UseCaseRegistry, get_default_registry, load_custom_use_cases
from .team_coordinator import TeamCoordinatorAgent

__all__ = [
    "ApprovalGateAgent",
    "AssistantAgent",
    "BaseUseCaseAgent",
    "ExpertDispatchAgent",
    "MultiPerspectiveAgent",
    "PipelineAgent",
    "PlanAndExecuteAgent",
    "RefineUntilGoodAgent",
    "TeamCoordinatorAgent",
    "UseCaseRegistry",
    "get_default_registry",
    "load_custom_use_cases",
]
