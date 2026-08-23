"""Phase C3 — compile layer tests: workflow/legacy backends + isolation."""

from __future__ import annotations

import ast
import asyncio
from pathlib import Path
from typing import Any

import pytest
from google.adk.agents import LlmAgent, LoopAgent, ParallelAgent, SequentialAgent
from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_response import LlmResponse
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.workflow import (
    DEFAULT_ROUTE as ADK_DEFAULT_ROUTE,
)
from google.adk.workflow import (
    START as ADK_START,
)
from google.adk.workflow import (
    Edge,
    FunctionNode,
    JoinNode,
    Workflow,
)
from google.genai import types

from basic_agent import compile as compile_pkg
from basic_agent.compile import compile_graph, compile_legacy
from basic_agent.config.graph import (
    START,
    GraphEdgeSpec,
    GraphNodeSpec,
    GraphSpec,
    RetrySpec,
)
from basic_agent.config.sugar import (
    AGAIN_ROUTE,
    LoopSugar,
    ParallelSugar,
    SequenceSugar,
    expand_sugar,
)
from basic_agent.strategies.base import RuntimeContext

APP_NAME = "compile-tests"
USER_ID = "compile-user"


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


def make_rt(model: Any = None) -> RuntimeContext:
    return RuntimeContext(
        model=model or DeterministicLlm(model="deterministic"),
        instruction="Runtime policy: follow the operator's task.",
        tools=[],
        description="compiled test agent",
        output_key="last_response",
    )


def llm_node(name: str, *, output_key: str | None = None) -> GraphNodeSpec:
    return GraphNodeSpec(name=name, kind="llm", output_key=output_key)


def run_workflow(workflow: Workflow, session_id: str) -> list[Any]:
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


def state_of(events: list[Any]) -> dict[str, Any]:
    state: dict[str, Any] = {}
    for event in events:
        if event.actions and event.actions.state_delta:
            state.update(event.actions.state_delta)
    return state


# ─── workflow compiler ───────────────────────────────────────────────────────


def test_compile_sequence_spec_to_workflow():
    spec = expand_sugar(
        SequenceSugar(items=["step_1", "step_2"]),
        {
            "step_1": llm_node("step_1", output_key="step1"),
            "step_2": llm_node("step_2", output_key="step2"),
        },
    )
    workflow = compile_graph(spec, make_rt(), name="compiled_chain")

    assert isinstance(workflow, Workflow)
    assert workflow.name == "compiled_chain"
    compiled = {
        node.name: node for node in workflow.graph.nodes if node is not ADK_START
    }
    assert set(compiled) == {"step_1", "step_2"}
    assert isinstance(compiled["step_1"], LlmAgent)
    # START edge + chain edge, both unconditional.
    assert workflow.graph.edges == [
        Edge(from_node=ADK_START, to_node=compiled["step_1"], route=None),
        Edge(from_node=compiled["step_1"], to_node=compiled["step_2"], route=None),
    ]


def test_workflow_compiled_chain_runs_with_fake_model():
    model = DeterministicLlm(model="deterministic")
    spec = expand_sugar(
        SequenceSugar(items=["step_1", "step_2"]),
        {
            "step_1": llm_node("step_1", output_key="step1"),
            "step_2": llm_node("step_2", output_key="step2"),
        },
    )
    workflow = compile_graph(spec, make_rt(model), name="compiled_chain")
    events = run_workflow(workflow, "compiled-chain-session")

    state = state_of(events)
    assert model.calls == 2
    assert state["step1"] == "deterministic response 1"
    assert state["step2"] == "deterministic response 2"
    authors = [e.author for e in events]
    assert authors[0] == "step_1" and authors[1] == "step_2"


