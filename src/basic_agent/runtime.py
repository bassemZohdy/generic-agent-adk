"""Shared runtime types for compiler and preset layers (E3).

Formerly ``strategies/base.py``: the strategy layer was removed in E3
(ADR-005 §3/§5 — presets + compilers replace it), but ``RoleConfig`` and
``RuntimeContext`` are framework-neutral data contracts that the compile and
preset layers (and the runtime assembly in ``agent.py``) still need.  They
live here, importing no ADK composition classes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class RoleConfig:
    """Per-role overrides applied on top of RuntimeContext defaults.

    Fields left as None fall back to the shared runtime values.
    """

    instruction: str | None = None
    model: str | None = None
    tools: list[Any] | None = None


@dataclass
class RuntimeContext:
    """Shared runtime resources and configuration for preset execution."""

    model: Any  # model name (str) or BaseLlm instance (e.g. LiteLlm)
    instruction: str
    tools: list[Any]
    description: str
    code_executor: Any = None
    code_execution_strategy: str | None = None  # "docker_container" | … | "unavailable"
    code_execution_detail: str = ""  # provenance, for logs/traces
    state_schema: type | None = None
    output_schema: type | None = None
    output_key: str | None = None
    before_agent_callback: Any = None
    after_agent_callback: Any = None
    max_iterations: int = 3
    require_approval: bool = False
    specialists: tuple[str, ...] = ()
    roles: dict[str, RoleConfig] = field(default_factory=dict)
    before_tool_callback: Any = None
    after_tool_callback: Any = None
    extra_config: dict[str, Any] = field(default_factory=dict)
