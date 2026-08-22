"""Phase C2 — sugar form expansion tests (exact structures)."""

from __future__ import annotations

import pytest

from basic_agent.config import loader
from basic_agent.config.graph import (
    DEFAULT_ROUTE,
    START,
    GraphEdgeSpec,
    GraphNodeSpec,
)
from basic_agent.config.sugar import (
    AGAIN_ROUTE,
    LoopSugar,
    ParallelSugar,
    SequenceSugar,
    expand_loop,
    expand_parallel,
    expand_sequence,
    expand_sugar,
)


def node(name: str, kind: str = "llm") -> GraphNodeSpec:
    return GraphNodeSpec(name=name, kind=kind)


def test_expand_sequence_exact_structure():
    by_name = {"a": node("a"), "b": node("b"), "c": node("c")}
    fragment = expand_sequence(SequenceSugar(items=["a", "b", "c"]), by_name)

    assert fragment.entry == "a"
    assert fragment.exit == "c"
    assert fragment.nodes == []
    assert fragment.edges == [
        GraphEdgeSpec(source=START, target="a"),
        GraphEdgeSpec(source="a", target="b"),
        GraphEdgeSpec(source="b", target="c"),
    ]


def test_expand_parallel_exact_structure_includes_implicit_join():
    by_name = {"p1": node("p1"), "p2": node("p2")}
    fragment = expand_parallel(ParallelSugar(items=["p1", "p2"]), by_name)

    assert fragment.nodes == [GraphNodeSpec(name="p1_join", kind="join")]
    assert fragment.entry == "p1"
    assert fragment.exit == "p1_join"
    assert fragment.edges == [
        GraphEdgeSpec(source=START, target=["p1", "p2"]),
        GraphEdgeSpec(source="p1", target="p1_join"),
        GraphEdgeSpec(source="p2", target="p1_join"),
    ]


def test_expand_parallel_custom_join_name():
    by_name = {"p1": node("p1"), "p2": node("p2")}
    fragment = expand_parallel(
        ParallelSugar(items=["p1", "p2"], join_name="collect"), by_name
    )
    assert fragment.exit == "collect"
    assert fragment.edges[1].target == "collect"


def test_expand_loop_exact_structure_bounded_by_routing():
    by_name = {"worker": node("worker")}
    fragment = expand_loop(
        LoopSugar(body="worker", max_iterations=5),
        by_name,
        exit="final",
    )

    counter = GraphNodeSpec(
        name="worker_loop_counter",
        kind="function",
        options={"max_iterations": 5},
    )
    assert fragment.nodes == [counter]
    assert fragment.entry == "worker"
    assert fragment.exit == "worker_loop_counter"
    assert fragment.edges == [
        GraphEdgeSpec(source=START, target="worker"),
        GraphEdgeSpec(source="worker", target="worker_loop_counter"),
        GraphEdgeSpec(source="worker_loop_counter", target="worker", route=AGAIN_ROUTE),
        GraphEdgeSpec(
            source="worker_loop_counter", target="final", route=DEFAULT_ROUTE
        ),
    ]


def test_expand_sugar_loop_without_exit_is_terminal():
    by_name = {"worker": node("worker")}
    spec = expand_sugar(LoopSugar(body="worker", max_iterations=3), by_name)

    assert spec.validate() is None
    assert [n.name for n in spec.nodes] == ["worker", "worker_loop_counter"]
    assert spec.edges[0].source == START
    # Only the routing edges exist; the counter is the terminal (routed) node.
    assert spec.edges[-1].route == AGAIN_ROUTE


def test_expand_sequence_with_nested_parallel_becomes_subgraph_node():
    by_name = {
        "pre": node("pre"),
        "p1": node("p1"),
        "p2": node("p2"),
        "post": node("post"),
    }
    sugar = SequenceSugar(items=["pre", ParallelSugar(items=["p1", "p2"]), "post"])
    spec = expand_sugar(sugar, by_name)

    subgraph_nodes = [n for n in spec.nodes if n.kind == "graph"]
    assert len(subgraph_nodes) == 1
    sub = subgraph_nodes[0]
    assert sub.name == "sub_1"
    assert sub.graph is not None
    assert [n.name for n in sub.graph.nodes] == ["p1", "p2", "p1_join"]
    assert sub.graph.edges[0] == GraphEdgeSpec(source=START, target=["p1", "p2"])
    # Outer sequence edges run through the subgraph node.
    names = {e.source: str(e.target) for e in spec.edges}
    assert names["pre"] == "sub_1"
    assert names["sub_1"] == "post"
    # The whole spec validates (START reachable, join rule holds inside).
    spec.validate()


