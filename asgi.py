from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("EVENTPLUS_ASGI", "true")

import flet as ft
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, RedirectResponse, Response

from app import main as eventplus_main
from config import (
    EVENTPLUS_SESSION_COOKIE_NAME,
    EVENTPLUS_SESSION_COOKIE_SAMESITE,
    EVENTPLUS_SESSION_COOKIE_SECURE,
)
from services.server_session_service import (
    EventPlusSessionMiddleware,
    InMemorySessionRepository,
    create_server_session_binding,
)
from services.webclient_telemetry import (
    log_webclient_telemetry,
    parse_webclient_telemetry,
)


session_repository = InMemorySessionRepository()
_QR_WEB_SPIKE_FILE = Path(__file__).resolve().parent / "assets" / "qr_web_spike.html"


def asgi_main(page: ft.Page) -> None:
    binding = create_server_session_binding(session_repository, page)
    eventplus_main(page, server_session_binding=binding)


flet_app = ft.run(
    asgi_main,
    assets_dir="assets",
    export_asgi_app=True,
)

app = FastAPI()


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/diagnostics/web-recovery", status_code=204)
async def web_recovery_diagnostic(request: Request) -> Response:
    payload = await parse_webclient_telemetry(request)
    log_webclient_telemetry(payload)
    return Response(status_code=204)


# Temporary isolated diagnostic route for evaluating the browser-only QR scanner.
@app.get("/diagnostics/qr-web-spike")
async def qr_web_spike() -> FileResponse:
    return FileResponse(_QR_WEB_SPIKE_FILE, media_type="text/html")


@app.get("/session/logout")
async def session_logout(request: Request) -> RedirectResponse:
    opaque_id = request.cookies.get(EVENTPLUS_SESSION_COOKIE_NAME)
    if opaque_id:
        session_repository.delete(opaque_id)
    response = RedirectResponse("/", status_code=303)
    response.delete_cookie(
        EVENTPLUS_SESSION_COOKIE_NAME,
        path="/",
        secure=EVENTPLUS_SESSION_COOKIE_SECURE,
        httponly=True,
        samesite=EVENTPLUS_SESSION_COOKIE_SAMESITE,
    )
    return response


app.mount("/", flet_app)
app.add_middleware(
    EventPlusSessionMiddleware,
    repository=session_repository,
)
