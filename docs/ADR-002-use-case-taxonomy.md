# ADR-002: Use-Case Taxonomy and Runtime Consolidation

**Status**: Accepted · **Date**: 2026-08-14 · **Supersedes**: the selection model described in ADR-001 (its registry/strategy core survives; the user-facing taxonomy and the `patterns/` parallel system do not)

## Context

ADR-001 delivered a generic runtime with a strategy registry, but two selection surfaces grew in parallel:

- `patterns/` — eight module-level agents selected by the `AGENT_PATTERN` env var at import time
- `strategies/` — ten strategy builders keyed by `agent.type` in YAML… which was **never wired to the runtime**. The Docker image runs `adk api_server`, which imports `agent.py:root_agent` built from env settings only. Mounting `/app/config/agent.yaml` — as every example and the README instructed — silently did nothing.

Both taxonomies spoke architecture (EVALUATOR_OPTIMIZER, PLANNER_EXECUTOR) instead of user intent, and they diverged: `SUPERVISOR` existed only in strategies, `GENERIC` only in the pattern enum, `DIRECT` duplicated `GENERIC`.

## Decision

1. **Reclassify the public surface to eight generic use cases.** Users pick `assistant`, `pipeline`, `multi_perspective`, `refine_until_good`, `expert_dispatch`, `team_coordinator`, `plan_and_execute`, or `approval_gate`. Use-case keys are the only accepted names; old pattern aliases are not supported.

2. **Two layers, one dependency direction — `use_cases` → `strategies`, never reverse.**
   - `strategies/` (internal): *how the ADK tree is shaped.* Ten builders share a base-class `llm()` builder and per-role `RoleConfig` (instruction/model/tools overrides).
   - `use_cases/` (public): *what the user picks and how it behaves at runtime.* One `BaseUseCaseAgent` subclass per use case carrying metadata (key, title, when-to-use, defaults, aliases) — the single source for the registry catalog, YAML validation errors, and docs.

3. **`BaseUseCaseAgent` is a facade, not an `Agent` subclass.** Use cases do not share an agent shape: single `LlmAgent`, `SequentialAgent` pipelines, `LoopAgent` refinement — no common runtime class can single-inherit across that fork. The facade *owns* a composed tree (delegating to its strategy) and attaches runtime hooks.

4. **Runtime hooks map 1:1 to ADK callbacks** (`before_run`/`after_run` → root agent callbacks; `before_tool`/`after_tool` → every `LlmAgent` in the tree; before-tool may veto by returning a dict). Only overridden hooks are wired — declarative use cases pay zero callback overhead. Two built-ins exercise hooks for real (`approval_gate` tool veto, `multi_perspective` output aggregation); a hook-less layer would have been deleted as ceremony.

5. **`patterns/` is deleted.** Its eight import-time agents duplicated the strategy builders with drift (e.g. shared prompts for all specialists). The deprecated `AgentPattern` enum and `AGENT_PATTERN*` environment variables were removed; the only selection path is `AGENT_USE_CASE` / `agent.use_case`.

6. **Configuration resolution — YAML base, env override, one provenance line:**
   1. YAML at `AGENT_CONFIG_FILE` or auto-detected `/app/config/agent.yaml` (explicitly configured but missing file fails fast); `${VAR:default}` substitution runs inside it.
   2. `apply_env_overrides()` applies only the six documented vars (`AGENT_USE_CASE`, `ADK_MODEL`, `AGENT_INSTRUCTION`, `AGENT_TOOLS`, `AGENT_MAX_ITERATIONS`, `AGENT_SPECIALISTS`; `GOOGLE_API_KEY` via substitution), only when explicitly set. Env-overriding specialists must match YAML `roles:` keys exactly, or load fails.
   3. No file → env-only builder produces the same `AgentConfig`.
   4. One log line records source + overrides: `config: yaml=…, use_case=…, env overrides: …`.
   Per-role *instructions* stay YAML-only — flat env vars cannot express structure.

7. **Custom use cases register from a module**: `AGENT_USE_CASE_MODULE=/path.py` — `BaseUseCaseAgent` subclasses found in it join the default registry. Extending the runtime requires no fork.

## Addendum (2026-08-15, cleanup)

The backward-compat layer described in the original decision — `AgentPattern`,
`AGENT_PATTERN*` environment variables, `agent.type`/`agent.pattern` YAML keys,
and old pattern-name aliases — has been removed. The public surface now accepts
only the canonical use-case keys listed above.