def test_compile_routed_fanout_join_spec_to_workflow():
    spec = GraphSpec(
        nodes=[
            llm_node("branch_a"),
            llm_node("branch_b"),
            GraphNodeSpec(name="collect", kind="join"),
            llm_node("finish"),
        ],
        edges=[
            GraphEdgeSpec(source=START, target=["branch_a", "branch_b"]),
            GraphEdgeSpec(source="branch_a", target="collect"),
            GraphEdgeSpec(source="branch_b", target="collect", route="done"),
            GraphEdgeSpec(source="collect", target="finish", route=ADK_DEFAULT_ROUTE),
        ],
    )
    workflow = compile_graph(spec, make_rt(), name="routed_wf")

    compiled = {
        node.name: node for node in workflow.graph.nodes if node is not ADK_START
    }
    assert isinstance(compiled["branch_a"], LlmAgent)
    assert isinstance(compiled["collect"], JoinNode)
    edges = workflow.graph.edges
    assert edges[0] == Edge(
        from_node=ADK_START, to_node=compiled["branch_a"], route=None
    )
    assert edges[1] == Edge(
        from_node=ADK_START, to_node=compiled["branch_b"], route=None
    )
    assert edges[2].route is None
    assert edges[3].route == "done"
    assert edges[4].route == ADK_DEFAULT_ROUTE


def test_compile_nested_graph_spec_to_subworkflow():
    inner = expand_sugar(
        SequenceSugar(items=["inner_step"]),
        {"inner_step": llm_node("inner_step")},
    )
    spec = GraphSpec(
        nodes=[
            llm_node("outer"),
            GraphNodeSpec(name="nested", kind="graph", graph=inner),
        ],
        edges=[
            GraphEdgeSpec(source=START, target="outer"),
            GraphEdgeSpec(source="outer", target="nested"),
        ],
    )
    workflow = compile_graph(spec, make_rt(), name="nested_wf")

    nested = {
        node.name: node for node in workflow.graph.nodes if node is not ADK_START
    }["nested"]
    assert isinstance(nested, Workflow)
    assert nested.name == "nested"
    assert {n.name for n in nested.graph.nodes if n is not ADK_START} == {"inner_step"}


def test_compile_loop_counter_function_is_built_in():
    spec = expand_sugar(
        LoopSugar(body="worker", max_iterations=3),
        {"worker": llm_node("worker")},
    )
    workflow = compile_graph(spec, make_rt(), name="compiled_loop")

    compiled = {
        node.name: node for node in workflow.graph.nodes if node is not ADK_START
    }
    counter = compiled["worker_loop_counter"]
    assert isinstance(counter, FunctionNode)
    assert counter.rerun_on_resume is False  # FunctionNode default
    # Counter edges: body → counter and routed back with AGAIN_ROUTE.
    edge_routes = {
        (e.from_node.name, e.to_node.name): e.route for e in workflow.graph.edges
    }
    assert edge_routes[("worker_loop_counter", "worker")] == AGAIN_ROUTE


def test_workflow_compiled_loop_runs_bounded():
    model = DeterministicLlm(model="deterministic")
    spec = expand_sugar(
        LoopSugar(body="worker", max_iterations=3),
        {"worker": llm_node("worker", output_key="body_out")},
    )
    workflow = compile_graph(spec, make_rt(model), name="compiled_loop")
    events = run_workflow(workflow, "compiled-loop-session")

    state = state_of(events)
    assert state["worker_loop_counter_count"] == 3
    assert state["body_out"] == "deterministic response 3"
    assert model.calls == 3, "loop must run the body exactly 3 times"


def test_compile_function_registry_node():
    def compute(ctx: Any, node_input: Any = None) -> str:
        return "computed"

    spec = GraphSpec(
        nodes=[
            GraphNodeSpec(
                name="compute", kind="function", options={"function": "compute"}
            )
        ],
        edges=[GraphEdgeSpec(source=START, target="compute")],
    )
    workflow = compile_graph(
        spec, make_rt(), name="fn_wf", function_registry={"compute": compute}
    )
    node = {n.name: n for n in workflow.graph.nodes}["compute"]
    assert isinstance(node, FunctionNode)

    with pytest.raises(ValueError, match="requires options.function"):
        compile_graph(
            GraphSpec(
                nodes=[GraphNodeSpec(name="bad", kind="function")],
                edges=[GraphEdgeSpec(source=START, target="bad")],
            ),
            make_rt(),
        )


