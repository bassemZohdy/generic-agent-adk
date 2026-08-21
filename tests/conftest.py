import os
import shutil
import tempfile
import uuid
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

_LOCAL_TMP = Path(__file__).resolve().parent.parent / ".pytest_working_dir"
_LOCAL_TMP.mkdir(parents=True, exist_ok=True)
tempfile.tempdir = str(_LOCAL_TMP)
os.environ["TMP"] = str(_LOCAL_TMP)
os.environ["TEMP"] = str(_LOCAL_TMP)


@pytest.fixture
def tmp_path():
    """Workspace-contained temporary directory for tests without tempdir sandbox issues."""
    sub = _LOCAL_TMP / f"t-{uuid.uuid4().hex}"
    sub.mkdir(parents=True, exist_ok=True)
    try:
        yield sub
    finally:
        shutil.rmtree(sub, ignore_errors=True)


@pytest.fixture
def tmpdir(tmp_path):
    """Compatibility fixture for pytest tmpdir."""
    return tmp_path


@pytest.fixture
def settings_patch(monkeypatch):
    """Patch a module's frozen settings snapshot and restore it automatically."""

    def patch(module: Any, **changes: Any):
        effective_changes = dict(changes)
        if (
            "keycloak_issuer" in effective_changes
            and "keycloak_jwks_url" not in effective_changes
        ):
            issuer = effective_changes["keycloak_issuer"]
            effective_changes["keycloak_jwks_url"] = (
                f"{issuer.rstrip('/')}/protocol/openid-connect/certs"
                if issuer
                else ""
            )

        target = module.settings if hasattr(module, "settings") else module
        updated = replace(target, **effective_changes)
        if hasattr(module, "settings"):
            monkeypatch.setattr(module, "settings", updated)

        from basic_agent import auth
        from basic_agent.interfaces import live, rest

        if module in (rest, live) or (
            hasattr(module, "__name__")
            and module.__name__
            in ("basic_agent.interfaces.rest", "basic_agent.interfaces.live")
        ):
            auth_updated = replace(auth.core.settings, **effective_changes)
            monkeypatch.setattr(auth.core, "settings", auth_updated)

        return updated

    return patch
