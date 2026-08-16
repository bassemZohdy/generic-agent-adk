# TODO

Findings from the 2026-08-16 project review. Grouped by priority.

## High priority — untested security-relevant paths

- [ ] `use_cases/registry.py:156,165,172,182` — add tests for the custom-use-case-module guardrails: nonexistent file, production-without-allowlist rejection, and outside-allowlist rejection. Only the happy path and idempotency are currently tested; this is the actual control preventing arbitrary code loading in production.
- [ ] `service_api.py:38-48` — add an end-to-end test for the real `/status` FastAPI endpoint (auth + role-check + subject logging) via `TestClient` with valid/invalid API keys and bearer tokens. Tests currently only exercise the underlying `get_service_status()` helper, not the endpoint's auth wiring.
- [ ] `.github/workflows/ci.yml` — fix publish-before-scan ordering: the `build` job pushes the image to GHCR (`push: true`) before `verify-image` (Trivy scan, dependency-drift check, smoke test) runs. Add a promote/retag-on-pass step, or gate the push on `verify-image` succeeding first.
- [ ] `.github/workflows/ci.yml` — `verify-image` only runs `if: github.event_name != 'pull_request'`, so PRs get no Trivy/image-verification coverage. Decide whether to run a scan-only (no-push) variant on PRs.

## Medium priority — architecture/config debt

- [ ] Resolve ADR-003's currently-failing migration gate: criterion #4 requires the test suite to run without deprecation warnings, but `SequentialAgent`/`ParallelAgent`/`LoopAgent` deprecation warnings fire today in `strategies/sequential.py:36`, `parallel.py:36`, `human_in_loop.py:48`, `planner_executor.py:40`, `loop.py:37`, `evaluator_optimizer.py:47`. Either complete the Workflow migration or update ADR-003's status/gate to reflect reality.
- [ ] `use_cases/base.py` — add tests for hook-chaining (`_chain`, `_chain_before_tool`/`_chain_after_tool` at lines 36, 48-52, 59-70, 181-183) and for `resolve_runtime`'s config-merge/override rules (lines 121, 125-129). This is documented extensibility behavior with no coverage.
- [ ] `strategies/base.py:138` — add a test for `positive_count`'s validation error on bad `workers`/`steps` config (bool, non-int, or < 1).
- [ ] `use_cases/registry.py:39,41-47` — add a test for the duplicate-key/alias registration `ValueError`.

## Low priority — doc hygiene / cleanup

- [ ] Update `.github/CI-CD-INTEGRATION.md` and `.github/PUBLISHING.md`: they don't mention pip-audit/gitleaks/Trivy/the verify script, and mischaracterize the image-verify job as "non-blocking (informational only)" when it's actually a hard `exit-code: 1` gate.
- [ ] Fix stale test-count/coverage claims: README badge says "199 tests passing"; `docs/SECURITY-HARDENING-2026-08-15.md` says "199 passed (87.62% coverage)". Actual is 186 passed, and the enforced CI gate is 85%, not ~87% (a test was deleted in commit `71444d8` without updating these).
- [ ] `use_cases/registry.py:94` — fix docstring: says "nine built-ins" registered, actually 8.
- [ ] `strategies/registry.py`'s `list_strategies()` has no callers anywhere in `src/` or `tests/` — either add a test/caller or remove it as dead code.
