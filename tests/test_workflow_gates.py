"""Phase B gate-verification spike: real Workflow graphs as the served root.

These are **permanent contract tests**, not throwaway spike scripts (ADR-003
re-evaluation, ADR-005 Phase B).  They pin, on the locked google-adk 2.6.3 and
the same ``Runner`` path production serves through (the ADK api server builds
``Runner(app=...)`` for a ``BaseNode`` root — see ``cli/api_server.py``), the
three gates the migration rests on:

- G1: a graph ``Workflow`` can be the runnable root (chain of LlmAgents).
- G2: fan-out + ``JoinNode`` and a routed, bounded loop execute correctly.
- G3 (B2 in this file): interrupt -> resume through the workflow root.

The transport middleware in ``interfaces/rest.py`` (subject binding, rate
limits) wraps the runner and is orthogonal to graph execution; it is not
reproduced here.  No real LLM is called — ``DeterministicLlm`` backs every
node.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from google.adk.agents import LlmAgent
from google.adk.agents.invocation_context import LlmCallsLimitExceededError
from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_response import LlmResponse
from google.adk.plugins import BasePlugin
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.workflow import (
    DEFAULT_ROUTE,
    START,
    Edge,
    FunctionNode,
    JoinNode,
    Workflow,
)
from google.adk.workflow._errors import DynamicNodeFailError
from google.genai import types

APP_NAME = "workflow-gates"
USER_ID = "gate-user"


class DeterministicLlm(BaseLlm):
    """A no-network model that returns one valid response per model turn."""

    calls: int = 0

    async def generate_content_async(self, llm_request, stream=False):
        self.calls += 1
        yield LlmResponse(
            content=types.Content(
                role="model",
                parts=[types.Part(text=f"deterministic response {self.calls}")],
            )
        )


async def _run_workflow(
    workflow: Workflow, session_id: str
) -> tuple[list[Any], dict[str, Any]]:
    """Run a Workflow root through the same Runner construction the api
    server uses (Runner(app=...) with a BaseNode root)."""
    session_service = InMemorySessionService()
    await session_service.create_session(
        app_name=APP_NAME,
        user_id=USER_ID,
        session_id=session_id,
    )
    runner = Runner(
        app_name=APP_NAME,
        node=workflow,
        session_service=session_service,
    )
    events = await _run_runner_turn(runner, session_id)
    state: dict[str, Any] = {}
    for event in events:
        if event.actions and event.actions.state_delta:
            state.update(event.actions.state_delta)
    return events, state


async def _run_runner_turn(
    runner: Runner, session_id: str, run_config: Any = None
) -> list[Any]:
    return [
        event
        async for event in runner.run_async(
            user_id=USER_ID,
            session_id=session_id,
            new_message=types.Content(
                role="user", parts=[types.Part(text="Do the thing.")]
            ),
            run_config=run_config,
        )
    ]


async def _run_first_turn(runner: Runner, session_id: str) -> list[Any]:
    return await _run_runner_turn(runner, session_id)


def _authors(events: list[Any]) -> list[str]:
    return [event.author for event in events if event.author]


def test_workflow_chain_of_two_llm_agents_as_served_root():
    """G1: a Workflow chaining two LlmAgents runs as the root node."""
    model = DeterministicLlm(model="deterministic")
    step_one = LlmAgent(
        name="step_one",
        model=model,
        instruction="Produce the first part.",
        output_key="first",
    )
    step_two = LlmAgent(
        name="step_two",
        model=model,
        instruction="Produce the second part.",
        output_key="second",
    )
    # Nodes are inferred from edges; START is the implicit entry node.
    workflow = Workflow(
        name="chain_wf",
        edges=[(START, step_one, step_two)],
    )

    events, state = asyncio.run(_run_workflow(workflow, "chain-session"))

    assert events, "workflow must record session events"
    assert model.calls == 2, "both LlmAgent nodes must consume one model turn"
    # Single_turn LlmAgent nodes promote their text via ``output_key`` into
    # state_delta; the model-response event itself is streamed as a delegated
    # output (event.output is None, actions.state_delta carries the value).
    assert state.get("first") == "deterministic response 1"
    assert state.get("second") == "deterministic response 2"
    authors = _authors(events)
    # Authors are the workflow/node names or the user turn — never an
    # unexpected third-party author, and ordering follows the chain.
    allowed = {"user", "chain_wf", "step_one", "step_two"}
    assert set(authors) <= allowed, f"unexpected authors: {authors}"
    assert authors[0] == "step_one" and authors[1] == "step_two"


def test_workflow_fan_out_join_two_llm_agents():
    """G2a: parallel fan-out to two LlmAgents + JoinNode aggregation."""
    model = DeterministicLlm(model="deterministic")
    perspective_a = LlmAgent(
        name="perspective_a",
        model=model,
        instruction="Analyze from the user's perspective.",
        output_key="perspective_a",
    )
    perspective_b = LlmAgent(
        name="perspective_b",
        model=model,
        instruction="Analyze from the market perspective.",
        output_key="perspective_b",
    )
    join = JoinNode(name="join_perspectives")
    edges = [
        Edge(from_node=START, to_node=perspective_a),
        Edge(from_node=START, to_node=perspective_b),
        Edge(from_node=perspective_a, to_node=join),
        Edge(from_node=perspective_b, to_node=join),
    ]
    workflow = Workflow(name="fanout_wf", edges=edges)

    events, state = asyncio.run(_run_workflow(workflow, "fanout-session"))

    assert events, "workflow must record session events"
    assert model.calls == 2, "both fan-out branches must consume a model turn"
    assert state.get("perspective_a") == "deterministic response 1"
    assert state.get("perspective_b") == "deterministic response 2"
    # JoinNode outputs the aggregated predecessors' outputs.
    join_outputs = [
        event.output
        for event in events
        if event.output is not None and isinstance(event.output, dict)
    ]
    assert join_outputs, "JoinNode must emit an aggregated output"
    assert join_outputs[-1]["perspective_a"] == "deterministic response 1"
    assert join_outputs[-1]["perspective_b"] == "deterministic response 2"
    # Fan-out nodes must not interleave: both branches complete before join.
    assert set(_authors(events)) <= {
        "user",
        "fanout_wf",
        "perspective_a",
        "perspective_b",
        "join_perspectives",
    }


def workflow_loop_step(ctx: Any, node_input: Any = None) -> str:
    """Bounded loop node: route back to itself twice, then fall through."""
    count = int(ctx.state.get("loop_count", 0)) + 1
    ctx.state["loop_count"] = count
    if count < 3:
        ctx.route = "again"
    return f"iteration {count}"


def workflow_loop_done() -> str:
    """Terminal loop node."""
    return "finished"


def test_workflow_routed_bounded_loop():
    """G2b: a routed self-edge loops within N iterations and falls through."""
    loop_node = FunctionNode(func=workflow_loop_step, name="loop_step")
    final_node = FunctionNode(func=workflow_loop_done, name="final_step")
    workflow = Workflow(
        name="loop_wf",
        edges=[
            (START, loop_node),
            Edge(from_node=loop_node, to_node=loop_node, route="again"),
            Edge(from_node=loop_node, to_node=final_node, route=DEFAULT_ROUTE),
        ],
    )

    events, state = asyncio.run(_run_workflow(workflow, "loop-session"))

    assert events, "workflow must record session events"
    assert state.get("loop_count") == 3, "loop must run exactly 3 iterations"
    outputs = [
        event.output
        for event in events
        if isinstance(event.output, str) and event.output.startswith("iteration")
    ]
    assert outputs == ["iteration 1", "iteration 2", "iteration 3"]
    # No iteration 4: the loop bounded itself.
    assert "iteration 4" not in [event.output for event in events]
    assert any(event.output == "finished" for event in events), (
        "default route must reach the terminal node"
    )
    assert set(_authors(events)) <= {"user", "loop_wf", "loop_step", "final_step"}


def test_workflow_node_names_must_be_valid_identifiers():
    """BaseNode validates names; a bad name must fail loudly at construction."""
    with pytest.raises((ValueError, TypeError)):
        FunctionNode(func=workflow_loop_done, name="not-valid name")


# ─── B2 — interrupt -> resume through a workflow root ────────────────────────


def workflow_gather_input(ctx: Any, node_input: Any = None):
    """HITL node: request input once, then publish the user's answer to state."""
    from google.adk.events.request_input import RequestInput

    resume = ctx.resume_inputs.get("gather-user-input") if ctx.resume_inputs else None
    if resume is None:
        yield RequestInput(
            interrupt_id="gather-user-input",
            message="Please provide your answer.",
        )
        return
    ctx.state["user_answer"] = resume
    return None


