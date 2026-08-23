"""Phase D1/D2 — approval and synthesis policy tests."""

from __future__ import annotations

import asyncio
from dataclasses import field
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from google.adk.agents import LlmAgent
from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_response import LlmResponse
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.tools import FunctionTool
from google.adk.tools.agent_tool import _TaskAgentTool
from google.adk.workflow import Workflow
from google.genai import types

from basic_agent.compile import compile_graph
from basic_agent.config import loader
from basic_agent.config.graph import (
    START,
    GraphEdgeSpec,
    GraphNodeSpec,
    GraphSpec,
)
from basic_agent.config.sugar import ParallelSugar, SequenceSugar, expand_sugar
from basic_agent.policies import (
    apply_approval_policy,
    is_unconditional_tool,
    make_approval_before_tool,
    with_synthesis,
)
from basic_agent.runtime import RuntimeContext
from basic_agent.tools import request_approval

APP_NAME = "policy-tests"
USER_ID = "policy-user"


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


class ScriptedLlm(BaseLlm):
    """A no-network model emitting a scripted function-call per turn."""

    calls: int = 0
    script: list[tuple[str, dict]] = field(default_factory=list)

    def __init__(self, script: list[tuple[str, dict]]):
        super().__init__(model=f"scripted-{len(script)}")
        self.script = script
        self.calls = 0

    async def generate_content_async(self, llm_request, stream=False):
        turn = min(self.calls, len(self.script) - 1)
        self.calls += 1
        name, args = self.script[turn]
        if name == "#text":
            yield LlmResponse(
                content=types.Content(
                    role="model",
                    parts=[types.Part(text=f"deterministic response {self.calls}")],
                )
            )
            return
        yield LlmResponse(
            content=types.Content(
                role="model",
                parts=[
                    types.Part(
                        function_call=types.FunctionCall(
                            name=name,
                            args=args,
                            id=f"call-{self.calls}",
                        )
                    )
                ],
            )
        )


def make_rt(model: BaseLlm, tools: list | None = None) -> RuntimeContext:
    return RuntimeContext(
        model=model,
        instruction="Runtime policy: follow the operator's task.",
        tools=tools or [],
        description="policy test agent",
        output_key="last_response",
    )


def run_node(workflow: Workflow, session_id: str) -> list:
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


def run_and_resume(workflow: Workflow, session_id: str) -> tuple[list, list]:
    """Run until the approval confirmation interrupt, then resume it."""

    async def _run():
        session_service = InMemorySessionService()
        await session_service.create_session(
            app_name=APP_NAME, user_id=USER_ID, session_id=session_id
        )
        runner = Runner(
            app_name=APP_NAME, node=workflow, session_service=session_service
        )

        async def turn(invocation_id=None, message=None):
            kwargs = {"invocation_id": invocation_id} if invocation_id else {}
            return [
                event
                async for event in runner.run_async(
                    user_id=USER_ID,
                    session_id=session_id,
                    new_message=message
                    or types.Content(
                        role="user", parts=[types.Part(text="Do the thing.")]
                    ),
                    **kwargs,
                )
            ]

        first = await turn()
        interrupt = next(e for e in first if e.long_running_tool_ids)
        interrupt_id = next(iter(interrupt.long_running_tool_ids))
        resumed = await turn(
            invocation_id=interrupt.invocation_id,
            message=types.Content(
                role="user",
                parts=[
                    types.Part(
                        function_response=types.FunctionResponse(
                            id=interrupt_id,
                            name="adk_request_confirmation",
                            response={"confirmed": True},
                        )
                    )
                ],
            ),
        )
        return first, resumed

    return asyncio.run(_run())


def state_of(events: list) -> dict:
    state: dict = {}
    for event in events:
        if event.actions and event.actions.state_delta:
            state.update(event.actions.state_delta)
    return state


def published_runs() -> list[str]:
    runs: list[str] = []

    def publish(action: str) -> str:
        runs.append(action)
        return f"published {action}"

    return runs, publish


# ─── D1 — approval policy ────────────────────────────────────────────────────


