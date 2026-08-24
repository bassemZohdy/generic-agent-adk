"""Custom graph-function loading (G01): the ``options.function`` extension point.

Mirrors the custom-use-case surface (``use_cases/registry.py``): an operator
module exposes a dict of callables and is registered into
:func:`compile_graph`'s function registry via two environment variables.
The allowlist/production rules are shared with the use-case loader through
:func:`basic_agent.util.resolve_allowlisted_file`.
"""

from __future__ import annotations

import importlib.util
import logging
import os
import sys
import uuid
from collections.abc import Callable
from typing import Any

from ..util import resolve_allowlisted_file

logger = logging.getLogger(__name__)

#: Env var pointing at a module whose ``FUNCTIONS`` get registered.
CUSTOM_FUNCTION_MODULE_ENV = "AGENT_FUNCTION_MODULE"
#: Env var holding the allowed root directories for that module.
CUSTOM_FUNCTION_ALLOWLIST_ENV = "AGENT_FUNCTION_MODULE_ALLOWLIST"

#: Names that custom modules may never override, even if they are not in
#: ``DEFAULT_FUNCTION_REGISTRY`` (e.g. ``plan_execute``, which is handled
#: by a hardcoded branch in ``_resolve_function`` — H01).
_RESERVED_FUNCTION_NAMES = frozenset({"plan_execute"})

#: Cached result of :func:`custom_function_registry` (H06).
_cached_registry: dict[str, Callable[..., Any]] | None = None


def load_custom_functions(
    module_path: str,
    functions: dict[str, Callable[..., Any]] | None = None,
) -> list[str]:
    """Import a module file and return its additional graph functions.

    The module must expose ``FUNCTIONS`` — a dict mapping node names to
    plain callables.  Entries whose name collides with a built-in function
    (from ``DEFAULT_FUNCTION_REGISTRY``), a reserved name (``plan_execute``),
    or an already-loaded custom entry are skipped, so a module can never
    override built-in behavior or win over an earlier module — regardless of
    what the caller seeds into *functions* (H02).

    Args:
        module_path: Filesystem path to a ``.py`` module.
        functions: Registry to merge into; defaults to empty.

    Returns:
        Sorted list of newly registered function names.

    Raises:
        OSError: If the file cannot be loaded or does not exist.
        ValueError: If the module does not expose a ``FUNCTIONS`` dict of
            callables, in production without an allowlist, or outside the
            allowlist.
        Exception: Import errors propagate (nothing is swallowed).
    """
    from .workflow import DEFAULT_FUNCTION_REGISTRY

    candidate = resolve_allowlisted_file(
        module_path, CUSTOM_FUNCTION_ALLOWLIST_ENV, "graph-function"
    )
    functions = {} if functions is None else functions

    module_uuid = uuid.uuid5(uuid.NAMESPACE_URL, str(candidate)).hex
    module_name = f"custom_graph_functions_{module_uuid}"
    spec = importlib.util.spec_from_file_location(module_name, candidate)
    if spec is None or spec.loader is None:
        raise ValueError(f"Cannot load graph-function module from {module_path!r}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        # H08: clean up sys.modules on partial import failure so a broken
        # module doesn't leave a half-initialized entry behind.
        sys.modules.pop(module_name, None)
        raise

    entries = getattr(module, "FUNCTIONS", None)
    if not isinstance(entries, dict):
        raise ValueError(  # noqa: TRY004 - actionable config error type
            f"Custom graph-function module {module_path!r} must expose a "
            "FUNCTIONS dict of callables"
        )

    # H02: the collision set always includes built-ins and reserved names,
    # regardless of what the caller seeded into *functions*.
    reserved = set(DEFAULT_FUNCTION_REGISTRY) | _RESERVED_FUNCTION_NAMES

    registered: list[str] = []
    for name, func in entries.items():
        if not callable(func):
            raise ValueError(  # noqa: TRY004 - actionable config error type
                f"Custom graph-function module {module_path!r} FUNCTIONS "
                f"entries must be callables; {name!r} is "
                f"{type(func).__name__}"
            )
        if not isinstance(name, str) or not name.strip():
            raise ValueError(
                f"Custom graph-function module {module_path!r} FUNCTIONS keys "
                "must be non-empty strings"
            )
        # H07: name the real source of the collision.
        if name in reserved:
            logger.info(
                "Custom graph function %r skipped: collides with a built-in "
                "or reserved function name",
                name,
            )
            continue
        if name in functions:
            logger.info(
                "Custom graph function %r skipped: already registered",
                name,
            )
            continue
        functions[name] = func
        registered.append(name)
        logger.info("Registered custom graph function %r from %s", name, module_path)
    return sorted(registered)


def custom_function_registry() -> dict[str, Callable[..., Any]]:
    """Build a function registry seeded with the built-ins plus any module.

    Reads ``AGENT_FUNCTION_MODULE`` at call time (not import time); when set,
    the module's ``FUNCTIONS`` are loaded into a copy of
    :data:`DEFAULT_FUNCTION_REGISTRY`.  Built-in and reserved names can never
    be shadowed (H02).  The result is memoized per process (H06).

    H03: a bad/missing module logs a warning and returns the built-in
    registry only, so presets/graphs that don't reference custom functions
    still serve normally.

    Returns:
        Registry suitable for :func:`compile_graph`'s ``function_registry``.
    """
    global _cached_registry
    if _cached_registry is not None:
        return _cached_registry

    from .workflow import DEFAULT_FUNCTION_REGISTRY

    functions: dict[str, Callable[..., Any]] = {**DEFAULT_FUNCTION_REGISTRY}
    module_path = os.environ.get(CUSTOM_FUNCTION_MODULE_ENV)
    if module_path:
        try:
            load_custom_functions(module_path, functions=functions)
        except Exception:
            logger.warning(
                "Failed to load custom graph-function module %r; "
                "serving built-in functions only",
                module_path,
                exc_info=True,
            )
    _cached_registry = functions
    return functions


def _reset_cache() -> None:
    """Reset the memoized registry (test helper)."""
    global _cached_registry
    _cached_registry = None


__all__ = [
    "CUSTOM_FUNCTION_ALLOWLIST_ENV",
    "CUSTOM_FUNCTION_MODULE_ENV",
    "_RESERVED_FUNCTION_NAMES",
    "_reset_cache",
    "custom_function_registry",
    "load_custom_functions",
]
