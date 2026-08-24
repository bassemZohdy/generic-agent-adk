# TODO — Current backlog

This file contains **unfinished work only**. Completed work is recorded in
[CHANGELOG.md](CHANGELOG.md) and git history; the sections below carry the
standing context a future contributor (human or agent) needs before taking
any task.

Last audited: **2026-08-24** — backlog reopened by a post-merge code
review of the G01/G02 commit (`a3c20e5`), filing **H01–H15**. Every prior
work stream remains closed: the workflow re-architecture program
(Phases A–F, ADR-005 Implemented), the deep code review (R01–R15), the CI
smoke-assertion fix (C01), and the doc/architecture-accuracy findings
(G01, G02) themselves.

## Verification baseline

- Local suite: **469 passed**, **94.17% coverage** (90% minimum) —
  2026-08-23 post-G01/G02 run.
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

**Backlog: 15 open findings (H01–H15), filed 2026-08-24** from a code
review of the G01/G02 commit (`a3c20e5`) — see "Remaining work" below.
Everything tracked before that review is closed:

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

Filed 2026-08-24 from a code review of the G01/G02 commit (`a3c20e5`),
ranked most severe first. Add new findings/tasks above this line with the
established format (problem → fix → done-when), ranked most severe first.

### H01 — `"plan_execute"` custom function nodes are silently unreachable

**Problem:** `compile/workflow.py:208`'s `_resolve_function` hardcodes a
`key == "plan_execute"` branch that runs *before* the custom-registry
lookup, so a module that registers `FUNCTIONS = {"plan_execute": fn}`
passes the built-in collision check (the name isn't in
`DEFAULT_FUNCTION_REGISTRY`) but `fn` is never called — the hardcoded
dynamic-planner branch always wins. Contradicts the documented guarantee
that built-ins "can never be shadowed" (`compile/functions.py:108-110`).

**Fix:** Either reserve `"plan_execute"` explicitly in the collision check
(so registering it is rejected with a clear error) or route it through
the same registry-lookup path as `route_dispatch`/`aggregate_perspectives`.

**Done when:** A test proves a custom `"plan_execute"` function is either
rejected at load time with a clear error, or actually invoked when a node
sets `options.function: plan_execute`.

### H02 — `load_custom_functions()` has no built-in-shadow guard of its own

**Problem:** `compile/functions.py:90`'s docstring claims a custom module
"can never override built-in behavior," but the guarantee only holds
because `custom_function_registry()` happens to pre-seed the dict with
`DEFAULT_FUNCTION_REGISTRY` before calling it.
`tests/test_custom_function_module.py::test_production_requires_allowlist`
already proves the unseeded case: calling `load_custom_functions(path,
functions={})` registers a colliding `route_dispatch` name.

