from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("EVENTPLUS_ASGI", "true")

_PROJECT_ROOT = Path(__file__).resolve().parent
_CUSTOM_CONTROL_SOURCE = _PROJECT_ROOT / "diagnostics" / "evkor_web_qr_probe" / "src"
if str(_CUSTOM_CONTROL_SOURCE) not in sys.path:
    sys.path.insert(0, str(_CUSTOM_CONTROL_SOURCE))

# The committed server-side Flutter client is deliberately selected before Flet
# initializes its ASGI runtime.  A deployment can override this setting, but a
# clean process (including Render) needs no inherited local shell variables.
_SERVER_WEB_CLIENT_DIR = (
    _PROJECT_ROOT
    / "diagnostics"
    / "evkor_server_web_qr_client"
    / "deploy"
    / "server_web"
)
os.environ.setdefault("FLET_WEB_PATH", str(_SERVER_WEB_CLIENT_DIR))

import flet as ft
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, RedirectResponse, Response
from starlette.staticfiles import StaticFiles

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
_FLET_WEB_QR_PROBE_DIR = (
    Path(__file__).resolve().parent
    / "diagnostics"
    / "evkor_web_qr_probe"
    / "deploy"
    / "web"
)


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


@app.get("/diagnostics/flet-web-qr-probe", include_in_schema=False)
async def flet_web_qr_probe_redirect() -> RedirectResponse:
    return RedirectResponse("/diagnostics/flet-web-qr-probe/", status_code=307)


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


app.mount(
    "/diagnostics/flet-web-qr-probe",
    StaticFiles(directory=_FLET_WEB_QR_PROBE_DIR, html=True),
    name="flet-web-qr-probe",
)
app.mount("/", flet_app)
app.add_middleware(
    EventPlusSessionMiddleware,
    repository=session_repository,
)
