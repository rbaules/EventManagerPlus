from __future__ import annotations

import importlib
import io
import logging
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import services.kiosk_diagnostic_log as diagnostic_log
from services.kiosk_diagnostic_log import LOGGER, kiosk_log
from services.web_reliability import PageWebTelemetry


class Page:
    route = "/kiosk?ignored=query"


def main() -> int:
    reloaded = importlib.reload(diagnostic_log)
    assert len(reloaded.LOGGER.handlers) == 1, "Reload must not duplicate logger handlers"
    old_handlers = list(LOGGER.handlers)
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    LOGGER.handlers[:] = [handler]
    LOGGER.setLevel(logging.INFO)
    LOGGER.propagate = False
    try:
        os.environ.pop("RENDER_INSTANCE_ID", None)
        os.environ.pop("RENDER_GIT_COMMIT", None)
        page = Page()
        web = PageWebTelemetry(page, page_id="PAGEA001")
        kiosk_log(page, "KIOSK-QR", "startup_begin", scanner_id=12, generation=3)
        kiosk_log(
            page,
            "KIOSK-CONFIRM",
            "success",
            guest_name="Ada Lovelace",
            guest_email="ada@example.test",
            qr_code="secret-qr-value",
            session_token="secret-token-value",
        )
        kiosk_log(None, "KIOSK-ROUTE", "event", camera_id=7)
        text = stream.getvalue()
        assert "[KIOSK-QR][startup_begin]" in text
        assert "page_id=PAGEA001" in text
        assert "render_instance=local git_commit=local route=/kiosk" in text
        assert "scanner_id=12 generation=3" in text
        assert "[KIOSK-ROUTE][event]" in text and "camera_id=7" in text
        assert "ignored=query" not in text
        assert "Ada" not in text and "example.test" not in text
        assert "secret-qr-value" not in text and "secret-token-value" not in text
        assert len(LOGGER.handlers) == 1
        assert web.page_id == "PAGEA001"
    finally:
        LOGGER.handlers[:] = old_handlers
    print("Kiosk diagnostic logging tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
