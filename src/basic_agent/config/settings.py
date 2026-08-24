"""Externalized runtime settings for the application and authorization policy."""

from __future__ import annotations

import os
from dataclasses import dataclass

from ..util import is_production, split_csv
from .defaults import (
    APP_VERSION,
    ENABLED_TOOLS,
    LIVE_MAX_AUDIO_BYTES,
    LIVE_MAX_MESSAGE_BYTES,
    LIVE_MAX_MESSAGES_PER_MINUTE,
    LIVE_MODEL,
    MAX_ITERATIONS,
    MCP_TOOLS,
    MODEL,
    SERVICE_API_URL,
)


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _roles(name: str, default: str) -> tuple[str, ...]:
    return tuple(split_csv(_env(name, default)))


def _bool(name: str, default: bool = False) -> bool:
    """Parse a strict boolean environment setting."""
    raw = _env(name, "true" if default else "false").lower()
    if raw not in {"true", "false"}:
        raise ValueError(f"{name} must be true or false")
    return raw == "true"


def _int(name: str, default: int, *, minimum: int = 0) -> int:
    """Parse an integer setting with an actionable error message."""
    raw = _env(name, str(default))
    try:
        value = int(raw)
    except ValueError as error:
        raise ValueError(f"{name} must be an integer; got {raw!r}") from error
    if value < minimum:
        raise ValueError(f"{name} must be at least {minimum}; got {value}")
    return value


def _float(name: str, default: float, *, minimum: float = 0.0) -> float:
    """Parse a floating-point setting with an actionable error message."""
    raw = _env(name, str(default))
    try:
        value = float(raw)
    except ValueError as error:
        raise ValueError(f"{name} must be a number; got {raw!r}") from error
    if value < minimum:
        raise ValueError(f"{name} must be at least {minimum}; got {value}")
    return value


@dataclass(frozen=True)
class Settings:
    app_name: str
    app_version: str
    deployment: str | None
    model: str
    live_model: str
    service_api_url: str
    service_api_key: str
    auth_disabled: bool
    keycloak_issuer: str
    keycloak_jwks_url: str
    keycloak_jwks_timeout: float
    keycloak_audience: str
    keycloak_role_claim: str
    keycloak_required_roles: tuple[str, ...]
    service_api_roles: tuple[str, ...]
    live_api_roles: tuple[str, ...]
    plugin_name: str
    agent_description: str
    agent_instruction: str
    enabled_tools: tuple[str, ...]
    read_only_tools: tuple[str, ...]
    mutating_tools: tuple[str, ...]
    enable_knowledge: bool
    enable_search: bool
    enable_code_execution: bool
    enable_mcp: bool
    enable_skills: bool
    enable_openapi: bool
    enable_application_integration: bool
    enable_structured_output: bool
    knowledge_file: str
    knowledge_result_limit: int
    knowledge_max_file_bytes: int
    knowledge_max_result_bytes: int
    max_iterations: int
    specialists: tuple[str, ...]
    mcp_tools: tuple[str, ...]
    mcp_tool_prefix: str
    skills_dir: str
    skills_tool_prefix: str
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
    live_max_message_bytes: int
    live_max_audio_bytes: int
    live_max_messages_per_minute: int
    code_execution_strategy: str
    code_execution_docker_host: str
    code_execution_docker_image: str
    code_execution_vertex_resource: str
    code_execution_agent_engine_resource: str
    code_execution_gke_kubeconfig_path: str
    code_execution_gke_kubeconfig_context: str


