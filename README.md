# Generic Agent Runtime (ADK)

One Docker image, eight use cases. Configure with env vars or YAML, run it.

[![Tests](https://img.shields.io/badge/tests-311%20passing-brightgreen)](./tests/)
[![Coverage](https://img.shields.io/badge/coverage-96%25-brightgreen)](./tests/)
[![Python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12%20%7C%203.13-blue)](https://www.python.org/)
[![Status](https://img.shields.io/badge/status-production%20ready-green)](.)

## Quick start

```bash
# Minimal — env vars only
docker run \
  -e OPENAI_API_KEY=your-key \
  -e AGENT_USE_CASE=assistant \
  -e ADK_MODEL=openai/gpt-4o \
  -e AUTH_DISABLED=true \
  ghcr.io/bassemzohdy/generic-agent-adk:latest

# Full control — mount a YAML config
docker run \
  -v ./examples/expert-dispatch.yaml:/app/config/agent.yaml \
  -e GOOGLE_API_KEY=your-key \
  -e AUTH_DISABLED=true \
  ghcr.io/bassemzohdy/generic-agent-adk:latest
```

## Use cases

| I want an agent that… | Use case |
|---|---|
| Answers questions; investigates when tools are enabled | `assistant` |
| Runs fixed steps in order | `pipeline` |
| Gets several independent takes and aggregates them | `multi_perspective` |
| Keeps improving until it's good enough | `refine_until_good` |
| Routes questions to the right specialist | `expert_dispatch` |
| Coordinates a team of workers | `team_coordinator` |
| Plans first, then executes | `plan_and_execute` |
| Proposes actions, waits for approval | `approval_gate` |

See [`examples/`](./examples/) for YAML configs.

## Configuration

| Variable | Default | Notes |
|---|---|---|
| `GOOGLE_API_KEY` | — | Required for Gemini models |
| `OPENAI_API_KEY` | — | Required for OpenAI (or `ANTHROPIC_API_KEY`, `GROQ_API_KEY`, etc.) |
| `AGENT_USE_CASE` | `assistant` | Any use case from the table above |
| `ADK_MODEL` | `gemini-3.6-flash` | `provider/model` prefix for LiteLLM routing |
| `AGENT_INSTRUCTION` | built-in prompt | Custom instruction for the agent |
| `AGENT_TOOLS` | `knowledge,search,mcp,openapi,approval,runtime,structured_output` | Comma-separated tool list |
| `AGENT_MAX_ITERATIONS` | `3` | For `refine_until_good`, `plan_and_execute` |
| `AGENT_SPECIALISTS` | `research,solution,risk` | For `expert_dispatch` |
| `AUTH_DISABLED` | `false` | Set `true` for local dev without Keycloak |

All variables listed in [.env.example](.env.example). YAML config supports `${VAR:default}` substitution and per-role overrides — see [examples/](./examples/).

## Tools

**Skills** — add `skills` to `AGENT_TOOLS`, set `AGENT_SKILLS_DIR` to a folder of `SKILL.md` directories. See [`skills/status-check/SKILL.md`](./skills/status-check/SKILL.md).

**Code execution** — add `code_execution` to `AGENT_TOOLS`. The agent auto-detects the best sandbox strategy:

| Strategy | Trigger |
|---|---|
| `vertex_ai` | `AGENT_CODE_EXECUTION_VERTEX_RESOURCE` set |
| `agent_engine_sandbox` | `AGENT_CODE_EXECUTION_AGENT_ENGINE_RESOURCE` set |
| `gke` | `AGENT_CODE_EXECUTION_GKE_KUBECONFIG_PATH` set |
| `docker_container` | Docker daemon reachable |
| `gemini_built_in` | Native Gemini 2.0+ model |
| `unsafe_local` | Explicit opt-in only — **no isolation** |

Pin with `AGENT_CODE_EXECUTION_STRATEGY`. In Compose, enable `--profile code-exec` and set `AGENT_CODE_EXECUTION_DOCKER_HOST=tcp://code-exec-socket-proxy:2375`. Default sandbox: `python:3.13-slim` (512 MB RAM, 1 CPU, read-only rootfs, no network).

## Docker Compose

```bash
cp .env.example .env
# Set KEYCLOAK_ADMIN_PASSWORD in .env
docker compose up --build
```

| Profile | Adds |
|---|---|
| `live` | Live WebSocket (`:8003`) |
| `observability` | Grafana/Loki/Tempo/Prometheus (`:3000`) |
| `demo` | Example service API (`:8001`) |
| `code-exec` | Sandbox code-execution proxy |

REST API at `:8002/docs`, Keycloak at `:8080`.

## Authentication

Keycloak OIDC. Set `DEMO_MODE=true` in `.env` for local dev with `demo`/`demo` credentials. Production: set `KEYCLOAK_ISSUER`, disable `DEMO_MODE`.

```bash
# Get a token
curl -X POST http://localhost:8080/realms/basic-agent/protocol/openid-connect/token \
  -d client_id=basic-agent -d username=demo -d password=demo -d grant_type=password

# Use it
curl -H "Authorization: Bearer <token>" http://localhost:8002/status
```

## Local development

```bash
uv sync
cp .env.example .env
export GOOGLE_API_KEY=your-key

uv run adk api_server src/basic_agent    # REST API
uv run adk web src/basic_agent           # Web UI
uv run pytest tests/ -v                  # Tests
```

## Documentation

- [Architecture](./docs/ARCHITECTURE.md) — module map, config pipeline, request path
- [ADR-001](./docs/ADR-001-generic-runtime-architecture.md) · [ADR-002](./docs/ADR-002-use-case-taxonomy.md) · [ADR-003](./docs/ADR-003-adk-workflow-migration.md) · [ADR-004](./docs/ADR-004-pluggable-code-execution.md)
- [CHANGELOG](./CHANGELOG.md) · [CI/CD guide](./.github/CI-CD-INTEGRATION.md) · [Publishing guide](./.github/PUBLISHING.md)

## Troubleshooting

- **Import errors** → `uv sync --upgrade`
- **Keycloak won't start** → check port 8080 is free, wait 30s
- **Wrong agent behavior** → check startup provenance log for resolved config

## Production checklist

1. Replace Keycloak starter with a managed identity provider
2. Set `KEYCLOAK_ISSUER`, `KEYCLOAK_AUDIENCE`, production secrets
3. Keep `AUTH_DISABLED=false`, `DEMO_MODE=false`
4. Keep CI gates enabled (pip-audit, gitleaks, Trivy)
5. If code execution enabled: keep `code-exec` proxy on dedicated network, digest-pin sandbox image, verify resource limits after ADK upgrades, never use `unsafe_local` in production
