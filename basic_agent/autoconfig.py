"""Stack-agnostic capability discovery with deterministic fallback chains."""

from __future__ import annotations

from dataclasses import dataclass
import logging
import os
from pathlib import Path
from typing import Mapping
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


class ProviderConfigurationError(ValueError):
    """Raised when a detected provider has invalid required configuration."""


@dataclass(frozen=True)
class CapabilityProvider:
    """Resolved provider contract; SDK clients remain behind this boundary."""

    capability: str
    strategy: str
    configuration: Mapping[str, str]

    @property
    def name(self) -> str:
        return f"{self.capability}:{self.strategy}"


def _value(environment: Mapping[str, str], name: str) -> str | None:
    value = environment.get(name)
    return value.strip() if value and value.strip() else None


def _detected(environment: Mapping[str, str], *names: str) -> bool:
    return any(_value(environment, name) is not None for name in names)


def _require(
    environment: Mapping[str, str], capability: str, strategy: str, *names: str
) -> dict[str, str]:
    values: dict[str, str] = {}
    missing: list[str] = []
    for name in names:
        value = _value(environment, name)
        if value is None:
            missing.append(name)
        else:
            values[name] = value
    if missing:
        raise ProviderConfigurationError(
            f"Detected {capability} provider '{strategy}', but required "
            f"configuration is missing: {', '.join(missing)}"
        )
    return values


def _url(value: str, capability: str, strategy: str) -> None:
    parsed = urlparse(value)
    if not parsed.scheme or not parsed.netloc:
        raise ProviderConfigurationError(
            f"Detected {capability} provider '{strategy}', but its URL is invalid: {value!r}"
        )


def _path(value: str, capability: str, strategy: str) -> str:
    path = Path(value).expanduser()
    if path.name in {"", ".", ".."}:
        raise ProviderConfigurationError(
            f"Detected {capability} provider '{strategy}', but its path is invalid: {value!r}"
        )
    return str(path)


class _ProviderSpec:
    capability: str
    strategy: str

    @classmethod
    def discover(cls, environment: Mapping[str, str]) -> CapabilityProvider | None:
        raise NotImplementedError


class CloudStorageProvider(_ProviderSpec):
    capability = "storage"
    strategy = "cloud"

    @classmethod
    def discover(cls, environment: Mapping[str, str]) -> CapabilityProvider | None:
        if not _detected(environment, "STORAGE_BUCKET"):
            return None
        values = _require(environment, cls.capability, cls.strategy, "STORAGE_BUCKET")
        bucket = values["STORAGE_BUCKET"]
        if "/" in bucket or " " in bucket:
            raise ProviderConfigurationError(f"Invalid storage bucket: {bucket!r}")
        return CapabilityProvider(cls.capability, cls.strategy, values)


class DatabaseStorageProvider(_ProviderSpec):
    capability = "storage"
    strategy = "database"

    @classmethod
    def discover(cls, environment: Mapping[str, str]) -> CapabilityProvider | None:
        if not _detected(environment, "DATABASE_URL"):
            return None
        values = _require(environment, cls.capability, cls.strategy, "DATABASE_URL")
        _url(values["DATABASE_URL"], cls.capability, cls.strategy)
        return CapabilityProvider(cls.capability, cls.strategy, values)


class LocalDiskStorageProvider(_ProviderSpec):
    capability = "storage"
    strategy = "local_disk"

    @classmethod
    def discover(cls, environment: Mapping[str, str]) -> CapabilityProvider | None:
        if not _detected(environment, "STORAGE_PATH"):
            return None
        values = _require(environment, cls.capability, cls.strategy, "STORAGE_PATH")
        values["STORAGE_PATH"] = _path(values["STORAGE_PATH"], cls.capability, cls.strategy)
        return CapabilityProvider(cls.capability, cls.strategy, values)


class CloudMessagingProvider(_ProviderSpec):
    capability = "messaging"
    strategy = "cloud"

    @classmethod
    def discover(cls, environment: Mapping[str, str]) -> CapabilityProvider | None:
        if not _detected(environment, "MESSAGING_URL"):
            return None
        values = _require(environment, cls.capability, cls.strategy, "MESSAGING_URL")
        _url(values["MESSAGING_URL"], cls.capability, cls.strategy)
        return CapabilityProvider(cls.capability, cls.strategy, values)


class LocalBrokerMessagingProvider(_ProviderSpec):
    capability = "messaging"
    strategy = "local_broker"

    @classmethod
    def discover(cls, environment: Mapping[str, str]) -> CapabilityProvider | None:
        if not _detected(environment, "BROKER_URL"):
            return None
        values = _require(environment, cls.capability, cls.strategy, "BROKER_URL")
        _url(values["BROKER_URL"], cls.capability, cls.strategy)
        return CapabilityProvider(cls.capability, cls.strategy, values)


