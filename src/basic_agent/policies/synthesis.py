"""Synthesis policy — cross-cutting, topology-independent (ADR-005 §4; TODO D2).

Replaces ``use_cases/multi_perspective.py``'s hand-rolled ``compose()``
override and ``after_run`` state scraping: a declarative synthesizer node is
appended after a fan-out (workflow: after the ``JoinNode``; legacy: as a
trailing sequential step of the nested-parallel sugar shape), and an
``after_run``-style callback aggregates the ``perspective_*`` state keys
into ``aggregated_perspectives`` — the exact state keys and instruction of
today's multi_perspective use case.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from ..config.graph import GraphEdgeSpec, GraphNodeSpec, GraphSpec
from ..config.sugar import ParallelSugar, SequenceSugar, expand_sugar
from ..runtime import RoleConfig

logger = logging.getLogger(__name__)

#: Synthesizer instruction — identical to the multi_perspective use case's
#: role instruction (C4 parity relies on text equality).
SYNTHESIZER_INSTRUCTION = (
    "Read the perspective outputs in session state, compare where they agree "
    "or differ, and produce one balanced final answer."
)
SYNTHESIZER_NAME = "perspective_synthesizer"
SYNTHESIZER_OUTPUT_KEY = "last_response"
SYNTHESIZER_STATE_KEY = "aggregated_perspectives"


def synthesizer_node(
    instruction: str = SYNTHESIZER_INSTRUCTION,
    *,
    name: str = SYNTHESIZER_NAME,
    output_key: str = SYNTHESIZER_OUTPUT_KEY,
) -> GraphNodeSpec:
    """Build the canonical synthesizer node (llm kind, same role contract)."""
    return GraphNodeSpec(
        name=name,
        kind="llm",
        role=RoleConfig(instruction=instruction),
        output_key=output_key,
    )


def _outgoing(spec: GraphSpec) -> dict[str, list[str]]:
    indexed: dict[str, list[str]] = {}
    for edge in spec.edges:
        targets = edge.target if isinstance(edge.target, list) else [edge.target]
        for target in targets:
            indexed.setdefault(edge.source, []).append(target)
    return indexed


def with_synthesis(
    spec: GraphSpec,
    synthesizer: GraphNodeSpec | None = None,
    *,
    join_name: str = "synthesis_join",
    aggregator_name: str = "synthesis_aggregate",
    with_aggregator: bool = True,
) -> GraphSpec:
    """Append a synthesizer node after a fan-out graph (workflow shape).

    Pure spec transformation: when the graph has a single terminal (e.g. the
    parallel sugar's join), the synthesizer follows it directly; a raw
    fan-out with several terminals first gets an implicit join.  By default
    an aggregation ``function`` node (``options.function:
    aggregate_perspectives`` — built-in registry entry) follows the
    synthesizer so ``perspective_*`` → ``aggregated_perspectives`` happens
    natively inside the graph (no after-run callback on the workflow
    backend).
    """
    synth = synthesizer or synthesizer_node()
    outgoing = _outgoing(spec)
    terminals = [node.name for node in spec.nodes if not outgoing.get(node.name)]
    new_nodes = list(spec.nodes) + [synth]
    new_edges = list(spec.edges)

    if len(terminals) == 1:
        new_edges.append(GraphEdgeSpec(source=terminals[0], target=synth.name))
    else:
        join = GraphNodeSpec(name=join_name, kind="join")
        new_nodes.append(join)
        for terminal in terminals:
            new_edges.append(GraphEdgeSpec(source=terminal, target=join.name))
        new_edges.append(GraphEdgeSpec(source=join.name, target=synth.name))

    if with_aggregator:
        aggregator = GraphNodeSpec(
            name=aggregator_name,
            kind="function",
            options={"function": "aggregate_perspectives"},
        )
        new_nodes.append(aggregator)
        new_edges.append(GraphEdgeSpec(source=synth.name, target=aggregator.name))

    combined = GraphSpec(nodes=new_nodes, edges=new_edges, shape=spec.shape)
    combined.validate()
    return combined


def legacy_multi_perspective_spec(
    worker_names: list[str],
    synthesizer: GraphNodeSpec | None = None,
    *,
    nested_name: str = "parallel_agent",
    join_name: str | None = None,
) -> GraphSpec:
    """Build the legacy shape: nested parallel sugar + trailing synthesizer.

    Equivalent to the spec the C4 parity test hand-built: a sequence whose
    first item is a named nested parallel (so the legacy compiler emits
    ``ParallelAgent`` under the same name) followed by the synthesizer.
    """
    synth = synthesizer or synthesizer_node()
    workers = [
        GraphNodeSpec(name=name, kind="llm", output_key=f"perspective_{index}")
        for index, name in enumerate(worker_names)
    ]
    sugar = SequenceSugar(
        items=[
            ParallelSugar(items=worker_names, name=nested_name, join_name=join_name),
            synth.name,
        ]
    )
    by_name = {worker.name: worker for worker in workers}
    by_name[synth.name] = synth
    return expand_sugar(sugar, by_name)


def make_synthesis_after_run() -> Callable[..., Any]:
    """Return the after-run aggregation callback (multi_perspective logic)."""

    def after_run(callback_context: Any) -> None:
        """Collect ``perspective_*`` state entries into an aggregated list."""
        try:
            state = callback_context.state
            keys = sorted(
                (key for key in state if key.startswith("perspective_")),
                key=lambda key: (
                    int(key.split("_", 1)[1])
                    if key.split("_", 1)[1].isdigit()
                    else 2**63
                ),
            )
            values = [state[key] for key in keys]
            state[SYNTHESIZER_STATE_KEY] = values
        except Exception:
            logger.debug("Unable to aggregate multi-perspective state", exc_info=True)

    return after_run
