"""Shared ADK LlmAgent builder for the compile layer (C3).

Replicates ``strategies/base.py::AgentStrategy.llm()`` semantics exactly:
the instruction-merge contract (role instructions are an addition to the
runtime policy, never a replacement for it), role-override precedence, code
executor, schemas, output key, and callback passthrough.  ``compile/`` is
the single sanctioned home for ADK composition-class construction
(ADR-005 §3); the import-isolation test enforces that.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from google.adk.agents import BaseAgent, LlmAgent

from ..runtime import RoleConfig, RuntimeContext

#: Sentinel distinguishing "not provided" from an explicit None schema:
#: per-node configs may deliberately clear a schema (intermediate state keys
#: the root schema does not declare, e.g. multi_perspective workers).
_UNSET = object()


#: Tool names that configure runtime behavior rather than exposing a tool
#: (mirrors ``agent._SILENT_TOOL_NAMES``; kept in sync by comment).
_SILENT_TOOL_NAMES = {"code_execution", "structured_output"}


def build_llm_agent(
    rt: RuntimeContext,
    *,
    name: str,
    role: RoleConfig | None = None,
    description: str | None = None,
    sub_agents: list[BaseAgent] | None = None,
    output_key: str | None = None,
    output_schema: type | None = None,
    state_schema: type | None | object = _UNSET,
    retry_config: Any = None,
    timeout: float | None = None,
    rerun_on_resume: bool = True,
) -> LlmAgent:
    """Build an LlmAgent from runtime config with optional role overrides.

    Semantics are identical to ``AgentStrategy.llm()``; the extra keyword
    arguments carry the per-node graph attributes (C1) on top of it:
    ``output_key``/``output_schema``/``state_schema`` override the runtime
    defaults when set, and ``retry_config``/``timeout`` map onto
    ``BaseNode`` fields.
    """
    role = role or RoleConfig()
    instruction = rt.instruction
    if role.instruction and role.instruction.strip():
        instruction = (
            f"{rt.instruction}\n\n"
            "Role-specific instructions (follow only if consistent with "
            f"the runtime policy above):\n{role.instruction.strip()}"
        )
    return LlmAgent(
        name=name,
        model=role.model if role.model is not None else rt.model,
        description=description if description is not None else rt.description,
        instruction=instruction,
        tools=role.tools if role.tools is not None else (rt.tools or []),
        code_executor=rt.code_executor,
        state_schema=rt.state_schema if state_schema is _UNSET else state_schema,  # type: ignore[arg-type]
        output_schema=output_schema if output_schema is not None else rt.output_schema,
        output_key=output_key if output_key is not None else rt.output_key,
        before_agent_callback=rt.before_agent_callback,
        after_agent_callback=rt.after_agent_callback,
        before_tool_callback=rt.before_tool_callback,
        after_tool_callback=rt.after_tool_callback,
        sub_agents=sub_agents or [],
        retry_config=retry_config,
        timeout=timeout,
        rerun_on_resume=rerun_on_resume,
    )


def resolve_schema(
    name: str | None,
    schema_registry: dict[str, type] | None,
) -> type | None:
    """Resolve a schema name against the compile-time registry.

    ``None`` (absent) maps to ``None``; unknown names raise with the list of
    valid names, keeping the config contract fail-fast.
    """
    if name is None:
        return None
    registry = schema_registry or {}
    if name not in registry:
        raise ValueError(
            f"Unknown schema name {name!r}; valid schemas: "
            + ", ".join(sorted(registry))
            or "(none)"
        )
    return registry[name]


def resolve_role_spec(
    role: RoleConfig | None,
    *,
    config: Any = None,
    known_tools: set[str],
    resolve_model: Callable[..., Any],
    build_tool: Callable[..., Any],
) -> RoleConfig | None:
    """Resolve a graph node role's string model/tool names.

    Mirrors the role-resolution contract in ``agent._build_runtime_context``:
    a string ``model`` is resolved via ``resolve_model`` (provider taken from
    ``config.model`` when available) and string ``tools`` names are resolved
    via ``build_tool``; unknown tool names and unavailable tools raise with
    the same style of actionable error.
    """
    if role is None:
        return None
    role_model = role.model
    if isinstance(role_model, str) and role_model.strip():
        provider = (
            config.model.provider if config is not None and config.model else "google"
        )
        role_model = resolve_model(role_model.strip(), provider=provider)
    role_tools = role.tools
    if role_tools is not None and all(isinstance(item, str) for item in role_tools):
        resolved_tools = []
        for tool_name in role_tools:
            if tool_name in _SILENT_TOOL_NAMES:
                continue
            if tool_name not in known_tools:
                raise ValueError(
                    f"Unknown tool name {tool_name!r} in a graph node role"
                )
            tool = build_tool(tool_name, config)
            if tool is None:
                raise ValueError(
                    f"Configured tool {tool_name!r} is unavailable for a graph node role"
                )
            resolved_tools.append(tool)
        role_tools = resolved_tools
    return RoleConfig(
        instruction=role.instruction,
        model=role_model,
        tools=role_tools,
    )
