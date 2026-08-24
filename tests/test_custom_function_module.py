"""G01 — custom graph-function modules are reachable from config.

``AGENT_FUNCTION_MODULE`` (allowlisted in production via
``AGENT_FUNCTION_MODULE_ALLOWLIST``) registers ``options.function``
implementations without editing ``compile/workflow.py``. Unit tests cover
the loader contract; the end-to-end test goes through
``agent._build_root_agent`` (the served entrypoint), NOT ``compile_graph``
directly — mirroring the R06 rule in ``test_served_graph_config.py``.
"""

from __future__ import annotations

import asyncio
import sys

import pytest
from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_response import LlmResponse
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.workflow import Workflow
from google.genai import types

from basic_agent import agent as agent_module
from basic_agent.agent import resolve_agent_config
from basic_agent.compile.functions import (
    _RESERVED_FUNCTION_NAMES,
    CUSTOM_FUNCTION_ALLOWLIST_ENV,
    CUSTOM_FUNCTION_MODULE_ENV,
    check_custom_function_error,
    custom_function_registry,
    load_custom_functions,
)
from basic_agent.compile.workflow import DEFAULT_FUNCTION_REGISTRY

USER_ID = "g01-user"

CUSTOM_FUNCTIONS_MODULE_SOURCE = """
def enrich_state(ctx, node_input=None):
    summary = ctx.state.get("request_summary", "")
    ctx.state["enriched"] = f"enriched:{summary}"


def pretend_builtin(ctx, node_input=None):
    ctx.state["shadowed"] = True


FUNCTIONS = {"enrich_state": enrich_state, "route_dispatch": pretend_builtin}
"""

BAD_NO_FUNCTIONS_SOURCE = "SOMETHING_ELSE = 1\n"

BAD_NOT_CALLABLE_SOURCE = "FUNCTIONS = {'broken': 42}\n"

GRAPH_WITH_CUSTOM_FUNCTION_YAML = """
agent:
  use_case: assistant
model:
  provider: google
  name: gemini-3.6-flash
tools:
  enabled: []
graph:
  nodes:
    - name: intake
      kind: llm
      role:
        instruction: Summarize the request.
      output_key: request_summary
      options:
        no_state_schema: true
    - name: enrich
      kind: function
      options:
        function: enrich_state
    - name: finalize
      kind: llm
      role:
        instruction: Produce the final answer.
  edges:
    - from: START
      to: intake
    - from: intake
      to: enrich
    - from: enrich
      to: finalize
"""


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


@pytest.fixture
def fake_model(monkeypatch):
    model = DeterministicLlm(model="deterministic")
    monkeypatch.setattr(agent_module, "resolve_model", lambda *args, **kwargs: model)
    return model


@pytest.fixture
def functions_module(tmp_path):
    module_file = tmp_path / "custom_functions.py"
    module_file.write_text(CUSTOM_FUNCTIONS_MODULE_SOURCE, encoding="utf-8")
    return module_file


def test_load_custom_functions_registers_new_names(functions_module):
    functions: dict = {**DEFAULT_FUNCTION_REGISTRY}
    registered = load_custom_functions(str(functions_module), functions=functions)

    assert registered == ["enrich_state"]
    assert functions["route_dispatch"] is DEFAULT_FUNCTION_REGISTRY["route_dispatch"]
    assert callable(functions["enrich_state"])


def test_builtins_are_never_shadowed_even_with_empty_seed(functions_module):
    """H02: the shadow guard is in load_custom_functions itself."""
    registered = load_custom_functions(str(functions_module), functions={})

    assert "route_dispatch" not in registered
    assert "enrich_state" in registered


def test_plan_execute_is_reserved(functions_module, tmp_path):
    """H01: plan_execute can't be overridden by a custom module."""
    source = 'def plan_execute(ctx, node_input=None): pass\nFUNCTIONS = {"plan_execute": plan_execute}\n'
    module_file = tmp_path / "plan_override.py"
    module_file.write_text(source, encoding="utf-8")
    registered = load_custom_functions(str(module_file), functions={})

    assert "plan_execute" not in registered
    assert "plan_execute" in _RESERVED_FUNCTION_NAMES


