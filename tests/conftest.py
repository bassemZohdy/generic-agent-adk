import os
import tempfile
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

_LOCAL_TMP = Path(__file__).resolve().parent.parent / ".pytest_working_dir"
_LOCAL_TMP.mkdir(parents=True, exist_ok=True)
tempfile.tempdir = str(_LOCAL_TMP)
os.environ["TMP"] = str(_LOCAL_TMP)
os.environ["TEMP"] = str(_LOCAL_TMP)
os.environ["TMPDIR"] = str(_LOCAL_TMP)

# R05: no tmp_path/tmpdir overrides.  pytest's own basetemp hierarchy (kept
# under .pytest_working_dir once tempfile.tempdir is set) is managed with the
# default `tmp_path_retention_count` policy; rmtree-ing per-test dirs here
# leaked `t-<uuid>` folders on Windows when SQLite handles stayed open.

# R02: the only interface modules whose settings must also sync auth.core.
# Matched by module __name__ so settings_patch never imports rest/live eagerly
# (importing `rest` executes module-level create_app(), which creates .adk/
# directories and raises in a production environment).
_AUTH_SYNC_MODULES = ("basic_agent.interfaces.rest", "basic_agent.interfaces.live")


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
                f"{issuer.rstrip('/')}/protocol/openid-connect/certs" if issuer else ""
            )

        target = module.settings if hasattr(module, "settings") else module
        updated = replace(target, **effective_changes)
        if hasattr(module, "settings"):
            monkeypatch.setattr(module, "settings", updated)

        if getattr(module, "__name__", "") in _AUTH_SYNC_MODULES:
            # Lazy import: only reached when the patched module is one of the
            # interface modules, and only auth.core is needed for the sync.
            from basic_agent import auth

            auth_updated = replace(auth.core.settings, **effective_changes)
            monkeypatch.setattr(auth.core, "settings", auth_updated)

        return updated

    return patch


@pytest.fixture(autouse=True)
def _default_deployment_env(monkeypatch):
    """Default DEPLOYMENT_ENV to docker-compose for all tests (H09).

    Unset DEPLOYMENT_ENV now requires an allowlist (fail closed).  Tests
    that need a different value set it explicitly via monkeypatch.setenv.
    """
    monkeypatch.setenv("DEPLOYMENT_ENV", "docker-compose")


@pytest.fixture
def write_config(tmp_path, monkeypatch):
    """Write a YAML config file and set AGENT_CONFIG_FILE (H15: shared helper)."""

    def _write(content: str):
        config_file = tmp_path / "agent.yaml"
        config_file.write_text(content, encoding="utf-8")
        monkeypatch.setenv("AGENT_CONFIG_FILE", str(config_file))

    return _write
