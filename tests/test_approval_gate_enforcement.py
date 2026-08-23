"""R08/R09/R13 — approval-gate enforcement, fail-closed detection, dedupe.

- R09: ``require_approval`` drives a real gate-all approval veto wired by
  ``Preset.build`` (default for approval_gate, opt-in for other presets).
- R08: ``_TaskAgentTool`` detection fails CLOSED (gate-able + warning).
- R13: ``presets/catalog.py`` no longer re-defines the tree-walk/chain
  helpers; it imports them from ``policies/approval``.
"""

from __future__ import annotations

import logging
import sys
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_response import LlmResponse
from google.genai import types

from basic_agent.config import loader
from basic_agent.policies import (
    is_unconditional_tool,
    iter_llm_agents,
    make_approval_before_tool,
)
from basic_agent.presets.catalog import PRESETS
from basic_agent.runtime import RuntimeContext

BLOCKED = {
    "status": "blocked",
    "reason": "This action requires human approval before execution.",
}


class DeterministicLlm(BaseLlm):
    """A no-network model returning one plain response per turn."""

    calls: int = 0

    async def generate_content_async(self, llm_request, stream=False):
        self.calls += 1
        yield LlmResponse(
            content=types.Content(
                role="model",
                parts=[types.Part(text=f"deterministic response {self.calls}")],
            )
        )


def make_rt(**overrides) -> RuntimeContext:
    base = RuntimeContext(
        model=DeterministicLlm(model="deterministic"),
        instruction="Runtime policy: follow the operator's task.",
        tools=[],
        description="approval gate test agent",
        output_key="last_response",
    )
    return replace(base, **overrides)


GATED_TOOL = SimpleNamespace(name="publish_project", basic_agent_mutating=False)


def fake_ctx(state: dict | None = None):
    """Tool context recording every request_confirmation call."""
    records: list[dict] = []
    ctx = SimpleNamespace(
        state=dict(state or {}),
        request_confirmation=lambda **kwargs: records.append(kwargs),
    )
    return records, ctx


def first_llm_node(root) -> object:
    return next(iter_llm_agents(root))


# ─── R09 — require_approval drives a real gate ───────────────────────────────


def test_approval_gate_preset_gets_default_gate():
    """approval_gate's require_approval default yields an enforceable veto."""
    root = PRESETS["approval_gate"].build(make_rt())
    node = first_llm_node(root)
    assert node.before_tool_callback is not None

    records, ctx = fake_ctx()
    assert node.before_tool_callback(GATED_TOOL, {"action": "deploy"}, ctx) == BLOCKED
    assert records, "a confirmation must have been requested"
    assert records[0]["payload"]["tool"] == "publish_project"

    # Prior human approval lets the tool through.
    _, approved = fake_ctx({"human_approved": True})
    assert node.before_tool_callback(GATED_TOOL, {}, approved) is None

    # Invariants hold under gate_all: unconditional names are never blocked.
    for name in ("request_approval", "finish_task"):
        recorded, plain = fake_ctx()
        assert node.before_tool_callback(SimpleNamespace(name=name), {}, plain) is None
        assert recorded == []


def test_require_approval_opt_in_gates_other_presets():
    """execution.require_approval: true is what wires the gate — not the key."""
    gated_root = PRESETS["assistant"].build(make_rt(require_approval=True))
    node = first_llm_node(gated_root)
    records, ctx = fake_ctx()
    assert node.before_tool_callback(GATED_TOOL, {}, ctx) == BLOCKED
    assert records

    # Without the flag (assistant default) there is no gate at all.
    plain_root = PRESETS["assistant"].build(make_rt())
    assert first_llm_node(plain_root).before_tool_callback is None


# ─── R08 — fail-closed delegation detection ──────────────────────────────────


def test_unconditional_detection_fails_closed_with_warning(monkeypatch, caplog):
    """An unresolvable _TaskAgentTool import must not disable gating."""
    monkeypatch.setitem(sys.modules, "google.adk.tools.agent_tool", None)
    with caplog.at_level(logging.WARNING, logger="basic_agent.policies.approval"):
        assert is_unconditional_tool(SimpleNamespace(name="anything")) is False
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert warnings, "detection failure must be logged as a warning"
    assert "_TaskAgentTool" in warnings[0].getMessage()


def test_gate_all_still_blocks_when_detection_fails(monkeypatch):
    """End-to-end: a gate_all callback blocks even with the import broken."""
    monkeypatch.setitem(sys.modules, "google.adk.tools.agent_tool", None)
    callback = make_approval_before_tool(
        loader.ApprovalPolicyConfig(enabled=True, gate_all=True)
    )
    records, ctx = fake_ctx()
    assert callback(GATED_TOOL, {}, ctx) == BLOCKED
    assert records
    # The unconditional names still pass (name check needs no ADK import).
    _, plain = fake_ctx()
    assert callback(SimpleNamespace(name="request_approval"), {}, plain) is None


# ─── gate_all config surface ─────────────────────────────────────────────────


def test_gate_all_parses_from_yaml(tmp_path):
    path = tmp_path / "gate-all.yaml"
    path.write_text(
        """
agent:
  use_case: assistant
policies:
  approval:
    enabled: true
    gate_all: true
""",
        encoding="utf-8",
    )
    config = loader.load_config_from_yaml(str(path))
    assert config.policies is not None
    assert config.policies.approval is not None
    assert config.policies.approval.gate_all is True


def test_gate_all_defaults_false(tmp_path):
    path = tmp_path / "gate-all-default.yaml"
    path.write_text(
        """
agent:
  use_case: assistant
policies:
  approval:
    enabled: true
""",
        encoding="utf-8",
    )
    config = loader.load_config_from_yaml(str(path))
    assert config.policies.approval.gate_all is False


# ─── R13 — catalog dedupe ────────────────────────────────────────────────────


def test_catalog_no_longer_redefines_tree_helpers():
    """catalog.py must not re-implement the approval.py helpers (R13)."""
    source = (
        Path(__file__).parents[1] / "src" / "basic_agent" / "presets" / "catalog.py"
    ).read_text(encoding="utf-8")
    assert "def _iter_llm_agents" not in source
    assert "def _chain_before_tool" not in source

    # The name catalog exports is the shared function object itself.
    from basic_agent.policies.approval import _chain_before_tool as shared_chain
    from basic_agent.presets.catalog import _chain_before_tool as catalog_chain

    assert catalog_chain is shared_chain
