"""Contract tests for the Python half of the isolated custom control."""

from pathlib import Path
import sys

import flet as ft


PACKAGE_SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(PACKAGE_SRC))

from evkor_web_qr_probe import EvkorWebQrProbe  # noqa: E402


def test_wrapper_is_registered_with_its_dart_control_name() -> None:
    control = EvkorWebQrProbe()

    assert control._c == "EvkorWebQrProbe"
    assert control.label == "EVKOR Web QR Control"


def test_wrapper_delivers_qr_state_metrics_and_error_callbacks() -> None:
    received: dict[str, list[str]] = {key: [] for key in ("qr", "state", "metrics", "error")}
    control = EvkorWebQrProbe(
        on_qr_detected=lambda event: received["qr"].append(event.data),
        on_scanner_state=lambda event: received["state"].append(event.data),
        on_scanner_metrics=lambda event: received["metrics"].append(event.data),
        on_scanner_error=lambda event: received["error"].append(event.data),
    )

    control.on_qr_detected(ft.Event(name="qr_detected", data="QR-123", control=control))
    control.on_scanner_state(ft.Event(name="scanner_state", data="camera_active", control=control))
    control.on_scanner_metrics(ft.Event(name="scanner_metrics", data="attempts=1", control=control))
    control.on_scanner_error(ft.Event(name="scanner_error", data="permission_denied", control=control))

    assert received == {
        "qr": ["QR-123"],
        "state": ["camera_active"],
        "metrics": ["attempts=1"],
        "error": ["permission_denied"],
    }


def test_camera_start_precedes_optional_detector_setup() -> None:
    scanner = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "flutter"
        / "evkor_web_qr_probe"
        / "lib"
        / "src"
        / "web_qr_scanner.dart"
    ).read_text(encoding="utf-8")

    start = scanner.index("Future<void> _start()")
    detector = scanner.index("Future<void> _startDetector")
    stream = scanner.index("getUserMedia", start)

    assert stream < detector
    assert "await _startDetector(started);" in scanner[start:detector]
    assert '_reportDetectorCapability("unavailable")' in scanner
