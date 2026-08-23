# Changelog

All notable changes to this project are recorded here, newest first.

## 2026-08-23 — R06: the declarative graph/policies config is load-bearing

- **`config.graph` and `config.policies` now drive the served agent**
  (code-review finding R06): `agent._build_root_agent` is graph-first — a
  configured `graph:` block compiles directly via `compile_graph` (new
  `_build_graph_root`), and the use-case preset path is the fallback when no
  graph is configured. `policies.synthesis` transforms the spec pre-compile;
  `policies.approval` applies to either root (graph or preset). Previously
  both sections parsed and validated but were silently discarded at build
  time.
- **Proven through the served entrypoint**: new
  `tests/test_served_graph_config.py` (6 tests) exercises
  `_build_root_agent` — not the compiler — with YAML configs: custom graph
  replaces the preset root and runs end-to-end (fake models), synthesis
  appends the join/synthesizer/aggregate nodes, approval vetoes gated tools
  with the confirmation interrupt on both topologies, and the preset
  fallback is unchanged.
- **Supporting changes**: `_KNOWN_TOOLS` hoisted to module level in
  `agent.py` and shared with `compile_graph`; root/`get_root_agent` types
  widened to `BaseAgent | Workflow`; snapshot `use_case` reports `graph`
  for configured graphs.
- **No public-surface change**: the eight use-case keys, YAML/env contract,
  catalog metadata, and preset custom-module surface are unchanged; the
  previously-documented-but-inert `graph:`/`policies:` YAML sections now do
  what CONFIGURATION.md said they do.

## 2026-08-23 — Program close: legacy retired, workflow backend only (F2/F3)

- **F2 — legacy path retired**: `compile/legacy.py` deleted together with
  the `AGENT_COMPOSE_BACKEND` switch — the ADK graph workflow is the only
  backend. Zero `src/` imports of the deprecated
  `SequentialAgent`/`ParallelAgent`/`LoopAgent` remain and their pytest
  deprecation filter was removed from `pyproject.toml`. Legacy-only
  surfaces removed: preset `legacy_spec`/`legacy_name` fields, the
  after-run aggregation helper (multi_perspective aggregation now runs
  natively as a graph node), the frozen C4 parity test (its golden expired
  with the compiler it guarded), and related tests. The ADK composition
  import-isolation test is now enforced correctly (its old prefix matching
  was vacuous) and allows only `compile/` and `agent.py`.
- **F3 — program closed**: ADR-005 marked **Implemented**; ADR-003 records
  the resolution; guard scripts re-run green on the final surface
  (google-adk 2.6.3 assumptions, doc links, workflow SHA pins, ruff,
  targeted pyright; full suite 421 passed, 5 platform skips, 93% coverage).
- **No public-surface change**: the eight use-case keys, YAML/env contract,
  catalog metadata, and preset custom-module surface are unchanged.

## 2026-08-23 — Graph-first re-architecture: workflow backend, presets, policies (Phases A–E)

