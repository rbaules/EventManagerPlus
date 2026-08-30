from __future__ import annotations

import io
import logging
import os
import sys
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.web_reliability import PageWebTelemetry  # noqa: E402


class Clock:
    def __init__(self) -> None:
        self.value = 10.0

    def __call__(self) -> float:
        return self.value


class FakePage:
    def __init__(self, route: str = "/app/dashboard") -> None:
        self.web = True
        self.platform = "android"
        self.width = 800
        self.height = 600
        self.route = route
        self.on_connect = None
        self.on_disconnect = None
        self.on_close = None
        self.on_error = None


def capture_logger() -> tuple[logging.Logger, io.StringIO]:
    stream = io.StringIO()
    logger = logging.getLogger(f"test.web.{id(stream)}")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    logger.addHandler(logging.StreamHandler(stream))
    return logger, stream


def main() -> int:
    os.environ.pop("RENDER_INSTANCE_ID", None)
    os.environ.pop("RENDER_GIT_COMMIT", None)
    logger, output = capture_logger()
    clock = Clock()
    page_a, page_b = FakePage(), FakePage("/app/llegadas")
    context = {
        "cuenta_actual": {"cuenta_id": 12},
        "evento_actual": {"evento_id": 34},
    }
    a = PageWebTelemetry(page_a, clock=clock, logger=logger)
    b = PageWebTelemetry(page_b, clock=clock, logger=logger)
    a.bind_session(lambda: True, lambda: context)
    b.bind_session(lambda: False, lambda: None)

    # Flet 0.85.3 lifecycle slots accept the callbacks used by app.main.
    page_a.on_connect = lambda event: a.connect()
    page_a.on_disconnect = lambda event: a.disconnect()
    page_a.on_close = lambda event: a.close()
    page_a.on_error = lambda event: a.error(event)
    assert all(
        callable(value)
        for value in (
            page_a.on_connect,
            page_a.on_disconnect,
            page_a.on_close,
            page_a.on_error,
        )
    )

    a.page_created()
    b.page_created()
    assert a.page_id != b.page_id
    page_a.on_disconnect(SimpleNamespace(data="secret@example.com"))
    clock.value += 18.4
    page_a.on_connect(SimpleNamespace())
    page_a.on_error(SimpleNamespace(data="secret@example.com token=abc"))
    page_a.on_close(SimpleNamespace())
    started = a.restore_start()
    clock.value += 0.25
    a.restore_result("OK", started)
    a.ready(restored_session=True)

    text = output.getvalue()
    assert text.count("[WEB][PAGE_CREATED]") == 2
    assert "disconnect_count=1" in text
    assert "connect_count=1" in text
    assert "reconnect=true disconnected_for=18.4" in text
    assert "render_instance=local git_commit=local" in text
    assert "[WEB][ERROR]" in text and "summary=unhandled_page_error" in text
    assert "[SESSION][RESTORE_START]" in text
    assert "[SESSION][RESTORE_OK]" in text
    assert "[WEB][READY]" in text
    assert "secret@example.com" not in text and "token=abc" not in text
    assert a.connect_count == 1 and a.disconnect_count == 1
    assert b.connect_count == 0 and b.disconnect_count == 0
    print("OK - PII-free Web reliability telemetry and Page isolation tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
