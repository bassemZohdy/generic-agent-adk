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

import atexit
import logging
import os
import threading
from dataclasses import dataclass
from typing import Any, Mapping

from google.adk.code_executors.code_execution_utils import CodeExecutionResult

from ..autoconfig import ProviderConfigurationError

logger = logging.getLogger(__name__)

#: Optional GCP-managed sandbox resource identifiers (TODO P7). Probes key
#: on these fields ONLY — never on ``GCP_PROJECT``/``GOOGLE_CLOUD_PROJECT``
#: alone, which already drive application integration and must not
#: incidentally activate a code-execution strategy.
VERTEX_RESOURCE_ENV = "AGENT_CODE_EXECUTION_VERTEX_RESOURCE"
AGENT_ENGINE_RESOURCE_ENV = "AGENT_CODE_EXECUTION_AGENT_ENGINE_RESOURCE"
GKE_KUBECONFIG_PATH_ENV = "AGENT_CODE_EXECUTION_GKE_KUBECONFIG_PATH"
GKE_KUBECONFIG_CONTEXT_ENV = "AGENT_CODE_EXECUTION_GKE_KUBECONFIG_CONTEXT"

#: Environment variable holding an explicit strategy override.
STRATEGY_ENV = "AGENT_CODE_EXECUTION_STRATEGY"

#: Mapping from ``ExecutionCodeExecutionConfig`` field names to their
#: environment-variable equivalents, consumed by ``agent.py`` when building
#: the resolver overlay. Single source of truth — the old hardcoded tuple
#: in ``agent.py`` was a duplication risk.
CE_FIELD_ENV_MAP: tuple[tuple[str, str], ...] = (
    ("strategy", "AGENT_CODE_EXECUTION_STRATEGY"),
    ("docker_host", "AGENT_CODE_EXECUTION_DOCKER_HOST"),
    ("docker_image", "AGENT_CODE_EXECUTION_DOCKER_IMAGE"),
    ("vertex_resource", "AGENT_CODE_EXECUTION_VERTEX_RESOURCE"),
    ("agent_engine_resource", "AGENT_CODE_EXECUTION_AGENT_ENGINE_RESOURCE"),
    ("gke_kubeconfig_path", "AGENT_CODE_EXECUTION_GKE_KUBECONFIG_PATH"),
    ("gke_kubeconfig_context", "AGENT_CODE_EXECUTION_GKE_KUBECONFIG_CONTEXT"),
)

#: Optional Docker daemon endpoint; falls back to ``DOCKER_HOST``.
DOCKER_HOST_ENV = "AGENT_CODE_EXECUTION_DOCKER_HOST"

#: Optional sandbox image override (TODO Appendix B).
DOCKER_IMAGE_ENV = "AGENT_CODE_EXECUTION_DOCKER_IMAGE"

#: Default sandbox image. ADK publishes none (TODO Appendix B): official
#: python images are maintained, scanned, and verified to run under the
#: full hardened constraint set (read-only rootfs + tmpfs + no caps).
DEFAULT_SANDBOX_IMAGE = "python:3.13-slim"

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


# ── GCP-managed strategies (TODO P7) ─────────────────────────────────────────
#
# Probes are identifier-presence only — no live probing, same rule as
# autoconfig.py's other cloud providers. Auto-detect order puts these ahead
# of docker_container/gemini_built_in (see the registration block at the
# bottom of this module).


class VertexAiCodeExecutionProvider(_CodeExecutionProviderSpec):
    """``vertex_ai`` strategy: Vertex Code Interpreter Extension."""

    strategy = "vertex_ai"

    @classmethod
    def probe(cls, environment: Mapping[str, str], *, model: Any) -> bool:
        return bool((environment.get(VERTEX_RESOURCE_ENV) or "").strip())

    @classmethod
    def build(cls, environment: Mapping[str, str]) -> Any:
        from google.adk.code_executors import VertexAiCodeExecutor  # deferred

        return VertexAiCodeExecutor(
            resource_name=environment.get(VERTEX_RESOURCE_ENV)
        )


