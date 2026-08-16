"""Small, import-cycle-free utilities shared across the package.

Every function here has zero imports from the rest of ``basic_agent`` so
it can be used anywhere without introducing cycles.
"""

from __future__ import annotations

_PRODUCTION_DEPLOYMENTS = frozenset(
    {"prod", "production", "staging", "cloud-run", "cloudrun"}
)


def is_production(deployment: str) -> bool:
    """Return ``True`` when ``deployment`` names a production-like environment.

    Used by every interface adapter (REST, Live, auth-gateway, service-api)
    and the use-case custom-module loader to gate documentation routes and
    enforce allowlist requirements.
    """
    return deployment.lower() in _PRODUCTION_DEPLOYMENTS


def split_csv(value: str) -> list[str]:
    """Split a comma-separated string into stripped, non-empty parts.

    Used by ``config.py`` (env var parsing) and ``config_loader.py``
    (YAML/env override merging) — both previously had their own identical
    implementations (``_roles`` and ``_split_names`` respectively).
    """
    return [part.strip() for part in value.split(",") if part.strip()]