# ─── legacy compiler (rollback-only) ─────────────────────────────────────────


def test_compile_legacy_sequence():
    spec = expand_sugar(
        SequenceSugar(items=["sequential_step_0", "sequential_step_1"]),
        {
            "sequential_step_0": llm_node("sequential_step_0"),
            "sequential_step_1": llm_node("sequential_step_1"),
        },
    )
    agent = compile_legacy(spec, make_rt(), name="sequential_agent")

    assert isinstance(agent, SequentialAgent)
    assert agent.name == "sequential_agent"
    assert [step.name for step in agent.sub_agents] == [
        "sequential_step_0",
        "sequential_step_1",
    ]
    assert all(isinstance(step, LlmAgent) for step in agent.sub_agents)


def test_compile_legacy_parallel():
    spec = expand_sugar(
        ParallelSugar(items=["parallel_worker_0", "parallel_worker_1"]),
        {
            "parallel_worker_0": llm_node("parallel_worker_0"),
            "parallel_worker_1": llm_node("parallel_worker_1"),
        },
    )
    agent = compile_legacy(spec, make_rt(), name="parallel_agent")

    assert isinstance(agent, ParallelAgent)
    assert [worker.name for worker in agent.sub_agents] == [
        "parallel_worker_0",
        "parallel_worker_1",
    ]


def test_compile_legacy_loop():
    spec = expand_sugar(
        LoopSugar(body="loop_worker", max_iterations=5),
        {"loop_worker": llm_node("loop_worker")},
    )
    agent = compile_legacy(spec, make_rt(), name="loop_agent")

    assert isinstance(agent, LoopAgent)
    assert agent.max_iterations == 5
    assert [worker.name for worker in agent.sub_agents] == ["loop_worker"]


def test_compile_legacy_rejects_explicit_edge_specs():
    spec = GraphSpec(
        nodes=[llm_node("a"), llm_node("b")],
        edges=[
            GraphEdgeSpec(source=START, target="a"),
            GraphEdgeSpec(source="a", target="b"),
        ],
    )
    with pytest.raises(ValueError, match="sugar subset only"):
        compile_legacy(spec, make_rt())


def test_per_node_concerns_attach_to_compiled_workflow_nodes():
    """D3: retry/timeout/schemas/output_key/code_executor per-node homes."""
    import pydantic
    from google.adk.code_executors.base_code_executor import BaseCodeExecutor

    class OutputModel(pydantic.BaseModel):
        answer: str

    class StateModel(pydantic.BaseModel):
        last_response: object | None = None

    class FakeExecutor(BaseCodeExecutor):
        def __init__(self) -> None:
            super().__init__(stateful=False)

        def execute_code(self, invocation_context, code_execution_input):
            return None

    executor = FakeExecutor()
    rt = make_rt()
    rt.code_executor = executor
    spec = GraphSpec(
        nodes=[
            GraphNodeSpec(
                name="step_0",
                kind="llm",
                retry=RetrySpec(max_attempts=4, initial_delay=0.5, max_delay=30.0),
                timeout=45.0,
                output_schema="OutputModel",
                state_schema="StateModel",
                output_key="answer_key",
            )
        ],
        edges=[GraphEdgeSpec(source=START, target="step_0")],
    )
    workflow = compile_graph(
        spec,
        rt,
        name="concern_wf",
        schema_registry={"OutputModel": OutputModel, "StateModel": StateModel},
    )
    node = next(n for n in workflow.graph.nodes if n is not ADK_START)
    assert node.name == "step_0"
    assert node.retry_config is not None
    assert node.retry_config.max_attempts == 4
    assert node.retry_config.initial_delay == 0.5
    assert node.retry_config.max_delay == 30.0
    assert node.timeout == 45.0
    assert node.output_schema is OutputModel
    assert node.state_schema is StateModel
    assert node.output_key == "answer_key"
    # ADR-004: the resolved executor attaches through the shared builder.
    assert node.code_executor is executor


