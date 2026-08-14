"""Approval gate use case: risky actions wait for human sign-off."""

from __future__ import annotations

from .base import BaseUseCaseAgent
from ..strategies import HumanInLoopStrategy


class ApprovalGateAgent(BaseUseCaseAgent):
    """Proposes actions and gates irreversible ones behind human approval."""

    use_case = "approval_gate"
    title = "Approval Gate"
    when_to_use = "You want risky or irreversible actions held back until a human approves them."
    aliases = ("human_in_loop",)
    defaults = {"require_approval": True}
    strategy = HumanInLoopStrategy()

    gated_tools: tuple[str, ...] = ("request_approval",)
    gated_prefixes: tuple[str, ...] = ()

    def before_tool(self, tool, args: dict, tool_context) -> dict | None:
        """Veto gated tools unless ``human_approved`` is truthy in state.

        Returns a blocking result dict (ADK before_tool_callback semantics:
        a non-None dict skips the actual tool call) or None to proceed.
        """
        try:
            name = getattr(tool, "name", tool)
            gated = name in self.gated_tools or any(
                isinstance(name, str) and name.startswith(p) for p in self.gated_prefixes
            )
            if gated and not tool_context.state.get("human_approved"):
                return {
                    "status": "blocked",
                    "reason": "This action requires human approval before execution.",
                }
        except Exception:  # noqa: BLE001 - tolerate fake/simple contexts
            pass
        return None
