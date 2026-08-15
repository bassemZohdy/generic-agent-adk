"""Tests for multi-provider model resolution (models.resolve_model)."""

from __future__ import annotations

import logging

from google.adk.models.lite_llm import LiteLlm

from basic_agent import models
from basic_agent.models import resolve_model


def test_native_passthrough_for_google_providers():
    for provider in ("google", "gemini", "Gemini", ""):
        result = resolve_model("gemini-2.0-flash", provider=provider)
        assert result == "gemini-2.0-flash"
        assert not isinstance(result, LiteLlm)


def test_prefix_rule_wins_over_provider():
    result = resolve_model("openai/gpt-4o")
    assert isinstance(result, LiteLlm)
    assert result.model == "openai/gpt-4o"


def test_provider_rule_builds_litellm():
    result = resolve_model("gpt-4o", provider="openai")
    assert isinstance(result, LiteLlm)
    assert result.model == "openai/gpt-4o"


def test_anthropic_provider():
    result = resolve_model("claude-3-5-sonnet-latest", provider="anthropic")
    assert isinstance(result, LiteLlm)
    assert result.model == "anthropic/claude-3-5-sonnet-latest"


def test_ollama_base_url_passed_through():
    result = resolve_model("llama3", provider="ollama")
    assert isinstance(result, LiteLlm)
    assert result.model == "ollama/llama3"

    with_url = resolve_model(
        "llama3", provider="ollama", base_url="http://localhost:11434"
    )
    assert isinstance(with_url, LiteLlm)
    assert with_url.model == "ollama/llama3"
    assert with_url._additional_args.get("base_url") == "http://localhost:11434"


def test_api_key_passed_through():
    result = resolve_model("gpt-4o", provider="openai", api_key="sk-test")
    assert isinstance(result, LiteLlm)
    assert result._additional_args.get("api_key") == "sk-test"


def test_missing_env_key_warns_once(monkeypatch, caplog):
    models._warned.clear()
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    caplog.set_level(logging.WARNING, logger="basic_agent.models")

    resolve_model("gpt-4o", provider="openai")
    assert "OPENAI_API_KEY" in caplog.text

    caplog.clear()
    resolve_model("gpt-4o", provider="openai")
    assert "OPENAI_API_KEY" not in caplog.text  # once per process


def test_no_warning_for_google(monkeypatch, caplog):
    models._warned.clear()
    caplog.set_level(logging.WARNING, logger="basic_agent.models")
    result = resolve_model("gemini-2.0-flash", provider="google")
    assert result == "gemini-2.0-flash"
    assert caplog.text == ""
