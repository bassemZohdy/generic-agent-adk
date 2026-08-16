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

from .autoconfig import ProviderConfigurationError

logger = logging.getLogger(__name__)

#: Environment variable holding an explicit strategy override.
STRATEGY_ENV = "AGENT_CODE_EXECUTION_STRATEGY"

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


# ── docker_container strategy (TODO P2) ──────────────────────────────────────

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
                """
                self._cleanup_container()
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


register(DockerContainerCodeExecutionProvider, auto=True)
