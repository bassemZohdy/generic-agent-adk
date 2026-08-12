# Release readiness ADK agent

A release-readiness coordinator built with [Google's Agent Development Kit
(ADK)](https://google.github.io/adk-docs/). It gathers project, external,
metrics, and operational evidence before returning a structured recommendation.

## Setup

Python 3.10+ and `uv` are recommended:

```bash
uv sync
cp .env.example .env
```

Add a Gemini API key to `.env`, or configure Google Cloud/Vertex AI
authentication using the ADK instructions.

## Run

Start the local ADK web UI from this directory:

```bash
uv run adk web
```

Select `basic_agent` in the UI. For a terminal session, use:

```bash
uv run adk run basic_agent
```

The agent entry point is `basic_agent/agent.py:root_agent`. Set `ADK_MODEL` to
override the default model.

## Run with Docker

Create `.env` from the example and add your API key:

```bash
cp .env.example .env
docker compose up --build
```

Compose builds one named application image, `${APP_IMAGE}` (default:
`basic-adk-agent:local`), and reuses it for the ADK Web, ADK REST/A2A, Live,
release API, and authentication-gateway containers. Their commands and
environment are externalized per service, so the containers remain isolated
without duplicating application images. Keycloak, Traefik, and the LGTM
observability stack continue to use their own infrastructure images.

One image does not mean one process: the Web UI and REST/A2A server both load
the same `root_agent`, but run as separate services because they have different
ports, protocols, and lifecycle requirements. This is why the Compose file can
still contain several `/app/basic_agent` references while Docker maintains one
application image.

Open http://localhost:8000 and select `basic_agent`. The container points ADK
directly at the single agent directory to avoid duplicate agent discovery. Set
`ADK_PORT` in `.env` to change the host port. The local OpenAPI service is
available at http://localhost:8001 and can be changed with `RELEASE_API_PORT`.
The ADK REST API is available at http://localhost:8002 and can be changed with
`ADK_API_PORT`.

Keycloak is available at http://localhost:8080. Compose imports the local
`basic-agent` realm with the development user `demo` / `demo`. Obtain a token
for the `basic-agent` client with:

```bash
curl -s -X POST http://localhost:8080/realms/basic-agent/protocol/openid-connect/token \
  -d client_id=basic-agent -d username=demo -d password=demo \
  -d grant_type=password
```

Send the returned access token as `Authorization: Bearer <token>` to the
release API, or as `?access_token=<token>` for a browser WebSocket connection
to `/live`. The internal release-status tool continues to use
`RELEASE_API_KEY` for service-to-service calls. The built-in ADK Web/API
servers are behind the Traefik `auth-proxy`, which validates every request
through the Keycloak-backed ForwardAuth service. The host ports remain 8000
(Web UI) and 8002 (ADK API), but the agent containers are not directly exposed.

The bidirectional Live API WebSocket is available at `ws://localhost:8003/live`
and can be changed with `LIVE_API_PORT`. Connect with optional `user_id` and
`session_id` query parameters, then send JSON messages such as
`{"text":"Is version 1.4 ready?"}`. Audio input can be sent as
`{"audio":{"mime_type":"audio/pcm;rate=16000","data":"<base64>"}}`;
ADK events, including streamed response parts, are returned as JSON. The Live
service uses the existing `root_agent` and defaults to
`gemini-3.1-flash-live-preview`.

The REST server exposes ADK's streaming response endpoints and A2A endpoint.
The container is also Cloud Run-compatible: replace the placeholders in
`deploy/cloudrun/service.yaml`, build and push the image, create the referenced
Secret Manager secret, then deploy the manifest with `gcloud run services
replace`.

## Auto-configuration fallback chain

At startup, the application discovers each subsystem independently and selects
the first provider whose prerequisites are satisfied. It does not require a
provider type flag or enum:

| Capability | Priority order | In-memory fallback |
| --- | --- | --- |
| Storage | `STORAGE_BUCKET` → `DATABASE_URL` → `STORAGE_PATH` | yes |
| Messaging | `MESSAGING_URL` → `BROKER_URL` | yes |
| Caching | `CACHE_URL`/`REDIS_URL` → `CACHE_PATH` | yes |
| Search | `SEARCH_URL` + `SEARCH_API_KEY` → `SEARCH_INDEX_PATH` | yes |
| Logging | `LOG_ENDPOINT` + `LOG_API_KEY` → `LOG_FILE` | yes |

The selected strategy is exposed in the Live API health response and logged by
the ADK plugin. A provider is considered detected as soon as any of its
identifying values are present. If detected configuration is incomplete or
malformed, startup raises `ProviderConfigurationError` instead of silently
downgrading to a weaker strategy. If no provider is detected, the capability
uses the in-memory implementation.

## Evaluation

Run the checked-in ADK evaluation set with configured Gemini credentials:

```bash
uv run python -m basic_agent.evaluation
uv run python -m basic_agent.evaluation --detailed
```

The entry point invokes the installed ADK evaluator with
`tests/eval/release_readiness.evalset.json` and its explicit metric
configuration in `tests/eval/eval_config.json`.

## Local OpenTelemetry observability

Compose starts the `grafana/otel-lgtm` development stack and exports ADK
invocation spans over OTLP/gRPC. Open [Grafana](http://localhost:3000) after
starting Compose; the default local ports are Grafana `3000`, OTLP/gRPC `4317`,
and OTLP/HTTP `4318`. The ADK plugin emits an invocation span with the selected
capability strategies. Override `OTEL_EXPORTER_OTLP_ENDPOINT` when the
collector runs outside Compose.

## Unified live example: release readiness

The main use case is a release-readiness assessment. Ask the agent:

> Is version 1.4 ready for release? Check the project requirements, current
> dependency information, test metrics, and live service status. Give me a
> recommendation with risks and next steps.

The coordinator runs the evidence-gathering branches in parallel, synthesizes
the results in sequence, then performs two bounded review/refinement passes:

```text
root_agent
└── release_readiness_workflow
    ├── release_evidence_workflow (parallel)
    │   ├── local RAG: release requirements and runbook
    │   ├── Google Search: current external findings
    │   ├── code execution: test metrics and pass rate
    │   └── MCP: live service and deployment status
    │   └── OpenAPI: documented release-status service
    ├── release_synthesis_agent
    └── release_review_loop (two iterations)
```

The final response follows `ReleaseReadinessReport` with a recommendation,
confidence, risks, evidence, and next steps. Local metrics and MCP status are
deterministic for repeatable development; Google Search requires a configured
API key and current network access.

## ADK feature checklist

The table below tracks the major Google ADK capabilities against this release-
readiness application. `Implemented` means the feature is present and usable here;
`Partial` means ADK provides it but this project only uses the default or a
minimal form; `Not yet` means it still needs to be added to this project.

| Status | ADK capability | Current project implementation |
| --- | --- | --- |
| - [x] | LLM agent | `root_agent` is a Google ADK `Agent`. |
| - [x] | Agent instructions | System behavior is defined with `instruction`. |
| - [x] | Agent description | The agent has a human-readable `description`. |
| - [x] | Gemini model integration | Uses configurable `gemini-3.6-flash` via `ADK_MODEL`. |
| - [x] | Custom function tools | Includes deterministic release-metrics and retrieval tools. |
| - [x] | Local ADK Web UI | Available with `adk web` or Docker Compose. |
| - [x] | ADK CLI execution | Supports `adk run basic_agent`. |
| - [x] | Environment configuration | `.env.example` documents API key and model settings. |
| - [x] | Containerization | Dockerfile and Compose configuration are included. |
| - [x] | Structured output / response schemas | `ReleaseReadinessReport` enforces recommendation, confidence, risks, evidence, and next steps. |
| - [x] | Multi-agent delegation | `root_agent` delegates release assessments to `release_readiness_workflow`. |
| - [x] | Sequential workflows | The release workflow gathers evidence, synthesizes it, and reviews the result. |
| - [x] | Parallel workflows | `release_evidence_workflow` gathers docs, web, metrics, and operations evidence concurrently. |
| - [x] | Loop workflows | `release_review_loop` runs two bounded review/refinement iterations. |
| - [x] | Custom agent classes | The existing root agent uses the `ReleaseReadinessAgent` specialization without adding another agent node. |
| - [x] | Built-in Google Search tool | `release_research_agent` uses ADK's `google_search` tool for current release risks. |
| - [x] | Code execution tool | `release_metrics_agent` uses `BuiltInCodeExecutor` for CI calculations. |
| - [x] | Retrieval / RAG | `release_knowledge_agent` retrieves release criteria and runbook passages. |
| - [x] | MCP tools | `release_operations_agent` connects to the bundled stdio MCP server through `McpToolset`. |
| - [x] | OpenAPI tools | `release_api_agent` calls the local FastAPI release-status API through `OpenAPIToolset`. |
| - [x] | Application Integration tools | `release_operations_agent` optionally loads `ApplicationIntegrationToolset` when GCP integration variables are configured. |
| - [x] | Tool authentication | The OpenAPI release service supports an optional `x-api-key` flow. |
| - [x] | Tool confirmation / approval | `request_release_approval` pauses before recording a release decision until confirmed. |
| - [x] | Sessions | Docker Compose configures a persistent SQLite session service under `.adk/sessions.db`. |
| - [x] | Persistent state | `ReleaseWorkflowState` types the evidence and draft keys shared by the workflow. |
| - [x] | Artifacts | Docker Compose configures ADK's local file artifact service under `.adk/artifacts`. |
| - [x] | Memory service | Completed sessions are added to ADK's configured memory service; Compose enables `memory://` for local operation. |
| - [x] | Streaming / Live API | REST streaming is available through ADK API Server, and `live-api` exposes a bidirectional WebSocket for text/audio input using the existing `root_agent`. |
| - [x] | A2A interoperability | The Compose ADK API server enables the ADK A2A endpoint for the existing root agent. |
| - [x] | REST API server | Compose exposes the same agent through `adk api_server` on port 8002. |
| - [x] | Callbacks | Root-agent before/after callbacks record assessment lifecycle events. |
| - [x] | Plugins | `ReleaseReadinessPlugin` is loaded by the ADK Web server for lifecycle logging. |
| - [x] | Evaluation datasets | The checked-in dataset and `python -m basic_agent.evaluation` command run the ADK evaluator with a tool-trajectory threshold. |
| - [x] | Automated agent tests | `tests/test_agent.py` covers the unified workflow structure, tools, and response contract. |
| - [x] | Tracing / observability | Compose runs `grafana/otel-lgtm`; the ADK plugin exports invocation spans over OTLP and Cloud Trace remains an optional deployment target. |
| - [x] | Authentication / authorization | Keycloak bearer JWTs protect the release API, Live WebSocket, ADK Web UI, and ADK REST/A2A API through the Traefik ForwardAuth gateway. |
| - [ ] | Cloud deployment | The Cloud Run manifest is a generic template; production image, service identity, secrets, and the release API endpoint still require deployment configuration. |
| - [x] | Stack-agnostic subsystem auto-configuration | `basic_agent.autoconfig` resolves Storage, Messaging, Caching, Search, and Logging through implicit cloud/local/in-memory fallback chains. |

For the full framework reference, see the [Google ADK documentation](https://google.github.io/adk-docs/).