def workflow_gather_no_rerun(ctx: Any, node_input: Any = None):
    """HITL node with rerun_on_resume=False: the response is the output."""
    from google.adk.events.request_input import RequestInput

    resume = ctx.resume_inputs.get("gather-passive") if ctx.resume_inputs else None
    if resume is None:
        yield RequestInput(
            interrupt_id="gather-passive",
            message="Please provide your answer.",
        )
        return
    return resume


def workflow_consume_answer(ctx: Any, node_input: Any = None) -> str:
    return f"final:{ctx.state.get('user_answer')}"


def workflow_consume_input(node_input: Any = None) -> str:
    return f"final:{node_input}"


def _run_workflow_resume(
    runner: Runner, session_id: str, interrupt_event: Any
) -> list[Any]:
    return asyncio.run(_resume_workflow(runner, session_id, interrupt_event))


async def _resume_workflow(
    runner: Runner, session_id: str, interrupt_event: Any
) -> list[Any]:
    interrupt_id = next(iter(interrupt_event.long_running_tool_ids))
    return [
        event
        async for event in runner.run_async(
            user_id=USER_ID,
            session_id=session_id,
            invocation_id=interrupt_event.invocation_id,
            new_message=types.Content(
                role="user",
                parts=[
                    types.Part(
                        function_response=types.FunctionResponse(
                            id=interrupt_id,
                            name="adk_request_input",
                            response={"result": "the answer"},
                        )
                    )
                ],
            ),
        )
    ]


