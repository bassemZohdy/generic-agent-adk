"""Pluggable code-execution sandbox resolution (ADR-004).

Resolves which ``BaseCodeExecutor`` (if any) the agent should attach when
the ``code_execution`` tool flag is enabled. Mirrors ``autoconfig.py``'s
fallback-chain shape, but with a stronger probe contract: providers declare
whether their backend is usable *right now* (a live, cheap liveness check
for Docker; identifier presence for cloud resources), resolved once at
startup.

Import discipline (ADR-004 §2): ADK's ``google.adk.code_executors`` package
resolves ``ContainerCodeExecutor``/``GkeCodeExecutor``/``VertexAiCodeExecutor``
/``AgentEngineSandboxCodeExecutor`` lazily and raises ``ImportError`` when
their optional dependencies are missing. Nothing in this module may import
those (or the ``docker`` SDK) at module scope — every optional import lives
inside ``probe()``/``build()`` behind ``try/except ImportError`` so that
Docker-less deployments (Cloud Run) import this module cleanly.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Mapping

from .autoconfig import ProviderConfigurationError

logger = logging.getLogger(__name__)

#: Environment variable holding an explicit strategy override.
STRATEGY_ENV = "AGENT_CODE_EXECUTION_STRATEGY"

#: Strategy reported when no provider probe succeeds (no executor attached).
UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class CodeExecutionResolution:
    """Resolved code-execution sandbox for one agent build.

    ``executor`` is ``None`` if and only if ``strategy`` is ``unavailable``.
    ``detail`` carries human-readable provenance ("explicit override",
    "auto-detected", …) for logs and telemetry.
    """

    executor: Any | None
    strategy: str
    detail: str = ""


class _CodeExecutionProviderSpec:
    """Base contract for one code-execution strategy (ADR-004 §1).

    Providers are stateless classmethod-only specs: ``probe()`` answers
    "usable right now?", ``build()`` constructs the executor. The split
    exists because the same ``probe()`` is called bare during auto-detect
    (where "not available" must be a quiet ``False``) and by the resolver
    during an explicit selection (where the identical ``False`` becomes a
    loud ``ProviderConfigurationError``) — the probe cannot know which
    caller is asking, so raising must live one level up.
    """

    strategy: str

    #: Message logged as a warning every time this strategy is selected
    #: explicitly. The "dangerous needs a named opt-in" convention
    #: (``AUTH_DISABLED``/``DEMO_MODE``); ``unsafe_local`` uses it (P4).
    warn_on_select: str | None = None

    @classmethod
    def probe(cls, environment: Mapping[str, str], *, model: Any) -> bool:
        """Return whether this provider is usable with this environment.

        Contract: a pure ``bool`` that NEVER raises — missing package,
        unreachable daemon, and invalid configuration are all ``False``.
        """
        raise NotImplementedError

    @classmethod
    def build(cls, environment: Mapping[str, str]) -> Any:
        """Construct the ``BaseCodeExecutor`` for this strategy."""
        raise NotImplementedError


#: All known provider specs, keyed by strategy name.
_PROVIDERS: dict[str, type[_CodeExecutionProviderSpec]] = {}

#: Auto-detect chain, in try order. ``unsafe_local`` is never a member.
_AUTO_DETECT_ORDER: tuple[str, ...] = ()


def register(spec: type[_CodeExecutionProviderSpec], *, auto: bool = False) -> None:
    """Register a provider spec; ``auto=True`` also appends it to the
    auto-detect chain (registration order = chain order)."""
    global _AUTO_DETECT_ORDER
    _PROVIDERS[spec.strategy] = spec
    if auto:
        _AUTO_DETECT_ORDER = (*_AUTO_DETECT_ORDER, spec.strategy)


def known_strategies() -> tuple[str, ...]:
    """Return the registered strategy names, sorted, for error messages."""
    return tuple(sorted(_PROVIDERS))


def resolve_code_executor(
    environment: Mapping[str, str], *, model: Any
) -> CodeExecutionResolution:
    """Resolve the code-execution strategy for this build (ADR-004 §2).

    Order:

    1. **Explicit override** — ``AGENT_CODE_EXECUTION_STRATEGY``: use exactly
       that provider; unknown names and failed probes raise
       ``ProviderConfigurationError`` rather than silently falling through
       (mirrors ``AGENT_CONFIG_FILE``'s fail-fast contract).
    2. **Auto-detect** — first provider in registration order whose
       ``probe()`` returns ``True`` wins.
    3. **Unavailable** — no executor; the model is told plainly (P6).

    Args:
        environment: Fresh environment mapping (os.environ + YAML overlay).
        model: The resolved model (native Gemini string or LiteLlm instance)
            — some probes key on it.

    Returns:
        A ``CodeExecutionResolution``; never ``None``.

    Raises:
        ProviderConfigurationError: An explicit override names an unknown
            strategy, or a known one whose probe failed.
    """
    explicit = (environment.get(STRATEGY_ENV) or "").strip()
    if explicit:
        spec = _PROVIDERS.get(explicit)
        if spec is None:
            raise ProviderConfigurationError(
                f"Unknown code-execution strategy {explicit!r}; "
                f"known: {', '.join(known_strategies()) or '(none registered)'}"
            )
        if not spec.probe(environment, model=model):
            raise ProviderConfigurationError(
                f"Code-execution strategy {explicit!r} is explicitly configured "
                "but unavailable (probe failed); fix its configuration or unset "
                f"{STRATEGY_ENV}"
            )
        if spec.warn_on_select:
            logger.warning("%s", spec.warn_on_select)
        return CodeExecutionResolution(
            spec.build(environment), spec.strategy, "explicit override"
        )
    for name in _AUTO_DETECT_ORDER:
        spec = _PROVIDERS[name]
        if spec.probe(environment, model=model):
            return CodeExecutionResolution(
                spec.build(environment), name, "auto-detected"
            )
    logger.info(
        "No code-execution sandbox available; resolving to '%s'", UNAVAILABLE
    )
    return CodeExecutionResolution(None, UNAVAILABLE, "no provider probe succeeded")