def test_production_requires_allowlist(monkeypatch, tmp_path, functions_module):
    monkeypatch.delenv(CUSTOM_FUNCTION_ALLOWLIST_ENV, raising=False)
    monkeypatch.setenv("DEPLOYMENT_ENV", "production")

    with pytest.raises(ValueError, match=CUSTOM_FUNCTION_ALLOWLIST_ENV):
        load_custom_functions(str(functions_module), functions={})

    allowed_dir = tmp_path / "allowed"
    allowed_dir.mkdir()
    monkeypatch.setenv(CUSTOM_FUNCTION_ALLOWLIST_ENV, str(allowed_dir))
    with pytest.raises(ValueError, match="outside the configured"):
        load_custom_functions(str(functions_module), functions={})

    monkeypatch.setenv(CUSTOM_FUNCTION_ALLOWLIST_ENV, str(tmp_path))
    assert load_custom_functions(str(functions_module), functions={}) == [
        "enrich_state",
    ]


def test_unrecognized_deployment_env_requires_allowlist(
    monkeypatch, tmp_path, functions_module
):
    """H09: fail closed on unrecognized and unset DEPLOYMENT_ENV values."""
    monkeypatch.delenv(CUSTOM_FUNCTION_ALLOWLIST_ENV, raising=False)

    # Unrecognized value requires allowlist.
    monkeypatch.setenv("DEPLOYMENT_ENV", "prod-us")
    with pytest.raises(ValueError, match=CUSTOM_FUNCTION_ALLOWLIST_ENV):
        load_custom_functions(str(functions_module), functions={})

    # H09: unset DEPLOYMENT_ENV also requires allowlist.
    monkeypatch.delenv("DEPLOYMENT_ENV", raising=False)
    with pytest.raises(ValueError, match=CUSTOM_FUNCTION_ALLOWLIST_ENV):
        load_custom_functions(str(functions_module), functions={})

    # Known non-production values still skip the allowlist.
    monkeypatch.setenv("DEPLOYMENT_ENV", "docker-compose")
    assert "enrich_state" in load_custom_functions(str(functions_module), functions={})


def test_missing_functions_dict_is_rejected(tmp_path):
    module_file = tmp_path / "no_functions.py"
    module_file.write_text(BAD_NO_FUNCTIONS_SOURCE, encoding="utf-8")
    with pytest.raises(ValueError, match="FUNCTIONS dict"):
        load_custom_functions(str(module_file), functions={})


def test_non_callable_entry_is_rejected(tmp_path):
    module_file = tmp_path / "not_callable.py"
    module_file.write_text(BAD_NOT_CALLABLE_SOURCE, encoding="utf-8")
    with pytest.raises(ValueError, match="must be callables"):
        load_custom_functions(str(module_file), functions={})


def test_broken_module_does_not_crash_unused_preset(monkeypatch, tmp_path):
    """H03: a bad AGENT_FUNCTION_MODULE warns but doesn't crash presets."""
    bad_module = tmp_path / "broken.py"
    bad_module.write_text("raise RuntimeError('boom')\n", encoding="utf-8")
    monkeypatch.setenv(CUSTOM_FUNCTION_MODULE_ENV, str(bad_module))

    registry = custom_function_registry()
    assert registry == DEFAULT_FUNCTION_REGISTRY


def test_broken_module_surfaces_error_for_custom_function(monkeypatch, tmp_path):
    """H17: a broken module's original error surfaces when a graph needs it."""
    bad_module = tmp_path / "broken_for_custom.py"
    bad_module.write_text("raise RuntimeError('module is broken')\n", encoding="utf-8")
    monkeypatch.setenv(CUSTOM_FUNCTION_MODULE_ENV, str(bad_module))

    registry = custom_function_registry()
    with pytest.raises(ValueError, match="failed to load"):
        check_custom_function_error("my_custom_fn", registry)


