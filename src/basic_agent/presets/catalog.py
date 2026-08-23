"""Built-in presets — metadata, graph-spec builders, and build() (ADR-005 §5).

A preset is a named partial config: catalog metadata (key, title,
when_to_use, aliases, interfaces — **identical to the pre-E3 catalog, pinned
by the snapshot test**), runtime-defaults merge semantics (formerly
``BaseUseCaseAgent.resolve_runtime``), graph-spec builders consumed by the
C3 compilers, and a custom-hook surface equivalent to the old
``BaseUseCaseAgent`` overrides (before/after run, before/after tool).

Classification per ADR-005 §5:

- assistant → single llm node
- pipeline → sequence sugar (per-step "step N of count" defaults + roles.step_{i})
- multi_perspective → parallel + synthesis policy (workflow: with_synthesis;
  legacy: nested parallel + trailing step) — aggregation wired as its
  after-run hook (D2)
- refine_until_good → loop sugar (default max_iterations 5)
- approval_gate → propose/complete sequence + approval policy
- plan_and_execute → dynamic-planning preset on the workflow backend
  (planner spawning executors via `ctx.run_node` — E2a; legacy fallback is
  the two-role sequence)
- expert_dispatch → routing-node graph (E1 finding: the ADK graph rejects
  duplicate (from,to) edges, so no DEFAULT_ROUTE fallback)
- team_coordinator → delegation escape hatch: NO graph shape (ADR-005 §6)
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field, replace
from typing import Any

from ..config.graph import (
    START,
    GraphEdgeSpec,
    GraphNodeSpec,
    GraphSpec,
)
from ..config.sugar import LoopSugar, ParallelSugar, SequenceSugar, expand_sugar
from ..policies.synthesis import (
    legacy_multi_perspective_spec,
    make_synthesis_after_run,
    with_synthesis,
)
from ..runtime import RoleConfig, RuntimeContext

PIPELINE_STEP_INSTRUCTION = (
    "You are step {index} of {count} in this pipeline. Perform your stage of "
    "the overall task, building on the output of any previous steps, then "
    "hand off your result."
)
REFINE_INSTRUCTION = (
    "Generate a solution, evaluate it critically, and improve it. Repeat "
    "until satisfied."
)
SYNTHESIZER_INSTRUCTION = (
    "Read the perspective outputs in session state, compare where they agree "
    "or differ, and produce one balanced final answer."
)
APPROVAL_PROPOSER_INSTRUCTION = (
    "Propose a clear, actionable solution for the user's request."
)
APPROVAL_COMPLETER_INSTRUCTION = (
    "Complete the user-approved action only after the approval tool has "
    "returned confirmed. If approval is pending or rejected, do not invoke "
    "any state-changing tool; explain that the action was not authorized."
)
PLANNER_INSTRUCTION = "Create a step-by-step plan to address the request."
EXECUTOR_INSTRUCTION = "Execute the plan step by step."
EXPERTS_DEFAULT = ("research", "solution", "risk")

#: RuntimeContext dataclass defaults used to detect "caller left it at default".
_DATACLASS_DEFAULTS: dict[str, Any] = {
    "max_iterations": RuntimeContext.max_iterations,
    "require_approval": RuntimeContext.require_approval,
    "specialists": RuntimeContext.specialists,
}


def _chain(first: Callable | list[Callable] | None, second: Callable) -> Callable:
    """Return a callback calling ``first`` then ``second``.

    ``first`` may be a single callback, a list of callbacks (ADK 2.x allows
    both; list semantics: run in order until one returns non-None), or None.
    The first side's non-None return value wins; ``second`` always runs.
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


def _chain_before_tool(
    first: Callable | list[Callable] | None, second: Callable
) -> Callable:
    """Chain before-tool callbacks while preserving veto short-circuiting."""
    callbacks = list(first) if isinstance(first, list) else ([first] if first else [])

    def chained(*args: Any, **kwargs: Any) -> Any:
        for callback in callbacks:
            result = callback(*args, **kwargs)
            if result is not None:
                return result
        return second(*args, **kwargs)

    return chained


