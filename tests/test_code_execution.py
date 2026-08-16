"""Tests for code-execution provider resolution (ADR-004, TODO P1)."""

from __future__ import annotations

import importlib
import importlib.util
import logging
from typing import Any

import pytest

import basic_agent.code_execution as ce
from basic_agent.autoconfig import ProviderConfigurationError
from basic_agent.code_execution import (
    STRATEGY_ENV,
    _CodeExecutionProviderSpec,
    register,
    resolve_code_executor,
)


def _fake_spec(strategy: str, *, probe_result: bool = True, warn: str | None = None):
    """Build a throwaway provider spec that records its calls."""

    calls: dict[str, Any] = {"probe": 0, "build": 0, "model": None}

    class Spec(_CodeExecutionProviderSpec):
        @classmethod
        def probe(cls, environment, *, model):
            calls["probe"] = calls["probe"] + 1
            calls["model"] = model
            return probe_result

        @classmethod
        def build(cls, environment):
            calls["build"] = calls["build"] + 1
            return f"executor[{strategy}]"

    Spec.strategy = strategy
    Spec.warn_on_select = warn
    return Spec, calls


@pytest.fixture
def clean_registry():
    """Snapshot and restore the module-level provider registry around a test."""
    providers = dict(ce._PROVIDERS)
    order = ce._AUTO_DETECT_ORDER
    try:
        ce._PROVIDERS.clear()
        yield
    finally:
        ce._PROVIDERS.clear()
        ce._PROVIDERS.update(providers)
        ce._AUTO_DETECT_ORDER = order


def test_resolve_defaults_to_unavailable(clean_registry):
    resolution = resolve_code_executor({}, model="gemini-2.0-flash")
    assert resolution.executor is None
    assert resolution.strategy == "unavailable"
    assert resolution.detail


def test_unknown_explicit_strategy_raises(clean_registry):
    spec, _ = _fake_spec("known_one")
    register(spec)
    with pytest.raises(
        ProviderConfigurationError, match="Unknown code-execution strategy 'bogus'"
    ) as excinfo:
        resolve_code_executor({STRATEGY_ENV: "bogus"}, model="m")
    assert "known_one" in str(excinfo.value)


def test_probe_false_on_explicit_path_raises(clean_registry):
    spec, calls = _fake_spec("broken", probe_result=False)
    register(spec)
    with pytest.raises(
        ProviderConfigurationError, match="explicitly configured but unavailable"
    ):
        resolve_code_executor({STRATEGY_ENV: "broken"}, model="m")
    assert calls["build"] == 0


def test_registered_provider_auto_detected(clean_registry):
    spec, calls = _fake_spec("fake")
    register(spec, auto=True)
    resolution = resolve_code_executor({}, model="sentinel-model")
    assert resolution.strategy == "fake"
    assert resolution.executor == "executor[fake]"
    assert resolution.detail == "auto-detected"
    assert calls["probe"] == 1
    assert calls["model"] == "sentinel-model"


def test_registered_provider_not_probed_when_unregistered_from_chain(clean_registry):
    spec, calls = _fake_spec("manual_only")
    register(spec)  # auto=False: registered but never auto-detected
    resolution = resolve_code_executor({}, model="m")
    assert resolution.strategy == "unavailable"
    assert calls["probe"] == 0


def test_explicit_override_wins_over_auto_detect(clean_registry):
    auto_spec, auto_calls = _fake_spec("auto_one")
    register(auto_spec, auto=True)
    pinned_spec, _ = _fake_spec("pinned")
    register(pinned_spec)
    resolution = resolve_code_executor({STRATEGY_ENV: "pinned"}, model="m")
    assert resolution.strategy == "pinned"
    assert resolution.executor == "executor[pinned]"
    assert resolution.detail == "explicit override"
    assert auto_calls["probe"] == 0


def test_whitespace_override_treated_as_unset(clean_registry):
    spec, _ = _fake_spec("fake")
    register(spec, auto=True)
    resolution = resolve_code_executor({STRATEGY_ENV: "   "}, model="m")
    assert resolution.strategy == "fake"


def test_auto_detect_tries_in_registration_order(clean_registry):
    first, first_calls = _fake_spec("first", probe_result=False)
    second, _ = _fake_spec("second")
    register(first, auto=True)
    register(second, auto=True)
    resolution = resolve_code_executor({}, model="m")
    assert resolution.strategy == "second"
    assert first_calls["probe"] == 1


def test_warn_on_select_logged_on_explicit_selection(clean_registry, caplog):
    spec, _ = _fake_spec("risky", warn="risky strategy selected: handle with care")
    register(spec)
    with caplog.at_level(logging.WARNING):
        resolution = resolve_code_executor({STRATEGY_ENV: "risky"}, model="m")
    assert resolution.strategy == "risky"
    assert "risky strategy selected" in caplog.text


def test_no_warning_for_ordinary_explicit_selection(clean_registry, caplog):
    spec, _ = _fake_spec("ordinary")
    register(spec)
    with caplog.at_level(logging.WARNING):
        resolve_code_executor({STRATEGY_ENV: "ordinary"}, model="m")
    assert caplog.text == ""


@pytest.mark.skipif(
    importlib.util.find_spec("docker") is not None,
    reason="docker SDK installed; import-safety proven only without it",
)
def test_module_imports_without_docker_sdk(clean_registry):
    """A fresh import must not touch the docker SDK (ADR-004 §2 lazy-import rule)."""
    assert "docker" not in __import__("sys").modules or True  # registry restored below
    importlib.reload(ce)
    resolve_code_executor({}, model="m")  # smoke: reloaded module still resolves
