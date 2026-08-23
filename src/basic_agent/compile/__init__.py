"""ADK composition compile layer (ADR-005 §3; TODO Phase C3).

After C3, ``compile/`` is the single sanctioned home for ADK composition-
class construction: ``compile_workflow`` (full graph specs) and
``compile_legacy`` (sugar subset, rollback-only).  The backend is selected
by ``AGENT_COMPOSE_BACKEND`` (default ``workflow`` per ADR-005; the legacy
compile target is rollback-only for one release).
"""

from __future__ import annotations

import os

from .legacy import compile_legacy
from .llm_node import build_llm_agent
from .workflow import compile_graph

COMPOSE_BACKEND_WORKFLOW = "workflow"
COMPOSE_BACKEND_LEGACY = "legacy"
_DEFAULT_COMPOSE_BACKEND = COMPOSE_BACKEND_WORKFLOW
_VALID_COMPOSE_BACKENDS = (COMPOSE_BACKEND_WORKFLOW, COMPOSE_BACKEND_LEGACY)

__all__ = [
    "COMPOSE_BACKEND_LEGACY",
    "COMPOSE_BACKEND_WORKFLOW",
    "build_llm_agent",
    "compile_graph",
    "compile_legacy",
    "compose_backend",
]


def compose_backend() -> str:
    """Return the active backend selection (fail-fast on unknown values)."""
    raw = (
        os.environ.get("AGENT_COMPOSE_BACKEND", _DEFAULT_COMPOSE_BACKEND)
        .strip()
        .lower()
    )
    if raw not in _VALID_COMPOSE_BACKENDS:
        raise ValueError(
            f"AGENT_COMPOSE_BACKEND must be 'workflow' or 'legacy'; got {raw!r}"
        )
    return raw
