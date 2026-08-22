# ADR-003 — ADK Workflow migration spike

**Status:** Re-evaluated 2026-08-23 — migration **unblocked in principle**;
"deferred pending upstream parity" no longer describes the pinned ADK. The
gates below are restated as local verification tasks (TODO Phase B) and the
migration itself is folded into
[ADR-005](./ADR-005-graph-first-taxonomy-and-configuration.md).  
**Date:** 2026-08-15 (original spike) · 2026-08-23 (re-evaluation)  
**Scope:** `src/basic_agent/strategies/`

## Context

Google ADK 2.6.3 marks `SequentialAgent`, `ParallelAgent`, and `LoopAgent` as
deprecated in favor of the graph-based `google.adk.workflow.Workflow`. The
current strategies deliberately retain the legacy nodes because they are still
the stable way to compose an `LlmAgent` tree: the installed ADK release warns
that a `Workflow` cannot yet be used as an `LlmAgent` sub-agent.

## Findings

| Existing strategy | Workflow shape to prototype | Blocking compatibility concern |
|---|---|---|
| sequential | `START → step_0 → step_1 → …` | preserve session event ordering and output keys |
| parallel | `START → fan-out → JoinNode` | preserve branch state isolation and aggregation hooks |
| loop / evaluator optimizer | bounded trigger back to worker | preserve `max_iterations` and resume behavior |
| human-in-loop | sequential graph with approval node | preserve ADK confirmation/resume semantics |

The strategy/use-case boundary is already the migration seam: a strategy owns
the ADK node type, while the use-case facade owns metadata and hooks. No public
configuration or registry change is required for the eventual swap.

## Migration gate

Keep the legacy implementations until all of the following are true in the
minimum locked ADK version:

1. A `Workflow` can be the root of the API server and can contain the same
   `LlmAgent` workers used by this project.
2. Workflow resume/replay preserves the current session event and state-key
   contracts.
3. Before/after agent and tool callbacks, approval confirmation, and branch
   aggregation have equivalent hooks.
4. A compatibility test matrix passes for all eight built-in use cases and the
   example YAML files without deprecation warnings. This cannot be true until
   gates 1–3 are; the deprecation warnings from `SequentialAgent`,
   `ParallelAgent`, and `LoopAgent` are expected in the meantime and are
   silenced in `pyproject.toml`'s `filterwarnings` (with a pointer back to
   this ADR) rather than worked around in the strategies themselves.

## Follow-up

Prototype the four shapes behind a strategy-local feature flag when ADK meets
the gate. Keep the legacy path as the rollback implementation for one release,
then remove it after the matrix and a production smoke test are green.

For every `google-adk` upgrade, run the automated guard and then complete the
manual compatibility steps in
[ADK-UPGRADE-CHECKLIST.md](ADK-UPGRADE-CHECKLIST.md) before widening the
dependency bound.

As of 2026-08-20, the upstream discussion on allowing `Workflow` as an
`LlmAgent` sub-agent still describes that inverse composition as unsupported
and is pursuing a Node-as-Tool path instead:
[google/adk-python discussion #5581](https://github.com/google/adk-python/discussions/5581).

## Re-evaluation (2026-08-23) — findings against the pinned google-adk 2.6.3

Direct inspection of the installed `google/adk/workflow/` package shows the
original findings understated what already ships. Verified in source:

1. **`Workflow` is a `BaseNode`** (`_workflow.py`), so graphs nest inside
   graphs natively. The graph model (`_graph.py`) supports chains, fan-out
   tuples, `JoinNode` fan-in, and **conditional routing** (`Edge.route` +
   `RoutingMap` keyed by emitted route values) — a capability the legacy
   composition classes never had.
2. **The Runner accepts a `BaseNode` root**: `runners.py` types the root as
   `agent: Optional[BaseAgent | 'BaseNode']` and runs non-agent nodes through
   `NodeRunner`. Gate 1 ("Workflow can be the root of the API server") is
   therefore likely met and needs local verification, not upstream waiting.
3. **`LlmAgent`s run as nodes via a task-mode wrapper**
   (`_llm_agent_wrapper.py`): completion is signaled with a `finish_task`
   tool, and task delegation exists via `_TaskAgentTool` with
   unresolved-task recovery from session events. ⚠️ This wrapper changes an
   `LlmAgent`'s termination contract (a synthetic tool appears in its tool
   stream) — the interaction with our per-agent tool callbacks and approval
   veto must be verified.
4. **Engine-level HITL and resume**: interrupt ids, `request_input` events,
   auth-request events (`utils/_workflow_hitl_utils.py`), and replay with a
   chronological sequence barrier (`utils/_replay_*`). Gates 2's contracts
   have first-class engine counterparts.
5. **Dynamic node scheduling**: `DynamicNodeScheduler` and `ctx.run_node()`
   let a running node spawn nodes at runtime with dedup/resume/replay
   handling — true dynamic plan-and-execute is an engine feature, not
   something to hand-build.
6. **Cross-cutting per-node config**: `retry_config`, `timeout`,
   `input_schema`/`output_schema`/`state_schema` on every `BaseNode`.
7. **New gap not in the original findings**: `BaseNode` has **no
   before/after-callback fields**. Per-`LlmAgent` tool callbacks survive
   inside wrapped nodes, but root-level `before_run`/`after_run` and
   tree-wide policy wiring (ADR-002 §4) need a new attachment point on the
   workflow backend — boundary `FunctionNode`s or an ADK plugin.
8. **Upstream declarative config is a dead end**: `agents/agent_config.py`
   (`AgentConfig`, `BaseAgent.from_config`, `config_agent_utils.from_config`)
   is marked `@deprecated` and experimental ("config is now loaded via
   reflection"). There is no stable upstream YAML format to adopt; our
   externalized configuration remains our own schema (ADR-005), kept
   field-aligned with the Workflow/BaseNode pydantic models.

**Restated gates** (now local verification tasks, tracked as TODO Phase B):
B1 — serve a real Workflow root (chain, fan-out+join, routed loop) through our
api_server path; B2 — verify resume/replay + HITL interrupts against our
session-event, state-key, and approval contracts; B3 — prototype and choose
the hook/policy attachment point (boundary nodes vs plugin), including the
task-mode wrapper's interaction with tool callbacks. The only remaining
upstream blocker is Workflow-as-an-`LlmAgent`-sub-agent (#5581), which
affects LLM-driven delegation embedding only; ADR-005 scopes that to a
delegation escape hatch rather than a program blocker.
