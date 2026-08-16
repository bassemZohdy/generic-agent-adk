# TODO

Findings from the 2026-08-16 project review. Grouped by priority.

## High priority — untested security-relevant paths

- [x] `use_cases/registry.py:156,165,172,182` — added tests for the custom-use-case-module guardrails (missing file, production-without-allowlist, outside-allowlist, within-allowlist). Coverage for this file is now 99%.
- [x] `service_api.py:38-48` — added `tests/test_service_api.py`: end-to-end `TestClient` tests for the `/status` endpoint covering auth-disabled, misconfigured issuer, no credentials, valid/invalid API key, and valid/insufficient-role bearer token. File is now 100% covered.
- [x] `.github/workflows/ci.yml` — fixed publish-before-scan ordering: `build` now only ever pushes an unverified `ci-<sha>` staging tag; a new `promote-image` job attaches the real release tags (`latest`, branch, semver) to the verified digest only after `verify-image` passes.
- [x] `.github/workflows/ci.yml` — PRs now get real image verification: `build` loads the image locally (`load: true`, no push) and runs the dependency-lock check, Trivy scan, and smoke test in-job against it, since forked-PR runs have no registry credentials to push/pull with.

## Medium priority — architecture/config debt

- [ ] Resolve ADR-003's currently-failing migration gate: criterion #4 requires the test suite to run without deprecation warnings, but `SequentialAgent`/`ParallelAgent`/`LoopAgent` deprecation warnings fire today in `strategies/sequential.py:36`, `parallel.py:36`, `human_in_loop.py:48`, `planner_executor.py:40`, `loop.py:37`, `evaluator_optimizer.py:47`. Either complete the Workflow migration or update ADR-003's status/gate to reflect reality.
- [ ] `use_cases/base.py` — add tests for hook-chaining (`_chain`, `_chain_before_tool`/`_chain_after_tool` at lines 36, 48-52, 59-70, 181-183) and for `resolve_runtime`'s config-merge/override rules (lines 121, 125-129). This is documented extensibility behavior with no coverage.
- [ ] `strategies/base.py:138` — add a test for `positive_count`'s validation error on bad `workers`/`steps` config (bool, non-int, or < 1).
- [ ] `use_cases/registry.py:39,41-47` — add a test for the duplicate-key/alias registration `ValueError`.

## Low priority — doc hygiene / cleanup

- [x] Rewrote `.github/CI-CD-INTEGRATION.md` and updated `.github/PUBLISHING.md` to match the actual pipeline (pip-audit, gitleaks, Trivy as a hard gate, the verify script, and the new staging-tag/promote model). Removed fabricated metrics/module tables that no longer matched the codebase.
- [x] README badges and `docs/SECURITY-HARDENING-2026-08-15.md` now reflect real counts (199 passed, 88% coverage after the new tests above); added a note on the security doc that its numbers are a point-in-time snapshot, not the live CI gate (which is `COVERAGE_THRESHOLD` = 85% in `ci.yml`).
- [x] `use_cases/registry.py:94` — docstring fixed: "eight built-ins" (was "nine").
- [x] `strategies/registry.py`'s unused `list_strategies()` removed (no callers, no test, unlike its sibling `list_use_cases()` which is genuinely used).
