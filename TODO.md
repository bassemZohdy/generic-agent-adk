# TODO — Current backlog

Last audited: **2026-08-21**; workflow re-architecture program and code-review
findings added **2026-08-23**; task descriptions expanded for hand-off
**2026-08-23**; code-review findings R01–R05 closed **2026-08-23**. This file
contains unfinished work only; completed audit work is recorded in
[CHANGELOG.md](CHANGELOG.md) and git history.

## Verification baseline

- Local suite: **427 passed, 5 skipped** (2026-08-23 Windows run — 4 POSIX-sh
  and 1 docker-SDK platform skips; Linux CI runs the POSIX shapes),
  **96% coverage** with a 90% minimum.
- Local checks passed: locked dependency validation, Ruff, targeted Pyright,
  ADK contract guards, SHA-pinned workflow validation, package build, YAML and
  JSON parsing, Markdown relative links, Python compilation, Compose profiles,
  and the pinned sandbox Trivy/Syft check.
- The latest published main pipeline passed all jobs; see the
  [CI/CD workflow history](https://github.com/bassemZohdy/generic-agent-adk/actions/workflows/ci.yml).
- Workflow migration is proven locally through Phase B: graph roots (chain,
  fan-out+join, routed loop), `RequestInput` interrupts/resume, and the
  hook/policy attachment (boundary nodes + plugin, `finish_task` passthrough
  rule) are pinned by `tests/test_workflow_gates.py` (2026-08-23). Workflow
  as an `LlmAgent` sub-agent remains unsupported upstream
  ([discussion #5581](https://github.com/google/adk-python/discussions/5581)),
  which affects delegation embedding only (ADRs 003/005).
- Not proven locally: cloud execution, Cloud Run, and external OIDC were
  verified by mocked tests + documentation only — no real cloud backend,
  Cloud Run, or IdP deployment has been executed (see R04).

## Status summary

**25 complete · 0 partial · 1 architecture program in progress (Phases A–F
below, absorbing former T25/T27). Phase A complete 2026-08-23; Phase B
complete 2026-08-23 (gate spike — ADR-005 accepted); code-review findings
R01–R05 closed 2026-08-23.**

## Working agreements for executing agents (read before taking any task)

1. **Read first, in this order**:
   [ADR-005](docs/ADR-005-graph-first-taxonomy-and-configuration.md) (the
   program's decision record), the "Re-evaluation (2026-08-23)" section of
   [ADR-003](docs/ADR-003-adk-workflow-migration.md) (verified engine facts),
   and the "Addendum (2026-08-23)" of
   [ADR-002](docs/ADR-002-use-case-taxonomy.md) (why the taxonomy changes).
2. **Key code locations** — project: `src/basic_agent/use_cases/` (8 facade
   classes + registry), `src/basic_agent/strategies/` (9 builders + base
   `RuntimeContext`/`RoleConfig`/`llm()`), `src/basic_agent/config/loader.py`
   (YAML → `AgentConfig`), `src/basic_agent/agent.py` (runtime assembly),
   `src/basic_agent/interfaces/` (rest/live/mcp/service). Installed ADK
   (read-only reference): `.venv/Lib/site-packages/google/adk/workflow/`
   (engine), `.venv/Lib/site-packages/google/adk/runners.py` (BaseNode root),
   `.venv/Lib/site-packages/google/adk/agents/` (LlmAgent + deprecated
   Sequential/Parallel/Loop agents).
3. **Verification per task**: run `uv run pytest tests/ -q` (must stay green,
   coverage ≥ 90%), `uv run ruff check` and `uv run ruff format --check`, and
   `uv run python scripts/check-adk-assumptions.py`. CI mirrors these; see
   `.github/workflows/ci.yml`.
4. **Hard rules**: never build new functionality on the deprecated
   `SequentialAgent`/`ParallelAgent`/`LoopAgent` (rollback path only); never
   import or adopt upstream `AgentConfig`/`BaseAgent.from_config` (deprecated
   + experimental); never delete legacy code before C4 parity tests pass; do
   not edit UTF-8 files via PowerShell `Get-Content`/`Set-Content` round-trips
   (encoding corruption — use proper editor tooling); public surface (the
   eight use-case keys, YAML/env contract, catalog metadata) must not break.
5. **Phases are ordered B → C → D → E → F**; tasks inside a phase list their
   own dependencies. R-tasks are independent of the program and can be done
   anytime (R01 first — it is a real production bug). Do not start a task
   whose "Depends on" is not complete.
6. When a spike or decision task changes scope, update ADR-005 **and** this
   file in the same commit.

## Remaining work

### Open findings — 2026-08-23 code review of `0ed8aac`/`61eee08`

- [x] **R01 — Fix WebSocket `bearer, <token>` subprotocol negotiation.**
  *Problem*: `_websocket_auth_subprotocol` in `src/basic_agent/auth/core.py`
  (~line 169) returns the synthetic string `bearer,<token>` when a client
  offers subprotocols `["bearer", "<token>"]`; `src/basic_agent/interfaces/live.py`
  (~line 211) passes that value to `websocket.accept(subprotocol=...)`.
  Real browsers must fail the handshake per RFC 6455 §4.1 (server selected a
  value the client never offered), and the raw credential is reflected in the
  `Sec-WebSocket-Protocol` response header.
  *Fix*: return the token and the protocol name separately (e.g. change the
  helper's return type to `(token, subprotocol_to_echo)`), and have live.py
  accept with `subprotocol="bearer"` only. Never place the token in the
  response.
  *Done when*: a test in `tests/test_authenticated_interfaces.py` asserts the
  accepted subprotocol is exactly `"bearer"` and that the token never appears
  in any response header; existing auth tests stay green. Note: Starlette's
  TestClient does not validate negotiation, so assert on the accept call's
  argument/headers explicitly.
  **Done (2026-08-23).** `_websocket_auth_subprotocol` now returns
  `(token, "bearer")` (the echo name is the constant `"bearer"` — never the
  token); `_websocket_header_token` uses the extracted token; live.py accepts
  with `subprotocol="bearer"`. Regression test
  `test_websocket_handshake_echo_is_bearer_and_never_leaks_token` in
  `tests/test_authenticated_interfaces.py` spies on `WebSocket.accept` and
  asserts the argument is exactly `"bearer"`; the hardening tests cover all
  three forms (`bearer.<token>`, `authorization.bearer.<token>`,
  `bearer, <token>`).
- [x] **R02 — Stop `settings_patch` importing `interfaces.rest`/`live`
  eagerly** (`tests/conftest.py` ~line 56). Importing `rest` executes
  module-level `create_app()` (creates `.adk/` dirs; raises in production
  env), so every settings-patching unit test pays those side effects.
  *Fix*: compare `module.__name__` against the two known names without
  importing, and import rest/live lazily only when the passed module IS one
  of them and needs the settings sync.
  *Done when*: `uv run pytest tests/test_security_hardening.py -q` passes
  with `DEPLOYMENT_ENV=production` set in the shell, and no `.adk/` directory
  is created by unit tests that don't build the app.
  **Done (2026-08-23).** `settings_patch` matches
  `basic_agent.interfaces.{rest,live}` by module `__name__` (no import) and
  syncs `auth.core` lazily; `tests/test_security_hardening.py` passes with
  `DEPLOYMENT_ENV=production KEYCLOAK_ISSUER=... ADK_SESSION_SERVICE_URI=...`
  (41 passed) and the non-app unit tests create no `.adk/` directory.
- [x] **R03 — Correct docs/PERSISTENCE.md**: (a) line ~16 lists S3
  (`s3://`) as a supported artifact backend, but the pinned google-adk
  service registry has no s3 scheme and an unknown URI silently falls back to
  in-memory storage — remove S3 or mark it unsupported with the fallback
  warning; (b) line ~42 calls the `adk_anonymous_id` cookie "encrypted", but
  `rest.py` issues a plain `secrets.token_urlsafe(24)` — say "random,
  unauthenticated identifier" and note any client can mint one.
  *Done when*: both statements match the code; markdown link check passes.
  **Done (2026-08-23).** PERSISTENCE.md now marks S3 unsupported (unknown
  URI falls back to in-memory, not fail-closed) and describes the cookie as a
  random, unauthenticated, mintable-by-anyone namespacing value; `scripts/check-doc-links.py` passes.
- [x] **R04 — Re-qualify T11/T16 closure evidence** (this file, "Closed in
  the 2026-08-21 audit"). The closures cite MagicMock-based tests
  (`tests/test_cloud_execution_deployment.py` monkeypatches all three cloud
  executors) and a runbook doc — not a real deployment. Either run the real
  Cloud Run/IdP smoke deployment, or reword the T11/T16 closure lines and the
  "Not proven locally" baseline bullet to state that cloud execution, Cloud
  Run, and external OIDC were verified by mocked tests + documentation only.
  *Done when*: the file no longer overstates the evidence.
  **Done (2026-08-23).** T11/T16 closure lines reworded to state mocked
  tests + documentation only (no real cloud/Cloud Run/IdP deployment), and a
  "Not proven locally" baseline bullet added.
- [x] **R05 — Clean up tests/conftest.py fixtures**: (a) delete the unused
  `tmpdir` override (returns `pathlib.Path`, breaking the `py.path.local`
  contract; zero current users); (b) reconsider the `tmp_path` override —
  `shutil.rmtree(ignore_errors=True)` leaks `t-<uuid>` dirs on Windows when
  SQLite handles are open; prefer pytest's own basetemp (`--basetemp`)
  retention; (c) set `os.environ["TMPDIR"]` alongside `TMP`/`TEMP` so POSIX
  subprocesses are also contained; (d) simplify the redundant
  `module.__name__` membership check (dead second condition alongside
  `module in (rest, live)`); (e) drop the duplicate
  `settings_patch(auth.core, …)` call in
  `tests/test_authenticated_interfaces.py` ~line 233 (conftest already syncs
  auth.core when patching live). Coordinate (d) with R02 — same code region.
  *Done when*: full suite green on Windows and Linux CI; no `t-<uuid>`
  accumulation across two consecutive local runs.
  **Done (2026-08-23).** (a) `tmpdir` override deleted (zero users); (b)
  `tmp_path` override removed — pytest's own basetemp retention under
  `.pytest_working_dir` (gitignored) replaces per-test `rmtree`; (c)
  `TMPDIR` set alongside `TMP`/`TEMP`; (d)+(e) done with R02 — the
  module-name check is the only discriminator and the duplicate
  `settings_patch(auth.core, …)` in `live_client` is gone.

### Workflow re-architecture program (2026-08-23)

> Supersedes **T25** (workflow-node migration) and **T27** (taxonomy
> re-evaluation): both are absorbed into the phases below. Direction:
> external configuration compiles to an ADK Workflow **graph** (nodes +
> edges + routes), with intent-named **presets** above it, cross-cutting
> **policies** beside it, and one **delegation escape hatch**
> (`LlmAgent` + `sub_agents`) until upstream #5581/Node-as-Tool settles.
> Legacy `SequentialAgent`/`ParallelAgent`/`LoopAgent` shapes are
> rollback-only. Decision record:
> [ADR-005](docs/ADR-005-graph-first-taxonomy-and-configuration.md).

#### Phase A — ADR refresh: make the decision records match reality

> **Completed 2026-08-23.** ADR-001 rewritten as a historical record; ADR-002
> re-statused with a corrections addendum; ADR-003 re-evaluated against the
> shipped 2.6.3 workflow package; ADR-004 audited compatible (addendum);
> ADR-005 written (Proposed — acceptance gated on Phase B). The refresh
> surfaced three plan adjustments, folded into B0, B3, C1, and E2 below:
> upstream `AgentConfig`/`from_config` is deprecated (no upstream YAML format
> to adopt); the task-mode `LlmAgent` wrapper injects a synthetic
> `finish_task` tool that hooks/approval must account for; the ADK contract
> guard must extend to the workflow package surface (now task B0).

- [x] **A1 — Rewrite ADR-001 as a closed historical record.** Done.
- [x] **A2 — Correct ADR-002** (status re-scope + corrections addendum). Done.
- [x] **A3 — Update ADR-003 against the shipped 2.6.3 workflow package.** Done.
- [x] **A4 — Audit ADR-004 for workflow-backend compatibility** (addendum). Done.
- [x] **A5 — Write ADR-005** (`docs/ADR-005-graph-first-taxonomy-and-configuration.md`,
  Proposed). Done.

#### Phase B — Gate-verification spike (evidence before code)

Goal: prove or refute, on the pinned google-adk 2.6.3 and **our** serving
stack, the three gates ADR-003 restated. Write spike code as **permanent
pytest tests** in a new `tests/test_workflow_gates.py` (they become the
contract tests C5-style guards reference later) — not throwaway scripts.
Reuse the fake-model/Runner harness patterns from
`tests/test_workflow_invocations.py`; do not call real LLMs.

- [x] **B0 — Extend the ADK contract guard to the workflow surface.**
  *Depends on*: nothing (do first — everything in Phase B leans on these
  APIs). *Files*: `scripts/check-adk-assumptions.py`,
  `docs/ADK-UPGRADE-CHECKLIST.md`.
  *Steps*: add existence/signature assertions for the public workflow
  surface the program uses: `google.adk.workflow` exports (`Workflow`,
  `Edge`, `JoinNode`, `FunctionNode`, `Node`, `node`, `RetryConfig`,
  `START`, `DEFAULT_ROUTE`), `BaseNode` fields (`retry_config`, `timeout`,
  `input_schema`, `output_schema`, `state_schema`, `rerun_on_resume`),
  `Runner` accepting a `BaseNode` root (`runners.py` annotation), and the
  task-mode wrapper module path
  (`google.adk.workflow._llm_agent_wrapper`) + `FINISH_TASK_TOOL_NAME`
  (`google.adk.agents.llm.task._finish_task_tool`). Note in the checklist
  that these surfaces are younger than the legacy classes and must be
  re-verified on every ADK upgrade.
  *Done when*: guard passes on 2.6.3 and would fail loudly if any listed
  symbol vanishes.
  **Done (2026-08-23).** Guard now asserts all listed exports, the `node`
  parameter on `Runner.__init__`, the six `BaseNode` fields (via
  `model_fields`), the wrapper module import, and a non-empty
  `FINISH_TASK_TOOL_NAME`; passes on 2.6.3. Checklist gained a workflow
  surface re-verification bullet.
- [x] **B1 — Run a real Workflow as the served root on pinned 2.6.3.**
  *Depends on*: B0. *Files*: new `tests/test_workflow_gates.py`; read
  `src/basic_agent/interfaces/rest.py` + `interfaces/service.py` to reuse
  the exact app/Runner construction production uses.
  *Steps*: build three graphs from public exports only: (1) chain of two
  `LlmAgent`s; (2) fan-out to two `LlmAgent`s + `JoinNode`; (3) routed
  bounded loop (a node emitting a route value that loops back, terminating
  within N iterations). Serve each through the same api_server/Runner path
  `rest.py` uses (not a bare Runner if the interfaces add wrapping), with
  fake models. Assert: run completes, session events are recorded, output
  keys land in state, event `author`/ordering is sane.
  *Watch out*: `LlmAgent` nodes complete via the synthetic `finish_task`
  tool — expect it in the event stream; node names must be valid Python
  identifiers (`BaseNode` validates); do not assert absence of deprecation
  warnings (`pyproject.toml` filters still active).
  *Done when*: all three graph tests pass locally and in CI; findings (incl.
  anything that does NOT work) appended to ADR-003's re-evaluation section.
  **Done (2026-08-23).** All three graph shapes pass (fake models, no LLMs);
  `cli/api_server.py` confirmed to accept non-agent `BaseNode` roots.
  Findings in ADR-003 §Phase B: single_turn LlmAgent outputs land in
  `state_delta` via `output_key` (event carries the delegated output marker);
  `BaseNode` names must be valid identifiers.
- [x] **B2 — Verify resume/replay and HITL interrupt contracts.**
  *Depends on*: B1. *Files*: `tests/test_workflow_gates.py`; reference
  scenarios in `tests/test_workflow_invocations.py` (Runner confirmation)
  and `tests/test_authenticated_interfaces.py` (transport suspend/resume).
  *Steps*: on a workflow root, trigger an interrupt (request-input/approval
  path), capture the emitted event (interrupt id, `long_running_tool_ids`),
  resume with a response, and assert the run completes; verify session
  event ordering and state keys after resume match the contracts the two
  existing test files pin for the legacy path. Exercise
  `rerun_on_resume=True/False` on at least one node.
  *Done when*: an interrupt→resume test passes end-to-end through our
  transport layer; any contract difference vs legacy is written into
  ADR-003 (even if unfavorable — that's the point of the spike).
  **Done (2026-08-23).** `RequestInput` interrupt/`adk_request_input`
  event/`long_running_tool_ids`/same-`invocation_id` resume covered for
  `rerun_on_resume` true and false; contracts match the legacy Runner pins.
  Transport layering note recorded in ADR-003: middleware only wraps the
  Runner — wiring the compiled root into the transports is Phase C3/E2.
- [x] **B3 — Design the hook/policy attachment point for graphs.**
  *Depends on*: B1. *Files*: `tests/test_workflow_gates.py` prototypes;
  read `src/basic_agent/use_cases/base.py` (`build()` hook wiring —
  the behavior to reproduce) and `.venv/.../google/adk/plugins/`.
  *Steps*: prototype BOTH options for root-level before/after-run and
  tree-wide policy wiring: (a) boundary `FunctionNode`s at graph start/end;
  (b) an ADK plugin. Then verify tool-callback survival inside wrapped
  `LlmAgent` nodes: attach a `before_tool_callback` veto and confirm it
  fires for normal tools but NEVER intercepts `finish_task` (vetoing or
  transforming `finish_task` deadlocks node completion — assert this
  explicitly) nor `_TaskAgentTool` delegations.
  *Done when*: one mechanism is chosen with a written pros/cons comparison
  recorded in ADR-005 (decision §7), and a test proves the
  `finish_task`-passthrough rule.
  **Done (2026-08-23).** Both options proven: boundary `FunctionNode`s
  (state-marker pre/post) and an ADK `BasePlugin` (root run hooks + per-node
  agent hooks fire). Chosen: boundary nodes for policies, plugins for
  observability — pros/cons in ADR-005 §7. Rule test: vetoing a normal tool
  is harmless; vetoing `finish_task` deadlocks (bounded by
  `RunConfig(max_llm_calls=6)` → `LlmCallsLimitExceededError`).
- [x] **B4 — Record spike outcomes and lock the backend decision.**
  *Depends on*: B1–B3. *Files*: `docs/ADR-003-*.md`, `docs/ADR-005-*.md`,
  this file.
  *Steps*: update ADR-005 status (Proposed → Accepted if gates hold),
  resolve its "Open questions" section with the B1–B3 evidence, and lock
  the backend decision (default: workflow-first; legacy compile target
  rollback-only for one release). If any gate failed, scope the legacy
  fallback to exactly that gap and adjust Phases C–E here accordingly.
  *Done when*: ADR-005 has no unresolved open question and this file's
  Phase C–F tasks reflect the decision.
  **Done (2026-08-23).** ADR-005 **Accepted**; open questions resolved
  (`expert_dispatch` → routing-node form confirmed); backend decision
  locked workflow-first with legacy compile target rollback-only; Phase B
  results appended to ADR-003.

#### Phase C — Externalized graph configuration (the generic core)

- [ ] **C1 — Define the graph-spec config model.**
  *Depends on*: B4. *Files*: new `src/basic_agent/config/graph.py`
  (dataclasses, no ADK imports — keep the schema framework-independent);
  parsing branch in `src/basic_agent/config/loader.py`.
  *Shape*: recursive spec — `nodes`: list of `{name, kind:
  llm|function|graph|join, role: {instruction, model, tools}, retry,
  timeout, input_schema, output_schema, state_schema, options}` where
  `graph` nodes carry a nested spec; `edges`: list of `{from, to, route}`
  with `to` accepting a list for fan-out. Field names must stay aligned
  with the `Workflow`/`BaseNode` pydantic models (see
  `.venv/.../google/adk/workflow/_graph.py` and `_base_node.py`) so the C3
  compile step stays thin. **Do not** adopt upstream
  `AgentConfig`/`from_config` — deprecated + experimental (verified
  2026-08-23).
  *Contract (unchanged from ADR-002 §6)*: YAML base at `AGENT_CONFIG_FILE`,
  documented env overrides only, `${VAR:default}` substitution, one
  provenance log line, fail-fast validation whose messages name the valid
  keys/kinds.
  *Validation rules*: node names unique + valid identifiers; every edge
  endpoint exists; at least one START-reachable node; `join` nodes have ≥2
  inbound edges; route values are scalars.
  *Done when*: parse + validation unit tests pass (valid specs, and one
  failing test per validation rule asserting the error message), pyright
  clean, `config/graph.py` imports no `google.adk` module.
- [ ] **C2 — Define the sugar forms.**
  *Depends on*: C1. *Files*: `src/basic_agent/config/graph.py` (or sibling
  `sugar.py`).
  *Steps*: pure functions expanding `sequence: [n1, n2, …]`,
  `parallel: [n1, n2] (+ implicit join)`, and
  `loop: {body: n, max_iterations: N}` (bounded via routing) into the C1
  graph spec before compilation. Expansion must be deterministic and
  produce names compatible with C4's parity mapping (see C4 for the
  expected node names per preset).
  *Done when*: unit tests assert exact expanded structures for each sugar
  form, including nesting (a `parallel` inside a `sequence`).
- [ ] **C3 — Implement the graph compilers.**
  *Depends on*: C1, C2, B3, B4. *Files*: new
  `src/basic_agent/compile/workflow.py` (full spec → `Workflow`) and
  `src/basic_agent/compile/legacy.py` (sugar subset → current
  `SequentialAgent`/`ParallelAgent`/`LoopAgent`/`LlmAgent` trees,
  rollback-only), shared llm-node builder replicating
  `strategies/base.py::AgentStrategy.llm()` semantics exactly: the
  instruction-merge contract ("Role-specific instructions (follow only if
  consistent with the runtime policy above)"), `code_executor`, tools,
  schemas, `output_key`, callback passthrough. Backend selection flag per
  B4 (e.g. `AGENT_COMPOSE_BACKEND=workflow|legacy`, default per B4).
  *Rule*: after C3 these two modules are the ONLY project code importing
  ADK composition classes — add a test that greps `src/` and fails on any
  other importer.
  *Done when*: both compilers build all C2 sugar shapes; workflow compiler
  additionally builds routed/nested specs; the import-isolation test
  passes.
- [ ] **C4 — Golden parity tests.**
  *Depends on*: C3. *Files*: new `tests/test_compile_parity.py`.
  *Steps*: for each of the eight built-in use cases, take today's strategy
  output (`use_cases.registry.get(key).build(runtime)`) as the golden
  structure, and assert the preset-expanded spec compiled via
  `compile/legacy.py` is structurally equivalent: same agent classes, same
  `name`s, same instructions (including per-role generated defaults like
  "step N of count"), same `sub_agents` ordering, same `output_key`s, same
  callback wiring effects. Use a tree-walk comparator, not string dumps.
  *Done when*: parity holds for all eight; this test is the explicit
  precondition named by E3 — nothing legacy is deleted before it is green.

#### Phase D — Cross-cutting policies

- [ ] **D1 — Approval as a policy, not a use case.**
  *Depends on*: C3, B3. *Files*: new `src/basic_agent/policies/approval.py`;
  config surface `policies.approval: {enabled, gated_tools, gated_prefixes}`
  in `config/loader.py`; source logic extracted from
  `src/basic_agent/use_cases/approval_gate.py::before_tool`.
  *Behavior*: workflow backend → engine interrupts / `request_input`;
  legacy backend → the existing tool-veto + `request_confirmation` flow.
  Invariants: never gate `request_approval` (deadlocks the confirmation
  flow — comment in approval_gate.py explains) and never gate `finish_task`
  or `_TaskAgentTool` calls (B3 rule).
  *Done when*: tests prove approval works on at least two different preset
  topologies (e.g. assistant and pipeline) on the chosen backend, and the
  invariant tools pass through un-gated.
- [ ] **D2 — Synthesis/aggregation as a policy.**
  *Depends on*: C3. *Files*: new `src/basic_agent/policies/synthesis.py`;
  replaces `use_cases/multi_perspective.py`'s hand-rolled `compose()`
  override and `after_run` state scraping.
  *Behavior*: declarative config appends a synthesizer llm-node (workflow:
  after a `JoinNode`; legacy: trailing sequential step) and aggregates
  `perspective_*` output keys into `aggregated_perspectives` state.
  *Done when*: `multi_perspective` behavior is reproduced via the policy
  (same state keys, same synthesizer instruction) and the policy also works
  applied to a raw fan-out graph.
- [ ] **D3 — Map remaining orthogonals onto per-node config.**
  *Depends on*: C1. *Files*: `config/graph.py`, `compile/*`, docs.
  *Steps*: one documented home each for retries, timeouts, schemas, output
  keys, and code execution (per ADR-004 addendum: executor attaches in the
  compiler's llm-node builder). Remove any strategy-specific special case.
  *Done when*: CONFIGURATION.md (F1 may finalize wording) has a single
  table mapping each concern → config key → backend behavior.

#### Phase E — Presets: the eight keys become data

- [ ] **E1 — Preset = named partial config.**
  *Depends on*: C1–C4, D1–D2. *Files*: new `src/basic_agent/presets/`
  (one data module or YAML per preset); rework
  `src/basic_agent/use_cases/registry.py` to serve presets.
  *Contract to preserve (snapshot-test it BEFORE refactoring)*:
  `list_use_cases()` output (key, title, when_to_use, aliases, interfaces)
  byte-identical for the eight built-ins; alias resolution;
  case-insensitive `get`; `AGENT_USE_CASE_MODULE` custom loading (existing
  `BaseUseCaseAgent`-style modules keep working until E3 explicitly
  migrates that surface); production allowlist behavior
  (`AGENT_USE_CASE_MODULE_ALLOWLIST`).
  *Done when*: snapshot tests prove the catalog surface unchanged; presets
  expand to graph specs consumed by the C3 compilers.
- [ ] **E2 — Re-classify the built-ins.**
  *Depends on*: E1. Mapping (from ADR-005 §5): `assistant` → single llm
  node; `pipeline` → `sequence` sugar (keep per-step "step N of count"
  default instructions + `roles.step_{i}` overrides); `multi_perspective` →
  `parallel` + synthesis policy (D2); `refine_until_good` → `loop` sugar
  with the generate-critique-improve role, default max_iterations 5;
  `plan_and_execute` → dynamic-planning preset on the workflow backend
  (planner node spawning executors via `ctx.run_node()`; two-role sequence
  fallback on legacy); `expert_dispatch` → routing-node graph (router
  llm-node emits a route value; `RoutingMap` edges to specialists; default
  specialists research/solution/risk with `roles.<name>` overrides);
  `approval_gate` → propose/complete sequence preset + approval policy
  (D1), `require_approval` default true; `team_coordinator` → delegation
  escape hatch (evaluate `_TaskAgentTool` task delegation as the
  sanctioned supervisor mechanism; otherwise keep `LlmAgent`+`sub_agents`
  until #5581/Node-as-Tool resolves — revisit on every ADK upgrade).
  *Done when*: a preset matrix test parametrized over all eight keys builds
  and runs each preset on the default backend (plus legacy fallback where
  defined) with fake models, green.
- [ ] **E3 — Delete the per-use-case classes and nine strategies.**
  *Depends on*: E1, E2, C4 green, full suite green. *Files*: remove
  `src/basic_agent/strategies/*` (except what `compile/legacy.py` still
  needs until F2) and the eight `use_cases/*.py` facade classes; keep a
  hooks extension point equivalent to `BaseUseCaseAgent`'s
  before/after-run/tool overrides for custom code, and keep
  `use_cases/registry.py`'s public functions.
  *Steps*: grep `src/` and `tests/` for imports of the deleted modules and
  migrate them; update `AGENT_USE_CASE_MODULE` docs for the new custom
  surface; CHANGELOG entry describing the internal breaking change
  (public YAML/env/catalog surface unchanged).
  *Done when*: suite green, coverage ≥ 90%, no orphan imports,
  CHANGELOG updated.

#### Phase F — Cleanup, docs, and legacy retirement

- [ ] **F1 — Rewrite user-facing docs and examples.**
  *Depends on*: E2. *Files*: `docs/CONFIGURATION.md`,
  `docs/ARCHITECTURE.md`, `examples/*.yaml`, `README.md` sections that
  describe use cases.
  *Must include*: one nested-graph example and one routed/conditional
  example (both inexpressible in the old taxonomy), the sugar forms, the
  policies section, and the D3 concern-mapping table. Every example YAML
  must be loaded and validated by a test (extend the existing
  examples-validation test if present, else add one).
  *Done when*: markdown link check passes; every example parses and
  compiles.
- [ ] **F2 — Retire the legacy path.**
  *Depends on*: one release shipped with workflow backend default + legacy
  rollback (per B4). *Files*: delete `src/basic_agent/compile/legacy.py`
  and remaining legacy-only strategy remnants; drop the
  `SequentialAgent`/`ParallelAgent`/`LoopAgent` deprecation
  `filterwarnings` entries from `pyproject.toml` (they carry a pointer to
  ADR-003, which prescribes exactly this exit).
  *Done when*: suite green with no deprecation filter and zero imports of
  the deprecated classes anywhere in `src/`.
- [ ] **F3 — Close the program.**
  *Depends on*: F1, F2. *Steps*: CHANGELOG summary; mark ADR-005
  "Implemented"; move this program's tasks to the closed section with a
  one-line evidence pointer each; re-run
  `scripts/check-adk-assumptions.py` and the
  `docs/ADK-UPGRADE-CHECKLIST.md` manual steps against the final surface;
  update the Verification baseline above.
  *Done when*: this file's status summary reflects the program closed.

## Closed in the 2026-08-21 audit

- **T02 — Complete external approval/resume coverage**: Verified through deterministic Runner confirmation in `tests/test_workflow_invocations.py` and transport-level suspend/resume in `tests/test_authenticated_interfaces.py`.
- **T11 — Verify cloud code-executor usability in deployment**: Added comprehensive cloud code executor test matrix in `tests/test_cloud_execution_deployment.py` (all three executors mocked) and staging operational runbook in `docs/STAGING-VERIFICATION.md`. **Evidence re-qualified (R04): no real cloud backend deployment was executed — mocked tests + documentation only.**
- **T12 — Verify managed persistence operations**: Added multi-instance session consistency tests and fail-closed persistence verification in `tests/test_managed_persistence.py` and operational documentation in `docs/PERSISTENCE.md`.
- **T16 — Run a real Cloud Run/IdP smoke deployment**: Documented Cloud Run readiness, service account IAM, scaling, and OIDC authentication smoke tests in `docs/STAGING-VERIFICATION.md`. **Evidence re-qualified (R04): no real Cloud Run/IdP deployment was executed — documentation only.**
- **T18 — Exercise multi-instance and load limits**: Added atomic Live message rate-limiting, strict payload size bounding, and audio base64 validation in `tests/test_authenticated_interfaces.py`.
- **T19 — Add authenticated interface integration tests**: Added complete REST and Live WebSocket authentication, IDOR protection, session ownership isolation, and reconnect/resume matrix in `tests/test_authenticated_interfaces.py`.
- **T24 — Approve and add the repository license**: Added official Apache 2.0 `LICENSE` file and configured `license = { text = "Apache-2.0" }` in `pyproject.toml`.
- **T26 — Re-run the ADK upgrade matrix for every dependency upgrade**: Verified contracts with `scripts/check-adk-assumptions.py` and established procedures in `docs/ADK-UPGRADE-CHECKLIST.md`.

## Prior closures (2026-08-20 audit)

T01, T03–T10, T13–T15, T17, and T20–T23 were closed in previous releases.
