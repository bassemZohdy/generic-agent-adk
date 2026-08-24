# TODO — Current backlog

This file contains **unfinished work only**. Completed work is recorded in
[CHANGELOG.md](CHANGELOG.md) and git history; the sections below carry the
standing context a future contributor (human or agent) needs before taking
any task.

Last audited: **2026-08-24** — backlog empty. All work streams closed on
that date: the workflow re-architecture program (Phases A–F, ADR-005
Implemented), the deep code review (R01–R15), the CI smoke-assertion
fix (C01), the doc/architecture-accuracy findings (G01, G02), and the
post-merge review findings (H01–H15).

## Verification baseline

- Local suite: **474 passed**, **94.17% coverage** (90% minimum) —
  2026-08-24 post-H01–H15 run.
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

### H01–H15 — post-merge review of G01/G02 commit (all closed 2026-08-24)

All 15 findings from the code review of `a3c20e5` are closed in a single
wave. Per-finding evidence:

- **H01** — `plan_execute` reserved in `_RESERVED_FUNCTION_NAMES`;
  `load_custom_functions` rejects it at load time. Test:
  `test_plan_execute_is_reserved`.
- **H02** — shadow guard moved into `load_custom_functions` itself;
  collision check always includes `DEFAULT_FUNCTION_REGISTRY` +
  `_RESERVED_FUNCTION_NAMES` regardless of caller's seed dict. Test:
  `test_builtins_are_never_shadowed_even_with_empty_seed`.
- **H03** — `custom_function_registry()` catches `Exception` from
  `load_custom_functions`, logs warning, returns builtins only. Test:
  `test_broken_module_does_not_crash_unused_preset`.
- **H04** — `value.strip()` applied before `Path()` construction in
  `resolve_allowlisted_file`. Covered by existing allowlist tests.
- **H05** — `use_cases/registry.py` migrated to
  `util.resolve_allowlisted_file`; no independent copy remains.
  `sys.modules` cleanup (H08 pattern) applied to the use-case loader too.
- **H06** — `custom_function_registry()` memoized in `_cached_registry`
  (module-level global, reset via `_reset_cache()`). Test:
  `test_memoized_registry_returns_same_objects`.
- **H07** — collision-skip log message now distinguishes built-in/reserved
  collisions ("collides with a built-in or reserved function name") from
  already-registered collisions ("already registered").
- **H08** — `exec_module` wrapped in try/except; `sys.modules` entry
  removed on failure. Test: `test_sys_modules_cleaned_on_import_failure`.
- **H09** — `_NON_PRODUCTION_DEPLOYMENTS` set added; unrecognized
  `DEPLOYMENT_ENV` values require allowlist (fail closed). Test:
  `test_unrecognized_deployment_env_requires_allowlist`.
- **H10** — `_is_within_root()` uses `os.path.samefile` for
  case-insensitive comparison on macOS APFS; falls back to `Path` equality
  when paths don't exist.
- **H11** — ADR-005 addendum corrected `_build_root_graph` →
  `_build_graph_root`.
- **H12** — ARCHITECTURE.md `util.py` row updated to list
  `resolve_allowlisted_file()`.
- **H13** — README.md now points to `AGENT_FUNCTION_MODULE`/
  `AGENT_FUNCTION_MODULE_ALLOWLIST` alongside the existing
  `AGENT_USE_CASE_MODULE` mention.
- **H14** — `_custom_function_registry` wrapper deleted from `agent.py`;
  `_build_graph_root` calls `custom_function_registry()` directly.
- **H15** — `_write_config` extracted to `conftest.py` as `write_config`
  fixture; both `test_served_graph_config.py` and
  `test_custom_function_module.py` use the shared fixture.

Suite: 474 passed, ruff check+format clean, ADK assumptions green.

## History

- **2026-08-24 post-merge review findings (H01–H15)** — all 15 closed in
  one wave: security hardening (H02 shadow guard, H03 graceful failure,
  H04 whitespace strip, H08 sys.modules cleanup, H09 fail-closed
  DEPLOYMENT_ENV, H10 case-insensitive allowlist), correctness (H01
  plan_execute reservation, H07 log message), performance (H06 caching),
  dedupe (H05 use-case loader migration), code quality (H14 wrapper
  removal, H15 shared test helper), docs (H11 ADR-005 name, H12
  ARCHITECTURE row, H13 README pointer). Suite 474 passed.
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
