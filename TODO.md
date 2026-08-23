# TODO — Current backlog

Last audited: **2026-08-21**; workflow re-architecture program and code-review
findings added **2026-08-23**; task descriptions expanded for hand-off
**2026-08-23**; code-review findings R01–R05 closed **2026-08-23**. This file
contains unfinished work only; completed audit work is recorded in
[CHANGELOG.md](CHANGELOG.md) and git history.

## Verification baseline

- Local suite: **421 passed, 5 skipped** (2026-08-23 F2 run — 4 POSIX-sh and
  1 docker-SDK platform skips; Linux CI runs the POSIX shapes), **93%
  coverage** with a 90% minimum.
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

**Program closed 2026-08-23 — 25 complete · 1 architecture program complete
(Phases A–F, ADR-005 Implemented, workflow backend only after F2).
Unchecked tasks: none.** ⚠️ **Re-qualification (2026-08-23 deep code review,
see R06–R15 below): the "Done" evidence for C1/D1/D3/E1/E2/F1 was produced
entirely through direct calls to `preset.build(runtime)` / the compiler
modules — never through `agent.py`'s actual served entrypoint. R06 found
that entrypoint never reads `config.graph` or `config.policies` at all, so
the declarative graph-spec/policies config surface documented in
CONFIGURATION.md and demonstrated in `examples/graph-nested.yaml` /
`examples/graph-routed.yaml` has no effect when mounted as a real agent
config — those examples are validated by `test_graph_examples.py` calling
the compiler directly, not by being served. Treat "ADR-005 Implemented" as
"compiler and presets implemented; declarative graph/policies config not
yet load-bearing" until R06 closes.

**Review log**: streak=3 (final), last_reviewed=2026-08-23, status=stopped —
three consecutive clean passes, recurring audit self-terminated (no new
commits since V01's fix at `8e0ef4f`; suite 425 passed/1 skipped, ruff
check + format check clean, ADK contract guard clean, no encoding issues)

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
   (runtime assembly), `interfaces/` (rest/live/mcp/service). Installed ADK
   (read-only reference): `.venv/Lib/site-packages/google/adk/workflow/`
   (engine), `.venv/Lib/site-packages/google/adk/runners.py` (BaseNode root),
   `.venv/Lib/site-packages/google/adk/agents/` (LlmAgent plus the retired
   Sequential/Parallel/Loop classes — nothing in `src/` imports them).
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
5. Phases are historical (the program is closed); new tasks are
   self-contained with their own dependencies stated. R-tasks from the code
   review are independent and can be done anytime. Do not start a task
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

- [x] **C1 — Define the graph-spec config model.**
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
  **Done (2026-08-23).** `config/graph.py` (pure dataclasses:
  `GraphSpec`/`GraphNodeSpec`/`GraphEdgeSpec`/`RetrySpec`, `START` and
  `DEFAULT_ROUTE` sentinels — AST-verified framework-free), loader branch
  (recursive parse incl. nesting), and the exact C1 validation rules with
  one failing test each (`tests/test_graph_config.py`, 17 tests). Node
  shape gained `output_key` per ADR-005 decision §1 (B1 proved LlmAgent
  outputs land in state via `output_key`).
- [x] **C2 — Define the sugar forms.**
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
  **Done (2026-08-23).** `config/sugar.py` (pure, no ADK imports):
  deterministic naming (`<first>_join`, `<body>_loop_counter`,
  `sub_<index>`), `AGAIN_ROUTE`/`DEFAULT_ROUTE` routing for bounded loops,
  nested sugars become `graph`-kind subgraph nodes;
  `tests/test_sugar_forms.py` pins exact structures incl. nesting (15
  tests). Loader sugar branch: exactly one of `sequence`/`parallel`/`loop`
  per graph (mutually exclusive with explicit `edges`), name references
  resolved against declared nodes.
