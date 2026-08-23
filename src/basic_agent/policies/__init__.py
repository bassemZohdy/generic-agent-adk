"""Cross-cutting policies (ADR-005 §4).

Policies are declarative, topology-independent behavior: they apply to any
preset or raw graph, unlike the use-case-specific hooks they replaced.
"""

from __future__ import annotations

from .approval import (
    UNCONDITIONAL_TOOLS,
    apply_approval_policy,
    is_unconditional_tool,
    iter_llm_agents,
    make_approval_before_tool,
)
from .synthesis import (
    SYNTHESIZER_INSTRUCTION,
    SYNTHESIZER_NAME,
    SYNTHESIZER_OUTPUT_KEY,
    SYNTHESIZER_STATE_KEY,
    synthesizer_node,
    with_synthesis,
)

__all__ = [
    "SYNTHESIZER_INSTRUCTION",
    "SYNTHESIZER_NAME",
    "SYNTHESIZER_OUTPUT_KEY",
    "SYNTHESIZER_STATE_KEY",
    "UNCONDITIONAL_TOOLS",
    "apply_approval_policy",
    "is_unconditional_tool",
    "iter_llm_agents",
    "make_approval_before_tool",
    "synthesizer_node",
    "with_synthesis",
]
