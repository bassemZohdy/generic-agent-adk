# TODO

Pluggable code-execution sandbox — design recorded in
[ADR-004](docs/ADR-004-pluggable-code-execution.md); implementation tracked
here. Work through in order; each is independently reviewable. Tasks 1-4 and
7-9 are the minimum viable slice (Docker + hardened container limits +
Gemini-built-in + settings plumbing + graceful "unavailable" + telling the
model); task 6 (`unsafe_local`) is small enough to bundle in alongside 7 even
though it isn't required for Docker+Gemini+unavailable to work. 5
(GCP-managed providers) and 10 (Compose wiring) can ship later without
blocking the rest — without 10, the Docker strategy's `probe()` will
correctly resolve to "unavailable" in the default local Compose stack (no
socket reachable from `adk-api` yet) rather than doing anything unsafe.

1. [ ] **Scaffold `src/basic_agent/code_execution.py`.** `_CodeExecutionProviderSpec`
   base class (`probe(environment, *, model) -> bool`,
   `build(environment) -> BaseCodeExecutor`), `CodeExecutionResolution`
   dataclass (`executor`, `strategy`, `detail`), and
   `resolve_code_executor(environment, *, model)` entrypoint implementing
   the explicit-override-then-auto-detect chain from ADR-004 §2. Contract:
   `probe()` is a pure `bool` — it never raises, for anything (missing
   package, unreachable daemon, invalid config are all `False`).
   `ProviderConfigurationError` (reuse `autoconfig.py`'s class) is raised
   by the **resolver**, not by `probe()` — and only on the
   explicit-override path (unknown strategy name, or an explicitly
   selected strategy whose `probe()` returned `False`). This resolves the
   ambiguity of a probe that "raises only when explicitly selected": the
   probe can't know which path is calling it, and the auto-detect chain
   must be able to call the same method bare. Ship with only the
   `unavailable` fallback wired so this task stays small; real providers
   land in tasks 2-6.

2. [ ] **`DockerContainerCodeExecutionProvider`.** Live probe:
   `docker.DockerClient(base_url=..., timeout=1).ping()` — the ~1s
   timeout must be set on the **constructor** (the docker SDK default is
   60s, which would blow the startup budget) — against the default socket
   or `AGENT_CODE_EXECUTION_DOCKER_HOST`/`DOCKER_HOST`. **The `docker`
   import must be deferred inside `probe()`/`build()` within
   `try/except ImportError`**: in ADK 2.6.3, even
   `from google.adk.code_executors import ContainerCodeExecutor` raises
   `ImportError: … pip install "google-adk[extensions]"` through the
   package's lazy `__getattr__` when `docker` isn't installed, so a
   module-level import in `code_execution.py` would crash agent startup
   on every Docker-less deployment (Cloud Run) — the exact failure this
   design exists to prevent. Missing package or unreachable daemon →
   `probe()` returns `False`, never raises. `build()` returns the
   hardened subclass from task 3 — do not override its
   `network_enabled=False` / dropped-capabilities defaults (ADR-004 §5).
   Add `docker` as an **optional** dependency in `pyproject.toml`: a
   minimal extra containing just the `docker` SDK (sufficient because the
   lazy import chain only needs `import docker` to succeed; task 5's GCP
   providers add their own extra when they ship, rather than pulling
   ADK's broader `extensions` extra now) — not a hard dependency.

3. [ ] **Hardened `ContainerCodeExecutor` subclass.** Verified against
   installed ADK 2.6.3: `ContainerCodeExecutor` starts containers with
   only `image`, `detach`, `tty`, `network_disabled`,
   `cap_drop=['ALL']`, `security_opt=['no-new-privileges']` — it exposes
   **no** CPU/memory/pids limits at all (its only knobs are `base_url`,
   `image`, `docker_path`, `network_enabled`; `BaseCodeExecutor` adds
   only `timeout_seconds`, default `None`). Docker defaults therefore
   mean a fork bomb or memory-exhaustion loop in model-generated code can
   take down the host. Thin subclass overriding container creation to add
   explicit `mem_limit`, `nano_cpus`, `pids_limit`, `read_only=True`
   (plus a small `tmpfs` for `/tmp`, which read-only Python execution
   needs). Keep `network_disabled`/`cap_drop`/`security_opt` exactly as
   ADK ships them. (This replaces the original task-12 bullet "confirm
   ContainerCodeExecutor's CPU/memory/timeout limits are set explicitly"
   — that confirmation can only fail; the knobs don't exist, so we add
   them.)

   **Second, separate finding, verified in the same file:**
   `execute_code()` calls `self._container.exec_run([...], demux=True)`
   with no timeout argument anywhere, and `timeout_seconds` (the
   `BaseCodeExecutor` field) is never read by this class — grep confirms
   zero occurrences of "timeout" in `container_code_executor.py`. Setting
   `timeout_seconds` on the instance is a no-op for this executor; an
   infinite loop in model-generated code hangs the `exec_run` call
   server-side forever. The subclass must also override `execute_code()`
   itself to enforce a real wall-clock timeout — run `exec_run` in a
   background thread, join with `self.timeout_seconds`, and on timeout
   kill/restart the (long-lived, reused-across-calls per
   `__init_container`) container rather than leaving it in an unknown
   state for the next call in the same session.

4. [ ] **`GeminiBuiltInCodeExecutionProvider`.** Wraps the existing
   `BuiltInCodeExecutor`. `probe()` = the resolved model
   (`models.resolve_model()`'s return value) is a native Gemini string,
   not a `LiteLlm` instance, **and** is Gemini 2.0+/EAP: ADK enforces the
   version check per request (`process_llm_request` →
   `is_gemini_eap_or_2_or_above` from
   `google.adk.code_executors.code_execution_utils`), so a native
   `gemini-1.5-*` string passes an isinstance-only probe and then blows
   up mid-run. Reuse ADK's own predicate (or mirror it) inside `probe()`
   so the misconfiguration fails at resolution time instead of during
   the first invocation. This is today's only behavior (`agent.py`'s
   `BuiltInCodeExecutor() if "code_execution" in configured else None`
   line in `_build_runtime_context`), now one path among several instead
   of the only one.

5. [ ] **GCP-managed providers (`vertex_ai`, `agent_engine_sandbox`, `gke`) —
   lower priority, can ship after 1-4+8-9.** Each requires an explicit
   code-execution resource identifier (project +
   extension/agent-engine/cluster name) to even attempt — no ambient
   auto-detection, so `probe()` is just "required identifiers present"
   (same as `autoconfig.py`'s other cloud providers, which don't
   live-probe either). The probes must key on the code-execution-specific
   fields only, **never** on `GCP_PROJECT` alone — that var already
   drives application integration (`agent.py`'s
   `_build_application_integration_toolset` guard) and must not
   incidentally activate a code-execution strategy for existing
   integration users. Add the corresponding settings and their own
   optional-dependency extra.

6. [ ] **`unsafe_local` — explicit-override-only, never auto-detected.**
   Reachable only via `AGENT_CODE_EXECUTION_STRATEGY=unsafe_local`; not in
   the auto-detect chain under any circumstance. Log a `logger.warning`
   naming the risk every time it's selected — same "dangerous needs a named
   opt-in" rule as `AUTH_DISABLED=true`/`DEMO_MODE=true` elsewhere in this
   codebase.

7. [ ] **Settings/config plumbing.** `config.py`: `code_execution_strategy`
   (explicit override), `code_execution_docker_host`, GCP resource-id
   fields from task 5. `config_loader.py`: YAML equivalents under
   `execution.code_execution.*` (mirror the `tools.skills.*` pattern added
   this session). `.env.example`: `AGENT_CODE_EXECUTION_STRATEGY`,
   `AGENT_CODE_EXECUTION_DOCKER_HOST`, plus the GCP fields.

8. [ ] **Wire `resolve_code_executor()` into `agent.py`.** Replace the
   hardcoded `BuiltInCodeExecutor() if "code_execution" in configured else
   None` line in `_build_runtime_context` with a call to
   `resolve_code_executor(...)`. Thread the resolved `strategy`/`detail`
   through so task 9 can use it — `RuntimeContext` (`strategies/base.py`)
   already has a `code_executor` field, so add sibling field(s) (e.g.
   `code_execution_strategy`) rather than inventing a parallel return
   shape; it already carries similar cross-cutting fields like
   `specialists`/`roles`.

9. [ ] **Tell the model, not just the operator.** Extend `inspect_runtime()`'s
   `capabilities` dict (currently built from `discover_capabilities()`) with
   a `code_execution` entry from the resolution's `strategy`. Separately,
   append one generated line to the agent instruction in
   `_build_runtime_context` — same pattern already used there for the
   untrusted-content warning — stating either "Code execution runs in an
   isolated sandbox (`<strategy>`)." or "Code execution was requested but no
   sandbox is currently available; do not claim to execute code." Also add
   the resolved strategy to `GenericAgentPlugin.before_run_callback`'s
   existing `adk.capabilities` span attribute so traces carry it too.

10. [ ] **`docker-compose.yml`: narrowly-scoped socket access for sandbox
     containers.** The existing `docker-socket-proxy` service
     (`tecnativa/docker-socket-proxy:0.3.0`) is read-only (`POST: "0"`,
     built for Traefik's container discovery) and must **not** be reused —
     container creation is a materially different trust boundary. Add a
     second docker-socket-proxy-style service scoped to `CONTAINERS=1`,
     `ALLOW_START=1`, `ALLOW_STOP=1`, `ALLOW_RESTARTS=1`, `EXEC=1`,
     `IMAGES=1` and everything else off (`AUTH`, `SECRETS`, `SERVICES`,
     `NETWORKS`, `SWARM`, `CONFIGS`, `BUILD`, `COMMIT`, …), gated behind
     a new Compose profile (e.g. `code-exec`, following the
     `observability`/`live`/`demo` profile pattern). Put it on a
     **dedicated network with only the agent service attached**:
     `EXEC=1` + `ALLOW_RESTARTS=1` permit exec/create against *every*
     container on that daemon, so without network isolation the "no exec
     into unrelated containers" review point in task 13 fails by
     construction. Wire the agent service too — profile membership,
     network attachment, and
     `AGENT_CODE_EXECUTION_DOCKER_HOST=tcp://<proxy>:2375` — or the proxy
     ships half-done. While implementing, verify against the proxy's
     current version: the exact `POST`/`ALLOW_*` interaction, and whether
     image auto-pull (`POST /images/create`) is admitted by `IMAGES=1`
     or the sandbox image must be pre-pulled — ADR-004 §4 flags this as
     unverified, not assumed.

11. [ ] **Tests.** Provider probe/build unit tests (mock Docker client:
     success, unreachable, package-not-installed); resolution-chain
     priority tests (explicit override wins and fails loudly when broken
     via `ProviderConfigurationError`; auto-detect order; `unsafe_local`
     never auto-selected under any environment; native-but-pre-2.0 Gemini
     model resolves away from `gemini_built_in`); `_build_runtime_context`
     integration tests asserting the right executor type *and* the right
     instruction text per scenario (available / unavailable / explicit
     override). Write each slice's tests alongside tasks 1-4 and 8-9
     rather than batching them here; this task is the consolidation and
     final coverage check.

12. [ ] **Docs.** New README section on code-execution sandbox selection
     (mirror the Skills section added this session — concrete example,
     concrete tradeoff). `.env.example` entries from task 7. CHANGELOG
     entry. [ADR-004](docs/ADR-004-pluggable-code-execution.md) has already
     been reviewed and sharpened against the real ADK 2.6.3 source (§1's
     `probe()`/resolver contract, §2's lazy-import and Gemini-version
     details, §4's network isolation, §5's resource-limit and timeout
     findings) — this task is confirming the implementation actually
     matches that design, then checking off its Verification-section
     checklist item by item, not re-deriving it.

13. [ ] **Security review pass before shipping.** Confirm the new
     docker-socket-proxy scope + network isolation (task 10) can't be
     used for anything beyond ephemeral sandbox containers (no image
     build/commit, no exec into unrelated containers). Confirm the
     hardened limits from task 3 (`mem_limit`, `nano_cpus`, `pids_limit`,
     `read_only`) are actually present on a started sandbox container —
     inspect `docker inspect` output of a live container, don't trust the
     code path. Add a paragraph to README's production checklist about
     this new attack surface (matches the existing checklist's treatment
     of Keycloak/Trivy/pip-audit as things a production deployer must not
     skip).

Completed work is recorded in [CHANGELOG.md](CHANGELOG.md). Design decisions
are recorded as ADRs in [docs/](docs/).
