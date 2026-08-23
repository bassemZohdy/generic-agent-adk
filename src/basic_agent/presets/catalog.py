"""Built-in presets — metadata + graph-spec builders (ADR-005 §5; TODO E1).

A preset is a named partial config: catalog metadata (key, title,
when_to_use, aliases, interfaces — **identical to the current facades**, pinned
by the snapshot test) plus spec builders that expand into the graph specs the
C3 compilers consume.  The E2 classification per ADR-005 §5:

- assistant → single llm node
- pipeline → sequence sugar (per-step "step N of count" defaults + roles.step_{i})
- multi_perspective → parallel + synthesis policy (workflow: with_synthesis;
  legacy: nested parallel + trailing step)
- refine_until_good → loop sugar (default max_iterations 5 via defaults)
- approval_gate → propose/complete sequence + approval policy
- plan_and_execute → two-role sequence (dynamic-planning preset on the
  workflow backend arrives with E2)
- expert_dispatch → routing-node graph (route emission + DEFAULT_ROUTE)
- team_coordinator → delegation escape hatch: NO graph shape (ADR-005 §6);
  its builder raises and ``escape_hatch_reason`` documents the path.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from ..config.graph import (
    START,
    GraphEdgeSpec,
    GraphNodeSpec,
    GraphSpec,
)
from ..config.sugar import LoopSugar, ParallelSugar, SequenceSugar, expand_sugar
from ..policies.synthesis import legacy_multi_perspective_spec, with_synthesis
from ..strategies.base import RoleConfig, RuntimeContext

PIPELINE_STEP_INSTRUCTION = (
    "You are step {index} of {count} in this pipeline. Perform your stage of "
    "the overall task, building on the output of any previous steps, then "
    "hand off your result."
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
EXPERTS_DEFAULT = ("research", "solution", "risk")


@dataclass
class Preset:
    """A named partial config: catalog metadata plus spec builders."""

    key: str
    title: str
    when_to_use: str
    aliases: tuple[str, ...] = ()
    interfaces: tuple[str, ...] = ("rest", "web", "cli")
    defaults: dict = field(default_factory=dict)
    spec: Callable[[RuntimeContext], GraphSpec] | None = None
    legacy_spec: Callable[[RuntimeContext], GraphSpec] | None = None
    escape_hatch_reason: str | None = None

    def build_spec(self, rt: RuntimeContext) -> GraphSpec:
        """Return the workflow-backend spec; raises for escape-hatch presets."""
        if self.spec is not None:
            return self.spec(rt)
        raise NotImplementedError(
            self.escape_hatch_reason or f"preset {self.key!r} has no graph spec yet"
        )

    def build_legacy_spec(self, rt: RuntimeContext) -> GraphSpec:
        """Return the legacy (sugar-subset) spec; raises when unsupported."""
        if self.legacy_spec is not None:
            return self.legacy_spec(rt)
        raise NotImplementedError(
            f"preset {self.key!r} has no legacy (sugar-subset) mapping"
        )


def _assistant_spec(rt: RuntimeContext) -> GraphSpec:
    return expand_sugar(
        SequenceSugar(items=["direct_agent"]),
        {"direct_agent": GraphNodeSpec(name="direct_agent", kind="llm")},
    )


def _pipeline_spec(rt: RuntimeContext) -> GraphSpec:
    count = int((rt.extra_config or {}).get("steps", 2))
    roles = rt.roles or {}
    nodes = []
    for index in range(count):
        override = roles.get(f"step_{index}", RoleConfig())
        nodes.append(
            GraphNodeSpec(
                name=f"sequential_step_{index}",
                kind="llm",
                role=RoleConfig(
                    instruction=override.instruction
                    or PIPELINE_STEP_INSTRUCTION.format(index=index, count=count),
                    model=override.model,
                    tools=override.tools,
                ),
            )
        )
    return expand_sugar(
        SequenceSugar(items=[node.name for node in nodes]),
        {node.name: node for node in nodes},
    )


def _multi_perspective_spec(rt: RuntimeContext) -> GraphSpec:
    workers = [
        GraphNodeSpec(
            name=f"parallel_worker_{index}",
            kind="llm",
            output_key=f"perspective_{index}",
        )
        for index in range(int((rt.extra_config or {}).get("workers", 2)))
    ]
    parallel = expand_sugar(
        ParallelSugar(items=[node.name for node in workers]),
        {node.name: node for node in workers},
    )
    return with_synthesis(parallel)


def _multi_perspective_legacy(rt: RuntimeContext) -> GraphSpec:
    count = int((rt.extra_config or {}).get("workers", 2))
    return legacy_multi_perspective_spec(
        [f"parallel_worker_{index}" for index in range(count)]
    )


def _refine_spec(rt: RuntimeContext) -> GraphSpec:
    body = GraphNodeSpec(
        name="evaluator_optimizer_worker",
        kind="llm",
        role=RoleConfig(instruction=REFINE_INSTRUCTION),
    )
    return expand_sugar(
        LoopSugar(body=body.name, max_iterations=rt.max_iterations),
        {body.name: body},
    )


def _approval_gate_spec(rt: RuntimeContext) -> GraphSpec:
    proposer = GraphNodeSpec(
        name="human_in_loop_proposer",
        kind="llm",
        role=RoleConfig(instruction=APPROVAL_PROPOSER_INSTRUCTION),
    )
    completer = GraphNodeSpec(
        name="human_in_loop_completer",
        kind="llm",
        role=RoleConfig(instruction=APPROVAL_COMPLETER_INSTRUCTION),
    )
    return expand_sugar(
        SequenceSugar(items=[proposer.name, completer.name]),
        {proposer.name: proposer, completer.name: completer},
    )


def _plan_execute_spec(rt: RuntimeContext) -> GraphSpec:
    planner = GraphNodeSpec(
        name="planner_agent",
        kind="llm",
        role=RoleConfig(instruction=PLANNER_INSTRUCTION),
    )
    executor = GraphNodeSpec(
        name="executor_agent",
        kind="llm",
        role=RoleConfig(instruction=EXECUTOR_INSTRUCTION),
    )
    return expand_sugar(
        SequenceSugar(items=[planner.name, executor.name]),
        {planner.name: planner, executor.name: executor},
    )


def _expert_dispatch_spec(rt: RuntimeContext) -> GraphSpec:
    """Routing-node graph: a router function emits a specialist route.

    The router's implementation is supplied at compile time via
    ``options.function = 'route_dispatch'`` (function registry); the graph
    edges carry a per-specialist route plus a DEFAULT_ROUTE fallback.
    """
    specialists = list(rt.specialists) or list(EXPERTS_DEFAULT)
    roles = rt.roles or {}
    router = GraphNodeSpec(
        name="router_agent",
        kind="function",
        options={"function": "route_dispatch"},
    )
    specialist_nodes = []
    for name in specialists:
        override = roles.get(name, RoleConfig())
        specialist_nodes.append(
            GraphNodeSpec(
                name=f"router_specialist_{name}",
                kind="llm",
                role=RoleConfig(
                    instruction=override.instruction
                    or f"You are the {name} specialist. Handle requests in your domain.",
                    model=override.model,
                    tools=override.tools,
                ),
            )
        )
    nodes = [router] + specialist_nodes
    edges = [GraphEdgeSpec(source=START, target=router.name)]
    for index, node in enumerate(specialist_nodes):
        edges.append(
            GraphEdgeSpec(
                source=router.name, target=node.name, route=specialists[index]
            )
        )
    spec = GraphSpec(nodes=nodes, edges=edges)
    spec.validate()
    return spec


def _team_coordinator_spec(rt: RuntimeContext) -> GraphSpec:
    raise NotImplementedError(
        "team_coordinator is the delegation escape hatch (ADR-005 §6): "
        "LlmAgent + sub_agents (and/or _TaskAgentTool task delegation) until "
        "upstream #5581 / Node-as-Tool settles; no graph shape is defined."
    )


PRESETS: dict[str, Preset] = {
    preset.key: preset
    for preset in [
        Preset(
            key="assistant",
            title="Assistant",
            when_to_use=(
                "You want questions answered directly, with optional tool-based "
                "search and investigation."
            ),
            interfaces=("rest", "web", "cli", "live"),
            spec=_assistant_spec,
            legacy_spec=_assistant_spec,
        ),
        Preset(
            key="pipeline",
            title="Pipeline",
            when_to_use=(
                "You want fixed steps always executed in the same order, like "
                "fetch, analyze, summarize."
            ),
            spec=_pipeline_spec,
            legacy_spec=_pipeline_spec,
        ),
        Preset(
            key="multi_perspective",
            title="Multi-Perspective",
            when_to_use=(
                "You want several independent takes on the same question "
                "compared or combined."
            ),
            spec=_multi_perspective_spec,
            legacy_spec=_multi_perspective_legacy,
        ),
        Preset(
            key="refine_until_good",
            title="Refine Until Good",
            when_to_use=(
                "You want the agent to critique and improve its own output "
                "until it meets a quality bar."
            ),
            defaults={"max_iterations": 5},
            spec=_refine_spec,
            legacy_spec=_refine_spec,
        ),
        Preset(
            key="expert_dispatch",
            title="Expert Dispatch",
            when_to_use=(
                "You want each incoming question routed to the right "
                "specialist out of a fixed roster."
            ),
            defaults={"specialists": EXPERTS_DEFAULT},
            spec=_expert_dispatch_spec,
        ),
        Preset(
            key="team_coordinator",
            title="Team Coordinator",
            when_to_use=(
                "You want complex work decomposed and delegated to worker "
                "agents by a coordinator."
            ),
            spec=_team_coordinator_spec,
            escape_hatch_reason=(
                "team_coordinator is the delegation escape hatch (ADR-005 §6): "
                "LlmAgent + sub_agents (and/or _TaskAgentTool task delegation) "
                "until upstream #5581 / Node-as-Tool settles."
            ),
        ),
        Preset(
            key="plan_and_execute",
            title="Plan and Execute",
            when_to_use=(
                "You want large tasks split into a plan first and executed "
                "step by step afterwards."
            ),
            spec=_plan_execute_spec,
            legacy_spec=_plan_execute_spec,
        ),
        Preset(
            key="approval_gate",
            title="Approval Gate",
            when_to_use=(
                "You want risky or irreversible actions held back until a "
                "human approves them."
            ),
            defaults={"require_approval": True},
            spec=_approval_gate_spec,
            legacy_spec=_approval_gate_spec,
        ),
    ]
}
