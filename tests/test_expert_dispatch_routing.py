"""R07/R12 — expert_dispatch request-dependent routing, fail-fast empty roster.

R07: the preset's router must actually depend on the request.  A classifier
LLM node writes ``routed_to`` and ``default_route_dispatch`` normalizes that
value against the bound routes — proven here by two runs whose event-author
sets differ (two different specialists ran), plus unit tests for the
normalization itself.

R12: an explicitly empty specialists roster must fail fast (loader raise on
``execution.specialists: []``; builder raise when handed ``specialists=()``
directly), while an unset roster still yields the default via
``apply_defaults``.
"""

from __future__ import annotations

import asyncio
from dataclasses import replace
from functools import partial

import pytest
from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_response import LlmResponse
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from basic_agent.compile.workflow import default_route_dispatch
from basic_agent.config.loader import load_config_from_yaml
from basic_agent.presets.catalog import _expert_dispatch_spec
from basic_agent.runtime import RuntimeContext
from basic_agent.use_cases import get_default_registry

APP_NAME = "expert-dispatch-routing"
USER_ID = "routing-user"

EMPTY_SPECIALISTS_YAML = """
agent:
  use_case: expert_dispatch

execution:
  specialists: []
"""


class KeywordRoutingLlm(BaseLlm):
    """Keyword-sensitive fake model for the classifier turn.

    Classifier turns are detected via the strict router instruction in the
    system prompt; the user message keywords then select the emitted
    specialist name.  All other (specialist) turns answer generically.
    """

    calls: int = 0

    @staticmethod
    def _text(text: str) -> LlmResponse:
        return LlmResponse(
            content=types.Content(role="model", parts=[types.Part(text=text)])
        )

    async def generate_content_async(self, llm_request, stream=False):
        self.calls += 1
        prompt = " ".join(
            part.text
            for content in llm_request.contents
            for part in (content.parts or [])
            if getattr(part, "text", None)
        )
        system = llm_request.config.system_instruction or ""
        if "request router" in system:
            for keyword, route in (("risk", "risk"), ("solution", "solution")):
                if keyword in prompt.lower():
                    yield self._text(route)
                    return
            yield self._text("research")
            return
        yield self._text(f"specialist answer {self.calls}")


class FakeCtx:
    """Minimal routing context: dict-like state plus a settable route."""

    def __init__(self, state: dict | None = None):
        self.state: dict = {} if state is None else state
        self.route: str | None = None


def make_rt(**overrides) -> RuntimeContext:
    base = RuntimeContext(
        model=KeywordRoutingLlm(model="keyword-router"),
        instruction="Runtime policy: follow the operator's task.",
        tools=[],
        description="expert dispatch routing test agent",
        output_key="last_response",
        specialists=("research", "solution", "risk"),
    )
    return replace(base, **overrides)


def run_with_message(workflow, session_id: str, message: str) -> set[str]:
    """Run the workflow once; return the set of event authors."""

    async def _run() -> set[str]:
        session_service = InMemorySessionService()
        await session_service.create_session(
            app_name=APP_NAME, user_id=USER_ID, session_id=session_id
        )
        runner = Runner(
            app_name=APP_NAME, node=workflow, session_service=session_service
        )
        return {
            event.author
            async for event in runner.run_async(
                user_id=USER_ID,
                session_id=session_id,
                new_message=types.Content(
                    role="user", parts=[types.Part(text=message)]
                ),
            )
        }

    return asyncio.run(_run())


def test_expert_dispatch_routes_different_inputs_to_different_specialists():
    """R07: two differently classified requests run two different specialists."""
    _, preset = get_default_registry().resolve("expert_dispatch")
    workflow = preset.build(make_rt())

    risk_authors = run_with_message(
        workflow, "risk-session", "Assess the risk of launching on Friday."
    )
    solution_authors = run_with_message(
        workflow, "solution-session", "Propose a solution for our onboarding drop-off."
    )

    assert "router_specialist_risk" in risk_authors
    assert "router_specialist_solution" not in risk_authors
    assert "router_specialist_research" not in risk_authors
    assert "router_specialist_solution" in solution_authors
    assert "router_specialist_risk" not in solution_authors
    assert risk_authors != solution_authors, (
        "different inputs must reach different specialists, not just the default"
    )


def test_default_route_dispatch_normalizes_fuzzy_state_values():
    """R07: bound routes normalize fuzzy classifier output; garbage falls back."""
    router = partial(
        default_route_dispatch,
        default_route="research",
        routes=["research", "solution", "risk"],
    )

    ctx = FakeCtx({"routed_to": "RISK."})
    router(ctx)
    assert ctx.route == "risk"

    ctx = FakeCtx({"routed_to": "Risk Analysis"})
    router(ctx)
    assert ctx.route == "risk"

    ctx = FakeCtx({"routed_to": "  Solution  "})
    router(ctx)
    assert ctx.route == "solution"

    ctx = FakeCtx({"routed_to": ""})
    router(ctx)
    assert ctx.route == "research"

    ctx = FakeCtx({"routed_to": "totally unknown category"})
    router(ctx)
    assert ctx.route == "research"

    ctx = FakeCtx({"routed_to": None})
    router(ctx)
    assert ctx.route == "research"

    ctx = FakeCtx({})
    router(ctx)
    assert ctx.route == "research"


def test_default_route_dispatch_without_routes_passes_state_through():
    """Without bound routes the router keeps today's passthrough behavior."""
    ctx = FakeCtx({"routed_to": "risk"})
    default_route_dispatch(ctx)
    assert ctx.route == "risk"

    ctx = FakeCtx({})
    default_route_dispatch(ctx, default_route="research")
    assert ctx.route == "research"


def test_loader_rejects_explicitly_empty_specialists(tmp_path):
    """R12: an explicit ``specialists: []`` must raise at load time."""
    config_file = tmp_path / "agent.yaml"
    config_file.write_text(EMPTY_SPECIALISTS_YAML)

    with pytest.raises(ValueError, match="execution.specialists must not be empty"):
        load_config_from_yaml(str(config_file))


def test_spec_builder_raises_on_empty_roster_bypassing_defaults():
    """R12: the builder itself fails fast when handed an empty roster."""
    rt = RuntimeContext(
        model="unused",
        instruction="Runtime policy.",
        tools=[],
        description="empty roster test",
        specialists=(),
    )

    with pytest.raises(ValueError, match="at least one specialist"):
        _expert_dispatch_spec(rt)


def test_unset_specialists_still_get_default_roster():
    """R12: unset (dataclass-default) specialists still yield the default roster."""
    _, preset = get_default_registry().resolve("expert_dispatch")
    resolved = preset.apply_defaults(make_rt(specialists=()))
    assert resolved.specialists == ("research", "solution", "risk")
