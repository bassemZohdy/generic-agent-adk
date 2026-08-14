# Generic Agent Runtime (ADK)

Production-grade Google Agent Development Kit (ADK) runtime with 10 execution strategies, YAML configuration, comprehensive testing, and complete CI/CD integration.

[![Tests](https://img.shields.io/badge/tests-99%20passing-brightgreen)](./TEST-COVERAGE-REPORT.md)
[![Coverage](https://img.shields.io/badge/coverage-85%25-brightgreen)](./TEST-COVERAGE-REPORT.md)
[![Python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12%20%7C%203.13-blue)](https://www.python.org/)
[![Status](https://img.shields.io/badge/status-production%20ready-green)](.)

## Overview

A fully-featured, configuration-driven ADK agent runtime supporting 10 execution patterns:

- **DIRECT** - Single agent, one-shot execution
- **REACT** - Iterative reasoning with tool use
- **SEQUENTIAL** - Ordered pipeline of agents
- **PARALLEL** - Concurrent independent agents
- **LOOP** - Iterative refinement with max iterations
- **ROUTER** - Intelligent specialist routing
- **SUPERVISOR** - Coordinated multi-worker execution
- **PLANNER_EXECUTOR** - Plan then execute pattern
- **EVALUATOR_OPTIMIZER** - Generate, evaluate, improve loop
- **HUMAN_IN_LOOP** - Proposal with approval gate

**One Docker image, multiple configurations** - Agent behavior determined entirely by YAML config, not code changes.

## Quick Start

### Local Development

```bash
# Setup
uv sync
cp .env.example .env
export GOOGLE_API_KEY=your-key

# Run REST API
uv run adk api_server basic_agent

# In another terminal, test it
curl http://localhost:8002/docs
```

### Docker Compose

```bash
cp .env.example .env
docker compose up --build
```

Services:
- REST API: http://localhost:8002/docs
- Live WebSocket: ws://localhost:8003/live
- Status API: http://localhost:8001/status
- Grafana: http://localhost:3000
- Keycloak: http://localhost:8080

### Change Execution Strategy

No code changes needed - just change the config:

```bash
# Run with REACT strategy (iterative tools)
docker run \
  -v ./examples/react-agent.yaml:/app/config/agent.yaml \
  -e GOOGLE_API_KEY=... \
  ghcr.io/your-org/adk:latest

# Same image, different behavior via YAML
```

## Configuration

### Environment Variables (for Runtime Settings)

```bash
# Core Configuration
APP_NAME=my-agent                    # Agent name
APP_VERSION=1.0.0                    # Version
AGENT_PATTERN=sequential             # Execution pattern (8 options)
ADK_MODEL=gemini-2.0-flash          # LLM model
AGENT_INSTRUCTION="Your prompt here" # System instruction
AGENT_TOOLS=knowledge,search,mcp    # Comma-separated tools

# Pattern-Specific
AGENT_PATTERN_MAX_ITERATIONS=5       # For LOOP, EVALUATOR_OPTIMIZER
AGENT_PATTERN_REQUIRE_APPROVAL=true  # For HUMAN_IN_LOOP
AGENT_PATTERN_SPECIALISTS=a,b,c     # For ROUTER

# Knowledge Source
AGENT_KNOWLEDGE_FILE=./knowledge.json

# Authentication
KEYCLOAK_ISSUER=https://keycloak/realms/agent
KEYCLOAK_ROLE_CLAIM=realm_access.roles
KEYCLOAK_REQUIRED_ROLES=agent-user

# External Services
AGENT_MCP_TOOLS=                     # MCP tool list
AGENT_OPENAPI_URL=https://api.example/openapi.json
```

See [.env.example](.env.example) for complete configuration.

### YAML Configuration (for Agent Behavior)

Deploy different configurations to the same Docker image:

```yaml
# examples/sequential-agent.yaml
agent:
  pattern: sequential
  description: "Research and analysis pipeline"

model:
  provider: google
  name: "${ADK_MODEL:gemini-2.0-flash}"

instructions:
  value: "You are part of a research pipeline..."

tools:
  enabled:
    - knowledge
    - search
    - code_execution

execution:
  steps: 3

output:
  schema: GenericAgentResponse
```

Configuration examples for all 10 patterns are in `examples/`:
- `direct-agent.yaml`, `react-agent.yaml`, `sequential-agent.yaml`, etc.

## Architecture

### Strategy + Registry Pattern

Each execution pattern is a pluggable **Strategy** registered in a **StrategyRegistry**. No hard-coded conditionals - dynamic strategy selection based on configuration.

```python
# Load config
config = load_config_from_yaml("examples/react-agent.yaml")

# Get strategy from registry
registry = get_default_registry()
strategy = registry.get(config.agent_type)

# Build agent
context = AgentStrategyContext(agent_type=config.agent_type, runtime=runtime)
agent = strategy.build(context)
```

**Benefits:**
- ✅ One Docker image, multiple behaviors
- ✅ No conditionals in core code
- ✅ Extensible - add new strategies easily
- ✅ Testable - each strategy has isolated tests
- ✅ Framework-agnostic configuration model

### Implementation Files

**Strategy Implementations** (10 files):
- `basic_agent/strategies/direct.py`
- `basic_agent/strategies/react.py`
- `basic_agent/strategies/sequential.py`
- `basic_agent/strategies/parallel.py`
- `basic_agent/strategies/loop.py`
- `basic_agent/strategies/router.py`
- `basic_agent/strategies/supervisor.py`
- `basic_agent/strategies/planner_executor.py`
- `basic_agent/strategies/evaluator_optimizer.py`
- `basic_agent/strategies/human_in_loop.py`

**Configuration & Registry**:
- `basic_agent/config.py` - Settings dataclass, AgentPattern enum
- `basic_agent/config_loader.py` - YAML loading with env var substitution
- `basic_agent/strategies/registry.py` - StrategyRegistry with lazy init

**Core Runtime**:
- `basic_agent/agent.py` - Root agent with strategy support
- `basic_agent/auth.py` - Keycloak/OIDC authentication
- `basic_agent/telemetry.py` - OpenTelemetry observability
- `basic_agent/service_api.py` - Status API

## Patterns Explained

### Pattern Characteristics

| Pattern | Workers | System Prompt | LLM | Consolidation |
|---------|---------|---------------|-----|---|
| DIRECT | 1 | SHARED | SHARED | One-shot |
| REACT | 1 | SHARED | SHARED | Iterative tools |
| SEQUENTIAL | N | SHARED | SHARED | Pipeline |
| PARALLEL | N | SHARED | SHARED | Aggregation |
| LOOP | 1 | SHARED | SHARED | Self-refinement |
| ROUTER | N+1 | DIFFERENT | SHARED | LLM routing |
| SUPERVISOR | N+1 | SHARED | SHARED | LLM synthesis |
| PLANNER_EXECUTOR | 2 | DIFFERENT | SHARED | Sequential |
| EVALUATOR_OPTIMIZER | 1 | SPECIAL | SHARED | Self-improve |
| HUMAN_IN_LOOP | 2 | DIFFERENT | SHARED | Approval gate |

**For detailed explanations** → See [AGENT-PATTERNS-ARCHITECTURE.md](./AGENT-PATTERNS-ARCHITECTURE.md)

## Testing

**Test Suite: 99 tests, 85% coverage**

```bash
# Run all tests
uv run pytest tests/ -v

# With coverage
uv run pytest tests/ --cov=basic_agent --cov-report=html

# Specific test file
uv run pytest tests/test_strategies.py -v
```

**Test Categories:**
- Unit tests (43) - Individual functions and classes
- Integration tests (8) - Component interactions
- Configuration tests (24) - YAML loading and validation
- Coverage improvement tests (26) - Edge cases
- Authentication tests (9) - Keycloak flows

**Coverage by Module:**
- Strategies: 93-100% ✅
- Configuration: 96-100% ✅
- Core agent: 85% ✅
- Patterns: 100% ✅

See [TEST-COVERAGE-REPORT.md](./TEST-COVERAGE-REPORT.md) for detailed analysis.

## CI/CD

GitHub Actions pipeline with:
- ✅ Multi-Python testing (3.10-3.13)
- ✅ Coverage reporting (85% threshold)
- ✅ Docker image building
- ✅ GHCR publishing
- ✅ Image verification

**Pipeline:**
1. **Lint** (5 min) - Code formatting, config validation
2. **Test** (15 min) - 99 tests, coverage reporting
3. **Build** (20 min) - Docker Buildx, push to GHCR
4. **Verify** (10 min) - Image verification
5. **Notify** (1 min) - Status notification

**Image Tagging:**
- `ghcr.io/your-org/adk:main` - Latest main branch
- `ghcr.io/your-org/adk:v1.0.0` - Version tags
- `ghcr.io/your-org/adk:latest` - Overall latest

See [.github/CI-CD-INTEGRATION.md](./.github/CI-CD-INTEGRATION.md) for complete guide.

## Docker Deployment

### Build Locally

```bash
docker build -t adk:local .
docker run -it \
  -v ./examples/react-agent.yaml:/app/config/agent.yaml \
  -e GOOGLE_API_KEY=... \
  adk:local
```

### Use Published Images

```bash
# Pull from GHCR
docker pull ghcr.io/your-org/adk:latest

# Run with custom config
docker run -it \
  -v ./examples/sequential-agent.yaml:/app/config/agent.yaml \
  -e GOOGLE_API_KEY=... \
  ghcr.io/your-org/adk:latest
```

### Docker Compose Services

- **api** - REST/A2A API (port 8002)
- **live** - WebSocket Live API (port 8003)
- **status** - Status API (port 8001)
- **auth-gateway** - Forward auth proxy
- **keycloak** - Identity provider (port 8080)
- **grafana** - Observability (port 3000)

All services reuse the same application image with different configurations.

## Authentication

Keycloak (OpenID Connect) authentication with configurable role-based access control.

**Development Credentials:**
- Username: `demo`
- Password: `demo`

**Get Token:**
```bash
curl -X POST http://localhost:8080/realms/basic-agent/protocol/openid-connect/token \
  -d client_id=basic-agent \
  -d username=demo \
  -d password=demo \
  -d grant_type=password
```

**Use Token:**
```bash
curl -H "Authorization: Bearer <token>" http://localhost:8002/status
```

**Roles:**
- `agent-user` - API access (default required)
- `agent-operator` - Operator access (for approvals)

Override with `KEYCLOAK_REQUIRED_ROLES`, `AGENT_SERVICE_API_ROLES`, `LIVE_API_ROLES`.

## Observability

**OpenTelemetry Integration:**
- OTLP/gRPC export to collector
- Grafana Loki (logs), Tempo (traces), Prometheus (metrics)
- Span attributes include strategy type, pattern, configuration

**Local Stack:**
```bash
docker compose up  # Includes grafana/otel-lgtm
```

Visit http://localhost:3000 (Grafana) for traces and metrics.

## Features

| Feature | Status | Implementation |
|---------|--------|-----------------|
| 10 execution strategies | ✅ | Fully implemented |
| YAML configuration | ✅ | config_loader.py |
| Environment variables | ✅ | Externalized settings |
| Strategy registry | ✅ | Pluggable patterns |
| Lazy initialization | ✅ | On-demand loading |
| Configuration validation | ✅ | Type-safe dataclasses |
| Tool management | ✅ | knowledge, search, mcp, etc. |
| State/output schemas | ✅ | GenericAgentResponse |
| Keycloak/OIDC | ✅ | JWT validation, roles |
| OpenTelemetry | ✅ | OTEL/gRPC export |
| Docker containerization | ✅ | Multi-stage, Buildx |
| GHCR publishing | ✅ | Automated CI/CD |
| Comprehensive testing | ✅ | 99 tests, 85% coverage |
| Multi-Python support | ✅ | 3.10, 3.11, 3.12, 3.13 |

## Documentation

Complete documentation available:

**Architecture & Design:**
- [AGENT-PATTERNS-ARCHITECTURE.md](./AGENT-PATTERNS-ARCHITECTURE.md) - Detailed pattern guide (1085 lines)
- [docs/ADR-001-generic-runtime-architecture.md](./docs/ADR-001-generic-runtime-architecture.md) - Architecture decisions

**Implementation & Deployment:**
- [.github/CI-CD-INTEGRATION.md](./.github/CI-CD-INTEGRATION.md) - CI/CD pipeline guide
- [.github/PUBLISHING.md](./.github/PUBLISHING.md) - Docker publishing guide
- [IMPLEMENTATION-COMPLETENESS-AUDIT.md](./IMPLEMENTATION-COMPLETENESS-AUDIT.md) - Completeness verification

**Testing & Analysis:**
- [TEST-COVERAGE-REPORT.md](./TEST-COVERAGE-REPORT.md) - Coverage analysis
- [docs/FEATURES-AND-TESTS.md](./docs/FEATURES-AND-TESTS.md) - Feature inventory

**Status Reports:**
- [FINAL-CICD-INTEGRATION-SUMMARY.md](./FINAL-CICD-INTEGRATION-SUMMARY.md) - Integration summary
- [CI-CD-INTEGRATION-REPORT.md](./CI-CD-INTEGRATION-REPORT.md) - Integration completion

## Development

### Setup

```bash
uv sync
cp .env.example .env
export GOOGLE_API_KEY=your-key
```

### Run

```bash
# API server
uv run adk api_server basic_agent

# Direct run
uv run adk run basic_agent

# Web UI
uv run adk web basic_agent
```

### Test

```bash
# Run all tests
uv run pytest tests/ -v

# Specific pattern
uv run pytest tests/test_strategies.py::TestSequentialStrategy -v

# With coverage
uv run pytest tests/ --cov=basic_agent
```

### Build Docker

```bash
docker build -t adk:dev .
docker run adk:dev
```

## Troubleshooting

**Tests fail with import errors:**
```bash
uv sync --upgrade
```

**Coverage below threshold:**
- Run `uv run pytest tests/ --cov=basic_agent --cov-report=html`
- View `htmlcov/index.html` for detailed coverage
- Add tests for uncovered code

**Docker build fails:**
- Check `.dockerignore` excludes large files
- Ensure base image available: `docker pull python:3.13-slim`
- View build logs: `docker build --progress=plain .`

**Keycloak won't start:**
- Ensure port 8080 is free
- Check logs: `docker compose logs keycloak`
- Wait 30 seconds for startup

## Production Deployment

For production deployment:

1. **Replace Keycloak** with managed identity provider
2. **Set production secrets** in environment
3. **Configure external storage** (database, cloud buckets)
4. **Enable image scanning** in CI/CD
5. **Set up monitoring** (Prometheus, custom dashboards)
6. **Configure rate limiting** as needed
7. **Use managed observability** (Cloud Trace, etc.)

See `deploy/cloudrun/service.yaml` for Cloud Run starter manifest.

## License

See LICENSE file.

## Support

**Documentation:**
- Architecture guide: [AGENT-PATTERNS-ARCHITECTURE.md](./AGENT-PATTERNS-ARCHITECTURE.md)
- CI/CD guide: [.github/CI-CD-INTEGRATION.md](./.github/CI-CD-INTEGRATION.md)
- Test report: [TEST-COVERAGE-REPORT.md](./TEST-COVERAGE-REPORT.md)

**Issues & Questions:**
- Check documentation first
- Review test examples in `tests/`
- Examine example configurations in `examples/`

---

**Status: ✅ Production Ready**

All 10 strategies implemented, tested (99 tests, 85% coverage), documented, and integrated with CI/CD. Ready for deployment.