def test_unconditional_tools_are_never_gated():
    """request_approval / finish_task / _TaskAgentTool must pass through."""
    cfg = loader.ApprovalPolicyConfig(
        enabled=True,
        gated_tools=["publish", "request_approval", "finish_task"],
        gated_prefixes=["legacy_"],
    )
    callback = make_approval_before_tool(cfg)
    ctx = SimpleNamespace(state={}, request_confirmation=Mock())

    for name in ("request_approval", "finish_task"):
        assert callback(SimpleNamespace(name=name), {}, ctx) is None, name

    delegation = _TaskAgentTool(LlmAgent(name="delegate", model="deterministic"))
    assert is_unconditional_tool(delegation) is True
    assert callback(delegation, {}, ctx) is None
    ctx.request_confirmation.assert_not_called()

    # An ordinary gated name is still vetoed by a configured gated_tools
    # entry even when it shares a name with the unconditional set.
    assert callback(SimpleNamespace(name="publish"), {}, ctx) is not None


def test_gated_tool_is_vetoed_and_confirmation_requested():
    cfg = loader.ApprovalPolicyConfig(enabled=True, gated_tools=["publish"])
    callback = make_approval_before_tool(cfg)
    ctx = SimpleNamespace(state={}, request_confirmation=Mock())

    result = callback(SimpleNamespace(name="publish"), {"action": "x"}, ctx)

    assert result == {
        "status": "blocked",
        "reason": "This action requires human approval before execution.",
    }
    ctx.request_confirmation.assert_called_once()
    hint = ctx.request_confirmation.call_args.kwargs["hint"]
    assert "publish" in hint
    # An unlisted tool passes; a disabled policy passes everything.
    assert callback(SimpleNamespace(name="web_search"), {}, ctx) is None
    disabled = make_approval_before_tool(
        loader.ApprovalPolicyConfig(enabled=False, gated_tools=["publish"])
    )
    assert disabled(SimpleNamespace(name="publish"), {}, ctx) is None


def test_approval_policy_works_on_assistant_topology():
    """D1: compiled single-llm-node workflow honors the gating policy."""
    model = ScriptedLlm([("publish", {"action": "deploy"}), ("#text", {})])
    runs, publish = published_runs()
    root = compile_graph(
        expand_sugar(
            SequenceSugar(items=["assistant_node"]),
            {"assistant_node": GraphNodeSpec(name="assistant_node", kind="llm")},
        ),
        make_rt(
            model,
            tools=[
                FunctionTool(publish),
                FunctionTool(request_approval, require_confirmation=True),
            ],
        ),
        name="assistant_wf",
    )
    apply_approval_policy(
        root,
        make_approval_before_tool(
            loader.ApprovalPolicyConfig(enabled=True, gated_tools=["publish"])
        ),
    )

    events, _ = run_and_resume(root, "assistant-approval-session")

    # The gated tool never executed; its FR carries the veto, and the policy's
    # request_confirmation produced the engine confirmation interrupt.
    assert runs == [], "gated tool must not run"
    assert any(
        p.function_response
        for e in events
        for p in (e.content.parts or [])
        if p.function_response
        and p.function_response.response.get("status") == "blocked"
    ), "gated tool must be vetoed"
    immediate = next(e for e in events if e.long_running_tool_ids)
    assert next(iter(immediate.long_running_tool_ids)) != "", (
        "confirmation interrupt must carry an id"
    )


def test_approval_policy_works_on_pipeline_topology():
    """D1: compiled sequence workflow honors the policy and resumes cleanly."""
    model = ScriptedLlm(
        [("publish", {"action": "deploy"}), ("#text", {}), ("#text", {})]
    )
    runs, publish = published_runs()
    spec = expand_sugar(
        SequenceSugar(items=["step_0", "step_1"]),
        {
            "step_0": GraphNodeSpec(name="step_0", kind="llm", output_key="step0"),
            "step_1": GraphNodeSpec(name="step_1", kind="llm", output_key="step1"),
        },
    )
    root = compile_graph(
        spec,
        make_rt(model, tools=[FunctionTool(publish)]),
        name="pipeline_wf",
    )
    apply_approval_policy(
        root,
        make_approval_before_tool(
            loader.ApprovalPolicyConfig(enabled=True, gated_tools=["publish"])
        ),
    )

    first, resumed = run_and_resume(root, "pipeline-approval-session")
    state = state_of(first + resumed)

    assert runs == [], "gated tool must not run"
    assert any(
        p.function_response
        for e in first
        for p in (e.content.parts or [])
        if p.function_response
        and p.function_response.response.get("reason", "").find("approval") != -1
    ), "step_0 must block the gated tool"
    assert state.get("step0") is not None, "step_0 must complete after resume"
    assert state.get("step1") is not None, "pipeline must complete after resume"


# ─── D2 — synthesis policy ───────────────────────────────────────────────────


