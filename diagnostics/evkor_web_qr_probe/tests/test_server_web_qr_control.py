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
    assert "on_lifecycle_action" in EvkorServerWebQrProbe.__annotations__
    assert EvkorServerWebQrProbe.__annotations__["active"] is bool
    assert EvkorServerWebQrProbe.__annotations__["detector_enabled"] is bool
    assert EvkorServerWebQrProbe.__annotations__["preview_visible"] is bool


def test_server_route_and_event_contract() -> None:
    assert SERVER_WEB_QR_CONTROL_ROUTE == "/diagnostics/server-web-qr-control"
    assert SERVER_WEB_QR_TEST_EVENT == "SERVER_WEB_QR_TEST"
    assert is_server_web_qr_control_route(SERVER_WEB_QR_CONTROL_ROUTE)
    assert is_server_web_qr_control_route(f"{SERVER_WEB_QR_CONTROL_ROUTE}/?source=test")
    assert not is_server_web_qr_control_route("/kiosk")


def test_server_qr_counter_keeps_raw_value_only_in_page_state() -> None:
    session = ServerWebQrProbeSession()

    assert session.accept_qr("QR-123") is None
    session.apply_action("start")
    assert session.accept_qr("  QR-123  ") == "QR-123"
    assert session.qr_count == 1
    assert session.last_qr == "QR-123"
    assert session.accept_qr("") is None
    assert session.qr_count == 1


def test_stream_lifecycle_keeps_camera_active_between_guests() -> None:
    session = ServerWebQrProbeSession()

    assert session.apply_action("start")
    assert (session.active, session.detector_enabled, session.preview_visible) == (True, True, True)
    assert session.accept_qr("QR-1") == "QR-1"
    assert session.active is True
    assert session.detector_enabled is False
    assert session.apply_action("hide_preview")
    assert session.active is True and session.preview_visible is False
    assert session.apply_action("next_guest")
    assert (session.generation, session.active, session.detector_enabled, session.preview_visible) == (1, True, True, True)
    assert session.apply_action("stop")
    assert (session.active, session.detector_enabled) == (False, False)


def test_dart_stream_metric_reads_live_video_tracks_and_reports_after_stop() -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "src/flutter/evkor_web_qr_probe/lib/src/web_qr_scanner.dart"
    ).read_text(encoding="utf-8")

    assert 'getVideoTracks().toDart.any((track) => track.readyState == "live")' in source
    cleanup = source.index("Future<void> _stopCamera")
    assert source.index("track.stop()", cleanup) < source.index("_stream = null", cleanup)
    assert source.index('widget.onState("stopped")', cleanup) < source.index("_reportMetrics();", cleanup)
