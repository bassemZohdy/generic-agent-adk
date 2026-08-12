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

Open http://localhost:8000 and select `basic_agent`. Set `ADK_PORT` in `.env`
to change the host port.
