# Generic Agent Runtime

An AI agent that adapts to your needs. Choose what you want it to do, configure it with environment variables, and run it with one Docker command.

[![Tests](https://img.shields.io/badge/tests-379%20passing-brightgreen)](./tests/)
[![Coverage](https://img.shields.io/badge/coverage-95.57%25-brightgreen)](./tests/)
[![Python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12%20%7C%203.13-blue)](https://www.python.org/)
[![Status](https://img.shields.io/badge/status-active%20%2F%20staging-yellow)](.)

## What does it do?

This agent can:

- **Answer questions** using your documents, web search, or connected services
- **Run multi-step workflows** — fetch data, analyze it, summarize results
- **Route questions to specialists** — billing goes to billing, tech goes to tech
- **Coordinate teams of AI workers** on complex tasks
- **Plan and execute** — make a plan first, then carry it out
- **Ask for your approval** before taking actions

All powered by Google's ADK (Agent Development Kit) with support for any AI model — Gemini, OpenAI, Anthropic, Ollama, and more.

## Quick start (30 seconds)

```bash
# 1. Set your API key and model (they must match)
export OPENAI_API_KEY=your-key

# 2. Run the agent
# Local-only demo: AUTH_DISABLED creates an isolated anonymous cookie/session;
# use Keycloak/OIDC before exposing this beyond localhost.
docker run -p 127.0.0.1:8002:8002 \
  -e OPENAI_API_KEY=$OPENAI_API_KEY \
  -e ADK_MODEL=openai/gpt-4o \
  -e AUTH_DISABLED=true \
  ghcr.io/bassemzohdy/generic-agent-adk:latest

# 3. Open http://localhost:8002/docs to try it
```

That's it! The agent runs as a REST API you can call from any application.

> **Model ↔ key must match**: without `ADK_MODEL`, the agent defaults to Gemini and needs `GOOGLE_API_KEY` instead.

## Choose what your agent does

Set `AGENT_USE_CASE` to pick a behavior:

| What you want | Use case | Example |
|---|---|---|
| Answer questions, use tools when needed | `assistant` | "What's our Q3 revenue?" |
| Run steps in order | `pipeline` | "Fetch data → analyze → summarize" |
| Get multiple perspectives | `multi_perspective` | "What do different experts think?" |
| Keep improving until it's good | `refine_until_good` | "Write a better version" |
| Route to the right specialist | `expert_dispatch` | "Billing question → billing AI" |
| Coordinate a team | `team_coordinator` | "Research, write, and review this" |
| Plan then execute | `plan_and_execute` | "Break this into steps and do them" |
| Ask before acting | `approval_gate` | "Should I send this email?" |

```bash
docker run -e AGENT_USE_CASE=pipeline \
  -e ADK_MODEL=openai/gpt-4o \
  -e OPENAI_API_KEY=$OPENAI_API_KEY \
  -e AUTH_DISABLED=true \
  ghcr.io/bassemzohdy/generic-agent-adk:latest
```

## Choose and configure your AI model

Gemini uses ADK's native model integration. To use LiteLLM as the model
provider, set `model.provider` to `litellm` in YAML and put LiteLLM's
underlying provider/model string in `model.name`. For environment-only
configuration, put that same `provider/model` string in `ADK_MODEL`.

| Underlying provider | LiteLLM model string | Typical environment variables |
|---|---|---|
| OpenAI | `openai/<model>` | `OPENAI_API_KEY` |
| Anthropic | `anthropic/<model>` | `ANTHROPIC_API_KEY` |
| DeepSeek | `deepseek/<model>` | `DEEPSEEK_API_KEY` |
| Groq | `groq/<model>` | `GROQ_API_KEY` |
| Mistral | `mistral/<model>` | `MISTRAL_API_KEY` |
| Ollama | `ollama/<model>` | `OLLAMA_API_BASE` |
| OpenRouter | `openrouter/<provider>/<model>` | `OPENROUTER_API_KEY` |

Examples:

```bash
# OpenAI
docker run -e ADK_MODEL=openai/gpt-4o -e OPENAI_API_KEY=...

# Anthropic
docker run -e ADK_MODEL=anthropic/claude-sonnet-5 -e ANTHROPIC_API_KEY=...

# DeepSeek
docker run -e ADK_MODEL=deepseek/<model-name> -e DEEPSEEK_API_KEY=...

# Local with Ollama
docker run \
  -e ADK_MODEL=ollama/<model-name> \
  -e OLLAMA_API_BASE=http://host.docker.internal:11434

# OpenRouter
docker run \
  -e ADK_MODEL=openrouter/<provider>/<model-name> \
  -e OPENROUTER_API_KEY=...
```

For a YAML configuration, set `model.provider: litellm`. The
`model.name`, `model.api_key`, and `model.base_url` values are passed to
LiteLLM. Keep secrets in environment variables rather than committing them.

```yaml
agent:
  use_case: assistant

model:
  provider: litellm
  name: openai/gpt-4o
  api_key: "${OPENAI_API_KEY}"
  # Useful for an OpenAI-compatible gateway or self-hosted endpoint.
  base_url: "${OPENAI_API_BASE:https://api.openai.com/v1}"
```

When using LiteLLM, keep the underlying provider prefix in `model.name` (for
example, `openai/gpt-4o`); `name: gpt-4o` with `provider: litellm` would resolve
to the invalid `litellm/gpt-4o` route. With environment-only configuration,
set `ADK_MODEL` to the complete `provider/model` value; the provider's
standard LiteLLM environment variables are then used automatically. See the [ADK LiteLLM
guide](https://adk.dev/agents/models/litellm/) and [LiteLLM provider
catalog](https://docs.litellm.ai/docs/providers) for provider-specific model
names and credentials.

## Give your agent tools

Add tools to make your agent more capable:

```bash
docker run -e AGENT_TOOLS=knowledge,search,code_execution \
  -e ADK_MODEL=openai/gpt-4o \
  -e OPENAI_API_KEY=$OPENAI_API_KEY \
  -e AUTH_DISABLED=true \
  ghcr.io/bassemzohdy/generic-agent-adk:latest
```

Available tools (default: `knowledge,search,mcp,approval,runtime,structured_output`):
- `knowledge` — search your documents (`AGENT_KNOWLEDGE_FILE`, JSON)
- `search` — web search
- `code_execution` — run Python in a sandbox (auto-detected; see [ADR-004](./docs/ADR-004-pluggable-code-execution.md))
- `approval` — ask for human approval before actions
- `skills` — load SKILL.md capability folders (`AGENT_SKILLS_DIR`)
- `mcp` — call tools via Model Context Protocol
- `openapi` — call an OpenAPI-described service (`AGENT_OPENAPI_URL`; opt in explicitly)
- `runtime` — let the agent inspect its own configuration
- `structured_output` — return responses in a fixed JSON schema
- `application_integration` — trigger GCP Application Integrations

`mcp` and `openapi` need a reachable backend — run the bundled example with the compose `demo` profile (`docker compose --profile demo up`).

## Run with Docker Compose (full stack)

For a setup with authentication, monitoring, and more:

```bash
# 1. Clone and configure
git clone https://github.com/bassemZohdy/generic-agent-adk.git
cd generic-agent-adk
cp .env.example .env
# Required: set KEYCLOAK_ADMIN_PASSWORD and a model API key
# (GRAFANA_ADMIN_PASSWORD too if you use the observability profile)

# 2. For local evaluation, enable the demo user (demo/demo)
echo "DEMO_MODE=true" >> .env

# 3. Start everything
docker compose up --build -d

# 4. Get a token and call the API
curl -s -X POST http://localhost:8080/realms/basic-agent/protocol/openid-connect/token \
  -d client_id=basic-agent -d username=demo -d password=demo -d grant_type=password \
  | python -c "import sys,json; print(json.load(sys.stdin)['access_token'])"
```

The API at `http://localhost:8002` requires that token (`Authorization: Bearer …`) — every request passes through Keycloak verification. Without `DEMO_MODE=true`, the production realm is imported (no demo user, no direct password grants) — bring your own users.

Add features with profiles:

```bash
# Add live WebSocket support (port 8003)
docker compose --profile live up --build

# Add monitoring dashboards (Grafana on localhost:3000)
docker compose --profile observability up --build

# Add the code execution sandbox
AGENT_TOOLS=knowledge,search,code_execution \
  docker compose --profile code-exec up --build

# Add the demo service API (port 8001) backing the mcp/openapi tools
docker compose --profile demo up --build
```

## Configure with YAML (advanced)

The complete strict YAML schema and environment reference is in
[docs/CONFIGURATION.md](./docs/CONFIGURATION.md); supported versions and
deployment boundaries are in [docs/SUPPORT.md](./docs/SUPPORT.md).

For complex setups, use a YAML config file:

```yaml
# config.yaml
agent:
  use_case: expert_dispatch
  description: "Customer support dispatcher"

model:
  name: "openai/gpt-4o"

roles:
  billing:
    instruction: "You handle billing and payment questions."
  technical:
    instruction: "You handle technical support issues."

tools:
  enabled: [knowledge, search, approval]
```

```bash
docker run \
  -v ./config.yaml:/app/config/agent.yaml \
  -e OPENAI_API_KEY=$OPENAI_API_KEY \
  -e AUTH_DISABLED=true \
  ghcr.io/bassemzohdy/generic-agent-adk:latest
```

## Authentication

A plain `docker run` has no identity provider attached, so for local testing disable auth:

```bash
docker run -e AUTH_DISABLED=true ...
```

With Docker Compose, a Keycloak service is included:

- `DEMO_MODE=true` imports the dev realm with a `demo` / `demo` user — local evaluation only (compose refuses it in production-like `DEPLOYMENT_ENV`s).
- Default is the production realm: no demo user, no direct password grants, brute-force protection on.

For production, use Keycloak or your own OIDC provider — the API fails closed if `KEYCLOAK_ISSUER` is unset (`503`), and identity is bound to the token subject on every request.

## Common configurations

### Simple Q&A agent
```bash
docker run -e ADK_MODEL=openai/gpt-4o -e OPENAI_API_KEY=your-key -e AUTH_DISABLED=true \
  ghcr.io/bassemzohdy/generic-agent-adk:latest
```

### Agent with web search
```bash
docker run -e ADK_MODEL=openai/gpt-4o -e OPENAI_API_KEY=your-key -e AUTH_DISABLED=true \
  -e AGENT_TOOLS=knowledge,search \
  ghcr.io/bassemzohdy/generic-agent-adk:latest
```

### Agent that writes and runs code
```bash
docker run -e ADK_MODEL=openai/gpt-4o -e OPENAI_API_KEY=your-key -e AUTH_DISABLED=true \
  -e AGENT_TOOLS=knowledge,search,code_execution \
  ghcr.io/bassemzohdy/generic-agent-adk:latest
```

### Multi-step workflow
```bash
docker run -e ADK_MODEL=openai/gpt-4o -e OPENAI_API_KEY=your-key -e AUTH_DISABLED=true \
  -e AGENT_USE_CASE=pipeline \
  -e AGENT_INSTRUCTION="First research the topic, then write a summary, then review it." \
  ghcr.io/bassemzohdy/generic-agent-adk:latest
```

## Learn more

- [Architecture](./docs/ARCHITECTURE.md) — how it works internally
- [Examples](./examples/) — ready-to-use YAML configs
- [Skills](./skills/) — add specialized capabilities
- [CHANGELOG](./CHANGELOG.md) — what's new

## Troubleshooting

| Problem | Solution |
|---|---|
| Agent doesn't start | Model and API key must match: `ADK_MODEL=openai/…` needs `OPENAI_API_KEY`, no prefix needs `GOOGLE_API_KEY` |
| `503` from the API | Auth not configured — set `KEYCLOAK_ISSUER` or explicitly `AUTH_DISABLED=true` |
| Compose won't start | `KEYCLOAK_ADMIN_PASSWORD` (and `GRAFANA_ADMIN_PASSWORD` with observability) must be set in `.env` |
| Wrong behavior | Check the startup log for which config was loaded |
| Keycloak won't start | Make sure port 8080 is free |
| Import errors | Run `uv sync --upgrade` |

## For developers

```bash
# Setup
git clone https://github.com/bassemZohdy/generic-agent-adk.git
cd generic-agent-adk
uv sync
cp .env.example .env
uvx pre-commit install       # gitleaks secret scan

# Run locally (same server compose uses)
uv run uvicorn basic_agent.interfaces.rest:app --port 8002

# Or via the ADK CLI
uv run adk api_server src/basic_agent

# Run tests
uv run pytest tests/ -v
```

See [Architecture](./docs/ARCHITECTURE.md) for how the code is organized.
