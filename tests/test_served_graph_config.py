"""R06 — the declarative graph/policies config surface is load-bearing.

Every test here goes through ``agent._build_root_agent`` (the served
entrypoint), NOT ``compile_graph`` or ``Preset.build`` directly: a YAML
``graph:`` block must change the served root, ``policies:`` must attach to
it, and the preset path must remain the fallback when no graph is
configured.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from google.adk.agents import LlmAgent
from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_response import LlmResponse
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.workflow import Workflow
from google.genai import types

from basic_agent import agent as agent_module
from basic_agent.agent import resolve_agent_config

USER_ID = "r06-user"

GRAPH_CHAIN_YAML = """
agent:
  use_case: assistant
  name: custom-graph-root
model:
  provider: google
  name: gemini-3.6-flash
tools:
  enabled: []
graph:
  nodes:
    - name: intake
      kind: llm
      role:
        instruction: Summarize the request.
      output_key: request_summary
      options:
        no_state_schema: true
    - name: finalize
      kind: llm
      role:
        instruction: Produce the final answer.
  edges:
    - from: START
      to: intake
    - from: intake
      to: finalize
"""

GRAPH_FANOUT_SYNTHESIS_YAML = """
agent:
  use_case: assistant
model:
  provider: google
  name: gemini-3.6-flash
tools:
  enabled: []
graph:
  nodes:
    - name: left
      kind: llm
      output_key: perspective_0
      options:
        no_state_schema: true
    - name: right
      kind: llm
      output_key: perspective_1
      options:
        no_state_schema: true
  edges:
    - from: START
      to: [left, right]
policies:
  synthesis:
    enabled: true
    instruction: Aggregate the takes.
"""

GRAPH_APPROVAL_YAML = """
agent:
  use_case: assistant
model:
  provider: google
  name: gemini-3.6-flash
tools:
  enabled: []
graph:
  nodes:
    - name: only_node
      kind: llm
  edges:
    - from: START
      to: only_node
policies:
  approval:
    enabled: true
    gated_tools: [publish]
"""

PRESET_FALLBACK_YAML = """
agent:
  use_case: assistant
model:
  provider: google
  name: gemini-3.6-flash
tools:
  enabled: []
"""

PRESET_APPROVAL_YAML = """
agent:
  use_case: assistant
model:
  provider: google
  name: gemini-3.6-flash
tools:
  enabled: []
policies:
  approval:
    enabled: true
    gated_tools: [publish]
