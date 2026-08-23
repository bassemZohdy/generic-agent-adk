"""Phase E2 — preset matrix: all eight preset keys build and RUN.

Each preset is compiled and executed with fake models (no real LLM): the
workflow backend via ``Runner(node=...)`` for every preset, the legacy
sugar fallback where defined, and ``team_coordinator`` through its
documented delegation escape hatch (current LlmAgent + sub_agents shape).
"""

from __future__ import annotations

import asyncio
from dataclasses import replace

import pytest
from google.adk.agents import LlmAgent
from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_response import LlmResponse
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.workflow import Workflow
from google.genai import types

from basic_agent.compile import compile_legacy
from basic_agent.runtime import RuntimeContext
from basic_agent.use_cases import get_default_registry

APP_NAME = "preset-matrix"
USER_ID = "matrix-user"


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
        description="preset matrix agent",
        output_key="last_response",
        max_iterations=5,
    )
    return replace(base, **overrides)


def state_of(events: list) -> dict:
    state: dict = {}
    for event in events:
        if event.actions and event.actions.state_delta:
            state.update(event.actions.state_delta)
    return state


def run_workflow(workflow: Workflow, session_id: str) -> list:
    async def _run():
        session_service = InMemorySessionService()
        await session_service.create_session(
            app_name=APP_NAME, user_id=USER_ID, session_id=session_id
        )
        runner = Runner(
            app_name=APP_NAME, node=workflow, session_service=session_service
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


def run_agent(agent: LlmAgent, session_id: str) -> list:
    async def _run():
        session_service = InMemorySessionService()
        await session_service.create_session(
            app_name=APP_NAME, user_id=USER_ID, session_id=session_id
        )
        runner = Runner(app_name=APP_NAME, agent=agent, session_service=session_service)
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


# (key, runtime overrides, name) — the full ADR-005 §5 classification.
MATRIX = [
    ("assistant", {}),
    ("pipeline", {"extra_config": {"steps": 2}}),
    ("multi_perspective", {"extra_config": {"workers": 2}}),
    ("refine_until_good", {}),
    ("expert_dispatch", {"specialists": ("research", "solution", "risk")}),
    ("approval_gate", {"require_approval": True}),
    ("plan_and_execute", {}),
    ("team_coordinator", {"extra_config": {"workers": 2}}),
]


@pytest.mark.parametrize(("key", "overrides"), MATRIX, ids=[case[0] for case in MATRIX])
def test_preset_runs_on_default_workflow_backend(key, overrides):
    """Each preset compiles and runs end-to-end via ``Preset.build``.

    team_coordinator runs through its documented delegation escape hatch
    (LlmAgent + sub_agents) — no graph shape exists.
    """
    registry = get_default_registry()
    preset = registry.get_preset(key)
    rt = make_rt(**overrides)
    root = preset.build(rt)
    if key == "team_coordinator":
        events = run_agent(root, "team_coordinator-workflow-session")
    else:
        events = run_workflow(root, f"{key}-workflow-session")
    state = state_of(events)

    assert events, f"{key}: run must record events"
    assert state.get("last_response"), f"{key}: output must land in state"
    if key == "refine_until_good":
        assert state["evaluator_optimizer_worker_loop_counter_count"] == 5
    if key == "expert_dispatch":
        assert "router_specialist_research" in {e.author for e in events}
    if key == "multi_perspective":
        assert "perspective_0" in state and "perspective_1" in state


@pytest.mark.parametrize(("key", "overrides"), MATRIX, ids=[case[0] for case in MATRIX])
def test_preset_legacy_fallback_where_defined(key, overrides):
    """Sugar-expressible presets also compile and run on the legacy backend."""
    registry = get_default_registry()
    preset = registry.get_preset(key)
    if key in ("expert_dispatch", "team_coordinator"):
        return  # no legacy sugar mapping (documented in the catalog)
    rt = make_rt(**overrides)
    spec = preset.build_legacy_spec(rt)
    root = compile_legacy(spec, rt, name=preset.legacy_name)
    events = run_agent(root, f"{key}-legacy-session")
    state = state_of(events)

    assert events, f"{key}: legacy run must record events"
    assert state.get("last_response"), f"{key}: legacy output must land in state"


def test_team_coordinator_runs_via_delegation_escape_hatch():
    """E2/E3: team_coordinator is the ADR-005 §6 escape hatch — LlmAgent+sub_agents."""
    registry = get_default_registry()
    rt = make_rt(extra_config={"workers": 2})
    root = registry.get_preset("team_coordinator").build(rt)

    assert isinstance(root, LlmAgent)
    assert [worker.name for worker in root.sub_agents] == [
        "supervisor_worker_0",
        "supervisor_worker_1",
    ]
    events = run_agent(root, "coordinator-session")
    assert events, "escape-hatch supervisor must complete its run"
