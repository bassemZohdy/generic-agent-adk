"""Sugar forms for the graph spec (ADR-005 decision §2; TODO Phase C2).

Pure, deterministic expansion of the three shorthand forms into the C1
``GraphSpec`` before compilation — no ADK imports, no I/O.  The expanded
specs are what ``compile/`` (C3) consumes, so every sugar shape is testable
in isolation and C4's parity mapping can pin the exact produced node names.

Naming (deterministic, documented for C4):

- ``sequence`` keeps the supplied node names; the fragment entry is the
  first item and the exit the last.
- ``parallel`` implicitly adds a ``join`` node named ``<first item>_join``
  (or the explicit ``join_name``).
- ``loop`` adds a ``function``-kind counter node named ``<body>_loop_counter``
  (or the explicit ``counter_name``) carrying
  ``options={"max_iterations": N}``; the counter emits ``"again"`` while the
  iteration budget lasts and falls through on the unmatched/default route.
- Nested sugars (a ``parallel``/``loop`` inside a ``sequence``) become a
  ``graph``-kind node named ``sub_<index>`` wrapping the expanded nested spec.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .graph import DEFAULT_ROUTE, START, GraphEdgeSpec, GraphNodeSpec, GraphSpec

#: Route value emitted by loop counters while the iteration budget lasts.
AGAIN_ROUTE = "again"

_SUBGRAPH_PREFIX = "sub_"


@dataclass
class SugarFragment:
    """One expanded sugar shape: added nodes + internal edges.

    ``entry`` is the node that must be triggered first (fragment start) and
    ``exit`` is the node whose completion out-edges the fragment; callers
    wire predecessor→``entry`` and ``exit``→successor.
    """

    nodes: list[GraphNodeSpec]
    edges: list[GraphEdgeSpec]
    entry: str
    exit: str


@dataclass
class SequenceSugar:
    """``sequence: [n1, n2, ...]`` — items are node names or nested sugars."""

    items: list[str | ParallelSugar | LoopSugar]

    def __post_init__(self) -> None:
        if not self.items:
            raise ValueError("sequence sugar must have at least one item")


@dataclass
class ParallelSugar:
    """``parallel: [n1, n2]`` — fan-out plus an implicit join."""

    items: list[str]
    join_name: str | None = None

    def __post_init__(self) -> None:
        if len(self.items) < 2:
            raise ValueError("parallel sugar must have at least two items")


@dataclass
class LoopSugar:
    """``loop: {body: n, max_iterations: N}`` — bounded via routing."""

    body: str
    max_iterations: int

    def __post_init__(self) -> None:
        if self.max_iterations < 1:
            raise ValueError(
                f"loop sugar max_iterations must be >= 1; got {self.max_iterations}"
            )


def _check_name_exists(name: str, by_name: dict[str, GraphNodeSpec]) -> None:
    if name not in by_name:
        raise ValueError(
            f"sugar references unknown node {name!r}; valid nodes: "
            + ", ".join(sorted(by_name))
            or "(none)"
        )


def _sugar_referenced_names(sugar: Any) -> list[str]:
    """Return the node names a sugar form references (recursively)."""
    if isinstance(sugar, SequenceSugar):
        names: list[str] = []
        for item in sugar.items:
            if isinstance(item, str):
                names.append(item)
            else:
                names.extend(_sugar_referenced_names(item))
        return names
    if isinstance(sugar, ParallelSugar):
        return list(sugar.items)
    return [sugar.body]


def _resolve_item(
    item: str | ParallelSugar | LoopSugar,
    index: int,
    by_name: dict[str, GraphNodeSpec],
    *,
    subgraph_name: str | None = None,
) -> GraphNodeSpec:
    """Resolve a sequence item to a node spec (nested sugars become subgraphs)."""
    if isinstance(item, str):
        _check_name_exists(item, by_name)
        return by_name[item]
    name = subgraph_name or f"{_SUBGRAPH_PREFIX}{index}"
    # Nested specs reference only their own nodes: scope the registry down so
    # the subgraph does not inherit the whole outer graph.
    nested_by_name = {
        ref: by_name[ref] for ref in _sugar_referenced_names(item) if ref in by_name
    }
    nested = expand_sugar(item, nested_by_name)
    nested.validate()
    return GraphNodeSpec(name=name, kind="graph", graph=nested)


def expand_sequence(
    sugar: SequenceSugar,
    by_name: dict[str, GraphNodeSpec] | None = None,
    *,
    entry: str = START,
) -> SugarFragment:
    """Expand ``sequence`` — straight chain from ``entry`` to the last item."""
    by_name = by_name or {}
    resolved = [
        _resolve_item(item, index, by_name) for index, item in enumerate(sugar.items)
    ]
    names = [node.name for node in resolved]
    nodes = [node for node in resolved if node.name not in by_name]
    edges = [
        GraphEdgeSpec(source=source, target=target)
        for source, target in zip([entry, *names[:-1]], names)
    ]
    return SugarFragment(
        nodes=nodes,
        edges=edges,
        entry=names[0],
        exit=names[-1],
    )


def expand_parallel(
    sugar: ParallelSugar,
    by_name: dict[str, GraphNodeSpec] | None = None,
    *,
    entry: str = START,
) -> SugarFragment:
    """Expand ``parallel`` — fan-out from ``entry`` plus an implicit join."""
    by_name = by_name or {}
    for name in sugar.items:
        _check_name_exists(name, by_name)
    join_name = sugar.join_name or f"{sugar.items[0]}_join"
    join_node = GraphNodeSpec(name=join_name, kind="join")
    edges = [GraphEdgeSpec(source=entry, target=list(sugar.items))]
    edges.extend(GraphEdgeSpec(source=name, target=join_name) for name in sugar.items)
    return SugarFragment(
        nodes=[join_node],
        edges=edges,
        entry=sugar.items[0],
        exit=join_name,
    )


def expand_loop(
    sugar: LoopSugar,
    by_name: dict[str, GraphNodeSpec] | None = None,
    *,
    entry: str = START,
    exit: str | None = None,
) -> SugarFragment:
    """Expand ``loop`` — body → counter, routed back while budget remains.

    The counter node is a ``function``-kind node carrying
    ``options={"max_iterations": N}``; its compiled implementation increments
    a state counter and emits ``"again"`` until the budget runs out, then
    falls through to the default route (``exit`` when provided).
    """
    by_name = by_name or {}
    _check_name_exists(sugar.body, by_name)
    body = sugar.body
    counter_name = f"{body}_loop_counter"
    counter = GraphNodeSpec(
        name=counter_name,
        kind="function",
        options={"max_iterations": sugar.max_iterations},
    )
    edges = [
        GraphEdgeSpec(source=entry, target=body),
        GraphEdgeSpec(source=body, target=counter_name),
        GraphEdgeSpec(source=counter_name, target=body, route=AGAIN_ROUTE),
    ]
    if exit is not None:
        # The exit target is wired by the caller (a forward reference); the
        # containing GraphSpec validates that the node actually exists.
        edges.append(
            GraphEdgeSpec(source=counter_name, target=exit, route=DEFAULT_ROUTE)
        )
    return SugarFragment(
        nodes=[counter],
        edges=edges,
        entry=body,
        exit=counter_name,
    )


def expand_sugar(
    sugar: SequenceSugar | ParallelSugar | LoopSugar,
    by_name: dict[str, GraphNodeSpec] | None = None,
    *,
    entry: str = START,
    exit: str | None = None,
) -> GraphSpec:
    """Expand any sugar form into a complete ``GraphSpec``.

    ``by_name`` holds the named node specs referenced by the sugar.  A
    standalone loop gets its ``exit`` wired when provided; otherwise the
    counter is the (routed, terminal) exit.
    """
    by_name = by_name or {}
    if isinstance(sugar, SequenceSugar):
        fragment = expand_sequence(sugar, by_name, entry=entry)
    elif isinstance(sugar, ParallelSugar):
        fragment = expand_parallel(sugar, by_name, entry=entry)
    elif isinstance(sugar, LoopSugar):
        fragment = expand_loop(sugar, by_name, entry=entry, exit=exit)
    else:  # pragma: no cover - defensive; sugar is a closed union of the above
        raise ValueError(  # noqa: TRY004 - preserve actionable config error type
            f"Unknown sugar form: {type(sugar).__name__}"
        )
    return GraphSpec(
        nodes=list(by_name.values()) + fragment.nodes, edges=fragment.edges
    )
