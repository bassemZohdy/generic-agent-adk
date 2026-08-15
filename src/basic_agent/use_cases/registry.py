"""Use-case registry with alias resolution and custom-module loading."""

from __future__ import annotations

import importlib.util
import inspect
import logging
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING
import uuid

if TYPE_CHECKING:
    from .base import BaseUseCaseAgent

logger = logging.getLogger(__name__)

#: Env var pointing at a module whose BaseUseCaseAgent subclasses get registered.
CUSTOM_MODULE_ENV = "AGENT_USE_CASE_MODULE"
CUSTOM_MODULE_ALLOWLIST_ENV = "AGENT_USE_CASE_MODULE_ALLOWLIST"


class UseCaseRegistry:
    """Registry of use-case agents by canonical key and alias (case-insensitive)."""

    def __init__(self) -> None:
        self._use_cases: dict[str, BaseUseCaseAgent] = {}
        self._alias_to_key: dict[str, str] = {}

    def register(self, instance: BaseUseCaseAgent) -> None:
        """Register a use-case agent instance under its key and aliases.

        Raises:
            ValueError: If the key or any alias is already registered.
        """
        key = instance.use_case.lower()
        if key in self._use_cases:
            raise ValueError(f"Use case {key!r} is already registered")
        for alias in instance.aliases:
            alias = alias.lower()
            if alias in self._alias_to_key and self._alias_to_key[alias] != key:
                raise ValueError(
                    f"Alias {alias!r} is already registered for "
                    f"{self._alias_to_key[alias]!r}"
                )
            self._alias_to_key[alias] = key
        self._use_cases[key] = instance
        logger.debug("Registered use case %r", key)

    def get(self, key: str) -> BaseUseCaseAgent:
        """Return the use case for a canonical key or alias (case-insensitive).

        Raises:
            ValueError: If the key is unknown; the message lists valid keys.
        """
        canonical = self._alias_to_key.get(key.lower(), key.lower())
        try:
            return self._use_cases[canonical]
        except KeyError:
            valid = ", ".join(sorted(self._use_cases))
            raise ValueError(
                f"Unknown use case {key!r}. Valid use cases: {valid}"
            ) from None

    def resolve(self, key: str) -> tuple[str, BaseUseCaseAgent]:
        """Return ``(canonical_key, instance)``, revealing alias resolution."""
        canonical = self._alias_to_key.get(key.lower(), key.lower())
        return canonical, self.get(canonical)

    def has(self, key: str) -> bool:
        """Return True if the key or alias resolves to a registered use case."""
        canonical = self._alias_to_key.get(key.lower(), key.lower())
        return canonical in self._use_cases

    def list_use_cases(self) -> list[dict]:
        """Return catalog entries sorted by key: key, title, when_to_use, aliases, interfaces."""
        return [
            {
                "key": key,
                "title": instance.title,
                "when_to_use": instance.when_to_use,
                "aliases": list(instance.aliases),
                "interfaces": list(instance.interfaces),
            }
            for key, instance in sorted(self._use_cases.items())
        ]


_default_registry: UseCaseRegistry | None = None


def get_default_registry() -> UseCaseRegistry:
    """Get or create the default registry with the nine built-ins registered.

    Reads ``AGENT_USE_CASE_MODULE`` at call time (not import time); when set,
    custom use cases from that module are registered too.
    """
    global _default_registry

    if _default_registry is None:
        _default_registry = UseCaseRegistry()
        _register_builtins(_default_registry)
        module_path = os.environ.get(CUSTOM_MODULE_ENV)
        if module_path:
            load_custom_use_cases(module_path, registry=_default_registry)
    return _default_registry


def _register_builtins(registry: UseCaseRegistry) -> None:
    """Register the eight built-in use cases (imports here avoid cycles)."""
    from .approval_gate import ApprovalGateAgent
    from .assistant import AssistantAgent
    from .expert_dispatch import ExpertDispatchAgent
    from .multi_perspective import MultiPerspectiveAgent
    from .pipeline import PipelineAgent
    from .plan_and_execute import PlanAndExecuteAgent
    from .refine_until_good import RefineUntilGoodAgent
    from .team_coordinator import TeamCoordinatorAgent

    for instance in (
        AssistantAgent(),
        PipelineAgent(),
        MultiPerspectiveAgent(),
        RefineUntilGoodAgent(),
        ExpertDispatchAgent(),
        TeamCoordinatorAgent(),
        PlanAndExecuteAgent(),
        ApprovalGateAgent(),
    ):
        registry.register(instance)


def load_custom_use_cases(
    module_path: str, registry: UseCaseRegistry | None = None
) -> list[str]:
    """Import a module file and register its new BaseUseCaseAgent subclasses.

    Args:
        module_path: Filesystem path to a ``.py`` module.
        registry: Target registry; defaults to the default registry.

    Returns:
        Sorted list of newly registered use-case keys.

    Raises:
        OSError: If the file cannot be loaded.
        Exception: Import errors propagate (nothing is swallowed).

    Classes without a ``use_case`` key set are skipped.
    """
    from .base import BaseUseCaseAgent

    candidate = Path(module_path).expanduser().resolve()
    if not candidate.is_file():
        raise OSError(f"Custom use-case module does not exist: {candidate}")
    allowed_roots = tuple(
        Path(value).expanduser().resolve()
        for value in os.environ.get(CUSTOM_MODULE_ALLOWLIST_ENV, "").split(os.pathsep)
        if value.strip()
    )
    deployment = os.environ.get("DEPLOYMENT_ENV", "docker-compose").lower()
    production = deployment in {"prod", "production", "staging", "cloud-run", "cloudrun"}
    if production and not allowed_roots:
        raise ValueError(
            f"{CUSTOM_MODULE_ALLOWLIST_ENV} is required before loading custom use cases in "
            f"{deployment}"
        )
    if allowed_roots and not any(
        candidate == root or root in candidate.parents for root in allowed_roots
    ):
        raise ValueError(
            f"Custom use-case module {candidate} is outside the configured "
            f"{CUSTOM_MODULE_ALLOWLIST_ENV}"
        )

    registry = registry if registry is not None else get_default_registry()
    module_uuid = uuid.uuid5(uuid.NAMESPACE_URL, str(candidate)).hex
    module_name = f"custom_use_cases_{module_uuid}"
    spec = importlib.util.spec_from_file_location(module_name, candidate)
    if spec is None or spec.loader is None:
        raise ValueError(f"Cannot load use-case module from {module_path!r}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)

    registered: list[str] = []
    members = inspect.getmembers(module, inspect.isclass)
    for _, cls in members:
        if not issubclass(cls, BaseUseCaseAgent) or cls is BaseUseCaseAgent:
            continue
        if not getattr(cls, "use_case", ""):
            continue  # abstract-ish subclass without a key
        if registry.has(cls.use_case):
            continue  # already registered
        instance = cls()
        registry.register(instance)
        registered.append(instance.use_case)
        logger.info("Registered custom use case %r from %s", instance.use_case, module_path)
    return sorted(registered)
