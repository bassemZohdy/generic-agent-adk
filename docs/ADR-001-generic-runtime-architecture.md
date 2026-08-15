# ADR-001: Generic Agent Runtime Architecture

## Status

Accepted — **partially superseded by [ADR-002](./ADR-002-use-case-taxonomy.md)** (2026-08-14): the strategy/registry core survives, but the `basic_agent/patterns/` parallel system described here was deleted, and the public selection surface is now use cases (`AGENT_USE_CASE` / `agent.use_case`), not patterns (`AGENT_PATTERN` / `agent.type`). Read this ADR for historical context only.

## Context

The Google ADK project demonstrates multiple orchestration patterns (Generic, Sequential, Parallel, Loop, Router, Supervisor, Planner-Executor, Evaluator-Optimizer, Human-in-Loop) through separate agent implementations in `basic_agent/patterns/`.

Different deployment scenarios require different agent behaviors, but the previous architecture required choosing between:
1. Separate Docker images per pattern
2. Hardcoded conditional logic to select patterns
3. Pre-built pattern agents without a systematic way to add new ones

We needed:
- One Docker image reusable across all patterns
- Agent behavior fully determined by external configuration
- Easy addition of new strategies without modifying core runtime
- Consistent testing and validation across all patterns

## Decision

We implemented a **Strategy + Registry** pattern for agent construction:

### Architecture

```text
Generic ADK Agent Runtime
        ↓
    External Config (YAML/Env)
        ↓
 AgentStrategyRegistry
        ↓
    ┌───┬───┬───┬───┬───┐
    │   │   │   │   │   │
  DIRECT REACT SEQUENTIAL PARALLEL LOOP ...
    │   │   │   │   │   │
    └───┴───┴───┴───┴───┘
        ↓
       ADK
```

### Key Design Principles

1. **Agent Type = Execution Pattern**
   - `DIRECT`: Single LlmAgent, no tool looping
   - `REACT`: Single LlmAgent with iterative tool use
   - `SEQUENTIAL`: SequentialAgent (ordered pipeline)
   - `PARALLEL`: ParallelAgent (concurrent workers)
   - `LOOP`: LoopAgent (iteration control)
   - `ROUTER`: LlmAgent with specialist delegation
   - `SUPERVISOR`: LlmAgent coordinating workers
   - `PLAN_EXECUTE`: Sequential planner + executor
   - `EVALUATOR_OPTIMIZER`: Loop-based generation + evaluation
   - `HUMAN_IN_LOOP`: Sequential with approval gate

2. **Agent Role = Configuration, Not Code**
   - Model selection
   - Instructions/system prompt
   - Tool enablement
   - MCP configuration
   - A2A configuration
   - Execution limits (max_iterations, approval policies)
   - Knowledge sources
   - Authentication/authorization

3. **MCP and A2A as Capabilities**
   - Not special agent types
   - Tools that can be added to any agent via config
   - Integration pattern: pluggable tool providers

4. **One Docker Image**
   - No business-specific variants
   - All behavior externalized through configuration
   - Enables true DevOps flexibility (configuration as deployment)

### Component Breakdown

| Component | Purpose | Location |
|-----------|---------|----------|
| `AgentStrategy` | Abstract interface for building agents | `strategies/base.py` |
| `AgentStrategyRegistry` | Registry of strategies, no conditionals | `strategies/registry.py` |
| `DirectStrategy`, `ReactStrategy`, etc. | Concrete strategy implementations | `strategies/direct.py`, etc. |
| `AgentConfig` | Type-safe configuration model | `config_loader.py` |
| `load_config_from_yaml()` | YAML → AgentConfig | `config_loader.py` |
| `GenericAgentPlugin` | Telemetry and capability discovery | `agent.py` |
| Pattern examples | Configuration demonstrating each strategy | `examples/*.yaml` |

## How to Add a New Strategy

1. Create `basic_agent/strategies/my_strategy.py`:

