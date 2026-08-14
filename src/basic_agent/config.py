"""Externalized runtime settings for the application and authorization policy."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import os


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _roles(name: str, default: str) -> tuple[str, ...]:
    return tuple(
        role.strip() for role in _env(name, default).split(",") if role.strip()
    )


class AgentPattern(str, Enum):
    """Externally selectable orchestration pattern for the root ADK agent."""

    GENERIC = "generic"
    SEQUENTIAL = "sequential"
    PARALLEL = "parallel"
    LOOP = "loop"
    ROUTER = "router"
    PLANNER_EXECUTOR = "planner_executor"
    EVALUATOR_OPTIMIZER = "evaluator_optimizer"
    HUMAN_IN_LOOP = "human_in_loop"


@dataclass(frozen=True)
class Settings:
    app_name: str
    app_version: str
    deployment: str
    model: str
    agent_pattern: AgentPattern
    live_model: str
    service_api_url: str
    service_api_key: str
    keycloak_issuer: str
    keycloak_jwks_url: str
    keycloak_audience: str
    keycloak_role_claim: str
    keycloak_required_roles: tuple[str, ...]
    service_api_roles: tuple[str, ...]
    live_api_roles: tuple[str, ...]
    plugin_name: str
    agent_description: str
    agent_instruction: str
    enabled_tools: tuple[str, ...]
    enable_knowledge: bool
    enable_search: bool
    enable_code_execution: bool
    enable_mcp: bool
    enable_openapi: bool
    enable_application_integration: bool
    enable_structured_output: bool
    knowledge_file: str
    knowledge_result_limit: int
    pattern_max_iterations: int
    pattern_require_approval: bool
    pattern_specialists: tuple[str, ...]
    mcp_tools: tuple[str, ...]
    mcp_tool_prefix: str
    openapi_url: str
    openapi_path: str
    openapi_title: str
    openapi_tool_prefix: str
    application_tool_prefix: str
    application_tool_instructions: str
    gcp_project: str
    gcp_location: str
    gcp_integration: str
    gcp_triggers: tuple[str, ...]


def load_settings() -> Settings:
    app_name = _env("APP_NAME", "basic_agent")
    issuer = _env("KEYCLOAK_ISSUER")
    enabled_tools = _roles(
        "AGENT_TOOLS",
        "knowledge,search,code_execution,mcp,openapi,approval,runtime,structured_output",
    )
    pattern_value = _env("AGENT_PATTERN", AgentPattern.GENERIC.value).lower()
    try:
        agent_pattern = AgentPattern(pattern_value)
    except ValueError as error:
        supported = ", ".join(pattern.value for pattern in AgentPattern)
        raise ValueError(
            f"Invalid AGENT_PATTERN {pattern_value!r}; choose from {supported}"
        ) from error
    max_iterations = int(_env("AGENT_PATTERN_MAX_ITERATIONS", "3"))
    if max_iterations < 1:
        raise ValueError("AGENT_PATTERN_MAX_ITERATIONS must be at least 1")
    require_approval = _env("AGENT_PATTERN_REQUIRE_APPROVAL", "false").lower()
    if require_approval not in {"true", "false"}:
        raise ValueError("AGENT_PATTERN_REQUIRE_APPROVAL must be true or false")
    return Settings(
        app_name=app_name,
        app_version=_env("APP_VERSION", "0.1.0"),
        deployment=_env("DEPLOYMENT_ENV", "docker-compose"),
        model=_env("ADK_MODEL", "gemini-3.6-flash"),
        agent_pattern=agent_pattern,
        live_model=_env("LIVE_ADK_MODEL", "gemini-3.1-flash-live-preview"),
        service_api_url=_env("AGENT_SERVICE_API_URL", "http://127.0.0.1:8001"),
        service_api_key=_env("AGENT_SERVICE_API_KEY"),
        keycloak_issuer=issuer,
        keycloak_jwks_url=_env(
            "KEYCLOAK_JWKS_URL",
            f"{issuer.rstrip('/')}/protocol/openid-connect/certs" if issuer else "",
        ),
        keycloak_audience=_env("KEYCLOAK_AUDIENCE"),
        keycloak_role_claim=_env("KEYCLOAK_ROLE_CLAIM", "realm_access.roles"),
        keycloak_required_roles=_roles("KEYCLOAK_REQUIRED_ROLES", "agent-user"),
        service_api_roles=_roles(
            "AGENT_SERVICE_API_ROLES", "agent-user"
        ),
        live_api_roles=_roles("LIVE_API_ROLES", "agent-user"),
        plugin_name=_env("AGENT_PLUGIN_NAME", "generic_agent_plugin"),
        agent_description=_env(
            "AGENT_DESCRIPTION", "A general-purpose, configuration-driven ADK agent."
        ),
        agent_instruction=_env(
            "AGENT_INSTRUCTION",
            "Answer the user's request helpfully and accurately. Use configured tools when useful. State assumptions, cite evidence when available, and do not claim actions you did not perform.",
        ),
        enabled_tools=enabled_tools,
        enable_knowledge="knowledge" in enabled_tools,
        enable_search="search" in enabled_tools,
        enable_code_execution="code_execution" in enabled_tools,
        enable_mcp="mcp" in enabled_tools,
        enable_openapi="openapi" in enabled_tools,
        enable_application_integration="application_integration" in enabled_tools,
        enable_structured_output="structured_output" in enabled_tools,
        knowledge_file=_env("AGENT_KNOWLEDGE_FILE"),
        knowledge_result_limit=int(_env("AGENT_KNOWLEDGE_RESULT_LIMIT", "3")),
        pattern_max_iterations=max_iterations,
        pattern_require_approval=require_approval == "true",
        pattern_specialists=_roles(
            "AGENT_PATTERN_SPECIALISTS", "research,solution,risk"
        ),
        mcp_tools=_roles("AGENT_MCP_TOOLS", "get_service_status"),
        mcp_tool_prefix=_env("AGENT_MCP_TOOL_PREFIX", "mcp_"),
        openapi_url=_env("AGENT_OPENAPI_URL", "http://127.0.0.1:8001"),
        openapi_path=_env("AGENT_OPENAPI_PATH", "/status"),
        openapi_title=_env("AGENT_OPENAPI_TITLE", "Configured Service API"),
        openapi_tool_prefix=_env("AGENT_OPENAPI_TOOL_PREFIX", "api_"),
        application_tool_prefix=_env("AGENT_APPLICATION_TOOL_PREFIX", "integration_"),
        application_tool_instructions=_env(
            "AGENT_APPLICATION_TOOL_INSTRUCTIONS",
            "Use this integration only for actions explicitly requested by the user.",
        ),
        gcp_project=_env("GOOGLE_CLOUD_PROJECT"),
        gcp_location=_env("GCP_LOCATION", "us-central1"),
        gcp_integration=_env("GCP_INTEGRATION"),
        gcp_triggers=_roles("GCP_INTEGRATION_TRIGGERS", ""),
    )


settings = load_settings()
