# TODO — Current backlog

This file contains **unfinished work only**. Completed work is recorded in
[CHANGELOG.md](CHANGELOG.md) and git history; the sections below carry the
standing context a future contributor (human or agent) needs before taking
any task.

Last audited: **2026-08-23** — 2 open items below (G01, G02), found during a
documentation/architecture-accuracy audit the same date. All prior work
streams are closed as of that date: the workflow re-architecture program
(Phases A–F, ADR-005 Implemented), the deep code review (R01–R15), and the
CI smoke-assertion fix (C01).

## Verification baseline

- Local suite: **459 passed**, **94.14% coverage** (90% minimum) —
  2026-08-23 close-of-work run.
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

**2 open items (2026-08-23 doc/architecture audit): G01, G02 — see
"Remaining work" below.** Everything from prior waves is closed:

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

Found 2026-08-23 during a documentation/architecture-accuracy audit
prompted by a recurring critique: that the use-case/strategy classification
was wrong and configuration needed to be more generic. That critique was
already addressed in code by ADR-005 (presets are data, not classes; the
`graph:` config is genuinely topology-generic) — the two gaps below are
what's left, ranked most severe first.

### G01 — `graph:` function nodes have no config-level extension point

**Problem**: `compile_graph()` (`compile/workflow.py`) accepts a
`function_registry` parameter merged over `DEFAULT_FUNCTION_REGISTRY`, but
neither call site (`agent.py` `_build_graph_root`, `presets/catalog.py`
`Preset.build`) ever passes one. A `graph:` node with `kind: function` can
therefore only ever resolve to the fixed built-in set (`route_dispatch`,
the loop counter, `aggregate_perspectives`, …). Unlike presets — pluggable
via `AGENT_USE_CASE_MODULE` — there is no equivalent mechanism to register a
custom function-node callable from YAML/env. This is the one concrete place
where "generic, flexible configuration" (ADR-005's stated goal) stops short:
graph *topology* is fully generic, but custom step *logic* beyond LLM nodes
is not configurable, only forkable.

**Fix**: either (a) design and implement a documented, allowlisted
extension point (e.g. `AGENT_FUNCTION_MODULE`, mirroring
`AGENT_USE_CASE_MODULE`'s allowlist pattern) so an operator can register
`options.function` implementations without editing `compile/workflow.py`;
or (b) if the team deliberately wants this closed (arbitrary callables from
config is a real execution-safety boundary, not an oversight), record that
decision in ADR-005 or a short new ADR, and delete the now-explicitly-dead
`function_registry` parameter from the two call sites so the code doesn't
imply an extension point that isn't reachable.

**Done when**: either custom function nodes are reachable from a documented
config surface with a passing test exercising a non-built-in function name,
or the closed-by-design decision is recorded in an ADR and the dead
parameter is removed.

### G02 — extend `tests/test_documentation_consistency.py` for architecture-doc/module-map drift

**Problem**: `docs/ARCHITECTURE.md`'s "one-minute version" diagram and
module-map table described the deleted `strategies/`/per-use-case-class
layer as current, well after E3/F2/F3 deleted that code (fixed in this
audit — see the current diff/commit). `test_documentation_consistency.py`
already guards README/CONFIGURATION.md against several classes of drift
(use-case keys, ports, model examples, sandbox terms) but has no check
tying `ARCHITECTURE.md`'s module map to the actual `src/basic_agent/`
package list, so this class of staleness has no regression guard and can
silently recur.

**Fix**: add a test that reads the top-level package/module names under
`src/basic_agent/` (e.g. via `git ls-files` or `pathlib`) and asserts each
has a corresponding row in `ARCHITECTURE.md`'s module-map table (or an
explicit skip-list for intentionally-undocumented internals), and that no
documented row names a module that no longer exists on disk.

**Done when**: the new test fails against the pre-audit version of
`ARCHITECTURE.md` (i.e., it would actually have caught this) and passes on
the current tree; added to the existing `test_documentation_consistency.py`
file, no new script needed.

## History

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
