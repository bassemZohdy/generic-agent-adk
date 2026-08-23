"""R15 — sequence-item sugar forms must be mutually exclusive."""

from __future__ import annotations

import pytest

from basic_agent.config import loader


def test_sequence_item_with_both_parallel_and_loop_is_rejected(tmp_path):
    path = tmp_path / "both.yaml"
    path.write_text(
        """
agent:
  use_case: assistant
graph:
  nodes:
    - {name: a, kind: llm}
    - {name: b, kind: llm}
    - {name: c, kind: llm}
  sequence:
    - {parallel: [a, b], loop: {body: c, max_iterations: 2}}
""",
        encoding="utf-8",
    )
    with pytest.raises(
        ValueError,
        match="exactly one of 'parallel' or 'loop' may be set; got both",
    ):
        loader.load_config_from_yaml(str(path))


def test_sequence_item_with_only_parallel_still_parses(tmp_path):
    path = tmp_path / "parallel.yaml"
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
    assert config.graph is not None
    config.graph.validate()


def test_sequence_item_with_only_loop_still_parses(tmp_path):
    path = tmp_path / "loop.yaml"
    path.write_text(
        """
agent:
  use_case: assistant
graph:
  nodes:
    - {name: worker, kind: llm}
  sequence:
    - {loop: {body: worker, max_iterations: 3}}
""",
        encoding="utf-8",
    )
    config = loader.load_config_from_yaml(str(path))
    assert config.graph is not None
    config.graph.validate()
