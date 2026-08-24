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


def load_custom_functions(
    module_path: str,
    functions: dict[str, Callable[..., Any]] | None = None,
) -> list[str]:
    """Import a module file and return its additional graph functions.

    The module must expose ``FUNCTIONS`` — a dict mapping node names to
    plain callables.  Entries whose name collides with an existing registry
    key (including the built-ins ``route_dispatch``/``aggregate_perspectives``
    and any already-loaded custom entry) are skipped, so a module can never
    override built-in behavior or win over an earlier module.

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
    spec.loader.exec_module(module)

    entries = getattr(module, "FUNCTIONS", None)
    if not isinstance(entries, dict):
        raise ValueError(  # noqa: TRY004 - actionable config error type
            f"Custom graph-function module {module_path!r} must expose a "
            "FUNCTIONS dict of callables"
        )

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
        if name in functions:
            logger.info(
                "Custom graph function %r skipped: %s already provides it",
                name,
                CUSTOM_FUNCTION_MODULE_ENV,
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
    :data:`DEFAULT_FUNCTION_REGISTRY`.  Built-in names can never be shadowed:
    the copy starts from the built-ins and :func:`load_custom_functions`
    skips colliding keys.

    Returns:
        Registry suitable for :func:`compile_graph`'s ``function_registry``.

    Raises:
        OSError: If the configured module cannot be loaded.
        ValueError: If the module violates the FUNCTIONS contract, is in
            production without an allowlist, or lies outside the allowlist.
    """
    from .workflow import DEFAULT_FUNCTION_REGISTRY

    functions: dict[str, Callable[..., Any]] = {**DEFAULT_FUNCTION_REGISTRY}
    module_path = os.environ.get(CUSTOM_FUNCTION_MODULE_ENV)
    if module_path:
        load_custom_functions(module_path, functions=functions)
    return functions


__all__ = [
    "CUSTOM_FUNCTION_ALLOWLIST_ENV",
    "CUSTOM_FUNCTION_MODULE_ENV",
    "custom_function_registry",
    "load_custom_functions",
]
