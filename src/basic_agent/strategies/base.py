"""Base strategy interface and supporting types."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from google.adk.agents import Agent, LlmAgent


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
    """Shared runtime resources and configuration for strategy execution."""

    model: Any  # model name (str) or BaseLlm instance (e.g. LiteLlm)
    instruction: str
    tools: list[Any]
    description: str
    code_executor: Any = None
    state_schema: type | None = None
    output_schema: type | None = None
    output_key: str | None = None
    before_agent_callback: Any = None
    after_agent_callback: Any = None
    max_iterations: int = 3
    require_approval: bool = False
    specialists: tuple[str, ...] = ()
    roles: dict[str, RoleConfig] = field(default_factory=dict)


@dataclass
class AgentStrategyContext:
    """Configuration specific to an agent strategy."""

    agent_type: str
    runtime: RuntimeContext
    extra_config: dict[str, Any] | None = None


class AgentStrategy(ABC):
    """Abstract base for agent-building strategies.

    Each strategy encapsulates the logic for building an agent of a specific
    execution pattern (DIRECT, REACT, SEQUENTIAL, etc.) from shared configuration.
    """

    @property
    @abstractmethod
    def agent_type(self) -> str:
        """Return the agent type identifier (e.g., 'DIRECT', 'REACT')."""

    @abstractmethod
    def build(self, context: AgentStrategyContext) -> Agent:
        """Build and return an ADK agent for this strategy.

        Args:
            context: Shared runtime configuration and strategy-specific context.

        Returns:
            An ADK Agent instance ready for use.

        Raises:
            ValueError: If configuration is invalid for this strategy.
        """

    def llm(
        self,
        rt: RuntimeContext,
        *,
        name: str,
        role: RoleConfig | None = None,
        description: str | None = None,
    ) -> LlmAgent:
        """Build an LlmAgent from runtime config with optional role overrides.

        Args:
            rt: Shared runtime configuration.
            name: Agent name.
            role: Per-role overrides; non-None fields win over rt defaults.
            description: Agent description; defaults to rt.description.

        Returns:
            A configured LlmAgent.
        """
        role = role or RoleConfig()
        return LlmAgent(
            name=name,
            model=role.model if role.model is not None else rt.model,
            description=description if description is not None else rt.description,
            instruction=role.instruction if role.instruction is not None else rt.instruction,
            tools=role.tools if role.tools is not None else (rt.tools or []),
            code_executor=rt.code_executor,
            state_schema=rt.state_schema,
            output_schema=rt.output_schema,
            output_key=rt.output_key,
            before_agent_callback=rt.before_agent_callback,
            after_agent_callback=rt.after_agent_callback,
        )

    def validate(self, context: AgentStrategyContext) -> None:
        """Validate strategy-specific configuration requirements.

        Override in subclasses to enforce constraints. Raise ValueError if
        configuration is invalid.

        Args:
            context: The strategy context to validate.

        Raises:
            ValueError: If required configuration is missing or invalid.
        """
