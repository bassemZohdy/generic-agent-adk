"""Shared test seams for immutable runtime settings."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

import pytest


@pytest.fixture
def settings_patch(monkeypatch):
    """Patch a module's frozen settings snapshot and restore it automatically."""

    def patch(module: Any, **changes: Any):
        updated = replace(module.settings, **changes)
        monkeypatch.setattr(module, "settings", updated)
        return updated

    return patch
