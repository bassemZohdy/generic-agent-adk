"""Tests for the public use-case layer (presets, E3+).

The per-use-case facade classes and the strategy layer were removed in E3;
the registry serves ADR-005 presets and the custom-module surface is a
``PRESETS`` dict of :class:`basic_agent.presets.Preset`.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from google.adk.agents import LlmAgent

from basic_agent.runtime import RuntimeContext
from basic_agent.use_cases import (
    UseCaseRegistry,
    get_default_registry,
    load_custom_use_cases,
)

MINIMAL_RUNTIME = RuntimeContext(
    model="gemini-2.0-flash", instruction="test", tools=[], description="test"
)

ALL_KEYS = [
    "assistant",
    "pipeline",
    "multi_perspective",
    "refine_until_good",
    "expert_dispatch",
    "team_coordinator",
    "plan_and_execute",
    "approval_gate",
]


def walk(root):
    """Yield every agent in the tree, root first."""
    yield root
    for child in getattr(root, "sub_agents", None) or []:
        yield from walk(child)


# --- T2.2: all eight built-ins build with a minimal runtime ---


@pytest.mark.parametrize("key", ALL_KEYS)
def test_all_builtins_build(key):
    root = get_default_registry().get(key).build(MINIMAL_RUNTIME)
    assert root is not None
    assert list(walk(root))


# --- defaults application (old resolve_runtime rules) ---


def test_preset_defaults_apply():
    registry = get_default_registry()
    assert (
        registry.get("approval_gate").apply_defaults(MINIMAL_RUNTIME).require_approval
        is True
    )
    assert registry.get("expert_dispatch").apply_defaults(
        MINIMAL_RUNTIME
    ).specialists == (
        "research",
        "solution",
        "risk",
    )
    assert (
        registry.get("refine_until_good").apply_defaults(MINIMAL_RUNTIME).max_iterations
        == 5
    )


def test_caller_value_not_overridden():
    rt = MINIMAL_RUNTIME
    rt.max_iterations = 2
    assert (
        get_default_registry()
        .get("refine_until_good")
        .apply_defaults(rt)
        .max_iterations
        == 2
    )


def test_defaults_do_not_mutate_caller():
    resolved = (
        get_default_registry().get("approval_gate").apply_defaults(MINIMAL_RUNTIME)
    )
    assert resolved is not MINIMAL_RUNTIME
    assert MINIMAL_RUNTIME.require_approval is False


# --- custom hook surface (old BaseUseCaseAgent equivalents) ---


def test_before_tool_hook_attached_to_every_llm_agent():
    from basic_agent.policies.approval import iter_llm_agents
    from basic_agent.presets.catalog import _chain_before_tool

    calls = []

    def hook(tool, args, tool_context):
        calls.append(getattr(tool, "name", tool))

    agent = LlmAgent(name="worker", model="gemini-2.0-flash", instruction="x")
    agent.before_tool_callback = _chain_before_tool(None, hook)
    agent.before_tool_callback(
        SimpleNamespace(name="web_search"), {}, SimpleNamespace()
    )
    assert calls == ["web_search"]
    # The graph-aware walker sees LlmAgents inside the workflow too.
    assert list(iter_llm_agents(agent)) == [agent]


# --- registry contract ---


def test_canonical_key_resolution():
    registry = get_default_registry()
    assert registry.get("expert_dispatch").key == "expert_dispatch"
    assert registry.get("approval_gate").key == "approval_gate"
    assert registry.get("plan_and_execute").key == "plan_and_execute"


def test_resolve_returns_canonical_key():
    canonical, preset = get_default_registry().resolve("expert_dispatch")
    assert canonical == "expert_dispatch"
    assert preset.key == canonical


def test_unknown_key_lists_valid_keys():
    with pytest.raises(ValueError, match="expert_dispatch"):
        get_default_registry().get("nonexistent")
    try:
        get_default_registry().get("bogus")
    except ValueError as exc:
        for key in ALL_KEYS:
            assert key in str(exc)


def test_list_use_cases_catalog():
    entries = get_default_registry().list_use_cases()
    assert len(entries) == 8
    keys = [e["key"] for e in entries]
    assert keys == sorted(keys)
    for entry in entries:
        assert entry["title"]
        assert entry["when_to_use"]
        assert isinstance(entry["aliases"], list)
        assert entry["aliases"] == []
        assert {"rest", "web", "cli"} <= set(entry["interfaces"])
    by_key = {e["key"]: e for e in entries}
    assert "live" in by_key["assistant"]["interfaces"]
    assert "live" not in by_key["pipeline"]["interfaces"]


def test_registry_has():
    registry = get_default_registry()
    assert registry.has("assistant")
    assert registry.has("ASSISTANT")
    assert not registry.has("nope")


# --- custom module loading (PRESETS surface) ---


CUSTOM_MODULE_SOURCE = """
from basic_agent.presets import PRESETS, Preset
from basic_agent.config.graph import GraphNodeSpec, GraphSpec, GraphEdgeSpec, START
from basic_agent.config.sugar import SequenceSugar, expand_sugar


