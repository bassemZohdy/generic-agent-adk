"""Phase C4 — golden parity: strategy trees vs legacy-compiled preset specs.

For each built-in use case that maps onto a legacy-expressible preset (per
ADR-005 §5 / TODO E2), the preset-expanded graph spec compiled by
``compile/legacy.py`` must be structurally equivalent to today's strategy
output: same agent classes, same names, same instructions (including the
generated per-step defaults and the instruction-merge contract), same
``sub_agents`` ordering, same ``output_key``\\ s, same loop bounds.

Tree-walk comparator, not string dumps — per the C4 spec.  Callback wiring
is excluded deliberately: use-case hook chaining (multi_perspective
``after_run``, approval_gate ``before_tool``) is re-homed by the D1/D2
policies; the trees must match on structure, not on the hook objects.
``expert_dispatch``/``team_coordinator`` are the routing/delegation presets
— workflow-first shapes whose parity lands with E2 (no legacy sugar shape).
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

import pytest
from google.adk.agents import LlmAgent, LoopAgent, SequentialAgent
from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_response import LlmResponse
from google.genai import types

from basic_agent.compile import compile_legacy
from basic_agent.config.graph import GraphNodeSpec
from basic_agent.config.sugar import (
    LoopSugar,
    ParallelSugar,
    SequenceSugar,
    expand_sugar,
)
from basic_agent.strategies.base import RoleConfig, RuntimeContext
from basic_agent.use_cases import get_default_registry

PIPELINE_STEP_0 = (
    "You are step 0 of 2 in this pipeline. Perform your stage of the overall "
    "task, building on the output of any previous steps, then hand off your "
    "result."
)
PIPELINE_STEP_1 = (
    "You are step 1 of 2 in this pipeline. Perform your stage of the overall "
    "task, building on the output of any previous steps, then hand off your "
    "result."
)
REFINE_INSTRUCTION = (
    "Generate a solution, evaluate it critically, and improve it. Repeat "
    "until satisfied."
)
SYNTHESIZER_INSTRUCTION = (
    "Read the perspective outputs in session state, compare where they agree "
    "or differ, and produce one balanced final answer."
)


class DeterministicLlm(BaseLlm):
    """A no-network model for runtime construction."""

    calls: int = 0

    async def generate_content_async(self, llm_request, stream=False):
        self.calls += 1
        yield LlmResponse(
            content=types.Content(
                role="model",
                parts=[types.Part(text=f"deterministic response {self.calls}")],
            )
        )


def make_runtime(**overrides: Any) -> RuntimeContext:
    base = RuntimeContext(
        model=DeterministicLlm(model="deterministic"),
        instruction="Runtime policy: follow the operator's task.",
        tools=[],
        description="parity test agent",
        output_key="last_response",
    )
    return replace(base, **overrides)


def describe(root: Any) -> dict[str, Any]:
    """Tree-walk structural description (classes, names, instructions, keys)."""
    entry: dict[str, Any] = {
        "type": type(root).__name__,
        "name": root.name,
        "instruction": getattr(root, "instruction", None),
        "output_key": getattr(root, "output_key", None),
    }
    if isinstance(root, LoopAgent):
        entry["max_iterations"] = root.max_iterations
    sub_agents = getattr(root, "sub_agents", None) or []
    entry["sub_agents"] = [describe(sub) for sub in sub_agents]
    return entry


def spec_single(name: str) -> Any:
    return expand_sugar(
        SequenceSugar(items=[name]),
        {name: GraphNodeSpec(name=name, kind="llm")},
    )


def spec_sequence(nodes: list[GraphNodeSpec]) -> Any:
    by_name = {node.name: node for node in nodes}
    return expand_sugar(SequenceSugar(items=[node.name for node in nodes]), by_name)


def spec_loop(body: GraphNodeSpec, max_iterations: int) -> Any:
    return expand_sugar(
        LoopSugar(body=body.name, max_iterations=max_iterations),
        {body.name: body},
    )


def _pipeline_spec() -> Any:
    nodes = [
        GraphNodeSpec(
            name="sequential_step_0",
            kind="llm",
            role=RoleConfig(instruction=PIPELINE_STEP_0),
        ),
        GraphNodeSpec(
            name="sequential_step_1",
            kind="llm",
            role=RoleConfig(instruction=PIPELINE_STEP_1),
        ),
    ]
    return spec_sequence(nodes)


def _multi_perspective_spec() -> Any:
    workers = [
        GraphNodeSpec(name="parallel_worker_0", kind="llm", output_key="perspective_0"),
        GraphNodeSpec(name="parallel_worker_1", kind="llm", output_key="perspective_1"),
    ]
    synthesizer = GraphNodeSpec(
        name="perspective_synthesizer",
        kind="llm",
        output_key="last_response",
        role=RoleConfig(instruction=SYNTHESIZER_INSTRUCTION),
    )
    sugar = SequenceSugar(
        items=[
            ParallelSugar(
                items=["parallel_worker_0", "parallel_worker_1"],
                name="parallel_agent",
            ),
            "perspective_synthesizer",
        ]
    )
    by_name = {node.name: node for node in workers + [synthesizer]}
    return expand_sugar(sugar, by_name)


def _refine_spec() -> Any:
    body = GraphNodeSpec(
        name="evaluator_optimizer_worker",
        kind="llm",
        role=RoleConfig(instruction=REFINE_INSTRUCTION),
    )
    return spec_loop(body, 5)


def _approval_spec() -> Any:
    proposer = GraphNodeSpec(
        name="human_in_loop_proposer",
        kind="llm",
        role=RoleConfig(
            instruction="Propose a clear, actionable solution for the user's request."
        ),
    )
    completer = GraphNodeSpec(
        name="human_in_loop_completer",
        kind="llm",
        role=RoleConfig(
            instruction=(
                "Complete the user-approved action only after the approval "
                "tool has returned confirmed. If approval is pending or "
                "rejected, do not invoke any state-changing tool; explain "
                "that the action was not authorized."
            )
        ),
    )
    return spec_sequence([proposer, completer])


def _plan_spec() -> Any:
    planner = GraphNodeSpec(
        name="planner_agent",
        kind="llm",
        role=RoleConfig(
            instruction="Create a step-by-step plan to address the request."
        ),
    )
    executor = GraphNodeSpec(
        name="executor_agent",
        kind="llm",
        role=RoleConfig(instruction="Execute the plan step by step."),
    )
    return spec_sequence([planner, executor])


CASES = [
    ("assistant", {}, spec_single("direct_agent"), "direct_agent"),
    ("pipeline", {"extra_config": {"steps": 2}}, _pipeline_spec(), "sequential_agent"),
    ("multi_perspective", {}, _multi_perspective_spec(), "multi_perspective_agent"),
    ("refine_until_good", {}, _refine_spec(), "evaluator_optimizer_agent"),
    ("approval_gate", {}, _approval_spec(), "human_in_loop_agent"),
    ("plan_and_execute", {}, _plan_spec(), "plan_execute_agent"),
]


@pytest.mark.parametrize(
    ("key", "runtime_overrides", "preset_spec", "root_name"),
    CASES,
    ids=[case[0] for case in CASES],
)
def test_legacy_compiled_preset_matches_strategy_parity(
    key, runtime_overrides, preset_spec, root_name
):
    """Golden (current strategy tree) ≡ legacy-compiled preset spec."""
    registry = get_default_registry()
    golden = registry.get(key).build(make_runtime(**runtime_overrides))
    compiled = compile_legacy(
        preset_spec, make_runtime(**runtime_overrides), name=root_name
    )

    assert describe(compiled) == describe(golden), (
        f"legacy-compiled preset for {key!r} diverges from the strategy tree"
    )


def test_parity_comparator_detects_divergence():
    """The comparator must catch a structural difference, not pass vacuously."""
    good = spec_sequence(
        [
            GraphNodeSpec(name="sequential_step_0", kind="llm"),
            GraphNodeSpec(name="sequential_step_1", kind="llm"),
        ]
    )
    compiled = compile_legacy(good, make_runtime(), name="sequential_agent")
    golden = SequentialAgent(
        name="sequential_agent",
        description="parity test agent",
        sub_agents=[
            LlmAgent(
                name="sequential_step_0",
                model=DeterministicLlm(model="deterministic"),
                instruction="Runtime policy: follow the operator's task.",
            )
        ],
    )
    assert describe(compiled) != describe(golden)
