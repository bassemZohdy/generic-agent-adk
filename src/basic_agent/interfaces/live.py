"""WebSocket adapter for the generic configured root agent."""

from __future__ import annotations

import asyncio
import base64
import contextlib
import json
import logging
import os
import secrets
import time
from collections import deque
from threading import Lock
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from google.adk.agents.live_request_queue import LiveRequestQueue
from google.adk.agents.run_config import RunConfig, StreamingMode
from google.adk.memory import InMemoryMemoryService
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from ..agent import GenericAgentPlugin, get_root_agent
from ..auth.core import (
    authenticate_websocket,
    authenticate_websocket_token,
    roles_from_claims,
    websocket_auth_subprotocol,
)
from ..autoconfig import discover_capabilities
from ..config.settings import settings
from ..util import is_production

logger = logging.getLogger(__name__)
APP_NAME = settings.app_name
LIVE_MODEL = settings.live_model
_production = is_production(settings.deployment)

app = FastAPI(
    title="Generic Agent Live API",
    description="Bidirectional ADK Live API access to the configured root agent.",
    version=settings.app_version,
    docs_url=None if _production else "/docs",
    redoc_url=None if _production else "/redoc",
)
session_uri = os.environ.get("ADK_SESSION_SERVICE_URI") or os.environ.get(
    "DATABASE_URL"
)
if _production and not session_uri:
    raise ValueError(
        "Production Live deployments require ADK_SESSION_SERVICE_URI or DATABASE_URL "
        "for shared session persistence"
    )
if session_uri:
    from google.adk.cli.utils.service_factory import create_session_service_from_options

    session_service = create_session_service_from_options(
        base_dir=os.environ.get("ADK_DATA_DIR", ".adk"),
        session_service_uri=session_uri,
    )
else:
    session_service = InMemorySessionService()
memory_uri = os.environ.get("ADK_MEMORY_SERVICE_URI")
if memory_uri:
    from google.adk.cli.utils.service_factory import create_memory_service_from_options

    memory_service = create_memory_service_from_options(
        base_dir=os.environ.get("ADK_DATA_DIR", ".adk"),
        memory_service_uri=memory_uri,
    )
else:
    memory_service = InMemoryMemoryService()
capabilities = discover_capabilities()
_runner: Runner | None = None
_message_windows: dict[str, deque[float]] = {}
_message_windows_lock = Lock()


def _get_runner() -> Runner:
    """Share one runner and plugin instance across WebSocket connections."""
    global _runner
    if _runner is None:
        # The configured preset compiles to a graph Workflow root — the
        # runner must take it as a BaseNode (`node=`), not as an `agent=`.
        _runner = Runner(
            node=get_root_agent(),
            app_name=APP_NAME,
            session_service=session_service,
            memory_service=memory_service,
            plugins=[GenericAgentPlugin()],
        )
    return _runner


async def _session(user_id: str, session_id: str | None):
    """Return an existing live session or create one for the authenticated user."""
    if session_id:
        existing = await session_service.get_session(
            app_name=APP_NAME, user_id=user_id, session_id=session_id
        )
        if existing:
            return existing
        raise HTTPException(
            status_code=403,
            detail="session_id is not owned by the authenticated token subject",
        )
    return await session_service.create_session(
        app_name=APP_NAME, user_id=user_id, session_id=session_id
    )


def _event_payload(event: Any) -> dict[str, Any]:
    """Serialize ADK events, including base64-encoded audio blobs."""
    return event.model_dump(mode="json", exclude_none=True)


async def _forward_events(
    websocket: WebSocket,
    runner: Runner,
    queue: LiveRequestQueue,
    *,
    user_id: str,
    session_id: str,
) -> None:
    try:
        async for event in runner.run_live(
            user_id=user_id,
            session_id=session_id,
            live_request_queue=queue,
            run_config=RunConfig(
                response_modalities=[types.Modality.TEXT],
                streaming_mode=StreamingMode.BIDI,
            ),
        ):
            payload = _event_payload(event)
            if (
                len(json.dumps(payload).encode("utf-8"))
                > settings.live_max_message_bytes
            ):
                await websocket.close(
                    code=1009, reason="Outbound WebSocket message is too large"
                )
                return
            await websocket.send_json(payload)
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("Live event forwarding failed for user_id=%s", user_id)


def _message_is_rate_limited(subject: str) -> bool:
    """Apply the message budget per authenticated subject across connections."""
    with _message_windows_lock:
        timestamps = _message_windows.setdefault(subject, deque())
        now = time.monotonic()
        cutoff = now - 60.0
        # Bound the number of retained subjects when clients reconnect
        # frequently. The lock keeps eviction and admission atomic when
        # multiple ASGI workers share this process.
        for key, values in list(_message_windows.items()):
            while values and values[0] <= cutoff:
                values.popleft()
            if not values:
                _message_windows.pop(key, None)
        timestamps = _message_windows.setdefault(subject, deque())
        if len(timestamps) >= settings.live_max_messages_per_minute:
            return True
        timestamps.append(now)
        return False


async def _receive_json_message(websocket: WebSocket) -> dict[str, Any]:
    """Read a bounded JSON WebSocket frame."""
    raw = await websocket.receive_text()
    if len(raw.encode("utf-8")) > settings.live_max_message_bytes:
        await websocket.close(code=1009, reason="WebSocket message is too large")
        raise WebSocketDisconnect(code=1009)
    try:
        message = json.loads(raw)
    except json.JSONDecodeError as error:
        await websocket.close(code=1003, reason="Expected a JSON object")
        raise WebSocketDisconnect(code=1003) from error
    if not isinstance(message, dict):
        await websocket.close(code=1003, reason="Expected a JSON object")
        raise WebSocketDisconnect(code=1003)
    return message


