# Generic configuration-driven ADK agent

This project is a reusable Google Agent Development Kit (ADK) runtime. It is
not tied to release readiness, CI metrics, or a fixed business workflow. The
agent identity, behavior, model, tools, knowledge source, authorization roles,
storage, observability, and deployment endpoints are external configuration.

The code supplies stable runtime adapters; users supply the agent policy.

## Configure

```bash
uv sync
cp .env.example .env
```

Set `GOOGLE_API_KEY` or configure Vertex AI authentication. The most important
agent settings are:

| Setting | Purpose |
| --- | --- |
| `APP_NAME` / `APP_VERSION` | Agent identity and metadata |
| `AGENT_PATTERN` | Root orchestration enum selecting the agentic pattern |
| `AGENT_PATTERN_MAX_ITERATIONS` | Bound for loop and evaluator/optimizer patterns |
| `AGENT_PATTERN_REQUIRE_APPROVAL` | Enables approval policy for human-in-the-loop flows |
| `AGENT_PATTERN_SPECIALISTS` | Comma-separated specialist roles for routing/coordinator flows |
| `ADK_MODEL` / `LIVE_ADK_MODEL` | Text and Live API models |
| `AGENT_DESCRIPTION` | Agent description shown by ADK |
| `AGENT_INSTRUCTION` | Complete system instruction/policy |
| `AGENT_TOOLS` | Comma-separated enabled tools |
| `AGENT_KNOWLEDGE_FILE` | Optional JSON or text knowledge source |
| `AGENT_OPENAPI_*` | External OpenAPI service contract |
| `AGENT_MCP_*` | MCP tool selection and namespacing |
| `KEYCLOAK_*` / `*_ROLES` | OIDC validation and authorization policy |

Available `AGENT_TOOLS` values are `knowledge`, `search`,
`code_execution`, `mcp`, `openapi`, `application_integration`, `approval`,
`runtime`, and `structured_output`. Remove a value to disable that capability;
no code change or new Agent is required.

`AGENT_KNOWLEDGE_FILE` accepts a JSON list of `{ "title", "content" }` objects
or a plain text/Markdown file. This makes the default retrieval tool useful for
any domain without embedding project content in Python.

## Run locally

```bash
uv run adk api_server basic_agent
uv run adk run basic_agent
```

The API server exposes the REST API and Swagger UI at `http://localhost:8000/docs`.
The ADK Web UI remains available as an explicitly local development tool when
interactive ADK-specific inspection is needed:

```bash
uv run adk web basic_agent
```

The entry point is `basic_agent/agent.py:root_agent`. It is one generic ADK
Agent whose tools are assembled from configuration. The agent does not create
domain-specific sub-agents or workflows.

## Agentic design patterns

The generic root agent remains the default. Native ADK workflow patterns are
available as separate agents under `basic_agent/patterns/` and selected by the
external `AGENT_PATTERN` enum:

| Pattern value | Agent file / ADK primitive | Use case | Required configuration |
| --- | --- | --- | --- |
| `generic` | `agent.py` / `GenericAgent` | Single configurable agent | `AGENT_TOOLS`, `AGENT_INSTRUCTION` |
| `sequential` | `patterns/sequential.py` / `SequentialAgent` | Ordered pipeline | `AGENT_TOOLS` |
| `parallel` | `patterns/parallel.py` / `ParallelAgent` | Independent perspectives | `AGENT_TOOLS` |
| `loop` | `patterns/loop.py` / `LoopAgent` | Repeated workflow | `AGENT_PATTERN_MAX_ITERATIONS` |
| `router` | `patterns/router.py` / `LlmAgent` delegation | Specialist routing | `AGENT_PATTERN_SPECIALISTS` |
| `planner_executor` | `patterns/planner_executor.py` / `SequentialAgent` | Plan → execute → verify | `AGENT_TOOLS` and external service settings |
| `evaluator_optimizer` | `patterns/evaluator_optimizer.py` / `LoopAgent` | Generate → evaluate → improve | `AGENT_PATTERN_MAX_ITERATIONS` |
| `human_in_loop` | `patterns/human_in_loop.py` / `SequentialAgent` | Propose → approve → complete | `AGENT_PATTERN_REQUIRE_APPROVAL=true` |

The configured pattern becomes the ADK `root_agent`; `generic` preserves the
original root agent. Hosts can also select one directly with
`get_pattern_agent(AgentPattern.PARALLEL)`. This keeps the default API
backward-compatible while allowing each pattern to be tested and deployed
independently.