def test_with_synthesis_follows_parallel_join():
    spec = expand_sugar(
        ParallelSugar(items=["p0", "p1"]),
        {
            "p0": GraphNodeSpec(name="p0", kind="llm", output_key="perspective_0"),
            "p1": GraphNodeSpec(name="p1", kind="llm", output_key="perspective_1"),
        },
    )
    combined = with_synthesis(spec)

    names = [n.name for n in combined.nodes]
    assert names == [
        "p0",
        "p1",
        "p0_join",
        "perspective_synthesizer",
        "synthesis_aggregate",
    ]
    assert combined.edges[-2] == GraphEdgeSpec(
        source="p0_join", target="perspective_synthesizer"
    )
    assert combined.edges[-1] == GraphEdgeSpec(
        source="perspective_synthesizer", target="synthesis_aggregate"
    )
    combined.validate()


def test_with_synthesis_adds_join_to_raw_fanout():
    raw = GraphSpec(
        nodes=[
            GraphNodeSpec(name="p0", kind="llm", output_key="perspective_0"),
            GraphNodeSpec(name="p1", kind="llm", output_key="perspective_1"),
        ],
        edges=[GraphEdgeSpec(source=START, target=["p0", "p1"])],
    )
    combined = with_synthesis(raw)

    nodes = {n.name: n for n in combined.nodes}
    assert nodes["synthesis_join"].kind == "join"
    assert combined.edges[-4] == GraphEdgeSpec(source="p0", target="synthesis_join")
    assert combined.edges[-3] == GraphEdgeSpec(source="p1", target="synthesis_join")
    assert combined.edges[-2] == GraphEdgeSpec(
        source="synthesis_join", target="perspective_synthesizer"
    )
    assert combined.edges[-1] == GraphEdgeSpec(
        source="perspective_synthesizer", target="synthesis_aggregate"
    )
    # Workflow-compilable shape.
    compile_graph(combined, make_rt(DeterministicLlm(model="deterministic")))
    assert set(combined.nodes_by_name()) == {
        "p0",
        "p1",
        "synthesis_join",
        "perspective_synthesizer",
        "synthesis_aggregate",
    }


def test_synthesis_workflow_runs_and_aggregates_like_multi_perspective():
    model = DeterministicLlm(model="deterministic")
    spec = expand_sugar(
        ParallelSugar(items=["p0", "p1"]),
        {
            "p0": GraphNodeSpec(name="p0", kind="llm", output_key="perspective_0"),
            "p1": GraphNodeSpec(name="p1", kind="llm", output_key="perspective_1"),
        },
    )
    root = compile_graph(
        with_synthesis(spec),
        make_rt(model),
        name="synthesis_wf",
    )
    events = run_node(root, "synthesis-session")
    state = state_of(events)

    assert state["perspective_0"] == "deterministic response 1"
    assert state["perspective_1"] == "deterministic response 2"
    assert state["last_response"] == "deterministic response 3", (
        "synthesizer node must run after the join"
    )
    assert "perspective_synthesizer" in {e.author for e in events}
    # The native aggregator node writes the same state keys the use case did.
    assert state["aggregated_perspectives"] == [
        "deterministic response 1",
        "deterministic response 2",
    ]


# ─── config surface ──────────────────────────────────────────────────────────


def test_policies_config_parses_from_yaml(tmp_path):
    path = tmp_path / "policies.yaml"
    path.write_text(
        """
agent:
  use_case: assistant
policies:
  approval:
    enabled: true
    gated_tools: ["publish", "deploy"]
    gated_prefixes: ["legacy_"]
  synthesis:
    enabled: true
    instruction: "Aggregate the takes."
    output_key: "summary"
""",
        encoding="utf-8",
    )
    config = loader.load_config_from_yaml(str(path))

    assert config.policies is not None
    assert config.policies.approval is not None
    assert config.policies.approval.enabled is True
    assert config.policies.approval.gated_tools == ["publish", "deploy"]
    assert config.policies.approval.gated_prefixes == ["legacy_"]
    assert config.policies.synthesis is not None
    assert config.policies.synthesis.enabled is True
    assert config.policies.synthesis.instruction == "Aggregate the takes."
    assert config.policies.synthesis.output_key == "summary"


def test_policies_config_defaults_and_fail_fast(tmp_path):
    path = tmp_path / "policies-defaults.yaml"
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
    assert config.policies.synthesis is None
    assert config.policies.approval.gated_tools == []

    with pytest.raises(ValueError, match="Unknown policies.approval field"):
        loader._parse_policies({"approval": {"enabled": True, "surprise": 1}})
