# Generic Agent Runtime (ADK)

One Docker image, nine generic use cases. Pick what you want the agent to do, configure it with environment variables or YAML, run it.

[![Tests](https://img.shields.io/badge/tests-169%20passing-brightgreen)](./tests/)
[![Coverage](https://img.shields.io/badge/coverage-88%25-brightgreen)](./tests/)
[![Python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12%20%7C%203.13-blue)](https://www.python.org/)
[![Status](https://img.shields.io/badge/status-production%20ready-green)](.)

## What do you want to build?

Start from what you need, not from architecture names:

| I want an agent that… | Use case | Example config |
|---|---|---|
| Answers questions directly, in one shot | `assistant` | [`examples/assistant.yaml`](./examples/assistant.yaml) |
| Searches and investigates using tools | `research_assistant` | [`examples/research-assistant.yaml`](./examples/research-assistant.yaml) |
| Runs fixed steps in order (fetch → analyze → summarize) | `pipeline` | [`examples/pipeline.yaml`](./examples/pipeline.yaml) |
| Gets several independent takes and aggregates them | `multi_perspective` | [`examples/multi-perspective.yaml`](./examples/multi-perspective.yaml) |
| Keeps improving its output until it's good enough | `refine_until_good` | [`examples/refine-until-good.yaml`](./examples/refine-until-good.yaml) |
| Sends each question to the right specialist | `expert_dispatch` | [`examples/expert-dispatch.yaml`](./examples/expert-dispatch.yaml) |
| Coordinates a team of workers on complex work | `team_coordinator` | [`examples/team-coordinator.yaml`](./examples/team-coordinator.yaml) |
| Makes a plan first, then executes it | `plan_and_execute` | [`examples/plan-and-execute.yaml`](./examples/plan-and-execute.yaml) |
| Proposes actions and waits for my approval | `approval_gate` | [`examples/approval-gate.yaml`](./examples/approval-gate.yaml) |

### Run with environment variables only (minimal)

```bash
docker run \
  -e GOOGLE_API_KEY=your-key \
  -e AGENT_USE_CASE=research_assistant \
  ghcr.io/your-org/adk:latest
```

That's it — every use case runs with sane defaults from two environment variables.

### Run with a YAML config (full control)

```bash
docker run \
  -v ./examples/expert-dispatch.yaml:/app/config/agent.yaml \
  -e GOOGLE_API_KEY=your-key \
  ghcr.io/your-org/adk:latest
```

A config file mounted at `/app/config/agent.yaml` is auto-detected (or set `AGENT_CONFIG_FILE`). YAML unlocks per-role instructions, models, and tools via the `roles:` section — see [`examples/expert-dispatch.yaml`](./examples/expert-dispatch.yaml).

## Configuration

### Minimal environment variables

| Variable | Required | Default | Applies to |
|---|---|---|---|
| `GOOGLE_API_KEY` | ✅ | — | all use cases |
| `AGENT_USE_CASE` | — | `assistant` | all |
| `ADK_MODEL` | — | `gemini-3.6-flash` | all |
| `AGENT_INSTRUCTION` | — | built-in generic prompt | all |
| `AGENT_TOOLS` | — | all tools | all |
| `AGENT_MAX_ITERATIONS` | — | `3` | `refine_until_good`, `plan_and_execute` |
| `AGENT_SPECIALISTS` | — | `research,solution,risk` | `expert_dispatch` |

Advanced variables (auth, MCP, OpenAPI, knowledge, telemetry) are listed in [.env.example](.env.example).

### How YAML and env vars merge

1. The YAML file (auto-detected `/app/config/agent.yaml`, or `AGENT_CONFIG_FILE`) is the base. `${VAR:default}` substitution runs inside it.
2. Then the **7 documented env vars above** override — but only the ones explicitly set. Env always wins for these keys.
3. No file → env-only configuration.
4. Startup logs one provenance line: `config: yaml=/app/config/agent.yaml, use_case=expert_dispatch, env overrides: ADK_MODEL`.

### YAML reference

```yaml
agent:
  use_case: expert_dispatch        # a key from the table above
  description: "Customer support dispatcher"

model:
  name: "${ADK_MODEL:gemini-3.6-flash}"

roles:                              # per-role overrides (YAML only)
  billing:
    instruction: "You answer billing and invoice questions precisely."
  technical:
    instruction: "You answer technical troubleshooting questions."
    model: "${ADK_MODEL:gemini-3.6-flash}"

tools:
  enabled: [knowledge, search]

execution:
  max_iterations: 5                # refine_until_good, plan_and_execute
```

### Deprecated names (still work, will be removed)

| Old | New |
|---|---|
| `AGENT_PATTERN` | `AGENT_USE_CASE` |
| `AGENT_PATTERN_MAX_ITERATIONS` | `AGENT_MAX_ITERATIONS` |
| `AGENT_PATTERN_SPECIALISTS` | `AGENT_SPECIALISTS` |
| `AGENT_PATTERN_REQUIRE_APPROVAL` | `AGENT_USE_CASE=approval_gate` |
| `agent.type` in YAML | `agent.use_case` |
| pattern names (`sequential`, `router`, `planner_executor`, …) | use-case keys (see table above) |

## Extending: custom use cases

Technical users can add use cases without forking the runtime:

1. Subclass `BaseUseCaseAgent` ([`src/basic_agent/use_cases/base.py`](./src/basic_agent/use_cases/base.py)), set its metadata and underlying strategy, and optionally override runtime hooks: `before_run`, `after_run`, `before_tool`, `after_tool` — wired automatically as ADK callbacks on the composed agent tree.
2. Point `AGENT_USE_CASE_MODULE=/path/to/your_module.py` at your module; `BaseUseCaseAgent` subclasses found in it register automatically.

## Architecture

Two layers, one dependency direction — `use_cases` → `strategies`, never reverse:

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

- **`use_cases/`** — the public surface. Metadata (key, title, when-to-use, defaults, aliases) lives only here; the registry catalog drives config validation errors and the decision table above.
- **`strategies/`** — internal composition. Registry pattern, no hard-coded conditionals; shared builders keep the 10 strategy files small.

Design records: [ADR-001](./docs/ADR-001-generic-runtime-architecture.md) · [ADR-002 use-case taxonomy](./docs/ADR-002-use-case-taxonomy.md)

## Local development

```bash
# Setup
uv sync
cp .env.example .env
export GOOGLE_API_KEY=your-key

# Run
uv run adk api_server src/basic_agent    # REST API at http://localhost:8002/docs
uv run adk web src/basic_agent           # Web UI

# Test
uv run pytest tests/ -v
```

## Docker

```bash
# Build locally
docker build -t adk:local .
docker run -p 8002:8002 -e GOOGLE_API_KEY=... adk:local

# Full stack (api, live, status, auth-gateway, keycloak, grafana)
cp .env.example .env
docker compose up --build
```

Services: REST API `:8002/docs` · Live WebSocket `:8003/live` · Status `:8001/status` · Grafana `:3000` · Keycloak `:8080`

## Authentication

Keycloak (OIDC) with role-based access control. Dev credentials: `demo` / `demo`.

```bash
# Get a token
curl -X POST http://localhost:8080/realms/basic-agent/protocol/openid-connect/token \
  -d client_id=basic-agent -d username=demo -d password=demo -d grant_type=password

# Use it
curl -H "Authorization: Bearer <token>" http://localhost:8002/status
```

Roles: `agent-user` (API access, default required), `agent-operator` (approvals). Override with `KEYCLOAK_REQUIRED_ROLES`, `AGENT_SERVICE_API_ROLES`, `LIVE_API_ROLES`.

## Observability

OpenTelemetry (OTLP/gRPC) → Grafana stack (Loki logs, Tempo traces, Prometheus metrics). Span attributes include the resolved use case and configuration. Included in `docker compose up` — visit Grafana at `http://localhost:3000`.

## Documentation

- [ADR-001 — Generic runtime architecture](./docs/ADR-001-generic-runtime-architecture.md)
- [ADR-002 — Use-case taxonomy & consolidation](./docs/ADR-002-use-case-taxonomy.md)
- [Feature & test inventory](./docs/FEATURES-AND-TESTS.md)
- [CI/CD guide](./.github/CI-CD-INTEGRATION.md) · [Publishing guide](./.github/PUBLISHING.md)
- Historical reports (pre-refactor) live in [docs/archive/](./docs/archive/)

## Troubleshooting

- **Import errors in tests** → `uv sync --upgrade`
- **Docker build fails** → check `.dockerignore`, `docker build --progress=plain .`
- **Keycloak won't start** → ensure port 8080 free, wait 30s, `docker compose logs keycloak`
- **Wrong agent behavior** → check the startup provenance log line for which config source and use case resolved

## Production checklist

1. Replace Keycloak with a managed identity provider
2. Set production secrets via environment
3. Configure external storage and monitoring
4. Enable image scanning in CI/CD

See `deploy/cloudrun/service.yaml` for a Cloud Run starter manifest.
