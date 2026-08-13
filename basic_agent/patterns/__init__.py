"""Externally selectable ADK orchestration patterns."""

from __future__ import annotations

from google.adk.agents.base_agent import BaseAgent

from ..config import AgentPattern, settings
from .loop import agent as loop_agent
from .parallel import agent as parallel_agent
from .evaluator_optimizer import agent as evaluator_optimizer_agent
from .human_in_loop import agent as human_in_loop_agent
from .planner_executor import agent as planner_executor_agent
from .router import agent as router_agent
from .sequential import agent as sequential_agent

PATTERN_AGENTS: dict[AgentPattern, BaseAgent] = {
    AgentPattern.SEQUENTIAL: sequential_agent,
    AgentPattern.PARALLEL: parallel_agent,
    AgentPattern.LOOP: loop_agent,
    AgentPattern.ROUTER: router_agent,
    AgentPattern.PLANNER_EXECUTOR: planner_executor_agent,
    AgentPattern.EVALUATOR_OPTIMIZER: evaluator_optimizer_agent,
    AgentPattern.HUMAN_IN_LOOP: human_in_loop_agent,
}


def get_pattern_agent(pattern: AgentPattern | str) -> BaseAgent:
    """Return the agent implementation for an explicit pattern value."""
    selected = pattern if isinstance(pattern, AgentPattern) else AgentPattern(pattern)
    try:
        return PATTERN_AGENTS[selected]
    except KeyError as error:
        raise ValueError(f"Pattern {selected.value!r} does not define a workflow agent") from error


selected_pattern_agent = (
    None if settings.agent_pattern is AgentPattern.GENERIC else get_pattern_agent(settings.agent_pattern)
)

__all__ = [
    "PATTERN_AGENTS",
    "get_pattern_agent",
    "selected_pattern_agent",
    "sequential_agent",
    "parallel_agent",
    "loop_agent",
    "router_agent",
    "planner_executor_agent",
    "evaluator_optimizer_agent",
    "human_in_loop_agent",
]
