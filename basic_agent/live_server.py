"""WebSocket adapter for the existing release-readiness root agent."""

from __future__ import annotations

import asyncio
import os
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from google.adk.agents.live_request_queue import LiveRequestQueue
from google.adk.agents.run_config import RunConfig, StreamingMode
from google.adk.memory import InMemoryMemoryService
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from .agent import ReleaseReadinessPlugin, root_agent
from .autoconfig import discover_capabilities


APP_NAME = "basic_agent"
LIVE_MODEL = os.getenv("ADK_MODEL", "gemini-3.1-flash-live-preview")

app = FastAPI(
    title="Release Readiness Live API",
    description="Bidirectional ADK Live API access to the existing root agent.",
    version="0.1.0",
)
session_service = InMemorySessionService()
memory_service = InMemoryMemoryService()
capabilities = discover_capabilities()


async def _session(user_id: str, session_id: str | None):
    """Return an existing live session or create one for the WebSocket."""
    if session_id:
        existing = await session_service.get_session(
            app_name=APP_NAME, user_id=user_id, session_id=session_id
        )
        if existing:
            return existing
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
    async for event in runner.run_live(
        user_id=user_id,
        session_id=session_id,
        live_request_queue=queue,
        run_config=RunConfig(
            response_modalities=[types.Modality.TEXT],
            streaming_mode=StreamingMode.BIDI,
        ),
    ):
        await websocket.send_json(_event_payload(event))


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
    """Handle JSON text/audio messages and stream ADK events back as JSON."""
    await websocket.accept()
    user_id = websocket.query_params.get("user_id", "live-user")
    session_id = websocket.query_params.get("session_id")
    session = await _session(user_id, session_id)
    queue = LiveRequestQueue()
    runner = Runner(
        agent=root_agent,
        app_name=APP_NAME,
        session_service=session_service,
        memory_service=memory_service,
        plugins=[ReleaseReadinessPlugin()],
    )
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
            message = await websocket.receive_json()
            if text := message.get("text"):
                queue.send_content(
                    types.Content(
                        role="user", parts=[types.Part.from_text(text=text)]
                    )
                )
            elif audio := message.get("audio"):
                queue.send_realtime(
                    types.Blob(
                        mime_type=audio.get("mime_type", "audio/pcm;rate=16000"),
                        data=audio["data"],
                    )
                )
            elif message.get("activity") == "start":
                queue.send_activity_start()
            elif message.get("activity") == "end":
                queue.send_activity_end()
            elif message.get("close"):
                break
    except WebSocketDisconnect:
        pass
    finally:
        queue.close()
        if event_task:
            event_task.cancel()