@app.get("/healthz")
async def healthz() -> dict[str, object]:
    return {
        "status": "ok",
        "model": LIVE_MODEL,
        "capabilities": {
            name: provider.strategy for name, provider in capabilities.items()
        },
    }


@app.websocket("/live")
async def live(websocket: WebSocket) -> None:
    """Handle authenticated, bounded JSON text/audio messages."""
    claims: dict[str, Any] | None = None
    auth_subprotocol_info = websocket_auth_subprotocol(websocket)
    has_auth_header = bool(websocket.headers.get("authorization"))
    try:
        if settings.auth_disabled or has_auth_header or auth_subprotocol_info:
            claims = authenticate_websocket(
                websocket, required_roles=settings.live_api_roles
            )
            # Never echo `bearer,<token>` or `bearer.<token>`: the token must
            # not appear in the Sec-WebSocket-Protocol response header.  The
            # safe constant "bearer" is the value the client actually offered
            # for the comma form.
            subprotocol = auth_subprotocol_info[1] if auth_subprotocol_info else None
            await websocket.accept(subprotocol=subprotocol)
        else:
            # Browser clients can authenticate as their first frame.  Tokens are
            # deliberately never accepted in query parameters.
            await websocket.accept()
            auth_message = await _receive_json_message(websocket)
            if auth_message.get("type") != "auth" or not isinstance(
                auth_message.get("access_token"), str
            ):
                raise HTTPException(
                    status_code=401,
                    detail="First WebSocket message must authenticate",
                )
            claims = authenticate_websocket_token(auth_message["access_token"])
    except (HTTPException, WebSocketDisconnect) as error:
        reason = str(getattr(error, "detail", error))[:123]
        logger.warning("WebSocket authentication rejected: %s", reason)
        with contextlib.suppress(Exception):
            await websocket.close(code=4401, reason=reason)
        return
    except Exception:
        logger.exception("Unexpected WebSocket authentication failure")
        with contextlib.suppress(Exception):
            await websocket.close(code=1011, reason="WebSocket authentication failed")
        return

    if claims and claims.get("sub"):
        user_id = str(claims["sub"])
    elif settings.auth_disabled:
        # Never put all unauthenticated WebSocket clients in one shared ADK
        # namespace.  A cookie, when supplied by a browser, gives reconnects
        # continuity; otherwise each connection gets an isolated subject.
        cookie = getattr(websocket, "cookies", {}).get("adk_anonymous_id", "")
        user_id = (
            f"anonymous:{cookie}"
            if cookie and all(char.isalnum() or char in "_-" for char in cookie)
            else f"anonymous:{secrets.token_urlsafe(24)}"
        )
    else:
        user_id = "anonymous"
    session_id = websocket.query_params.get("session_id")
    try:
        session = await _session(user_id, session_id)
    except HTTPException as error:
        reason = str(error.detail)[:123]
        logger.warning("WebSocket session rejected sub=%s: %s", user_id, reason)
        with contextlib.suppress(Exception):
            await websocket.close(code=4403, reason=reason)
        return
    logger.info(
        "authenticated live connection sub=%s auth_method=%s roles=%s session_id=%s",
        user_id,
        claims.get("auth_method", "bearer") if claims else "disabled",
        sorted(roles_from_claims(claims)) if claims else [],
        session.id,
    )
    queue = LiveRequestQueue()
    runner = _get_runner()
    event_task = None
    try:
        event_task = asyncio.create_task(
            _forward_events(
                websocket,
                runner,
                queue,
                user_id=user_id,
                session_id=session.id,
            )
        )
        await websocket.send_json({"type": "session", "session_id": session.id})
        while True:
            message = await _receive_json_message(websocket)
            if _message_is_rate_limited(user_id):
                await websocket.close(
                    code=4429, reason="WebSocket message rate exceeded"
                )
                return
            if text := message.get("text"):
                if not isinstance(text, str):
                    await websocket.close(code=1003, reason="text must be a string")
                    return
                queue.send_content(
                    types.Content(role="user", parts=[types.Part.from_text(text=text)])
                )
            elif audio := message.get("audio"):
                if not isinstance(audio, dict) or not isinstance(
                    audio.get("data"), str
                ):
                    await websocket.close(
                        code=1003, reason="audio.data must be a string"
                    )
                    return
                if len(audio["data"]) > settings.live_max_audio_bytes:
                    await websocket.close(
                        code=1009, reason="Audio payload is too large"
                    )
                    return
                try:
                    decoded_audio = base64.b64decode(audio["data"], validate=True)
                except (ValueError, TypeError):
                    await websocket.close(code=1003, reason="audio.data must be base64")
                    return
                if len(decoded_audio) > settings.live_max_audio_bytes:
                    await websocket.close(
                        code=1009, reason="Audio payload is too large"
                    )
                    return
                mime_type = audio.get("mime_type", "audio/pcm;rate=16000")
                if not isinstance(mime_type, str) or not mime_type.lower().startswith(
                    "audio/"
                ):
                    await websocket.close(
                        code=1003, reason="audio.mime_type must be audio/*"
                    )
                    return
                queue.send_realtime(
                    types.Blob(
                        mime_type=mime_type,
                        data=audio["data"],
                    )
                )
            elif message.get("activity") == "start":
                queue.send_activity_start()
            elif message.get("activity") == "end":
                queue.send_activity_end()
            elif message.get("close"):
                break
            else:
                await websocket.close(code=1003, reason="Unsupported WebSocket message")
                return
    except WebSocketDisconnect:
        logger.info("Live connection closed sub=%s session_id=%s", user_id, session.id)
    except Exception:
        logger.exception(
            "Live connection failed sub=%s session_id=%s", user_id, session.id
        )
    finally:
        queue.close()
        if event_task:
            event_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await event_task
