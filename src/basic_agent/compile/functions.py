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


class _FunctionRegistry(dict):
    """Dict subclass that can carry a load-error attribute (H18)."""

    _load_error: Exception | None = None


def load_custom_functions(
    module_path: str,
    functions: dict[str, Callable[..., Any]] | None = None,
    sources: dict[str, str] | None = None,
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
        sources: Optional name → origin mapping for collision logging (H07).

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
    sources = {} if sources is None else sources

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
            origin = sources.get(name, "a previously registered source")
            logger.info(
                "Custom graph function %r skipped: already registered by %s",
                name,
                origin,
            )
            continue
        functions[name] = func
        sources[name] = str(module_path)
        registered.append(name)
        logger.info("Registered custom graph function %r from %s", name, module_path)
    return sorted(registered)


def custom_function_registry() -> dict[str, Callable[..., Any]]:
    """Build a function registry seeded with the built-ins plus any module.

    Reads ``AGENT_FUNCTION_MODULE`` at call time (not import time); when set,
    the module's ``FUNCTIONS`` are loaded into a copy of
    :data:`DEFAULT_FUNCTION_REGISTRY`.  Built-in and reserved names can never
    be shadowed (H02).

    H03: a bad/missing module logs a warning and returns the built-in
    registry only, so presets/graphs that don't reference custom functions
    still serve normally.  H17: the load error is stored in
    :data:`_last_load_error` so :func:`check_custom_function_error` can
    surface it when a graph actually needs a custom function.

    H06: NOT memoized — reads env on every call so that changing
    ``AGENT_FUNCTION_MODULE`` mid-process is reflected immediately.
    The ``get_root_agent()`` singleton already ensures at most one build
    per process in production.

    Returns:
        Registry suitable for :func:`compile_graph`'s ``function_registry``.
        If the module failed to load, the error is attached as
        ``_load_error`` attribute on the returned dict (H18: scoped to the
        call, not a module global).
    """
    from .workflow import DEFAULT_FUNCTION_REGISTRY

    functions: dict[str, Callable[..., Any]] = _FunctionRegistry(
        DEFAULT_FUNCTION_REGISTRY
    )
    sources: dict[str, str] = {name: "built-in" for name in DEFAULT_FUNCTION_REGISTRY}
    module_path = os.environ.get(CUSTOM_FUNCTION_MODULE_ENV)
    if module_path:
        try:
            load_custom_functions(module_path, functions=functions, sources=sources)
        except Exception as exc:
            functions._load_error = exc
            logger.warning(
                "Failed to load custom graph-function module %r; "
                "serving built-in functions only",
                module_path,
                exc_info=True,
            )
    return functions


def check_custom_function_error(
    name: str, registry: dict[str, Callable[..., Any]]
) -> None:
    """Re-raise the module load error if *name* is an unresolvable custom function (H17).

    Called by :func:`compile.workflow._resolve_function` when a function name
    is not found in the registry.  If the module failed to load and the name
    is not a built-in, the original actionable error is raised instead of the
    generic "requires options.function" message.

    H18: the error is read from the *registry* dict's ``_load_error``
    attribute (set by :func:`custom_function_registry`), not a module
    global, so unrelated ``compile_graph()`` calls are unaffected.
    """
    from .workflow import DEFAULT_FUNCTION_REGISTRY

    load_error = getattr(registry, "_load_error", None)
    if load_error is not None and name not in DEFAULT_FUNCTION_REGISTRY:
        raise ValueError(
            f"Custom graph function {name!r} is unavailable because "
            f"{CUSTOM_FUNCTION_MODULE_ENV} failed to load; see log for details"
        ) from load_error


__all__ = [
    "CUSTOM_FUNCTION_ALLOWLIST_ENV",
    "CUSTOM_FUNCTION_MODULE_ENV",
    "_RESERVED_FUNCTION_NAMES",
    "check_custom_function_error",
    "custom_function_registry",
    "load_custom_functions",
]
