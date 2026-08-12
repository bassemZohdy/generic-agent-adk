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
uv run adk web
uv run adk run basic_agent
```

The entry point is `basic_agent/agent.py:root_agent`. It is one generic ADK
Agent whose tools are assembled from configuration. The agent does not create
domain-specific sub-agents or workflows.

## Run with Docker

```bash
cp .env.example .env
docker compose up --build
```

Compose builds one `${APP_IMAGE}` (default `basic-adk-agent:local`) and reuses
it for the Web, REST/A2A, Live, service-status, and auth-gateway containers.
Commands and environment are externalized per service. Keycloak, Traefik, and
Grafana/OTEL-LGTM remain infrastructure images.

One image does not mean one process: separate containers preserve protocol and
lifecycle isolation while loading the same generic `root_agent`.

Services:

- Web UI: `http://localhost:8000` (Keycloak bearer token required)
- ADK REST/A2A: `http://localhost:8002` (Keycloak bearer token required)
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
requires `agent-user` for the Web/API proxy, status API, and Live API.
Override `KEYCLOAK_REQUIRED_ROLES`, `AGENT_SERVICE_API_ROLES`, and `LIVE_API_ROLES`
with comma-separated roles. Role claims are configured by
`KEYCLOAK_ROLE_CLAIM`, defaulting to `realm_access.roles`.

`agent-operator` is available as a separate realm role for policies that
require human approval. Credentials and realm administration must be replaced
with managed secrets/configuration outside development.

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

## ADK capability status

| Status | Capability | Generic implementation |
| --- | --- | --- |
| [x] | Agent/model/instructions | Externalized `AGENT_*` settings drive one root Agent. |
| [x] | Tools | Function, Search, code execution, MCP, OpenAPI, integration, approval, and retrieval are configurable. |
| [x] | Structured output | Optional `GenericAgentResponse` contract. |
| [x] | Sessions/state/artifacts/memory | ADK service URIs are supplied by Compose. |
| [x] | REST/A2A/Web/Live | Existing ADK and Live endpoints use the same root Agent. |
| [x] | Keycloak authorization | JWT validation, configurable roles, and Traefik ForwardAuth. |
| [x] | OTEL-LGTM | Local spans exported to Grafana/Tempo/Loki/Prometheus stack. |
| [x] | Auto-configuration | Storage, Messaging, Caching, Search, and Logging fallback chains. |
| [x] | Container reuse | One configurable application image across Python services. |
| [ ] | Production cloud deployment | Cloud Run manifest still requires environment-specific image, identity, secrets, and endpoints. |

See the [Google ADK documentation](https://google.github.io/adk-docs/) for the
framework reference.