class AgentEngineSandboxCodeExecutionProvider(_CodeExecutionProviderSpec):
    """``agent_engine_sandbox`` strategy: Vertex AI Agent Engine sandbox."""

    strategy = "agent_engine_sandbox"

    @classmethod
    def probe(cls, environment: Mapping[str, str], *, model: Any) -> bool:
        return bool((environment.get(AGENT_ENGINE_RESOURCE_ENV) or "").strip())

    @classmethod
    def build(cls, environment: Mapping[str, str]) -> Any:
        from google.adk.code_executors import (  # deferred
            AgentEngineSandboxCodeExecutor,
        )

        return AgentEngineSandboxCodeExecutor(
            agent_engine_resource_name=environment.get(AGENT_ENGINE_RESOURCE_ENV)
        )


class GkeCodeExecutionProvider(_CodeExecutionProviderSpec):
    """``gke`` strategy: gVisor-sandboxed Pods on GKE.

    Opt-in means naming an explicit kubeconfig file — in-cluster and
    default ``~/.kube/config`` auth are never auto-detected, mirroring the
    "identifier present" rule of the other GCP providers.
    """

    strategy = "gke"

    @classmethod
    def probe(cls, environment: Mapping[str, str], *, model: Any) -> bool:
        return bool((environment.get(GKE_KUBECONFIG_PATH_ENV) or "").strip())

    @classmethod
    def build(cls, environment: Mapping[str, str]) -> Any:
        from google.adk.code_executors import GkeCodeExecutor  # deferred

        return GkeCodeExecutor(
            kubeconfig_path=environment.get(GKE_KUBECONFIG_PATH_ENV),
            kubeconfig_context=(environment.get(GKE_KUBECONFIG_CONTEXT_ENV) or None),
        )


# Registration happens at the bottom of this module, after all classes are
# defined — the order of those calls defines the auto-detect chain.


_hardened_executor_cls: type | None = None