The current ADK release reports the workflow-agent classes as deprecated in
favor of `Workflow`, but `Workflow` is not yet importable from the installed
Python ADK package and cannot currently be used as an `LlmAgent` sub-agent.
The implementation therefore keeps this compatibility boundary isolated in
the individual pattern modules for a future migration.

### Patterns not enabled by this Python runtime

ADK also documents graph-based workflows, dynamic workflows, custom agents,
and explicit runtime routing/fallback. They are not silently represented by a
prompt or mislabeled as one of the patterns above. The installed Python ADK
version does not expose the graph `Workflow` class used by those examples, so
they require a dedicated graph/custom-agent implementation before being added
to `AGENT_PATTERN`. This is an intentional boundary, not an unimplemented
configuration flag.

## Agent Strategy Registry (Architecture)

A **Strategy + Registry** pattern allows systematic, testable agent construction
without hard-coded conditionals. Each execution pattern (DIRECT, REACT, SEQUENTIAL, etc.)
is represented as a pluggable strategy.

### Using Configuration Files (Recommended for Deployment)

Declare agent behavior in YAML:

```yaml
# examples/react-agent.yaml
agent:
  type: REACT
  description: Research agent with iterative tool use

model:
  provider: google
  name: "${ADK_MODEL:gemini-2.0-flash}"

instructions:
  value: "Use tools iteratively to research and answer the user's request."

tools:
  enabled:
    - knowledge
    - search
    - code_execution
    - mcp

execution:
  max_iterations: 5

output:
  schema: GenericAgentResponse
  key: last_response

state:
  enabled: true
```

Launch with:

```bash
# Single Docker image, multiple configurations
docker run \
  -v ./examples/react-agent.yaml:/app/config/agent.yaml \
  -e GOOGLE_API_KEY=... \
  basic-adk-agent:local

# Different config = different agent, no image change
docker run \
  -v ./examples/sequential-agent.yaml:/app/config/agent.yaml \
  -e GOOGLE_API_KEY=... \
  basic-adk-agent:local
```

### Strategy Registry Programmatic Usage

```python
from basic_agent.strategies.registry import get_default_registry
from basic_agent.config_loader import load_config_from_yaml
from basic_agent.strategies.base import RuntimeContext, AgentStrategyContext

# Load configuration
config = load_config_from_yaml("examples/react-agent.yaml")

# Resolve strategy
registry = get_default_registry()
strategy = registry.get(config.type)

# Build runtime context
runtime = RuntimeContext(
    model=config.model.name,
    instruction=config.instructions.value,
    tools=[...],  # Configured tool instances
    description=config.description,
)

# Build agent
context = AgentStrategyContext(agent_type=config.type, runtime=runtime)
agent = strategy.build(context)
```

### Architecture Benefits

1. **One Docker Image**: Agent behavior determined entirely by configuration, not separate images.
2. **No Conditionals**: Strategy registry eliminates `if agent_type == "REACT"...` branches.
3. **Extensible**: Add new strategies by implementing `AgentStrategy`; no core runtime changes.
4. **Testable**: Each strategy has isolated unit and integration tests.
5. **Framework-Ready**: Configuration model is framework-agnostic, enabling future adapters (LangGraph, etc.).

### Example Configurations

Configuration examples for all patterns are in `examples/`:

- `direct-agent.yaml` - Single LlmAgent, one-shot
- `react-agent.yaml` - Iterative tool use
- `sequential-agent.yaml` - Ordered pipeline
- `parallel-agent.yaml` - Concurrent workers
- `loop-agent.yaml` - Iteration control
- `router-agent.yaml` - Specialist routing
- `supervisor-agent.yaml` - Coordinator pattern
- `planner-executor-agent.yaml` - Plan-then-execute
- `evaluator-optimizer-agent.yaml` - Generate-evaluate-improve
- `human-in-loop-agent.yaml` - Propose-approve-complete

See [FEATURES-AND-TESTS.md](./docs/FEATURES-AND-TESTS.md) for complete feature inventory and test coverage.
See [ADR-001](./docs/ADR-001-generic-runtime-architecture.md) for architecture decisions.

## Run with Docker

```bash
cp .env.example .env
docker compose up --build
```

Compose builds one `${APP_IMAGE}` (default `basic-adk-agent:local`) and reuses
it for the REST/A2A, Live, service-status, and authentication-gateway
containers. The Compose stack does not run or expose the ADK Web UI.
Commands and environment are externalized per service. Keycloak, Traefik, and
Grafana/OTEL-LGTM remain infrastructure images.