## Addendum (2026-08-14, post-acceptance)

Three refinements shipped after acceptance:

1. **Use-case consolidation: 9 → 8.** `research_assistant` merged into `assistant` (its alias was later removed along with the rest of the backward-compat surface). Rationale: after the shared `llm()` builder landed, the DIRECT and REACT strategies produce *identical* agents — one-shot with no tools, tool-iterating with tools — so two use cases were one behavior wearing two names. Reviewed and deliberately kept separate: `expert_dispatch` vs `team_coordinator` (classify→one specialist vs delegate→many workers — different intent and config), `pipeline` vs `plan_and_execute` (fixed known steps vs dynamic planning).
2. **Multi-provider models.** `model.name` with a provider prefix (or a non-Google `model.provider`) routes through ADK's LiteLLM integration (OpenAI-compatible, Anthropic, Ollama, vLLM, Groq, DeepSeek, Mistral, …); Gemini stays native. Resolution lives in `basic_agent/models.py` behind `resolve_model()`; keys/base URLs pass through from YAML/env. (ADR-003 candidate: provider-specific tool support nuances.)
3. **Interface fit metadata.** Each use case declares `interfaces` (`rest`, `web`, `cli`, + `live` for chat-like `assistant`), exposed via `list_use_cases()` — the catalog is the single source of truth for interface tooling. ADK's built-in surfaces (api_server / web / run / live service) host all use cases; no bespoke UIs were built.

## Addendum (2026-08-16, strategy cleanup)

Follow-up cleanup after a codebase review:

1. **Removed dead `ReactStrategy`.** Its `build()` was byte-identical to
   `DirectStrategy`'s and unreachable from any use case — a leftover from
   before DIRECT/REACT were merged into `assistant` (see the addendum
   above).
2. **Extracted shared worker/iteration-count validation**
   (`build_worker_pool()`, `require_min_iterations()`) into `AgentStrategy`
   (`strategies/base.py`), removing duplicated `validate()` overrides
   across `parallel.py`, `sequential.py`, `supervisor.py`, `loop.py`, and
   `evaluator_optimizer.py`.
3. **Fixed undifferentiated workers/steps.** `SupervisorStrategy`
   (`team_coordinator`) and `SequentialStrategy` (`pipeline`) built
   anonymous sub-agents that all received the identical top-level
   instruction — no positional awareness, unlike `RouterStrategy`'s named
   specialists. Both now generate a distinct default instruction per
   worker/step ("worker N of count" / "step N of count"), overridable via
   `rt.roles["worker_{i}"]` / `rt.roles["step_{i}"]` — the same override
   mechanism `RouterStrategy` already used. `examples/team-coordinator.yaml`
   and `examples/pipeline.yaml` now demonstrate this via `roles:`.
4. **Renamed for naming consistency**: `ParallelAgentStrategy` →
   `ParallelStrategy`, `LoopAgentStrategy` → `LoopStrategy`,
   `SequentialAgentStrategy` → `SequentialStrategy` (formerly the only
   three strategy classes carrying a redundant "Agent" in the name; every
   other strategy — `DirectStrategy`, `RouterStrategy`, `SupervisorStrategy`,
   `PlannerExecutorStrategy`, `EvaluatorOptimizerStrategy`,
   `HumanInLoopStrategy` — already omitted it).

## Consequences

- One Docker image, one selection path; mounted YAML finally works.
- Two behavior changes, release-noted: mounted YAML now takes effect (previously ignored — deployments that mounted files *and* set env vars will switch from env behavior to file behavior); the seven env vars override mounted YAML by design.
- Two abstractions exist and must stay coherent — enforced by the one-way import rule and by keeping all public naming/metadata on use-case classes only.

## Verification

At acceptance, `uv run pytest` reported 169 tests, with the Docker smoke
matrix covering the no-config default, mounted YAML, env-only configuration,
environment-over-YAML merging, hooks, and custom modules. Those counts are a
historical snapshot; the current tree is verified by the CI workflow.

Current snapshot (2026-08-20): `uv run pytest tests/` reports 379 passing tests
and 95.57% coverage; the latest published main pipeline passed all jobs. See
the [CI/CD workflow history](https://github.com/bassemZohdy/generic-agent-adk/actions/workflows/ci.yml).