def test_workflow_request_input_interrupts_then_resumes():
    """B2: a RequestInput FunctionNode interrupts; resume completes the run.

    Mirrors the legacy Runner confirmation contract pinned in
    ``test_workflow_invocations.py``: the interrupt event carries the
    interrupt id in ``long_running_tool_ids``, the invocation id is reused on
    resume, and a ``FunctionResponse(id, name='adk_request_input', ...)``
    delivers the answer.
    """
    gather_node = FunctionNode(
        func=workflow_gather_input, name="gather_step", rerun_on_resume=True
    )
    final_node = FunctionNode(func=workflow_consume_answer, name="final_step")
    workflow = Workflow(name="hitl_wf", edges=[(START, gather_node, final_node)])

    session_service = InMemorySessionService()
    session_id = "hitl-session"
    asyncio.run(
        session_service.create_session(
            app_name=APP_NAME, user_id=USER_ID, session_id=session_id
        )
    )
    runner = Runner(app_name=APP_NAME, node=workflow, session_service=session_service)
    pending = asyncio.run(_run_first_turn(runner, session_id))

    interrupt_event = next(e for e in pending if e.long_running_tool_ids)
    assert interrupt_event.long_running_tool_ids == {"gather-user-input"}
    first_fc = next(
        p.function_call
        for p in (interrupt_event.content.parts or [])
        if p.function_call
    )
    assert first_fc.name == "adk_request_input"
    assert first_fc.id == "gather-user-input"
    assert interrupt_event.invocation_id, "interrupt event carries the invocation id"

    resumed = _run_workflow_resume(runner, session_id, interrupt_event)

    # The node re-ran (rerun_on_resume=True) with its response in
    # ctx.resume_inputs, published the answer to state, and the workflow
    # completed with the terminal node's output.
    assert any(
        e.actions and e.actions.state_delta.get("user_answer") == "the answer"
        for e in resumed
    )
    assert any(e.output == "final:the answer" for e in resumed), (
        "resume must complete the workflow run"
    )


