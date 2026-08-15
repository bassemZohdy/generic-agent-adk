"""Tests for the public use-case layer."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from google.adk.agents import LlmAgent, SequentialAgent

from basic_agent.strategies import RuntimeContext
from basic_agent.use_cases import (
    ApprovalGateAgent,
    AssistantAgent,
    ExpertDispatchAgent,
    MultiPerspectiveAgent,
    RefineUntilGoodAgent,
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
    agent = get_default_registry().get(key).build(MINIMAL_RUNTIME)
    assert agent is not None
    assert list(walk(agent))


# --- T2.1: defaults application ---


def test_approval_gate_forces_require_approval():
    resolved = ApprovalGateAgent().resolve_runtime(MINIMAL_RUNTIME)
    assert resolved.require_approval is True


def test_expert_dispatch_forces_specialists():
    resolved = ExpertDispatchAgent().resolve_runtime(MINIMAL_RUNTIME)
    assert resolved.specialists == ("research", "solution", "risk")


def test_refine_until_good_forces_max_iterations():
    resolved = RefineUntilGoodAgent().resolve_runtime(MINIMAL_RUNTIME)
    assert resolved.max_iterations == 5


def test_caller_max_iterations_not_overridden():
    rt = MINIMAL_RUNTIME
    rt.max_iterations = 2
    resolved = RefineUntilGoodAgent().resolve_runtime(rt)
    assert resolved.max_iterations == 2


def test_resolve_runtime_does_not_mutate_caller():
    resolved = ApprovalGateAgent().resolve_runtime(MINIMAL_RUNTIME)
    assert resolved is not MINIMAL_RUNTIME
    assert MINIMAL_RUNTIME.require_approval is False


# --- T2.1: hook wiring ---


def test_before_tool_hook_attached_to_every_llm_agent():
    # approval_gate overrides before_tool; root is a SequentialAgent container.
    root = ApprovalGateAgent().build(MINIMAL_RUNTIME)
    assert isinstance(root, SequentialAgent)
    # Containers have no tool-callback fields; only LlmAgents carry them.
    assert not hasattr(root, "before_tool_callback")
    assert not hasattr(root, "after_tool_callback")
    llm_agents = [n for n in walk(root) if isinstance(n, LlmAgent)]
    assert llm_agents
    for node in llm_agents:
        assert node.before_tool_callback is not None


def test_no_hooks_no_callbacks_beyond_runtime():
    root = AssistantAgent().build(MINIMAL_RUNTIME)
    for node in walk(root):
        assert node.before_agent_callback is None
        assert node.after_agent_callback is None
        if isinstance(node, LlmAgent):
            assert node.before_tool_callback is None
            assert node.after_tool_callback is None


def test_after_run_hook_attached_to_root():
    root = MultiPerspectiveAgent().build(MINIMAL_RUNTIME)
    assert root.after_agent_callback is not None


def test_before_run_chains_with_runtime_callback():
    calls = []

    def runtime_cb(callback_context):
        calls.append("runtime")

    class Hooked(AssistantAgent):
        def before_run(self, callback_context):
            calls.append("hook")

    rt = MINIMAL_RUNTIME
    rt.before_agent_callback = runtime_cb
    root = Hooked().build(rt)
    root.before_agent_callback(SimpleNamespace())
    assert calls == ["runtime", "hook"]
    rt.before_agent_callback = None


# --- T2.2: approval veto ---


class FakeTool(SimpleNamespace):
    pass


def make_tool(name):
    return FakeTool(name=name)


def test_approval_veto_blocks_unapproved():
    ctx = SimpleNamespace(state={})
    result = ApprovalGateAgent().before_tool(
        make_tool("request_approval"), {}, ctx
    )
    assert result == {
        "status": "blocked",
        "reason": "This action requires human approval before execution.",
    }


def test_approval_veto_passes_when_approved():
    ctx = SimpleNamespace(state={"human_approved": True})
    assert ApprovalGateAgent().before_tool(make_tool("request_approval"), {}, ctx) is None


def test_non_gated_tool_passes():
    ctx = SimpleNamespace(state={})
    assert ApprovalGateAgent().before_tool(make_tool("web_search"), {}, ctx) is None


def test_gated_prefix_veto():
    class Gated(ApprovalGateAgent):
        gated_prefixes = ("delete_",)

    ctx = SimpleNamespace(state={})
    assert Gated().before_tool(make_tool("delete_file"), {}, ctx)["status"] == "blocked"


# --- T2.2: perspective aggregation ---


def test_aggregation_collects_perspective_entries():
    state = {"perspective_a": 1, "perspective_b": 2, "other": 3}
    ctx = SimpleNamespace(state=state)
    MultiPerspectiveAgent().after_run(ctx)
    assert state["aggregated_perspectives"] == [1, 2]


def test_aggregation_ignores_non_matching_keys():
    state = {"perspective_a": 1, "other": 2}
    ctx = SimpleNamespace(state=state)
    MultiPerspectiveAgent().after_run(ctx)
    assert state["aggregated_perspectives"] == [1]


# --- T2.3: registry ---


def test_canonical_key_resolution():
    registry = get_default_registry()
    assert registry.get("expert_dispatch").use_case == "expert_dispatch"
    assert registry.get("approval_gate").use_case == "approval_gate"
    assert registry.get("plan_and_execute").use_case == "plan_and_execute"


def test_resolve_returns_canonical_key():
    canonical, instance = get_default_registry().resolve("expert_dispatch")
    assert canonical == "expert_dispatch"
    assert instance.use_case == canonical


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


# --- T2.4: custom module loading ---


CUSTOM_MODULE_SOURCE = '''
from basic_agent.strategies import DirectStrategy
from basic_agent.use_cases import BaseUseCaseAgent


class SnarkyAgent(BaseUseCaseAgent):
    """Custom one-shot agent used only in tests."""

    use_case = "snarky"
    title = "Snarky"
    when_to_use = "Test-only use case."
    aliases = ()
    strategy = DirectStrategy()


class KeylessAgent(BaseUseCaseAgent):
    """Subclass without a use_case key; must be skipped."""
    strategy = DirectStrategy()
'''


def test_load_custom_use_cases(tmp_path):
    module_file = tmp_path / "custom_use_cases.py"
    module_file.write_text(CUSTOM_MODULE_SOURCE)

    keys = load_custom_use_cases(str(module_file))
    assert keys == ["snarky"]

    registry = get_default_registry()
    assert registry.has("snarky")
    built = registry.get("snarky").build(MINIMAL_RUNTIME)
    assert built is not None


def test_load_custom_is_idempotent(tmp_path):
    module_file = tmp_path / "custom_use_cases.py"
    module_file.write_text(CUSTOM_MODULE_SOURCE)
    load_custom_use_cases(str(module_file))
    assert load_custom_use_cases(str(module_file)) == []


def test_env_module_autoregisters(tmp_path, monkeypatch):
    module_file = tmp_path / "env_use_cases.py"
    module_file.write_text(CUSTOM_MODULE_SOURCE)
    monkeypatch.setenv("AGENT_USE_CASE_MODULE", str(module_file))

    import basic_agent.use_cases.registry as registry_mod

    monkeypatch.setattr(registry_mod, "_default_registry", None)
    registry = registry_mod.get_default_registry()
    assert registry.has("snarky")


def test_env_module_unset_keeps_eight(tmp_path, monkeypatch):
    monkeypatch.delenv("AGENT_USE_CASE_MODULE", raising=False)
    fresh = UseCaseRegistry()
    from basic_agent.use_cases import registry as registry_mod

    registry_mod._register_builtins(fresh)
    assert len(fresh.list_use_cases()) == 8
