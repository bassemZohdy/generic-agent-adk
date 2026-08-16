"""Code-execution sandbox resolution (ADR-004)."""

from .resolver import (
    CE_FIELD_ENV_MAP,
    STRATEGY_ENV,
    UNAVAILABLE,
    CodeExecutionResolution,
    known_strategies,
    register,
    resolve_code_executor,
)

__all__ = [
    "CE_FIELD_ENV_MAP",
    "STRATEGY_ENV",
    "UNAVAILABLE",
    "CodeExecutionResolution",
    "known_strategies",
    "register",
    "resolve_code_executor",
]
