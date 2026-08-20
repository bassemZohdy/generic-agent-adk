# Configuration reference

The runtime resolves `/app/config/agent.yaml` (or `AGENT_CONFIG_FILE`) first,
then applies explicit environment overrides. YAML is strict: unknown fields and
wrong scalar/container types fail at startup with the field path.

## YAML shape

```yaml
agent:
  use_case: assistant                # required
  name: optional-root-name
  description: optional-description
model:
  provider: google                   # google or litellm-compatible provider
  name: gemini-3.6-flash
  api_key: ${OPTIONAL_API_KEY}
  base_url: ${OPTIONAL_BASE_URL}
instructions:
  value: operator instructions
  file: /app/config/instructions.md   # UTF-8; appended to value (relative paths use process cwd)
tools:
  enabled: [knowledge, runtime]      # [] intentionally disables all tools
  mcp: {enabled: false, tools: [], prefix: mcp_}
  openapi: {enabled: false, url: http://service-api:8001, path: /status, title: Service API, prefix: api_}
  skills: {enabled: false, dir: /app/skills, prefix: ""}
execution:
  max_iterations: 3
  require_approval: false
  steps: 3
  workers: 3
  specialists: [research, solution, risk]
  code_execution: {strategy: "", docker_host: "", docker_image: ""}
output:
  schema: GenericAgentResponse
  key: last_response
state:
  enabled: true
roles:
  research:
    instruction: research-only role prompt
    model: gemini-3.6-flash
    tools: [knowledge]
```

`tools.enabled` omitted means the environment defaults; an explicit empty list
means no tools. OpenAPI, skills, MCP, and Application Integration are opt-in.
Role tool names are resolved through the same factory and safety policy as root
tools. Unknown names and unsupported output schemas fail before an agent starts.

To use the Docker-backed sandbox with Compose, include `code_execution` in
`AGENT_TOOLS` and start the `code-exec` profile. The profile supplies the
scoped Docker socket proxy and defaults `AGENT_CODE_EXECUTION_DOCKER_HOST` to
`tcp://code-exec-socket-proxy:2375`; the application image includes the
Docker SDK but does not activate it unless the resolver selects the Docker
strategy.

Set `AGENT_CODE_EXECUTION_STRATEGY` to pin a provider, or leave it empty for
ordered capability detection. Docker-specific overrides are
`AGENT_CODE_EXECUTION_DOCKER_HOST` and
`AGENT_CODE_EXECUTION_DOCKER_IMAGE`; the YAML equivalents are under
`execution.code_execution`. The image should be digest-pinned in production.
`unsafe_local` executes in the application process and is not a sandbox.

## Interfaces and ports

Compose publishes host ports from environment variables. The defaults below
are convenience values, not required host assignments. `*_BIND_ADDRESS`
controls the host interface; change both settings when exposing a service on a
different interface.

| Component | Host variables | Container variable | Default host / container port |
|---|---|---:|---:|
| REST/A2A API through Traefik | `ADK_API_BIND_ADDRESS`, `ADK_API_PORT` | `ADK_API_CONTAINER_PORT` | `8002 / 8002` |
| Live WebSocket through Traefik | `LIVE_API_BIND_ADDRESS`, `LIVE_API_PORT` | `LIVE_API_CONTAINER_PORT` | `8003 / 8003` |
| Keycloak | `KEYCLOAK_BIND_ADDRESS`, `KEYCLOAK_PORT` | `KEYCLOAK_CONTAINER_PORT` | `8080 / 8080` |
| Demo service API (`demo` profile) | `AGENT_SERVICE_API_BIND_ADDRESS`, `AGENT_SERVICE_API_PORT` | `AGENT_SERVICE_API_CONTAINER_PORT` | `8001 / 8001` |
| Authentication gateway (internal only) | — | `AUTH_GATEWAY_CONTAINER_PORT` | `8010` |
| Grafana (`observability` profile) | `GRAFANA_BIND_ADDRESS`, `GRAFANA_PORT` | image listener | `3000 / 3000` |
| OTLP gRPC (`observability` profile) | `OTLP_BIND_ADDRESS`, `OTLP_GRPC_PORT` | image listener | `4317 / 4317` |
| OTLP HTTP (`observability` profile) | `OTLP_BIND_ADDRESS`, `OTLP_HTTP_PORT` | image listener | `4318 / 4318` |

Host and container ports are independent for the application, API, Live,
Keycloak, and demo services. The authentication gateway is internal-only and
has no host mapping. Grafana and OTLP use fixed listeners supplied by the
observability image; their `*_PORT` variables change only the published host
side. Compose service URLs use the container variables, so changing a host
port does not change URLs such as `http://keycloak:${KEYCLOAK_CONTAINER_PORT}`
or `http://service-api:${AGENT_SERVICE_API_CONTAINER_PORT}`. Cloud Run is
different: its platform-provided `PORT` controls the container listener, and
local Compose port variables do not apply. For a process running outside
Compose, update public URLs such as `KEYCLOAK_ISSUER` and
`AGENT_SERVICE_API_URL` yourself when their corresponding host ports change.

## Environment overrides and limits

`AGENT_USE_CASE`, `ADK_MODEL`, `AGENT_INSTRUCTION`, `AGENT_TOOLS`,
`AGENT_MAX_ITERATIONS`, and `AGENT_SPECIALISTS` override the corresponding YAML
fields. `AUTH_DISABLED=true` is accepted only for local/test deployments.
Production REST deployments require `ADK_SESSION_SERVICE_URI` or `DATABASE_URL`.

Knowledge input is capped by `AGENT_KNOWLEDGE_MAX_FILE_BYTES` (default 2 MiB)
and `AGENT_KNOWLEDGE_MAX_RESULT_BYTES` (default 64 KiB). Live JSON frames and
decoded audio are bounded by `LIVE_MAX_MESSAGE_BYTES` and `LIVE_MAX_AUDIO_BYTES`.

See [.env.example](../.env.example) for the complete environment list and
[ADR-004](ADR-004-pluggable-code-execution.md) for sandbox configuration.
