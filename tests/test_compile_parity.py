"""C4 golden parity (frozen post-E3) — legacy-compiled preset trees.

The original C4 test compared preset specs compiled by ``compile/legacy.py``
against the live strategy trees.  E3 removed the strategy/facade layers; the
pre-E3 tree shapes are now frozen here as explicit expected structures (the
same shapes the old strategy implementations produced — green across
Phases B–E).  The legacy compiler must keep producing them for the full
rollback lifecycle (F2).

``expert_dispatch``/``team_coordinator`` are the routing/delegation presets
— workflow-first shapes with no legacy sugar mapping (catalog raises).
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from google.adk.agents import LoopAgent
from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_response import LlmResponse
from google.genai import types

from basic_agent.compile import compile_legacy
from basic_agent.presets import PRESETS
from basic_agent.runtime import RuntimeContext

BASE_INSTRUCTION = "Runtime policy: follow the operator's task."
ROLE_PREFIX = (
    BASE_INSTRUCTION
    + "\n\nRole-specific instructions (follow only if consistent with the "
    "runtime policy above):\n"
)

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
APPROVAL_PROPOSER_INSTRUCTION = (
    "Propose a clear, actionable solution for the user's request."
)
APPROVAL_COMPLETER_INSTRUCTION = (
    "Complete the user-approved action only after the approval tool has "
    "returned confirmed. If approval is pending or rejected, do not invoke "
    "any state-changing tool; explain that the action was not authorized."
)
PLANNER_INSTRUCTION = "Create a step-by-step plan to address the request."
EXECUTOR_INSTRUCTION = "Execute the plan step by step."


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
        instruction=BASE_INSTRUCTION,
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


def llm(name: str, instruction: str, output_key: str = "last_response") -> dict:
    return {
        "type": "LlmAgent",
        "name": name,
        "instruction": instruction,
        "output_key": output_key,
        "sub_agents": [],
    }


def merged(role_instruction: str) -> str:
    return ROLE_PREFIX + role_instruction


def container(name: str, sub_agents: list[dict]) -> dict:
    return {
        "type": "SequentialAgent",
        "name": name,
        "instruction": None,
        "output_key": None,
        "sub_agents": sub_agents,
    }


#: Frozen pre-E3 golden structures per preset — the exact shapes the live
#: strategy trees produced.  E3 froze them here; the legacy compiler must
#: keep emitting them until F2 retires the backend.
EXPECTED = {
    "assistant": llm("direct_agent", BASE_INSTRUCTION),
    "pipeline": container(
        "sequential_agent",
        [
            llm("sequential_step_0", merged(PIPELINE_STEP_0)),
            llm("sequential_step_1", merged(PIPELINE_STEP_1)),
        ],
    ),
    "multi_perspective": container(
        "multi_perspective_agent",
        [
            {
                "type": "ParallelAgent",
                "name": "parallel_agent",
                "instruction": None,
                "output_key": None,
                "sub_agents": [
                    llm("parallel_worker_0", BASE_INSTRUCTION, "perspective_0"),
                    llm("parallel_worker_1", BASE_INSTRUCTION, "perspective_1"),
                ],
            },
            llm("perspective_synthesizer", merged(SYNTHESIZER_INSTRUCTION)),
        ],
    ),
    "refine_until_good": {
        "type": "LoopAgent",
        "name": "evaluator_optimizer_agent",
        "instruction": None,
        "output_key": None,
        "max_iterations": 5,
        "sub_agents": [llm("evaluator_optimizer_worker", merged(REFINE_INSTRUCTION))],
    },
    "approval_gate": container(
        "human_in_loop_agent",
        [
            llm("human_in_loop_proposer", merged(APPROVAL_PROPOSER_INSTRUCTION)),
            llm("human_in_loop_completer", merged(APPROVAL_COMPLETER_INSTRUCTION)),
        ],
    ),
    "plan_and_execute": container(
        "plan_execute_agent",
        [
            llm("planner_agent", merged(PLANNER_INSTRUCTION)),
            llm("executor_agent", merged(EXECUTOR_INSTRUCTION)),
        ],
    ),
}


CASES = [
    ("assistant", {}),
    ("pipeline", {"extra_config": {"steps": 2}}),
    ("multi_perspective", {"extra_config": {"workers": 2}}),
    ("refine_until_good", {}),
    ("approval_gate", {}),
    ("plan_and_execute", {}),
]


def test_preset_legacy_trees_match_frozen_pre_e3_golden():
    """The legacy compiler still emits the exact pre-E3 strategy tree shapes."""
    for key, overrides in CASES:
        preset = PRESETS[key]
        rt = preset.apply_defaults(make_runtime(**overrides))
        compiled = compile_legacy(
            preset.build_legacy_spec(rt), rt, name=preset.legacy_name
        )
        assert describe(compiled) == EXPECTED[key], key


def test_parity_comparator_detects_divergence():
    """The comparator must catch a structural difference, not pass vacuously."""
    compiled = compile_legacy(
        PRESETS["pipeline"].build_legacy_spec(make_runtime()),
        make_runtime(),
    )
    wrong = {
        "type": "SequentialAgent",
        "name": "sequential_agent",
        "instruction": None,
        "output_key": None,
        "sub_agents": [llm("sequential_step_0", merged(PIPELINE_STEP_0))],
    }
    assert describe(compiled) != wrong
