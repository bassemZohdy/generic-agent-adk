"""Comprehensive authenticated REST and Live WebSocket interface integration matrix.

Covers T02, T18, and T19:
- Authenticated REST requests, token verification, role enforcement, and IDOR protection
- Anonymous subject namespacing and cookie persistence under auth_disabled
- Live WebSocket authentication paths (header, subprotocol, and first-frame JSON)
- Session isolation, ownership validation, disconnect, reconnect, and resume
- Bounded message limits, payload validation, and atomic rate limiting
- Transport error handling and clean disconnects
"""

from __future__ import annotations

import base64
from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI, WebSocketDisconnect
from fastapi.testclient import TestClient
from starlette.requests import Request

from basic_agent import auth
from basic_agent.interfaces import live as live_module
from basic_agent.interfaces import rest as rest_module


@pytest.fixture(scope="module")
def rsa_keypair():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key()
    return private_key, public_key


@pytest.fixture
def mock_jwks(rsa_keypair, monkeypatch):
    _, public_key = rsa_keypair

    class FakeJwksClient:
        def get_signing_key_from_jwt(self, _token):
            return SimpleNamespace(key=public_key)

    monkeypatch.setattr(auth.core, "_jwks_client", lambda _url: FakeJwksClient())


def make_token(
    rsa_keypair,
    sub: str = "user-123",
    roles: tuple[str, ...] = ("agent-user",),
    issuer: str = "https://keycloak.example/realms/basic-agent",
    audience: str = "basic-agent",
) -> str:
    private_key, _ = rsa_keypair
    return jwt.encode(
        {
            "sub": sub,
            "iss": issuer,
            "aud": audience,
            "realm_access": {"roles": list(roles)},
        },
        private_key,
        algorithm="RS256",
    )


# ── REST Interface Tests ──────────────────────────────────────────────────────