def _chain_after_tool(
    first: Callable | list[Callable] | None, second: Callable
) -> Callable:
    """Chain after-tool callbacks, allowing the preset hook to transform results."""
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


@dataclass
class Preset:
    """A named partial config: catalog metadata plus spec builders.

    Custom presets (``AGENT_USE_CASE_MODULE``) may set the hook fields; they
    are wired by :meth:`build` with the same chaining semantics the old
    ``BaseUseCaseAgent`` hooks had.
    """

    key: str
    title: str
    when_to_use: str
    aliases: tuple[str, ...] = ()
    interfaces: tuple[str, ...] = ("rest", "web", "cli")
    defaults: dict = field(default_factory=dict)
    spec: Callable[[RuntimeContext], GraphSpec] | None = None
    legacy_spec: Callable[[RuntimeContext], GraphSpec] | None = None
    legacy_name: str | None = None
    escape_hatch_reason: str | None = None
    escape_hatch_builder: Callable[[RuntimeContext], Any] | None = None
    before_run_callback: Callable[..., Any] | None = None
    after_run_callback: Callable[..., Any] | None = None
    before_tool_callback: Callable[..., Any] | None = None
    after_tool_callback: Callable[..., Any] | None = None

    def apply_defaults(self, rt: RuntimeContext) -> RuntimeContext:
        """Apply ``defaults`` onto a copy of ``rt`` (old resolve_runtime rules).

        - ``max_iterations``/``require_approval``/``specialists``: the preset
          default replaces the caller value ONLY when it still equals the
          RuntimeContext dataclass default. Any explicitly customized value
          wins.
        - ``model``/``instruction``/``tools``: applies only when the runtime
          value is empty (these have no dataclass default to compare against).
        - ``roles``: dicts merge; the caller's per-key entries win.
        """
        overrides: dict[str, Any] = {}
        for key, default_value in self.defaults.items():
            current = getattr(rt, key, None)
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
        return replace(rt, **overrides)

    def build_spec(self, rt: RuntimeContext) -> GraphSpec:
        """Return the workflow-backend spec; raises for escape-hatch presets."""
        if self.spec is not None:
            return self.spec(rt)
        raise NotImplementedError(
            self.escape_hatch_reason or f"preset {self.key!r} has no graph spec yet"
        )

    def build_legacy_spec(self, rt: RuntimeContext) -> GraphSpec:
        """Return the legacy (sugar-subset) spec; raises when unsupported."""
        if self.legacy_spec is not None:
            return self.legacy_spec(rt)
        raise NotImplementedError(
            f"preset {self.key!r} has no legacy (sugar-subset) mapping"
        )

    def build(self, rt: RuntimeContext) -> Any:
        """Compile the preset into a runnable root (via the backend flag).

        The public entry point previously served by ``BaseUseCaseAgent``:
        applies defaults, compiles via ``compile_graph`` (workflow, default)
        or ``compile_legacy`` (rollback), then wires any custom hook
        callbacks with the old chaining semantics.
        """
        from ..compile import compose_backend
        from ..compile.legacy import compile_legacy
        from ..compile.workflow import compile_graph

        resolved = self.apply_defaults(rt)
        if self.escape_hatch_builder is not None:
            root = self.escape_hatch_builder(resolved)
        elif compose_backend() == "workflow":
            root = compile_graph(self.build_spec(resolved), resolved, name=self.key)
        else:
            root = compile_legacy(
                self.build_legacy_spec(resolved),
                resolved,
                name=self.legacy_name or self.key,
            )
        if (
            self.before_tool_callback is not None
            or self.after_tool_callback is not None
        ):
            for agent in _iter_llm_agents(root):
                if self.before_tool_callback is not None:
                    agent.before_tool_callback = _chain_before_tool(
                        agent.before_tool_callback, self.before_tool_callback
                    )
                if self.after_tool_callback is not None:
                    agent.after_tool_callback = _chain_after_tool(
                        agent.after_tool_callback, self.after_tool_callback
                    )
        self._wire_run_hooks(root, resolved)
        return root

    def _wire_run_hooks(self, root: Any, resolved: RuntimeContext) -> None:
        """Wire before/after run hooks onto the root (old build() semantics)."""
        try:
            before = self.before_run_callback
            after = self.after_run_callback
            if before is not None:
                first = (
                    root.before_agent_callback
                    if root.before_agent_callback is not None
                    else resolved.before_agent_callback
                )
                root.before_agent_callback = _chain(
                    first,
                    lambda callback_context: before(callback_context),
                )
            if after is not None:
                first = (
                    root.after_agent_callback
                    if root.after_agent_callback is not None
                    else resolved.after_agent_callback
                )
                root.after_agent_callback = _chain(
                    first,
                    lambda callback_context: after(callback_context),
                )
        except AttributeError:  # pragma: no cover - no run-hook fields on nodes
            pass


