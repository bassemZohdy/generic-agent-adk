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

Open http://localhost:8000 and select `basic_agent`. The container points ADK
directly at the single agent directory to avoid duplicate agent discovery. Set
`ADK_PORT` in `.env` to change the host port.

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
| - [ ] | Custom agent classes | Uses the built-in `Agent` class only. |
| - [x] | Built-in Google Search tool | `release_research_agent` uses ADK's `google_search` tool for current release risks. |
| - [x] | Code execution tool | `release_metrics_agent` uses `BuiltInCodeExecutor` for CI calculations. |
| - [x] | Retrieval / RAG | `release_knowledge_agent` retrieves release criteria and runbook passages. |
| - [x] | MCP tools | `release_operations_agent` connects to the bundled stdio MCP server through `McpToolset`. |
| - [ ] | OpenAPI tools | No OpenAPI specification is connected. |
| - [ ] | Application Integration tools | No Google Cloud Application Integration toolset is connected. |
| - [ ] | Tool authentication | No OAuth/API-key tool authentication flow is configured. |
| - [ ] | Tool confirmation / approval | No human approval callback is configured. |
| - [ ] | Sessions | Uses ADK defaults; no explicit persistent session service is configured. |
| - [ ] | Persistent state | No application state schema or state-backed workflow is implemented. |
| - [ ] | Artifacts | No artifact service or file-producing agent flow is implemented. |
| - [ ] | Memory service | No long-term memory or memory search is configured. |
| - [ ] | Streaming / Live API | No bidirectional streaming or voice agent is configured. |
| - [ ] | A2A interoperability | No A2A endpoint or remote agent integration is configured. |
| - [ ] | REST API server | Only the ADK Web UI is exposed; no dedicated API deployment is configured. |
| - [ ] | Callbacks | No before/after agent, model, or tool callbacks are implemented. |
| - [ ] | Plugins | No ADK plugin is registered. |
| - [ ] | Evaluation datasets | No ADK evaluation set or regression cases are included. |
| - [x] | Automated agent tests | `tests/test_agent.py` covers the unified workflow structure, tools, and response contract. |
| - [ ] | Tracing / observability | No cloud telemetry, tracing, or dashboard integration is configured. |
| - [ ] | Authentication / authorization | The local Web UI has no application-level user authentication. |
| - [ ] | Cloud deployment | No Cloud Run, Agent Engine, GKE, or other cloud deployment configuration is included. |

For the full framework reference, see the [Google ADK documentation](https://google.github.io/adk-docs/).
