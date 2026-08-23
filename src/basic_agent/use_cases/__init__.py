"""Public use-case layer: ADR-005 presets and their registry.

Use cases are presets (metadata + graph-spec builders) compiled by the
``compile`` layer; the per-use-case facade classes and the strategy layer
were removed in E3.  Public crate: catalog metadata, alias resolution,
``AGENT_USE_CASE_MODULE`` custom preset loading, and runtime assembly via
``Preset.build``.
"""

from __future__ import annotations

from ..presets import PRESETS, Preset
from .registry import (
    UseCaseRegistry,
    get_default_registry,
    load_custom_use_cases,
)

__all__ = [
    "PRESETS",
    "Preset",
    "UseCaseRegistry",
    "get_default_registry",
    "load_custom_use_cases",
]