```python
from .base import AgentStrategy, AgentStrategyContext
from google.adk.agents import Agent

class MyStrategy(AgentStrategy):
    @property
    def agent_type(self) -> str:
        return "MY_TYPE"
    
    def build(self, context: AgentStrategyContext) -> Agent:
        # Construct and return agent
        return ...
```

2. Add to `strategies/__init__.py` and registry automatically registers on first access.

3. Create `examples/my-agent.yaml`:

```yaml
agent:
  type: MY_TYPE
  description: ...
model:
  provider: google
  name: ${ADK_MODEL:gemini-2.0-flash}
...
```

4. Tests automatically validate the new strategy through the registry.

**No modifications to core runtime required.**

## How to Add a New Capability (MCP, A2A, Custom Tools)

Capabilities are treated as tool providers, not agent types.

1. **MCP**: Already supported via `tools.mcp` in config
2. **A2A**: Already supported; add remote agents as tools
3. **Custom Tools**: Add functions to tools list in config_loader

Example config:

```yaml
tools:
  enabled:
    - knowledge
    - mcp
    - custom_tool
  mcp:
    enabled: true
    tools:
      - search
      - calendar
```

## How to Adapt to Another Framework (e.g., LangGraph)

Current structure enables framework adapters:

```text
frameworks/
  adk/
    strategies/       (current)
    runtime/
  langgraph/          (future)
    strategies/       (LangGraph equivalents)
    runtime/
```

Core config model (`AgentConfig`, YAML loading, validation) is framework-independent.
Only strategy implementations and runtime lifecycle differ.

Each framework registers its own strategies:

```python
# frameworks/langgraph/strategies/direct.py
class LangGraphDirectStrategy(AgentStrategy):
    def build(self, context: AgentStrategyContext) -> Any:
        # Use LangGraph's Builder API, etc.
```

Benefit: **Configuration and tests transfer across frameworks; only runtime code changes.**

## Backward Compatibility

> Historical note: the `basic_agent/patterns/` modules and the compatibility
> surface described here were removed in the cleanup that followed ADR-002.
> The runtime now exposes only the use-case keys documented in ADR-002.

Existing pattern modules (`basic_agent/patterns/*`) remained functional during
 the transition.

The `AgentStrategyRegistry` coexisted with the original pattern agent
 definitions during the migration. Gradual migration path at the time:
1. Strategies demonstrated the new architecture
2. Pattern modules remained for reference/compatibility
3. New deployments used strategy-based configuration
4. No breaking changes to existing code during the transition

## Consequences

### Positive

- ✅ One Docker image for all agent patterns
- ✅ Agent behavior fully externalized and validated
- ✅ No hard-coded conditionals or switch statements
- ✅ Easy to add new strategies
- ✅ Easy to test all patterns systematically
- ✅ Framework-agnostic configuration model
- ✅ Future framework adapters require minimal new abstractions

### Negative

- ⚠️ More files/modules (strategies for each pattern)
- ⚠️ Coexistence with old pattern modules during transition
- ⚠️ Workflow class not yet available (uses deprecated SequentialAgent, etc.)

### Neutral

- Configuration YAML examples now source of truth over code
- Encourages configuration-first design (good for ops, not always good for exploration)

## Validation

All strategies tested through:
- Unit tests (`tests/test_strategies.py`)
- Configuration tests (`tests/test_config_loader.py`)
- Existing pattern tests (`tests/test_agent.py`)
- E2E tests (planned: Docker container + configuration scenarios)

Registry verification:
- All built-in strategies register automatically
- Registry rejects duplicate registrations
- All strategies are retrievable and buildable

## Related Decisions

- **ADR-002** (if created): Details on MCP integration
- **ADR-003** (if created): Details on A2A and delegation patterns

## References

- Google ADK Documentation: https://google.github.io/adk-docs/
- Pattern examples: `basic_agent/patterns/`
- Strategy implementations: `basic_agent/strategies/`
- Configuration examples: `examples/*.yaml`
