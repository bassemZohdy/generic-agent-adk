"""ADK composition compile layer (ADR-005 §3).

``compile/`` is the single sanctioned home for ADK composition-class
construction: the workflow compiler (``compile_graph``) plus the shared
LlmAgent builder.  The legacy sugar compiler was retired with F2 — the
workflow backend is the only backend.
"""

from __future__ import annotations

from .llm_node import build_llm_agent
from .workflow import compile_graph

__all__ = ["build_llm_agent", "compile_graph"]
