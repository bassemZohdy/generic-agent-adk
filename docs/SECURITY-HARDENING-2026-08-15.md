# Security hardening completion record — 2026-08-15

The improvement-round checklist formerly kept in `TODO.md` is complete and
has been removed from the active TODO file.

Implemented areas:

- Keycloak: production-safe realm import, no default admin password, brute-force
  protection, disabled password grants outside the explicit development realm,
  fail-closed issuer configuration, RS256/issuer/audience/subject validation,
  cached JWKS clients, role-checked constant-time service keys, and safe
  ForwardAuth headers.
- Identity and transport: REST `sub` binding for ADK user IDs and sessions,
  Live subject-bound session ownership, header/subprotocol/first-message
  WebSocket authentication, per-subject message budgets, bounded frames/audio,
  and production documentation-route removal.
- Runtime and supply chain: lazy agent/tool construction, read-only OpenAPI
  exposure, approval/audit callbacks, locked non-root Docker builds, image
  dependency verification, pip-audit, Trivy, gitleaks, resource limits, and a
  Docker socket proxy.
- Configuration and operations: positive numeric validation, unresolved YAML
  substitution failures, custom-module directory allowlisting, Cloud Run
  ingress/IAM instructions, and the ADK Workflow migration gate in
  `docs/ADR-003-adk-workflow-migration.md`.
- Tests: immutable-settings fixture, authentication/IDOR/prompt-injection/
  WebSocket regressions, subject-scoped quota checks, and CI-gate assertions.

Verification completed (as of this record's date; the CI-enforced coverage
gate is `COVERAGE_THRESHOLD` in `.github/workflows/ci.yml`, currently 85% —
see the README badges for the current test count/coverage, which drift as
tests are added or removed):

- `uv run pytest -q`: **199 passed** (87.62% coverage at the time of this
  record).
- `docker compose config` with required CI passwords: passed.
- `uv lock --check`: passed.
- Python compilation, JSON validation, shell syntax, and `git diff --check`:
  passed.

The local Docker daemon was unavailable during the final image-build attempt;
the build, frozen install, image dependency comparison, vulnerability scan, and
startup smoke are wired into `.github/workflows/ci.yml` for CI execution.