def test_legacy_compiled_llm_applies_output_keys_schemas_executor_only():
    """D3: legacy (rollback) applies schemas/keys/executor; retry/timeout are
    workflow-backend-only per the concern table."""
    import pydantic
    from google.adk.code_executors.base_code_executor import BaseCodeExecutor

    class OutputModel(pydantic.BaseModel):
        answer: str

    class FakeExecutor(BaseCodeExecutor):
        def __init__(self) -> None:
            super().__init__(stateful=False)

        def execute_code(self, invocation_context, code_execution_input):
            return None

    executor = FakeExecutor()
    rt = make_rt()
    rt.code_executor = executor
    spec = GraphSpec(
        nodes=[
            GraphNodeSpec(
                name="direct_agent",
                kind="llm",
                retry=RetrySpec(max_attempts=9),
                timeout=15.0,
                output_schema="OutputModel",
                output_key="answer_key",
            )
        ],
        edges=[GraphEdgeSpec(source=START, target="direct_agent")],
        shape="sequence",
    )
    node = compile_legacy(
        spec, rt, name="direct_agent", schema_registry={"OutputModel": OutputModel}
    )
    assert isinstance(node, LlmAgent)
    assert node.output_key == "answer_key"
    assert node.output_schema is OutputModel
    assert node.code_executor is executor
    # Documented rollback limitation: per-node retry/timeout are not applied
    # by the legacy sugar trees.
    assert node.retry_config is None
    assert node.timeout is None


def test_unknown_schema_name_fails_fast():
    with pytest.raises(ValueError, match="Unknown schema name"):
        compile_graph(
            GraphSpec(
                nodes=[
                    GraphNodeSpec(name="step_0", kind="llm", output_schema="Missing")
                ],
                edges=[GraphEdgeSpec(source=START, target="step_0")],
            ),
            make_rt(),
        )


# ─── backend selection + import isolation ────────────────────────────────────


def test_compose_backend_flag(monkeypatch):
    assert compile_pkg.compose_backend() == "workflow"
    monkeypatch.setenv("AGENT_COMPOSE_BACKEND", "legacy")
    assert compile_pkg.compose_backend() == "legacy"
    monkeypatch.setenv("AGENT_COMPOSE_BACKEND", "bogus")
    with pytest.raises(ValueError, match="AGENT_COMPOSE_BACKEND"):
        compile_pkg.compose_backend()


_COMPOSITION_SYMBOLS = {
    "Agent",
    "BaseAgent",
    "LlmAgent",
    "SequentialAgent",
    "ParallelAgent",
    "LoopAgent",
    "Workflow",
    "Edge",
    "JoinNode",
    "FunctionNode",
    "Node",
    "BaseNode",
    "RetryConfig",
    "node",
    "START",
    "DEFAULT_ROUTE",
}

#: Importers allowed outside ``compile/``: agent.py subclasses Agent/BaseAgent
#: (runtime assembly) and strategies/ + use_cases/ are the E3 retirement
#: targets whose construction moves into compile/ before deletion.
_ALLOWED_COMPOSITION_IMPORTERS = {
    Path("basic_agent/agent.py"),
    Path("basic_agent/strategies"),
    Path("basic_agent/use_cases"),
    Path("basic_agent/compile"),
}


def test_only_compile_and_retiring_modules_import_adk_composition():
    """ADR-005 §3 rule: compile/ is the sole composition-class importer."""
    src_root = Path(__file__).parents[1] / "src" / "basic_agent"
    offenders: list[str] = []
    for path in src_root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module in (
                "google.adk.agents",
                "google.adk.workflow",
            ):
                for alias in node.names:
                    imported.add(alias.asname or alias.name)
        offending = imported & _COMPOSITION_SYMBOLS
        if offending:
            relative = path.relative_to(src_root.parent)
            if not any(
                relative == allowed or relative.parts[0] == allowed.parts[0]
                for allowed in _ALLOWED_COMPOSITION_IMPORTERS
            ):
                offenders.append(f"{relative}: {sorted(offending)}")
    assert not offenders, (
        "Only compile/ (and the E3-retirement modules agent.py, strategies/, "
        f"use_cases/) may import ADK composition classes; found: {offenders}"
    )
