---
name: status-check
description: Use when the user asks about this agent's runtime configuration, health, or which capabilities/tools are currently active.
---

# Status Check

1. Call the `inspect_runtime` tool to read the active configuration and detected capability strategies (model, enabled tools, storage/cache/search backends).
2. If a configured-service status tool is available (an `openapi`-prefixed tool calling the service API's `/status` endpoint), call it too and report both results together.
3. Summarize the model, enabled tools, and capability strategies in plain language for the user — do not dump raw JSON.
