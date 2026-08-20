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
