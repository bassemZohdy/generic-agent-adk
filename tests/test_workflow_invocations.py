"""Deterministic Runner-level coverage for every shipped example workflow."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import patch

import pytest
from google.adk.agents import LlmAgent
from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_response import LlmResponse
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from basic_agent import agent as agent_module
from basic_agent.config.loader import load_config_from_yaml
from basic_agent.tools import build_tool

ROOT = Path(__file__).parents[1]
EXAMPLES = ROOT / "examples"


class DeterministicLlm(BaseLlm):
    """A no-network model that returns one valid response per model turn."""

    calls: int = 0

    async def generate_content_async(self, llm_request, stream=False):
        self.calls += 1
        yield LlmResponse(
            content=types.Content(
                role="model",
                parts=[types.Part(text=f"deterministic response {self.calls}")],
            )
        )


EXPECTED_FINAL_AUTHORS = {
    "approval-gate.yaml": "human_in_loop_completer",
    "assistant.yaml": "direct_agent",
    "expert-dispatch.yaml": "router_agent",
    "multi-perspective.yaml": "perspective_synthesizer",
    "pipeline.yaml": "sequential_step_2",
    "plan-and-execute.yaml": "executor_agent",
    "refine-until-good.yaml": "evaluator_optimizer_worker",
    "team-coordinator.yaml": "supervisor_agent",
}


async def _invoke_example(path: Path) -> tuple[list, int]:
    model = DeterministicLlm(model="deterministic")
    config = load_config_from_yaml(str(path))
    with patch.object(agent_module, "resolve_model", return_value=model):
        root = agent_module._build_root_agent(config, f"test:{path.name}")

    session_service = InMemorySessionService()
    await session_service.create_session(
        app_name="workflow-tests",
        user_id="test-user",
        session_id=path.stem,
    )
    runner = Runner(
        app_name="workflow-tests",
        agent=root,
        session_service=session_service,
    )
    events = [
        event
        async for event in runner.run_async(
            user_id="test-user",
            session_id=path.stem,
            new_message=types.Content(
                role="user",
                parts=[types.Part(text="Give a deterministic answer.")],
            ),
        )
    ]
    return events, model.calls


@pytest.mark.parametrize(
    "filename",
    sorted(EXPECTED_FINAL_AUTHORS),
)
def test_example_workflow_completes_with_deterministic_runner(filename):
    """Each documented example must execute through its real Runner path."""
    events, model_calls = asyncio.run(_invoke_example(EXAMPLES / filename))

    assert events
    assert events[-1].author == EXPECTED_FINAL_AUTHORS[filename]
    assert model_calls >= 1
    assert all(event.invocation_id for event in events)


class ConfirmationLlm(BaseLlm):
    """Emit one approval tool call, then answer after the resume message."""

    calls: int = 0

    async def generate_content_async(self, llm_request, stream=False):
        self.calls += 1
        if self.calls == 1:
            yield LlmResponse(
                content=types.Content(
                    role="model",
                    parts=[
                        types.Part(
                            function_call=types.FunctionCall(
                                name="request_approval",
                                args={"action": "publish"},
                                id="approval-call",
                            )
                        )
                    ],
                )
            )
            return
        yield LlmResponse(
            content=types.Content(
                role="model", parts=[types.Part(text="approval flow complete")]
            )
        )


async def _run_confirmation(confirmed: bool):
    model = ConfirmationLlm(model="deterministic-confirmation")
    root = LlmAgent(
        name="approval_test_agent",
        model=model,
        instruction="Request approval before proceeding.",
        tools=[build_tool("approval", None)],
    )
    session_service = InMemorySessionService()
    await session_service.create_session(
        app_name="approval-tests",
        user_id="test-user",
        session_id="approval-session",
    )
    runner = Runner(
        app_name="approval-tests",
        agent=root,
        session_service=session_service,
    )
    pending = [
        event
        async for event in runner.run_async(
            user_id="test-user",
            session_id="approval-session",
            new_message=types.Content(
                role="user", parts=[types.Part(text="publish the change")]
            ),
        )
    ]
    initial_model_calls = model.calls
    interrupt = next(event for event in pending if event.long_running_tool_ids)
    interrupt_id = next(iter(interrupt.long_running_tool_ids))
    resumed = [
        event
        async for event in runner.run_async(
            user_id="test-user",
            session_id="approval-session",
            invocation_id=interrupt.invocation_id,
            new_message=types.Content(
                role="user",
                parts=[
                    types.Part(
                        function_response=types.FunctionResponse(
                            id=interrupt_id,
                            name="adk_request_confirmation",
                            response={"confirmed": confirmed},
                        )
                    )
                ],
            ),
        )
    ]
    return model, initial_model_calls, pending, resumed


@pytest.mark.parametrize("confirmed", [True, False])
def test_approval_runner_suspends_and_resumes_for_decision(confirmed):
    """Approval must suspend the Runner and continue only after a decision."""
    model, initial_model_calls, pending, resumed = asyncio.run(
        _run_confirmation(confirmed)
    )

    assert initial_model_calls == 1
    assert model.calls == 2
    assert len(pending) == 3
    assert pending[-2].long_running_tool_ids
    assert pending[-1].content.parts[0].function_response.name == "request_approval"
    assert resumed[-1].content.parts[0].text == "approval flow complete"
    response = resumed[0].content.parts[0].function_response.response
    if confirmed:
        assert response["result"] == "Action confirmed."
    else:
        assert response["error"] == "This tool call is rejected."
