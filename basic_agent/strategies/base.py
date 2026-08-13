"""Base strategy interface and supporting types."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from google.adk.agents import Agent


@dataclass
class RuntimeContext:
    """Shared runtime resources and configuration for strategy execution."""

    model: str
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

    def validate(self, context: AgentStrategyContext) -> None:
        """Validate strategy-specific configuration requirements.

        Override in subclasses to enforce constraints. Raise ValueError if
        configuration is invalid.

        Args:
            context: The strategy context to validate.

        Raises:
            ValueError: If required configuration is missing or invalid.
        """