- [x] **C3 — Implement the graph compilers.**
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
  **Done (2026-08-23).** `compile/` ships: `workflow.py` (explicit-edge
  compile of the full spec incl. routed/fan-out/join and nested subgraphs;
  built-in bounded-loop counter via options.kind='loop_counter'; function
  registry for function nodes), `legacy.py` (sugar-subset only — raises on
  explicit-edge specs; rollback-only), `llm_node.py` (exact
  `AgentStrategy.llm()` semantics + per-node output_key/schemas/retry/
  timeout), `compose_backend()` (`AGENT_COMPOSE_BACKEND`, default
  `workflow`). Import-isolation test greps `src/` for composition imports
  and fails on anything outside `compile/` and the E3-retirement modules
  (agent.py, strategies/, use_cases/). `tests/test_compile.py` (13 tests)
  includes end-to-end runs of compiled chains and bounded loops with fake
  models.
- [x] **C4 — Golden parity tests.**
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
  **Done (2026-08-23) with one scoping note.** Tree-walk parity
  (`tests/test_compile_parity.py`, 7 tests) holds for the six
  legacy-expressible presets: `assistant` (single llm node → bare LlmAgent),
  `pipeline` (sequence + generated "step N of count" defaults),
  `multi_perspective` (nested parallel sugar named `parallel_agent` +
  synthesizer → `SequentialAgent[ParallelAgent, LlmAgent]`),
  `refine_until_good` (loop, max_iterations 5), `approval_gate` (sequence),
  `plan_and_execute` (sequence). Comparator asserts class, name,
  instruction (post-merge), sub_agents ordering, output_key, and loop
  bounds; callback wiring is excluded deliberately (use-case hooks re-home
  into D1/D2 policies). **`expert_dispatch`/`team_coordinator` parity is
  tracked with E2**: they are delegation/escape-hatch shapes
  (LlmAgent + sub_agents), not graph-expressible until the E2 preset data
  exists — no legacy sugar mapping, so E3's "C4 green" precondition applies
  to this matrix plus the E2 preset-matrix test. Supporting changes: legacy
  compiler now compiles nested sugar (parallel inside a sequence) and a
  one-node sequence as a bare LlmAgent; sugar dataclasses carry an optional
  nested `name` (YAML `name:` supported inside nested sugar mappings);
  `expand_sugar` scopes the outer spec to fragment-touched nodes only.

#### Phase D — Cross-cutting policies

- [x] **D1 — Approval as a policy, not a use case.**
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
  **Done (2026-08-23).** `policies/approval.py` ships the extracted
  veto + `request_confirmation` flow with the B3 invariants
  (`UNCONDITIONAL_TOOLS = {request_approval, finish_task}` plus
  `_TaskAgentTool` detection) and an `apply_approval_policy()` walker that
  chains the callback after existing per-agent callbacks on both
  `sub_agents` trees AND `Workflow.graph.nodes`. Config surface
  `policies.approval` parses in the loader. `tests/test_policies.py`
  proves: invariant passthrough (unit), gating on the compiled assistant
  topology, and full interrupt→resume gating on the compiled pipeline
  topology (gated tool never runs, confirmation interrupt raised, pipeline
  completes after resume). Workflow-backend interrupt notes: the same
  `request_confirmation` callback is the engine interrupt on LlmAgent
  nodes; `request_input`-based (FunctionNode) policy interrupts were proven
  in B2.