def _iter_llm_agents(root: Any):
    """Yield every LlmAgent in the tree, root included, depth-first.

    Walks both legacy ``sub_agents`` trees and Workflow graphs.
    """
    from google.adk.agents import LlmAgent

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


def _assistant_spec(rt: RuntimeContext) -> GraphSpec:
    return expand_sugar(
        SequenceSugar(items=["direct_agent"]),
        {"direct_agent": GraphNodeSpec(name="direct_agent", kind="llm")},
    )


def _pipeline_spec(rt: RuntimeContext) -> GraphSpec:
    count = int((rt.extra_config or {}).get("steps", 2))
    roles = rt.roles or {}
    nodes = []
    for index in range(count):
        override = roles.get(f"step_{index}", RoleConfig())
        nodes.append(
            GraphNodeSpec(
                name=f"sequential_step_{index}",
                kind="llm",
                role=RoleConfig(
                    instruction=override.instruction
                    or PIPELINE_STEP_INSTRUCTION.format(index=index, count=count),
                    model=override.model,
                    tools=override.tools,
                ),
            )
        )
    return expand_sugar(
        SequenceSugar(items=[node.name for node in nodes]),
        {node.name: node for node in nodes},
    )


def _multi_perspective_spec(rt: RuntimeContext) -> GraphSpec:
    workers = [
        GraphNodeSpec(
            name=f"parallel_worker_{index}",
            kind="llm",
            output_key=f"perspective_{index}",
            # Intermediate state keys are not in the root state schema
            # (e.g. AgentState); clear the schema for these nodes so the
            # workflow engine does not reject the writes (legacy backends
            # never validated them).
            options={"no_state_schema": True},
        )
        for index in range(int((rt.extra_config or {}).get("workers", 2)))
    ]
    parallel = expand_sugar(
        ParallelSugar(items=[node.name for node in workers]),
        {node.name: node for node in workers},
    )
    return with_synthesis(parallel)


def _multi_perspective_legacy(rt: RuntimeContext) -> GraphSpec:
    count = int((rt.extra_config or {}).get("workers", 2))
    return legacy_multi_perspective_spec(
        [f"parallel_worker_{index}" for index in range(count)]
    )


def _refine_spec(rt: RuntimeContext) -> GraphSpec:
    body = GraphNodeSpec(
        name="evaluator_optimizer_worker",
        kind="llm",
        role=RoleConfig(instruction=REFINE_INSTRUCTION),
    )
    return expand_sugar(
        LoopSugar(body=body.name, max_iterations=rt.max_iterations),
        {body.name: body},
    )


def _approval_gate_spec(rt: RuntimeContext) -> GraphSpec:
    proposer = GraphNodeSpec(
        name="human_in_loop_proposer",
        kind="llm",
        role=RoleConfig(instruction=APPROVAL_PROPOSER_INSTRUCTION),
    )
    completer = GraphNodeSpec(
        name="human_in_loop_completer",
        kind="llm",
        role=RoleConfig(instruction=APPROVAL_COMPLETER_INSTRUCTION),
    )
    return expand_sugar(
        SequenceSugar(items=[proposer.name, completer.name]),
        {proposer.name: proposer, completer.name: completer},
    )