def _hardened_executor_cls_get() -> type:
    """Return the hardened executor class, defining it on first use.

    The class cannot live at module scope: subclassing
    ``ContainerCodeExecutor`` requires importing it, which (through ADK's
    lazy ``__getattr__``) imports the ``docker`` SDK and would crash agent
    startup on Docker-less deployments — the exact failure this module
    exists to prevent (ADR-004 §2).
    """
    global _hardened_executor_cls
    if _hardened_executor_cls is None:
        from google.adk.code_executors import ContainerCodeExecutor  # deferred

        class HardenedContainerCodeExecutor(ContainerCodeExecutor):
            """``ContainerCodeExecutor`` + resource limits, read-only
            rootfs, and a real execution timeout (ADR-004 §5).

            Over ADK 2.6.3 defaults (which already set ``network_disabled``,
            ``cap_drop=['ALL']``, ``no-new-privileges``) this adds
            ``mem_limit='512m'``, ``nano_cpus=1e9`` (1 CPU),
            ``pids_limit=128``, ``read_only=True`` and a ``/tmp`` tmpfs —
            without them, a fork bomb or memory-exhaustion loop in
            model-generated code can take down the host, and an infinite
            loop hangs ``exec_run`` forever (ADK never reads
            ``timeout_seconds`` for this executor).
            """

            def __init__(
                self,
                *,
                base_url: str | None = None,
                image: str | None = DEFAULT_SANDBOX_IMAGE,
                docker_path: str | None = None,
                mem_limit: str = "512m",
                nano_cpus: int = 1_000_000_000,
                pids_limit: int = 128,
                tmpfs_size: str = "64m",
                timeout_seconds: int = 60,
                **data: Any,
            ) -> None:
                import docker  # deferred (ADR-004 §2)

                data["timeout_seconds"] = timeout_seconds
                # Skip ContainerCodeExecutor.__init__: it would start an
                # *unhardened* container via a name-mangled __init_container
                # that no subclass can intercept. This mirrors the parent's
                # init (ADK 2.6.3) — re-verify on upgrade.
                super(ContainerCodeExecutor, self).__init__(**data)
                if not image and not docker_path:
                    raise ValueError(
                        "Either image or docker_path must be set."
                    )
                if self.stateful or self.optimize_data_file:
                    raise ValueError(
                        "Cannot set stateful/optimize_data_file=True."
                    )
                self.base_url = base_url
                self.image = image if image else DEFAULT_SANDBOX_IMAGE
                self.docker_path = (
                    os.path.abspath(docker_path) if docker_path else None
                )
                self._client = (
                    docker.DockerClient(base_url=base_url)
                    if base_url
                    else docker.from_env()
                )
                self._hardening: dict[str, Any] = {
                    "mem_limit": mem_limit,
                    "nano_cpus": nano_cpus,
                    "pids_limit": pids_limit,
                    "read_only": True,
                    "tmpfs": {"/tmp": f"size={tmpfs_size},rw"},
                }
                self._start_container()
                atexit.register(self._cleanup_container)

            def _start_container(self) -> None:
                """ADK's ``__init_container`` plus ``self._hardening``."""
                if self.docker_path:
                    self._build_docker_image()  # inherited from ADK
                self._container = self._client.containers.run(
                    image=self.image,
                    detach=True,
                    tty=True,
                    # ADK's own hardening, kept exactly as it ships it:
                    network_disabled=not self.network_enabled,
                    cap_drop=["ALL"],
                    security_opt=["no-new-privileges"],
                    **self._hardening,
                )
                self._verify_python_installation()  # inherited from ADK

            def _cleanup_container(self) -> None:
                if getattr(self, "_container", None):
                    try:
                        self._container.stop()
                        self._container.remove()
                    except Exception:
                        logger.debug(
                            "sandbox container cleanup failed", exc_info=True
                        )

            def _recover_container(self) -> None:
                """Kill and restart the reused container after a hung exec.

                ADK reuses one long-lived container across every
                ``exec_run`` in a session; without active recovery one hung
                execution degrades every subsequent call.

                Uses SIGKILL (``kill()``), not the graceful ``stop()`` of
                ``_cleanup_container``: docker-py's stop defaults to a 10s
                grace period, which would dominate recovery latency for an
                already-hung process (live-measured: 15.6s wall for a 5s
                timeout under stop()).
                """
                if getattr(self, "_container", None):
                    try:
                        self._container.kill()
                    except Exception:
                        logger.debug(
                            "sandbox container kill failed", exc_info=True
                        )
                    try:
                        self._container.remove()
                    except Exception:
                        logger.debug(
                            "sandbox container remove failed", exc_info=True
                        )
                self._start_container()

            def execute_code(self, invocation_context, code_execution_input):
                """Run the snippet under a real wall-clock timeout.

                ADK's implementation calls ``exec_run`` with no timeout and
                never reads ``timeout_seconds``; an infinite loop in
                model-generated code would hang forever. This runs the exec
                in a worker thread, joins with ``self.timeout_seconds``, and
                on timeout kills/restarts the container instead of leaving
                it in an unknown state.
                """
                timeout = self.timeout_seconds or 60
                result_box: dict[str, Any] = {}

                def _run() -> None:
                    try:
                        result_box["exec"] = self._container.exec_run(
                            ["python3", "-c", code_execution_input.code],
                            demux=True,
                        )
                    except Exception as error:  # container killed mid-exec
                        result_box["error"] = error

                worker = threading.Thread(target=_run, daemon=True)
                worker.start()
                worker.join(timeout)
                if worker.is_alive():
                    logger.warning(
                        "sandbox exec exceeded %ss; restarting container",
                        timeout,
                    )
                    self._recover_container()
                    return CodeExecutionResult(
                        stderr=f"Execution timed out after {timeout}s."
                    )
                if "error" in result_box:
                    return CodeExecutionResult(
                        stderr=f"Execution failed: {result_box['error']}"
                    )
                out = getattr(result_box.get("exec"), "output", None) or (
                    None,
                    None,
                )
                stdout = out[0].decode("utf-8", "replace") if out[0] else ""
                stderr = (
                    out[1].decode("utf-8", "replace")
                    if len(out) > 1 and out[1]
                    else ""
                )
                return CodeExecutionResult(stdout=stdout, stderr=stderr)

        _hardened_executor_cls = HardenedContainerCodeExecutor
    return _hardened_executor_cls


