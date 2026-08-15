"""Base use-case agent facade owning a composed ADK tree."""

from __future__ import annotations

import dataclasses
from typing import Any, Callable, ClassVar

from google.adk.agents import BaseAgent, LlmAgent

from ..strategies.base import AgentStrategy, AgentStrategyContext, RuntimeContext

# RuntimeContext dataclass defaults used to detect "caller left it at default".
_DATACLASS_DEFAULTS: dict[str, Any] = {
    "max_iterations": RuntimeContext.max_iterations,
    "require_approval": RuntimeContext.require_approval,
    "specialists": RuntimeContext.specialists,
}


def _chain(first: Callable | list[Callable] | None, second: Callable) -> Callable:
    """Return a callback calling ``first`` then ``second``.

    ``first`` may be a single callback, a list of callbacks (ADK 2.x allows
    both; list semantics: run in order until one returns non-None), or None.
    The first side's non-None return value wins (ADK semantics: a non-None
    result from before-agent/before-tool callbacks short-circuits the default
    behavior). The ``second`` hook always runs.
    """
    callbacks = list(first) if isinstance(first, list) else ([first] if first else [])

    def chained(*args: Any, **kwargs: Any) -> Any:
        first_result = None
        for cb in callbacks:
            first_result = cb(*args, **kwargs)
            if first_result is not None:
                break
        second_result = second(*args, **kwargs)
        return first_result if first_result is not None else second_result

    return chained


def _chain_before_tool(first: Callable | list[Callable] | None, second: Callable) -> Callable:
    """Chain before-tool callbacks while preserving veto short-circuiting."""
    callbacks = list(first) if isinstance(first, list) else ([first] if first else [])

    def chained(*args: Any, **kwargs: Any) -> Any:
        for callback in callbacks:
            result = callback(*args, **kwargs)
            if result is not None:
                return result
        return second(*args, **kwargs)

    return chained


def _chain_after_tool(first: Callable | list[Callable] | None, second: Callable) -> Callable:
    """Chain after-tool callbacks, allowing the use-case hook to transform results."""
    callbacks = list(first) if isinstance(first, list) else ([first] if first else [])

    def chained(*args: Any, **kwargs: Any) -> Any:
        result = None
        for callback in callbacks:
            candidate = callback(*args, **kwargs)
            if candidate is not None:
                result = candidate
        candidate = second(*args, **kwargs)
        return candidate if candidate is not None else result

    return chained


def _iter_llm_agents(root: BaseAgent):
    """Yield every LlmAgent in the tree, root included, depth-first."""
    stack = [root]
    while stack:
        node = stack.pop()
        if isinstance(node, LlmAgent):
            yield node
        stack.extend(reversed(getattr(node, "sub_agents", None) or []))


