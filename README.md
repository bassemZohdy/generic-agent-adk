# Basic ADK agent

A minimal conversational agent built with [Google's Agent Development Kit
(ADK)](https://google.github.io/adk-docs/).

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

## ADK feature checklist

The table below tracks the major Google ADK capabilities against this starter
repository. `Implemented` means the feature is present and usable here;
`Partial` means ADK provides it but this project only uses the default or a
minimal form; `Not yet` means it still needs to be added to this project.

| Status | ADK capability | Current project implementation |
| --- | --- | --- |
| - [x] | LLM agent | `root_agent` is a Google ADK `Agent`. |
| - [x] | Agent instructions | System behavior is defined with `instruction`. |
| - [x] | Agent description | The agent has a human-readable `description`. |
| - [x] | Gemini model integration | Uses configurable `gemini-3.6-flash` via `ADK_MODEL`. |
| - [x] | Custom function tools | Includes the deterministic `get_project_info` tool. |
| - [x] | Local ADK Web UI | Available with `adk web` or Docker Compose. |
| - [x] | ADK CLI execution | Supports `adk run basic_agent`. |
| - [x] | Environment configuration | `.env.example` documents API key and model settings. |
| - [x] | Containerization | Dockerfile and Compose configuration are included. |
| - [x] | Structured output / response schemas | `AgentResponse` enforces an `answer` and `used_project_tool` response shape. |
| - [x] | Multi-agent delegation | `root_agent` can delegate repository questions to `project_guide_agent`. |
| - [x] | Sequential workflows | `project_overview_workflow` gathers facts and then summarizes them. |
| - [x] | Parallel workflows | `project_parallel_workflow` analyzes structure and runtime setup concurrently. |
| - [x] | Loop workflows | `project_review_loop` runs bounded review/refinement iterations. |
| - [ ] | Custom agent classes | Uses the built-in `Agent` class only. |
| - [x] | Built-in Google Search tool | `research_agent` uses ADK's `google_search` tool for current/external information. |
| - [x] | Code execution tool | `analysis_agent` uses ADK's `BuiltInCodeExecutor` for calculations and data analysis. |
| - [ ] | Retrieval / RAG | No corpus, embeddings, or retriever is configured. |
| - [ ] | MCP tools | No MCP server or MCP toolset is connected. |
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
| - [ ] | Automated agent tests | No agent behavior tests are included yet. |
| - [ ] | Tracing / observability | No cloud telemetry, tracing, or dashboard integration is configured. |
| - [ ] | Authentication / authorization | The local Web UI has no application-level user authentication. |
| - [ ] | Cloud deployment | No Cloud Run, Agent Engine, GKE, or other cloud deployment configuration is included. |

For the full framework reference, see the [Google ADK documentation](https://google.github.io/adk-docs/).
