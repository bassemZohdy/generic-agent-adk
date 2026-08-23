"""Workflow-backend compiler (ADR-005 §3; TODO Phase C3).

Turns a full ``GraphSpec`` (explicit edges, routes, nesting) into an ADK
``google.adk.workflow.Workflow`` graph.  Explicit ``Edge`` objects are
emitted (rather than the chain-tuple sugar) so the mapping from config edges
to graph edges stays 1:1 and testable.  ``START`` sources map to the
engine's START node; our ``DEFAULT_ROUTE`` is the engine's value already
(verified in B0).
"""

from __future__ import annotations

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
from ..strategies.base import RuntimeContext
from ..tools import build_tool
from .llm_node import build_llm_agent, resolve_role_spec, resolve_schema

SchemaRegistry = dict[str, type]
FunctionRegistry = dict[str, Callable[..., Any]]


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


def _resolve_function(
    node: GraphNodeSpec,
    functions: FunctionRegistry,
) -> Callable[..., Any]:
    """Resolve a function-kind node's implementation.

    ``options.kind == 'loop_counter'`` selects the built-in bounded-loop
    counter; otherwise ``options.function`` names an entry in the
    ``function_registry`` passed to :func:`compile_graph`.
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
    if isinstance(key, str) and key in functions:
        return functions[key]
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
    schemas = schema_registry or {}
    functions = function_registry or {}

    def compile_node(node_spec: GraphNodeSpec) -> BaseNode:
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
            return build_llm_agent(
                rt,
                name=node_spec.name,
                role=role,
                output_key=node_spec.output_key,
                output_schema=resolve_schema(node_spec.output_schema, schemas),
                state_schema=resolve_schema(node_spec.state_schema, schemas),
                retry_config=retry,
                timeout=timeout,
            )
        if node_spec.kind == "join":
            return JoinNode(name=node_spec.name, retry_config=retry, timeout=timeout)
        if node_spec.kind == "function":
            func = _resolve_function(node_spec, functions)
            return FunctionNode(
                func=func,
                name=node_spec.name,
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

    compiled = {node.name: compile_node(node) for node in spec.nodes}

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
