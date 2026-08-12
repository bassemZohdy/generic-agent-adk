from basic_agent.agent import (
    ReleaseReadinessReport,
    ReleaseReadinessAgent,
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
from basic_agent.live_server import LIVE_MODEL, app
from basic_agent.autoconfig import ProviderConfigurationError, discover_capabilities
from basic_agent.evaluation import EVAL_CONFIG, EVAL_SET, build_eval_command
from basic_agent.telemetry import tracer


def test_root_agent_is_focused_on_release_readiness():
    assert root_agent.output_schema is ReleaseReadinessReport
    assert root_agent.output_key == "last_response"
    assert root_agent.sub_agents == [release_readiness_workflow]
    assert isinstance(root_agent, ReleaseReadinessAgent)
    assert root_agent.domain == "release_readiness"
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


def test_live_api_reuses_root_agent():
    routes = {(route.path, route.name) for route in app.routes}

    assert ("/healthz", "healthz") in routes
    assert any(getattr(route, "path", None) == "/live" for route in app.routes)
    assert LIVE_MODEL


def test_capabilities_fall_back_to_in_memory_without_configuration():
    capabilities = discover_capabilities({})

    assert {name: provider.strategy for name, provider in capabilities.items()} == {
        "storage": "in_memory",
        "messaging": "in_memory",
        "caching": "in_memory",
        "search": "in_memory",
        "logging": "in_memory",
    }


def test_capabilities_choose_cloud_over_local_without_type_flags():
    capabilities = discover_capabilities(
        {
            "STORAGE_BUCKET": "release-artifacts",
            "STORAGE_PATH": "./artifacts",
            "MESSAGING_URL": "amqp://cloud.example/messages",
            "BROKER_URL": "amqp://localhost/messages",
            "CACHE_URL": "redis://cache.example:6379/0",
            "CACHE_PATH": "./cache",
            "SEARCH_URL": "https://search.example",
            "SEARCH_API_KEY": "secret",
            "SEARCH_INDEX_PATH": "./index",
            "LOG_ENDPOINT": "https://logs.example/ingest",
            "LOG_API_KEY": "secret",
            "LOG_FILE": "./agent.log",
        }
    )

    assert {name: provider.strategy for name, provider in capabilities.items()} == {
        "storage": "cloud",
        "messaging": "cloud",
        "caching": "cloud",
        "search": "cloud",
        "logging": "cloud",
    }


def test_capabilities_choose_database_and_local_strategies_when_cloud_is_absent():
    capabilities = discover_capabilities(
        {
            "DATABASE_URL": "postgresql://db.example/releases",
            "STORAGE_PATH": "./artifacts",
            "BROKER_URL": "amqp://localhost/messages",
            "CACHE_PATH": "./cache",
            "SEARCH_INDEX_PATH": "./index",
            "LOG_FILE": "./agent.log",
        }
    )

    assert {name: provider.strategy for name, provider in capabilities.items()} == {
        "storage": "database",
        "messaging": "local_broker",
        "caching": "local_disk",
        "search": "local_index",
        "logging": "local_file",
    }


def test_detected_malformed_provider_fails_without_silent_fallback():
    try:
        discover_capabilities(
            {"MESSAGING_URL": "not-a-url", "BROKER_URL": "amqp://localhost"}
        )
    except ProviderConfigurationError as error:
        assert "messaging" in str(error)
    else:
        raise AssertionError("Malformed detected messaging configuration was accepted")


def test_evaluation_entry_point_targets_adk_dataset_and_config():
    command = build_eval_command(detailed=True)

    assert command[1:2] == ["eval"]
    assert str(EVAL_SET) in command
    assert any(str(EVAL_CONFIG) in argument for argument in command)
    assert "--print_detailed_results" in command


def test_local_otel_tracer_is_available_for_adk_plugin_spans():
    assert tracer is not None
