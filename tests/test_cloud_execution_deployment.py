"""Tests for cloud code-executor deployment reachability and sandbox resolution.

Covers T11:
- Vertex AI Code Interpreter extension resolution and credential probes
- Vertex AI Agent Engine sandbox resolution and parameter validation
- GKE Code Executor sandbox resolution, kubeconfig context handling, and job modes
- Explicit cloud strategy override error messaging and fallback semantics
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from basic_agent.autoconfig import ProviderConfigurationError
from basic_agent.execution.resolver import (
    AGENT_ENGINE_RESOURCE_ENV,
    GKE_KUBECONFIG_CONTEXT_ENV,
    GKE_KUBECONFIG_PATH_ENV,
    STRATEGY_ENV,
    VERTEX_RESOURCE_ENV,
    resolve_code_executor,
)
from fakes import install_fake_kubernetes


class TestCloudCodeExecutorResolution:
    """Test cloud sandbox resolution across Vertex AI, Agent Engine, and GKE."""

    def test_vertex_ai_explicit_strategy_success(self, monkeypatch):
        mock_vertex_cls = MagicMock()
        monkeypatch.setattr(
            "google.adk.code_executors.VertexAiCodeExecutor",
            mock_vertex_cls,
            raising=False,
        )
        env = {
            STRATEGY_ENV: "vertex_ai",
            VERTEX_RESOURCE_ENV: "projects/my-proj/locations/us-central1/extensions/code-interp",
        }
        res = resolve_code_executor(env, model="gemini-2.0-flash")
        assert res.strategy == "vertex_ai"
        assert "explicit override" in res.detail

    def test_vertex_ai_missing_resource_fails_explicitly(self):
        env = {STRATEGY_ENV: "vertex_ai"}
        with pytest.raises(ProviderConfigurationError) as exc:
            resolve_code_executor(env, model="gemini-2.0-flash")
        assert "vertex_ai" in str(exc.value)
        assert "unavailable" in str(exc.value)

    def test_agent_engine_sandbox_explicit_strategy_success(self, monkeypatch):
        mock_ae_cls = MagicMock()
        monkeypatch.setattr(
            "google.adk.code_executors.AgentEngineSandboxCodeExecutor",
            mock_ae_cls,
            raising=False,
        )
        env = {
            STRATEGY_ENV: "agent_engine_sandbox",
            AGENT_ENGINE_RESOURCE_ENV: "projects/my-proj/locations/us-central1/agentEngines/my-engine",
        }
        res = resolve_code_executor(env, model="gemini-2.0-flash")
        assert res.strategy == "agent_engine_sandbox"
        assert "explicit override" in res.detail

    def test_agent_engine_missing_resource_fails_explicitly(self):
        env = {STRATEGY_ENV: "agent_engine_sandbox"}
        with pytest.raises(ProviderConfigurationError) as exc:
            resolve_code_executor(env, model="gemini-2.0-flash")
        assert "agent_engine_sandbox" in str(exc.value)
        assert "unavailable" in str(exc.value)

    def test_gke_explicit_strategy_success(self, monkeypatch, tmp_path):
        install_fake_kubernetes(monkeypatch)
        mock_gke_cls = MagicMock()
        monkeypatch.setattr(
            "google.adk.code_executors.GkeCodeExecutor",
            mock_gke_cls,
            raising=False,
        )
        kubeconfig = tmp_path / "kubeconfig"
        kubeconfig.write_text("apiVersion: v1\nclusters: []\n", encoding="utf-8")
        env = {
            STRATEGY_ENV: "gke",
            GKE_KUBECONFIG_PATH_ENV: str(kubeconfig),
            GKE_KUBECONFIG_CONTEXT_ENV: "my-gke-context",
        }
        res = resolve_code_executor(env, model="gemini-2.0-flash")
        assert res.strategy == "gke"
        assert "explicit override" in res.detail

    def test_gke_missing_kubeconfig_file_fails_explicitly(self, monkeypatch):
        install_fake_kubernetes(monkeypatch)
        env = {
            STRATEGY_ENV: "gke",
            GKE_KUBECONFIG_PATH_ENV: "/non/existent/kubeconfig.yaml",
        }
        with pytest.raises(ProviderConfigurationError) as exc:
            resolve_code_executor(env, model="gemini-2.0-flash")
        assert "gke" in str(exc.value)
        assert "unavailable" in str(exc.value)

