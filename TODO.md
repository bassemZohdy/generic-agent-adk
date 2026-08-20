# TODO — Current backlog

Last audited: **2026-08-20**. This file contains unfinished work only;
completed audit work is recorded in [CHANGELOG.md](CHANGELOG.md) and git
history.

## Verification baseline

- Local suite: **379 passed**, **95.57% coverage** with a 90% minimum.
- Local checks passed: locked dependency validation, Ruff, targeted Pyright,
  ADK contract guards, SHA-pinned workflow validation, package build, YAML and
  JSON parsing, Markdown relative links, Python compilation, Compose profiles,
  and the pinned sandbox Trivy/Syft check.
- The latest published main pipeline passed its Python matrix, optional extras,
  lint/static gates, dependency audit, sandbox scan, Docker build, staged-image
  verification, Cosign promotion, cleanup, and workflow-complete jobs; see the
  [CI/CD workflow history](https://github.com/bassemZohdy/generic-agent-adk/actions/workflows/ci.yml).
- Not proven locally: real LLM calls, authenticated external REST/Live
  transport, Cloud Run deployment, external OIDC, managed persistence,
  multi-instance staging, and upstream Workflow migration.

## Status summary

**17 complete · 8 partial · 1 deferred pending upstream parity.**

`[~]` means the local implementation is complete enough to protect the
runtime, but deployment, external-service, policy, or manual-upgrade evidence
remains. `[ ]` means implementation is intentionally blocked by upstream API
parity.

## Remaining work

### P0/P1 — Safety and production reliability

- [~] **T02 — Complete external approval/resume coverage.** ADK confirmation
  now suspends a real Runner until approve or reject, and the mutating path is
  guarded. Add authenticated REST/Live disconnect, reconnect, and resume tests
  against the deployed transport boundary; the deterministic Runner coverage
  is already in `tests/test_workflow_invocations.py`.

- [~] **T11 — Verify cloud code-executor usability in deployment.** Local
  provider probes validate optional imports, configuration, and remediation,
  but Vertex AI, Agent Engine, and GKE credential reachability and any adopted
  `k8s_agent_sandbox` mode still require a real deployment.

- [~] **T12 — Verify managed persistence operations.** External ADK service
  factories and production fail-closed settings are wired. Run staging
  multi-instance tests and document database migration, artifact retention,
  backup, and restore evidence before calling persistence production-ready.

- [~] **T16 — Run a real Cloud Run/IdP smoke deployment.** Cloud Run manifest
  hardening and development-only Keycloak guardrails are present. Verify a
  deployed service account, readiness behavior, external OIDC, and scaling;
  the local Keycloak pull is currently blocked by a quay.io HTTP 403.

### P2 — Operations and behavior coverage

- [~] **T18 — Exercise multi-instance and load limits.** Local Live eviction,
  strict audio/JSON bounds, bounded knowledge loading, and concurrent rate
  limit admission are covered. Add process-level or distributed load tests for
  memory, rate-limit consistency, disconnects, and large inputs.

- [~] **T19 — Add authenticated interface integration tests.** All eight
  examples now run through a deterministic ADK Runner, including approval
  suspend/resume. Add a small authenticated REST/Live matrix covering session
  isolation, reconnect/resume, transport errors, and external service
  boundaries.

### P3 — Release policy and upstream work

- [~] **T24 — Approve and add the repository license.** Project metadata,
  URLs, authorship, supported Python policy, SemVer policy, and wheel/sdist
  validation are present. A repository-approved license still requires an
  owner decision; do not invent one in an automated cleanup.

- [ ] **T25 — Migrate deprecated ADK workflow nodes when upstream parity is
  available.** Prototype sequential, parallel/join, bounded-loop, and
  approval shapes behind a strategy-local flag; pass the eight-use-case matrix,
  retain the legacy rollback for one release, then remove the deprecation
  filter. As of 2026-08-20, Workflow-as-an-LlmAgent-sub-agent remains
  unsupported; track [upstream discussion #5581](https://github.com/google/adk-python/discussions/5581).

- [~] **T26 — Re-run the ADK upgrade matrix for every dependency upgrade.**
  `scripts/check-adk-assumptions.py` guards the locked version, imports,
  Runner/confirmation signatures, and socket-proxy ACL assumptions. Complete
  the manual matrix in [ADK-UPGRADE-CHECKLIST.md](docs/ADK-UPGRADE-CHECKLIST.md)
  and record version, commands, and evidence in each upgrade PR.

## Closed in the 2026-08-20 audit

T01, T03–T10, T13–T15, T17, and T20–T23 are closed. The delivered work
includes runtime-policy composition, strict configuration and tool resolution,
safe Docker execution, pinned sandbox verification, deployment guardrails,
resolved-runtime telemetry, security input bounds, deterministic workflow
coverage, static-quality gates, supply-chain controls, centralized defaults,
and documentation/support-policy cleanup.

## Backlog update rules

When closing an item, add the test, deployment, policy, or upstream evidence
that justifies the change. Keep external validation tasks `[~]` until the
evidence exists, and keep T25 open until the ADK migration gate in
[ADR-003](docs/ADR-003-adk-workflow-migration.md) is satisfied.