def test_sugar_validation_errors():
    with pytest.raises(ValueError, match="at least one item"):
        SequenceSugar(items=[])
    with pytest.raises(ValueError, match="at least two items"):
        ParallelSugar(items=["a"])
    with pytest.raises(ValueError, match="max_iterations must be >= 1"):
        LoopSugar(body="w", max_iterations=0)
    with pytest.raises(ValueError, match="unknown node 'ghost'"):
        expand_sugar(SequenceSugar(items=["ghost"]), {})


# ─── YAML sugar surface (loader branch) ─────────────────────────────────────


SUGAR_YAML = """
agent:
  use_case: assistant
graph:
  nodes:
    - {name: step_1, kind: llm}
    - {name: step_2, kind: llm}
    - {name: refine, kind: llm}
  sequence: [step_1, step_2]
"""


def test_loader_parses_sequence_sugar(tmp_path):
    path = tmp_path / "sugar.yaml"
    path.write_text(SUGAR_YAML, encoding="utf-8")
    config = loader.load_config_from_yaml(str(path))
    assert config.graph is not None
    assert config.graph.edges == [
        GraphEdgeSpec(source=START, target="step_1"),
        GraphEdgeSpec(source="step_1", target="step_2"),
    ]
    # step_2 is not terminal yet only because refs remain reachable; validate
    # passes as long as START reaches a node.
    config.graph.validate()


def test_loader_parses_loop_sugar(tmp_path):
    path = tmp_path / "loop.yaml"
    path.write_text(
        """
agent:
  use_case: assistant
graph:
  nodes:
    - {name: worker, kind: llm}
  loop: {body: worker, max_iterations: 5}
""",
        encoding="utf-8",
    )
    config = loader.load_config_from_yaml(str(path))
    spec = config.graph
    assert spec is not None
    counter = spec.nodes_by_name()["worker_loop_counter"]
    assert counter.kind == "function"
    assert counter.options == {"max_iterations": 5}
    assert spec.edges[-1].route == AGAIN_ROUTE


def test_loader_parses_nested_parallel_in_sequence(tmp_path):
    path = tmp_path / "nested.yaml"
    path.write_text(
        """
agent:
  use_case: assistant
graph:
  nodes:
    - {name: pre, kind: llm}
    - {name: p1, kind: llm}
    - {name: p2, kind: llm}
  sequence: [pre, {parallel: [p1, p2]}]
""",
        encoding="utf-8",
    )
    config = loader.load_config_from_yaml(str(path))
    spec = config.graph
    assert spec is not None
    sub = spec.nodes_by_name()["sub_1"]
    assert sub.kind == "graph"
    assert sorted(n.name for n in sub.graph.nodes) == ["p1", "p1_join", "p2"]


def test_loader_sugar_requires_exactly_one_form():
    with pytest.raises(
        ValueError, match="exactly one of 'sequence', 'parallel', 'loop'"
    ):
        loader._parse_graph_spec(
            {
                "nodes": [{"name": "a", "kind": "llm"}],
                "sequence": ["a"],
                "parallel": ["a", "a"],
            }
        )
    # No sugar form and no plain edges is still a validation failure.
    with pytest.raises(ValueError, match="no edge from START"):
        loader._parse_graph_spec({"nodes": [{"name": "a", "kind": "llm"}]})


def test_loader_sugar_rejects_combined_edges():
    with pytest.raises(ValueError, match="cannot be combined with explicit 'edges'"):
        loader._parse_graph_spec(
            {
                "nodes": [
                    {"name": "a", "kind": "llm"},
                    {"name": "b", "kind": "llm"},
                ],
                "sequence": ["a", "b"],
                "edges": [{"from": "a", "to": "b"}],
            }
        )


def test_loader_sugar_rejects_unknown_node_reference():
    with pytest.raises(ValueError, match="unknown node 'ghost'"):
        loader._parse_graph_spec(
            {
                "nodes": [{"name": "a", "kind": "llm"}],
                "sequence": ["a", "ghost"],
            }
        )


def test_empty_graph_sections_still_rejected():
    with pytest.raises(ValueError, match="graph: graph spec has no edge from START"):
        loader._parse_graph_spec({"nodes": [], "edges": []})


def test_expand_loop_sugar_requires_existing_node():
    with pytest.raises(ValueError, match="unknown node"):
        loader._parse_graph_spec(
            {
                "nodes": [{"name": "a", "kind": "llm"}],
                "loop": {"body": "ghost", "max_iterations": 3},
            }
        )