def load_settings() -> Settings:
    app_name = _env("APP_NAME", "basic_agent")
    deployment = os.environ.get("DEPLOYMENT_ENV")
    issuer = _env("KEYCLOAK_ISSUER")
    auth_disabled = _bool("AUTH_DISABLED")
    # H16: use the raw env var (None when unset) so unset DEPLOYMENT_ENV is
    # treated as production (fail closed), matching resolve_allowlisted_file().
    if is_production(deployment):
        if auth_disabled:
            raise ValueError(
                "AUTH_DISABLED=true is only permitted for local/test deployments; "
                "configure KEYCLOAK_ISSUER for production-like environments"
            )
        if not issuer:
            raise ValueError(
                "KEYCLOAK_ISSUER is required when DEPLOYMENT_ENV is production-like"
            )
    enabled_tools = _roles(
        "AGENT_TOOLS",
        ENABLED_TOOLS,
    )
    return Settings(
        app_name=app_name,
        app_version=_env("APP_VERSION", APP_VERSION),
        deployment=deployment,
        model=_env("ADK_MODEL", MODEL),
        live_model=_env("LIVE_ADK_MODEL", LIVE_MODEL),
        service_api_url=_env("AGENT_SERVICE_API_URL", SERVICE_API_URL),
        service_api_key=_env("AGENT_SERVICE_API_KEY"),
        auth_disabled=auth_disabled,
        keycloak_issuer=issuer,
        keycloak_jwks_url=_env(
            "KEYCLOAK_JWKS_URL",
            f"{issuer.rstrip('/')}/protocol/openid-connect/certs" if issuer else "",
        ),
        keycloak_jwks_timeout=_float("KEYCLOAK_JWKS_TIMEOUT", 5.0, minimum=0.1),
        keycloak_audience=_env("KEYCLOAK_AUDIENCE", "basic-agent"),
        keycloak_role_claim=_env("KEYCLOAK_ROLE_CLAIM", "realm_access.roles"),
        keycloak_required_roles=_roles("KEYCLOAK_REQUIRED_ROLES", "agent-user"),
        service_api_roles=_roles("AGENT_SERVICE_API_ROLES", "agent-user"),
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
        read_only_tools=_roles(
            "AGENT_READ_ONLY_TOOLS",
            "request_approval,inspect_runtime,retrieve_knowledge,google_search,"
            "get_service_status,mcp_get_service_status,api_getconfiguredservicestatus",
        ),
        mutating_tools=_roles("AGENT_MUTATING_TOOLS", ""),
        enable_knowledge="knowledge" in enabled_tools,
        enable_search="search" in enabled_tools,
        enable_code_execution="code_execution" in enabled_tools,
        enable_mcp="mcp" in enabled_tools,
        enable_skills="skills" in enabled_tools,
        enable_openapi="openapi" in enabled_tools,
        enable_application_integration="application_integration" in enabled_tools,
        enable_structured_output="structured_output" in enabled_tools,
        knowledge_file=_env("AGENT_KNOWLEDGE_FILE"),
        knowledge_result_limit=_int("AGENT_KNOWLEDGE_RESULT_LIMIT", 3, minimum=1),
        knowledge_max_file_bytes=_int(
            "AGENT_KNOWLEDGE_MAX_FILE_BYTES", 2_097_152, minimum=1
        ),
        knowledge_max_result_bytes=_int(
            "AGENT_KNOWLEDGE_MAX_RESULT_BYTES", 65_536, minimum=1
        ),
        max_iterations=_int("AGENT_MAX_ITERATIONS", MAX_ITERATIONS, minimum=1),
        specialists=_roles("AGENT_SPECIALISTS", "research,solution,risk"),
        mcp_tools=_roles("AGENT_MCP_TOOLS", MCP_TOOLS),
        mcp_tool_prefix=_env("AGENT_MCP_TOOL_PREFIX", "mcp_"),
        skills_dir=_env("AGENT_SKILLS_DIR"),
        skills_tool_prefix=_env("AGENT_SKILLS_TOOL_PREFIX"),
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
        live_max_message_bytes=_int(
            "LIVE_MAX_MESSAGE_BYTES", LIVE_MAX_MESSAGE_BYTES, minimum=1
        ),
        live_max_audio_bytes=_int(
            "LIVE_MAX_AUDIO_BYTES", LIVE_MAX_AUDIO_BYTES, minimum=1
        ),
        live_max_messages_per_minute=_int(
            "LIVE_MAX_MESSAGES_PER_MINUTE", LIVE_MAX_MESSAGES_PER_MINUTE, minimum=1
        ),
        code_execution_strategy=_env("AGENT_CODE_EXECUTION_STRATEGY"),
        code_execution_docker_host=_env("AGENT_CODE_EXECUTION_DOCKER_HOST"),
        code_execution_docker_image=_env("AGENT_CODE_EXECUTION_DOCKER_IMAGE"),
        code_execution_vertex_resource=_env("AGENT_CODE_EXECUTION_VERTEX_RESOURCE"),
        code_execution_agent_engine_resource=_env(
            "AGENT_CODE_EXECUTION_AGENT_ENGINE_RESOURCE"
        ),
        code_execution_gke_kubeconfig_path=_env(
            "AGENT_CODE_EXECUTION_GKE_KUBECONFIG_PATH"
        ),
        code_execution_gke_kubeconfig_context=_env(
            "AGENT_CODE_EXECUTION_GKE_KUBECONFIG_CONTEXT"
        ),
    )


settings = load_settings()
