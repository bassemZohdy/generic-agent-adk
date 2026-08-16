# Changelog

All notable changes to this project are recorded here, newest first.

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
