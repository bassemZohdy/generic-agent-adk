"""Authenticated ADK API-server wrapper with subject-bound sessions."""

from __future__ import annotations

import contextlib
import json
import os
import re
import secrets
import sys
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from ..auth.core import authenticate_request
from ..config.settings import settings
from ..util import is_production

_RUN_PATHS = {"/run", "/run_sse"}
_ANONYMOUS_COOKIE = "adk_anonymous_id"
_ANONYMOUS_TOKEN = re.compile(r"^[A-Za-z0-9_-]{16,128}$")


def _subject(claims: dict[str, Any] | None) -> str:
    return str(claims.get("sub")) if claims and claims.get("sub") else "anonymous"


def _anonymous_subject(request: Request) -> tuple[str, str | None]:
    """Return a per-client subject when authentication is intentionally disabled.

    A shared literal ``anonymous`` subject would let every unauthenticated
    client read or mutate the same ADK sessions.  The cookie is only a
    namespacing mechanism (AUTH_DISABLED is still explicitly unauthenticated),
    and is marked secure in production deployments.
    """
    token = request.cookies.get(_ANONYMOUS_COOKIE, "")
    if not _ANONYMOUS_TOKEN.fullmatch(token):
        token = secrets.token_urlsafe(24)
        return f"anonymous:{token}", token
    return f"anonymous:{token}", None


def _path_user_id(path: str) -> str | None:
    parts = path.strip("/").split("/")
    try:
        index = parts.index("users")
    except ValueError:
        return None
    return parts[index + 1] if len(parts) > index + 1 else None


class SubjectBindingMiddleware(BaseHTTPMiddleware):
    """Authenticate each REST request and bind every ADK user ID to ``sub``."""

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Any]]
    ):
        if request.url.path in {"/health", "/version"}:
            return await call_next(request)

        try:
            claims = authenticate_request(
                request, required_roles=settings.keycloak_required_roles
            )
        except Exception as error:  # noqa: BLE001 - auth boundary returns API errors
            status = getattr(error, "status_code", 503)
            detail = getattr(error, "detail", "Authentication failed")
            return JSONResponse(status_code=status, content={"detail": detail})

        anonymous_cookie: str | None = None
        if settings.auth_disabled:
            user_id, anonymous_cookie = _anonymous_subject(request)
        else:
            user_id = _subject(claims)
        requested_path_user = _path_user_id(request.url.path)
        if requested_path_user and requested_path_user != user_id:
            return JSONResponse(
                status_code=403,
                content={
                    "detail": "user_id must match the authenticated token subject"
                },
            )

        if request.url.path in _RUN_PATHS:
            try:
                payload = await request.json()
            except (json.JSONDecodeError, UnicodeDecodeError):
                payload = None
            if isinstance(payload, dict):
                requested_user = payload.get("user_id")
                if requested_user and requested_user != user_id:
                    if settings.auth_disabled:
                        payload["user_id"] = user_id
                    else:
                        return JSONResponse(
                            status_code=403,
                            content={
                                "detail": "user_id must match the authenticated token subject"
                            },
                        )
                elif requested_user is None:
                    payload["user_id"] = user_id
                request._body = json.dumps(payload).encode("utf-8")

        request.state.auth_claims = claims or {}
        request.state.auth_subject = user_id
        response = await call_next(request)
        if anonymous_cookie is not None:
            response.set_cookie(
                _ANONYMOUS_COOKIE,
                anonymous_cookie,
                httponly=True,
                secure=is_production(settings.deployment),
                samesite="strict",
                max_age=86400,
            )
        return response


def create_app():
    """Build the ADK API app and install identity binding before serving it."""
    from google.adk.cli.fast_api import get_fast_api_app

    # ``.adk`` works for local CLI runs and resolves to ``/app/.adk`` in the
    # container because the image's working directory is ``/app``.
    data_dir = Path(os.environ.get("ADK_DATA_DIR", ".adk")).expanduser()
    data_dir.mkdir(parents=True, exist_ok=True)
    artifact_dir = data_dir / "artifacts"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    database_uri = os.environ.get("ADK_SESSION_SERVICE_URI") or os.environ.get(
        "DATABASE_URL"
    )
    artifact_uri = os.environ.get("ADK_ARTIFACT_SERVICE_URI")
    if not artifact_uri and os.environ.get("STORAGE_BUCKET"):
        artifact_uri = f"gs://{os.environ['STORAGE_BUCKET'].strip()}/adk-artifacts"
    memory_uri = os.environ.get("ADK_MEMORY_SERVICE_URI")
    if is_production(settings.deployment) and not database_uri:
        raise ValueError(
            "Production REST deployments require ADK_SESSION_SERVICE_URI or DATABASE_URL "
            "for shared session persistence"
        )
    agents_dir = str(Path(__file__).parent)
    app = get_fast_api_app(
        agents_dir=agents_dir,
        session_service_uri=database_uri or f"sqlite:///{data_dir / 'api-sessions.db'}",
        artifact_service_uri=artifact_uri or artifact_dir.resolve().as_uri(),
        memory_service_uri=memory_uri or "memory://",
        web=False,
        a2a=True,
        auto_create_session=False,
        extra_plugins=["basic_agent.agent.GenericAgentPlugin"],
    )
    # ADK prepends ``agents_dir`` to sys.path while importing agent modules.
    # This repository has ``interfaces/mcp.py``; leaving that directory first
    # shadows the third-party ``mcp`` package for later tool construction.
    with contextlib.suppress(ValueError):
        sys.path.remove(agents_dir)
    imported_mcp = sys.modules.get("mcp")
    if imported_mcp is not None and str(
        getattr(imported_mcp, "__file__", "")
    ).startswith(agents_dir):
        sys.modules.pop("mcp", None)
    if is_production(settings.deployment):
        documentation_paths = {
            "/openapi.json",
            "/docs",
            "/docs/oauth2-redirect",
            "/redoc",
        }
        app.router.routes = [
            route
            for route in app.router.routes
            if getattr(route, "path", None) not in documentation_paths
        ]
    app.add_middleware(SubjectBindingMiddleware)
    return app


app = create_app()
