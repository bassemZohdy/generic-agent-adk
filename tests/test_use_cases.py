"""Tests for the public use-case layer."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from google.adk.agents import LlmAgent, SequentialAgent

from basic_agent.strategies import DirectStrategy, RuntimeContext
from basic_agent.use_cases import (
    ApprovalGateAgent,
    AssistantAgent,
    BaseUseCaseAgent,
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


def test_approval_veto_tolerates_broken_state():
    ctx = SimpleNamespace(state=None)
    assert ApprovalGateAgent().before_tool(make_tool("request_approval"), {}, ctx) is None


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


def test_aggregation_tolerates_broken_state():
    ctx = SimpleNamespace(state=SimpleNamespace())
    MultiPerspectiveAgent().after_run(ctx)  # should not raise


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


# --- T2.5: custom module loading guardrails ---


def test_load_custom_use_cases_missing_file_raises(tmp_path):
    missing = tmp_path / "does_not_exist.py"
    with pytest.raises(OSError, match="does not exist"):
        load_custom_use_cases(str(missing))


def test_load_custom_use_cases_production_requires_allowlist(tmp_path, monkeypatch):
    module_file = tmp_path / "prod_use_cases.py"
    module_file.write_text(CUSTOM_MODULE_SOURCE)
    monkeypatch.delenv("AGENT_USE_CASE_MODULE_ALLOWLIST", raising=False)
    monkeypatch.setenv("DEPLOYMENT_ENV", "production")

    with pytest.raises(ValueError, match="AGENT_USE_CASE_MODULE_ALLOWLIST"):
        load_custom_use_cases(str(module_file), registry=UseCaseRegistry())


def test_load_custom_use_cases_outside_allowlist_rejected(tmp_path, monkeypatch):
    allowed_dir = tmp_path / "allowed"
    allowed_dir.mkdir()
    other_dir = tmp_path / "other"
    other_dir.mkdir()
    module_file = other_dir / "custom_use_cases.py"
    module_file.write_text(CUSTOM_MODULE_SOURCE)
    monkeypatch.setenv("AGENT_USE_CASE_MODULE_ALLOWLIST", str(allowed_dir))
    monkeypatch.delenv("DEPLOYMENT_ENV", raising=False)

    with pytest.raises(ValueError, match="outside the configured"):
        load_custom_use_cases(str(module_file), registry=UseCaseRegistry())


def test_load_custom_use_cases_within_allowlist_allowed(tmp_path, monkeypatch):
    allowed_dir = tmp_path / "allowed"
    allowed_dir.mkdir()
    module_file = allowed_dir / "custom_use_cases.py"
    module_file.write_text(CUSTOM_MODULE_SOURCE)
    monkeypatch.setenv("AGENT_USE_CASE_MODULE_ALLOWLIST", str(allowed_dir))
    monkeypatch.delenv("DEPLOYMENT_ENV", raising=False)

    keys = load_custom_use_cases(str(module_file), registry=UseCaseRegistry())
    assert keys == ["snarky"]


# --- T2.6: registry duplicate-key/alias guardrails ---


def test_register_duplicate_key_raises():
    registry = UseCaseRegistry()
    registry.register(AssistantAgent())
    with pytest.raises(ValueError, match="already registered"):
        registry.register(AssistantAgent())


def test_register_duplicate_alias_raises():
    class FirstAgent(BaseUseCaseAgent):
        use_case = "first_agent"
        title = "First"
        when_to_use = "Test-only."
        aliases = ("shared_alias",)
        strategy = DirectStrategy()

    class SecondAgent(BaseUseCaseAgent):
        use_case = "second_agent"
        title = "Second"
        when_to_use = "Test-only."
        aliases = ("shared_alias",)
        strategy = DirectStrategy()

    registry = UseCaseRegistry()
    registry.register(FirstAgent())
    with pytest.raises(ValueError, match="already registered for"):
        registry.register(SecondAgent())


# --- T2.7: hook-chaining semantics (base._chain / _chain_before_tool / _chain_after_tool) ---


def test_chain_short_circuits_and_always_runs_second():
    from basic_agent.use_cases.base import _chain

    calls = []

    def first_cb(ctx):
        calls.append("first")
        return {"vetoed": True}

    def unreached_cb(ctx):
        calls.append("unreached")
        return None

    def hook(ctx):
        calls.append("hook")
        return None

    chained = _chain([first_cb, unreached_cb], hook)
    result = chained(SimpleNamespace())

    assert calls == ["first", "hook"]
    assert result == {"vetoed": True}


def test_chain_falls_through_to_second_result_when_first_is_none():
    from basic_agent.use_cases.base import _chain

    chained = _chain(None, lambda ctx: "hook-result")
    assert chained(SimpleNamespace()) == "hook-result"


def test_chain_before_tool_veto_short_circuits_second():
    from basic_agent.use_cases.base import _chain_before_tool

    calls = []

    def veto(tool, args, ctx):
        calls.append("veto")
        return {"status": "blocked"}

    def hook(tool, args, ctx):
        calls.append("hook")
        return None

    chained = _chain_before_tool(veto, hook)
    result = chained(None, {}, None)

    assert result == {"status": "blocked"}
    assert calls == ["veto"]


def test_chain_before_tool_falls_through_when_first_is_none():
    from basic_agent.use_cases.base import _chain_before_tool

    chained = _chain_before_tool(None, lambda tool, args, ctx: {"proceed": True})
    assert chained(None, {}, None) == {"proceed": True}


def test_chain_after_tool_prefers_hooks_non_none_result():
    from basic_agent.use_cases.base import _chain_after_tool

    def first(tool, args, ctx, result):
        return {"from": "first"}

    def hook(tool, args, ctx, result):
        return {"from": "hook"}

    chained = _chain_after_tool(first, hook)
    assert chained(None, {}, None, {}) == {"from": "hook"}


def test_chain_after_tool_falls_back_to_first_when_hook_returns_none():
    from basic_agent.use_cases.base import _chain_after_tool

    def first(tool, args, ctx, result):
        return {"from": "first"}

    def hook(tool, args, ctx, result):
        return None

    chained = _chain_after_tool(first, hook)
    assert chained(None, {}, None, {}) == {"from": "first"}


# --- T2.8: after_tool hook wiring end-to-end ---


def test_after_tool_hook_attached_and_invoked():
    class AfterToolAgent(AssistantAgent):
        def after_tool(self, tool, args, tool_context, result):
            return {"wrapped": result}

    root = AfterToolAgent().build(MINIMAL_RUNTIME)
    llm_agents = [n for n in walk(root) if isinstance(n, LlmAgent)]
    assert llm_agents
    for node in llm_agents:
        assert node.after_tool_callback is not None
    result = llm_agents[0].after_tool_callback(None, {}, None, {"original": True})
    assert result == {"wrapped": {"original": True}}


# --- T2.9: resolve_runtime merge/override rules for roles/model/instruction/tools ---


class DefaultsAgent(BaseUseCaseAgent):
    """Custom use case exercising the roles/model/instruction/tools default branches."""

    use_case = "defaults_test"
    title = "Defaults Test"
    when_to_use = "Test-only."
    aliases = ()
    strategy = DirectStrategy()
    defaults = {
        "roles": {"billing": "billing-default"},
        "model": "default-model",
        "instruction": "default instruction",
        "tools": ["default_tool"],
        "description": "default description",
    }


def test_resolve_runtime_merges_roles_caller_entries_win_per_key():
    rt = RuntimeContext(
        model="gemini-2.0-flash",
        instruction="test",
        tools=[],
        description="test",
        roles={"billing": "caller-billing", "technical": "caller-technical"},
    )
    resolved = DefaultsAgent().resolve_runtime(rt)
    assert resolved.roles == {
        "billing": "caller-billing",
        "technical": "caller-technical",
    }


def test_resolve_runtime_keeps_caller_model_instruction_tools_when_set():
    rt = RuntimeContext(
        model="caller-model",
        instruction="caller instruction",
        tools=["caller_tool"],
        description="test",
    )
    resolved = DefaultsAgent().resolve_runtime(rt)
    assert resolved.model == "caller-model"
    assert resolved.instruction == "caller instruction"
    assert resolved.tools == ["caller_tool"]


def test_resolve_runtime_applies_defaults_when_caller_left_them_empty():
    rt = RuntimeContext(model="", instruction="", tools=[], description="test")
    resolved = DefaultsAgent().resolve_runtime(rt)
    assert resolved.model == "default-model"
    assert resolved.instruction == "default instruction"
    assert resolved.tools == ["default_tool"]


def test_resolve_runtime_applies_unconditional_default_for_other_keys():
    # Keys outside the roles/dataclass-default/model-instruction-tools special
    # cases (e.g. "description") apply unconditionally, caller value or not.
    rt = RuntimeContext(model="m", instruction="i", tools=[], description="caller description")
    resolved = DefaultsAgent().resolve_runtime(rt)
    assert resolved.description == "default description"
