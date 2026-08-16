# Generic Agent Runtime

An AI agent that adapts to your needs. Choose what you want it to do, configure it with environment variables, and run it with one Docker command.

[![Tests](https://img.shields.io/badge/tests-311%20passing-brightgreen)](./tests/)
[![Coverage](https://img.shields.io/badge/coverage-96%25-brightgreen)](./tests/)
[![Python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12%20%7C%203.13-blue)](https://www.python.org/)
[![Status](https://img.shields.io/badge/status-production%20ready-green)](.)

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
# 1. Set your API key
export OPENAI_API_KEY=your-key

# 2. Run the agent
docker run -p 8002:8002 \
  -e OPENAI_API_KEY=$OPENAI_API_KEY \
  -e AUTH_DISABLED=true \
  ghcr.io/bassemzohdy/generic-agent-adk:latest

# 3. Open http://localhost:8002/docs to try it
```

That's it! The agent runs as a REST API you can call from any application.

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
  -e OPENAI_API_KEY=$OPENAI_API_KEY \
  -e AUTH_DISABLED=true \
  ghcr.io/bassemzohdy/generic-agent-adk:latest
```

## Choose your AI model

Works with any AI provider:

```bash
# OpenAI
docker run -e ADK_MODEL=openai/gpt-4o -e OPENAI_API_KEY=...

# Anthropic
docker run -e ADK_MODEL=anthropic/claude-sonnet-4-5 -e ANTHROPIC_API_KEY=...

# Google Gemini
docker run -e GOOGLE_API_KEY=...

# Local with Ollama
docker run -e ADK_MODEL=ollama/llama3 -e OLLAMA_API_BASE=http://host.docker.internal:11434
```

## Give your agent tools

Add tools to make your agent more capable:

```bash
docker run -e AGENT_TOOLS=knowledge,search,code_execution \
  -e OPENAI_API_KEY=$OPENAI_API_KEY \
  -e AUTH_DISABLED=true \
  ghcr.io/bassemzohdy/generic-agent-adk:latest
```

Available tools:
- `knowledge` — search your documents
- `search` — web search
- `code_execution` — run Python code safely in a sandbox
- `approval` — ask for human approval before actions
- `skills` — load specialized capabilities from folders

## Run with Docker Compose (production)

For a full setup with authentication, monitoring, and more:

```bash
# 1. Clone and configure
git clone https://github.com/bassemZohdy/generic-agent-adk.git
cd generic-agent-adk
cp .env.example .env
# Edit .env with your API keys

# 2. Start everything
docker compose up --build

# 3. Open http://localhost:8002/docs
```

Add features with profiles:

```bash
# Add live WebSocket support
docker compose --profile live up --build

# Add monitoring dashboards
docker compose --profile observability up --build

# Add code execution sandbox
docker compose --profile code-exec up --build
```

## Configure with YAML (advanced)

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

By default, the agent requires authentication. For local development:

```bash
# Disable auth for local testing
docker run -e AUTH_DISABLED=true ...

# Or use the demo credentials
docker run -e DEMO_MODE=true ...
# Login with: demo / demo
```

For production, set up Keycloak or your own identity provider.

## Common configurations

### Simple Q&A agent
```bash
docker run -e OPENAI_API_KEY=your-key -e AUTH_DISABLED=true \
  ghcr.io/bassemzohdy/generic-agent-adk:latest
```

### Agent with web search
```bash
docker run -e OPENAI_API_KEY=your-key -e AUTH_DISABLED=true \
  -e AGENT_TOOLS=knowledge,search \
  ghcr.io/bassemzohdy/generic-agent-adk:latest
```

### Agent that writes and runs code
```bash
docker run -e OPENAI_API_KEY=your-key -e AUTH_DISABLED=true \
  -e AGENT_TOOLS=knowledge,search,code_execution \
  ghcr.io/bassemzohdy/generic-agent-adk:latest
```

### Multi-step workflow
```bash
docker run -e OPENAI_API_KEY=your-key -e AUTH_DISABLED=true \
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
| Agent doesn't start | Check your API key is set correctly |
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

# Run locally
uv run adk api_server src/basic_agent

# Run tests
uv run pytest tests/ -v
```

See [Architecture](./docs/ARCHITECTURE.md) for how the code is organized.
