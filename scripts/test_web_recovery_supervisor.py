from __future__ import annotations

import contextlib
import io
import sys
import warnings
from pathlib import Path

from starlette.exceptions import StarletteDeprecationWarning


warnings.filterwarnings(
    "ignore",
    message="Using `httpx` with `starlette.testclient` is deprecated.*",
    category=StarletteDeprecationWarning,
)
from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import asgi  # noqa: E402
from services.webclient_telemetry import (  # noqa: E402
    MAX_TELEMETRY_BODY_BYTES,
    TELEMETRY_EVENTS,
    LOGGER,
)


VALID_PAYLOAD = {
    "event": "HEALTH_OK",
    "client_recovery_id": "recovery_20260905",
    "timestamp": "2026-09-05T12:00:00.000Z",
    "path": "/app/llegadas",
    "elapsed_seconds": 3.125,
}


def assert_assets_and_flet_index_contract() -> None:
    index = (ROOT / "assets" / "index.html").read_text(encoding="utf-8")
    script = (ROOT / "assets" / "recovery_supervisor.js").read_text(
        encoding="utf-8"
    )
    assert "<!-- fletAppConfig -->" in index
    assert 'src="recovery_supervisor.js"' in index
    assert "main.dart.js" not in script
    assert 'fetch("/health"' in script
    assert 'window.location.reload()' in script
    assert 'path === "/auth/callback"' in script
    assert 'path.startsWith("/app/")' in script
    assert 'credentials: "omit"' in script
    assert "Working..." not in script


def assert_diagnostic_endpoint_contract() -> None:
    stream = io.StringIO()
    handler = __import__("logging").StreamHandler(stream)
    LOGGER.addHandler(handler)
    LOGGER.setLevel("INFO")
    try:
        with TestClient(asgi.app) as client:
            accepted = client.post(
                "/diagnostics/web-recovery",
                json=VALID_PAYLOAD,
            )
            assert accepted.status_code == 204 and accepted.content == b""

            for event in TELEMETRY_EVENTS:
                response = client.post(
                    "/diagnostics/web-recovery",
                    json={**VALID_PAYLOAD, "event": event},
                )
                assert response.status_code == 204

            assert client.post(
                "/diagnostics/web-recovery",
                json={**VALID_PAYLOAD, "event": "ARBITRARY"},
            ).status_code == 422
            assert client.post(
                "/diagnostics/web-recovery",
                json={**VALID_PAYLOAD, "email": "person@example.com"},
            ).status_code == 422
            assert client.post(
                "/diagnostics/web-recovery",
                json={**VALID_PAYLOAD, "path": "/auth/callback"},
            ).status_code == 422
            assert client.post(
                "/diagnostics/web-recovery",
                content=b"{" + b"x" * MAX_TELEMETRY_BODY_BYTES + b"}",
                headers={"Content-Type": "application/json"},
            ).status_code == 413
            assert client.post(
                "/diagnostics/web-recovery",
                content=b"not-json",
                headers={"Content-Type": "application/json"},
            ).status_code == 400

            health = client.get("/health")
            assert health.status_code == 200
            assert health.json() == {"status": "ok"}

            root = client.get("/")
            assert root.status_code == 200
            assert "recovery_supervisor.js" in root.text
            script_response = client.get("/recovery_supervisor.js")
            assert script_response.status_code == 200
            assert "javascript" in script_response.headers["content-type"]

        routes = {getattr(route, "path", "") for route in asgi.app.routes}
        assert "/health" in routes
        assert "/diagnostics/web-recovery" in routes
        assert any(getattr(route, "path", None) == "" for route in asgi.app.routes)
        assert "person@example.com" not in stream.getvalue()
        assert "[WEBCLIENT][HEALTH_OK]" in stream.getvalue()
    finally:
        LOGGER.removeHandler(handler)


if __name__ == "__main__":
    assert_assets_and_flet_index_contract()
    assert_diagnostic_endpoint_contract()
    print("OK - web recovery assets, telemetry validation, health and Flet routes passed.")