**Fix:** Move the shadow-guard check inside `load_custom_functions()`
itself (e.g. always merge against `DEFAULT_FUNCTION_REGISTRY` internally,
or raise if the caller's seed dict is missing required built-in keys).

**Done when:** `load_custom_functions(path, functions={})` with a
colliding name raises/rejects instead of registering, and the docstring's
claim is true regardless of caller.

### H03 — bad `AGENT_FUNCTION_MODULE` crashes every preset, not just the ones using it

**Problem:** `presets/catalog.py:180` (`Preset.build`) and `agent.py`'s
`_build_graph_root` call `custom_function_registry()` unconditionally,
even for graphs with zero `kind: function` nodes. A
missing/non-allowlisted/malformed module raises `OSError`/`ValueError`
out of `get_root_agent()` and fails the whole served agent.

**Fix:** Only resolve the custom registry when the graph/preset being
built actually contains a `kind: function` node (or lazily resolve
per-node instead of eagerly for the whole graph).

**Done when:** A config with an invalid `AGENT_FUNCTION_MODULE` still
serves presets/graphs that don't reference custom functions; a test
covers this.

### H04 — whitespace-padded allowlist entries silently never match

**Problem:** `util.py:52`'s allowed-roots generator filters entries with
`if value.strip()` but builds the `Path` from the unstripped `value`, so
`"/allowed/a: /allowed/b"` (stray space after the separator) makes the
second entry resolve with a literal leading space and never match a real
directory.

**Fix:** Strip `value` before constructing the `Path`.

**Done when:** A test with a whitespace-padded allowlist entry resolves
correctly.

### H05 — use-case loader was never migrated to the shared allowlist helper (dedupe claim is false)

**Problem:** CHANGELOG.md, the ADR-005 addendum, and
`compile/functions.py`'s docstring all claim the allowlist/production
logic is now shared with the use-case loader via
`util.resolve_allowlisted_file` ("R13-style dedupe"), but
`use_cases/registry.py:160` still runs its own independent, byte-for-byte
copy of the same logic (confirmed: `git diff -- src/basic_agent/use_cases/registry.py`
is empty across the G01 commit).

**Fix:** Migrate `load_custom_use_cases` (and its importlib boilerplate,
`registry.py:183-190`) to call `util.resolve_allowlisted_file`, and
correct the CHANGELOG/ADR-005/docstring claims if migration is
deliberately deferred.

**Done when:** `registry.py` calls `util.resolve_allowlisted_file` (no
independent copy remains), or the false "shared" claims are removed from
CHANGELOG.md, ADR-005, and `compile/functions.py`.

### H06 — `custom_function_registry()` re-imports the module on every call (no caching)

**Problem:** Unlike `use_cases/registry.py`'s `get_default_registry()`
(memoized in a module-level global), `compile/functions.py:103`'s
`custom_function_registry()` re-resolves the allowlist and fully
re-imports/re-execs the `AGENT_FUNCTION_MODULE` file on every call.
Callers that build more than one root/preset per process (several tests
already do) re-run the module's top-level code each time, resetting any
module-level state and returning function objects with different
identity across calls.

**Fix:** Memoize the registry the same way `get_default_registry()` does.

**Done when:** Two calls to `custom_function_registry()` in the same
process return the same function objects (identity-equal) and the module
is imported once.

### H07 — collision-skip log message blames the wrong module

**Problem:** `compile/functions.py:90` logs
`"Custom graph function %r skipped: %s already provides it"` with
`CUSTOM_FUNCTION_MODULE_ENV` (the literal string
`"AGENT_FUNCTION_MODULE"`) as the second value — naming the operator's
own env var, not the built-in registry or prior module that actually
caused the skip.

**Fix:** Log the actual source of the collision (e.g. "a built-in
function" or the module that already registered the name).

**Done when:** The log message names the real conflicting source.

### H08 — `sys.modules` left in a broken state on partial custom-module import failure

**Problem:** `compile/functions.py:61` assigns
`sys.modules[module_name] = module` before `spec.loader.exec_module(module)`
runs, with no cleanup if `exec_module` raises partway through — unlike
CPython's real import machinery, which removes the entry on exec failure.

**Fix:** Wrap `exec_module` in try/except and `del sys.modules[module_name]`
on failure (or only insert into `sys.modules` after `exec_module`
succeeds).

**Done when:** A custom module whose top-level code raises leaves no
entry in `sys.modules`; a test covers this.

### H09 — unset/unlisted `DEPLOYMENT_ENV` silently skips allowlist enforcement

**Problem:** `util.py:57`'s production check matches `DEPLOYMENT_ENV`
against an exact-string set (`prod`, `production`, `staging`,
`cloud-run`, `cloudrun`); any unset or unlisted value (e.g. `prod-us`) is
silently treated as non-production, skipping allowlist enforcement. This
diff extends the pre-existing (use-case-only) fail-open behavior to a
second, more dangerous surface: arbitrary code execution via
`AGENT_FUNCTION_MODULE`.

**Fix:** Fail closed on unrecognized `DEPLOYMENT_ENV` values for the
function-module path (or require an explicit "non-production" opt-in
rather than defaulting to it).

**Done when:** An unset/unrecognized `DEPLOYMENT_ENV` with
`AGENT_FUNCTION_MODULE` set either enforces the allowlist or raises,
rather than silently bypassing it; a test covers this.

### H10 — allowlist path containment check is case-sensitive, breaks on macOS

**Problem:** `util.py:63`'s `candidate == root or root in candidate.parents`
is a case-sensitive comparison, but `Path.resolve()` doesn't normalize
case on case-insensitive filesystems (macOS's default APFS), so an
allowlist root and a same-file module path differing only in case fail
the check.

**Fix:** Normalize case for comparison on case-insensitive platforms, or
document the requirement that allowlist entries must case-match exactly.

**Done when:** An allowlist root and a module path that differ only in
case resolve consistently on macOS; a test covers this (or the
limitation is explicitly documented).

### H11 — ADR-005 addendum misnames `_build_graph_root`

**Problem:** `docs/ADR-005-graph-first-taxonomy-and-configuration.md:192`
names the call site `agent._build_root_graph`; the real function
(`agent.py:428`) is `_build_graph_root`. CHANGELOG.md's G01 entry has the
correct name.

**Fix:** Correct the ADR-005 addendum to `_build_graph_root`.

**Done when:** ADR-005 and CHANGELOG.md agree on the function name.

### H12 — `ARCHITECTURE.md` module-map row for `util.py` is stale

**Problem:** `docs/ARCHITECTURE.md:62` still lists only `is_production()`
and `split_csv()` for `util.py`, unchanged by the G01 commit even though
it added a third public export, `resolve_allowlisted_file()`. G02's new
drift-guard tests only check row *presence*, not row *content*, so this
staleness passes them undetected.

**Fix:** Add `resolve_allowlisted_file()` to the `util.py` module-map row.

**Done when:** The `util.py` row lists all three public exports.

### H13 — README.md not updated for the new `AGENT_FUNCTION_MODULE*` env vars

**Problem:** `.env.example`, CHANGELOG.md, and TODO.md were updated for
the new `AGENT_FUNCTION_MODULE`/`AGENT_FUNCTION_MODULE_ALLOWLIST` config
surface, but README.md — which documents the analogous
`AGENT_USE_CASE_MODULE` pair by pointing readers at `.env.example`
(README.md:63) — was not given an equivalent pointer.

**Fix:** Add a README.md pointer for `AGENT_FUNCTION_MODULE`/
`AGENT_FUNCTION_MODULE_ALLOWLIST`, matching the existing
`AGENT_USE_CASE_MODULE` pattern.

**Done when:** README.md documents (or points to) both env var pairs
symmetrically.

### H14 — needless wrapper `_custom_function_registry()` in `agent.py`

**Problem:** `agent.py:421`'s `_custom_function_registry()` is a private
5-line wrapper that only lazy-imports and calls through to
`compile.functions.custom_function_registry()`, used at one call site,
with no circular-import need forcing the indirection — inconsistent with
`catalog.py`'s direct call to the same function.

**Fix:** Delete the wrapper; call `custom_function_registry()` directly
at the `_build_graph_root` call site.

**Done when:** `agent.py` has no `_custom_function_registry` wrapper.

### H15 — duplicate `_write_config` test helper

**Problem:** `tests/test_custom_function_module.py:115`'s
`_write_config(tmp_path, monkeypatch, content)` is a byte-for-byte
duplicate of `tests/test_served_graph_config.py`'s `_write_config`
(line 155).

**Fix:** Extract the shared helper into a common test-support module (or
import one from the other) instead of maintaining two copies.

**Done when:** Only one implementation of `_write_config` exists, shared
by both test files.

## History

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
