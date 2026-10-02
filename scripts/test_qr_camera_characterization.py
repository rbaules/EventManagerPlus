"""Contrato QR-3B previo a QR-KIOSK-0B; no modifica producción."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.qr_scanner_service import is_camera_transient


def main() -> int:
    source = (ROOT / "views" / "home_view.py").read_text(encoding="utf-8")
    runtime = (ROOT / "services" / "qr_camera_runtime.py").read_text(encoding="utf-8")
    for marker in (
        "QrCameraRuntime",
        "generation",
        "snapshot_task",
        "controller_initialized",
        "preview_paused",
        "def invalidate",
    ):
        assert marker in runtime, marker
    for marker in ("qr_scanner_lifecycle_lock", "persistent_camera_host", "qr finalizer", "take_picture end"):
        assert marker in source, marker
    assert is_camera_transient(RuntimeError("cameraNotReadable"))
    assert is_camera_transient(RuntimeError("cameraAbort"))
    assert "camera is not initialized. call initialize() first." in source.lower()
    for marker in (
        "qr_runtime.controller_initialized",
        "qr_runtime.preview_paused",
        'def _scanner_state_change(event: fcam.CameraStateEvent)',
        'qr_runtime.preview_paused = bool(event.is_preview_paused)',
        'qr_runtime.preview_paused = True',
        'qr_runtime.preview_paused = False',
        'if not camera_initialized or not qr_runtime.controller_initialized:',
        'if not _controller_camera_no_inicializado(ex):',
        'print("[QR-SCAN][INFO] Camera controller already uninitialized during Home cleanup")',
        'if event.has_error:',
        'elif event.is_initialized:',
        'state["qr_scanner_camera_state"] = "paused" if event.is_preview_paused else "initialized"',
        'state["qr_scanner_camera_state"] = "closing"',
        'state["qr_scanner_camera_state"] = "error"',
    ):
        assert marker in source, marker
    assert '"qr_scanner_camera_initialized"' not in source
    assert '"qr_scanner_preview_paused"' not in source
    print("OK - QR camera characterization contract preserved.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
