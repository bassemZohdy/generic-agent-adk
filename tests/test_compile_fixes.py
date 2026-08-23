"""Review fixes R10/R11/R14 — compile-layer regression tests.

- R10: ``default_aggregate_perspectives`` must surface failures (warning
  log + ``aggregation_failed`` state marker) instead of swallowing them at
  debug level, while never propagating out of the graph function.
- R11: empty-registry error messages must end in ``(none)`` (the
  ``"...: " + ", ".join(x) or "(none)"`` precedence bug).
- R14: ``plan_execute`` dispatches independent steps concurrently while
  keeping ``plan_outputs`` in step order.
"""

from __future__ import annotations

import asyncio
import logging
import time

import pytest
from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_response import LlmResponse
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from basic_agent.compile.llm_node import resolve_schema
from basic_agent.compile.workflow import default_aggregate_perspectives
from basic_agent.config.sugar import SequenceSugar, expand_sugar
from basic_agent.runtime import RuntimeContext
from basic_agent.use_cases import get_default_registry

APP_NAME = "compile-fixes"
USER_ID = "fixes-user"
AGGREGATION_LOGGER = "basic_agent.compile.workflow"


class _Ctx:
    """Minimal invocation-context stand-in exposing ``state``."""

    def __init__(self, state):
        self.state = state


class _BoomToDict(dict):
    """First failure mode: ``state.to_dict`` raises."""

    def to_dict(self):
        raise RuntimeError("to_dict exploded")


class _BoomAggregateWrite(dict):
    """Second failure mode: writing the aggregate key raises."""

    def to_dict(self):
        return dict(self)

    def __setitem__(self, key, value):
        if key == "aggregated_perspectives":
            raise RuntimeError("aggregate write rejected")
        super().__setitem__(key, value)


class _BoomAllWrites(dict):
    """Broken-state mode: every write raises (marker write must not propagate)."""

    def to_dict(self):
        return dict(self)

    def __setitem__(self, key, value):
        raise RuntimeError("state is read-only")


def _warnings(caplog, fragment):
    return [
        record
        for record in caplog.records
        if record.levelno == logging.WARNING
        and record.name == AGGREGATION_LOGGER
        and fragment in record.message
    ]


# ---------------------------------------------------------------------------
# R10 — aggregation failure visibility
# ---------------------------------------------------------------------------


def test_aggregation_failure_to_dict_raises_warns_and_marks_state(caplog):
    state = _BoomToDict(perspective_0="a")

    with caplog.at_level(logging.WARNING, logger=AGGREGATION_LOGGER):
        default_aggregate_perspectives(_Ctx(state), None)

    assert _warnings(caplog, "Unable to aggregate")
    assert state["aggregation_failed"] is True
    assert "aggregated_perspectives" not in state


def test_aggregation_failure_aggregate_write_raises_warns_and_marks_state(caplog):
    state = _BoomAggregateWrite(perspective_0="a")

    with caplog.at_level(logging.WARNING, logger=AGGREGATION_LOGGER):
        default_aggregate_perspectives(_Ctx(state), None)

    assert _warnings(caplog, "Unable to aggregate")
    assert state["aggregation_failed"] is True


def test_aggregation_marker_write_failure_never_propagates(caplog):
    state = _BoomAllWrites(perspective_0="a")

    with caplog.at_level(logging.WARNING, logger=AGGREGATION_LOGGER):
        default_aggregate_perspectives(_Ctx(state), None)  # must not raise

    assert _warnings(caplog, "Unable to aggregate")
    assert _warnings(caplog, "aggregation_failed")


def test_aggregation_success_behavior_unchanged():
    state = {
        "perspective_10": "c",
        "perspective_2": "b",
        "perspective_1": "a",
        "unrelated": "x",
    }

    default_aggregate_perspectives(_Ctx(state), None)

    assert state["aggregated_perspectives"] == ["a", "b", "c"]
    assert "aggregation_failed" not in state


# ---------------------------------------------------------------------------
# R11 — "(none)" error messages on empty registries
# ---------------------------------------------------------------------------