class TestRestAuthenticatedMatrix:
    """REST interface authentication, identity binding, and IDOR protection matrix."""

    @pytest.fixture
    def rest_app(self, settings_patch):
        # Create a test FastAPI app with SubjectBindingMiddleware
        app = FastAPI()

        @app.get("/health")
        def health():
            return {"status": "ok"}

        @app.get("/version")
        def version():
            return {"version": "0.1.0"}

        @app.post("/run")
        async def run(request: Request):
            body = await request.json()
            return {
                "user_id": body.get("user_id"),
                "auth_subject": getattr(request.state, "auth_subject", None),
            }

        @app.get("/users/{user_id}/sessions")
        async def get_user_sessions(user_id: str, request: Request):
            return {
                "user_id": user_id,
                "auth_subject": getattr(request.state, "auth_subject", None),
            }

        app.add_middleware(rest_module.SubjectBindingMiddleware)
        return app

    def test_health_and_version_bypass_auth(self, rest_app, settings_patch):
        settings_patch(
            rest_module,
            auth_disabled=False,
            keycloak_issuer="https://keycloak.example/realms/basic-agent",
        )
        client = TestClient(rest_app)

        res_health = client.get("/health")
        assert res_health.status_code == 200
        assert res_health.json() == {"status": "ok"}

        res_version = client.get("/version")
        assert res_version.status_code == 200
        assert res_version.json() == {"version": "0.1.0"}

    def test_missing_auth_header_fails(self, rest_app, settings_patch):
        settings_patch(
            rest_module,
            auth_disabled=False,
            keycloak_issuer="https://keycloak.example/realms/basic-agent",
        )
        client = TestClient(rest_app)
        res = client.post("/run", json={"message": "hello"})
        assert res.status_code == 401

    def test_authenticated_run_injects_and_binds_subject(
        self, rest_app, settings_patch, rsa_keypair, mock_jwks
    ):
        settings_patch(
            rest_module,
            auth_disabled=False,
            keycloak_issuer="https://keycloak.example/realms/basic-agent",
            keycloak_audience="basic-agent",
            keycloak_required_roles=("agent-user",),
        )
        token = make_token(rsa_keypair, sub="alice")
        client = TestClient(rest_app)

        # Without user_id in payload, middleware injects subject
        res = client.post(
            "/run",
            json={"message": "hello"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res.status_code == 200
        assert res.json()["user_id"] == "alice"
        assert res.json()["auth_subject"] == "alice"

    def test_authenticated_run_rejects_idor_mismatched_user(
        self, rest_app, settings_patch, rsa_keypair, mock_jwks
    ):
        settings_patch(
            rest_module,
            auth_disabled=False,
            keycloak_issuer="https://keycloak.example/realms/basic-agent",
            keycloak_audience="basic-agent",
            keycloak_required_roles=("agent-user",),
        )
        token = make_token(rsa_keypair, sub="alice")
        client = TestClient(rest_app)

        # Attacker tries to execute as bob
        res = client.post(
            "/run",
            json={"user_id": "bob", "message": "exploit"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res.status_code == 403
        assert "user_id must match" in res.json()["detail"]

    def test_authenticated_path_user_id_mismatch_rejected(
        self, rest_app, settings_patch, rsa_keypair, mock_jwks
    ):
        settings_patch(
            rest_module,
            auth_disabled=False,
            keycloak_issuer="https://keycloak.example/realms/basic-agent",
            keycloak_audience="basic-agent",
            keycloak_required_roles=("agent-user",),
        )
        token = make_token(rsa_keypair, sub="alice")
        client = TestClient(rest_app)

        # Accessing /users/bob/sessions with alice's token
        res = client.get(
            "/users/bob/sessions",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res.status_code == 403

        # Accessing /users/alice/sessions succeeds
        res_ok = client.get(
            "/users/alice/sessions",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res_ok.status_code == 200
        assert res_ok.json()["user_id"] == "alice"

    def test_auth_disabled_isolated_anonymous_cookie(self, rest_app, settings_patch):
        settings_patch(
            rest_module,
            auth_disabled=True,
            deployment="development",
        )
        client = TestClient(rest_app)

        # First request without cookie gets assigned a fresh cookie
        res1 = client.post("/run", json={"message": "first"})
        assert res1.status_code == 200
        cookie = res1.cookies.get("adk_anonymous_id")
        assert cookie is not None
        subject1 = res1.json()["auth_subject"]
        assert subject1 == f"anonymous:{cookie}"

        # Second request with the same cookie preserves subject
        res2 = client.post(
            "/run", json={"message": "second"}, cookies={"adk_anonymous_id": cookie}
        )
        assert res2.status_code == 200
        assert res2.json()["auth_subject"] == subject1


# ── Live WebSocket Interface Tests ────────────────────────────────────────────


class TestLiveWebSocketMatrix:
    """Live WebSocket transport authentication, limits, rate limiting, and reconnect tests."""

    @pytest.fixture
    def live_client(self, settings_patch):
        # Configure live app settings for tests
        settings_patch(
            live_module,
            auth_disabled=False,
            keycloak_issuer="https://keycloak.example/realms/basic-agent",
            keycloak_audience="basic-agent",
            keycloak_required_roles=("agent-user",),
            live_api_roles=("agent-user",),
            live_max_messages_per_minute=5,
            live_max_message_bytes=1024,
            live_max_audio_bytes=2048,
        )
        settings_patch(
            auth.core,
            auth_disabled=False,
            keycloak_issuer="https://keycloak.example/realms/basic-agent",
            keycloak_audience="basic-agent",
            keycloak_required_roles=("agent-user",),
            live_api_roles=("agent-user",),
        )
        return TestClient(live_module.app)

    def test_healthz_endpoint(self, live_client):
        res = live_client.get("/healthz")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "ok"
        assert "model" in data

    def test_websocket_auth_via_header_success(
        self, live_client, rsa_keypair, mock_jwks
    ):
        token = make_token(rsa_keypair, sub="carol")
        with live_client.websocket_connect(
            "/live",
            headers={"authorization": f"Bearer {token}"},
        ) as ws:
            session_msg = ws.receive_json()
            assert session_msg.get("type") == "session"
            assert "session_id" in session_msg
            ws.send_json({"close": True})

    def test_websocket_auth_via_subprotocol_success(
        self, live_client, rsa_keypair, mock_jwks
    ):
        token = make_token(rsa_keypair, sub="dave")
        subprotocol = f"bearer,{token}"
        with live_client.websocket_connect(
            "/live",
            subprotocols=[subprotocol],
        ) as ws:
            session_msg = ws.receive_json()
            assert session_msg.get("type") == "session"
            assert "session_id" in session_msg
            ws.send_json({"close": True})

    def test_websocket_auth_via_first_frame_success(
        self, live_client, rsa_keypair, mock_jwks
    ):
        token = make_token(rsa_keypair, sub="eve")
        with live_client.websocket_connect("/live") as ws:
            # Send auth as first frame
            ws.send_json({"type": "auth", "access_token": token})
            session_msg = ws.receive_json()
            assert session_msg.get("type") == "session"
            assert "session_id" in session_msg
            ws.send_json({"close": True})

    def test_websocket_first_frame_invalid_token_closed(
        self, live_client, rsa_keypair, mock_jwks
    ):
        with (
            pytest.raises(WebSocketDisconnect) as exc,
            live_client.websocket_connect("/live") as ws,
        ):
            ws.send_json({"type": "auth", "access_token": "invalid.token.here"})
            ws.receive_json()
        assert exc.value.code == 4401

    def test_websocket_first_frame_missing_auth_type_closed(
        self, live_client, rsa_keypair, mock_jwks
    ):
        with (
            pytest.raises(WebSocketDisconnect) as exc,
            live_client.websocket_connect("/live") as ws,
        ):
            ws.send_json({"text": "hello before authenticating"})
            ws.receive_json()
        assert exc.value.code == 4401

    def test_websocket_session_ownership_isolation(
        self, live_client, rsa_keypair, mock_jwks
    ):
        alice_token = make_token(rsa_keypair, sub="alice")
        bob_token = make_token(rsa_keypair, sub="bob")

        # 1. Alice connects and gets a session ID
        with live_client.websocket_connect(
            "/live",
            headers={"authorization": f"Bearer {alice_token}"},
        ) as ws:
            session_msg = ws.receive_json()
            alice_session_id = session_msg["session_id"]
            ws.send_json({"close": True})

        # 2. Alice reconnects with her session_id -> succeeds
        with live_client.websocket_connect(
            f"/live?session_id={alice_session_id}",
            headers={"authorization": f"Bearer {alice_token}"},
        ) as ws:
            resumed = ws.receive_json()
            assert resumed["session_id"] == alice_session_id
            ws.send_json({"close": True})

        # 3. Bob attempts to connect using Alice's session_id -> rejected with 4403
        with (
            pytest.raises(WebSocketDisconnect) as exc,
            live_client.websocket_connect(
                f"/live?session_id={alice_session_id}",
                headers={"authorization": f"Bearer {bob_token}"},
            ) as ws,
        ):
            ws.receive_json()
        assert exc.value.code == 4403

    def test_websocket_rate_limit_exceeded(self, live_client, rsa_keypair, mock_jwks):
        token = make_token(rsa_keypair, sub="rate-limited-user")
        with (
            pytest.raises(WebSocketDisconnect) as exc,
            live_client.websocket_connect(
                "/live",
                headers={"authorization": f"Bearer {token}"},
            ) as ws,
        ):
            ws.receive_json()  # session frame
            # Send more messages than allowed limit (limit is 5)
            for i in range(10):
                ws.send_json({"text": f"msg {i}"})
            ws.receive_json()
        assert exc.value.code == 4429

    def test_websocket_oversized_payload_rejected(
        self, live_client, rsa_keypair, mock_jwks
    ):
        token = make_token(rsa_keypair, sub="oversized-user")
        with (
            pytest.raises(WebSocketDisconnect) as exc,
            live_client.websocket_connect(
                "/live",
                headers={"authorization": f"Bearer {token}"},
            ) as ws,
        ):
            ws.receive_json()
            # Send text exceeding 1024 bytes
            ws.send_json({"text": "A" * 2048})
            ws.receive_json()
        assert exc.value.code == 1009

    def test_websocket_oversized_audio_rejected(
        self, live_client, rsa_keypair, mock_jwks
    ):
        token = make_token(rsa_keypair, sub="audio-user")
        huge_audio = base64.b64encode(b"0" * 4096).decode("utf-8")
        with (
            pytest.raises(WebSocketDisconnect) as exc,
            live_client.websocket_connect(
                "/live",
                headers={"authorization": f"Bearer {token}"},
            ) as ws,
        ):
            ws.receive_json()
            ws.send_json(
                {
                    "audio": {
                        "data": huge_audio,
                        "mime_type": "audio/pcm;rate=16000",
                    }
                }
            )
            ws.receive_json()
        assert exc.value.code in {1009, 1003}

    def test_websocket_invalid_json_frame_rejected(
        self, live_client, rsa_keypair, mock_jwks
    ):
        token = make_token(rsa_keypair, sub="json-user")
        with (
            pytest.raises(WebSocketDisconnect) as exc,
            live_client.websocket_connect(
                "/live",
                headers={"authorization": f"Bearer {token}"},
            ) as ws,
        ):
            ws.receive_json()
            ws.send_text("not a valid json")
            ws.receive_json()
        assert exc.value.code == 1003

    def test_websocket_unsupported_message_rejected(
        self, live_client, rsa_keypair, mock_jwks
    ):
        token = make_token(rsa_keypair, sub="unsupported-user")
        with (
            pytest.raises(WebSocketDisconnect) as exc,
            live_client.websocket_connect(
                "/live",
                headers={"authorization": f"Bearer {token}"},
            ) as ws,
        ):
            ws.receive_json()
            ws.send_json({"unknown_field": 123})
            ws.receive_json()
        assert exc.value.code == 1003

    def test_websocket_activity_start_and_end(
        self, live_client, rsa_keypair, mock_jwks
    ):
        token = make_token(rsa_keypair, sub="activity-user")
        with live_client.websocket_connect(
            "/live",
            headers={"authorization": f"Bearer {token}"},
        ) as ws:
            session_msg = ws.receive_json()
            assert session_msg.get("type") == "session"
            ws.send_json({"activity": "start"})
            ws.send_json({"activity": "end"})
            ws.send_json({"close": True})
