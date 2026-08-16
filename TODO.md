# TODO — Pluggable code-execution sandbox: patch series

Design: [ADR-004](docs/ADR-004-pluggable-code-execution.md).
This file is the **implementation spec**: each patch below is self-contained
enough to be implemented in a fresh session without any other context — it
includes verified facts, file paths, code sketches, tests, and a done-when
checklist. Work in order; each patch lands as one commit.

**Status:** P1–P5 ✅ complete; **P6 is next**. Branch `main`:

| Patch | Commit | Summary |
|---|---|---|
| P1 resolver scaffold | `dcf35b4` | `_CodeExecutionProviderSpec`, `CodeExecutionResolution`, registry, `resolve_code_executor()`; 11 tests |
| P2 docker + hardened executor | `a321312` | `HardenedContainerCodeExecutor` (cached lazy factory; mem/cpu/pids/read-only/tmpfs + wall-clock timeout w/ container recovery), docker provider (1s ping probe), `docker` extra; 13 tests; live-verified on Docker 29.6.2 |
| P3 gemini_built_in | `774f519` | isinstance(str) + `is_gemini_eap_or_2_or_above` probe; 8 tests |
| P4 unsafe_local | `16b1d4f` | explicit-override-only, `warn_on_select`; 3 tests |
| P5 settings plumbing | `0aaf737` | 7 `code_execution_*` settings fields, `ExecutionCodeExecutionConfig` (YAML `execution.code_execution.*`), `.env.example`; 4 tests |

Baseline commit `5e747d0`: Skills support + ADR-004 + the previous
13-task TODO (see git history, which also preserves the full original
text of patches P1–P5). Old-task → patch mapping: 1→P1, 2+3→P2, 4→P3,
6→P4, 7→P5, 8+9→P6, 5→P7, 10→P8, 11→P9, 12→P10, 13→P11.

**Gates for every patch** (CI runs these; coverage threshold is 90%):

```bash
uv run pytest tests/ -q --tb=short          # all green (285 passing after P5)
uv run pytest tests/ --cov=basic_agent --cov-fail-under=90
uv lock && uv sync --quiet                   # REQUIRED after any pyproject.toml edit (CI uses --frozen)
docker compose config -q                     # after docker-compose.yml edits
```

Local Docker daemon available (29.6.2) for live verification.

---

## Appendix A — Verified facts (do not re-derive; re-verify only on upgrades)

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

## Appendix B — Sandbox image decision (the "ready-made image?" question)

**There is no official ready-made ADK sandbox image.** `adk-python` ships no
Dockerfile for `adk-code-executor:latest` and publishes nothing to a
registry; the tag is a build-it-yourself placeholder. We considered
building one vs using an existing public image:

| Candidate | Verdict | Notes (verified live on Docker 29.6.2) |
|---|---|---|
| `python:3.13-slim` | **RECOMMENDED DEFAULT** | 178 MB, digest `sha256:ffb752e1…`; `which python3` ✓ (Cpython 3.13.15 at `/usr/local/bin/python3`); **verified running under the full hardened constraint set** (`--read-only --tmpfs /tmp --cap-drop ALL --security-opt no-new-privileges --memory 512m --pids-limit 128 --network none`): executes `python3 -c`, writes to tmpfs, root fs read-only. glibc ⇒ best wheel compatibility. |
| `python:3.13-alpine` | Documented alternative | 70.3 MB, digest `sha256:540c7d91…`; `which python3` ✓; same constraints work. musl breaks some C-extension wheels — fine for pure-stdlib snippets, worse if model code `pip install`s (it can't anyway: no network). |
| `python:3.12-slim` | Supported via config | 179 MB, digest `sha256:57cd7c3a…`; use if a 3.12 runtime is required. |
| jupyter `docker-stacks` | Rejected | Notebook-oriented, ~2 GB, ships a full userland we don't need. |
| E2B / Firecracker sandboxes | Rejected | µVM-based, not plain Docker — wrong abstraction for `ContainerCodeExecutor`. |
| Self-built `adk-code-executor:latest` | Rejected as default | Nothing wrong with it, but no published base means everyone re-invents it; official `python` images are maintained and scanned by Docker Hub. Precedent: ADK's own `GkeCodeExecutor` defaults its sandbox image to `python:3.11-slim`. |

**Decisions for implementation:**

- Default image constant in `code_execution.py`:
  `DEFAULT_SANDBOX_IMAGE = "python:3.13-slim"`.
- Operator override: `AGENT_CODE_EXECUTION_DOCKER_IMAGE` env /
  `execution.code_execution.docker_image` YAML (P5 plumbing).
- README (P10) documents digest pinning for production
  (`python@sha256:ffb752e1…`) and the alpine/smaller-variant tradeoff.
- Compose (P8) keeps `IMAGES=1` so a missing image is auto-pulled on first
  use; hardened deployments may pre-pull + drop `IMAGES` to `0` (then a
  missing image fails fast at first execution instead of pulling).

---

## P6 — Wire the resolver into `agent.py` + tell the model

**Old tasks 8+9. Files:** `src/basic_agent/agent.py`,
`src/basic_agent/strategies/base.py`, tests
(`tests/test_runtime_wiring.py`, `tests/test_agent.py`).

1. `strategies/base.py` — add sibling fields next to `code_executor`:

   ```python
   code_executor: Any = None
   code_execution_strategy: str | None = None   # "docker_container" | … | "unavailable"
   code_execution_detail: str = ""              # provenance, for logs/traces
   ```

   Defaults keep every existing `RuntimeContext(...)` construction working.

2. `agent.py` — in `_build_runtime_context`, replace the hardcoded line
   with:

   ```python
   resolution = None
   if "code_execution" in configured:
       overlay = {}
       ce = execution.code_execution if execution else None
       if ce:
           for attr, env_name in (
               ("strategy", "AGENT_CODE_EXECUTION_STRATEGY"),
               ("docker_host", "AGENT_CODE_EXECUTION_DOCKER_HOST"),
               ("docker_image", "AGENT_CODE_EXECUTION_DOCKER_IMAGE"),
               ("vertex_resource", "AGENT_CODE_EXECUTION_VERTEX_RESOURCE"),
               ("agent_engine_resource", "AGENT_CODE_EXECUTION_AGENT_ENGINE_RESOURCE"),
               ("gke_kubeconfig_path", "AGENT_CODE_EXECUTION_GKE_KUBECONFIG_PATH"),
               ("gke_kubeconfig_context", "AGENT_CODE_EXECUTION_GKE_KUBECONFIG_CONTEXT"),
           ):
               value = getattr(ce, attr)
               if value:
                   overlay[env_name] = value
       resolution = resolve_code_executor({**os.environ, **overlay}, model=model)
       logger.info("code execution resolved: strategy=%s (%s)",
                   resolution.strategy, resolution.detail)
   ```

   then pass `code_executor=resolution.executor if resolution else None`,
   `code_execution_strategy=resolution.strategy if resolution else None`,
   `code_execution_detail=resolution.detail if resolution else ""` into
   `RuntimeContext`. Keep the module import of `BuiltInCodeExecutor` only
   if still used elsewhere — otherwise drop it (check: it becomes unused
   after this change).

3. **Instruction line** (same pattern as the untrusted-content prefix —
   appended right after it, before the operator instruction):

   ```python
   if resolution is not None:
       if resolution.executor is not None:
           instruction += (
               f"\n\nCode execution runs in an isolated sandbox (`{resolution.strategy}`)."
           )
       else:
           instruction += (
               "\n\nCode execution was requested but no sandbox is currently "
               "available; do not claim to execute code."
           )
   ```

4. **Module-level resolution stash** for the two consumers below:

   ```python
   _code_execution_resolution: CodeExecutionResolution | None = None   # set in _build_runtime_context
   ```

5. **`inspect_runtime()`** — extend the capabilities dict (only when the
   tool flag is enabled):

   ```python
   capabilities = {name: provider.strategy for name, provider in discover_capabilities().items()}
   if _code_execution_resolution is not None:
       capabilities["code_execution"] = _code_execution_resolution.strategy
   ```

6. **Trace attribute** — in `GenericAgentPlugin.before_run_callback`,
   append the strategy to the existing `adk.capabilities` attribute:

   ```python
   parts = [f"{name}:{provider.strategy}" for name, provider in self.capabilities.items()]
   if _code_execution_resolution is not None:
       parts.append(f"code_execution:{_code_execution_resolution.strategy}")
   span.set_attribute("adk.capabilities", ",".join(parts))
   ```

**Tests:**
- `_build_runtime_context` integration matrix (monkeypatch
  `resolve_code_executor` or the provider probes):
  - docker available → `HardenedContainerCodeExecutor` instance +
    instruction contains "isolated sandbox (`docker_container`)" +
    `RuntimeContext.code_execution_strategy == "docker_container"`.
  - nothing available → executor None + instruction contains "do not claim
    to execute code" + strategy `"unavailable"`.
  - explicit override (env `AGENT_CODE_EXECUTION_STRATEGY`) wins over
    auto-detect; broken override raises `ProviderConfigurationError` out
    of `_build_runtime_context`.
  - `code_execution` NOT in tools → no instruction line,
    `code_execution_strategy is None`.
- `inspect_runtime()` JSON includes `capabilities.code_execution` when
  resolved, absent otherwise.
- Plugin span attribute carries `code_execution:<strategy>` (build a span
  via the plugin with a stub invocation context; read back the attribute).

**Done when:** old hardcoded `BuiltInCodeExecutor` line is gone; all
scenarios above asserted; full suite + coverage green.

---

## P7 — GCP-managed providers (`vertex_ai`, `agent_engine_sandbox`, `gke`)

**Old task 5. Lower priority — ships after P1–P6. Files:**
`code_execution.py`, `pyproject.toml` (+`uv lock`), `.env.example` (fields
already added in P5), tests.

Probes = "required identifiers present" only (no live probing — same rule
as `autoconfig.py`'s cloud providers), keyed on **code-execution-specific
fields only, never `GOOGLE_CLOUD_PROJECT`/`GCP_PROJECT` alone** (that var
already drives `application_integration`; reusing it here would silently
activate a sandbox for integration-only users):

```python
class VertexAiCodeExecutionProvider(_CodeExecutionProviderSpec):
    strategy = "vertex_ai"
    # probe: env AGENT_CODE_EXECUTION_VERTEX_RESOURCE non-empty
    #        (full resource_name: projects/…/locations/…/extensions/…)
    # build (deferred import): VertexAiCodeExecutor(resource_name=…)

class AgentEngineSandboxCodeExecutionProvider(_CodeExecutionProviderSpec):
    strategy = "agent_engine_sandbox"
    # probe: AGENT_CODE_EXECUTION_AGENT_ENGINE_RESOURCE non-empty
    # build (deferred import): AgentEngineSandboxCodeExecutor(
    #     agent_engine_resource_name=…)   # verify exact kwarg against installed ADK

class GkeCodeExecutionProvider(_CodeExecutionProviderSpec):
    strategy = "gke"
    # probe: AGENT_CODE_EXECUTION_GKE_KUBECONFIG_PATH non-empty
    #        (explicit kubeconfig only — in-cluster/default-kubeconfig are
    #        never auto-detected; opting in means naming a file)
    # build (deferred import; module-level `import kubernetes` raises
    #        ImportError without the extra): GkeCodeExecutor(
    #     kubeconfig_path=…, kubeconfig_context=… or None)
```

`_AUTO_DETECT_ORDER` becomes:
`(vertex_ai, agent_engine_sandbox, gke, docker_container, gemini_built_in)`.

`pyproject.toml`: add optional extra `gke = ["kubernetes>=29.0"]` (the
executor's module import needs `kubernetes`). For `executor_type="sandbox"`
it also imports `k8s_agent_sandbox` — **verify that package's exact PyPI
name/version before pinning it** (only needed if you use sandbox mode; job
mode is the default and doesn't import it). Vertex/AgentEngine need no new
deps (Appendix A). `uv lock`.

**Tests:** each probe true/false on identifier presence; probe false when
only `GCP_PROJECT` is set (the regression case from ADR-004's Verification
list); auto-detect order — GCP resource beats reachable Docker; build
constructs the right executor class (deferred imports mocked).

---

## P8 — `docker-compose.yml`: dedicated sandbox socket proxy

**Old task 10 — with corrected v0.3.0 semantics (Appendix A: `POST=1` is
required; `POST=0`+`ALLOW_*` does NOT work). Files:**
`docker-compose.yml` (the `.env.example` entries, including the
`tcp://code-exec-socket-proxy:2375` example, already landed in P5); README
cross-ref lands in P10.

```yaml
  # Narrowly-scoped Docker API access for sandbox containers ONLY.
  # NOT the Traefik proxy above — that one is read-only (POST=0) and must
  # stay that way. v0.3.0 semantics (verified): POST is a master switch for
  # ALL non-GET methods (create/start/exec/stop/DELETE); ALLOW_* alone is
  # insufficient. POST=1 grants nothing by itself — sections below stay
  # deny-by-default (AUTH/BUILD/COMMIT/NETWORKS/SECRETS/… all 0).
  code-exec-socket-proxy:
    <<: *resource-limits
    profiles: ["code-exec"]
    image: tecnativa/docker-socket-proxy:0.3.0
    environment:
      POST: "1"            # master switch: required for create/start/exec/DELETE
      CONTAINERS: "1"      # create/start/stop/kill/inspect/exec endpoints
      EXEC: "1"            # POST /exec/{id}/start (exec_run's second hop)
      IMAGES: "1"          # GET image inspect + POST /images/create (auto-pull)
      PING: "1"            # GET /_ping — the resolver's probe
      VERSION: "1"
      ALLOW_START: "1"     # belt-and-braces (only relevant if CONTAINERS=0)
      ALLOW_STOP: "1"
      ALLOW_RESTARTS: "1"
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock:ro
    networks:
      - code-exec
    restart: unless-stopped
```

Top-level:

```yaml
networks:
  code-exec: {}   # dedicated: EXEC=1 permits exec against EVERY container
                  # on the daemon; network isolation is the only thing that
                  # bounds it to this proxy's callers (see P11 review)
```

Wire `adk-api` (does NOT get a profile — it's core; it merely gains an
extra, normally-empty network + env passthroughs):

```yaml
  adk-api:
    ...
    networks:
      - default
      - code-exec
    environment:
      ...
      AGENT_CODE_EXECUTION_STRATEGY: ${AGENT_CODE_EXECUTION_STRATEGY:-}
      AGENT_CODE_EXECUTION_DOCKER_HOST: ${AGENT_CODE_EXECUTION_DOCKER_HOST:-}
      AGENT_CODE_EXECUTION_DOCKER_IMAGE: ${AGENT_CODE_EXECUTION_DOCKER_IMAGE:-}
```

Note: `adk-api` (like `auth-gateway`) currently relies on the implicit
default network; once ANY service declares `networks:`, compose semantics
require listing `default` explicitly for it — verify `docker compose
config` shows `adk-api` still attached to `default` (Traefik routing,
keycloak, service-api) plus `code-exec`.

Operator usage (documented in P10): enable with
`docker compose --profile code-exec up`, set
`AGENT_CODE_EXECUTION_DOCKER_HOST=tcp://code-exec-socket-proxy:2375` in
`.env`. Without the profile, nothing listens and the probe correctly
resolves `unavailable` — never anything unsafe.

**Pre-pull note (Appendix A/B):** with `POST=1`+`IMAGES=1` a missing
`python:3.13-slim` is auto-pulled on first sandbox start. Hardened
deployments may pre-pull (`docker pull python:3.13-slim`) and set
`IMAGES: "0"` — then a missing image fails fast at first execution.

**Done when:** `docker compose config -q` clean; `docker compose --profile
code-exec config` shows the proxy on `code-exec` only and `adk-api` on
`default+code-exec`; default (no profile) config still starts everything
as today.

---

## P9 — Tests consolidation + coverage check

**Old task 11. Most tests were written alongside P1–P7; this patch is the
consolidation pass.** Files: `tests/test_code_execution.py` (+ any gaps in
`tests/test_runtime_wiring.py`).

Final checklist (every line asserted somewhere):

- [ ] Docker probe: success / unreachable / package-missing — none raise.
- [ ] Explicit override: unknown name → `ProviderConfigurationError` from
      the *resolver* (probe stays pure-bool).
- [ ] Explicit override: known name, probe False → loud error.
- [ ] Auto-detect order: GCP → docker → gemini → unavailable.
- [ ] `unsafe_local` never auto-selected under any environment; warns on
      explicit selection.
- [ ] Native-but-pre-2.0 Gemini (`gemini-1.5-flash`) resolves away from
      `gemini_built_in`.
- [ ] `_build_runtime_context`: executor type AND instruction text for
      available / unavailable / explicit-override scenarios.
- [ ] `inspect_runtime()` capabilities entry; plugin span attribute.
- [ ] Coverage ≥ 90% (`--cov-fail-under=90`) with and without
      `--extra docker`.

---

## P10 — Docs

**Old task 12. Files:** `README.md`, `CHANGELOG.md`,
`docs/ADR-004-pluggable-code-execution.md`.

- **README** — new "Code execution" section mirroring the Skills section:
  concrete example (`AGENT_TOOLS=…,code_execution` + optional
  `AGENT_CODE_EXECUTION_STRATEGY`), the strategy table (docker_container /
  gemini_built_in / vertex_ai / agent_engine_sandbox / gke / unsafe_local /
  unavailable), the tradeoff callout (Docker needs the daemon or the
  `code-exec` proxy; `unsafe_local` runs in-process and is never
  auto-selected), the sandbox image note (default `python:3.13-slim`,
  override + digest pinning, alpine variant), and the compose `code-exec`
  profile quick-start.
- **CHANGELOG** — one entry covering the whole feature series.
- **ADR-004** — update the Verification section item-by-item as things are
  actually verified end-to-end, and record the two corrections found
  during implementation research (Appendix A): the Gemini predicate lives
  in `google.adk.utils.model_name_utils` (not `code_execution_utils`), and
  §4's `POST=0`+`ALLOW_*` assumption is wrong for proxy v0.3.0 — `POST=1`
  is required and auto-pull is admitted by `POST=1`+`IMAGES=1`.

---

## P11 — Security review pass before shipping

**Old task 13. Run with a live Docker daemon; record results in ADR-004's
Verification section.**

1. **Proxy scope** (with `--profile code-exec` up; the proxy has no host
   port mapping — probe it from a throwaway container on the `code-exec`
   network):
   - `docker run --rm --network <project>_code-exec curlimages/curl -sS
     -o /dev/null -w '%{http_code}' -X POST
     http://code-exec-socket-proxy:2375/build` → `403` (BUILD=0); same for
     `/auth`, `/commit`, `/networks/create`, `/secrets`, `/swarm`.
   - Positive control in the same harness: `-X POST
     …/containers/create` (with a minimal JSON body) must **not** 403, and
     `GET /_ping` must 200 — proves the denials above are ACL denials, not
     connectivity noise.
   - From inside `adk-api`: exec into an *unrelated* container (e.g.
     keycloak) through the proxy fails — it isn't reachable on the
     `code-exec` network (that's the isolation guarantee; the daemon-side
     ACL can't provide it, only network topology can).
   - Confirm Traefik's original `docker-socket-proxy` still has `POST=0`.
2. **Hardened limits on a real container** — start the sandbox (e.g. via a
   one-shot script constructing `HardenedContainerCodeExecutor`), then on
   the running container `docker inspect` and verify **all** of:
   `HostConfig.Memory` (536870912), `HostConfig.NanoCpus` (1000000000),
   `HostConfig.PidsLimit` (128), `HostConfig.ReadonlyRootfs` (true),
   `HostConfig.CapDrop` (["ALL"]), `HostConfig.SecurityOpt`
   (["no-new-privileges"]), `Config.NetworkDisabled` (true — the disabled
   network surfaces here, NOT as `NetworkMode: "none"`).
   Don't trust the code path — read the daemon's own answer.
   ✅ Done during P2 (commit `a321312`): live `docker inspect` confirmed
   every value above, and an in-sandbox `socket.create_connection` to
   1.1.1.1:53 raised `OSError`. Item 3 (timeout-recovery live run)
   remains.
3. **Timeout recovery** — execute a deliberately hung snippet
   (`while True: pass`), assert the call returns within
   `timeout_seconds`+slack with the timeout stderr, and the *next*
   execution in the same session succeeds on the restarted container.
4. **README production checklist** — add a paragraph on the new attack
   surface: the `code-exec` proxy grants container create/exec on the
   host daemon; it must stay on its dedicated network, the sandbox image
   should be digest-pinned, `IMAGES=0`+pre-pull is the hardened default,
   and resource limits must be re-verified after any ADK upgrade (the
   subclass mirrors ADK-private init code — Appendix A).

---

Completed work is recorded in [CHANGELOG.md](CHANGELOG.md). Design
decisions are recorded as ADRs in [docs/](docs/).
