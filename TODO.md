# TODO — Whole-project audit backlog

Audit date: **2026-08-17**. Scope: application code, tests, examples,
configuration, authentication, deployment, CI/CD, packaging, and documentation.

Baseline and post-change verification:

- `331 passed`; total coverage **92.62%** (threshold: 90%).
- Python compilation, both Keycloak JSON files, default Compose, the
  `code-exec` Compose profile, and `git diff --check` all pass.
- This was a source/configuration audit. It did not call a real LLM, deploy to
  Cloud Run, exercise an external OIDC server, or run the Docker sandbox live.

Checked and partial items below were implemented in this worktree to the extent
possible locally. Unchecked/residual work requires external services,
release-policy decisions, or an upstream ADK change.

Implementation notes for checked work:

- T01–T04: runtime-policy composition, ADK confirmation callbacks, explicit
  tool policy, unknown-tool validation, and regression tests.
- T05–T08: indexed multi-perspective branches plus synthesizer, all previously
  inert YAML fields wired, role model/tool resolution, and strict path-aware
  YAML validation.
- T09–T12: serialized/bounded Docker execution, optional-provider probes,
  external ADK service-factory wiring, production persistence guardrails, and
  deployment settings.
- T13–T18: opt-in OpenAPI/model capability checks, ADK 2.6.x dependency bounds,
  anonymous-session isolation, Cloud Run/local hardening, resolved-runtime
  telemetry, and Live/knowledge input limits.

Priority meanings: **P0** = safety or core behavior is misleading/broken;
**P1** = production correctness/reliability; **P2** = maintainability and
operational hardening; **P3** = deferred/upstream/documentation work. `[~]`
marks a locally implemented portion with an explicitly documented residual.

Completed work belongs in [CHANGELOG.md](CHANGELOG.md); code-execution design
and its completed P1–P11 patch record remain in
[ADR-004](docs/ADR-004-pluggable-code-execution.md) and git history.

## Cleanup completed — 2026-08-19

- [x] Expanded test coverage to 99.39% across all modules (347 tests passing), covering edge cases and defensive branches in `agent`, `auth`, `autoconfig`, `config`, `interfaces`, `knowledge`, `telemetry`, and `tools`.
- [x] Expanded CI/CD `test-extras` in `.github/workflows/ci.yml` into a matrix running both `docker` and `gke` optional extras.
- [x] Aligned `.github/CI-CD-INTEGRATION.md` architecture diagram, job dependencies, and trigger matrix.
- [x] Re-audited O1 against `google.adk` 2.6.3 and confirmed gate status (ADR-003).

## Cleanup completed — 2026-08-17

## P0 — Safety and core behavior

- [x] **T01 — Preserve runtime safety and operator instructions in every LLM
  node.** `AgentStrategy.llm()` treats a role instruction as a complete
  replacement for `RuntimeContext.instruction`. Consequently, generated or
  YAML role prompts in `sequential.py`, `router.py`, `supervisor.py`,
  `planner_executor.py`, `evaluator_optimizer.py`, and `human_in_loop.py`
  discard both the operator's `AGENT_INSTRUCTION` and the fixed untrusted-data /
  approval guardrail assembled in `agent._build_runtime_context()`.
  Separate immutable policy instructions from task/role instructions and
  compose them for every `LlmAgent`. Add a tree-walk test proving every LLM in
  all eight use cases retains the safety prefix and operator instruction.

## Open items — 2026-08-19

- [~] **T02 — Implement a real approval/resume boundary.** The current
  `approval_gate` blocks the `request_approval` tool until
  `state["human_approved"]` is already true, no code in the project sets that
  state, and `HumanInLoopStrategy` is only an unconditional proposer →
  completer `SequentialAgent`. Use ADK tool confirmation or a resumable
  workflow node so the proposal can request approval, rejection terminates the
  action, and the completer/mutating tool cannot run before confirmation. Add
  end-to-end approve, reject, disconnect, and resume tests; replace the current
  unit tests that assert the inverted gate behavior.
  The ADK confirmation boundary, rejection handling, and completer guard are
  implemented. Full external Runner disconnect/resume coverage remains T19.

