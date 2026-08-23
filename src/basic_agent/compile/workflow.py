"""Workflow-backend compiler (ADR-005 §3; TODO Phase C3).

Turns a full ``GraphSpec`` (explicit edges, routes, nesting) into an ADK
``google.adk.workflow.Workflow`` graph.  Explicit ``Edge`` objects are
emitted (rather than the chain-tuple sugar) so the mapping from config edges
to graph edges stays 1:1 and testable.  ``START`` sources map to the
engine's START node; our ``DEFAULT_ROUTE`` is the engine's value already
(verified in B0).
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import Any

from google.adk.workflow import (
    START as ADK_START,
)
from google.adk.workflow import (
    BaseNode,
    Edge,
    FunctionNode,
    JoinNode,
    RetryConfig,
    Workflow,
)

from ..config.graph import START, GraphNodeSpec, GraphSpec, RetrySpec
from ..config.sugar import AGAIN_ROUTE
from ..models import resolve_model
from ..runtime import RuntimeContext
from ..tools import build_tool
from .llm_node import _UNSET, build_llm_agent, resolve_role_spec, resolve_schema

SchemaRegistry = dict[str, type]
FunctionRegistry = dict[str, Callable[..., Any]]

logger = logging.getLogger(__name__)


def default_route_dispatch(
    ctx: Any, node_input: Any = None, default_route: str = "research"
) -> None:
    """Default routing-node implementation (ADR-005 §5, TODO E2).

    Deterministic, state-driven routing: uses ``ctx.state['routed_to']`` when
    present (matched against the graph's route edges at runtime), else
    ``default_route`` — the preset's first specialist, bound at compile time
    from the router node's ``options.default_route``.  Presets/custom
    configs can replace it via the function registry; an emitted route with
    no matching edge ends the branch (engine behavior).
    """
    route = ctx.state.get("routed_to", default_route)
    ctx.route = route if isinstance(route, str) and route else default_route


def default_aggregate_perspectives(ctx: Any, node_input: Any = None) -> None:
    """Default synthesis aggregation (D2): ``perspective_*`` → aggregated list.

    Boundary-node equivalent of
    ``policies.synthesis.make_synthesis_after_run`` for the workflow
    backend: runs after the synthesizer node and writes
    ``aggregated_perspectives`` into session state with the exact key and
    ordering the multi_perspective use case used.
    """
    try:
        # ADK's State is a delta-tracking view: snapshot via to_dict() to
        # iterate it, then write the aggregate back (recorded as a delta).
        state = ctx.state
        source = state.to_dict() if hasattr(state, "to_dict") else state
        keys = sorted(
            (key for key in source if key.startswith("perspective_")),
            key=lambda key: (
                int(key.split("_", 1)[1]) if key.split("_", 1)[1].isdigit() else 2**63
            ),
        )
        state["aggregated_perspectives"] = [source[key] for key in keys]
    except Exception:
        # Runtime boundary (graph function): never propagate — raising here
        # would fail the node — but surface the failure at warning level
        # and mark state so downstream consumers can detect the absence
        # instead of silently missing ``aggregated_perspectives`` (R10).
        logger.warning("Unable to aggregate multi-perspective state", exc_info=True)
        try:
            ctx.state["aggregation_failed"] = True
        except Exception:
            # State itself is broken: still never propagate (graph function).
            logger.warning(
                "Unable to write aggregation_failed state marker", exc_info=True
            )


#: Built-in function implementations resolvable from ``options.function``.
DEFAULT_FUNCTION_REGISTRY: FunctionRegistry = {
    "route_dispatch": default_route_dispatch,
    "aggregate_perspectives": default_aggregate_perspectives,
}


def _retry_config(spec: RetrySpec | None) -> RetryConfig | None:
    """Map the config RetrySpec onto the ADK RetryConfig (None = engine default)."""
    if spec is None:
        return None
    return RetryConfig(
        max_attempts=spec.max_attempts,
        initial_delay=spec.initial_delay,
        max_delay=spec.max_delay,
        backoff_factor=spec.backoff_factor,
        jitter=spec.jitter,
    )


def _make_loop_counter(counter_name: str, max_iterations: int) -> Callable[..., Any]:
    """Build the bounded-loop counter function for a loop sugar.

    Runs AFTER the loop body each iteration: increments the counter in
    session state and emits ``"again"`` while the budget lasts; when the
    budget is exhausted it emits no route, so the default edge (if any)
    carries the flow onward.  Matches the semantics proven in Phase B's
    ``test_workflow_routed_bounded_loop``.
    """

    def loop_counter(ctx: Any, node_input: Any = None) -> None:
        key = f"{counter_name}_count"
        count = int(ctx.state.get(key, 0)) + 1
        ctx.state[key] = count
        if count < max_iterations:
            ctx.route = AGAIN_ROUTE

    return loop_counter


def _make_plan_execute(executor_node: BaseNode, steps: list[str]) -> Callable[..., Any]:
    """Build the dynamic plan-and-execute function (E2a).

    Spawns the executor node once per plan step via ``ctx.run_node`` (the
    engine's DynamicNodeScheduler — dedup/resume/replay handled by run_id),
    collects the outputs, and publishes ``plan_outputs`` to session state.
    The planner's ``rerun_on_resume`` is set at FunctionNode construction.
    """

    async def plan_execute(ctx: Any, node_input: Any = None) -> None:
        # Steps are independent (each has its own run_id and sub-branch), so
        # dispatch them concurrently (R14).  asyncio.gather preserves the
        # awaitables' input order in its result list, so plan_outputs stays
        # in step order.
        outputs = await asyncio.gather(
            *(
                ctx.run_node(
                    executor_node,
                    node_input=step,
                    run_id=f"plan_step_{index}",
                    use_sub_branch=True,
                    raise_on_wait=True,
                )
                for index, step in enumerate(steps)
            )
        )
        ctx.state["plan_outputs"] = list(outputs)

    return plan_execute


def _resolve_function(
    node: GraphNodeSpec,
    functions: FunctionRegistry,
    compiled: dict[str, BaseNode] | None = None,
) -> Callable[..., Any]:
    """Resolve a function-kind node's implementation.

    ``options.kind == 'loop_counter'`` selects the built-in bounded-loop
    counter; otherwise ``options.function`` names an entry in the
    ``function_registry`` passed to :func:`compile_graph`.  The built-in
    ``plan_execute`` (E2a) gets the compiled executor node bound in.
    """
    options = node.options
    if options.get("kind") == "loop_counter":
        max_iterations = options.get("max_iterations")
        if not isinstance(max_iterations, int) or max_iterations < 1:
            raise ValueError(
                f"loop counter node {node.name!r} requires options.max_iterations >= 1"
            )
        return _make_loop_counter(node.name, max_iterations)
    key = options.get("function")
    if key == "plan_execute":
        # Dynamic planning (E2a): bind the compiled executor node and the
        # plan steps (the executor is edge-disconnected and spawned via
        # ctx.run_node at runtime).
        executor_name = options.get("executor")
        if (
            not isinstance(executor_name, str)
            or not compiled
            or executor_name not in compiled
        ):
            raise ValueError(
                f"plan_execute node {node.name!r} requires options.executor "
                "naming a compiled node in the same graph"
            )
        steps = options.get("steps", ["step 1", "step 2", "step 3"])
        if not isinstance(steps, list) or not all(isinstance(s, str) for s in steps):
            raise ValueError(
                f"plan_execute node {node.name!r} options.steps must be a "
                "list of strings"
            )
        return _make_plan_execute(compiled[executor_name], steps)
    if isinstance(key, str) and key in functions:
        func = functions[key]
        if func is DEFAULT_FUNCTION_REGISTRY["route_dispatch"]:
            # Bind the preset's default route (first specialist) into the
            # built-in router so it matches the graph's route edges.  Custom
            # routers control their own behavior and are passed through.
            default = options.get("default_route", "research")
            if isinstance(default, str) and default:
                from functools import partial

                return partial(func, default_route=default)
        return func
    raise ValueError(
        f"function node {node.name!r} requires options.function (an entry in "
        "the function registry) or options.kind='loop_counter'"
    )


def compile_graph(
    spec: GraphSpec,
    rt: RuntimeContext,
    *,
    name: str = "graph_agent",
    config: Any = None,
    schema_registry: SchemaRegistry | None = None,
    function_registry: FunctionRegistry | None = None,
    known_tools: set[str] | None = None,
) -> Workflow:
    """Compile a GraphSpec into an ADK Workflow (the served root).

    Args:
        spec: The validated graph spec.
        rt: Shared runtime context (model, instruction, tools, callbacks…).
        name: Root workflow name (valid Python identifier).
        config: Optional AgentConfig for role tool/model resolution.
        schema_registry: Schema name → type resolution for per-node schemas.
        function_registry: options.function → callable resolution.
        known_tools: Tool-name allowlist for role resolution (defaults to
            ``agent._KNOWN_TOOLS`` semantics via the caller).

    Returns:
        A Workflow ready to be served as ``Runner(node=...)`` root.
    """
    spec.validate()
    # Built-in functions (e.g. route_dispatch) always resolve; explicit
    # registries override them by name.
    functions = {**DEFAULT_FUNCTION_REGISTRY, **(function_registry or {})}
    schemas = schema_registry or {}

    def compile_node(
        node_spec: GraphNodeSpec, compiled: dict[str, BaseNode]
    ) -> BaseNode:
        retry = _retry_config(node_spec.retry)
        timeout = node_spec.timeout
        if node_spec.kind == "llm":
            role = resolve_role_spec(
                node_spec.role,
                config=config,
                known_tools=known_tools or set(),
                resolve_model=resolve_model,
                build_tool=build_tool,
            )
            # ``options.no_state_schema`` clears the schema for nodes that
            # write intermediate keys the root schema does not declare
            # (e.g. multi_perspective workers); an explicit per-node schema
            # overrides it; otherwise the runtime default applies.
            if node_spec.options.get("no_state_schema"):
                state_schema: type | None | object = None
            elif node_spec.state_schema is not None:
                state_schema = resolve_schema(node_spec.state_schema, schemas)
            else:
                state_schema = _UNSET
            return build_llm_agent(
                rt,
                name=node_spec.name,
                role=role,
                output_key=node_spec.output_key,
                output_schema=resolve_schema(node_spec.output_schema, schemas),
                state_schema=state_schema,
                retry_config=retry,
                timeout=timeout,
            )
        if node_spec.kind == "join":
            return JoinNode(name=node_spec.name, retry_config=retry, timeout=timeout)
        if node_spec.kind == "function":
            func = _resolve_function(node_spec, functions, compiled)
            return FunctionNode(
                func=func,
                name=node_spec.name,
                rerun_on_resume=True,
                retry_config=retry,
                timeout=timeout,
            )
        # kind == "graph": recursive subgraph.
        assert node_spec.graph is not None
        return compile_graph(
            node_spec.graph,
            rt,
            name=node_spec.name,
            config=config,
            schema_registry=schemas,
            function_registry=functions,
            known_tools=known_tools,
        )

    # Two-phase compile: function nodes that need sibling nodes (dynamic
    # plan_execute spawns its executor via ctx.run_node) compile after the
    # rest of the map is available.
    compiled: dict[str, BaseNode] = {}
    deferred: list[GraphNodeSpec] = []
    for node in spec.nodes:
        if node.kind == "function" and node.options.get("function") == "plan_execute":
            deferred.append(node)
        else:
            compiled[node.name] = compile_node(node, compiled)
    for node_spec in deferred:
        compiled[node_spec.name] = compile_node(node_spec, compiled)

    edges: list[Any] = []
    for edge_spec in spec.edges:
        source = ADK_START if edge_spec.source == START else compiled[edge_spec.source]
        targets = (
            edge_spec.target
            if isinstance(edge_spec.target, list)
            else [edge_spec.target]
        )
        for target in targets:
            edges.append(
                Edge(
                    from_node=source,
                    to_node=compiled[target],
                    route=edge_spec.route,
                )
            )
    return Workflow(name=name, edges=edges)