def test_workflow_request_input_resume_without_rerun_uses_response_output():
    """B2: rerun_on_resume=False fast-forwards the response as node output."""
    gather_node = FunctionNode(
        func=workflow_gather_no_rerun,
        name="gather_passive",
        rerun_on_resume=False,
    )
    final_node = FunctionNode(func=workflow_consume_input, name="final_step")
    workflow = Workflow(
        name="hitl_passive_wf", edges=[(START, gather_node, final_node)]
    )

    session_service = InMemorySessionService()
    session_id = "hitl-passive-session"
    asyncio.run(
        session_service.create_session(
            app_name=APP_NAME, user_id=USER_ID, session_id=session_id
        )
    )
    runner = Runner(app_name=APP_NAME, node=workflow, session_service=session_service)
    pending = asyncio.run(_run_first_turn(runner, session_id))
    interrupt_event = next(e for e in pending if e.long_running_tool_ids)

    resumed = _run_workflow_resume(runner, session_id, interrupt_event)

    assert any(e.output == "final:the answer" for e in resumed), (
        "the cancelled response must be promoted as the node output"
    )


# ─── B3 — hook/policy attachment point prototypes ────────────────────────────


def workflow_policy_pre(ctx: Any, node_input: Any = None) -> None:
    ctx.state["policy_marker"] = "pre-ran"


def workflow_policy_post(ctx: Any, node_input: Any = None) -> str:
    return f"policy:{ctx.state.get('policy_marker')}"


def test_workflow_boundary_function_nodes_attach_policies():
    """B3(a): boundary FunctionNodes at graph start/end are one policy point.

    The pre node writes a state marker; the post node reads it — proving
    per-run policy wiring that surrounds the whole graph.
    """
    pre = FunctionNode(func=workflow_policy_pre, name="policy_pre")
    post = FunctionNode(func=workflow_policy_post, name="policy_post")
    model = DeterministicLlm(model="deterministic")
    worker = LlmAgent(
        name="policy_worker",
        model=model,
        instruction="Do the work.",
        output_key="work_output",
    )
    workflow = Workflow(
        name="policy_wf",
        edges=[(START, pre, worker, post)],
    )

    events, state = asyncio.run(_run_workflow(workflow, "policy-session"))

    assert state.get("policy_marker") == "pre-ran"
    assert state.get("work_output") == "deterministic response 1"
    assert any(e.output == "policy:pre-ran" for e in events)


class RecordingPlugin(BasePlugin):
    """Plugin prototype (B3 option b) recording which hooks fire."""

    name: str = "recording-plugin"

    def __init__(self) -> None:
        super().__init__(name="recording-plugin")
        self.before_run: list[str] = []
        self.after_run: list[str] = []
        self.before_agent: list[str] = []
        self.after_agent: list[str] = []

    async def before_run_callback(self, *, invocation_context: Any) -> Any:
        self.before_run.append(invocation_context.invocation_id)
        return None

    async def after_run_callback(self, *, invocation_context: Any) -> None:
        self.after_run.append(invocation_context.invocation_id)

    async def before_agent_callback(self, *, agent: Any, callback_context: Any) -> Any:
        self.before_agent.append(getattr(agent, "name", "?"))
        return None

    async def after_agent_callback(self, *, agent: Any, callback_context: Any) -> Any:
        self.after_agent.append(getattr(agent, "name", "?"))
        return None


def test_workflow_plugin_hooks_cover_root_and_node_invocations():
    """B3(b): an ADK plugin gives root-level and per-node policy hooks."""
    from google.adk.apps import App

    model = DeterministicLlm(model="deterministic")
    worker = LlmAgent(
        name="plugin_worker",
        model=model,
        instruction="Do the work.",
        output_key="work_output",
    )
    workflow = Workflow(name="plugin_wf", edges=[(START, worker)])
    plugin = RecordingPlugin()
    app = App(name="plugin-probe", root_agent=workflow, plugins=[plugin])

    session_service = InMemorySessionService()
    session_id = "plugin-session"
    asyncio.run(
        session_service.create_session(
            app_name=app.name, user_id=USER_ID, session_id=session_id
        )
    )
    runner = Runner(app=app, session_service=session_service)
    events = asyncio.run(_run_runner_turn(runner, session_id))

    assert events, "run must record events"
    assert plugin.before_run and plugin.after_run, "run hooks must fire"
    assert plugin.before_agent, "agent hooks must fire for graph nodes"
    assert "plugin_worker" in plugin.before_agent


def _task_tool_callback(calls: list[str], veto_normal: bool, veto_finish: bool):
    def callback(tool: Any, args: Any, tool_context: Any):
        calls.append(tool.name)
        if tool.name == "finish_task" and veto_finish:
            return {"error": "vetoed finish_task"}
        if tool.name == "my_tool" and veto_normal:
            return {"error": "vetoed normal tool"}
        return None

    return callback