- [x] **D2 — Synthesis/aggregation as a policy.**
  *Depends on*: C3. *Files*: new `src/basic_agent/policies/synthesis.py`;
  replaces `use_cases/multi_perspective.py`'s hand-rolled `compose()`
  override and `after_run` state scraping.
  *Behavior*: declarative config appends a synthesizer llm-node (workflow:
  after a `JoinNode`; legacy: trailing sequential step) and aggregates
  `perspective_*` output keys into `aggregated_perspectives` state.
  *Done when*: `multi_perspective` behavior is reproduced via the policy
  (same state keys, same synthesizer instruction) and the policy also works
  applied to a raw fan-out graph.
  **Done (2026-08-23).** `policies/synthesis.py`: `synthesizer_node()`
  (canonical instruction/output_key — byte-equal to the use case's),
  `with_synthesis()` (pure spec transform: appends the synthesizer after a
  single terminal — the parallel sugar's join — or inserts a `synthesis_join`
  for raw fan-outs), `legacy_multi_perspective_spec()` (nested parallel +
  trailing step), `make_synthesis_after_run()` (same `perspective_*` →
  `aggregated_perspectives` aggregation). Config surface
  `policies.synthesis` parses. Tests: raw fan-out + join compile and run
  with fake models (state keys match), after-run aggregation reproduces the
  multi_perspective state contract, and the legacy spec reproduces the
  golden parity (the C4 multi_perspective case now consumes this policy
  helper).
- [x] **D3 — Map remaining orthogonals onto per-node config.**
  *Depends on*: C1. *Files*: `config/graph.py`, `compile/*`, docs.
  *Steps*: one documented home each for retries, timeouts, schemas, output
  keys, and code execution (per ADR-004 addendum: executor attaches in the
  compiler's llm-node builder). Remove any strategy-specific special case.
  *Done when*: CONFIGURATION.md (F1 may finalize wording) has a single
  table mapping each concern → config key → backend behavior.
  **Done (2026-08-23).** CONFIGURATION.md gained a "Graph configuration
  (graph-first, ADR-005)" section with the graph/policies YAML shapes and
  the concern → config key → backend behavior table (retries/timeouts/
  schemas/output keys/code execution). Executor attachment verified: the
  compiler's shared llm-node builder passes `RuntimeContext.code_executor`
  to every LlmAgent (ADR-004 attachment point moved with C3 — evidenced by
  `tests/test_compile.py` asserting the executor, retry_config, timeout,
  schema, and output_key on compiled nodes; legacy compile applies
  schemas/output keys/executor and documents retry/timeout as
  workflow-backend-only). Strategy special cases: the multi_perspective
  `output_key` override and approval `before_tool` were the per-concern
  special cases and are re-homed by D2/D1; nothing remains in the
  strategies that D3 must remove (strategies themselves retire in E3).
  No example config changed — F1 finalizes docs wording.

#### Phase E — Presets: the eight keys become data

- [x] **E1 — Preset = named partial config.**
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
  **Done (2026-08-23).** `presets/catalog.py` ships the eight preset
  records (metadata byte-identical to the snapshot — hardcoded
  `CATALOG_SNAPSHOT` in `tests/test_presets.py` taken before the refactor —
  plus `defaults` and spec builders per the ADR-005 §5 classification:
  assistant single node, pipeline sequence with "step N of count" defaults
  and `roles.step_{i}` overrides, multi_perspective = with_synthesis
  (workflow) / `legacy_multi_perspective_spec` (legacy), refine loop,
  approval_gate sequence, plan_and_execute sequence, expert_dispatch
  routing graph (`options.function: route_dispatch` + per-specialist
  routes), team_coordinator escape hatch (builder raises with the documented
  reason). Registry serves presets (`get_preset`/`has_preset`/
  `list_presets` with the same alias/case resolution; facades remain the
  build path until E3; custom-module loading untouched). Finding recorded:
  ADK graph validation rejects duplicate (from,to) edge pairs even with
  different routes, so the routing preset has no DEFAULT_ROUTE fallback —
  the router function must always emit a valid route (validated at runtime).
  `tests/test_presets.py` (10 tests): snapshot, metadata parity, preset
  resolution, spec expansion + compile on both backends, escape-hatch
  behavior.
- [x] **E2 — Re-classify the built-ins.**
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
  **Done (2026-08-23).** `tests/test_preset_matrix.py` (17 tests): all
  eight keys build and RUN with fake models — workflow backend via
  `Runner(node=...)` for every preset (team_coordinator through its
  documented delegation escape hatch: LlmAgent + `supervisor_worker_{i}`
  sub_agents), legacy sugar fallback for the six sugar-expressible presets
  (expert_dispatch/team_coordinator have no legacy mapping — catalog
  raises). Per-preset assertions: bounded loop counter == 5 for
  refine_until_good, research specialist runs for expert_dispatch,
  perspective_0/1 state for multi_perspective, output in state everywhere.
  `expert_dispatch` router contract settled: a built-in
  `default_route_dispatch` (compile-time `DEFAULT_FUNCTION_REGISTRY`,
  overrideable) routes deterministically from `ctx.state['routed_to']`
  (default `"research"`) — `options.function: route_dispatch` now resolves
  without a custom registry.
- [x] **E2a — Dynamic-planning preset for plan_and_execute.** ADR-005 §5
  targets a planner node spawning executors via `ctx.run_node()` on the
  workflow backend. Preset shape: planner `function` node →
  `options.function: plan_execute` (built-in; `options.executor` names the
  compiled executor node, `options.steps` the deterministic step list) →
  per step, `ctx.run_node(executor, node_input=step, run_id=f"plan_step_{i}")`
  prints outputs to `plan_outputs` state; the executor is edge-disconnected
  (dynamic-only). Engine requirements captured: dynamically scheduled nodes
  (and the planner FunctionNode) need `rerun_on_resume=True` — `build_llm_agent`
  defaults it True (matching ADK's own graph-node semantics) and the
  compiler sets it on FunctionNodes. The two-role sequence remains the
  legacy/rollback path (`_plan_execute_legacy`).
  *Done when*: the preset runs the dynamic shape with fake models on the
  workflow backend and the sequence remains the legacy/rollback path.
  **Done (2026-08-23).** The matrix test runs `plan_and_execute` dynamically
  (executor 3×, `plan_outputs` == the three responses, executor author in
  the stream); legacy compile still emits the frozen pre-E3 sequence tree
  (C4 parity green); `plan-and-execute.yaml` example runs through the
  dynamic shape.
- [x] **E3 — Delete the per-use-case classes and nine strategies.**
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
  **Done (2026-08-23).** Strategies (9 builders + base/registry) and the
  eight facade classes removed; `RoleConfig`/`RuntimeContext` moved to
  `basic_agent.runtime` (no ADK imports; consumed by compile/presets/
  policies/agent). Registry serves presets only (get/resolve/has/
  list_use_cases identical contracts; `AGENT_USE_CASE_MODULE` custom
  surface migrated: modules expose `PRESETS`/`PRESET` of `Preset` —
  legacy `BaseUseCaseAgent`-style modules are rejected with migration
  guidance; production allowlist unchanged). `Preset` gained
  `apply_defaults` (old resolve_runtime rules), `build()` (backend flag,
  root naming via legacy_name), `escape_hatch_builder`
  (team_coordinator = LlmAgent + `supervisor_worker_{i}`), and the hook
  surface (before/after run/tool with old chaining semantics — run hooks
  attach on legacy roots; workflow roots use boundary nodes/plugins per
  the B3 decision: the D2 aggregation now runs natively as a graph node,
  `aggregate_perspectives`, and multi_perspective workflow runs keep the
  state contract without an after-run hook). Built-ins: 43 lines removed
  from the old facade path; no orphan imports; docs (CONFIGURATION.md,
  ARCHITECTURE.md) updated for the preset/custom surface; CHANGELOG entry
  files the internal breaking change. C4 frozen: the legacy compiler's
  post-E3 trees are pinned against explicit pre-E3 golden structures
  (test_compile_parity.py). Notes: state-schema semantics for intermediate
  keys (`options.no_state_schema` on multi_perspective workers — the
  workflow engine validates state_delta against the schema, the legacy
  path never did); default router binds the preset's first specialist via
  `options.default_route` (the ADK graph rejects duplicate (from,to)
  edges, so no DEFAULT_ROUTE fallback).

#### Phase F — Cleanup, docs, and legacy retirement

- [x] **F1 — Rewrite user-facing docs and examples.**
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
  **Done (2026-08-23).** New examples: `examples/graph-nested.yaml`
  (outer sequence with a `graph` node whose subgraph fans out → join →
  synthesizer — uses the documented `options.no_state_schema` for
  intermediate keys) and `examples/graph-routed.yaml` (router function +
  per-specialist route edges). `tests/test_graph_examples.py` (3 tests)
  loads+validates+compiles EVERY `examples/*.yaml` through the real loader
  and runs both new graph examples end-to-end with fake models (nested:
  intake + perspectives + synthesize state keys; routed: default route
  reaches the research branch). CONFIGURATION.md carries the sugar forms,
  the policies section, the D3 concern table, the node-name/identifier and
  `no_state_schema` notes; ARCHITECTURE.md (E3) documents the preset
  shapes and custom surface; README use-case table is metadata-pinned and
  unchanged.
- [x] **F2 — Retire the legacy path.**
  *Depends on*: one release shipped with workflow backend default + legacy
  rollback (per B4). *Files*: delete `src/basic_agent/compile/legacy.py`
  and remaining legacy-only strategy remnants; drop the
  `SequentialAgent`/`ParallelAgent`/`LoopAgent` deprecation
  `filterwarnings` entries from `pyproject.toml` (they carry a pointer to
  ADR-003, which prescribes exactly this exit).
  *Done when*: suite green with no deprecation filter and zero imports of
  the deprecated classes anywhere in `src/`.
  **Done (2026-08-23).** `compile/legacy.py` deleted; the backend flag
  (`AGENT_COMPOSE_BACKEND`/`compose_backend`) removed — the workflow
  compiler is the only backend; the Workflow deprecation `filterwarnings`
  entry dropped (suite shows no such warnings with it gone) and **zero
  `src/` imports** of `SequentialAgent`/`ParallelAgent`/`LoopAgent` (the
  isolation test is now enforced correctly — its old prefix-matching was
  vacuous — and allows only `compile/` + `agent.py`; policies/presets were
  re-pointed to duck typing). Legacy-only surfaces removed: `Preset`
  `legacy_spec`/`legacy_name`/`build_legacy_spec`, the pre-E3 parity test
  (its frozen golden expired with the compiler — the gate had held),
  `legacy_multi_perspective_spec`, `_plan_execute_legacy` and the
  after-run aggregation helper (the multi_perspective aggregation runs
  natively as a graph node); related tests removed/updated.
- [x] **F3 — Close the program.**
  *Depends on*: F1, F2. *Steps*: CHANGELOG summary; mark ADR-005
  "Implemented"; move this program's tasks to the closed section with a
  one-line evidence pointer each; re-run
  `scripts/check-adk-assumptions.py` and the
  `docs/ADK-UPGRADE-CHECKLIST.md` manual steps against the final surface;
  update the Verification baseline above.
  *Done when*: this file's status summary reflects the program closed.
  **Done (2026-08-23).** ADR-005 → **Implemented**; ADR-003 records the
  F2 resolution; CHANGELOG carries the closing entry; guard scripts
  re-run green against the final surface (assumptions on google-adk 2.6.3,
  doc links, workflow pins, ruff, targeted pyright, full suite 421 passed /
  5 platform skips, 93% coverage); Verification baseline and status summary
  below updated. Phase-by-phase evidence stays in the records above
  (A1–A5, B0–B4, C1–C4, D1–D3, E1–E2a, F1); no unchecked task remains in
  this file except none — the program is closed.

### Review findings — recurring 10-minute audit

- [x] **V01 — Refresh the stale "Working agreements" preamble now that the
  program is closed.** *Problem*: §2 "Key code locations" still describes
  `src/basic_agent/use_cases/` as "(8 facade classes + registry)" and
  `src/basic_agent/strategies/` as "(9 builders + base
  `RuntimeContext`/`RoleConfig`/`llm()`)" — both are gone (verified
  2026-08-23: `use_cases/` now contains only `__init__.py` + `registry.py`,
  tracked via `git ls-files`; `strategies/` has zero tracked files, deleted
  in F2; `RuntimeContext`/`RoleConfig` moved to `src/basic_agent/runtime.py`
  per the E3 closure note). §3 documents `uv run ruff check` and
  `uv run ruff format --check` as the verification commands, but `ruff` is
  not declared anywhere in `pyproject.toml` (confirmed by grep) and
  `.venv`'s python reports "No module named ruff" — the actual working
  invocation, per `.github/workflows/ci.yml:73-74`, is
  `uvx --from ruff ruff check .` and `uvx --from ruff ruff format --check .`.
  §4's hard rules about never building on
  `SequentialAgent`/`ParallelAgent`/`LoopAgent` and never deleting legacy
  code before C4 parity are now moot — F2 already deleted the legacy path
  entirely, so there is nothing left to build on or delete. A future agent
  reading this section first (as §1 instructs) would look for files that no
  longer exist and run a command that fails.
  *Fix*: rewrite §2 to point at the current layout
  (`use_cases/registry.py` serving presets; `presets/catalog.py`;
  `compile/workflow.py` + `compile/llm_node.py`; `policies/approval.py` +
  `policies/synthesis.py`; `runtime.py` for `RuntimeContext`/`RoleConfig`);
  fix §3's ruff invocation to `uvx --from ruff ruff check .` /
  `uvx --from ruff ruff format --check .`; either remove §4's
  legacy-path rules or reframe them as historical (the workflow backend is
  now the only backend, so "never build on deprecated composition classes"
  applies unconditionally, not as a migration-era carve-out).
  *Done when*: §2's file list matches `git ls-files src/basic_agent/` for
  the modules it names; the documented ruff command succeeds when copy-pasted
  verbatim; §4 no longer references a legacy path that doesn't exist.
  **Done (2026-08-23).** Preamble rewritten: §2 lists the post-E3/F2 layout
  (presets/, use_cases/registry, compile/workflow+llm_node, config/graph+
  sugar+loader, policies/, runtime.py, agent.py, interfaces/ — all verified
  present via `git ls-files src/basic_agent/`); §3 uses the CI-verbatim
  `uvx --from ruff ruff check .` / `uvx --from ruff ruff format --check .`
  invocations (ruff isn't a declared project dependency — CI uses uvx per
  `.github/workflows/ci.yml:73-74`); §4's legacy-path rules reframed as
  unconditional hard rules (legacy retired with F2; nothing left to build
  on or delete) plus the enforced composition-import isolation; phases
  marked historical. Review log updated.

### Code review findings — deep review of the workflow re-architecture program (2026-08-23, `e0bf24f..HEAD`)

> High-effort correctness/simplification review of the entire graph-first
> re-architecture diff. The two most severe findings (R06, R07) were
> independently re-verified against source in this session (not just by the
> review agent) before logging. Ranked most-severe first.

- [ ] **R06 — `_build_root_agent` never reads `config.graph` or
  `config.policies`; the declarative graph-config/policies system parses,
  validates, and is fully tested in isolation but has zero effect on the
  served agent.** *Problem*: `src/basic_agent/agent.py:406`
  (`_build_root_agent`) only calls
  `get_default_registry().resolve(config.use_case or "assistant")` then
  `preset.build(runtime)` — it never touches `config.graph` or
  `config.policies` anywhere. Verified directly: neither identifier appears
  in the function body. A user who follows `docs/CONFIGURATION.md` or
  `examples/graph-nested.yaml`/`examples/graph-routed.yaml` and mounts a
  custom `graph:` block or sets `policies.approval.enabled: true` gets no
  error — the config loads and validates cleanly, then is silently
  discarded in favor of whatever `use_case` preset resolves.
  *Fix*: wire `_build_root_agent` to compile `config.graph` (via
  `compile/workflow.py`) when present, apply `config.policies` (via
  `policies/approval.py` / `policies/synthesis.py`) to the resulting tree,
  and fall back to the preset path only when no `graph:` is configured.
  Add a test that builds the actual served root (through `agent.py`, not
  the compiler directly) from a YAML file containing a custom `graph:` +
  `policies:` block and asserts the compiled shape/policy is present.
  *Done when*: a config-file-driven graph/policy actually changes the
  served agent's behavior, proven by a test that goes through
  `_build_root_agent`, not `compile/workflow.py` or `Preset.build()`
  directly.
- [ ] **R07 — `expert_dispatch`'s router always dispatches to the first
  specialist; nothing ever writes `ctx.state['routed_to']` before the
  router node runs.** *Problem*: `src/basic_agent/compile/workflow.py:51`,
  `default_route_dispatch` does `route = ctx.state.get("routed_to",
  default_route)`. Verified directly: no node upstream of `route_dispatch`
  in the compiled graph ever sets `routed_to` — it is a bare `function`
  node fed straight from START with no classifier. So `route` is always
  `default_route`, which `presets/catalog.py` sets to
  `specialists[0]` (`"research"` by default). Every request is silently
  routed to the same specialist regardless of content.
  `tests/test_preset_matrix.py`'s "research specialist runs for
  expert_dispatch" assertion cannot catch this because research is also the
  always-taken default path.
  *Fix*: add an LLM classifier node before `route_dispatch` that writes
  `ctx.state['routed_to']` based on the request (e.g. an `llm` node with a
  routing instruction and structured output, or a `before` hook on the
  function node), or otherwise make the route selection request-dependent.
  Add a test with two different inputs asserting two different specialists
  actually run (not just that the default one runs).
  *Done when*: `expert_dispatch` demonstrably routes different inputs to
  different specialists, not just to `specialists[0]` every time.
- [ ] **R08 — Approval policy's `_TaskAgentTool` detection fails open
  (never gates) on `ImportError`/`AttributeError` instead of failing
  closed.** *Problem*: `src/basic_agent/policies/approval.py:39`,
  `is_unconditional_tool` catches the private-ADK-symbol lookup for
  `_TaskAgentTool` and returns `True` (meaning "never gate this tool") on
  exception, rather than treating an unresolvable check as "gate it to be
  safe." An ADK upgrade that renames/removes
  `google.adk.tools.agent_tool._TaskAgentTool` makes every tool call hit
  the except branch, so `is_unconditional_tool` returns `True` universally
  and the approval veto silently stops blocking anything — with no error.
  *Fix*: fail closed — on lookup failure, treat the tool as gate-able
  (return `False`) rather than unconditional, and log a warning so the ADK
  upgrade checklist (`docs/ADK-UPGRADE-CHECKLIST.md`) surfaces it.
  *Done when*: a test that monkeypatches the `_TaskAgentTool` import to
  raise confirms the approval gate still blocks state-changing tools rather
  than passing everything through.
- [ ] **R09 — `approval_gate` preset sets `RuntimeContext.require_approval
  = True` but nothing reads that field; the preset enforces nothing beyond
  prompt text.** *Problem*: `src/basic_agent/presets/catalog.py:280` sets
  `require_approval=True` in the preset defaults, but neither
  `compile/workflow.py` nor `compile/llm_node.py` reads
  `RuntimeContext.require_approval` anywhere (grep confirms no consumer).
  The compiled `approval_gate` graph is two plain LLM nodes relying
  entirely on prompt instructions ("only after the approval tool has
  returned confirmed") with no programmatic veto boundary — a regression
  from the pre-refactor `use_cases/approval_gate.py`'s `before_tool` veto.
  A model can ignore or be prompt-injected around plain instruction text.
  *Fix*: either have the preset apply the D1 approval policy
  (`policies/approval.py`) by default when `require_approval` is true (so
  `approval_gate` gets a real gate, matching D1's stated design), or wire
  `require_approval` to something enforceable in the compiler.
  *Done when*: `approval_gate` has a programmatic veto (proven by a test
  that a gated tool call is blocked, not just discouraged by instruction
  text) rather than relying solely on prompt compliance.
- [ ] **R10 — `default_aggregate_perspectives` swallows all exceptions at
  debug level, silently dropping `aggregated_perspectives` from state
  instead of surfacing the failure.** *Problem*:
  `src/basic_agent/compile/workflow.py:79` wraps the aggregation logic in a
  bare `except Exception` logged only via `logger.debug` (unlikely enabled
  in production). A `KeyError` or similar bug during
  snapshot/write-back silently leaves `aggregated_perspectives` missing
  from state with no error anywhere in the run.
  *Fix*: narrow the exception handling to expected failure modes, log at
  `warning`/`error` level, and consider surfacing a state marker (e.g.
  `aggregation_failed: true`) so downstream consumers can detect the
  absence rather than silently getting nothing.
  *Done when*: a forced-failure test proves the failure is visible (log
  level or state marker), not silently swallowed.
- [ ] **R11 — Operator-precedence bug duplicated in two error-message
  builders: `"..." + ", ".join(x) or "(none)"` always takes the non-empty
  branch because `+` binds tighter than `or`.** *Problem*:
  `src/basic_agent/compile/llm_node.py:96` (`resolve_schema`'s "Unknown
  schema name" error) and `src/basic_agent/config/sugar.py:92`
  (`_check_name_exists`'s "unknown node" error) both write
  `f"...: " + ", ".join(sorted(x)) or "(none)"`. Since the f-string prefix
  is always non-empty, the whole expression is always truthy, so `or
  "(none)"` never fires — an empty registry/node-set produces a
  dangling `"...valid schemas: "` / `"...valid nodes: "` with nothing
  after the colon instead of the intended `"(none)"`.
  *Fix*: parenthesize correctly:
  `f"...: {', '.join(sorted(x)) or '(none)'}"` (or build the joined string
  in a local variable first) in both files.
  *Done when*: calling each error path with an empty registry/node-set
  produces a message ending in `(none)`, verified by a test for each.
- [ ] **R12 — `expert_dispatch` silently substitutes a default specialist
  roster when `specialists` is empty, instead of failing fast like the
  pre-refactor `RouterStrategy.validate()` did.** *Problem*:
  `src/basic_agent/presets/catalog.py:333`,
  `list(rt.specialists) or list(EXPERTS_DEFAULT)` treats an empty
  `specialists` list as "use the default roster" rather than a
  configuration error. The removed `RouterStrategy.validate()` raised
  `ValueError` for exactly this case ("ROUTER strategy requires at least
  one specialist in config"); this preset silently ignores a
  `specialists: []` misconfiguration and builds anyway — compounding R07,
  since the router won't even reflect the intended roster.
  *Fix*: raise a clear `ValueError` when `rt.specialists` is explicitly
  empty (distinguish "not set, use default" from "set to `[]`" if the
  config model allows that distinction; otherwise restore fail-fast
  behavior matching the removed strategy).
  *Done when*: a test asserts `specialists: []` raises rather than
  silently falling back to `EXPERTS_DEFAULT`.
- [ ] **R13 — `_chain_before_tool`/`_iter_llm_agents` in
  `presets/catalog.py` are near-verbatim duplicates of
  `_chain_before_tool`/`iter_llm_agents` already defined and exported in
  `policies/approval.py`, instead of being imported.** *Problem*:
  `src/basic_agent/presets/catalog.py:73` and `:195` re-implement tree-walk
  helpers that already exist in `src/basic_agent/policies/approval.py:75`
  and `:94`. A future fix to the traversal logic (e.g. handling a new
  node/composition type) applied to one copy leaves the other stale,
  making the preset-level tool-wiring and the D1 approval policy's own
  wiring walk the LLM-agent tree inconsistently.
  *Fix*: import `iter_llm_agents`/`_chain_before_tool` from
  `policies/approval.py` in `presets/catalog.py` (or hoist both into a
  shared module both import from) and delete the duplicate.
  *Done when*: `presets/catalog.py` has no local re-implementation; both
  call sites use the same function object.
- [ ] **R14 — `plan_and_execute`'s dynamic plan steps run sequentially via
  a for-loop instead of concurrently, despite being independent.**
  *Problem*: `src/basic_agent/compile/workflow.py:138`, `_make_plan_execute`
  `await ctx.run_node(...)` one step at a time in a `for` loop even though
  each step is dispatched to its own sub-branch with no data dependency on
  a prior step's output. An N-step plan takes roughly N× a single LLM
  call's latency instead of roughly 1×.
  *Fix*: gather the per-step `ctx.run_node(...)` awaitables (e.g. via
  `asyncio.gather`) so independent steps execute concurrently, unless a
  genuine ordering dependency is intended (in which case document why the
  sequential await is required).
  *Done when*: a test with fake models measures (or otherwise proves)
  concurrent dispatch of independent plan steps, or a comment justifies why
  sequential execution is required.
- [ ] **R15 — `_parse_sugar_item` doesn't enforce mutual exclusivity
  between `parallel` and `loop` in the same sequence entry, unlike the
  sibling `_parse_sugar_form`.** *Problem*:
  `src/basic_agent/config/loader.py:792`, a sequence item with both
  `parallel:` and `loop:` keys set (e.g. a copy-paste error) silently uses
  `parallel` and drops `loop` — no validation error — because the
  `parallel` branch returns first. `_parse_sugar_form` (the top-level
  sugar parser) does enforce `len(present) != 1` for the analogous case.
  *Fix*: apply the same `len(present) != 1` (or equivalent) check inside
  `_parse_sugar_item` before branching.
  *Done when*: a test config with both `parallel` and `loop` set on one
  sequence item raises a clear validation error instead of silently
  picking one.

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
