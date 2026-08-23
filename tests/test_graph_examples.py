"""F1 — example validation: every example YAML loads and compiles.

The eight preset examples are additionally exercised end-to-end in
``test_workflow_invocations.py``; this suite guarantees the whole examples/
directory loads through the real loader (including the graph-first examples
added in F1) and that the two graph examples compile AND run with fake
models.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_response import LlmResponse
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from basic_agent import agent as agent_module
from basic_agent.compile import compile_graph
from basic_agent.config.loader import load_config_from_yaml

ROOT = Path(__file__).parents[1]
EXAMPLES = ROOT / "examples"
USER_ID = "example-user"


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


def test_every_example_loads_and_validates(fake_model):
    """The loader accepts every shipped example YAML (graph specs validated)."""
    paths = sorted(EXAMPLES.glob("*.yaml"))
    assert len(paths) >= 10, "all eight presets plus the F1 graph examples"
    for path in paths:
        config = load_config_from_yaml(str(path))
        config.validate()
        if config.graph is not None:
            config.graph.validate()
            # Compile the graph section (workflow backend) so examples stay
            # structurally valid against the engine, not just the parser.
            rt = agent_module._build_runtime_context(config)
            compile_graph(config.graph, rt, name=path.stem.replace("-", "_"))


def run_graph(root, session_id):
    async def _run():
        session_service = InMemorySessionService()
        await session_service.create_session(
            app_name="example-tests", user_id=USER_ID, session_id=session_id
        )
        runner = Runner(
            app_name="example-tests", node=root, session_service=session_service
        )
        return [
            event
            async for event in runner.run_async(
                user_id=USER_ID,
                session_id=session_id,
                new_message=types.Content(
                    role="user", parts=[types.Part(text="Do the thing.")]
                ),
            )
        ]

    return asyncio.run(_run())


def state_of(events):
    state = {}
    for event in events:
        if event.actions and event.actions.state_delta:
            state.update(event.actions.state_delta)
    return state


def test_graph_nested_example_runs(fake_model):
    config = load_config_from_yaml(str(EXAMPLES / "graph-nested.yaml"))
    rt = agent_module._build_runtime_context(config)
    root = compile_graph(config.graph, rt, name="nested_example")

    events = run_graph(root, "nested-example-session")
    state = state_of(events)

    assert events, "nested example must run"
    # Intake writes its schema-cleared key; the subgraph fan-out writes the
    # perspective keys; the inner synthesizer writes the shared output.
    assert state["request_summary"] == "deterministic response 1"
    assert state["perspective_0"] == "deterministic response 2"
    assert state["perspective_1"] == "deterministic response 3"
    assert state["last_response"] == "deterministic response 4"
    assert "synthesize" in {e.author for e in events}


def test_graph_routed_example_runs(fake_model):
    config = load_config_from_yaml(str(EXAMPLES / "graph-routed.yaml"))
    rt = agent_module._build_runtime_context(config)
    root = compile_graph(config.graph, rt, name="routed_example")

    events = run_graph(root, "routed-example-session")
    state = state_of(events)

    assert events, "routed example must run"
    assert "research_specialist" in {e.author for e in events}, (
        "the default route must reach the research branch"
    )
    assert "risk_specialist" not in {e.author for e in events}
    assert state.get("last_response") == "deterministic response 1"
