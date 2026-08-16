# TODO — Pluggable code-execution sandbox: patch series

Design: [ADR-004](docs/ADR-004-pluggable-code-execution.md).
This file is the **implementation spec**: each patch below is self-contained
enough to be implemented in a fresh session without any other context — it
includes verified facts, file paths, code sketches, tests, and a done-when
checklist. Work in order; each patch lands as one commit.

**Status:** **P1–P11 all ✅ complete — series finished.** Branch `main`:

| Patch | Commit | Summary |
|---|---|---|
| P1 resolver scaffold | `dcf35b4` | `_CodeExecutionProviderSpec`, `CodeExecutionResolution`, registry, `resolve_code_executor()`; 11 tests |
| P2 docker + hardened executor | `a321312` | `HardenedContainerCodeExecutor` (cached lazy factory; mem/cpu/pids/read-only/tmpfs + wall-clock timeout w/ container recovery), docker provider (1s ping probe), `docker` extra; 13 tests; live-verified on Docker 29.6.2 |
| P3 gemini_built_in | `774f519` | isinstance(str) + `is_gemini_eap_or_2_or_above` probe; 8 tests |
| P4 unsafe_local | `16b1d4f` | explicit-override-only, `warn_on_select`; 3 tests |
| P5 settings plumbing | `0aaf737` | 7 `code_execution_*` settings fields, `ExecutionCodeExecutionConfig` (YAML `execution.code_execution.*`), `.env.example`; 4 tests |
| P6 agent wiring + tell-the-model | `98c2644` | `_build_runtime_context` resolves via `resolve_code_executor` (env + YAML overlay); RuntimeContext strategy/detail fields; instruction line per scenario; `inspect_runtime()` + `adk.capabilities` span entries; 9 tests |
| P7 GCP providers | `a25600c` | vertex_ai / agent_engine_sandbox / gke identifier-presence probes (never `GCP_PROJECT` alone — regression-tested), consolidated registration = chain order, `gke` extra + lock; 10 tests |
| P8 compose sandbox proxy | `4e4747e` | `code-exec-socket-proxy` behind `code-exec` profile (POST=1 master switch + CONTAINERS/EXEC/IMAGES/PING/VERSION), dedicated `code-exec` network, adk-api passthroughs; `docker compose config` gates verified |
| P9 test consolidation | `2328a1e`+ | full checklist verified against named tests; coverage 95.90% both with `--extra docker` (303 passed, 1 skip) and without (304 passed); remaining uncovered lines in `code_execution.py` are defensive branches only |
| P10 docs | `41029ed` | README "Code execution" section (strategy table, tradeoffs, image note), CHANGELOG series entry, ADR-004 §4 verified-proxy note + Verification check-off + corrections |
| P11 security review | `2d80e2f` | Live: proxy ACL 403s on build/auth/commit/networks/secrets/swarm with 200/201 positive controls; proxy unresolvable off the `code-exec` network; timeout-recovery verified (5.5s for a 5s timeout after fixing stop()→kill(), 15.6s before); README production-checklist paragraph; all 8 ADR-004 Verification items ✅ |

Baseline commit `5e747d0`: Skills support + ADR-004 + the previous
13-task TODO (see git history, which also preserves the full original
text of patches P1–P11). Old-task → patch mapping: 1→P1, 2+3→P2, 4→P3,
6→P4, 7→P5, 8+9→P6, 5→P7, 10→P8, 11→P9, 12→P10, 13→P11.

**Gates for every patch** (CI runs these; coverage threshold is 90%):

```bash
uv run pytest tests/ -q --tb=short          # all green (304 passing after P7)
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

**All patches P1–P11 are complete.** Final commits: P10 `41029ed`
(README/CHANGELOG/ADR-004 docs), P11 `2d80e2f` (live security review:
proxy ACL scope + isolation verified, timeout-recovery defect found and
fixed, README production-checklist paragraph; all eight ADR-004
Verification items now ✅ with live evidence).

Completed work is recorded in [CHANGELOG.md](CHANGELOG.md). Design
decisions are recorded as ADRs in [docs/](docs/).
