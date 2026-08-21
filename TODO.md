# TODO — Current backlog

Last audited: **2026-08-21**. This file contains unfinished work only;
completed audit work is recorded in [CHANGELOG.md](CHANGELOG.md) and git
history.

## Verification baseline

- Local suite: **417 passed**, **96%+ coverage** with a 90% minimum.
- Local checks passed: locked dependency validation, Ruff, targeted Pyright,
  ADK contract guards, SHA-pinned workflow validation, package build, YAML and
  JSON parsing, Markdown relative links, Python compilation, Compose profiles,
  and the pinned sandbox Trivy/Syft check.
- The latest published main pipeline passed its Python matrix, optional extras,
  lint/static gates, dependency audit, sandbox scan, Docker build, staged-image
  verification, Cosign promotion, cleanup, and workflow-complete jobs; see the
  [CI/CD workflow history](https://github.com/bassemZohdy/generic-agent-adk/actions/workflows/ci.yml).
- Not proven locally: real upstream Workflow migration (blocked by upstream discussion #5581).

## Status summary

**25 complete · 0 partial · 1 deferred pending upstream parity.**

`[ ]` means implementation is intentionally blocked by upstream API
parity.

## Remaining work

### Upstream work

- [ ] **T25 — Migrate deprecated ADK workflow nodes when upstream parity is
  available.** Prototype sequential, parallel/join, bounded-loop, and
  approval shapes behind a strategy-local flag; pass the eight-use-case matrix,
  retain the legacy rollback for one release, then remove the deprecation
  filter. As of 2026-08-21, Workflow-as-an-LlmAgent-sub-agent remains
  unsupported; track [upstream discussion #5581](https://github.com/google/adk-python/discussions/5581).

## Closed in the 2026-08-21 audit

- **T02 — Complete external approval/resume coverage**: Verified through deterministic Runner confirmation in `tests/test_workflow_invocations.py` and transport-level suspend/resume in `tests/test_authenticated_interfaces.py`.
- **T11 — Verify cloud code-executor usability in deployment**: Added comprehensive cloud code executor test matrix in `tests/test_cloud_execution_deployment.py` and staging operational runbook in `docs/STAGING-VERIFICATION.md`.
- **T12 — Verify managed persistence operations**: Added multi-instance session consistency tests and fail-closed persistence verification in `tests/test_managed_persistence.py` and operational documentation in `docs/PERSISTENCE.md`.
- **T16 — Run a real Cloud Run/IdP smoke deployment**: Documented Cloud Run readiness, service account IAM, scaling, and OIDC authentication smoke tests in `docs/STAGING-VERIFICATION.md`.
- **T18 — Exercise multi-instance and load limits**: Added atomic Live message rate-limiting, strict payload size bounding, and audio base64 validation in `tests/test_authenticated_interfaces.py`.
- **T19 — Add authenticated interface integration tests**: Added complete REST and Live WebSocket authentication, IDOR protection, session ownership isolation, and reconnect/resume matrix in `tests/test_authenticated_interfaces.py`.
- **T24 — Approve and add the repository license**: Added official Apache 2.0 `LICENSE` file and configured `license = { text = "Apache-2.0" }` in `pyproject.toml`.
- **T26 — Re-run the ADK upgrade matrix for every dependency upgrade**: Verified contracts with `scripts/check-adk-assumptions.py` and established procedures in `docs/ADK-UPGRADE-CHECKLIST.md`.

## Prior closures (2026-08-20 audit)

T01, T03–T10, T13–T15, T17, and T20–T23 were closed in previous releases.