class CloudCachingProvider(_ProviderSpec):
    capability = "caching"
    strategy = "cloud"

    @classmethod
    def discover(cls, environment: Mapping[str, str]) -> CapabilityProvider | None:
        if not _detected(environment, "CACHE_URL", "REDIS_URL"):
            return None
        name = "CACHE_URL" if _value(environment, "CACHE_URL") else "REDIS_URL"
        values = _require(environment, cls.capability, cls.strategy, name)
        _url(values[name], cls.capability, cls.strategy)
        return CapabilityProvider(cls.capability, cls.strategy, values)


class LocalDiskCachingProvider(_ProviderSpec):
    capability = "caching"
    strategy = "local_disk"

    @classmethod
    def discover(cls, environment: Mapping[str, str]) -> CapabilityProvider | None:
        if not _detected(environment, "CACHE_PATH"):
            return None
        values = _require(environment, cls.capability, cls.strategy, "CACHE_PATH")
        values["CACHE_PATH"] = _path(values["CACHE_PATH"], cls.capability, cls.strategy)
        return CapabilityProvider(cls.capability, cls.strategy, values)


class CloudSearchProvider(_ProviderSpec):
    capability = "search"
    strategy = "cloud"

    @classmethod
    def discover(cls, environment: Mapping[str, str]) -> CapabilityProvider | None:
        if not _detected(environment, "SEARCH_URL", "SEARCH_API_KEY"):
            return None
        values = _require(environment, cls.capability, cls.strategy, "SEARCH_URL", "SEARCH_API_KEY")
        _url(values["SEARCH_URL"], cls.capability, cls.strategy)
        return CapabilityProvider(cls.capability, cls.strategy, values)


class LocalIndexSearchProvider(_ProviderSpec):
    capability = "search"
    strategy = "local_index"

    @classmethod
    def discover(cls, environment: Mapping[str, str]) -> CapabilityProvider | None:
        if not _detected(environment, "SEARCH_INDEX_PATH"):
            return None
        values = _require(environment, cls.capability, cls.strategy, "SEARCH_INDEX_PATH")
        values["SEARCH_INDEX_PATH"] = _path(values["SEARCH_INDEX_PATH"], cls.capability, cls.strategy)
        return CapabilityProvider(cls.capability, cls.strategy, values)


class CloudLoggingProvider(_ProviderSpec):
    capability = "logging"
    strategy = "cloud"

    @classmethod
    def discover(cls, environment: Mapping[str, str]) -> CapabilityProvider | None:
        if not _detected(environment, "LOG_ENDPOINT", "LOG_API_KEY"):
            return None
        values = _require(environment, cls.capability, cls.strategy, "LOG_ENDPOINT", "LOG_API_KEY")
        _url(values["LOG_ENDPOINT"], cls.capability, cls.strategy)
        return CapabilityProvider(cls.capability, cls.strategy, values)


class LocalFileLoggingProvider(_ProviderSpec):
    capability = "logging"
    strategy = "local_file"

    @classmethod
    def discover(cls, environment: Mapping[str, str]) -> CapabilityProvider | None:
        if not _detected(environment, "LOG_FILE"):
            return None
        values = _require(environment, cls.capability, cls.strategy, "LOG_FILE")
        values["LOG_FILE"] = _path(values["LOG_FILE"], cls.capability, cls.strategy)
        return CapabilityProvider(cls.capability, cls.strategy, values)


_FALLBACK_CHAINS: Mapping[str, tuple[type[_ProviderSpec], ...]] = {
    "storage": (CloudStorageProvider, DatabaseStorageProvider, LocalDiskStorageProvider),
    "messaging": (CloudMessagingProvider, LocalBrokerMessagingProvider),
    "caching": (CloudCachingProvider, LocalDiskCachingProvider),
    "search": (CloudSearchProvider, LocalIndexSearchProvider),
    "logging": (CloudLoggingProvider, LocalFileLoggingProvider),
}


def discover_capabilities(
    environment: Mapping[str, str] | None = None,
) -> dict[str, CapabilityProvider]:
    """Resolve each capability to its highest-priority satisfied strategy."""
    if environment is None:
        environment = os.environ
    resolved: dict[str, CapabilityProvider] = {}
    for capability, chain in _FALLBACK_CHAINS.items():
        selected = next(
            (provider for spec in chain if (provider := spec.discover(environment))),
            CapabilityProvider(capability, "in_memory", {}),
        )
        resolved[capability] = selected
        logger.info("Resolved %s capability to %s", capability, selected.name)
    return resolved
