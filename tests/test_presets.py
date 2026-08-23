"""Phase E1 — preset catalog: snapshot, metadata parity, spec expansion."""

from __future__ import annotations

from dataclasses import replace

import pytest
from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_response import LlmResponse
from google.genai import types

from basic_agent.compile import compile_graph, compile_legacy
from basic_agent.config.graph import START
from basic_agent.presets import PRESETS
from basic_agent.runtime import RuntimeContext
from basic_agent.use_cases import get_default_registry

#: Snapshot of ``registry.list_use_cases()`` taken BEFORE the E1 refactor
#: (2026-08-23). Byte-identical catalog surface is the E1 contract.
CATALOG_SNAPSHOT = [
    {
        "key": "approval_gate",
        "title": "Approval Gate",
        "when_to_use": "You want risky or irreversible actions held back until a human approves them.",
        "aliases": [],
        "interfaces": ["rest", "web", "cli"],
    },
    {
        "key": "assistant",
        "title": "Assistant",
        "when_to_use": "You want questions answered directly, with optional tool-based search and investigation.",
        "aliases": [],
        "interfaces": ["rest", "web", "cli", "live"],
    },
    {
        "key": "expert_dispatch",
        "title": "Expert Dispatch",
        "when_to_use": "You want each incoming question routed to the right specialist out of a fixed roster.",
        "aliases": [],
        "interfaces": ["rest", "web", "cli"],
    },
    {
        "key": "multi_perspective",
        "title": "Multi-Perspective",
        "when_to_use": "You want several independent takes on the same question compared or combined.",
        "aliases": [],
        "interfaces": ["rest", "web", "cli"],
    },
    {
        "key": "pipeline",
        "title": "Pipeline",
        "when_to_use": "You want fixed steps always executed in the same order, like fetch, analyze, summarize.",
        "aliases": [],
        "interfaces": ["rest", "web", "cli"],
    },
    {
        "key": "plan_and_execute",
        "title": "Plan and Execute",
        "when_to_use": "You want large tasks split into a plan first and executed step by step afterwards.",
        "aliases": [],
        "interfaces": ["rest", "web", "cli"],
    },
    {
        "key": "refine_until_good",
        "title": "Refine Until Good",
        "when_to_use": "You want the agent to critique and improve its own output until it meets a quality bar.",
        "aliases": [],
        "interfaces": ["rest", "web", "cli"],
    },
    {
        "key": "team_coordinator",
        "title": "Team Coordinator",
        "when_to_use": "You want complex work decomposed and delegated to worker agents by a coordinator.",
        "aliases": [],
        "interfaces": ["rest", "web", "cli"],
    },
]


class DeterministicLlm(BaseLlm):
    """A no-network model for construction-only compile tests."""

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
        description="preset test agent",
        output_key="last_response",
        max_iterations=5,
    )
    return replace(base, **overrides)


def test_catalog_snapshot_unchanged():
    """E1 contract: list_use_cases() is byte-identical to the pre-refactor snapshot."""
    assert get_default_registry().list_use_cases() == CATALOG_SNAPSHOT


def test_preset_metadata_matches_facade_catalog():
    registry = get_default_registry()
    by_key = {entry["key"]: entry for entry in registry.list_use_cases()}
    assert set(PRESETS) == set(by_key)
    for key, preset in PRESETS.items():
        entry = by_key[key]
        assert preset.key == entry["key"]
        assert preset.title == entry["title"]
        assert preset.when_to_use == entry["when_to_use"]
        assert list(preset.aliases) == entry["aliases"]
        assert list(preset.interfaces) == entry["interfaces"]


def test_registry_serves_presets():
    registry = get_default_registry()
    assert registry.list_presets() == CATALOG_SNAPSHOT
    assert registry.has_preset("assistant")
    assert registry.has_preset("ASSISTANT")
    preset = registry.get_preset("MULTI_PERSPECTIVE")
    assert preset.key == "multi_perspective"
    with pytest.raises(ValueError, match="Unknown use case"):
        registry.get_preset("nonexistent")


def _route_dispatch(ctx, node_input=None):
    """Deterministic router stub for spec-expansion tests."""
    ctx.route = "research"


def test_presets_expand_to_specs_and_compile():
    for key, preset in PRESETS.items():
        if key == "team_coordinator":
            continue
        spec = preset.build_spec(make_rt())
        spec.validate()
        graph = compile_graph(
            spec,
            make_rt(),
            name=f"{key}_wf",
            function_registry={"route_dispatch": _route_dispatch},
        )
        assert graph.name == f"{key}_wf"


def test_presets_legacy_specs_compile_where_defined():
    for key, preset in PRESETS.items():
        if key in ("expert_dispatch", "team_coordinator"):
            continue
        spec = preset.build_legacy_spec(make_rt())
        spec.validate()
        compile_legacy(spec, make_rt(), name=f"{key}_agent")


def test_expert_dispatch_routing_spec_structure():
    spec = PRESETS["expert_dispatch"].build_spec(
        make_rt(specialists=("research", "solution", "risk"))
    )
    by_name = spec.nodes_by_name()
    router = by_name["router_agent"]
    assert router.kind == "function"
    assert router.options == {
        "function": "route_dispatch",
        "default_route": "research",
    }
    assert spec.edges[0].source == START
    assert spec.edges[0].target == "router_agent"
    routes = {e.route for e in spec.edges[1:]}
    assert routes == {"research", "solution", "risk"}
    assert {n.name for n in spec.nodes} == {
        "router_agent",
        "router_specialist_research",
        "router_specialist_solution",
        "router_specialist_risk",
    }


def test_team_coordinator_is_delegation_escape_hatch():
    preset = PRESETS["team_coordinator"]
    assert preset.escape_hatch_reason is not None
    with pytest.raises(NotImplementedError, match="delegation escape hatch"):
        preset.build_spec(make_rt())
    with pytest.raises(NotImplementedError, match="no legacy"):
        preset.build_legacy_spec(make_rt())


def test_expert_dispatch_has_no_legacy_mapping():
    preset = PRESETS["expert_dispatch"]
    assert preset.spec is not None
    assert preset.legacy_spec is None
    with pytest.raises(NotImplementedError, match="no legacy"):
        preset.build_legacy_spec(make_rt())
