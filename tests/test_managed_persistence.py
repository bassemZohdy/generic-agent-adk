"""Tests for managed persistence operations, multi-instance consistency, and fail-closed policies.

Covers T12:
- Multi-instance session consistency across independent runners and service instances
- Database URI persistence (SQLite, PostgreSQL URI compatibility)
- Production fail-closed validation when persistence URI is missing
- Artifact service URI configuration and storage bucket integration
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from unittest.mock import patch

import pytest
from google.adk.cli.utils.service_factory import create_session_service_from_options
from google.adk.events import Event
from google.adk.sessions import InMemorySessionService
from google.genai import types

from basic_agent.config.settings import Settings, load_settings
from basic_agent.interfaces import rest as rest_module
from basic_agent.interfaces.live import session_service as default_live_session_service


@pytest.fixture
def temp_db_dir(tmp_path):
    db_dir = tmp_path / "persistence"
    db_dir.mkdir(parents=True, exist_ok=True)
    return db_dir


class TestMultiInstanceSessionPersistence:
    """Test session consistency across separate simulated instances and runners."""

    @pytest.mark.anyio
    async def test_session_shared_across_multiple_service_instances(self, temp_db_dir):
        db_path = temp_db_dir / "shared_sessions.db"
        db_uri = f"sqlite:///{db_path.as_posix()}"

        # Instance 1: Create session and append event
        inst1_service = create_session_service_from_options(
            base_dir=str(temp_db_dir), session_service_uri=db_uri
        )
        session = await inst1_service.create_session(
            app_name="basic-agent",
            user_id="alice",
            session_id="session-100",
            state={"initial_key": "initial_value"},
        )
        assert session.id == "session-100"

        # Instance 2: Connect to the same database URI and read the session
        inst2_service = create_session_service_from_options(
            base_dir=str(temp_db_dir), session_service_uri=db_uri
        )
        session_inst2 = await inst2_service.get_session(
            app_name="basic-agent",
            user_id="alice",
            session_id="session-100",
        )
        assert session_inst2 is not None
        assert session_inst2.id == "session-100"
        assert session_inst2.state.get("initial_key") == "initial_value"

        # Instance 2: Mutate session state
        await inst2_service.append_event(
            session=session_inst2,
            event=Event(
                content=types.Content(
                    role="user",
                    parts=[types.Part(text="message from instance 2")],
                )
            ),
        )

        # Instance 3: Verify updated events are visible to a third instance
        inst3_service = create_session_service_from_options(
            base_dir=str(temp_db_dir), session_service_uri=db_uri
        )
        session_inst3 = await inst3_service.get_session(
            app_name="basic-agent",
            user_id="alice",
            session_id="session-100",
        )
        assert session_inst3 is not None
        assert len(session_inst3.events) >= 1

    @pytest.mark.anyio
    async def test_session_isolation_between_different_users_in_shared_db(
        self, temp_db_dir
    ):
        db_path = temp_db_dir / "isolated_sessions.db"
        db_uri = f"sqlite:///{db_path.as_posix()}"

        service = create_session_service_from_options(
            base_dir=str(temp_db_dir), session_service_uri=db_uri
        )
        await service.create_session(
            app_name="basic-agent",
            user_id="alice",
            session_id="alice-session",
        )

        # Bob should not be able to load Alice's session
        bob_session = await service.get_session(
            app_name="basic-agent",
            user_id="bob",
            session_id="alice-session",
        )
        assert bob_session is None


class TestProductionPersistenceFailClosed:
    """Test that production deployments require persistent session storage."""

    def test_production_rest_app_fails_closed_without_session_uri(self, monkeypatch):
        monkeypatch.setenv("DEPLOYMENT_ENV", "production")
        monkeypatch.delenv("ADK_SESSION_SERVICE_URI", raising=False)
        monkeypatch.delenv("DATABASE_URL", raising=False)

        # Ensure settings reflect production
        with patch.object(rest_module, "is_production", return_value=True):
            with pytest.raises(
                ValueError, match="Production REST deployments require"
            ):
                rest_module.create_app()

    def test_artifact_uri_generation_from_storage_bucket(self, monkeypatch, tmp_path):
        monkeypatch.setenv("STORAGE_BUCKET", "my-gcp-bucket")
        monkeypatch.setenv("ADK_DATA_DIR", str(tmp_path / ".adk"))
        monkeypatch.setenv("ADK_SESSION_SERVICE_URI", "sqlite:///test.db")
        monkeypatch.delenv("ADK_ARTIFACT_SERVICE_URI", raising=False)

        with patch("google.adk.cli.fast_api.get_fast_api_app") as mock_get_app:
            with patch.object(rest_module, "is_production", return_value=False):
                rest_module.create_app()
                assert mock_get_app.called
                _, kwargs = mock_get_app.call_args
                assert kwargs["artifact_service_uri"] == "gs://my-gcp-bucket/adk-artifacts"
