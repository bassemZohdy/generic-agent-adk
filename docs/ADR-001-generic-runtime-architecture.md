# ADR-001: Generic Agent Runtime Architecture (historical)

## Status

**Superseded — historical record only.** Accepted 2026 (pre-08-14), then
superseded in stages: the user-facing selection surface by
[ADR-002](./ADR-002-use-case-taxonomy.md) (use cases replaced patterns), and
the strategy/registry core by [ADR-005](./ADR-005-graph-first-taxonomy-and-configuration.md)
(graph-first configuration replaces per-pattern strategy classes). Nothing in
this document describes the current implementation; it is retained because two
principles it introduced still govern the project.

## What this ADR decided (summary)

The project originally shipped eight module-level "pattern" agents selected by
an `AGENT_PATTERN` env var. This ADR replaced that with a
**Strategy + Registry** design: an `AgentStrategy` interface with one concrete
builder per execution pattern (DIRECT, REACT, SEQUENTIAL, PARALLEL, LOOP,
ROUTER, SUPERVISOR, PLAN_EXECUTE, EVALUATOR_OPTIMIZER, HUMAN_IN_LOOP), an
`AgentStrategyRegistry` for lookup without conditionals, and a type-safe
`AgentConfig` loaded from YAML/env.

## What survived, and where it lives now

1. **One Docker image; behavior fully externalized through configuration.**
   Still the project's defining constraint. Carried forward by ADR-002 §6
   (YAML base, documented env overrides, provenance logging) and by ADR-005's
   graph-spec configuration.
2. **Capabilities (MCP, A2A, custom tools) are tool providers, not agent
   types.** Still true; `tools.*` config attaches capabilities to any agent
   shape.
3. **A registry with metadata as the single catalog source.** Reborn as the
   use-case registry (ADR-002 §2), which ADR-005 keeps as the preset catalog.

## What did not survive

- The `basic_agent/patterns/` parallel system and the `AGENT_PATTERN*`
  selection surface — deleted by ADR-002.
- Architecture-speak public naming (`EVALUATOR_OPTIMIZER`, `PLAN_EXECUTE`) —
  replaced by intent-named use cases (ADR-002 §1).
- The ten per-pattern strategy classes and the `AgentStrategyRegistry` — their
  taxonomy mirrored the ADK composition classes (`SequentialAgent`,
  `ParallelAgent`, `LoopAgent`) that upstream has since deprecated in favor of
  the graph-based `google.adk.workflow.Workflow`; ADR-005 replaces the
  builders with a single graph compiler.
- The "framework adapters" aspiration (`frameworks/langgraph/`) — never
  built; dropped from scope.
- The how-to sections ("How to Add a New Strategy", etc.) — described a
  surface that no longer exists; see ADR-005 and CONFIGURATION.md for the
  current extension points.

## References

- Superseding decisions: [ADR-002](./ADR-002-use-case-taxonomy.md),
  [ADR-005](./ADR-005-graph-first-taxonomy-and-configuration.md)
- Google ADK Documentation: https://google.github.io/adk-docs/
