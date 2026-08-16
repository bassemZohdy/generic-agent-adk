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

Configuration (YAML + env vars) in, a Google ADK agent tree out, served
behind three interfaces (REST, Live WebSocket, MCP) with Keycloak
authentication and OpenTelemetry telemetry. Two internal layers with a
strict one-way dependency — `use_cases` → `strategies`, never reverse —
keep "what the user picks" separate from "how the ADK tree is shaped".

```
YAML / env vars
      │
      ▼
use_cases (public)          what the user picks + runtime behavior
  • one class per use case    (metadata, defaults, before/after hooks)
  • registry + alias catalog
      │
      ▼
strategies (internal)       how the ADK agent tree is shaped
  • pluggable builders        (LlmAgent / SequentialAgent /
  • shared llm() builder       ParallelAgent / LoopAgent)
  • per-role config
      │
      ▼
Google ADK agent tree
```

## Module map (`src/basic_agent/`)

| Module | Responsibility |
|---|---|
| `agent.py` | Entrypoint (~250 lines). Resolves config, builds the `RuntimeContext` (tool construction, model, code executor, instruction assembly), asks the use-case registry for the agent tree, exposes `root_agent`, the observability plugin, and `inspect_runtime`. Tool construction and knowledge retrieval live in focused companion modules. |
| `tools.py` | Tool building factories (`build_tool`, MCP/OpenAPI/Skill/ApplicationIntegration toolsets) and the before/after-tool audit callbacks (`protect_and_audit_tool`, `audit_tool_result`). Extracted from `agent.py` for single-responsibility. |
| `knowledge.py` | Knowledge file caching and `retrieve_knowledge` tool function. Extracted from `agent.py`. |
| `_util.py` | Import-cycle-free shared utilities: `is_production()` (unifies the production-deployment check duplicated across 5 files) and `split_csv()` (comma-split used by `config.py` and `config_loader.py`). Zero imports from the rest of the package. |
| `config.py` | `Settings`: frozen dataclass snapshotted from the environment once at import. Operational knobs (ports, limits, feature env vars). |
| `config_loader.py` | YAML ↔ env merge: `load_config_from_yaml` (with `${VAR:default}` substitution), `load_config_from_env`, `apply_env_overrides` (explicit env vars win), provenance logging. Defines the `AgentConfig` dataclass tree. |
| `models.py` | `resolve_model()`: bare string → native Gemini; `provider/model` prefix → `LiteLlm` instance. The single place provider routing is decided. |
| `autoconfig.py` | Ambient capability discovery (`discover_capabilities()`): probes for knowledge/search/storage backends etc. and reports a strategy per capability. Source of `ProviderConfigurationError`. |
| `code_execution.py` | ADR-004: the code-execution sandbox resolver — provider specs with pure-bool `probe()`, explicit-override-then-auto-detect chain, `CE_FIELD_ENV_MAP`, and the hardened Docker executor. See below. |
| `strategies/` | Internal composition layer. `base.py` defines `RuntimeContext` (everything a strategy may consume); one builder file per composition pattern; `registry.py` maps strategy keys to builders. |
| `use_cases/` | Public catalog. One class per use case binding metadata + a strategy; `base.py` provides `BaseUseCaseAgent` with runtime hooks wired as ADK callbacks. |
| `api_server.py` | REST/A2A interface (compose service `adk-api`, port 8002). |
| `live_server.py` | Live WebSocket interface (port 8003; `assistant` use case). Frame size/rate limits, session identity binding. |
| `auth_gateway.py` | FastAPI forward-auth endpoint Traefik calls on every request (port 8010). Validates JWTs against Keycloak, injects the verified identity. |
| `auth.py` | JWT validation primitives shared by the adapters. |
| `mcp_server.py` | Exposes the agent over the Model Context Protocol. |
| `service_api.py` | Demo-only read-only backend (`demo` profile) used as the example OpenAPI tool target. |
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

`Settings` (config.py) is deliberately a separate, import-time snapshot:
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
5. The use-case registry resolves the use-case key (aliases included) and
   its `build(runtime)` composes the final ADK agent tree.

## Use cases → strategies

| Use case | Strategy | ADK shape |
|---|---|---|
| `assistant` | `direct` | single `LlmAgent` |
| `pipeline` | `sequential` | `SequentialAgent` |
| `multi_perspective` | `parallel` | `ParallelAgent` |
| `refine_until_good` | `evaluator_optimizer` | optimizer/evaluator loop |
| `expert_dispatch` | `router` | dynamic sub-agent routing |
| `team_coordinator` | `supervisor` | supervisor + workers |
| `plan_and_execute` | `planner_executor` | planner then executor |
| `approval_gate` | `human_in_loop` | action + human confirmation |

Strategies consume only `RuntimeContext`; metadata (key, title,
when-to-use, defaults, aliases) lives only in `use_cases/`, and the
registry catalog drives config validation errors — no hard-coded
conditionals anywhere in the chain. Custom use cases plug in the same way:
subclass `BaseUseCaseAgent`, point `AGENT_USE_CASE_MODULE` at the module
(allowlisted in production via `AGENT_USE_CASE_MODULE_ALLOWLIST`), and the
class registers itself.

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
`/tmp` tmpfs, and a wall-clock `execute_code` timeout that SIGKILLs and
restarts the reused container. Verified internals and upgrade
re-verification duties are recorded in ADR-004 Appendices A/B.

## Request path (compose deployment)

```
client ──► api-proxy (Traefik :8002/:8003)
              │  forward-auth middleware
              ▼
          auth-gateway (:8010) ──► Keycloak JWKS (:8080)
              │  injects verified identity
              ▼
          adk-api (:8002) ──► root_agent (ADK) ──► tools
```

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
2. **test** — Python 3.10–3.13 matrix + an extras job
   (`uv sync --frozen --extra docker`), coverage ≥ 90%, pip-audit.
3. **build → verify-image → promote-image** — the image is built to an
   unverified `ci-<sha>` tag, then locked-dependency checks, Trivy
   (HIGH/CRITICAL), and startup smoke tests must pass **before** the
   verified digest is promoted to any release tag (`latest`, branch,
   semver). A broken or vulnerable image is never reachable under a
   release tag.
