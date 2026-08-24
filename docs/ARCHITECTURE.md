# Architecture

This document is for **contributors and operators who need to know how the
runtime works inside** — module responsibilities, the config pipeline,
agent-tree composition, code-execution resolution, the request path, and the
deployment topology. If you just want to *use* the agent, start with the
[README](../README.md).

Design decisions are recorded as dated, immutable ADRs:

- [ADR-001 — Generic runtime architecture](./ADR-001-generic-runtime-architecture.md)
- [ADR-002 — Use-case taxonomy & consolidation](./ADR-002-use-case-taxonomy.md)
- [ADR-003 — ADK Workflow migration spike](./ADR-003-adk-workflow-migration.md)
- [ADR-004 — Pluggable code-execution sandbox selection](./ADR-004-pluggable-code-execution.md)

## The one-minute version

Configuration (YAML + env vars) in, a Google ADK `Workflow` graph out, served
behind three interfaces (REST, Live WebSocket, MCP) with Keycloak
authentication and OpenTelemetry telemetry. Since the graph-first
re-architecture ([ADR-005](./ADR-005-graph-first-taxonomy-and-configuration.md)),
the eight use cases are **data, not classes**: a preset is catalog metadata
plus a graph-spec template, and one compiler (`compile/`) is the only place
that touches ADK composition classes. An explicit `graph:` config block
bypasses presets entirely and becomes the root directly — that is the
generic, topology-agnostic surface; presets are convenience defaults built
on top of it, not a separate architectural layer.

```
YAML / env vars
      │
      ▼
graph: present? ──yes──► GraphSpec (explicit nodes/edges, or the
      │                   sequence:/parallel:/loop: sugar expanded to it)
      │ no
      ▼
use_cases registry (public) — resolves agent.use_case (+ aliases) to a
  presets/catalog.py entry:    Preset: graph-spec template + default
  data, not classes              roles/policies (custom modules add more)
      │
      ▼
policies (approval / synthesis) — apply to either root, topology-independent
      │
      ▼
compile/ — the only ADK composition home (compile_graph, build_llm_agent)
      │
      ▼
Google ADK Workflow (BaseNode tree)
```

## Module map (`src/basic_agent/`)

| Module / Package | Responsibility |
|---|---|
| `agent.py` | Entrypoint (~250 lines). Resolves config, builds the `RuntimeContext` (tool construction, model, code executor, instruction assembly), asks the use-case registry for the agent tree, exposes `root_agent`, the observability plugin, and `inspect_runtime`. Tool construction and knowledge retrieval live in focused companion modules. |
| `config/` | Configuration package. `settings.py`: `Settings` frozen dataclass snapshotted from the environment once at import. `loader.py`: YAML ↔ env merge, `AgentConfig` dataclass tree, provenance logging. `graph.py`: the framework-independent `GraphSpec` (recursive nodes/edges) that presets and a raw `graph:` config both compile to. `sugar.py`: `sequence:`/`parallel:`/`loop:` shorthand, expanded to a `GraphSpec` before compilation. `defaults.py`: single-source defaults shared by runtime config and tests. |
| `auth/` | Authentication package. `core.py`: JWT validation primitives shared by all adapters. `gateway.py`: Traefik forward-auth endpoint (internal listener `AUTH_GATEWAY_CONTAINER_PORT`). |
| `interfaces/` | Interface adapters. `rest.py`: REST/A2A (container listener `ADK_API_CONTAINER_PORT`; host default `ADK_API_PORT`). `live.py`: Live WebSocket (container listener `LIVE_API_CONTAINER_PORT`; host default `LIVE_API_PORT`). `service.py`: demo OpenAPI backend. `mcp.py`: Model Context Protocol. |
| `execution/` | Code-execution sandbox resolution (ADR-004). `resolver.py`: provider specs, `resolve_code_executor()`, `CE_FIELD_ENV_MAP`, hardened Docker executor factory. |
| `tools.py` | Tool building factories (`build_tool`, MCP/OpenAPI/Skill/ApplicationIntegration toolsets) and the before/after-tool audit callbacks. |
| `knowledge.py` | Knowledge file caching and `retrieve_knowledge` tool function. |
| `util.py` | Import-cycle-free shared utilities: `is_production()`, `split_csv()`, `resolve_allowlisted_file()` (shared allowlist/production gate for custom-module loaders). Zero imports from the rest of the package. |
| `models.py` | `resolve_model()`: bare string → native Gemini; `provider: litellm` with a `provider/model` name (or a provider-prefixed name) → ADK's `LiteLlm` instance. |
| `autoconfig.py` | Ambient capability discovery (`discover_capabilities()`). Source of `ProviderConfigurationError`. |
| `runtime.py` | Framework-neutral `RoleConfig`/`RuntimeContext` data contracts shared by the compile and preset layers (formerly `strategies/base.py`; imports no ADK composition classes). |
| `presets/` | `catalog.py`: the eight built-in presets — catalog metadata (key, title, when-to-use, aliases, interfaces), runtime-defaults merge, and the graph-spec builders the compiler consumes. Presets are data, not classes. |
| `policies/` | Cross-cutting, topology-independent behavior applied to any preset or raw graph: `approval.py` (tool-veto + confirmation-interrupt gate; never gates `request_approval`/`finish_task`/delegation tools) and `synthesis.py` (appends a synthesizer node plus native aggregation after a fan-out). |
| `compile/` | The single sanctioned home for ADK composition-class construction. `workflow.py`: turns a `GraphSpec` into an ADK `google.adk.workflow.Workflow`. `llm_node.py`: the shared `LlmAgent` builder (instruction merge, role overrides, code executor, schemas, callbacks). `functions.py`: custom graph-function loading (`AGENT_FUNCTION_MODULE`, allowlisted in production via `AGENT_FUNCTION_MODULE_ALLOWLIST`). |
| `use_cases/` | Public registry only (`registry.py`): resolves `agent.use_case` (+ aliases) to a `presets/` entry and loads custom presets via `AGENT_USE_CASE_MODULE`. The per-use-case facade classes and the strategy layer were deleted in E3 (ADR-005); nothing else lives here. |
| `telemetry.py` | OpenTelemetry tracer, invocation span attributes. |

