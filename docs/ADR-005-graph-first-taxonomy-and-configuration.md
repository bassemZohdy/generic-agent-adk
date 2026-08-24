# ADR-005: Graph-first taxonomy and externalized configuration

**Status:** Implemented — the full program (Phases A–F2) shipped 2026-08-23.
Gates B1–B3 verified in `tests/test_workflow_gates.py`; presets, policies,
and the workflow compiler are the production path; the legacy sugar compiler
has been **retired** (F2) and the program closed (F3). Evidence and history
in [ADR-003](./ADR-003-adk-workflow-migration.md#phase-b-spike-results-2026-08-23--gates-verified-evidence-in-tests)
and the TODO phases.
**Supersedes** the taxonomy and strategy layers of
[ADR-002](./ADR-002-use-case-taxonomy.md) (its catalog, config-resolution,
custom-module, and hook concepts survive) and absorbs the migration plan of
[ADR-003](./ADR-003-adk-workflow-migration.md).  
**Date:** 2026-08-23

## Context

Two independent pressures converged on the same conclusion.

**1. The eight-use-case taxonomy conflates three orthogonal axes.** A
2026-08-23 review (recorded in ADR-002's correction addendum) decomposed
every built-in use case into topology, role prompts, and cross-cutting
policy:

| Use case | Topology | Role prompts | Cross-cutting policy |
|---|---|---|---|
| assistant | single llm | — | — |
| pipeline | sequential(N) | generic step N | — |
| plan_and_execute | sequential(2) | planner, executor | — |
| multi_perspective | parallel(N) → llm | synthesizer | state aggregation |
| refine_until_good | loop(1) | generate-critique-improve | — |
| expert_dispatch | delegation | named specialists, route-one | — |
| team_coordinator | delegation | worker N, decompose | — |
| approval_gate | sequential(2) | proposer, completer | require_approval + tool veto |

Only the topology column is structural, and it collapses to a handful of
shapes; everything else is data. Symptoms in the shipped code: two use cases
that are the same tree with different prompts (`expert_dispatch` /
`team_coordinator`), a "dynamic" use case that is a fixed two-step sequence
(`plan_and_execute`), a policy locked inside one use case (`approval_gate`),
a registered strategy reachable from nowhere (`LoopStrategy`), and a config
language that cannot express nesting, forcing `multi_perspective` to
hand-override `compose()`.

**2. Upstream deprecated the primitives the taxonomy is built on.** The
pinned google-adk 2.6.3 marks `SequentialAgent`, `ParallelAgent`, and
`LoopAgent` deprecated in favor of the graph-based
`google.adk.workflow.Workflow`. Per ADR-003's 2026-08-23 re-evaluation
(verified in installed source): `Workflow` is a nestable `BaseNode`; edges
support chains, fan-out, `JoinNode` fan-in, and conditional routing
(`RoutingMap`); the Runner accepts a `BaseNode` root; HITL interrupts,
resume/replay, dynamic node spawning (`ctx.run_node()`), and per-node
`retry_config`/`timeout`/schemas are engine features. Sequence, parallelism,
and loops are no longer classes — they are *edge patterns in one graph
model*. A redesign that hard-codes "sequential/parallel/loop" node kinds
would rebuild the deprecated taxonomy on top of the new engine.

**Also verified:** upstream's own declarative surface (`AgentConfig`,
`BaseAgent.from_config`) is `@deprecated` and experimental — there is no
stable upstream YAML format to adopt. Externalized configuration remains this
project's own schema. The one upstream gap: a `Workflow` cannot be an
`LlmAgent` sub-agent ([discussion #5581](https://github.com/google/adk-python/discussions/5581));
LLM-driven delegation therefore stays outside the graph model for now.

## Decision

**External configuration compiles to a Workflow graph, with intent-named
presets above it, cross-cutting policies beside it, and one delegation escape
hatch.**

1. **Graph spec is the generic core.** The externalized config gains a
   recursive graph section: `nodes` (kinds: `llm`, `function`, `graph`
   sub-workflow, `join`) each carrying an optional role
   (instruction/model/tools) and per-node `retry`/`timeout`/
   `input_schema`/`output_schema`/`state_schema`; `edges` with optional
   `route` values and fan-out lists. Field names stay aligned with the
   Workflow/BaseNode pydantic models so the compile step is thin. The
   externalization contract is unchanged from ADR-002 §6: YAML base,
   documented env overrides, `${VAR:default}` substitution, fail-fast
   validation naming valid keys, one provenance log line.

2. **Sugar forms keep simple configs simple.** `sequence:`, `parallel:`
   (with implicit join), and `loop:` (bounded via routing) are shorthand that
   expands to the graph spec *before* compilation, testable in isolation.
   Simple deployments never write edges by hand.

3. **One compiler owns ADK composition.** A workflow-backend compiler builds
   the full spec; it is the single place in the codebase that touches ADK
   composition classes. The ten strategy classes and the strategy registry
   are retired. During migration only, a legacy compiler covers the sugar
   subset (which is sufficient for all eight presets) as a rollback target —
   **no new capability is built on the deprecated classes** (workflow-first;
   legacy is rollback-only, removed after one release).

4. **Policies are declarative and topology-independent.**
   `policies.approval` (engine interrupts / `request_input` on the workflow
   backend; the extracted tool-veto + `request_confirmation` flow on legacy)
   and `policies.synthesis` (join/synthesizer node) apply to any preset or
   raw graph. Retries, timeouts, schemas, output keys, and code execution
   (ADR-004, audited compatible) each get exactly one documented home in the
   node/graph config.

5. **The eight public keys become presets — data, not classes.** A preset is
   a named partial config: graph-spec template + default roles + default
   policies, carrying the ADR-002 catalog metadata (key, title, when_to_use,
   aliases, interfaces). Registry behavior, alias resolution,
   `list_use_cases()`, and `AGENT_USE_CASE_MODULE` custom loading keep their
   public contracts; custom modules can also contribute presets as data.
   Re-classification: `assistant` → single llm node; `pipeline` → sequence
   sugar; `multi_perspective` → parallel + synthesis policy;
   `refine_until_good` → loop sugar with critic role; `plan_and_execute` →
   dynamic-planning preset (planner node spawning executors via
   `ctx.run_node()`), with a two-role sequence fallback on legacy;
   `expert_dispatch` → routing-node graph (route emission + `RoutingMap`);
   `approval_gate` → propose/complete sequence + approval policy;
   `team_coordinator` → delegation escape hatch.

6. **Delegation escape hatch.** LLM-driven open-ended delegation
   (`LlmAgent` + `sub_agents`, and/or ADK task delegation via
   `_TaskAgentTool`) remains a supported non-graph shape until #5581 /
   Node-as-Tool settles upstream. Re-evaluated on every ADK upgrade via the
   existing upgrade checklist.

7. **Hooks get a graph-native attachment point.** Chosen at acceptance
   (B3, pros/cons below): **boundary `FunctionNode`s are the policy
   attachment point for per-run, tree-wide wiring** (`policies.approval`,
   `policies.synthesis` compile to boundary/named nodes in the spec);
   **ADK plugins are the observability layer** (root-level
   `before_run_callback`/`after_run_callback` and per-node
   `*_agent_callback` hooks — verified to fire for workflow roots). A rule
   proven by the spike: `before_tool_callback` on a task-mode `LlmAgent`
   node receives the synthetic `finish_task` call, and **vetoing it
   deadlocks completion** — every policy callback must pass `finish_task`
   and `_TaskAgentTool` delegations through un-gated.
   *Pros* — boundary nodes: declarative in the config spec, ordered
   deterministically by graph edges, no plugin-manager ordering concerns,
   tested as ordinary nodes, and policies reduce to named node templates.
   *Cons* — they appear in the event stream as extra nodes (audited), and a
   node that should not exist on the legacy backend needs a compiler guard.
   *Pros* — plugin: single attachment for transport-level concerns
   (rate limits, metrics), fires once per run and per node without graph
   changes. *Cons* — plugin methods are global (no per-node instance
   config), ordering across plugins is manager-defined, and plugins are a
   separate execution path from the graph (harder to snapshot-test as
   config data).

## Open questions (resolved 2026-08-23 by the Phase B spike)

- **B1 — Workflow root served through our api_server/live interfaces: PASS.**
  Chain, fan-out+join, and routed-loop graphs run to completion via
  `Runner(node=...)`; `cli/api_server.py` handles non-agent (`BaseNode`)
  roots. Transport middleware is orthogonal to graph execution; pointing
  the served root at a compiled workflow happens in Phase C3/E2.
- **B2 — resume/replay + HITL interrupts: PASS.** `RequestInput` interrupt
  events (`adk_request_input`, `long_running_tool_ids`), resume with the
  same `invocation_id` + `FunctionResponse`, and the `rerun_on_resume`
  true/false contracts all match the legacy pins.
- **B3 — hook/policy attachment: PASS.** Boundary `FunctionNode`s and ADK
  plugins both work; choice recorded in Decision §7; the `finish_task`
  passthrough rule is proven and pinned by a test.
- **Should `expert_dispatch` move to routing-node form immediately?**
  **Yes — resolved.** The routed-loop gate proves route emission/`RoutingMap`
  matching on 2.6.3, so `expert_dispatch` compiles to a routing-node graph
  (Phase E2 default), staying synchronized with `team_coordinator`'s
  delegation escape hatch on upgrades.

## Consequences

- The public surface (eight keys, catalog, YAML/env contract) is preserved;
  every class behind it is replaced. Breaking-change surface is limited to
  users who imported strategy/use-case classes directly (undocumented).
- Nesting, conditional routing, per-step retries/timeouts, and true dynamic
  planning become YAML-expressible — none were possible before.
- Two compile targets exist during migration only; the deprecation
  `filterwarnings` in `pyproject.toml` (per ADR-003) are removed with the
  legacy path.
- The ADK contract-guard script and upgrade checklist must extend to the
  workflow package's surface (`Workflow`, `Edge`, `JoinNode`, `NodeRunner`,
  task-mode wrapper), which is younger and likelier to shift than the legacy
  classes — the price of building on the current engine.

## Verification

Tracked as the phased "Workflow re-architecture program" in TODO.md:
Phase B (gate spike) gates acceptance of this ADR; Phase C golden parity
tests (preset-expanded specs structurally equal to current strategy trees)
gate any legacy deletion; the preset matrix plus interface/auth suites gate
Phase E–F cleanup.

## Addendum (2026-08-23, G01): custom graph-function extension point

The original ADR noted that `compile_graph` accepts a `function_registry`
parameter but neither call site (`agent._build_root_graph`, `Preset.build`)
ever passes one, making `options.function` nodes resolvable only against the
fixed built-in set (`route_dispatch`, `aggregate_perspectives`, …).  This
was the one concrete gap where "generic, flexible configuration" stopped
short: graph *topology* was fully generic, but custom step *logic* beyond
LLM nodes was not configurable without forking the compiler.

**Decision**: option (a) — implement a documented, allowlisted extension
point mirroring `AGENT_USE_CASE_MODULE`'s pattern.  `AGENT_FUNCTION_MODULE`
(allowlisted in production via `AGENT_FUNCTION_MODULE_ALLOWLIST`) loads a
Python module exposing a `FUNCTIONS` dict of callables into the compiler's
function registry.  Built-in names (`route_dispatch`,
`aggregate_perspectives`) can never be shadowed: the registry is seeded with
the built-ins before the custom module is loaded.  Both call sites now pass
the merged registry, so custom presets (loaded via `AGENT_USE_CASE_MODULE`)
can also reference custom function-node implementations.

**Rationale**: closing the extension point (option (b) — record
closed-by-design, delete the dead parameter) would have been simpler but
contradicts ADR-005's stated goal of generic, topology-agnostic
configuration.  The allowlist pattern is already proven for custom use cases
and the security posture (production requires an explicit allowlist of
permitted module roots) is identical.