def _plan_execute_spec(rt: RuntimeContext) -> GraphSpec:
    """Dynamic-planning preset (E2a): a planner node spawns executors.

    The planner is a ``function`` node (``options.function: plan_execute``)
    that runs the executor node once per plan step via ``ctx.run_node`` —
    the engine's dynamic scheduler (dedup/resume by run_id).  The executor
    is edge-disconnected: it is only ever spawned dynamically.  The legacy
    fallback remains the two-role sequence (``_plan_execute_legacy``).
    """
    planner = GraphNodeSpec(
        name="planner_agent",
        kind="function",
        options={
            "function": "plan_execute",
            "executor": "executor_agent",
            "steps": ["step 1", "step 2", "step 3"],
        },
    )
    executor = GraphNodeSpec(name="executor_agent", kind="llm")
    spec = GraphSpec(
        nodes=[planner, executor],
        edges=[GraphEdgeSpec(source=START, target="planner_agent")],
    )
    spec.validate()
    return spec


def _plan_execute_legacy(rt: RuntimeContext) -> GraphSpec:
    planner = GraphNodeSpec(
        name="planner_agent",
        kind="llm",
        role=RoleConfig(instruction=PLANNER_INSTRUCTION),
    )
    executor = GraphNodeSpec(
        name="executor_agent",
        kind="llm",
        role=RoleConfig(instruction=EXECUTOR_INSTRUCTION),
    )
    return expand_sugar(
        SequenceSugar(items=[planner.name, executor.name]),
        {planner.name: planner, executor.name: executor},
    )


def _expert_dispatch_spec(rt: RuntimeContext) -> GraphSpec:
    """Routing-node graph: a router function emits a specialist route.

    The router's implementation is supplied at compile time via
    ``options.function = 'route_dispatch'`` (in the default function
    registry).  Edge routes carry a per-specialist route; there is no
    DEFAULT_ROUTE fallback (ADK rejects duplicate (from,to) edge pairs — E1
    finding), so the router function must always emit a valid route.
    """
    specialists = list(rt.specialists) or list(EXPERTS_DEFAULT)
    roles = rt.roles or {}
    router = GraphNodeSpec(
        name="router_agent",
        kind="function",
        options={
            "function": "route_dispatch",
            "default_route": specialists[0],
        },
    )
    specialist_nodes = []
    for name in specialists:
        override = roles.get(name, RoleConfig())
        specialist_nodes.append(
            GraphNodeSpec(
                name=f"router_specialist_{name}",
                kind="llm",
                role=RoleConfig(
                    instruction=override.instruction
                    or f"You are the {name} specialist. Handle requests in your domain.",
                    model=override.model,
                    tools=override.tools,
                ),
            )
        )
    nodes = [router] + specialist_nodes
    edges = [GraphEdgeSpec(source=START, target=router.name)]
    for index, node in enumerate(specialist_nodes):
        edges.append(
            GraphEdgeSpec(
                source=router.name, target=node.name, route=specialists[index]
            )
        )
    spec = GraphSpec(nodes=nodes, edges=edges)
    spec.validate()
    return spec


def _team_coordinator_spec(rt: RuntimeContext) -> GraphSpec:
    raise NotImplementedError(
        "team_coordinator is the delegation escape hatch (ADR-005 §6): "
        "LlmAgent + sub_agents (and/or _TaskAgentTool task delegation) until "
        "upstream #5581 / Node-as-Tool settles; no graph shape is defined."
    )


