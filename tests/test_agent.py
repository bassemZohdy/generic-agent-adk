from basic_agent.agent import (
    ReleaseReadinessReport,
    ReleaseWorkflowState,
    get_release_metrics,
    release_api_agent,
    release_api_toolset,
    release_evidence_workflow,
    release_knowledge_agent,
    release_metrics_agent,
    release_operations_agent,
    release_readiness_workflow,
    release_refinement_agent,
    release_research_agent,
    release_review_agent,
    release_review_loop,
    release_synthesis_agent,
    retrieve_project_knowledge,
    request_release_approval,
    ReleaseReadinessPlugin,
    application_integration_toolset,
    root_agent,
)
from basic_agent.release_api import get_release_status


def test_root_agent_is_focused_on_release_readiness():
    assert root_agent.output_schema is ReleaseReadinessReport
    assert root_agent.output_key == "last_response"
    assert root_agent.sub_agents == [release_readiness_workflow]
    assert root_agent.state_schema is ReleaseWorkflowState
    assert root_agent.before_agent_callback is not None
    assert root_agent.after_agent_callback is not None


def test_release_evidence_fans_out_to_five_sources():
    assert release_readiness_workflow.sub_agents[0] is release_evidence_workflow
    assert release_evidence_workflow.sub_agents == [
        release_knowledge_agent,
        release_research_agent,
        release_metrics_agent,
        release_operations_agent,
        release_api_agent,
    ]


def test_release_workflow_synthesizes_then_reviews():
    assert release_readiness_workflow.sub_agents[1] is release_synthesis_agent
    assert release_readiness_workflow.sub_agents[2] is release_review_loop
    assert release_review_loop.sub_agents == [
        release_review_agent,
        release_refinement_agent,
    ]
    assert release_review_loop.max_iterations == 2


def test_retrieval_returns_release_criteria():
    result = retrieve_project_knowledge("release criteria")

    assert "Release readiness criteria" in result
    assert "blocking risks" in result


def test_release_metrics_are_deterministic():
    metrics = get_release_metrics()

    assert '"total_tests": 120' in metrics
    assert '"critical_failures": 0' in metrics


def test_release_api_agent_uses_openapi_toolset():
    assert release_api_agent in release_evidence_workflow.sub_agents
    assert release_api_toolset in release_api_agent.tools
    assert release_api_toolset.tool_name_prefix == "release_api_"


def test_release_api_returns_live_status_shape():
    status = get_release_status()

    assert status["status"] == "healthy"
    assert status["deployment"] == "docker-compose"


def test_release_approval_rejects_invalid_recommendation():
    assert "Invalid recommendation" in request_release_approval("maybe", object())


def test_release_plugin_is_registered_type():
    assert ReleaseReadinessPlugin().name == "release_readiness_plugin"


def test_application_integration_is_optional_for_local_runs():
    assert application_integration_toolset is None


def test_release_report_contract():
    report = ReleaseReadinessReport(
        answer="Ready with conditions.",
        recommendation="ready_with_conditions",
        confidence=0.8,
        risks=["Two non-critical tests failed."],
        evidence=["Service is healthy."],
        next_steps=["Review the failed tests."],
    )

    assert report.recommendation == "ready_with_conditions"
    assert report.confidence == 0.8
