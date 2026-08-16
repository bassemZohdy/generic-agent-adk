# Changelog

All notable changes to this project are recorded here, newest first.

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
