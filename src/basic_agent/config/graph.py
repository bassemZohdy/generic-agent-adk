"""Graph-spec configuration model (ADR-005 decision §1; TODO Phase C1).

Framework-independent dataclasses describing the externalized graph
configuration: a recursive ``nodes`` + ``edges`` spec.  Sugar forms (C2)
expand into this spec *before* compilation; the compilers (C3) turn it into
the ADK Workflow graph.  This module imports **no** ``google.adk`` module —
the schema stays a pure data contract, while field names stay aligned with
the ``Workflow``/``BaseNode`` pydantic models so the compile step remains
thin (``retry`` mirrors ``RetryConfig``, ``timeout``/``input_schema``/
``output_schema``/``state_schema`` mirror ``BaseNode``, edges mirror the
``from_node``/``to_node``/``route`` triple, and ``START`` is the entry
sentinel source).
"""

from __future__ import annotations

import keyword
from dataclasses import dataclass, field
from typing import Any

from ..strategies.base import RoleConfig

#: Sentinel source name for the workflow entry point.  Matches the edge DSL
#: value used by the ADK graph parser (``START`` strings are resolved to the
#: framework's START node at compile time).
START = "START"

#: Route value meaning "fall through when no specific route matched" — the
#: value the ADK engine treats as the default edge route
#: (``google.adk.workflow.DEFAULT_ROUTE``).  Kept as data here so the spec
#: stays framework-independent while the compiler maps it 1:1.
DEFAULT_ROUTE = "__DEFAULT__"

#: Node kinds accepted by the spec (aligned with ADR-005 decision §1).
NODE_KINDS = ("llm", "function", "graph", "join")

_SCALAR_TYPES = (bool, int, str)


def _is_route_scalar(value: Any) -> bool:
    """Return whether a route value is a scalar (bool/int/str)."""
    return isinstance(value, _SCALAR_TYPES)


@dataclass
class RetrySpec:
    """Per-node retry policy (field-aligned with ADK ``RetryConfig``).

    ``None`` values fall back to the engine defaults at compile time.
    """

    max_attempts: int | None = None
    initial_delay: float | None = None
    max_delay: float | None = None
    backoff_factor: float | None = None
    jitter: float | None = None


@dataclass
class GraphEdgeSpec:
    """One graph edge.

    ``target`` accepts a single node name or a list (fan-out to several
    nodes).  ``source`` may be ``START`` or a node name.  ``route`` is a
    scalar (bool/int/str) matched against the routed ``Edge.route`` values.
    """

    source: str
    target: str | list[str]
    route: bool | int | str | None = None


@dataclass
class GraphNodeSpec:
    """One graph node.

    ``kind`` is one of ``llm`` | ``function`` | ``graph`` | ``join``; a
    ``graph`` node carries a nested ``graph`` spec.  ``role`` reuses
    ``RoleConfig`` (``instruction``/``model``/``tools`` names) so node-level
    overrides resolve identically to strategy-time role overrides.
    """

    name: str
    kind: str
    role: RoleConfig | None = None
    retry: RetrySpec | None = None
    timeout: float | None = None
    input_schema: str | None = None
    output_schema: str | None = None
    state_schema: str | None = None
    output_key: str | None = None
    options: dict[str, Any] = field(default_factory=dict)
    graph: GraphSpec | None = None


@dataclass
class GraphSpec:
    """The graph-spec configuration model (nodes + edges).

    ``shape`` is set by sugar expansion (C2) to ``"sequence"``/``"parallel"``/
    ``"loop"`` and left ``None`` for explicitly-edged specs; it is provenance
    for the legacy compiler (which covers the sugar subset only) and ignored
    by the workflow compiler.
    """

    shape: str | None = None
    nodes: list[GraphNodeSpec] = field(default_factory=list)
    edges: list[GraphEdgeSpec] = field(default_factory=list)

    def nodes_by_name(self) -> dict[str, GraphNodeSpec]:
        """Return nodes indexed by name (raises on duplicates)."""
        by_name: dict[str, GraphNodeSpec] = {}
        for node in self.nodes:
            if node.name in by_name:
                raise ValueError(f"Duplicate node name in graph: {node.name!r}")
            by_name[node.name] = node
        return by_name

    def validate(self) -> None:
        """Validate the graph spec, fail-fast with actionable messages.

        Raises:
            ValueError: On the first violation found.  Messages name the
                offending key/value and the valid alternatives.
        """
        by_name = self.nodes_by_name()

        # Node-level structural rules.
        for node in self.nodes:
            if node.kind not in NODE_KINDS:
                raise ValueError(
                    f"graph node {node.name!r} has unknown "
                    f"kind {node.kind!r}; valid kinds: {', '.join(NODE_KINDS)}"
                )
            if not node.name.isidentifier() or keyword.iskeyword(node.name):
                raise ValueError(
                    f"graph node name {node.name!r} must be a valid Python "
                    "identifier and not a Python keyword"
                )
            if node.kind == "graph" and node.graph is None:
                raise ValueError(
                    f"graph node {node.name!r} has kind 'graph' but no nested "
                    "'graph' spec"
                )
            if node.kind != "graph" and node.graph is not None:
                raise ValueError(
                    f"graph node {node.name!r} has a nested 'graph' spec but "
                    f"kind {node.kind!r}"
                )

        # Edge-level structural rules.
        node_names = set(by_name)
        joined_names = ", ".join(sorted(node_names)) or "(none)"
        has_start_edge = False
        inbound_counts: dict[str, int] = {}
        for edge in self.edges:
            if edge.source not in node_names and edge.source != START:
                raise ValueError(
                    f"graph edge to {edge.target!r} has unknown source "
                    f"{edge.source!r}; valid sources: START or {joined_names}"
                )
            if edge.source == START:
                has_start_edge = True
            targets = edge.target if isinstance(edge.target, list) else [edge.target]
            for target in targets:
                if target not in node_names:
                    raise ValueError(
                        f"graph edge from {edge.source!r} targets unknown node "
                        f"{target!r}; valid nodes: {joined_names}"
                    )
                inbound_counts[target] = inbound_counts.get(target, 0) + 1
            if not _is_route_scalar(edge.route) and edge.route is not None:
                raise ValueError(
                    f"graph edge from {edge.source!r} has non-scalar route "
                    f"{edge.route!r}; route values must be a string, integer, "
                    "or boolean"
                )

        if not has_start_edge:
            raise ValueError(
                "graph spec has no edge from START; at least one node must be "
                "reachable from START"
            )

        # Join nodes need at least two inbound edges.
        for node in self.nodes:
            if node.kind == "join" and inbound_counts.get(node.name, 0) < 2:
                raise ValueError(
                    f"join node {node.name!r} must have at least 2 inbound "
                    f"edges; got {inbound_counts.get(node.name, 0)}"
                )