One image does not mean one process: separate containers preserve protocol and
lifecycle isolation while loading the same generic `root_agent`.

Services:

- ADK REST/A2A and Swagger UI: `http://localhost:8002` and `http://localhost:8002/docs` (Keycloak bearer token required through the API proxy)
- Live WebSocket: `ws://localhost:8003/live`
- Generic status API: `http://localhost:8001/status`
- Keycloak: `http://localhost:8080`
- Grafana: `http://localhost:3000`

## Authentication and roles

Compose imports the development `basic-agent` Keycloak realm. The development
user is `demo` / `demo`; obtain an access token with:

```bash
curl -s -X POST http://localhost:8080/realms/basic-agent/protocol/openid-connect/token \
  -d client_id=basic-agent -d username=demo -d password=demo \
  -d grant_type=password
```

Use the returned token as `Authorization: Bearer <token>`. The default policy
requires `agent-user` for the API proxy, status API, and Live API.
Override `KEYCLOAK_REQUIRED_ROLES`, `AGENT_SERVICE_API_ROLES`, and `LIVE_API_ROLES`
with comma-separated roles. Role claims are configured by
`KEYCLOAK_ROLE_CLAIM`, defaulting to `realm_access.roles`.

`agent-operator` is available as a separate realm role for policies that
require human approval. Credentials and realm administration must be replaced
with managed secrets/configuration outside development.

## Deployment

The default Docker image starts `adk api_server` on port `8002`. Compose uses
the same image with explicit service commands and externalized settings. The
Cloud Run file under `deploy/cloudrun/service.yaml` is a provider-specific
starter manifest; replace its image, identity, secrets, persistence, and
authentication settings before deployment.

## Auto-configured subsystems

Each subsystem discovers the first satisfied provider without a type flag:

| Capability | Priority chain | Final fallback |
| --- | --- | --- |
| Storage | cloud bucket → database → local disk | in-memory |
| Messaging | cloud endpoint → local broker | in-memory |
| Caching | cloud/Redis → local disk | in-memory |
| Search | cloud endpoint → local index | in-memory |
| Logging | cloud endpoint → local file | in-memory |

Partial or malformed detected configuration fails fast. Unconfigured providers
are skipped. The selected strategies are visible from the Live health endpoint
and included in telemetry attributes.

## Observability

Compose starts `grafana/otel-lgtm` and exports invocation spans over OTLP/gRPC.
Open Grafana at `http://localhost:3000`; ports `4317` and `4318` accept OTLP
gRPC and HTTP. Set `OTEL_EXPORTER_OTLP_ENDPOINT` to use another collector.

## Evaluation and tests

The repository includes a smoke evaluation only as a regression check for the
generic runtime; it is not the product behavior:

```bash
uv run python -m basic_agent.evaluation
uv run pytest -q
```

## CI/CD

GitHub Actions runs on pushes to `main` and on pull requests through
`.github/workflows/ci.yml`. The pipeline tests Python 3.10 through 3.13,
builds the shared application image, and checks:

- all Python tests;
- evaluation, realm, and configuration JSON fixtures;
- the evaluation entry point;
- Docker Compose interpolation and service configuration; and
- patch whitespace errors.
- the production Dockerfile build.

The workflow intentionally does not call Gemini, Keycloak, or external
providers. Network-backed evaluation and deployment should be separate
environment-protected workflows with production credentials.

## ADK capability status

| Status | Capability | Generic implementation |
| --- | --- | --- |
| [x] | Agent/model/instructions | Externalized `AGENT_*` settings drive one root Agent. |
| [x] | Tools | Function, Search, code execution, MCP, OpenAPI, integration, approval, and retrieval are configurable. |
| [x] | Structured output | Optional `GenericAgentResponse` contract. |
| [x] | Sessions/state/artifacts/memory | ADK service URIs are supplied by Compose. |
| [x] | REST/A2A/Live | Existing ADK REST/A2A and Live endpoints use the same root Agent. |
| [x] | Keycloak authorization | JWT validation, configurable roles, and Traefik ForwardAuth. |
| [x] | OTEL-LGTM | Local spans exported to Grafana/Tempo/Loki/Prometheus stack. |
| [x] | Auto-configuration | Storage, Messaging, Caching, Search, and Logging fallback chains. |
| [x] | Container reuse | One configurable application image across Python services. |
| [ ] | Production cloud deployment | `deploy/cloudrun/service.yaml` is a starter manifest and still requires environment-specific image, identity, secrets, storage, and endpoints. |

See the [Google ADK documentation](https://google.github.io/adk-docs/) for the
framework reference.
