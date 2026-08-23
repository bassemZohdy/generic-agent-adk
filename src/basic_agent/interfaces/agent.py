"""Serving entry for the ADK api server (ADR-003 Phase B scope note).

The ADK ``AgentLoader`` discovers agents under the ``agents_dir`` passed to
``get_fast_api_app`` — ``src/basic_agent/interfaces`` — by importing
``interfaces.agent`` (absolute-import-safe module) and reading ``root_agent``
from it.  This module defers to ``basic_agent.agent.get_root_agent()`` so the
configured use-case preset **compiled to a graph Workflow** is what the REST
API actually serves.  The attribute stays lazy (PEP 562) so simply importing
this module has no runtime side effects — the compiled root is built on the
first access, exactly like ``basic_agent.agent.root_agent``.
"""

from __future__ import annotations

from typing import Any

_loaded: Any = None


def __getattr__(name: str) -> Any:
    if name == "root_agent":
        global _loaded
        if _loaded is None:
            from basic_agent.agent import get_root_agent

            _loaded = get_root_agent()
        return _loaded
    raise AttributeError(name)