## Configuration pipeline

```
/app/config/agent.yaml (auto-detected) or $AGENT_CONFIG_FILE
        │  ${VAR:default} substitution, structural validation
        ▼
   AgentConfig (dataclass tree)
        │  apply_env_overrides: the 7 documented env vars,
        │  explicit-set ones only — env always wins
        ▼
   resolved config ──► one provenance log line at startup:
        "config: yaml=/app/config/agent.yaml, use_case=expert_dispatch,
         env overrides: ADK_MODEL"
```

No YAML present → env-only configuration (`load_config_from_env`), which
produces the same `AgentConfig` shape so downstream code never branches on
config source.

`Settings` (`config/settings.py`) is deliberately a separate, import-time snapshot:
it answers "how is this *process* configured" (ports, limits, feature
flags), while `AgentConfig` answers "what agent is this" (use case, model,
tools, roles). Things that must react to a fresh environment — like the
code-execution resolver — take an explicit environment mapping rather than
reading `Settings`, because YAML values arrive via overlay, not env.

## Runtime wiring (per build)

`_build_root_agent` → `_build_runtime_context`:

1. Tool list from config; silent tools (`code_execution`) filtered from
   ADK tool construction — they configure the executor, not a tool object.
2. `resolve_model()` — native Gemini string or `LiteLlm`.
3. If `code_execution` is enabled: `resolve_code_executor()` over
   `os.environ` + the `execution.code_execution.*` YAML overlay
   (env wins). The resolution is surfaced four ways: the
   `RuntimeContext.code_executor`/`code_execution_strategy` fields, one
   generated instruction line, an `inspect_runtime()` capabilities entry,
   and the `adk.capabilities` span attribute.
4. Instruction assembly: fixed untrusted-content prefix, the code-execution
   line, then the operator's instruction.
5. Root assembly is **graph-first**: a configured `graph:` section compiles
   directly via `compile_graph` (`agent.use_case` is ignored); otherwise the
   use-case registry resolves the use-case key (aliases included) and its
   `Preset.build(runtime)` composes the root. `policies.approval` applies to
   either root, and `policies.synthesis` transforms a configured graph spec
   before compilation.

## Use cases → presets → graph

