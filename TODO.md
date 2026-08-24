# TODO — Current backlog

This file contains **unfinished work only**. Completed work is recorded in
[CHANGELOG.md](CHANGELOG.md) and git history; the sections below carry the
standing context a future contributor (human or agent) needs before taking
any task.

Last audited: **2026-08-24** — backlog empty. All work streams closed on
that date: the workflow re-architecture program (Phases A–F, ADR-005
Implemented), the deep code review (R01–R15), the CI smoke-assertion
fix (C01), the doc/architecture-accuracy findings (G01, G02), and the
post-merge review findings (H01–H18).

## Verification baseline

- Local suite: **476 passed**, **90.41% coverage** (90% minimum) —
  2026-08-24 post-H16/H18 run.
- Local checks passed: locked dependency validation, Ruff (check + format),
  targeted Pyright (config + agent.py), ADK contract guards, SHA-pinned
  workflow validation, package build, YAML and JSON parsing, Markdown
  relative links, Python compilation, Compose profiles, and the pinned
  sandbox Trivy/Syft check.
- The published main pipeline is green end-to-end (restored 2026-08-23 by
  the C01 smoke-assertion fix; confirmed on two consecutive runs —
  [32637911226](https://github.com/bassemZohdy/generic-agent-adk/actions/runs/32637911226),
  [32638230997](https://github.com/bassemZohdy/generic-agent-adk/actions/runs/32638230997)),
  including image verification, sandbox-runtime hardening, and image
  promotion/signing. See the
  [CI/CD workflow history](https://github.com/bassemZohdy/generic-agent-adk/actions/workflows/ci.yml).
- Workflow migration is proven locally: graph roots (chain, fan-out+join,
  routed loop), `RequestInput` interrupts/resume, and hook/policy
  attachment are pinned by `tests/test_workflow_gates.py`. Workflow as an
  `LlmAgent` sub-agent remains unsupported upstream
  ([discussion #5581](https://github.com/google/adk-python/discussions/5581)),
  which affects delegation embedding only (ADRs 003/005).
- **Not proven locally** (standing caveat, not backlog): cloud execution,
  Cloud Run, and external OIDC were verified by mocked tests +
  documentation only — no real cloud backend, Cloud Run, or IdP deployment
  has been executed.

## Status summary

**Backlog empty (2026-08-24).** Everything ever tracked here is closed:

- **Workflow re-architecture program** — Phases A–F complete; ADR-005
  **Implemented**; the workflow compiler is the only backend (legacy
  retired with F2). The declarative `graph:`/`policies:` config surface is
  load-bearing through the served entrypoint (R06).
- **Deep code review findings R01–R15** — all closed, in three waves:
  R01–R05 (auth/docs/test-hygiene), R06 + R07/R10–R12/R14/R15 (served-root
  wiring, request-dependent expert routing, fail-fast config, error
  surfaces, concurrent plan steps), and R08/R09/R13 (fail-closed
  `_TaskAgentTool` detection, `require_approval` driving a real gate-all
  approval policy, tree-helper dedupe).
- **C01** — the post-F2 CI image-smoke assertions fixed; the main pipeline
  is green again (it had been red on every push between F1 and C01 while
  the unit-test/lint/build jobs stayed green).

Per-wave evidence lives in [CHANGELOG.md](CHANGELOG.md); per-task evidence
lives in git history (each closure was committed with its findings text).

**Standing watch items** (revisit on trigger, not scheduled work):

1. Upstream [adk-python #5581](https://github.com/google/adk-python/discussions/5581)
   (Workflow-as-sub-agent / Node-as-Tool) — the `team_coordinator`
   delegation escape hatch retires when it resolves.
2. Every ADK upgrade: re-run `scripts/check-adk-assumptions.py` and the
   manual steps in `docs/ADK-UPGRADE-CHECKLIST.md` (includes the
   `_TaskAgentTool` fail-closed detection check added with R08).
3. Cloud execution / Cloud Run / external OIDC remain mock-verified only
   (see the baseline caveat above); a real deployment would upgrade that
   evidence.

## Working agreements for executing agents (read before taking any task)

1. **Read first, in this order**:
   [ADR-005](docs/ADR-005-graph-first-taxonomy-and-configuration.md) (the
   decision record — Implemented), the "Resolution (F2/F3)" and
   "Phase B spike results" sections of
   [ADR-003](docs/ADR-003-adk-workflow-migration.md) (verified engine facts),
   and the "Addendum (2026-08-23)" of
   [ADR-002](docs/ADR-002-use-case-taxonomy.md) (why the taxonomy changed —
   historical).
2. **Key code locations** (post-E3/F2 layout; verify with
   `git ls-files src/basic_agent/`): `presets/catalog.py` (the eight presets
   — metadata, defaults, spec builders, `Preset.build`),
   `use_cases/registry.py` (registry serving presets + custom-module
   loading), `compile/workflow.py` + `compile/llm_node.py` (the only ADK
   composition home), `config/graph.py` + `config/sugar.py` (graph spec and
   sugar forms), `config/loader.py` (YAML → `AgentConfig`),
   `policies/approval.py` + `policies/synthesis.py` (cross-cutting
   policies), `runtime.py` (`RuntimeContext`/`RoleConfig`), `agent.py`
   (runtime assembly; graph-first `_build_root_agent`), `interfaces/`
   (rest/live/mcp/service). Installed ADK (read-only reference):
   `.venv/lib/python3.13/site-packages/google/adk/workflow/` (engine),
   `.../google/adk/runners.py` (BaseNode root), `.../google/adk/agents/`
   (LlmAgent plus the retired Sequential/Parallel/Loop classes — nothing in
   `src/` imports them).
3. **Verification per task**: `uv run pytest tests/ -q` (must stay green,
   coverage ≥ 90%), `uvx --from ruff ruff check .`,
   `uvx --from ruff ruff format --check .` (ruff is not a declared project
   dependency — CI uses the same `uvx --from ruff` invocations), and
   `uv run python scripts/check-adk-assumptions.py`. CI mirrors these; see
   `.github/workflows/ci.yml`.
4. **Hard rules**: never build new functionality on the deprecated legacy
   composition classes (they were retired from the project with F2 — the
   workflow compiler is the only backend, and the import-isolation test in
   `tests/test_compile.py` forbids ADK composition imports outside
   `compile/`); never import or adopt upstream
   `AgentConfig`/`BaseAgent.from_config` (deprecated + experimental); do
   not edit UTF-8 files via PowerShell `Get-Content`/`Set-Content`
   round-trips (encoding corruption — use proper editor tooling); public
   surface (the eight use-case keys, YAML/env contract, catalog metadata)
   must not break.
5. New tasks are self-contained with their own dependencies stated. Do not
   start a task whose "Depends on" is not complete. When a spike or
   decision task changes scope, update the relevant ADR **and** this file
   in the same commit.
6. **Branching**: work happens on `main` in the upstream repo; use
   worktrees (or short-lived branches) for isolated/parallel tasks and
   merge back to `main` before pushing to GitHub.

## Remaining work

None — the backlog is empty. Add new findings/tasks above this line with
the established format (problem → fix → done-when), ranked most severe
first.

### H16, H18 — verification review findings (all closed 2026-08-24)

- **H16** — `Settings.deployment` changed to `str | None`; `load_settings()`
  uses `os.environ.get("DEPLOYMENT_ENV")` (None when unset) instead of
  defaulting to `"docker-compose"`. `is_production(None)` returns True
  (fail closed). All callers using `settings.deployment` now agree with
  `resolve_allowlisted_file()` on the unset case.
- **H18** — `_last_load_error` module global replaced with `_FunctionRegistry`
  dict subclass carrying `_load_error` as an instance attribute.
  `check_custom_function_error()` reads from the registry dict passed by
  `_resolve_function`, so unrelated `compile_graph()` calls are unaffected.
  Test: `test_unrelated_compile_unaffected_by_prior_broken_load`.

Suite: 476 passed, ruff check+format clean, ADK assumptions green.

## History

- **2026-08-24 verification review findings (H16, H18)** — both closed:
  H16 (Settings.deployment now None when unset, is_production(None) → True),
  H18 (_FunctionRegistry dict subclass scopes _load_error per call).
  Suite 476 passed.
- **2026-08-24 verification review of the H06/H07/H09/H16/H17 fix commit
  (`154731f`)** — checked each fix against its original failure scenario.
  **H06, H07, H09, H17 genuinely closed** (H07 has a minor residual gap
  in an unreachable-in-production code path, not filed). **H16 reopened,
  narrowed**: unified for explicit unrecognized `DEPLOYMENT_ENV` values,
  but the unset case still splits from the allowlist check via
  `config/settings.py`'s pre-defaulting. **H18 filed**: the H17 fix's new
  `_last_load_error` module global leaks across unrelated
  `compile_graph()` calls — confirmed with an actual failing pytest run.
  See "Remaining work" for the reopened/new items. Suite 475 passed
  otherwise.
- **2026-08-24 verification review findings (H06, H07, H09, H16, H17)
  filed** — 5 findings from a verification review of commit `91ff930`;
  see the verification entry above for actual closure status.
- **2026-08-24 post-merge review findings (H01–H15) filed** — 15 findings
  from a code review of the G01/G02 commit (`a3c20e5`); see the
  verification entry above for actual closure status.
- **2026-08-23 doc/architecture-accuracy findings (G01, G02)** — G01:
  `AGENT_FUNCTION_MODULE` extension point implemented (option (a));
  `compile/functions.py` + wiring in `agent.py`/`catalog.py`; 8 tests in
  `test_custom_function_module.py`; ADR-005 addendum.  G02: module-map
  drift guard in `test_documentation_consistency.py` (2 tests); proven to
  catch pre-audit `strategies/` staleness.
- **2026-08-23 deep code review (R01–R15)** — logged against
  `e0bf24f..HEAD`; R01–R05 closed the same day, R06–R15 in two waves the
  same day (evidence: CHANGELOG "Review wave 1/2" entries; commits
  `e1d1830`, `d6820c5`/`d6a239b`/`faff004`, `f8a58c0` and their merges).
- **2026-08-23 CI fix (C01)** — stale post-F2 image-smoke assertions;
  commit `f460e88` (merge `6196f36`), pipeline green since.
- **2026-08-23 workflow re-architecture program (A1–F3)** — ADR-005
  Implemented; CHANGELOG "Graph-first re-architecture" and "Program close"
  entries carry the phase-by-phase summary; per-phase task records are in
  git history (removed from this file 2026-08-23 during backlog cleanup).
- **2026-08-21 audit (T01–T26)** — all closed; the R04 re-qualification
  caveat on T11/T16 evidence is recorded in the baseline above.
