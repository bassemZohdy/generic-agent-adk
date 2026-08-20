# ADR-003 — ADK Workflow migration spike

**Status:** Spike complete; migration deferred pending upstream parity  
**Date:** 2026-08-15  
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