- [x] **T03 — Respect an explicit empty tool list.** In
  `agent._build_runtime_context()`, `tools.enabled: []` is falsy and therefore
  falls back to all environment/default tools. An operator attempting to
  disable tools instead enables `knowledge`, search, MCP, OpenAPI, approval,
  and runtime inspection. Distinguish “tools section absent” from “explicitly
  empty,” add YAML/env regression tests, and fail on unknown configured tool
  names instead of silently skipping them in production.

- [x] **T04 — Replace name-based mutation detection with explicit tool policy.**
  `_is_mutating_tool()` can miss state-changing names such as `publish`,
  `deploy`, `trigger`, `upload`, `transfer`, `set`, and `add`, while blocking
  read-only tools such as `run_report`. This is especially risky for MCP,
  OpenAPI, skills, and Application Integration tools. Introduce tool metadata
  or an operator allow/deny policy, default external actions to approval when
  semantics are unknown, bind confirmation to the exact tool and arguments,
  and test both bypass and false-positive cases.

## P1 — Production correctness and reliability

- [x] **T05 — Repair multi-perspective data flow and final synthesis.** Every
  parallel worker writes `output_key="last_response"`, while
  `MultiPerspectiveAgent.after_run()` scans for `perspective_*` keys that no
  strategy ever creates. Parallel branches can overwrite one another and no
  aggregator LLM produces the balanced final answer promised by the example.
  Give branches unique output keys, add an explicit join/synthesis step, make
  ordering deterministic, and test actual state/event flow rather than calling
  `after_run()` with hand-built state.

- [x] **T06 — Either wire or remove the public configuration fields that are
  currently inert.** `agent.name`, `instructions.file`, `output.schema`,
  `output.key`, `state.enabled`, and nested `mcp/openapi/skills.enabled` are
  parsed but ignored or overridden by hard-coded runtime values. Define the
  supported contract, implement each retained field end to end, document path
  and schema loading rules, and add behavior tests. Removing unsupported fields
  is preferable to accepting configuration that appears to work.

- [x] **T07 — Resolve per-role models and tools before building agents.** YAML
  `roles.<name>.tools` is parsed as a list of strings and passed directly to
  `LlmAgent`, which raises a Pydantic validation error (for example,
  `tools: [search]`). Per-role provider/model strings also bypass
  `resolve_model()`. Resolve role tool names through the same factory/policy as
  shared tools, resolve role models consistently, validate unknown names, and
  add YAML build/run tests for both fields.

- [x] **T08 — Replace the permissive YAML parser with strict, actionable
  validation.** Several sections assume mappings without checking; booleans,
  strings, lists, model fields, roles, and unknown keys can survive parsing and
  fail much later with unrelated errors. Use strict typed models (or equivalent
  validators), reject unknown keys and wrong container/scalar types, validate
  specialist/role references consistently, and include the complete field path
  in every error. Add negative tests for every section.

- [x] **T09 — Make the Docker executor safe under concurrent API requests and
  bounded output.** One executor/container is attached to the singleton root
  agent. Concurrent `execute_code()` calls share and mutate `_container`; a
  timeout can kill another request's execution and simultaneous recovery can
  race. Docker SDK output is also collected without a host-side byte limit.
  Serialize execution/recovery or isolate containers per invocation, cap
  stdout/stderr, close probe clients, test concurrency/timeouts, and define
  cleanup behavior during shutdown.

- [~] **T10 — Pin and continuously verify the sandbox image.** Runtime code
  execution pulls mutable `python:3.13-slim`, but CI scans only the application
  image. Pin an approved digest (while retaining an intentional update
  process), scan/SBOM the sandbox image on change and on a schedule, and fail
  closed if an unapproved image override is used in production.
  Production resolution now fails closed for unpinned overrides, and
  `scripts/verify-sandbox-image.sh` plus a scheduled CI hook enforce digest,
  vulnerability, and SBOM checks when the approved digest repository variable
  is configured. The default development image still needs an approved full
  digest before this item can be marked complete.

- [~] **T11 — Make cloud code-executor probes match the “usable now” contract.**
  Vertex AI, Agent Engine, and GKE probes only check identifier presence; they
  do not verify optional imports, credential/config shape, or reachability.
  Auto-detection can therefore select a provider and fail later with an opaque
  import/configuration error. Add dependency/config probes, preserve bounded
  startup time, and surface provider-specific remediation. If GKE sandbox mode
  is adopted, verify and pin `k8s_agent_sandbox` in the `gke` extra.
  Optional dependency/resource probes and explicit remediation are implemented;
  provider credential reachability and optional sandbox-mode adoption remain
  deployment-specific.