class DockerContainerCodeExecutionProvider(_CodeExecutionProviderSpec):
    """``docker_container`` strategy: local/reachable Docker daemon."""

    strategy = "docker_container"

    @classmethod
    def _docker_host(cls, environment: Mapping[str, str]) -> str | None:
        return (
            environment.get(DOCKER_HOST_ENV)
            or environment.get("DOCKER_HOST")
            or None
        )

    @classmethod
    def probe(cls, environment: Mapping[str, str], *, model: Any) -> bool:
        try:
            import docker
        except ImportError:
            return False
        try:
            host = cls._docker_host(environment)
            # The ~1s timeout must live on the constructor: the docker SDK
            # default is 60s, which would blow the startup budget on every
            # Docker-less deployment (ADR-004 §2.ii).
            client = (
                docker.DockerClient(base_url=host, timeout=1)
                if host
                else docker.from_env(timeout=1)
            )
            return bool(client.ping())
        except Exception:
            return False

    @classmethod
    def build(cls, environment: Mapping[str, str]) -> Any:
        return _hardened_executor_cls_get()(
            base_url=cls._docker_host(environment),
            image=(
                environment.get(DOCKER_IMAGE_ENV) or DEFAULT_SANDBOX_IMAGE
            ),
        )


# ── gemini_built_in strategy (TODO P3) ───────────────────────────────────────


class GeminiBuiltInCodeExecutionProvider(_CodeExecutionProviderSpec):
    """``gemini_built_in`` strategy: the model's own code-execution tool.

    This is the pre-P6 behavior (``agent.py``'s hardcoded
    ``BuiltInCodeExecutor()``), now one path among several.
    """

    strategy = "gemini_built_in"

    @classmethod
    def probe(cls, environment: Mapping[str, str], *, model: Any) -> bool:
        if not isinstance(model, str):
            # models.resolve_model() returns a LiteLlm instance for any
            # provider-prefixed model; built-in execution is native-Gemini
            # strings only.
            return False
        try:
            from google.adk.utils.model_name_utils import (
                is_gemini_eap_or_2_or_above,
            )
        except ImportError:
            return False
        # Mirror BuiltInCodeExecutor.process_llm_request's per-request gate:
        # ADK raises ValueError mid-run for pre-2.0 Gemini, so evaluating the
        # same predicate at resolution time turns that into a quiet
        # fall-through (auto-detect) or a loud ProviderConfigurationError
        # (explicit override) instead of a first-invocation crash.
        return bool(is_gemini_eap_or_2_or_above(model))

    @classmethod
    def build(cls, environment: Mapping[str, str]) -> Any:
        from google.adk.code_executors import BuiltInCodeExecutor  # eager, safe

        return BuiltInCodeExecutor()


# ── unsafe_local strategy (TODO P4) ──────────────────────────────────────────


class UnsafeLocalCodeExecutionProvider(_CodeExecutionProviderSpec):
    """``unsafe_local`` strategy: in-process execution, no isolation.

    Never auto-detected — reachable ONLY through an explicit
    ``AGENT_CODE_EXECUTION_STRATEGY=unsafe_local`` opt-in. Every selection
    logs a warning naming the risk, mirroring the ``AUTH_DISABLED`` /
    ``DEMO_MODE`` dangerous-needs-a-named-opt-in convention.
    """

    strategy = "unsafe_local"
    warn_on_select = (
        "unsafe_local code execution selected: model-generated code runs "
        "IN-PROCESS on the host with NO isolation"
    )

    @classmethod
    def probe(cls, environment: Mapping[str, str], *, model: Any) -> bool:
        return True  # always "available"; never in _AUTO_DETECT_ORDER

    @classmethod
    def build(cls, environment: Mapping[str, str]) -> Any:
        from google.adk.code_executors import UnsafeLocalCodeExecutor  # eager

        return UnsafeLocalCodeExecutor()


# ── Registration: this order IS the auto-detect chain (ADR-004 §2):
# GCP-managed sandboxes first (explicit identifiers present), then the
# local Docker daemon, then the model's built-in execution. unsafe_local is
# deliberately last and NOT auto — explicit-override-only.

register(VertexAiCodeExecutionProvider, auto=True)
register(AgentEngineSandboxCodeExecutionProvider, auto=True)
register(GkeCodeExecutionProvider, auto=True)
register(DockerContainerCodeExecutionProvider, auto=True)
register(GeminiBuiltInCodeExecutionProvider, auto=True)
register(UnsafeLocalCodeExecutionProvider)
