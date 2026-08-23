"""Use-case registry: presets with alias resolution and custom-module loading."""

from __future__ import annotations

import importlib.util
import inspect
import logging
import os
import sys
import uuid
from pathlib import Path

from ..presets import PRESETS, Preset
from ..util import is_production

logger = logging.getLogger(__name__)

#: Env var pointing at a module whose ``PRESETS`` get registered.
CUSTOM_MODULE_ENV = "AGENT_USE_CASE_MODULE"
CUSTOM_MODULE_ALLOWLIST_ENV = "AGENT_USE_CASE_MODULE_ALLOWLIST"


class UseCaseRegistry:
    """Registry of use-case presets by canonical key and alias (case-insensitive).

    Built-ins are the ADR-005 presets (catalog metadata + graph-spec
    builders).  Custom modules via ``AGENT_USE_CASE_MODULE`` contribute
    additional presets by exposing a ``PRESETS`` dict of
    :class:`basic_agent.presets.Preset`.
    """

    def __init__(self) -> None:
        self._presets: dict[str, Preset] = {}
        self._preset_alias_to_key: dict[str, str] = {}

    def register(self, preset: Preset) -> None:
        """Register a preset under its key and aliases.

        Raises:
            ValueError: If the key or any alias is already registered.
        """
        key = preset.key.lower()
        if key in self._presets:
            raise ValueError(f"Use case {key!r} is already registered")
        for alias in preset.aliases:
            alias = alias.lower()
            if (
                alias in self._preset_alias_to_key
                and self._preset_alias_to_key[alias] != key
            ):
                raise ValueError(
                    f"Alias {alias!r} is already registered for "
                    f"{self._preset_alias_to_key[alias]!r}"
                )
            self._preset_alias_to_key[alias] = key
        self._presets[key] = preset
        logger.debug("Registered use case %r", key)

    def get(self, key: str) -> Preset:
        """Return the preset for a canonical key or alias (case-insensitive).

        Raises:
            ValueError: If the key is unknown; the message lists valid keys.
        """
        canonical = self._preset_alias_to_key.get(key.lower(), key.lower())
        try:
            return self._presets[canonical]
        except KeyError:
            valid = ", ".join(sorted(self._presets))
            raise ValueError(
                f"Unknown use case {key!r}. Valid use cases: {valid}"
            ) from None

    def resolve(self, key: str) -> tuple[str, Preset]:
        """Return ``(canonical_key, preset)``, revealing alias resolution."""
        canonical = self._preset_alias_to_key.get(key.lower(), key.lower())
        return canonical, self.get(canonical)

    def has(self, key: str) -> bool:
        """Return True if the key or alias resolves to a registered preset."""
        canonical = self._preset_alias_to_key.get(key.lower(), key.lower())
        return canonical in self._presets

    def list_use_cases(self) -> list[dict]:
        """Return catalog entries sorted by key: key, title, when_to_use, aliases, interfaces."""
        return self.list_presets()

    def get_preset(self, key: str) -> Preset:
        """Alias of :meth:`get` (preset-explicit surface)."""
        return self.get(key)

    def has_preset(self, key: str) -> bool:
        """Alias of :meth:`has` (preset-explicit surface)."""
        return self.has(key)

    def list_presets(self) -> list[dict]:
        """Return preset catalog entries sorted by key (same shape as
        ``list_use_cases``) — both are preset-backed after E3."""
        return [
            {
                "key": key,
                "title": preset.title,
                "when_to_use": preset.when_to_use,
                "aliases": list(preset.aliases),
                "interfaces": list(preset.interfaces),
            }
            for key, preset in sorted(self._presets.items())
        ]


_default_registry: UseCaseRegistry | None = None


def get_default_registry() -> UseCaseRegistry:
    """Get or create the default registry with the eight built-in presets.

    Reads ``AGENT_USE_CASE_MODULE`` at call time (not import time); when set,
    custom presets from that module are registered too.
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
    """Register the eight built-in ADR-005 presets."""
    for preset in PRESETS.values():
        registry.register(preset)


def load_custom_use_cases(
    module_path: str, registry: UseCaseRegistry | None = None
) -> list[str]:
    """Import a module file and register its additional presets.

    The module must expose ``PRESETS`` — a dict of
    :class:`basic_agent.presets.Preset` — or a single ``PRESET`` instance.
    (Pre-E3 ``BaseUseCaseAgent``-style modules are rejected with migration
    guidance; see TODO E3.)

    Args:
        module_path: Filesystem path to a ``.py`` module.
        registry: Target registry; defaults to the default registry.

    Returns:
        Sorted list of newly registered use-case keys.

    Raises:
        OSError: If the file cannot be loaded.
        ValueError: If the module does not expose presets, in production
            without an allowlist, or outside the allowlist.
        Exception: Import errors propagate (nothing is swallowed).
    """
    candidate = Path(module_path).expanduser().resolve()
    if not candidate.is_file():
        raise OSError(f"Custom use-case module does not exist: {candidate}")
    allowed_roots = tuple(
        Path(value).expanduser().resolve()
        for value in os.environ.get(CUSTOM_MODULE_ALLOWLIST_ENV, "").split(os.pathsep)
        if value.strip()
    )
    deployment = os.environ.get("DEPLOYMENT_ENV", "docker-compose")
    if is_production(deployment) and not allowed_roots:
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

    presets: dict[str, Preset] | None = getattr(module, "PRESETS", None)
    if presets is None and isinstance(getattr(module, "PRESET", None), Preset):
        presets = {module.PRESET.key: module.PRESET}
    if presets is None:
        legacy = [
            cls.__name__
            for _, cls in inspect.getmembers(module, inspect.isclass)
            if hasattr(cls, "use_case")
        ]
        raise ValueError(
            f"Custom use-case module {module_path!r} must expose a PRESETS "
            "dict of basic_agent.presets.Preset"
            + (
                f". It defines legacy BaseUseCaseAgent-style class(es) "
                f"{legacy} — migrate them to presets (TODO E3; the strategy/"
                "facade layers were removed)."
                if legacy
                else ""
            )
        )

    registered: list[str] = []
    for preset in presets.values():
        if not isinstance(preset, Preset):
            raise ValueError(  # noqa: TRY004 - actionable config error type
                f"Custom use-case module {module_path!r} PRESETS entries must "
                f"be basic_agent.presets.Preset; got {type(preset).__name__}"
            )
        if registry.has(preset.key):
            continue  # already registered
        registry.register(preset)
        registered.append(preset.key)
        logger.info("Registered custom preset %r from %s", preset.key, module_path)
    return sorted(registered)
