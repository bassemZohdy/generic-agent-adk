"""Tests for the local MCP server exposing service status."""

import json

from basic_agent.interfaces.mcp import get_service_status


def test_get_service_status_returns_expected_shape():
    payload = json.loads(get_service_status())
    assert payload["service"] == "basic-adk-agent"
    assert payload["environment"] == "local"
    assert payload["status"] == "healthy"
    assert "version" in payload
    assert "deployment" in payload
