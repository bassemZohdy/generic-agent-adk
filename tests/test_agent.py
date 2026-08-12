from basic_agent.agent import (
    AgentResponse,
    get_project_info,
    project_guide_agent,
    project_facts_agent,
    project_overview_workflow,
    project_parallel_workflow,
    project_refinement_agent,
    project_review_agent,
    project_review_loop,
    project_runtime_agent,
    project_summary_agent,
    project_structure_agent,
    research_agent,
    analysis_agent,
    knowledge_agent,
    retrieve_project_knowledge,
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


def test_project_review_is_parallel():
    assert project_parallel_workflow in root_agent.sub_agents
    assert project_parallel_workflow.sub_agents == [
        project_structure_agent,
        project_runtime_agent,
    ]


def test_project_review_loop_is_bounded():
    assert project_review_loop in root_agent.sub_agents
    assert project_review_loop.max_iterations == 2
    assert project_review_loop.sub_agents == [
        project_review_agent,
        project_refinement_agent,
    ]


def test_research_agent_uses_google_search():
    assert research_agent in root_agent.sub_agents
    assert research_agent.tools[0].__class__.__name__ == "GoogleSearchTool"


def test_analysis_agent_uses_code_execution():
    assert analysis_agent in root_agent.sub_agents
    assert analysis_agent.code_executor.__class__.__name__ == "BuiltInCodeExecutor"


def test_knowledge_agent_retrieves_relevant_passages():
    assert knowledge_agent in root_agent.sub_agents
    result = retrieve_project_knowledge("How do I run Docker?")
    assert "Docker deployment" in result
    assert "docker compose up --build" in result


def test_agent_response_contract():
    response = AgentResponse(answer="Ready.", used_project_tool=False)

    assert response.model_dump() == {
        "answer": "Ready.",
        "used_project_tool": False,
    }


def test_project_info_tool_is_deterministic():
    assert get_project_info("run").startswith("Run `adk web`")
