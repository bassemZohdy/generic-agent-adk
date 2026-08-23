"""Approval policy — cross-cutting, topology-independent (ADR-005 §4; TODO D1).

Extracted from ``use_cases/approval_gate.py::before_tool`` so approval is a
policy that applies to any preset or raw graph, not a use case.

Invariants (proven by the Phase B spike, ADR-003 §Phase B):
- NEVER gate ``request_approval``: it creates the pending confirmation event,
  so vetoing it deadlocks the confirmation flow itself.
- NEVER gate ``finish_task``: the task-mode wrapper waits for the tool's
  success response; replacing it with an error response makes the model
  retry until the LLM-call limit and the node fails (deadlock).
- NEVER gate ``_TaskAgentTool`` delegations (B3 rule).

Flow (legacy backend, and the shared LlmAgent-callback flow on the workflow
backend — both use the engine's ``request_confirmation`` interrupt): a
gated tool call with no prior approval records the confirmation request and
returns a veto response; after the human confirms, the tool proceeds.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from google.adk.agents import BaseAgent, LlmAgent

#: Tool names that must never be gated by the approval policy.
UNCONDITIONAL_TOOLS = frozenset({"request_approval", "finish_task"})


def is_unconditional_tool(tool: Any) -> bool:
    """Return True when a tool must never be gated (approval/finish/delegation)."""
    name = getattr(tool, "name", tool)
    if name in UNCONDITIONAL_TOOLS:
        return True
    try:
        from google.adk.tools.agent_tool import _TaskAgentTool

        return isinstance(tool, _TaskAgentTool)
    except (ImportError, AttributeError):  # pragma: no cover - ADK surface
        return True  # fail safe: unknown tool classes are not gated


def make_approval_before_tool(config: Any) -> Callable[..., Any]:
    """Build the before-tool approval callback for a policy config.

    Mirrors the use case's veto contract: returning a dict skips the actual
    tool call (ADK before_tool_callback semantics); ``None`` lets it run.
    """

    def before_tool(tool: Any, args: dict[str, Any], tool_context: Any) -> dict | None:
        name = getattr(tool, "name", tool)
        if is_unconditional_tool(tool):
            return None
        if not config.enabled:
            return None
        gated = name in config.gated_tools or any(
            isinstance(name, str) and name.startswith(prefix)
            for prefix in config.gated_prefixes
        )
        if gated and not tool_context.state.get("human_approved"):
            request_confirmation = getattr(tool_context, "request_confirmation", None)
            if callable(request_confirmation):
                request_confirmation(
                    hint=f"Confirm state-changing tool: {name}",
                    payload={"tool": name, "arguments": args},
                )
            return {
                "status": "blocked",
                "reason": "This action requires human approval before execution.",
            }
        return None

    return before_tool


def _chain_before_tool(first: Any, second: Callable[..., Any]):
    """Chain before-tool callbacks preserving veto short-circuiting.

    Matches ``BaseUseCaseAgent`` semantics: callbacks run in order; the first
    non-None result wins (ADK veto contract).  ``first`` may be a single
    callback, a list of callbacks (ADK 2.x allows both), or None.
    """
    callbacks = list(first) if isinstance(first, list) else ([first] if first else [])

    def chained(*args: Any, **kwargs: Any) -> Any:
        for callback in callbacks:
            result = callback(*args, **kwargs)
            if result is not None:
                return result
        return second(*args, **kwargs)

    return chained


def iter_llm_agents(root: BaseAgent):
    """Yield every LlmAgent in the tree, root included, depth-first.

    Walks both legacy ``sub_agents`` trees and Workflow graphs (LlmAgent
    nodes live in ``Workflow.graph.nodes``, not ``sub_agents``).
    """
    stack = [root]
    while stack:
        node = stack.pop()
        if isinstance(node, LlmAgent):
            yield node
            stack.extend(reversed(getattr(node, "sub_agents", None) or []))
            continue
        graph = getattr(node, "graph", None)
        if graph is not None:
            stack.extend(reversed(graph.nodes))
        else:
            stack.extend(reversed(getattr(node, "sub_agents", None) or []))


def apply_approval_policy(
    root: BaseAgent,
    before_tool: Callable[..., Any],
) -> BaseAgent:
    """Wire the approval callback after any existing per-agent callback.

    The runtime callback (if any) runs first and its veto wins; the approval
    policy sees only calls the runtime allowed — the same chaining contract
    the use-case facade used.
    """
    for agent in iter_llm_agents(root):
        agent.before_tool_callback = _chain_before_tool(
            agent.before_tool_callback, before_tool
        )
    return root
