"""Small, import-cycle-free utilities shared across the package.

Every function here has zero imports from the rest of ``basic_agent`` so
it can be used anywhere without introducing cycles.
"""

from __future__ import annotations

import os
from pathlib import Path

#: Explicitly non-production deployments that skip the allowlist requirement
#: and cookie-security/docs-route gating.  Any ``DEPLOYMENT_ENV`` value not
#: in this set — including unrecognized values and a fully unset variable —
#: is treated as production (H09, H16: fail closed).
_NON_PRODUCTION_DEPLOYMENTS = frozenset(
    {"docker-compose", "dev", "development", "test", "local"}
)


def is_production(deployment: str | None) -> bool:
    """Return ``True`` when *deployment* is NOT explicitly non-production.

    Fail closed: only deployments in :data:`_NON_PRODUCTION_DEPLOYMENTS`
    are exempt; unrecognized values (e.g. ``prod-us``) and ``None`` (unset
    ``DEPLOYMENT_ENV``) are treated as production (H09, H16).

    Used by every interface adapter (REST, Live, auth-gateway, service-api)
    and the custom-module allowlist gate.
    """
    if deployment is None:
        return True
    return deployment.lower() not in _NON_PRODUCTION_DEPLOYMENTS


def _is_within_root(candidate: Path, root: Path) -> bool:
    """Check if *candidate* is the same path as *root* or a descendant.

    Uses ``os.path.samefile`` so the comparison is correct on
    case-insensitive filesystems (macOS APFS) where pure ``Path`` equality
    would fail for paths differing only in case (H10).
    """
    try:
        if os.path.samefile(candidate, root):
            return True
    except (OSError, ValueError):
        if candidate == root:
            return True
    for parent in candidate.parents:
        try:
            if os.path.samefile(parent, root):
                return True
        except (OSError, ValueError):
            if parent == root:
                return True
    return False


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
        ValueError: If a production-like deployment (or unset
            ``DEPLOYMENT_ENV``) sets no allowlist, or the module lies
            outside the configured allowlist roots.
    """
    candidate = Path(module_path).expanduser().resolve()
    if not candidate.is_file():
        raise OSError(f"Custom {noun} module does not exist: {candidate}")
    allowed_roots = tuple(
        Path(value.strip()).expanduser().resolve()
        for value in os.environ.get(allowlist_env, "").split(os.pathsep)
        if value.strip()
    )
    deployment = os.environ.get("DEPLOYMENT_ENV")
    # H09: unset DEPLOYMENT_ENV requires allowlist (fail closed — only
    # explicitly non-production deployments skip the requirement).
    if (deployment is None or is_production(deployment)) and not allowed_roots:
        raise ValueError(
            f"{allowlist_env} is required before loading custom {noun}"
            + (f" in {deployment}" if deployment is not None else "")
        )
    if allowed_roots and not any(
        _is_within_root(candidate, root) for root in allowed_roots
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