def test_resolve_schema_empty_registry_message_ends_with_none():
    with pytest.raises(ValueError) as excinfo:
        resolve_schema("Whatever", {})

    message = str(excinfo.value)
    assert "valid schemas" in message
    assert message.endswith("(none)")


def test_check_name_exists_empty_registry_message_ends_with_none():
    with pytest.raises(ValueError) as excinfo:
        expand_sugar(SequenceSugar(items=["nope"]), {})

    message = str(excinfo.value)
    assert "valid nodes" in message
    assert message.endswith("(none)")


def test_error_messages_list_known_names():
    with pytest.raises(ValueError) as excinfo:
        resolve_schema("Whatever", {"Beta": int, "Alpha": str})
    assert str(excinfo.value).endswith("Alpha, Beta")

    from basic_agent.config.graph import GraphNodeSpec

    node = GraphNodeSpec(name="real", kind="llm")
    with pytest.raises(ValueError) as excinfo:
        expand_sugar(SequenceSugar(items=["nope"]), {"real": node})
    assert "valid nodes: real" in str(excinfo.value)


# ---------------------------------------------------------------------------
# R14 — concurrent plan steps, ordered outputs
# ---------------------------------------------------------------------------


class SlowEchoLlm(BaseLlm):
    """Fake model: sleeps per call, echoes the plan step, tracks peak concurrency."""

    delay: float = 0.15
    calls: int = 0
    active: int = 0
    peak: int = 0

    async def generate_content_async(self, llm_request, stream=False):
        self.calls += 1
        self.active += 1
        self.peak = max(self.peak, self.active)
        try:
            await asyncio.sleep(self.delay)
            text = " ".join(
                part.text
                for content in llm_request.contents
                for part in (content.parts or [])
                if part.text
            )
            step = next(s for s in ("step 1", "step 2", "step 3") if s in text)
            response = LlmResponse(
                content=types.Content(
                    role="model", parts=[types.Part(text=f"ran: {step}")]
                )
            )
        finally:
            self.active -= 1
        yield response


def test_plan_execute_steps_run_concurrently_and_outputs_stay_ordered():
    model = SlowEchoLlm(model="slow-echo")
    rt = RuntimeContext(
        model=model,
        instruction="Runtime policy: follow the operator's task.",
        tools=[],
        description="compile-fixes agent",
        output_key="last_response",
        max_iterations=5,
    )
    root = get_default_registry().get_preset("plan_and_execute").build(rt)

    async def _run(session_id: str):
        session_service = InMemorySessionService()
        await session_service.create_session(
            app_name=APP_NAME, user_id=USER_ID, session_id=session_id
        )
        runner = Runner(app_name=APP_NAME, node=root, session_service=session_service)
        events = []
        started = time.monotonic()
        async for event in runner.run_async(
            user_id=USER_ID,
            session_id=session_id,
            new_message=types.Content(
                role="user", parts=[types.Part(text="Do the thing.")]
            ),
        ):
            events.append(event)
        return events, time.monotonic() - started

    # Warm-up run: the first in-process workflow run pays one-time engine /
    # telemetry initialization (~2s observed) that would swamp the timing
    # bound; only the second (warm) run is measured.
    warm_events, _ = asyncio.run(_run("plan-concurrency-warm"))
    events, elapsed = asyncio.run(_run("plan-concurrency-measured"))

    for run_events in (warm_events, events):
        state: dict = {}
        for event in run_events:
            if event.actions and event.actions.state_delta:
                state.update(event.actions.state_delta)
        # Ordered-outputs contract (gather preserves awaitable input order).
        assert state["plan_outputs"] == ["ran: step 1", "ran: step 2", "ran: step 3"]

    assert model.calls == 6  # 3 steps x 2 runs
    # Concurrency proof (primary): sequential dispatch would keep active == 1
    # for the whole run; overlapping model calls mean concurrent steps.
    assert model.peak >= 2, f"plan steps did not overlap (peak={model.peak})"
    # Secondary timing bound: a warm sequential run must await the three
    # 0.15s sleeps serially (>= 0.45s); a warm concurrent run was measured
    # at ~0.2s locally.  0.42s leaves margin on both sides.
    assert elapsed < 0.42, f"warm run took {elapsed:.3f}s; sequential floor ~0.45s"
