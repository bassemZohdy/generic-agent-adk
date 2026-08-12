from basic_agent.agent import (
    AgentResponse,
    get_project_info,
    project_guide_agent,
    project_facts_agent,
    project_overview_workflow,
    project_summary_agent,
    root_agent,
)


def test_agent_uses_structured_output_schema():
    assert root_agent.output_schema is AgentResponse
    assert root_agent.output_key == "last_response"


def test_root_agent_has_project_guide_sub_agent():
    assert project_guide_agent in root_agent.sub_agents
    assert project_guide_agent.name == "project_guide_agent"


def test_project_overview_is_sequential():
    assert root_agent.sub_agents[1] is project_overview_workflow
    assert project_overview_workflow.sub_agents == [
        project_facts_agent,
        project_summary_agent,
    ]


def test_agent_response_contract():
    response = AgentResponse(answer="Ready.", used_project_tool=False)

    assert response.model_dump() == {
        "answer": "Ready.",
        "used_project_tool": False,
    }


def test_project_info_tool_is_deterministic():
    assert get_project_info("run").startswith("Run `adk web`")