class BaseUseCaseAgent:
    """Facade for a user-facing use case; owns a composed ADK agent tree.

    Not an ``Agent`` subclass: multi-agent shapes (sequential, parallel, ...)
    cannot single-inherit. Subclasses declare metadata (``use_case``, ``title``,
    ``when_to_use``, ``aliases``), pick a ``strategy``, and optionally override
    runtime hooks (``before_run``/``after_run``/``before_tool``/``after_tool``).
    Only overridden hooks are wired into the built tree.
    """

    use_case: str = ""
    title: str = ""
    when_to_use: str = ""
    defaults: ClassVar[dict] = {}
    aliases: tuple[str, ...] = ()
    strategy: AgentStrategy
    # Interfaces this use case fits: rest (API/A2A), web (adk web UI),
    # cli (adk run), live (WebSocket voice/streaming). Chat-like use cases
    # add "live"; every built-in supports rest/web/cli.
    interfaces: tuple[str, ...] = ("rest", "web", "cli")

    def resolve_runtime(self, runtime: RuntimeContext) -> RuntimeContext:
        """Apply ``self.defaults`` onto a copy of ``runtime``.

        Merge rule (pragmatic — detect "caller left it at default"):
        - ``max_iterations``/``require_approval``/``specialists``: the use-case
          default replaces the caller value ONLY when it still equals the
          RuntimeContext dataclass default (3 / False / ()). Any explicitly
          customized value wins.
        - ``model``/``instruction``/``tools``: the use-case default applies only
          when the runtime value is empty (these have no dataclass default to
          compare against).
        - ``roles``: dicts merge; the caller's per-key entries win.
        """
        overrides: dict[str, Any] = {}
        for key, default_value in self.defaults.items():
            current = getattr(runtime, key, None)
            if key == "roles":
                overrides[key] = {**default_value, **(current or {})}
            elif key in _DATACLASS_DEFAULTS:
                if current == _DATACLASS_DEFAULTS[key]:
                    overrides[key] = default_value
            elif key in ("model", "instruction", "tools"):
                if not current:
                    overrides[key] = default_value
            else:
                overrides[key] = default_value
        return dataclasses.replace(runtime, **overrides)

    def compose(self, runtime: RuntimeContext) -> BaseAgent:
        """Build the ADK tree via this use case's strategy (no hook wiring)."""
        resolved = self.resolve_runtime(runtime)
        return self.strategy.build(
            AgentStrategyContext(
                agent_type=self.strategy.agent_type,
                runtime=resolved,
                extra_config=dict(resolved.extra_config),
            )
        )

    def build(self, runtime: RuntimeContext) -> BaseAgent:
        """Compose the tree and wire overridden hooks as ADK callbacks.

        - ``before_run``/``after_run`` attach to the ROOT agent's
          ``before_agent_callback``/``after_agent_callback``, chaining after any
          runtime-supplied callback (runtime callback runs first, both run).
        - ``before_tool``/``after_tool`` attach to every LlmAgent in the tree.
          ``before_tool`` may veto: returning a dict skips the actual tool call
          (ADK before_tool_callback semantics); return None to proceed.
        """
        resolved = self.resolve_runtime(runtime)
        root = self.compose(resolved)

        cls = type(self)
        if cls.before_run is not BaseUseCaseAgent.before_run:
            first = (
                root.before_agent_callback
                if root.before_agent_callback is not None
                else resolved.before_agent_callback
            )
            root.before_agent_callback = _chain(first, lambda ctx: self.before_run(ctx))
        if cls.after_run is not BaseUseCaseAgent.after_run:
            first = (
                root.after_agent_callback
                if root.after_agent_callback is not None
                else resolved.after_agent_callback
            )
            root.after_agent_callback = _chain(first, lambda ctx: self.after_run(ctx))
        if cls.before_tool is not BaseUseCaseAgent.before_tool:
            for agent in _iter_llm_agents(root):
                first = agent.before_tool_callback or resolved.before_tool_callback
                agent.before_tool_callback = _chain_before_tool(
                    first,
                    lambda tool, args, tool_context: self.before_tool(
                        tool, args, tool_context
                    ),
                )
        if cls.after_tool is not BaseUseCaseAgent.after_tool:
            for agent in _iter_llm_agents(root):
                first = agent.after_tool_callback or resolved.after_tool_callback
                agent.after_tool_callback = _chain_after_tool(
                    first,
                    lambda tool, args, tool_context, result: self.after_tool(
                        tool, args, tool_context, result
                    ),
                )
        return root

    # Runtime hooks — default no-ops; only overridden hooks are wired.

    def before_run(self, callback_context: Any) -> Any:
        """Hook run before the agent tree; override to customize."""

    def after_run(self, callback_context: Any) -> Any:
        """Hook run after the agent tree; override to customize."""

    def before_tool(self, tool: Any, args: dict, tool_context: Any) -> dict | None:
        """Hook run before each tool call; return a dict to veto the call."""

    def after_tool(self, tool: Any, args: dict, tool_context: Any, result: dict) -> Any:
        """Hook run after each tool call; may transform ``result``."""
