# ADR-004 — Pluggable code-execution sandbox selection

**Status:** Accepted; implementation complete (P1–P11)
**Date:** 2026-08-16
**Scope:** code-execution resolution, runtime wiring, configuration, and
Docker Compose sandbox integration.

> Implementation note: this ADR was written before the 2026-08-16 source
> reorganization. The current implementation lives in
> `src/basic_agent/execution/resolver.py`, `src/basic_agent/agent.py`,
> `src/basic_agent/config/loader.py`, and `docker-compose.yml`; historical
> module names in the design narrative are retained for traceability.

## Context

`code_execution` is one of the `AGENT_TOOLS` capability flags (`agent.py`'s
`_SILENT_TOOL_NAMES`); when enabled, `_build_runtime_context` currently does:

```python
code_executor = (BuiltInCodeExecutor() if "code_execution" in configured else None,)
```

`BuiltInCodeExecutor` (`google.adk.code_executors`) does not execute
anything itself — it tells the *model* to use its own server-side code tool,
and raises `ValueError` for any model that isn't Gemini 2.0+. This project's
defining feature is multi-provider model support (OpenAI, Anthropic, Groq,
Ollama, … via LiteLLM — see `models.py`, ADR-002 addendum 2); the current
wiring means `code_execution` silently only works for the Gemini path, which
contradicts the project's own design goal.

Skills (ADR: none yet, see CHANGELOG 2026-08-16 "Native ADK Skills support")
made this concrete: `run_skill_script` needs *some* `BaseCodeExecutor`
attached to the agent, and skill scripts are exactly the kind of
model-generated-and-selected code that must run isolated from the host.

ADK ships six concrete `BaseCodeExecutor` implementations
(`google/adk/code_executors/`):