| Use case | Preset shape (ADR-005) | Default backend output |
|---|---|---|
| `assistant` | single llm node | one `LlmAgent` node in a `Workflow` graph |
| `pipeline` | `sequence` sugar | chain of `LlmAgent` nodes |
| `multi_perspective` | `parallel` + synthesis policy | fan-out → `JoinNode` → synthesizer → aggregator |
| `refine_until_good` | `loop` sugar | bounded routed loop |
| `expert_dispatch` | routing-node graph | router function + specialist nodes |
| `team_coordinator` | delegation escape hatch | `LlmAgent` + worker sub-agents (until #5581 / Node-as-Tool) |
| `plan_and_execute` | dynamic planning (`plan_execute`, spawns executors via `ctx.run_node`) | planner function + dynamically scheduled executor |
| `approval_gate` | propose/complete sequence + approval policy | proposer/completer nodes |

Presets consume only `RuntimeContext` (`basic_agent.runtime`); catalog
metadata (key, title, when-to-use, defaults, aliases) lives only in
`presets/`, and the registry catalog drives config validation errors — no
hard-coded conditionals anywhere in the chain. Custom use cases plug in the
same way: expose a `PRESETS` dict of `basic_agent.presets.Preset` in a
module (or a single `PRESET`), point `AGENT_USE_CASE_MODULE` at it
(allowlisted in production via `AGENT_USE_CASE_MODULE_ALLOWLIST`), and the
registry registers them. Custom graph function nodes plug in the same way:
expose a `FUNCTIONS` dict of callables in a module, point
`AGENT_FUNCTION_MODULE` at it (allowlisted via
`AGENT_FUNCTION_MODULE_ALLOWLIST`), and the compiler resolves
`options.function` names against the merged registry. The `compile/` layer is the single sanctioned home
for ADK composition classes; policies (`policies/`) attach per-run behavior
(approval, synthesis) to any preset or raw graph.

## Code-execution resolution (ADR-004)

Providers implement `probe()` (pure bool, never raises) and `build()`.
The resolver applies an explicit `AGENT_CODE_EXECUTION_STRATEGY` override
first — unknown or unsatisfiable names raise `ProviderConfigurationError`
at startup — then auto-detects in registration order:
`vertex_ai` → `agent_engine_sandbox` → `gke` → `docker_container` →
`gemini_built_in`; otherwise `unavailable` with no executor and an honest
instruction line. `unsafe_local` is explicit-override-only and warns on
every selection.

The `docker_container` provider builds `HardenedContainerCodeExecutor`:
defined inside a cached factory (subclassing `ContainerCodeExecutor`
triggers ADK's lazy import, which must not happen at module scope on
Docker-less deployments), adding mem/cpu/pids limits, read-only rootfs +
`/tmp` tmpfs, a numeric non-root user, and a wall-clock `execute_code` timeout
that SIGKILLs and restarts the reused container. The published application
image includes the optional Docker SDK; the provider still remains inactive
unless code execution is configured and a Docker endpoint probes successfully.
Verified internals and upgrade
re-verification duties are recorded in ADR-004 Appendices A/B.

## Request path (compose deployment)

```
client ──► api-proxy (host ${ADK_API_PORT:-8002}/${LIVE_API_PORT:-8003} → container :${ADK_API_CONTAINER_PORT:-8002}/:${LIVE_API_CONTAINER_PORT:-8003})
              │  forward-auth middleware
              ▼
          auth-gateway (:${AUTH_GATEWAY_CONTAINER_PORT:-8010}) ──► Keycloak JWKS (container :${KEYCLOAK_CONTAINER_PORT:-8080}; host default ${KEYCLOAK_PORT:-8080})
              │  injects verified identity
              ▼
          adk-api (:${ADK_API_CONTAINER_PORT:-8002}) ──► root_agent (ADK) ──► tools
```

All host and application container ports shown here are environment-driven;
see the [configuration port matrix](./CONFIGURATION.md#interfaces-and-ports).
The auth gateway is internal-only and has no host port mapping.

- Traefik discovers containers through the read-only
  `docker-socket-proxy` (`POST=0`) — discovery only, never mutation.
- Session identity is bound to the validated token subject; client-supplied
  `user_id` values cannot select another user's session.
- Live WebSocket authenticates via Authorization header, subprotocol, or
  first `auth` message — never a query parameter; frames are size- and
  rate-limited.
- The sandbox `code-exec-socket-proxy` (`code-exec` profile, `POST=1` +
  container-lifecycle sections only) sits on a dedicated `code-exec`
  network with only `adk-api` attached — network isolation is the boundary
  that scopes its daemon-wide exec power (verified live in ADR-004).

## Observability

OpenTelemetry spans (OTLP/gRPC) flow to the `observability` profile's
Grafana/Loki/Tempo/Prometheus stack. Every invocation span carries
`adk.capabilities` (auto-detected capability strategies + resolved
code-execution strategy), app name, and invocation id. The
`GenericAgentPlugin` starts/ends invocation spans and logs lifecycle
events.

## CI/CD

Gates on every push/PR (see [CI/CD guide](../.github/CI-CD-INTEGRATION.md)
and [publishing guide](../.github/PUBLISHING.md) for details):

1. **lint** — formatting, JSON fixture validation, compose config
   validation (default **and** `code-exec` profile shapes), gitleaks over
   full history.
2. **test** — Python 3.10–3.13 matrix plus `docker` and `gke` extras jobs,
   with coverage ≥ 90%; the separate **audit** job runs `pip-audit` once per
   lockfile.
3. **build → verify-image → promote-image** — the image is built to an
   unverified `ci-<sha>` tag, then locked-dependency checks, Trivy
   (HIGH/CRITICAL), and startup smoke tests must pass **before** the
   verified digest is promoted to any release tag (`latest`, branch,
   semver). A broken or vulnerable image is never reachable under a
   release tag. Version tags must descend from `main`, and the temporary
   `ci-<sha>` tag is removed after the build path completes.
