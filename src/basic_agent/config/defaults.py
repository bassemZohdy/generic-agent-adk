"""Single-source defaults shared by runtime configuration and tests."""

from __future__ import annotations

APP_VERSION = "0.1.0"
MODEL = "gemini-3.6-flash"
LIVE_MODEL = "gemini-3.1-flash-live-preview"
SERVICE_API_URL = "http://127.0.0.1:8001"
ENABLED_TOOLS = "knowledge,search,mcp,approval,runtime,structured_output"
MCP_TOOLS = "get_service_status"
MAX_ITERATIONS = 3
LIVE_MAX_MESSAGE_BYTES = 1_048_576
LIVE_MAX_AUDIO_BYTES = 786_432
LIVE_MAX_MESSAGES_PER_MINUTE = 60