| Class | Isolation | Requires |
|---|---|---|
| `BuiltInCodeExecutor` | Google-hosted (Gemini's own tool) | Gemini 2.0+ model only |
| `ContainerCodeExecutor` | Docker container, network disabled + capabilities dropped by default | reachable Docker daemon |
| `GkeCodeExecutor` | gVisor-isolated K8s Job | GKE cluster config |
| `VertexAiCodeExecutor` | Vertex AI Code Interpreter Extension | GCP project + extension resource |
| `AgentEngineSandboxCodeExecutor` | Vertex AI Agent Engine sandbox | GCP project + Agent Engine resource |
| `UnsafeLocalCodeExecutor` | **none** — runs in-process on the host | nothing |

No single one fits every deployment target this project supports (local
Docker Compose, Cloud Run, arbitrary self-hosted). The right answer is the
same shape this codebase already uses for storage/cache/search/messaging/
logging in `autoconfig.py`: a fallback chain of provider specs, each
declaring whether its backend is actually usable *right now*, resolved once
at startup, with the resolution visible to both the operator (logs/
telemetry) and the model (system prompt).

## Decision

### 1. New provider abstraction, not a copy of `autoconfig.py`

`autoconfig.py`'s `_ProviderSpec.discover()` only checks *env var presence*
(`_detected()`) — it never dials out to confirm a backend is reachable.
Code execution needs a stronger guarantee ("if a Docker socket is provided
and it is available and working, use it") because silently handing the LLM
a code-execution tool backed by a dead socket is worse than not offering
one. So this gets its own module, `src/basic_agent/code_execution.py`, with
a `probe()` step that can perform a real (cheap, short-timeout) liveness
check, separate from `build()` which does the actual construction:

```python
class _CodeExecutionProviderSpec:
    strategy: str  # e.g. "docker_container", "gemini_built_in", "vertex_ai", ...

    @classmethod
    def probe(cls, environment: Mapping[str, str], *, model: str | LiteLlm) -> bool: ...

    @classmethod
    def build(cls, environment: Mapping[str, str]) -> BaseCodeExecutor: ...
```

`probe()` is a pure `bool` and must never raise, period — missing package,
unreachable socket, missing config are all `False`. `ProviderConfigurationError`
(reusing `autoconfig.py`'s class) is raised by the **resolver**, not by
`probe()` itself, and only on the explicit-override path (unknown strategy
name, or an explicitly selected strategy whose `probe()` returned `False`)
— same "explicit-but-broken fails loudly" rule already used for
`AGENT_CONFIG_FILE`. Splitting the raise out of `probe()` matters: the same
`probe()` method is called bare during auto-detect (where "not available"
must be a quiet `False`, tried-and-moved-on) and by the resolver during an
explicit selection (where the identical `False` result becomes a loud
error) — `probe()` itself has no way to know which caller it's answering,
so the raising has to live one level up.

### 2. Resolution order: explicit override, then auto-detect, never silently unsafe

```python
def resolve_code_executor(
    environment: Mapping[str, str], *, model: str | LiteLlm
) -> CodeExecutionResolution: ...
```

1. **Explicit override** — `AGENT_CODE_EXECUTION_STRATEGY` (env) or
   `execution.code_execution.strategy` (YAML). If set, use exactly that
   provider; if its `probe()` fails, raise `ProviderConfigurationError`
   rather than silently falling through (mirrors `AGENT_CONFIG_FILE`'s
   fail-fast contract).
2. **Auto-detect**, tried in this order, first `probe()==True` wins:
   1. `vertex_ai` / `agent_engine_sandbox` / `gke` — these require an
      explicit GCP resource identifier (project + resource name) to even
      attempt, so they only ever activate when the operator has already
      configured them; there's no ambient signal to auto-detect from.
      Their `probe()`s must key on code-execution-specific settings only —
      **never** on `GCP_PROJECT` alone. `agent.py`'s
      `_build_application_integration_toolset` already reads `GCP_PROJECT`
      for an unrelated capability (`application_integration`); reusing it
      here would silently activate a code-execution strategy for existing
      integration-only users who never asked for one.
   2. `docker_container` — probes a real Docker daemon: try
      `docker.DockerClient(base_url=..., timeout=1).ping()` (default
      socket, or `AGENT_CODE_EXECUTION_DOCKER_HOST` / `DOCKER_HOST` if
      set). The `~1s` timeout must be set on the **client constructor**,
      not assumed — the `docker` SDK's own default is 60s, which would
      blow the startup budget on every Docker-less deployment. Missing
      `docker` package or unreachable daemon → `False`, not a crash. This
      is the "if a Docker socket is provided and working, use it" case
      from the request that started this ADR.

      Import discipline matters here, verified against installed ADK
      2.6.3: `google.adk.code_executors` lazily resolves
      `ContainerCodeExecutor` via module `__getattr__`, and re-raises as
      `ImportError('ContainerCodeExecutor requires additional
      dependencies. Please install with: pip install
      "google-adk[extensions]"')` when `docker` isn't importable. A
      module-level `from google.adk.code_executors import
      ContainerCodeExecutor` in `code_execution.py` would therefore crash
      *agent startup* on every Docker-less deployment (Cloud Run) — the
      exact failure this ADR exists to prevent. The import must be
      deferred inside `probe()`/`build()`, wrapped in
      `try/except ImportError`.
   3. `gemini_built_in` — `probe()` returns true only when the *resolved*
      model (`models.resolve_model()`'s return value) is a native Gemini
      string, not a `LiteLlm` instance, **and** passes ADK's own
      `is_gemini_eap_or_2_or_above` check (`google.adk.code_executors.
      code_execution_utils`) — `BuiltInCodeExecutor.process_llm_request`
      enforces that version gate per request, so a native
      `gemini-1.5-*` string would pass an isinstance-only probe and then
      raise mid-invocation instead of at resolution time. Preserves
      today's behavior as one path in the new system instead of the only
      one.
   4. `unavailable` — no executor. The `code_execution` tool flag stays
      set (so `AGENT_TOOLS` config is honored) but no `BaseCodeExecutor` is
      attached; the agent is told plainly it cannot execute code (§3).
3. **`unsafe_local`** (`UnsafeLocalCodeExecutor`) is **never** in the
   auto-detect chain. It is reachable only via the explicit-override path
   (`AGENT_CODE_EXECUTION_STRATEGY=unsafe_local`), and every time it is
   selected the resolver logs a `logger.warning` naming the risk. Same
   "dangerous behavior needs a named, explicit opt-in" rule as
   `AUTH_DISABLED=true` and `DEMO_MODE=true` elsewhere in this codebase —
   never a fallback destination, only a deliberate choice.

### 3. Tell the model, not just the operator

`inspect_runtime()` already exposes `discover_capabilities()`'s resolved
strategies as a tool the model can call. Extend the same `capabilities`
dict with a `code_execution` entry from `CodeExecutionResolution.strategy`.
That alone isn't enough for the stated goal ("provide that way to the llm
in agent system prompt") — a tool the model *might* call is weaker than a
fact it's told upfront. So `_build_runtime_context` also appends one
generated line to the instruction, the same way it already prepends the
untrusted-content warning:

- Available: `"Code execution runs in an isolated sandbox (<strategy>)."`
- Unavailable: `"Code execution was requested but no sandbox is currently
  available; do not claim to execute code."`

### 4. `docker-compose.yml` needs its own, narrowly-scoped socket access

The existing `docker-socket-proxy` service is deliberately locked down
(`POST: "0"`) for Traefik's read-only container discovery — it must not be
reused for spinning up sandbox containers, which is a materially different
trust boundary (POST access to create/start/stop containers, vs. read-only
GET access to list them). This needs a **second**, separately-scoped
`tecnativa/docker-socket-proxy` instance (or equivalent) gated behind a new
Compose profile (e.g. `code-exec`), with only the container-lifecycle
surface enabled — confirmed available knobs: `CONTAINERS=1`,
`ALLOW_START=1`, `ALLOW_STOP=1`, `ALLOW_RESTARTS=1`, `EXEC=1`, `IMAGES=1`,
everything else (`AUTH`, `SECRETS`, `SERVICES`, `NETWORKS`, `SWARM`,
`CONFIGS`, `BUILD`, `COMMIT`, …) left at `0`. Exact `POST` interaction with
those `ALLOW_*` flags, and whether `IMAGES=1` admits the sandbox image's
auto-pull (`POST /images/create`) or the image must be pre-pulled into the
daemon, both need verification against the proxy's current version during
implementation — not assumed from this ADR.

> **Verified during implementation (proxy v0.3.0, from its `haproxy.cfg`
> and its own test suite):** the frontend's first ACL rule is
> `deny unless METH_GET || { env(POST) -m bool }` — `POST=1` is a **master
> switch** evaluated before every `ALLOW_*` rule and gates all non-GET
> methods (create/start/exec/DELETE). The knob list above therefore also
> needs `POST: "1"`; with `POST=0` the `ALLOW_*` flags admit nothing for
> writes. `POST=1` alone grants nothing either — sections stay
> deny-by-default. Auto-pull (`POST /images/create`) **is** admitted by
> `POST=1` + `IMAGES=1`; pre-pulling remains a hardening/latency choice,
> not a functional requirement. Landed in `docker-compose.yml` as
> `code-exec-socket-proxy` behind the `code-exec` profile.

This second proxy must sit on a **dedicated network with only the agent
service attached to it**. `EXEC=1` combined with `ALLOW_RESTARTS=1` grants
exec/create/kill against *every* container reachable on the daemon the
proxy fronts, not just ones the sandbox itself created — the proxy has no
concept of "containers this caller is allowed to touch." Without network
isolation, anything else on the same Docker host becomes reachable through
the sandbox tool, which fails the "no exec into unrelated containers" bar
in §Consequences and the task-13 security review by construction. The
`adk-api` service also needs to actually be wired to this — profile
membership, network attachment, and
`AGENT_CODE_EXECUTION_DOCKER_HOST=tcp://<proxy-service-name>:2375` — a
proxy nothing points at is a no-op.

### 5. Hardening `ContainerCodeExecutor`: resource limits and a real timeout

ADK's `ContainerCodeExecutor` already starts sandbox containers with
networking disabled and all Linux capabilities dropped by default (verified
in `container_code_executor.py`: `containers.run(image=..., detach=True,
tty=True, network_disabled=not self.network_enabled, cap_drop=['ALL'],
security_opt=['no-new-privileges'])`). This project does not override
`network_enabled=True` anywhere in the default path — a skill or tool that
genuinely needs network access from inside the sandbox is an explicit,
reviewed exception, not a default.

Two things that same call *doesn't* set, both verified by reading the
source rather than assumed:

- **No resource limits at all.** No `mem_limit`, `nano_cpus`/`cpu_quota`,
  or `pids_limit` — a fork bomb or memory-exhaustion loop in
  model-generated code can take down the whole host, not just its own
  container. `ContainerCodeExecutor`'s only public knobs are `base_url`,
  `image`, `docker_path`, `network_enabled`; none of them touch resource
  limits.
- **`timeout_seconds` (the `BaseCodeExecutor` field) is defined but never
  read.** `execute_code()` calls `self._container.exec_run([...],
  demux=True)` with no timeout argument — grep confirms zero occurrences of
  "timeout" anywhere in `container_code_executor.py`. Setting
  `timeout_seconds` on the instance changes nothing for this executor; an
  infinite loop hangs the `exec_run` call server-side indefinitely.

Both require a thin subclass, not just constructor arguments: add
`mem_limit`/`nano_cpus`/`pids_limit`/`read_only=True` (plus a small `tmpfs`
for `/tmp`, since read-only execution still needs a scratch directory) to
the container-creation call, and override `execute_code()` to run
`exec_run` in a background thread joined against `self.timeout_seconds`,
killing/restarting the container on timeout rather than leaving it in an
unknown state — `__init_container` starts one container that's reused
across every `exec_run` call for the lifetime of the executor, so a hung or
corrupted exec leaks into the *next* call in the same session if not
actively recovered.

## Consequences

### Positive
- `code_execution` actually works for every model provider this project
  supports, not just Gemini — closes a real, previously-undocumented gap.
- Same fallback-chain shape as `autoconfig.py`, so the pattern is familiar
  rather than a new thing to learn.
- Never silently lands on `UnsafeLocalCodeExecutor` — matches the project's
  existing "dangerous requires an explicit name" convention.
- Both the operator (logs, `inspect_runtime`) and the model (system prompt)
  know which sandbox — or lack of one — is in effect.

### Negative
- A second Docker-socket-adjacent service in `docker-compose.yml` is more
  moving parts, and it's a materially more sensitive trust boundary
  (container creation, not just read-only discovery) than anything else in
  this compose file today — needs careful review before it ships, and needs
  its own dedicated network (§4) or it exposes every container on the host.
- Live-probing Docker (§2.ii) adds a small, bounded startup latency
  (~1s worst case) when `code_execution` is enabled; acceptable but worth
  noting since nothing else in `autoconfig.py` does a real network probe
  today, they all trust env var presence.
- `docker` becomes an optional dependency (only needed for the
  `docker_container` strategy) — must not become a hard requirement for
  deployments that don't use it (e.g. Cloud Run, where the GCP-managed
  strategies apply instead and no Docker daemon exists at all). Its import
  must stay deferred inside the provider, never at module scope (§2.ii).
- `ContainerCodeExecutor` reuses one long-lived container across every
  `exec_run` call in a session rather than starting fresh per snippet
  (`__init_container` runs once; cleanup is `atexit`-registered). The
  hardened subclass (§5) must actively recover (kill/restart) on timeout —
  without that, one hung execution degrades every subsequent call in the
  same agent session, not just the one that hung.

## Verification

Implemented as patch series P1–P11 in git history and recorded in
`CHANGELOG.md`. The current residual work is tracked in `TODO.md`. Verified so
far, item by item:

- ✅ Docker probe: success, unreachable daemon, `docker` package not
  installed — none of the three raise, only the last two differ in log
  detail. Unit-tested (P2) and live-probed on Docker 29.6.2.
- ✅ Explicit-override fail-fast: an unknown or unreachable explicitly-selected
  strategy raises `ProviderConfigurationError` from the resolver, not from
  `probe()`. Unit-tested (P1/P2/P3).
- ✅ Gemini detection rejects a native-but-pre-2.0 Gemini model string instead
  of resolving to `gemini_built_in` and failing mid-invocation.
  Unit-tested (P3) using ADK's own predicate.
- ✅ GCP-managed providers never activate from `GCP_PROJECT` alone without
  their own resource identifier also set (regression test against
  `_build_application_integration_toolset`'s existing use of the same var).
  Unit-tested (P7).
- ✅ Instruction-text injection for both the available and unavailable cases,
  and the `code_execution` entry appearing in both `inspect_runtime()`'s
  capabilities dict and the `adk.capabilities` span attribute.
  Unit-tested (P6); a third variant (honest no-isolation wording) covers
  `unsafe_local`.
- ✅ A started sandbox container actually carries the hardened limits —
  verified against live `docker inspect` output (commit `a321312`):
  `Memory=536870912`, `NanoCpus=1000000000`, `PidsLimit=128`,
  `ReadonlyRootfs=true`, `CapDrop=["ALL"]`,
  `SecurityOpt=["no-new-privileges"]`, `Config.NetworkDisabled=true`
  (note: the disabled network surfaces as `Config.NetworkDisabled`, *not*
  as `NetworkMode: "none"`), plus an in-sandbox `socket.create_connection`
  to 1.1.1.1:53 raising `OSError`.
- ✅ The `code-exec` socket-proxy network genuinely can't reach containers
  outside the sandbox's own — verified live (P11, proxy v0.3.0 behind the
  `code-exec` profile): attempted-exec endpoints all denied with 403
  (`POST /build`, `/auth`, `/commit`, `/networks/create`, `GET /secrets`,
  `POST /swarm/init`) while positive controls succeeded on the same
  harness (`GET /_ping` → 200, `POST /containers/create` → 201 — proving
  the denials are ACL denials, not connectivity noise); from the default
  bridge network the proxy does not even resolve, so only `code-exec`-
  attached containers (adk-api alone) can reach it; Traefik's original
  proxy still renders `POST=0`.
- ✅ A deliberately-hung script triggers the timeout path and the container
  is usable again on the next call in the same session — verified live
  (P11): `while True: pass` under `timeout_seconds=5` returned in 5.5s
  wall with the timeout stderr, and the subsequent execution in the same
  session succeeded on the restarted container. (This review pass also
  found and fixed a real defect: recovery originally routed through
  docker-py's graceful `stop()` with its 10s default grace period —
  15.6s wall for the 5s timeout; `_recover_container` now SIGKILLs.
  Commit `2d80e2f`.)
- ✅ The published application image includes the Docker SDK, the Compose
  `code-exec` profile points the resolver at its scoped proxy by default, and
  CI creates a real child sandbox from the built image to verify execution,
  rootless operation, read-only rootfs, no network, resource limits, and
  cleanup (`scripts/verify-sandbox-runtime.sh`).

### Corrections recorded during implementation research

1. ADK's Gemini-version predicate `is_gemini_eap_or_2_or_above` lives in
   `google.adk.utils.model_name_utils` (where
   `built_in_code_executor.py` imports it from), **not** in
   `code_execution_utils` as §2's original note implied.
2. §4's open question is answered above: proxy v0.3.0 requires `POST=1`
   (master switch before every `ALLOW_*` rule), and `POST=1`+`IMAGES=1`
   admits image auto-pull.

---

## Appendix A — Verified facts (do not re-derive; re-verify only on upgrades)

Reference facts captured during implementation research (2026-08-16);
kept here because the hardened executor and compose wiring depend on
them and any `google-adk`/docker-socket-proxy upgrade must re-verify.


All checked against the installed environment on 2026-08-16:
`google-adk 2.6.3`, `docker-py 7.2.0` (installed ad-hoc, **not** in the
project lock), `tecnativa/docker-socket-proxy` **v0.3.0** (the pinned tag;
commit `393a99c`), Docker Engine 29.6.2.

### ADK 2.6.3 internals

- `google.adk.code_executors/__init__.py` eagerly imports
  `BuiltInCodeExecutor` and `UnsafeLocalCodeExecutor` (no lazy-import risk
  for those two), but resolves `ContainerCodeExecutor`, `GkeCodeExecutor`,
  `VertexAiCodeExecutor`, `AgentEngineSandboxCodeExecutor` through a module
  `__getattr__`. Importing `ContainerCodeExecutor` without `docker`
  installed raises
  `ImportError: … pip install "google-adk[extensions]"`. ⇒ **every** import
  of these four must be deferred inside `probe()`/`build()` behind
  `try/except ImportError`.
- `ContainerCodeExecutor.__init__(base_url=None, image=None,
  docker_path=None, **data)` requires `image` or `docker_path`; raises on
  `stateful=True`/`optimize_data_file=True`; creates the client
  (`docker.from_env()` or `docker.DockerClient(base_url=…)`), then calls
  `self.__init_container()` — **name-mangled**, so a subclass defining its
  own `__init_container` is silently bypassed, and the parent constructor
  starts an *unhardened* container before any subclass code runs. The
  hardened subclass therefore must NOT call `ContainerCodeExecutor.__init__`
  (see P2 sketch).
- `__init_container` runs the container with exactly:
  `image, detach=True, tty=True, network_disabled=not network_enabled,
  cap_drop=['ALL'], security_opt=['no-new-privileges']` — **no** mem/cpu/
  pids limits, **no** read-only rootfs. Then `_verify_python_installation()`
  runs `exec_run(['which', 'python3'])` and requires exit 0 (⇒ the sandbox
  image must contain `which` + `python3`).
- `execute_code()` = `self._container.exec_run(['python3', '-c', code],
  demux=True)`. Zero occurrences of "timeout" in the file;
  `BaseCodeExecutor.timeout_seconds` (default `None`) is never read. One
  long-lived container per executor instance (`atexit`-registered cleanup of
  stop+remove) — a hung exec leaks into the next call in the session.
- `DEFAULT_IMAGE_TAG = 'adk-code-executor:latest'`. **ADK ships no
  Dockerfile for it and publishes no image** — verified against the
  `google/adk-python` repo tree (no executor Dockerfile exists). The tag is
  a build-it-yourself placeholder. See Appendix B for the image decision.
- `BuiltInCodeExecutor.process_llm_request` raises `ValueError` for any
  model where `is_gemini_eap_or_2_or_above(llm_request.model)` is false,
  unless env `ADK_DISABLE_GEMINI_MODEL_ID_CHECK` is enabled. ⚠️ That
  predicate lives in **`google.adk.utils.model_name_utils`** (that's where
  `built_in_code_executor.py` imports it from) — *not* in
  `code_execution_utils` as the old TODO task 4 claimed.
- GKE executor: **hard module-level** `import kubernetes` + optional
  `k8s_agent_sandbox` ⇒ importing it without `kubernetes` installed raises
  `ImportError` through the lazy `__getattr__`. Knobs: `namespace`,
  `image` (default `python:3.11-slim`), `timeout_seconds=300`,
  `executor_type="job"|"sandbox"`, `cpu_requested/mem_requested/cpu_limit/
  mem_limit`, `kubeconfig_path`, `kubeconfig_context`; auth: explicit
  kubeconfig, in-cluster SA, or default `~/.kube/config`.
- Vertex AI executor: single `resource_name` arg, format
  `projects/123/locations/us-central1/extensions/456`. Uses `google.genai`
  (already a dependency — no extra install needed).
- AgentEngineSandbox executor: `sandbox_resource_name` /
  `agent_engine_resource_name`, format
  `projects/…/locations/…/reasoningEngines/…[/sandboxEnvironments/…]`.
  Stdlib + ADK imports only — no extra dependency.
- `BaseCodeExecutor` is a pydantic `BaseModel` (`timeout_seconds:
  Optional[int]`, `stateful: bool`, …). Plain attribute assignment after
  init works (no `validate_assignment`).
- ADK also ships `integrations/cloud_run/_cloud_run_sandbox_code_executor`
  — out of scope (Cloud Run integration, not one of the six
  `code_executors`).

### docker-py 7.2.0

- `client.containers.run(...)` accepts (all verified in the installed
  source): `mem_limit`, `nano_cpus`, `pids_limit`, `read_only`, `tmpfs`
  (dict, e.g. `{"/tmp": "size=64m,rw"}`), `network_disabled`, `cap_drop`,
  `security_opt`, alongside `image`, `detach`, `tty`.
- `docker.DockerClient(base_url=…, timeout=…)` / `docker.from_env(timeout=…)`
  — constructor sets the per-request timeout; SDK default is **60s**.
- `client.ping()` → `GET /_ping`.
- Sandbox container lifecycle through the proxy needs: `POST
  /containers/create`, `POST /containers/{id}/start`, `GET
  /containers/{id}/json`(inspect), `POST /containers/{id}/exec`, `POST
  /exec/{id}/start`, `POST /containers/{id}/stop|kill`, `DELETE
  /containers/{id}` (cleanup), optional `POST /images/create` (auto-pull),
  `GET /_ping`, `GET /version`.

### docker-socket-proxy v0.3.0 (haproxy-based)

Verified from the tag's `haproxy.cfg` + its own test suite:

- **Rule 1 of the frontend ACL is
  `http-request deny unless METH_GET || { env(POST) -m bool }`** — `POST=1`
  is a master switch gating **all** non-GET methods (including PUT/DELETE,
  e.g. container remove). The `ALLOW_START`/`ALLOW_STOP`/`ALLOW_RESTARTS`
  rules are evaluated *after* it, so with `POST=0` they are unreachable for
  writes. The proxy's tests confirm: `CONTAINERS=1` without `POST` forbids
  even `docker restart`. ⚠️ **This corrects ADR-004 §4 and old task 10**,
  which assumed `POST=0` + `ALLOW_*=1` works — it does not on v0.3.0.
- Consequence: the sandbox proxy must set `POST=1`. That alone grants
  nothing (their tests: `POST=1` alone still forbids pull/run/rm/network
  create) — endpoints stay gated by their section envs.
- **Auto-pull is admitted** iff `POST=1` **and** `IMAGES=1` (`POST
  /images/create` matches the `^…/images` ACL). This resolves ADR-004 §4's
  open question: pre-pulling is *not* required for function, only a
  hardening/latency choice (pull lets the agent-side executor fetch images
  from registries; the pulled code still only runs inside the hardened
  sandbox).
- Everything not explicitly enabled defaults to denied: `AUTH BUILD COMMIT
  CONFIGS DISTRIBUTION EVENTS GRPC INFO NETWORKS NODES PLUGINS SECRETS
  SERVICES SESSION SWARM SYSTEM TASKS VOLUMES` → 403.

### Repo facts

- `ProviderConfigurationError` lives in `src/basic_agent/autoconfig.py`.
- `models.resolve_model()` returns the bare model string for the native
  Gemini path, else a `LiteLlm` instance — the P3 probe keys on exactly
  this distinction.
- `config.py`'s `Settings` is a frozen dataclass snapshotted at import;
  the resolver therefore takes an explicit `environment: Mapping[str, str]`
  (fresh `dict(os.environ)` + YAML overlay) instead of reading `settings`.
- YAML pattern to mirror: `tools.skills.*` (`ToolsSkillsConfig` dataclass +
  branch in `_parse_agent_config`, `src/basic_agent/config_loader.py`).
- `agent.py`: `_SILENT_TOOL_NAMES` filters `code_execution` from tool
  construction; the line to replace in `_build_runtime_context` (~line
  443) is
  `code_executor=BuiltInCodeExecutor() if "code_execution" in configured else None`.
- `RuntimeContext` (`src/basic_agent/strategies/base.py`) already has
  `code_executor: Any = None`; sibling fields go next to it.
- `docker-compose.yml` profiles in use: `observability`, `live`, `demo`.
  The existing `docker-socket-proxy` service (Traefik's, `POST: "0"`) must
  stay untouched.
- The `docker` SDK is **not** in the project lock; CI installs via
  `uv sync --frozen` — adding an optional extra requires `uv lock`.

---

## Appendix B — Sandbox image decision

**There is no official ready-made ADK sandbox image.** `adk-python` ships no
Dockerfile for `adk-code-executor:latest` and publishes nothing to a
registry; the tag is a build-it-yourself placeholder. We considered
building one vs using an existing public image:

| Candidate | Verdict | Notes (verified live on Docker 29.6.2) |
|---|---|---|
| `python:3.13-slim-bookworm@sha256:00faa2debb87529f9f0764e9491d8ba400a3678976616c3bd7cb193745ac20d1` | **RECOMMENDED DEFAULT** | 178 MB; `which python3` ✓ (Cpython 3.13.15 at `/usr/local/bin/python3`); **verified running under the full hardened constraint set** (`--read-only --tmpfs /tmp --cap-drop ALL --security-opt no-new-privileges --memory 512m --pids-limit 128 --network none`): executes `python3 -c`, writes to tmpfs, root fs read-only. glibc ⇒ best wheel compatibility. Trivy scans the Debian runtime packages; the official image's embedded build-time Python SBOM is excluded because it describes non-installed wheel contents. |
| `python:3.13-alpine` | Documented alternative | 70.3 MB, digest `sha256:540c7d91…`; `which python3` ✓; same constraints work. musl breaks some C-extension wheels — fine for pure-stdlib snippets, worse if model code `pip install`s (it can't anyway: no network). |
| `python:3.12-slim` | Supported via config | 179 MB, digest `sha256:57cd7c3a…`; use if a 3.12 runtime is required. |
| jupyter `docker-stacks` | Rejected | Notebook-oriented, ~2 GB, ships a full userland we don't need. |
| E2B / Firecracker sandboxes | Rejected | µVM-based, not plain Docker — wrong abstraction for `ContainerCodeExecutor`. |
| Self-built `adk-code-executor:latest` | Rejected as default | Nothing wrong with it, but no published base means everyone re-invents it; official `python` images are maintained and scanned by Docker Hub. Precedent: ADK's own `GkeCodeExecutor` defaults its sandbox image to `python:3.11-slim`. |

**Decisions for implementation:**

- Default image constant in `execution/resolver.py`:
  `DEFAULT_SANDBOX_IMAGE = "python:3.13-slim-bookworm@sha256:00faa2debb87529f9f0764e9491d8ba400a3678976616c3bd7cb193745ac20d1"`.
- Operator override: `AGENT_CODE_EXECUTION_DOCKER_IMAGE` env /
  `execution.code_execution.docker_image` YAML (P5 plumbing).
- README (P10) documents digest pinning for production and the
  alpine/smaller-variant tradeoff.
- Compose (P8) keeps `IMAGES=1` so a missing image is auto-pulled on first
  use; hardened deployments may pre-pull + drop `IMAGES` to `0` (then a
  missing image fails fast at first execution instead of pulling).

---

**All patches P1–P11 are complete.** Final commits: P10 `41029ed`
(README/CHANGELOG/ADR-004 docs), P11 `2d80e2f` (live security review:
proxy ACL scope + isolation verified, timeout-recovery defect found and
fixed, README production-checklist paragraph; all eight ADR-004
Verification items now ✅ with live evidence).