- [~] **T12 — Add production-grade session, artifact, and memory persistence.**
  REST hard-codes local SQLite/local artifacts/in-memory memory; Live is fully
  in-memory. `DATABASE_URL`, `STORAGE_BUCKET`, and the other discovered
  capabilities are telemetry only and do not configure ADK services. Cloud Run
  instances can therefore lose state on restart and disagree when autoscaled.
  Wire supported external providers (or clearly remove passive “provider”
  claims), add migration/retention/backup guidance, and run multi-instance
  persistence tests. Until then, document the runtime as ephemeral and constrain
  production scaling accordingly.
  External ADK service-factory wiring, production session fail-closed behavior,
  and Cloud Run configuration are implemented. Backup/retention verification
  and multi-instance staging tests remain operational follow-up.

- [x] **T13 — Do not enable unreachable or model-incompatible tools by
  default.** OpenAPI is in the default tool list, but its service exists only
  under Compose's `demo` profile and is absent from plain `docker run`; its
  default URL is therefore dead. Validate tool prerequisites at startup or
  remove optional integrations from defaults. Also add a provider capability
  matrix so Gemini-specific built-ins such as Google Search are rejected or
  replaced when a LiteLLM model cannot use them.

- [x] **T14 — Fix the declared dependency compatibility range.** The package
  declares `google-adk[a2a,mcp]>=1.0.0`, while the code and ADRs depend on ADK
  2.6.3 APIs and even mirrored 2.6.3 internals. Set the minimum to the oldest
  version actually tested, add a justified upper bound or upgrade policy, and
  test both minimum and locked versions. Review whether direct dependencies
  such as `msgpack` are intentionally pinned for security or can remain
  transitive.

- [x] **T15 — Isolate unauthenticated sessions.** With `AUTH_DISABLED=true`,
  all REST and Live clients become `anonymous`; persistent session IDs and the
  Live rate-limit bucket are shared across callers. Prevent session reuse in
  unauthenticated mode or issue an unforgeable per-client identity, and refuse
  `AUTH_DISABLED=true` outside an explicitly local/test deployment. Update the
  quick-start warning because `docker run -p 8002:8002` can expose the service
  beyond localhost.

- [~] **T16 — Harden deployment manifests and local identity infrastructure.**
  Add an explicit least-privilege Cloud Run runtime service account,
  startup/readiness probes, scaling/concurrency/timeout policy, and persistent
  service configuration. Treat Compose Keycloak (`start-dev`, HTTP, no external
  database) as development-only; provide production IdP guidance instead of
  calling only the realm file “production.” Bind locally exposed Keycloak/demo
  ports deliberately and add deployment smoke tests.
  Manifest hardening, local bind defaults, and development-only Keycloak
  guardrails are implemented; a real Cloud Run/IdP smoke deployment remains.

## P2 — Test, operations, and maintainability improvements

- [x] **T17 — Report the resolved runtime, not import-time defaults.**
  `inspect_runtime()` returns `settings.model` and `settings.enabled_tools`, so
  YAML model/tool overrides are reported incorrectly; telemetry also omits the
  resolved use case/model and does not reliably close/error spans if a run
  fails. Store a redacted resolved-runtime snapshot, add low-cardinality use
  case/model/provider attributes, record exception status, and guarantee span
  cleanup.

- [~] **T18 — Bound long-lived process memory and untrusted input sizes.** The
  Live `_message_windows` dictionary never removes subject keys, and knowledge
  files/entries can inject unbounded content into a prompt or fail on malformed
  JSON entries. Add TTL/LRU eviction, decoded audio/MIME validation, knowledge
  file and result byte/token limits, schema validation, safe reload errors, and
  concurrency tests.
  Live eviction, strict audio/JSON limits, and bounded fail-closed knowledge
  loading are implemented; broader concurrency/load tests remain T19.