def _task_agent_finish_llm(turn: int):
    class FinishLlm(BaseLlm):
        calls: int = 0

        async def generate_content_async(self, llm_request, stream=False):
            self.calls += 1
            if self.calls == 1 and turn > 0:
                yield LlmResponse(
                    content=types.Content(
                        role="model",
                        parts=[
                            types.Part(
                                function_call=types.FunctionCall(
                                    name="my_tool",
                                    args={"value": 1},
                                    id="call-1",
                                )
                            )
                        ],
                    )
                )
                return
            yield LlmResponse(
                content=types.Content(
                    role="model",
                    parts=[
                        types.Part(
                            function_call=types.FunctionCall(
                                name="finish_task",
                                args={"result": "task answer"},
                                id="finish-1",
                            )
                        )
                    ],
                )
            )

    return FinishLlm


def _run_task_node(
    veto_normal: bool, veto_finish: bool
) -> tuple[list[str], int | None]:
    from google.adk.tools import FunctionTool

    model = _task_agent_finish_llm(1)(model="deterministic")
    calls: list[str] = []
    callback = _task_tool_callback(calls, veto_normal, veto_finish)

    def my_tool(value: int) -> str:
        return f"tool ran with {value}"

    agent = LlmAgent(
        name="task_agent",
        model=model,
        instruction="Do the task.",
        mode="task",
        tools=[FunctionTool(func=my_tool)],
        before_tool_callback=callback,
    )
    workflow = Workflow(name="task_wf", edges=[(START, agent)])

    session_service = InMemorySessionService()
    session_id = f"task-{veto_normal}-{veto_finish}"
    asyncio.run(
        session_service.create_session(
            app_name=APP_NAME, user_id=USER_ID, session_id=session_id
        )
    )
    runner = Runner(app_name=APP_NAME, node=workflow, session_service=session_service)
    model_calls: int | None = None
    try:
        events = asyncio.run(_run_runner_turn(runner, session_id))
        model_calls = model.calls
        assert any(e.output == {"result": "task answer"} for e in events), (
            "task node must complete when finish_task passes through"
        )
    except Exception:  # noqa: BLE001 - deadlock case re-raised as workflow error
        model_calls = model.calls
    return calls, model_calls


def test_task_mode_node_before_tool_callback_finish_task_rule():
    """B3: before_tool_callback sees finish_task; vetoing it deadlocks.

    Rule for policies: never gate ``finish_task`` (or ``_TaskAgentTool``
    delegations) — a veto replaces the success FR the wrapper waits for and
    the task node retries until the LLM-call limit (here bounded to 6 by
    ``RunConfig.max_llm_calls``) and the workflow fails.
    """
    from google.adk.agents.run_config import RunConfig

    calls, _ = _run_task_node(veto_normal=True, veto_finish=False)
    assert "my_tool" in calls, "callback must fire for normal tools"
    assert "finish_task" in calls, "callback must also see finish_task"
    # The veto of a normal tool is fine; completion still happens (checked in
    # _run_task_node).  Vetoing finish_task must deadlock the node:
    model = _task_agent_finish_llm(0)(model="deterministic")
    calls_deadlock: list[str] = []
    agent = LlmAgent(
        name="task_agent_deadlock",
        model=model,
        instruction="Do the task.",
        mode="task",
        before_tool_callback=_task_tool_callback(
            calls_deadlock, veto_normal=False, veto_finish=True
        ),
    )
    workflow = Workflow(name="deadlock_wf", edges=[(START, agent)])
    session_service = InMemorySessionService()
    session_id = "deadlock-session"
    asyncio.run(
        session_service.create_session(
            app_name=APP_NAME, user_id=USER_ID, session_id=session_id
        )
    )
    runner = Runner(app_name=APP_NAME, node=workflow, session_service=session_service)
    with pytest.raises((DynamicNodeFailError, LlmCallsLimitExceededError)):
        asyncio.run(
            _run_runner_turn(runner, session_id, run_config=RunConfig(max_llm_calls=6))
        )
    assert "finish_task" in calls_deadlock
    assert model.calls > 1, "finish_task veto must force repeated model rounds"
