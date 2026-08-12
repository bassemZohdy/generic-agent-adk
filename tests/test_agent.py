from basic_agent.agent import (
    AgentResponse,
    get_project_info,
    project_guide_agent,
    root_agent,
)


def test_agent_uses_structured_output_schema():
    assert root_agent.output_schema is AgentResponse
    assert root_agent.output_key == "last_response"


def test_root_agent_has_project_guide_sub_agent():
    assert root_agent.sub_agents == [project_guide_agent]
    assert project_guide_agent.name == "project_guide_agent"


def test_agent_response_contract():
    response = AgentResponse(answer="Ready.", used_project_tool=False)

    assert response.model_dump() == {
        "answer": "Ready.",
        "used_project_tool": False,
    }


def test_project_info_tool_is_deterministic():
    assert get_project_info("run").startswith("Run `adk web`")
