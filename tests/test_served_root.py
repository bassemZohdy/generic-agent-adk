"""ADR-003 scope note: the REST API serves the compiled workflow root.

``interfaces/agent.py`` is the ADK AgentLoader discovery entry: the api server
imports it and reads ``root_agent`` — which builds the configured preset
**compiled to a graph Workflow** (lazy, via ``basic_agent.agent.get_root_agent``).
This suite proves the served app discovers the agent and that ``/run``
executes it end-to-end with a fake model.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_response import LlmResponse
from google.genai import types

from basic_agent import agent as agent_module
from basic_agent.interfaces import agent as serving_module
from basic_agent.interfaces import rest


class DeterministicLlm(BaseLlm):
    """A no-network model returning one valid JSON response per turn."""

    calls: int = 0

    async def generate_content_async(self, llm_request, stream=False):
        self.calls += 1
        yield LlmResponse(
            content=types.Content(
                role="model",
                parts=[
                    types.Part(
                        text=(
                            '{"answer": "served answer 1", "confidence": 0.9, '
                            '"evidence": [], "risks": [], "next_steps": []}'
                        )
                    )
                ],
            )
        )


@pytest.fixture
def served_client(monkeypatch, settings_patch):
    """Fresh, fake-model-backed app: compiled workflow root served by /run."""
    settings_patch(rest, auth_disabled=True, deployment="development")
    model = DeterministicLlm(model="deterministic")
    monkeypatch.setattr(agent_module, "resolve_model", lambda *a, **k: model)
    monkeypatch.setattr(agent_module, "_root_agent", None)
    monkeypatch.setattr(serving_module, "_loaded", None)
    client = TestClient(rest.app)
    # Auth-disabled path: the first request assigns the anonymous cookie.
    client.post("/run", json={"message": "warm", "sessionId": "s-warm"})
    cookie = client.cookies.get("adk_anonymous_id")
    user_id = f"anonymous:{cookie}"
    created = client.post(
        f"/apps/interfaces/users/{user_id}/sessions",
        json={"sessionId": "s-served"},
    )
    assert created.status_code == 200
    return client, model


def test_served_app_lists_the_configured_agent(settings_patch):
    settings_patch(rest, auth_disabled=True, deployment="development")
    client = TestClient(rest.app)
    apps = client.get("/list-apps").json()
    assert "interfaces" in apps


def test_served_root_runs_end_to_end(served_client):
    client, model = served_client
    response = client.post("/run", json={"message": "hello", "sessionId": "s-served"})
    assert response.status_code == 200, response.text[:300]
    body = response.json()
    assert model.calls >= 1, "the served run must reach the model"
    assert "served answer 1" in str(body)


def test_serving_module_root_agent_is_a_workflow():
    from google.adk.workflow import Workflow

    root = serving_module.root_agent
    assert isinstance(root, Workflow), "the served root is the compiled graph"