- **Architecture program complete through Phase E** (ADR-005 **Accepted**;
  the migration plan and evidence live in ADR-003's Phase B results):
  - **Phase B gate spike**: real `Workflow` roots (chains, fan-out/join,
    routed loops), `RequestInput` interrupt/resume, and the hook/policy
    attachment point (boundary `FunctionNode`s for policies, ADK plugins
    for observability; `finish_task` passthrough rule proven) pinned by
    `tests/test_workflow_gates.py`.
  - **Graph-spec config** (`config/graph.py` + sugar forms in
    `config/sugar.py`): recursive nodes/edges with per-node retry, timeout,
    schemas, output keys; `sequence`/`parallel`/`loop` sugar; fail-fast
    validation.
  - **Compilers** (`compile/`): the workflow backend is the default
    (`AGENT_COMPOSE_BACKEND`); the legacy sugar compiler is the one-release
    rollback path. The compile layer is the single sanctioned home for ADK
    composition classes (enforced by a test).
  - **Policies** (`policies/`): approval (veto + confirmation interrupt,
    never gates `request_approval`/`finish_task`/`_TaskAgentTool`) and
    synthesis (join + synthesizer + `perspective_*` aggregation) are now
    declarative and topology-independent.
  - **Presets** (`presets/`): the eight public use-case keys are data —
    catalog byte-identical to the previous surface (snapshot-pinned), each
    with graph-spec builders; `team_coordinator` keeps its documented
    delegation escape hatch. The registry serves presets (alias/case
    resolution and `AGENT_USE_CASE_MODULE` custom loading preserved; custom
    modules now expose a `PRESETS` dict of `Preset`).
- **Internal breaking change**: the per-use-case facade classes
  (`use_cases/*.py`) and the strategy layer (`strategies/*`, nine builders)
  were **removed**; `RuntimeContext`/`RoleConfig` moved to
  `basic_agent.runtime`. **The public surface is unchanged**: the eight
  use-case keys, the YAML/env contract, and the catalog metadata
  (`list_use_cases()` byte-identical). Code that imported strategy or
  facade classes directly (undocumented) must port to presets + compilers.
- **Code-review findings R01–R05 closed**: WebSocket subprotocol token leak,
  eager `settings_patch` imports, PERSISTENCE.md corrections, T11/T16
  evidence re-qualification, and test-fixture cleanup.
- Verified: 439+ tests, 96% coverage, ruff/pyright/doc-link/ADK-assumption
  guards green on google-adk 2.6.3.

## 2026-08-21 — Authenticated interface integration, cloud executor & persistence tests, and Apache 2.0 license

- **Authenticated interface integration matrix (`tests/test_authenticated_interfaces.py`)**:
  - Added REST authentication, token verification, role enforcement, and IDOR protection tests.
  - Added Live WebSocket transport authentication across Authorization header, `Sec-WebSocket-Protocol`, and first-frame JSON auth.
  - Added session ownership isolation, session resume across reconnects, and rate limiting / payload bounds enforcement.
- **Managed persistence operations (`tests/test_managed_persistence.py`, `docs/PERSISTENCE.md`)**:
  - Added multi-instance session consistency tests across independent service instances using SQLite and external URI backends.
  - Added fail-closed verification for production deployments without configured persistence URIs.
  - Documented operational procedures for database migration, backup, restore, and artifact lifecycle management.
- **Cloud code execution verification (`tests/test_cloud_execution_deployment.py`, `docs/STAGING-VERIFICATION.md`)**:
  - Added test matrix for Vertex AI Code Interpreter, Agent Engine sandbox, and GKE code executor resolution.
  - Added staging verification runbook covering Cloud Run deployment, service account permissions, OIDC verification, and horizontal scaling.
- **Repository licensing & compliance**:
  - Added standard Apache 2.0 `LICENSE` file.
  - Added `license = { text = "Apache-2.0" }` metadata in `pyproject.toml`.
  - Added cross-platform UTF-8 explicit encoding handling in regression tests.

## 2026-08-20 — Runner workflows, approval resume, and CI supply-chain checks

- Updated the sandbox default to the OS-clean, digest-pinned Python 3.13
  bookworm image and scoped its Trivy gate to Debian runtime packages; the
  official image's embedded build-time wheel SBOM is not an installed runtime
  dependency. Application images continue to scan their resolved Python
  dependencies separately.
- Fixed ADK callback parameter wiring so configured before/after hooks receive
  `callback_context` under real Runner execution.
- Added deterministic Runner coverage for all eight example YAML workflows,
  including real approval suspend/resume tests for both approve and reject
  decisions.
- Wrapped the approval tool with ADK's `require_confirmation` boundary so a
  model turn cannot continue before the human decision.
- Pinned the default Docker sandbox image by digest and added push/PR plus
  weekly/manual vulnerability and SBOM verification.
- Added Pyright, ADK contract guards, GitHub Actions SHA-pin validation,
  provenance/SBOM build attestations, and configuration-default drift tests.
- Made Live rate-limit eviction/admission atomic and covered concurrent callers.

## 2026-08-19 — Coverage expansion, CI/CD extras matrix, and documentation alignment

- **Test coverage expanded to 99.39% (347 tests)**:
  - Added test coverage across `basic_agent.agent` (callbacks lifecycle, span handling, unknown tool skipping).
  - Added test coverage across `basic_agent.auth.core` and `basic_agent.auth.gateway` (missing token subjects, auth-disabled WebSocket token bypass, ForwardAuth healthz/verify status codes).
  - Added test coverage for `basic_agent.autoconfig` (storage bucket path validation, cloud messaging, cloud caching with Redis/Cache URL, cloud search, and cloud logging providers).
  - Added test coverage for `basic_agent.config.loader` and `basic_agent.config.settings` (positive integer validation, unresolved substitutions, malformed YAML schemas, code execution config typing, strict boolean/integer/float settings constraints).
  - Added test coverage for `basic_agent.interfaces.rest` (SubjectBindingMiddleware bypass on `/health` and `/version`, malformed JSON error handling, and subject override behavior when auth is disabled).
  - Added test coverage for `basic_agent.knowledge` (cache hit / stat verification, missing file cache reset), `basic_agent.telemetry` (OTLP endpoint initialization), and `basic_agent.tools` (service API headers, non-directory skills scanning, GCP Application Integration toolset construction).
- **CI/CD matrix for optional dependency extras**:
  - Expanded `test-extras` in `.github/workflows/ci.yml` to a matrix covering both `docker` and `gke` extras (`extra: ["docker", "gke"]`).
  - Aligned `.github/CI-CD-INTEGRATION.md` architecture diagram, job dependencies (`needs: [test, test-extras, lint]`), and trigger matrix.
- **Backlog audit**:
  - Audited O1 Workflow migration against ADK 2.6.3 and confirmed gate status (ADR-003).
  - Verified GKE dependency set and filterwarnings under pytest across all matrix configurations.

## 2026-08-17 — Whole-project audit remediation

- Preserved runtime safety policy across every role prompt and added strict
  YAML validation, explicit empty-tool semantics, role model/tool resolution,
  output/state/name wiring, and indexed multi-perspective synthesis.
- Replaced heuristic mutation detection with explicit tool policy and ADK
  confirmation callbacks; isolated unauthenticated sessions and rejected
  `AUTH_DISABLED` in production-like deployments.
- Serialized and bounded Docker code execution, tightened optional-provider
  probes, removed OpenAPI/search defaults that cannot work for every model,
  added knowledge/Live input limits, and wired external ADK persistence URIs.
- Hardened Cloud Run/Compose defaults, added resolved-runtime telemetry/error
  spans, pinned the ADK dependency range, expanded behavior regression tests,
  and added Ruff/build/coverage/sandbox-image CI gates.
- Added the strict [configuration reference](docs/CONFIGURATION.md); residual
  release-supply-chain, license, staging, and upstream Workflow migration work
  remains tracked in `TODO.md`.

## 2026-08-17 — Image CVE fix: apply Debian security upgrades in build

- The previous push failed the CI Trivy gate (9 × HIGH, all one CVE):
  CVE-2026-53615 in the util-linux family (`bsdutils`, `libblkid1`,
  `libmount1`, `login`, `mount`, …) as shipped by the `python:3.13-slim`
  snapshot — time-drift between yesterday's green run and the advisory
  landing in the Trivy DB, not a regression.
- `Dockerfile` now runs `apt-get update && apt-get upgrade` before the
  hardening step, so base-image packages pick up Debian security fixes
  without waiting for an upstream python image rebuild. Verified locally:
  all flagged packages report `2.41.5-0+deb13u1` (the Trivy-published
  fixed version) and the built image still boots with the default CMD
  (`/docs` → 200).

## 2026-08-17 — Docs accuracy pass + broken default CMD fix

- **Fixed broken image CMD**: `Dockerfile` still launched
  `basic_agent.api_server:app`, a module removed by the source
  reorganization — every plain `docker run` of the image (the README
  quick start) crashed at startup. Now targets
  `basic_agent.interfaces.rest:app` (what compose already used).
- **CI gap closed**: the image smoke tests overrode the container
  command (`python -c …`), so the dead CMD module passed CI. Both
  startup-test steps (PR and verify-image) now additionally boot the
  container with its **default CMD** and poll `/docs` to 200.
- README corrections:
  - Quick start and all "Common configurations" examples passed
    `OPENAI_API_KEY` without `ADK_MODEL` — the default Gemini model
    needs `GOOGLE_API_KEY`, so every example failed as written.
    Added `-e ADK_MODEL=openai/gpt-4o` throughout.
  - Auth section: `DEMO_MODE=true` was documented as a plain
    `docker run` switch; it only selects the dev Keycloak realm under
    Docker Compose. Rewritten (plain run → `AUTH_DISABLED=true`;
    compose → `DEMO_MODE` demo/demo; production realm by default).
  - Compose section: now states the required `KEYCLOAK_ADMIN_PASSWORD`
    / `GRAFANA_ADMIN_PASSWORD` env vars, the bearer-token step for
    `:8002` (forward-auth), and the previously undocumented `demo`
    profile backing the `mcp`/`openapi` tools.
  - Tools list completed (was 5 of 10): added `mcp`, `openapi`,
    `runtime`, `structured_output`, `application_integration` and the
    default tool set.
  - Stale `anthropic/claude-sonnet-4-5` example (regressed in the
    end-user rewrite) back to `claude-sonnet-5`; same fix in
    `.env.example`.
  - Developers section: `pre-commit install` step and the uvicorn
    command matching compose; troubleshooting rows for model/key
    mismatch, `503` auth, and required compose passwords.
- `docs/ARCHITECTURE.md`: `Settings` module reference corrected to
  `config/settings.py`.
- `.github/PUBLISHING.md`: 23 placeholder `ghcr.io/your-org/adk`
  image references replaced with the real image name.

## 2026-08-16 — Source folder reorganization

- `src/basic_agent/` reorganized from 17 root-level files into 4 focused
  packages + 7 root modules:
  - `config/` — `settings.py` (from `config.py`) + `loader.py` (from
    `config_loader.py`); `__init__.py` re-exports the public API.
  - `auth/` — `core.py` (from `auth.py`) + `gateway.py` (from
    `auth_gateway.py`).
  - `interfaces/` — `rest.py`, `live.py`, `service.py`, `mcp.py` (from
    `api_server.py`, `live_server.py`, `service_api.py`, `mcp_server.py`);
    `__init__.py` is intentionally lazy (no eager import of adapters that
    run `create_app()` at module level).
  - `execution/` — `resolver.py` (from `code_execution.py`).
  - `_util.py` renamed to `util.py` (public utility, not private).
- All internal imports, test imports, and compose references
  (`basic_agent.auth.gateway:app`, `basic_agent.interfaces.rest:app`, etc.)
  updated to the new paths. `tools.py`'s `MCP_SERVER_PATH` updated to
  `interfaces/mcp.py`.
- `docs/ARCHITECTURE.md` module map updated to reflect the new structure.

## 2026-08-16 — Source structure refactoring

- New `src/basic_agent/_util.py`: `is_production()` (unifies the
  production-deployment check previously duplicated across 5 files with
  the same `{"prod", "production", "staging", "cloud-run", "cloudrun"}`
  set) and `split_csv()` (unifies `_roles`/`_split_names` in
  `config.py`/`config_loader.py`).
- New `src/basic_agent/knowledge.py`: knowledge file caching +
  `retrieve_knowledge` tool function extracted from `agent.py`.
- New `src/basic_agent/tools.py`: tool building factories
  (`build_tool`, MCP/OpenAPI/Skill/ApplicationIntegration toolsets),
  tool audit callbacks (`protect_and_audit_tool`, `audit_tool_result`),
  and `request_approval` extracted from `agent.py`.
- `agent.py` slimmed from 560 to ~248 lines — now focused on config
  resolution, runtime wiring, and the root agent/plugin contract.
- `CE_FIELD_ENV_MAP` constant added to `code_execution.py` — single
  source of truth for the config-field → env-var mapping consumed by
  `agent.py`'s code-execution overlay (previously a hardcoded tuple).
- All test imports updated to reflect the new module boundaries.

## 2026-08-16 — End-user README + architecture doc

- README restructured for *using* the application: the deep architecture
  section moved out; the internals (module map, config pipeline, runtime
  wiring, use-case→strategy mapping, code-execution resolution, request
  path, observability, CI/CD overview) now live in
  `docs/ARCHITECTURE.md` aimed at contributors and operators.
- README examples now reference the actually-published image
  (`ghcr.io/bassemzohdy/generic-agent-adk`) instead of a placeholder org;
  the Interfaces table's compose service name corrected to `adk-api`;
  the Docker profiles table gained the `code-exec` row with its
  `AGENT_CODE_EXECUTION_DOCKER_HOST` prerequisite.
- Stale bits fixed: test badge 242 → 311 passing; ADR-004's
  "implementation tracked in TODO.md" note replaced (it shipped).
- Custom-use-case section trimmed to essentials with a pointer to the
  architecture doc.

## 2026-08-16 — Test & CI hardening follow-up (post code-execution series)

- Shared test doubles: `tests/fakes.py` now holds the single canonical
  fake docker SDK module graph (`FakeDockerClient`/`FakeContainer`/
  `FakeExecResult`, `install_fake_docker`, `install_fake_kubernetes`),
  replacing the implementations duplicated across `test_code_execution.py`
  and `test_runtime_wiring.py`.
- Warning hygiene: the pytest suite now runs with **zero** warnings via a
  curated `filterwarnings` list — each entry is an individually-commented
  third-party noise filter (ADK `BaseAgentConfig`/`plugins=` deprecations,
  EXPERIMENTAL-feature notices, pydantic-settings lifespan, fastapi httpx).
  Anything unlisted still surfaces loudly.
- Seven new edge-case tests, one of which caught a real wiring bug: the
  code-execution env/YAML merge made YAML values beat explicit
  environment variables, contradicting the repo-wide env-wins convention
  (`apply_env_overrides`). Fixed to `{**overlay, **os.environ}`; covered by
  `test_yaml_strategy_is_overridden_by_env`.
- CI: new `test-extras` job runs the full suite (with the coverage gate)
  against `uv sync --frozen --extra docker` — the opt-in extra was never
  previously exercised; `build` now gates on it. Compose validation in
  lint and build also renders the `--profile code-exec` shape, which the
  default config alone cannot see.
- Docs: TODO.md closed out (landed-work record only); the verified-facts
  appendices (ADK 2.6.3 internals, docker-py kwargs, socket-proxy v0.3.0
  ACL semantics, sandbox-image decision) moved into ADR-004 Appendices
  A/B, where the upgrade re-verification duties belong.

## 2026-08-16 — Pluggable code-execution sandbox (ADR-004)

- The `code_execution` tool flag now resolves a sandbox at agent startup
  instead of unconditionally attaching ADK's `BuiltInCodeExecutor`:
  explicit `AGENT_CODE_EXECUTION_STRATEGY` override (fails loudly when
  unsatisfiable), else auto-detect in order `vertex_ai` →
  `agent_engine_sandbox` → `gke` → `docker_container` → `gemini_built_in`,
  else a graceful `unavailable` with no executor.
- New `src/basic_agent/code_execution.py`: provider specs with a
  pure-bool never-raise `probe()` contract (the *resolver* decides when a
  False is a loud `ProviderConfigurationError`, and only on the explicit
  path); `unsafe_local` is explicit-override-only, never auto-detected,
  and warns on every selection.
- `docker_container` builds `HardenedContainerCodeExecutor` (defined via
  cached lazy factory so Docker-less deployments import cleanly):
  mem_limit 512m, 1 CPU, pids_limit 128, read-only rootfs + `/tmp` tmpfs
  on top of ADK's network_disabled/cap_drop/no-new-privileges, plus a
  wall-clock `execute_code` timeout with kill/restart recovery of the
  reused container. Default sandbox image `python:3.13-slim` (ADK ships
  none); `docker` optional extra added (`uv sync --extra docker`).
- `gemini_built_in` probes with ADK's own `is_gemini_eap_or_2_or_above`
  (from `google.adk.utils.model_name_utils`), so a native-but-pre-2.0
  model resolves away at startup rather than crashing on first
  invocation.
- GCP providers probe on code-execution-specific identifiers only — never
  `GCP_PROJECT` alone (that var drives application integration and must
  not silently activate a sandbox); `gke` opt-in means naming an explicit
  kubeconfig. `gke` optional extra added (`kubernetes>=29.0`).
- Settings/YAML plumbing: `AGENT_CODE_EXECUTION_*` env vars +
  `execution.code_execution.*` in YAML converge on one config shape.
- The resolution is surfaced three ways: `RuntimeContext`
  `code_execution_strategy`/`detail` fields, a generated instruction line
  (sandbox named / "do not claim to execute code" / honest no-isolation
  wording for `unsafe_local`), and a `code_execution` entry in
  `inspect_runtime()`'s capabilities plus the `adk.capabilities` span
  attribute.
- Compose: new `code-exec-socket-proxy` behind the `code-exec` profile
  (`POST=1` master switch + `CONTAINERS/EXEC/IMAGES/PING/VERSION` only)
  on a dedicated `code-exec` network with just `adk-api` attached;
  Traefik's read-only proxy untouched.
- Corrections recorded vs the original plan/ADR: socket-proxy v0.3.0
  evaluates `deny unless METH_GET || POST` before every `ALLOW_*` rule,
  so `POST=1` is required (the planned `POST=0`+`ALLOW_*` admits
  nothing) and auto-pull is admitted by `POST=1`+`IMAGES=1`.

## 2026-08-16 — Native ADK Skills support

- `google-adk` 2.6.3 ships a native Agent Skills system (`google.adk.skills`,
  `SkillToolset`) — SKILL.md-format skill folders with instructions,
  references, assets, and scripts, loaded on demand by the LLM via
  `list_skills`/`load_skill`/`load_skill_resource`/`run_skill_script` tools.
  Wired it in as a new `skills` tool, following the same
  config-driven pattern as `mcp`/`openapi`: `AGENT_TOOLS=...,skills` +
  `AGENT_SKILLS_DIR` (env) or `tools.skills.dir` (YAML) point at a directory
  of skill folders. Opt-in (not in the default `AGENT_TOOLS` list) and
  empty-safe when unconfigured, matching `AGENT_KNOWLEDGE_FILE`'s pattern.
  `run_skill_script` reuses the agent's existing `code_execution` executor —
  no separate wiring needed, just enable both tools together.
- Added `skills/status-check/SKILL.md` as a minimal, runnable example
  (mount-only, like `examples/*.yaml` — never baked into the Docker image).
- Updated the stale `anthropic/claude-sonnet-4-5` example in README's model
  docs to `anthropic/claude-sonnet-5`.

## 2026-08-16 — Test coverage: live_server and mcp_server, CI hardening

- `live_server.py` (the Live WebSocket adapter — auth, rate limiting, session
  binding, the full message loop) was 45% covered by isolated helper tests
  and had no test exercising the `live()` endpoint end-to-end. Added 21
  tests covering every auth path (disabled, header, first-message,
  failures), session rejection, rate limiting, oversized/malformed
  messages, disconnects, and runner event forwarding. Now 100% covered.
- `mcp_server.py` was untested (0%). Added a test for `get_service_status()`;
  now 90% (only the `if __name__ == "__main__"` stdio entry point is
  untested, which needs a subprocess to exercise).
- Closed two small defensive-tolerance gaps: `use_cases/multi_perspective.py`
  and `use_cases/approval_gate.py` now 100% covered.
- **Overall: 218 → 242 tests, 90% → 96% coverage.** Raised
  `COVERAGE_THRESHOLD` in `.github/workflows/ci.yml` from 85 to 90 to lock
  in the improvement.
- CI: bumped three stale GitHub Actions pins — `astral-sh/setup-uv` v5→v10,
  `actions/checkout` v4→v5, `actions/setup-python` v5→v6 (inputs unchanged,
  confirmed via upstream docs). Left Docker/Trivy/Codecov/upload-artifact
  pins untouched — those sit in the image build/push/verify/promote
  pipeline and weren't confirmed stale or broken, so bumping them
  unverified right before a push wasn't worth the risk.

## 2026-08-16 — Strategy/use-case cleanup: dead code, duplication, worker differentiation

Follow-up to the project review below: a deep-dive on `strategies/` and
`use_cases/` for reusable code and use-case merge/split candidates.

- Removed dead `ReactStrategy` (`strategies/react.py`) — byte-identical to
  `DirectStrategy`, unreachable from any use case.
- Extracted `build_worker_pool()` and `require_min_iterations()` helpers
  into `strategies/base.py`, removing duplicated `validate()` overrides from
  `parallel.py`, `sequential.py`, `supervisor.py`, `loop.py`, and
  `evaluator_optimizer.py`.
- Fixed `SupervisorStrategy` (`team_coordinator`) and `SequentialStrategy`
  (`pipeline`): workers/steps were anonymous and got the identical
  top-level instruction. Both now generate a distinct positional default
  instruction, overridable per-index via `rt.roles["worker_{i}"]` /
  `rt.roles["step_{i}"]` — matching `RouterStrategy`'s existing
  per-specialist override pattern. `examples/team-coordinator.yaml` and
  `examples/pipeline.yaml` now demonstrate this.
- Renamed `ParallelAgentStrategy` → `ParallelStrategy`,
  `LoopAgentStrategy` → `LoopStrategy`, and `SequentialAgentStrategy` →
  `SequentialStrategy` for naming consistency — they were the last
  strategy classes carrying a redundant "Agent" suffix no sibling strategy
  class used.
- Merge/split review: all 8 use cases confirmed genuinely distinct — no
  redundant aliases, no config-flag-driven fake splits. See the
  [ADR-002 addendum](docs/ADR-002-use-case-taxonomy.md).

**Verified:** 218 tests passing, 90% coverage; `sequential.py` and
`supervisor.py` at 100% coverage.

## 2026-08-16 — Project review: security-path coverage, CI ordering, doc accuracy

Full-project audit (CI/CD and Docker supply chain, examples/ADRs/config completeness, untested code paths) — 13 findings, all resolved.

### Security-relevant test coverage
- `use_cases/registry.py:156,165,172,182` — added tests for custom-use-case-module guardrails (missing file, production-without-allowlist, outside-allowlist, within-allowlist). Coverage 99%.
- `service_api.py:38-48` — added `tests/test_service_api.py`: end-to-end `TestClient` tests for `/status` (auth-disabled, misconfigured issuer, no credentials, valid/invalid API key, valid/insufficient-role bearer token). Coverage 100%.

### CI/CD supply chain
- `.github/workflows/ci.yml` — fixed publish-before-scan ordering: `build` now only pushes an unverified `ci-<sha>` staging tag; a new `promote-image` job attaches release tags (`latest`, branch, semver) to the verified digest only after `verify-image` passes.
- `.github/workflows/ci.yml` — PRs now get real image verification: `build` loads the image locally (no push) and runs the dependency-lock check, Trivy scan, and smoke test in-job, since forked-PR runs lack registry credentials.

### Architecture / config debt
- ADR-003's migration gate can't be met until upstream ADK lets `Workflow` act as an `LlmAgent` sub-agent. Added a targeted `filterwarnings` ignore in `pyproject.toml` (pointing back to the ADR) so the expected deprecation noise doesn't look like an untracked bug.
- `use_cases/base.py` — added hook-chaining tests (`_chain`, `_chain_before_tool`/`_chain_after_tool`), the `after_tool` wiring path, and `resolve_runtime`'s roles-merge / model-instruction-tools-override / unconditional-default branches. Coverage 100%.
- `strategies/base.py:138` — parametrized test for `positive_count`'s validation error (0, negative, bool, non-int, float). Coverage 100%.
- `use_cases/registry.py:39,41-47` — covered by duplicate-key/duplicate-alias registration tests.

### Doc hygiene / cleanup
- Rewrote `.github/CI-CD-INTEGRATION.md` and updated `.github/PUBLISHING.md` to match the actual pipeline (pip-audit, gitleaks, Trivy as a hard gate, the verify script, the staging-tag/promote model). Removed fabricated metrics/module tables.
- README badges and this changelog reflect real counts; `COVERAGE_THRESHOLD` in `ci.yml` (85%) is the enforced gate — badges are a point-in-time snapshot and drift as tests are added.
- `use_cases/registry.py:94` — docstring fixed: "eight built-ins" (was "nine").
- `strategies/registry.py`'s unused `list_strategies()` removed (no callers, no tests, unlike `list_use_cases()`).

**Verified:** 215 tests passing, 90% coverage; `actionlint` clean; workflow YAML and `pyproject.toml` parse cleanly; `git diff --check` passed.

## 2026-08-15 — Security and correctness hardening

- **Keycloak:** production-safe realm import, no default admin password, brute-force protection, disabled password grants outside the explicit development realm, fail-closed issuer configuration, RS256/issuer/audience/subject validation, cached JWKS clients, role-checked constant-time service keys, safe ForwardAuth headers.
- **Identity and transport:** REST `sub` binding for ADK user IDs and sessions, Live subject-bound session ownership, header/subprotocol/first-message WebSocket authentication, per-subject message budgets, bounded frames/audio, production documentation-route removal.
- **Runtime and supply chain:** lazy agent/tool construction, read-only OpenAPI exposure, approval/audit callbacks, locked non-root Docker builds, image dependency verification, pip-audit, Trivy, gitleaks, resource limits, Docker socket proxy.
- **Configuration and operations:** positive numeric validation, unresolved YAML substitution failures, custom-module directory allowlisting, Cloud Run ingress/IAM instructions, the ADK Workflow migration gate ([ADR-003](docs/ADR-003-adk-workflow-migration.md)).
- **Tests:** immutable-settings fixture, authentication/IDOR/prompt-injection/WebSocket regressions, subject-scoped quota checks, CI-gate assertions.

**Verified:** 199 tests passing, 87.62% coverage at the time; `docker compose config` with required CI passwords passed; `uv lock --check` passed; Python compilation, JSON validation, shell syntax, and `git diff --check` passed.