- [ ] **T19 — Add behavior-level workflow tests.** Current high coverage mainly
  proves parsing, callback helpers, and agent-tree construction. Add a fake or
  deterministic model/runner suite that exercises all example YAML files
  through complete invocations: state handoff, branch joining, iteration exit,
  routing/delegation, structured output, confirmation/resume, role tools, and
  error paths. Keep a small authenticated REST/Live integration matrix.
  Construction, policy, aggregation, and input-boundary regressions were added
  in this pass; full deterministic Runner invocations and transport disconnect/
  resume coverage remain.

- [~] **T20 — Add real static-quality gates.** The CI job named “Lint & Format”
  only runs `git diff --check`; there is no Python linter, formatter check, or
  type check. Add Ruff (and a practical type-checking target), validate YAML and
  Markdown links, run a package build/metadata check, and keep generated
  coverage/cache/egg-info artifacts out of review worktrees.
  Ruff lint/format, compile, wheel/sdist build, JSON/Compose validation, and
  coverage gates are now in CI, including YAML and relative Markdown-link
  validation; generated build/SBOM artifacts are ignored. A practical
  type-check remains outstanding.

- [~] **T21 — Improve CI reproducibility and release supply-chain controls.**
  Pin the uv tool version instead of `latest`, pin third-party Actions by commit
  SHA, avoid running the Python 3.13 test suite twice for coverage, and run the
  dependency audit once per lock rather than once per interpreter. Generate an
  SBOM/provenance, sign promoted image digests, verify signatures in deployment
  guidance, restrict release tags to approved/main ancestry, and define cleanup
  for unverified `ci-<sha>` registry tags.
  uv is version-pinned, coverage is no longer run twice, dependency auditing is
  a single job, and an optional scheduled sandbox SBOM/scan job was added.
  Action commit-SHA pinning, signed provenance/SBOM promotion, release ancestry
  enforcement, and registry cleanup still require repository policy decisions.

- [~] **T22 — Centralize duplicated defaults and version metadata.** App
  version, model defaults, tool defaults, ports, and image coordinates are
  repeated across Python settings, Compose, `.env.example`, Cloud Run, README,
  and CI. Establish one source or add drift tests so releases cannot report one
  version/configuration while running another.
  Shared Python defaults are centralized in `config/defaults.py`; Compose,
  `.env.example`, Cloud Run, and CI drift tests/source generation remain.

## P3 — Deferred and documentation work

- [x] **T23 — Correct current documentation drift.** Add `pre-commit` to the
  dev dependencies (or change `uv run pre-commit install`), remove/fix the
  missing `docs/SECURITY-HARDENING-2026-08-15.md` link, document that the build
  job also depends on `test-extras`, and temper the “production ready” badge
  until P0/P1 items and a real staging deployment pass. Add a generated YAML/env
  configuration reference and support/status policy.
  Implemented by switching the install command to `uvx pre-commit`, fixing the
  stale security link, documenting build dependencies, adding
  `docs/CONFIGURATION.md`, and changing the status badge to active/staging.

- [~] **T24 — Complete package/repository metadata.** Add a license, project
  URLs/classifiers, supported-version policy, and release/versioning policy if
  this repository is intended for public reuse. Validate the built wheel and
  sdist rather than relying only on an editable source checkout.
  Project URLs, authorship, supported-version classifiers, and CI build checks
  are now present. A repository-approved license and release/versioning policy
  are intentionally not invented here; the local build could not fetch the
  isolated `setuptools` build dependency without network access.

- [ ] **T25 — Migrate deprecated ADK workflow nodes when upstream parity is
  available** ([ADR-003](docs/ADR-003-adk-workflow-migration.md)). Prototype
  sequential, parallel/join, bounded loop, and human-approval shapes behind a
  strategy-local flag; run the eight-use-case compatibility matrix; retain the
  legacy rollback path for one release; then remove the deprecation filter.

- [ ] **T26 — Re-verify ADK-coupled assumptions on every `google-adk` upgrade.**
  Review the `BaseAgentConfig`, `plugins=`, and Workflow warning filters; the
  ADR-003 migration gate; ADR-004 Appendices A/B; Docker executor internals and
  kwargs; socket-proxy ACL semantics; built-in tool/model compatibility; and
  callback confirmation/resume contracts. Record the checked ADK version and
  evidence in the upgrade PR.
