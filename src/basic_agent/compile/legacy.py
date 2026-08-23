"""Legacy-backend compiler (ADR-005 §3; TODO Phase C3 — rollback-only).

Compiles the sugar subset (``sequence``/``parallel``/``loop`` shapes) into the
deprecated legacy ADK trees (``SequentialAgent``/``ParallelAgent``/
``LoopAgent``).  This is the one-release rollback path — **no new capability
is built on the deprecated classes**; explicit-edge specs (routing, joins,
nesting) are the workflow backend's job and raise here.

The shape is read from ``GraphSpec.shape`` (set by sugar expansion); the
node names inside the spec are the preset-provided names and must match the
C4 parity mapping.
"""

from __future__ import annotations

from typing import Any

from google.adk.agents import BaseAgent, LoopAgent, ParallelAgent, SequentialAgent

from ..config.graph import START, GraphSpec
from ..models import resolve_model
from ..strategies.base import RuntimeContext
from ..tools import build_tool
from .llm_node import build_llm_agent, resolve_role_spec, resolve_schema

SchemaRegistry = dict[str, type]


def _edges_by_source(spec: GraphSpec) -> dict[str, list[str]]:
    indexed: dict[str, list[str]] = {}
    for edge in spec.edges:
        targets = edge.target if isinstance(edge.target, list) else [edge.target]
        for target in targets:
            indexed.setdefault(edge.source, []).append(target)
    return indexed


def _linear_order(spec: GraphSpec) -> list[str]:
    """Return the ordered node names of a linear chain (sequence shape)."""
    by_name = spec.nodes_by_name()
    edges = _edges_by_source(spec)
    start_edges = edges.get(START, [])
    if len(start_edges) != 1:
        raise ValueError("legacy sequence compile requires exactly one edge from START")
    order: list[str] = []
    current = start_edges[0]
    for _ in range(len(by_name)):
        order.append(current)
        following = edges.get(current, [])
        if not following:
            break
        if len(following) != 1:
            raise ValueError(
                "legacy sequence compile only supports linear chains "
                f"(node {current!r} fans out)"
            )
        current = following[0]
    if set(order) != set(by_name) or len(order) != len(by_name):
        raise ValueError("legacy sequence compile: spec is not a linear chain")
    return order


def compile_legacy(
    spec: GraphSpec,
    rt: RuntimeContext,
    *,
    name: str | None = None,
    config: Any = None,
    schema_registry: SchemaRegistry | None = None,
    known_tools: set[str] | None = None,
) -> BaseAgent:
    """Compile a sugar-shaped GraphSpec into a legacy ADK agent tree.

    Raises:
        ValueError: If the spec is not a supported sugar shape (explicit
            edges, routing, joins, or nesting are workflow-backend only) or
            the sugar structure is malformed.
    """
    spec.validate()
    shape = spec.shape
    if shape not in ("sequence", "parallel", "loop"):
        raise ValueError(
            f"legacy compiler covers the sugar subset only (sequence, "
            f"parallel, loop); got shape={shape!r}"
        )

    by_name = spec.nodes_by_name()
    schemas = schema_registry or {}

    def build_step(node_name: str) -> BaseAgent:
        node = by_name[node_name]
        role = resolve_role_spec(
            node.role,
            config=config,
            known_tools=known_tools or set(),
            resolve_model=resolve_model,
            build_tool=build_tool,
        )
        return build_llm_agent(
            rt,
            name=node.name,
            role=role,
            output_key=node.output_key,
            output_schema=resolve_schema(node.output_schema, schemas),
            state_schema=resolve_schema(node.state_schema, schemas),
        )

    def compile_item(node_name: str) -> BaseAgent:
        """Compile one sequence item (llm node or nested sugar subgraph)."""
        node = by_name[node_name]
        if node.kind == "llm":
            return build_step(node_name)
        if node.kind == "graph" and node.graph is not None:
            return compile_legacy(
                node.graph,
                rt,
                name=node.name,
                config=config,
                schema_registry=schemas,
                known_tools=known_tools,
            )
        raise ValueError(
            f"legacy sequence compile does not support node {node_name!r} "
            f"of kind {node.kind!r}"
        )

    if shape == "sequence":
        order = _linear_order(spec)
        if len(order) == 1 and by_name[order[0]].kind == "llm":
            # Single llm node (assistant preset): the legacy tree is the
            # bare LlmAgent, mirroring DirectStrategy.
            return build_step(order[0])
        steps = [compile_item(node_name) for node_name in order]
        return SequentialAgent(
            name=name or "sequential_agent",
            description=rt.description,
            sub_agents=steps,
        )

    if shape == "parallel":
        join_nodes = {n.name for n in spec.nodes if n.kind == "join"}
        worker_names = [n.name for n in spec.nodes if n.name not in join_nodes]
        for worker_name in worker_names:
            if by_name[worker_name].kind != "llm":
                raise ValueError(
                    f"legacy parallel compile does not support node "
                    f"{worker_name!r} of kind {by_name[worker_name].kind!r}"
                )
        workers = [build_step(worker_name) for worker_name in worker_names]
        return ParallelAgent(
            name=name or "parallel_agent",
            description=rt.description,
            sub_agents=workers,
        )

    # shape == "loop": the body node is the non-counter node; the counter
    # node carries options.max_iterations.
    counters = [
        n
        for n in spec.nodes
        if n.kind == "function" and n.options.get("kind") == "loop_counter"
    ]
    if len(counters) != 1:
        raise ValueError("legacy loop compile requires exactly one loop-counter node")
    counter_node = counters[0]
    body_names = [n.name for n in spec.nodes if n.name != counter_node.name]
    if len(body_names) != 1:
        raise ValueError("legacy loop compile requires exactly one body node")
    max_iterations = counter_node.options.get("max_iterations")
    if not isinstance(max_iterations, int) or max_iterations < 1:
        raise ValueError(
            f"loop counter node {counter_node.name!r} requires "
            "options.max_iterations >= 1"
        )
    worker = build_step(body_names[0])
    return LoopAgent(
        name=name or "loop_agent",
        description=rt.description,
        sub_agents=[worker],
        max_iterations=max_iterations,
    )