def test_unrelated_compile_unaffected_by_prior_broken_load(monkeypatch, tmp_path):
    """H18: a broken module's error doesn't leak into unrelated registries."""
    bad_module = tmp_path / "broken_leak.py"
    bad_module.write_text("raise RuntimeError('leak test')\n", encoding="utf-8")
    monkeypatch.setenv(CUSTOM_FUNCTION_MODULE_ENV, str(bad_module))

    # First call: broken module attaches _load_error to this registry.
    broken_registry = custom_function_registry()
    assert getattr(broken_registry, "_load_error", None) is not None

    # Second call: no AGENT_FUNCTION_MODULE → clean registry, no error.
    monkeypatch.delenv(CUSTOM_FUNCTION_MODULE_ENV, raising=False)
    clean_registry = custom_function_registry()
    assert getattr(clean_registry, "_load_error", None) is None

    # check_custom_function_error on the clean registry does NOT raise.
    check_custom_function_error("any_function", clean_registry)


def test_sys_modules_cleaned_on_import_failure(monkeypatch, tmp_path):
    """H08: a broken module leaves no sys.modules entry behind."""
    bad_module = tmp_path / "broken_import.py"
    bad_module.write_text("raise ImportError('test failure')\n", encoding="utf-8")

    import uuid
    from pathlib import Path

    resolved = Path(str(bad_module)).expanduser().resolve()
    expected_name = (
        f"custom_graph_functions_{uuid.uuid5(uuid.NAMESPACE_URL, str(resolved)).hex}"
    )

    before = set(sys.modules)
    with pytest.raises(ImportError, match="test failure"):
        load_custom_functions(str(bad_module), functions={})
    after_new = set(sys.modules) - before

    assert expected_name not in after_new, (
        f"broken module left {expected_name!r} in sys.modules"
    )


def test_served_graph_resolves_custom_function_node(
    tmp_path, monkeypatch, functions_module, write_config
):
    """A non-built-in options.function name compiles through the served root."""
    write_config(GRAPH_WITH_CUSTOM_FUNCTION_YAML)
    monkeypatch.setenv(CUSTOM_FUNCTION_MODULE_ENV, str(functions_module))

    config = resolve_agent_config()
    root = agent_module._build_root_agent(config, "yaml")

    assert isinstance(root, Workflow)
    enrich = next(n for n in root.graph.nodes if n.name == "enrich")
    assert enrich._func.__name__ == "enrich_state"
    assert enrich._func.__module__.startswith("custom_graph_functions_")


def test_served_graph_runs_custom_function_end_to_end(
    tmp_path, monkeypatch, functions_module, fake_model, write_config
):
    """The custom function executes inside the served workflow and writes state."""

    async def _run():
        session_service = InMemorySessionService()
        await session_service.create_session(
            app_name="g01-tests", user_id=USER_ID, session_id="s1"
        )
        runner = Runner(
            app_name="g01-tests",
            node=agent_module._build_root_agent(config, "yaml"),
            session_service=session_service,
        )
        return [
            event
            async for event in runner.run_async(
                user_id=USER_ID,
                session_id="s1",
                new_message=types.Content(
                    role="user", parts=[types.Part(text="Do the thing.")]
                ),
            )
        ]

    write_config(GRAPH_WITH_CUSTOM_FUNCTION_YAML)
    monkeypatch.setenv(CUSTOM_FUNCTION_MODULE_ENV, str(functions_module))
    config = resolve_agent_config()

    events = asyncio.run(_run())
    authors = {e.author for e in events}
    state = {}
    for event in events:
        if event.actions and event.actions.state_delta:
            state.update(event.actions.state_delta)

    assert {"intake", "finalize"} <= authors
    assert state["enriched"] == "enriched:deterministic response 1"
    assert state["last_response"] == "deterministic response 2"


def test_no_env_var_leaves_only_builtins(monkeypatch):
    monkeypatch.delenv(CUSTOM_FUNCTION_MODULE_ENV, raising=False)
    assert custom_function_registry() == DEFAULT_FUNCTION_REGISTRY


def test_registry_reads_env_on_every_call(monkeypatch, functions_module):
    """H06: changing AGENT_FUNCTION_MODULE between calls is reflected."""
    monkeypatch.delenv(CUSTOM_FUNCTION_MODULE_ENV, raising=False)
    reg1 = custom_function_registry()
    assert "enrich_state" not in reg1

    monkeypatch.setenv(CUSTOM_FUNCTION_MODULE_ENV, str(functions_module))
    reg2 = custom_function_registry()
    assert "enrich_state" in reg2