def _snarky_spec(rt):
    return expand_sugar(
        SequenceSugar(items=["snarky_direct"]),
        {"snarky_direct": GraphNodeSpec(name="snarky_direct", kind="llm")},
    )


SNARKY = Preset(
    key="snarky",
    title="Snarky",
    when_to_use="Test-only use case.",
    spec=_snarky_spec,
)

PRESETS = {"snarky": SNARKY}
"""

LEGACY_CUSTOM_MODULE_SOURCE = """
class OldStyleAgent:
    use_case = "old_style"
"""


def test_load_custom_presets(tmp_path):
    module_file = tmp_path / "custom_presets.py"
    module_file.write_text(CUSTOM_MODULE_SOURCE)

    import basic_agent.use_cases.registry as registry_mod

    registry = UseCaseRegistry()
    registry_mod._register_builtins(registry)
    keys = load_custom_use_cases(str(module_file), registry=registry)
    assert keys == ["snarky"]
    assert registry.has("snarky")
    assert registry.get("snarky").title == "Snarky"


def test_fresh_registry_registers_builtins_only():
    import basic_agent.use_cases.registry as registry_mod

    fresh = UseCaseRegistry()
    registry_mod._register_builtins(fresh)
    assert len(fresh.list_use_cases()) == 8


def test_production_requires_allowlist(monkeypatch, tmp_path):
    import basic_agent.use_cases.registry as registry_mod

    module_file = tmp_path / "custom_presets.py"
    module_file.write_text(CUSTOM_MODULE_SOURCE)
    monkeypatch.delenv("AGENT_USE_CASE_MODULE_ALLOWLIST", raising=False)
    monkeypatch.setenv("DEPLOYMENT_ENV", "production")

    registry = UseCaseRegistry()
    registry_mod._register_builtins(registry)
    with pytest.raises(ValueError, match="AGENT_USE_CASE_MODULE_ALLOWLIST"):
        load_custom_use_cases(str(module_file), registry=registry)
    allowed_dir = tmp_path / "allowed"
    allowed_dir.mkdir()
    monkeypatch.setenv("AGENT_USE_CASE_MODULE_ALLOWLIST", str(allowed_dir))
    with pytest.raises(ValueError, match="outside the configured"):
        load_custom_use_cases(str(module_file), registry=registry)
    monkeypatch.setenv("AGENT_USE_CASE_MODULE_ALLOWLIST", str(tmp_path))
    assert load_custom_use_cases(str(module_file), registry=registry) == ["snarky"]


def test_legacy_custom_modules_rejected_with_guidance(tmp_path):
    module_file = tmp_path / "legacy_custom.py"
    module_file.write_text(LEGACY_CUSTOM_MODULE_SOURCE)
    with pytest.raises(ValueError, match="BaseUseCaseAgent-style"):
        load_custom_use_cases(str(module_file))
