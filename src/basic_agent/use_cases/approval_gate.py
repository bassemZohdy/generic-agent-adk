"""Approval gate use case: risky actions wait for human sign-off."""

from __future__ import annotations

import logging
from typing import ClassVar

from ..strategies import HumanInLoopStrategy
from .base import BaseUseCaseAgent

logger = logging.getLogger(__name__)


class ApprovalGateAgent(BaseUseCaseAgent):
    """Proposes actions and gates irreversible ones behind human approval."""

    use_case = "approval_gate"
    title = "Approval Gate"
    when_to_use = (
        "You want risky or irreversible actions held back until a human approves them."
    )
    aliases = ()
    defaults: ClassVar[dict] = {"require_approval": True}
    strategy = HumanInLoopStrategy()

    # The approval tool itself is the mechanism that creates a confirmation
    # request.  Gating it behind an already-approved state deadlocks the flow.
    gated_tools: tuple[str, ...] = ()
    gated_prefixes: tuple[str, ...] = ()

    def before_tool(self, tool, args: dict, tool_context) -> dict | None:
        """Apply optional use-case gates without deadlocking approval.

        Global runtime policy handles unknown/state-changing tools and invokes
        ADK's resumable ``request_confirmation`` boundary. This hook remains
        for deployments that explicitly declare additional gated names; the
        ``request_approval`` tool itself must stay callable so it can create
        the pending confirmation event.
        """
        try:
            name = getattr(tool, "name", tool)
            if name == "request_approval":
                return None
            gated = name in self.gated_tools or any(
                isinstance(name, str) and name.startswith(p)
                for p in self.gated_prefixes
            )
            if gated and not tool_context.state.get("human_approved"):
                request_confirmation = getattr(
                    tool_context, "request_confirmation", None
                )
                if callable(request_confirmation):
                    request_confirmation(
                        hint=f"Confirm state-changing tool: {name}",
                        payload={"tool": name, "arguments": args},
                    )
                return {
                    "status": "blocked",
                    "reason": "This action requires human approval before execution.",
                }
        except Exception:
            logger.debug("Unable to evaluate approval-gate tool state", exc_info=True)
        return None
