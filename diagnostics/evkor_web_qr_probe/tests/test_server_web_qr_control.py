"""Contract checks for the server-side custom-control transport spike."""

from pathlib import Path
import sys


PACKAGE_SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(PACKAGE_SRC))

from evkor_web_qr_probe import EvkorServerWebQrProbe  # noqa: E402
from views.server_web_qr_control_view import (  # noqa: E402
    SERVER_WEB_QR_CONTROL_ROUTE,
    SERVER_WEB_QR_TEST_EVENT,
    ServerWebQrProbeSession,
    is_server_web_qr_control_route,
)


def test_server_wrapper_is_registered() -> None:
    control = EvkorServerWebQrProbe()

    assert control._c == "EvkorServerWebQrProbe"
    assert "on_qr_detected" in EvkorServerWebQrProbe.__annotations__
    assert "on_scanner_state" in EvkorServerWebQrProbe.__annotations__


def test_server_route_and_event_contract() -> None:
    assert SERVER_WEB_QR_CONTROL_ROUTE == "/diagnostics/server-web-qr-control"
    assert SERVER_WEB_QR_TEST_EVENT == "SERVER_WEB_QR_TEST"
    assert is_server_web_qr_control_route(SERVER_WEB_QR_CONTROL_ROUTE)
    assert is_server_web_qr_control_route(f"{SERVER_WEB_QR_CONTROL_ROUTE}/?source=test")
    assert not is_server_web_qr_control_route("/kiosk")


def test_server_qr_counter_keeps_raw_value_only_in_page_state() -> None:
    session = ServerWebQrProbeSession()

    assert session.accept_qr("  QR-123  ") == "QR-123"
    assert session.qr_count == 1
    assert session.last_qr == "QR-123"
    assert session.accept_qr("") is None
    assert session.qr_count == 1