def _team_coordinator_escape(rt: RuntimeContext) -> Any:
    """Delegation escape hatch shape (old SupervisorStrategy output).

    ``LlmAgent`` supervisor with ``supervisor_worker_{i}`` sub-agents
    (count from ``extra_config['workers']``, default 2; per-index overrides
    via ``roles.worker_{i}`` — the same contract the pre-E3 implementation
    had).
    """
    from ..compile.llm_node import build_llm_agent

    count = int((rt.extra_config or {}).get("workers", 2))
    roles = rt.roles or {}
    workers = []
    for index in range(count):
        override = roles.get(f"worker_{index}", RoleConfig())
        workers.append(
            build_llm_agent(
                rt,
                name=f"supervisor_worker_{index}",
                role=RoleConfig(
                    instruction=override.instruction
                    or (
                        f"You are worker {index} of {count} on this team. "
                        "Handle the portion of the coordinator's request "
                        "assigned to you, then report your result back."
                    ),
                    model=override.model,
                    tools=override.tools,
                ),
            )
        )
    return build_llm_agent(
        rt,
        name="supervisor_agent",
        description=rt.description,
        sub_agents=workers,
    )


PRESETS: dict[str, Preset] = {
    preset.key: preset
    for preset in [
        Preset(
            key="assistant",
            title="Assistant",
            when_to_use=(
                "You want questions answered directly, with optional tool-based "
                "search and investigation."
            ),
            interfaces=("rest", "web", "cli", "live"),
            spec=_assistant_spec,
            legacy_spec=_assistant_spec,
            legacy_name="direct_agent",
        ),
        Preset(
            key="pipeline",
            title="Pipeline",
            when_to_use=(
                "You want fixed steps always executed in the same order, like "
                "fetch, analyze, summarize."
            ),
            spec=_pipeline_spec,
            legacy_spec=_pipeline_spec,
            legacy_name="sequential_agent",
        ),
        Preset(
            key="multi_perspective",
            title="Multi-Perspective",
            when_to_use=(
                "You want several independent takes on the same question "
                "compared or combined."
            ),
            spec=_multi_perspective_spec,
            legacy_spec=_multi_perspective_legacy,
            legacy_name="multi_perspective_agent",
            after_run_callback=make_synthesis_after_run(),
        ),
        Preset(
            key="refine_until_good",
            title="Refine Until Good",
            when_to_use=(
                "You want the agent to critique and improve its own output "
                "until it meets a quality bar."
            ),
            defaults={"max_iterations": 5},
            spec=_refine_spec,
            legacy_spec=_refine_spec,
            legacy_name="evaluator_optimizer_agent",
        ),
        Preset(
            key="expert_dispatch",
            title="Expert Dispatch",
            when_to_use=(
                "You want each incoming question routed to the right "
                "specialist out of a fixed roster."
            ),
            defaults={"specialists": EXPERTS_DEFAULT},
            spec=_expert_dispatch_spec,
        ),
        Preset(
            key="team_coordinator",
            title="Team Coordinator",
            when_to_use=(
                "You want complex work decomposed and delegated to worker "
                "agents by a coordinator."
            ),
            spec=_team_coordinator_spec,
            escape_hatch_reason=(
                "team_coordinator is the delegation escape hatch (ADR-005 §6): "
                "LlmAgent + sub_agents (and/or _TaskAgentTool task delegation) "
                "until upstream #5581 / Node-as-Tool settles."
            ),
            escape_hatch_builder=_team_coordinator_escape,
        ),
        Preset(
            key="plan_and_execute",
            title="Plan and Execute",
            when_to_use=(
                "You want large tasks split into a plan first and executed "
                "step by step afterwards."
            ),
            spec=_plan_execute_spec,
            legacy_spec=_plan_execute_legacy,
            legacy_name="plan_execute_agent",
        ),
        Preset(
            key="approval_gate",
            title="Approval Gate",
            when_to_use=(
                "You want risky or irreversible actions held back until a "
                "human approves them."
            ),
            defaults={"require_approval": True},
            spec=_approval_gate_spec,
            legacy_spec=_approval_gate_spec,
            legacy_name="human_in_loop_agent",
        ),
    ]
}
