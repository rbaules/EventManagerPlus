"""Contract checks for the server-side custom-control transport spike."""

from pathlib import Path
import sys


PACKAGE_SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(PACKAGE_SRC))

from evkor_web_qr_probe import EvkorServerWebQrProbe  # noqa: E402
from views.server_web_qr_control_view import (  # noqa: E402
    SERVER_WEB_QR_CONTROL_ROUTE,
    SERVER_WEB_QR_TEST_EVENT,
    is_server_web_qr_control_route,
)


def test_server_wrapper_is_registered() -> None:
    control = EvkorServerWebQrProbe()

    assert control._c == "EvkorServerWebQrProbe"


def test_server_route_and_event_contract() -> None:
    assert SERVER_WEB_QR_CONTROL_ROUTE == "/diagnostics/server-web-qr-control"
    assert SERVER_WEB_QR_TEST_EVENT == "SERVER_WEB_QR_TEST"
    assert is_server_web_qr_control_route(SERVER_WEB_QR_CONTROL_ROUTE)
    assert is_server_web_qr_control_route(f"{SERVER_WEB_QR_CONTROL_ROUTE}/?source=test")
    assert not is_server_web_qr_control_route("/kiosk")