"""


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


@pytest.fixture
def fake_model(monkeypatch):
    model = DeterministicLlm(model="deterministic")
    monkeypatch.setattr(agent_module, "resolve_model", lambda *args, **kwargs: model)
    return model


def test_graph_config_compiles_to_the_served_root(tmp_path, monkeypatch, write_config):
    """A YAML graph: block replaces the preset root entirely."""
    write_config(GRAPH_CHAIN_YAML)

    config = resolve_agent_config()
    root = agent_module._build_root_agent(config, "yaml")

    assert isinstance(root, Workflow)
    names = {n.name for n in root.graph.nodes if hasattr(n, "name")}
    assert {"intake", "finalize"} <= names
    assert "direct_agent" not in names, "assistant preset must NOT build"
    assert root.name == "custom-graph-root"
    # The snapshot tells the truth: a custom graph is served, not a preset.
    assert agent_module._resolved_runtime_snapshot["use_case"] == "graph"


def test_served_graph_root_runs_end_to_end(
    tmp_path, monkeypatch, fake_model, write_config
):
    """The graph-config root is runnable, not just structurally present."""

    async def _run():
        session_service = InMemorySessionService()
        await session_service.create_session(
            app_name="r06-tests", user_id=USER_ID, session_id="s1"
        )
        runner = Runner(
            app_name="r06-tests",
            node=agent_module._build_root_agent(config, "yaml"),
            session_service=session_service,
        )
        return [
            event
            async for event in runner.run_async(
                user_id=USER_ID,
                session_id="s1",
                new_message=types.Content(
                    role="user", parts=[types.Part(text="Do the thing.")]
                ),
            )
        ]

    write_config(GRAPH_CHAIN_YAML)
    config = resolve_agent_config()

    events = asyncio.run(_run())
    authors = {e.author for e in events}
    state = {}
    for event in events:
        if event.actions and event.actions.state_delta:
            state.update(event.actions.state_delta)

    assert {"intake", "finalize"} <= authors, "custom graph nodes must execute"
    assert state["request_summary"] == "deterministic response 1"
    assert state["last_response"] == "deterministic response 2"


def test_synthesis_policy_appends_synthesizer_to_served_root(
    tmp_path, monkeypatch, write_config
):
    """policies.synthesis transforms the configured graph spec pre-compile."""
    write_config(GRAPH_FANOUT_SYNTHESIS_YAML)

    config = resolve_agent_config()
    root = agent_module._build_root_agent(config, "yaml")

    assert isinstance(root, Workflow)
    names = {n.name for n in root.graph.nodes if hasattr(n, "name")}
    assert {
        "synthesis_join",
        "perspective_synthesizer",
        "synthesis_aggregate",
    } <= names
    synth = next(
        n
        for n in root.graph.nodes
        if isinstance(n, LlmAgent) and n.name == "perspective_synthesizer"
    )
    assert "Aggregate the takes." in synth.instruction


def test_approval_policy_wires_veto_onto_served_graph_root(
    tmp_path, monkeypatch, write_config
):
    """policies.approval chains a gating callback onto the compiled nodes."""
    write_config(GRAPH_APPROVAL_YAML)

    config = resolve_agent_config()
    root = agent_module._build_root_agent(config, "yaml")

    node = next(n for n in root.graph.nodes if isinstance(n, LlmAgent))
    assert node.before_tool_callback is not None

    confirmations: list[dict] = []
    ctx = SimpleNamespace(
        state={},
        user_id="u1",
        request_confirmation=lambda **kw: confirmations.append(kw),
    )
    # basic_agent_mutating=False keeps the runtime protect callback passive so
    # the approval policy's veto is the one under test.
    gated = SimpleNamespace(name="publish", basic_agent_mutating=False)
    result = node.before_tool_callback(gated, {}, ctx)
    assert result == {
        "status": "blocked",
        "reason": "This action requires human approval before execution.",
    }
    assert confirmations, "the confirmation interrupt must be requested"

    # Unconditional tools always pass through (B3 invariants).
    passthrough = SimpleNamespace(name="finish_task", basic_agent_mutating=False)
    assert node.before_tool_callback(passthrough, {}, ctx) is None


def test_approval_policy_also_applies_to_preset_fallback_root(
    tmp_path, monkeypatch, write_config
):
    """The approval policy is topology-independent: preset roots get it too."""
    write_config(PRESET_APPROVAL_YAML)

    config = resolve_agent_config()
    root = agent_module._build_root_agent(config, "yaml")

    node = next(
        n
        for n in root.graph.nodes
        if isinstance(n, LlmAgent) and n.name == "direct_agent"
    )
    ctx = SimpleNamespace(state={}, user_id="u1", request_confirmation=None)
    gated = SimpleNamespace(name="publish", basic_agent_mutating=False)
    result = node.before_tool_callback(gated, {}, ctx)
    assert result is not None and result["status"] == "blocked"


def test_preset_fallback_when_no_graph_configured(tmp_path, monkeypatch, write_config):
    """Without a graph: block the preset path is unchanged."""
    write_config(PRESET_FALLBACK_YAML)

    config = resolve_agent_config()
    root = agent_module._build_root_agent(config, "yaml")

    assert isinstance(root, Workflow)
    names = {n.name for n in root.graph.nodes if hasattr(n, "name")}
    assert "direct_agent" in names
    assert agent_module._resolved_runtime_snapshot["use_case"] == "assistant"
