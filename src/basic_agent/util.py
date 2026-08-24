"""Small, import-cycle-free utilities shared across the package.

Every function here has zero imports from the rest of ``basic_agent`` so
it can be used anywhere without introducing cycles.
"""

from __future__ import annotations

import os
from pathlib import Path

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


def resolve_allowlisted_file(module_path: str, allowlist_env: str, noun: str) -> Path:
    """Validate a custom-module path against its allowlist environment.

    Shared by the custom-use-case and custom-graph-function loaders so the
    filesystem resolution, production allowlist requirement, and containment
    check cannot drift between them.

    Args:
        module_path: Filesystem path to a ``.py`` module.
        allowlist_env: Environment variable holding ``os.pathsep``-separated
            allowed root directories.
        noun: Human-readable loader kind used in error messages
            (e.g. ``"use cases"``, ``"graph functions"``).

    Returns:
        The fully-resolved module path.

    Raises:
        OSError: If the file does not exist.
        ValueError: If a production-like deployment sets no allowlist, or
            the module lies outside the configured allowlist roots.
    """
    candidate = Path(module_path).expanduser().resolve()
    if not candidate.is_file():
        raise OSError(f"Custom {noun} module does not exist: {candidate}")
    allowed_roots = tuple(
        Path(value).expanduser().resolve()
        for value in os.environ.get(allowlist_env, "").split(os.pathsep)
        if value.strip()
    )
    deployment = os.environ.get("DEPLOYMENT_ENV", "docker-compose")
    if is_production(deployment) and not allowed_roots:
        raise ValueError(
            f"{allowlist_env} is required before loading custom {noun} in {deployment}"
        )
    if allowed_roots and not any(
        candidate == root or root in candidate.parents for root in allowed_roots
    ):
        raise ValueError(
            f"Custom {noun} module {candidate} is outside the configured "
            f"{allowlist_env}"
        )
    return candidate


def split_csv(value: str) -> list[str]:
    """Split a comma-separated string into stripped, non-empty parts.

    Used by ``config.py`` (env var parsing) and ``config_loader.py``
    (YAML/env override merging) — both previously had their own identical
    implementations (``_roles`` and ``_split_names`` respectively).
    """
    return [part.strip() for part in value.split(",") if part.strip()]
