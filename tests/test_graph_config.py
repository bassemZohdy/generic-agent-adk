"""Phase C1 — graph-spec config model parse + validation tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from basic_agent.config import loader
from basic_agent.config.graph import (
    START,
    GraphEdgeSpec,
    GraphNodeSpec,
    GraphSpec,
    RetrySpec,
)

VALID_YAML = """
agent:
  use_case: assistant
model:
  provider: google
  name: gemini-2.0-flash
graph:
  nodes:
    - name: step_1
      kind: llm
      role:
        instruction: Do step one.
        model: gemini-2.0-flash
        tools: ["web_search"]
      retry:
        max_attempts: 4
        initial_delay: 0.5
      timeout: 30
      output_schema: GenericAgentResponse
      output_key: step1
    - name: step_2
      kind: llm
      input_schema: UserData
      state_schema: AgentState
    - name: aggregate
      kind: join
    - name: nested
      kind: graph
      graph:
        nodes:
          - name: inner
            kind: llm
        edges:
          - from: START
            to: inner
  edges:
    - from: START
      to: [step_1, step_2]
    - from: step_1
      to: aggregate
    - from: step_2
      to: aggregate
      route: done
    - from: aggregate
      to: nested
"""


def test_graph_config_parses_from_yaml(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(VALID_YAML, encoding="utf-8")
    config = loader.load_config_from_yaml(str(path))

    assert config.graph is not None
    spec = config.graph
    assert [node.name for node in spec.nodes] == [
        "step_1",
        "step_2",
        "aggregate",
        "nested",
    ]
    step_1 = spec.nodes[0]
    assert step_1.kind == "llm"
    assert step_1.role is not None
    assert step_1.role.instruction == "Do step one."
    assert step_1.role.model == "gemini-2.0-flash"
    assert step_1.role.tools == ["web_search"]
    assert step_1.retry == RetrySpec(max_attempts=4, initial_delay=0.5)
    assert step_1.timeout == 30.0
    assert step_1.output_schema == "GenericAgentResponse"
    assert step_1.output_key == "step1"
    assert spec.nodes[2].kind == "join"
    nested = spec.nodes[3]
    assert nested.kind == "graph"
    assert nested.graph is not None
    assert nested.graph.nodes[0].name == "inner"
    # Edge with fan-out target and route.
    assert spec.edges[0] == GraphEdgeSpec(source=START, target=["step_1", "step_2"])
    assert spec.edges[1].route is None
    assert spec.edges[2].route == "done"
    # Nested specs are validated at parse time too.
    with pytest.raises(ValueError, match="graph: graph spec has no edge from START"):
        loader._parse_graph_spec(
            {
                "nodes": [{"name": "x", "kind": "llm"}],
                "edges": [{"from": "x", "to": "x"}],
            }
        )


def test_graph_without_section_is_absent():
    raw = {"agent": {"use_case": "assistant"}}
    config = loader._parse_agent_config(raw)
    assert config.graph is None


def test_graph_empty_sections_are_rejected():
    with pytest.raises(ValueError, match="no edge from START"):
        loader._parse_graph_spec({"nodes": [], "edges": []})


@pytest.mark.parametrize(
    ("spec", "match"),
    [
        (
            # duplicate node names
            {
                "nodes": [
                    {"name": "a", "kind": "llm"},
                    {"name": "a", "kind": "llm"},
                ],
                "edges": [{"from": "START", "to": "a"}],
            },
            "Duplicate node name",
        ),
        (
            # unknown kind
            {
                "nodes": [{"name": "a", "kind": "widget"}],
                "edges": [{"from": "START", "to": "a"}],
            },
            "valid kinds: llm, function, graph, join",
        ),
        (
            # invalid identifier
            {
                "nodes": [{"name": "not-valid name", "kind": "llm"}],
                "edges": [{"from": "START", "to": "not-valid name"}],
            },
            "must be a valid Python identifier",
        ),
        (
            # python keyword name
            {
                "nodes": [{"name": "class", "kind": "llm"}],
                "edges": [{"from": "START", "to": "class"}],
            },
            "must be a valid Python identifier",
        ),
        (
            # unknown edge source
            {
                "nodes": [{"name": "a", "kind": "llm"}],
                "edges": [{"from": "ghost", "to": "a"}],
            },
            "unknown source 'ghost'",
        ),
        (
            # unknown edge target
            {
                "nodes": [{"name": "a", "kind": "llm"}],
                "edges": [{"from": "START", "to": "ghost"}],
            },
            "targets unknown node 'ghost'",
        ),
        (
            # no START edge
            {
                "nodes": [{"name": "a", "kind": "llm"}],
                "edges": [{"from": "a", "to": "a"}],
            },
            "no edge from START",
        ),
        (
            # join with fewer than 2 inbound edges
            {
                "nodes": [
                    {"name": "a", "kind": "llm"},
                    {"name": "j", "kind": "join"},
                ],
                "edges": [{"from": "START", "to": "a"}, {"from": "a", "to": "j"}],
            },
            "join node 'j' must have at least 2 inbound edges",
        ),
        (
            # non-scalar route
            {
                "nodes": [
                    {"name": "a", "kind": "llm"},
                    {"name": "b", "kind": "llm"},
                ],
                "edges": [
                    {"from": "START", "to": "a"},
                    {"from": "a", "to": "b", "route": ["x"]},
                ],
            },
            "non-scalar route",
        ),
        (
            # graph node without nested spec
            {
                "nodes": [{"name": "a", "kind": "graph"}],
                "edges": [{"from": "START", "to": "a"}],
            },
            "kind 'graph' but no nested 'graph' spec",
        ),
        (
            # non-graph node with nested spec
            {
                "nodes": [
                    {
                        "name": "a",
                        "kind": "llm",
                        "graph": {
                            "nodes": [{"name": "inner", "kind": "llm"}],
                            "edges": [{"from": "START", "to": "inner"}],
                        },
                    }
                ],
                "edges": [{"from": "START", "to": "a"}],
            },
            "has a nested 'graph' spec but kind 'llm'",
        ),
    ],
)
def test_graph_validation_rules_fail_loudly(spec, match):
    with pytest.raises(ValueError, match=match):
        loader._parse_graph_spec(spec)


def test_graph_unknown_yaml_keys_are_rejected():
    with pytest.raises(ValueError, match=r"Unknown graph\.nodes\[0\] field"):
        loader._parse_graph_spec(
            {
                "nodes": [{"name": "a", "kind": "llm", "surprise": 1}],
                "edges": [{"from": "START", "to": "a"}],
            }
        )
    with pytest.raises(ValueError, match=r"Unknown graph\.edges\[0\] field"):
        loader._parse_graph_spec(
            {
                "nodes": [{"name": "a", "kind": "llm"}],
                "edges": [{"from": "START", "to": "a", "invented": True}],
            }
        )


def test_graph_parameter_types_are_validated():
    with pytest.raises(ValueError, match=r"timeout must be a positive number"):
        loader._parse_graph_spec(
            {
                "nodes": [{"name": "a", "kind": "llm", "timeout": 0}],
                "edges": [{"from": "START", "to": "a"}],
            }
        )
    with pytest.raises(ValueError, match=r"retry.max_attempts must be an integer"):
        loader._parse_graph_spec(
            {
                "nodes": [{"name": "a", "kind": "llm", "retry": {"max_attempts": 0}}],
                "edges": [{"from": "START", "to": "a"}],
            }
        )
    with pytest.raises(ValueError, match=r"to must not be an empty list"):
        loader._parse_graph_spec(
            {
                "nodes": [{"name": "a", "kind": "llm"}],
                "edges": [{"from": "START", "to": []}],
            }
        )


def test_graph_module_is_framework_independent():
    """config/graph.py must not import any google.adk module (AST check)."""
    import ast

    graph_file = Path(loader.__file__).parent / "graph.py"
    tree = ast.parse(graph_file.read_text(encoding="utf-8"))
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.append(node.module)
    assert not any(name.startswith("google.adk") for name in imports), imports
    assert GraphSpec.__module__ == "basic_agent.config.graph"
    assert GraphNodeSpec.__module__ == "basic_agent.config.graph"
    assert GraphEdgeSpec.__module__ == "basic_agent.config.graph"
    assert RetrySpec.__module__ == "basic_agent.config.graph"
