"""Contrato QR-3B previo a QR-KIOSK-0B; no modifica producción."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.qr_scanner_service import is_camera_transient
from services.qr_camera_runtime import QrCameraRuntime


def main() -> int:
    source = (ROOT / "views" / "home_view.py").read_text(encoding="utf-8")
    runtime = (ROOT / "services" / "qr_camera_runtime.py").read_text(encoding="utf-8")
    for marker in (
        "QrCameraRuntime",
        "generation",
        "snapshot_task",
        "controller_initialized",
        "preview_paused",
        "lifecycle_lock",
        "camera_description",
        "def invalidate",
    ):
        assert marker in runtime, marker
    for marker in ("qr_runtime.lifecycle_lock", "persistent_camera_host", "qr finalizer", "take_picture end"):
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

    # QR-KIOSK-0B3B-1B: cada runtime es dueño de un único lock, sin compartirlo
    # con otro Home/runtime. Home sólo consume la instancia del runtime.
    runtime_one = QrCameraRuntime()
    runtime_two = QrCameraRuntime()
    assert runtime_one.lifecycle_lock is not runtime_two.lifecycle_lock
    assert runtime.count("asyncio.Lock()") == 1
    assert source.count("qr_runtime.lifecycle_lock") == 4
    assert '"qr_scanner_lifecycle_lock"' not in source
    for marker in (
        'async with lock:',
        'await lock.acquire()',
        'await camera.resume_preview()',
        'await camera.pause_preview()',
        'await camera.stop_image_stream()',
        'await polling_task',
        'async def take_snapshot()',
        'return await camera.take_picture()',
        'def _reintentar_scanner_qr() -> None:',
        'abrir_scanner_qr()',
    ):
        assert marker in source, marker
    cleanup = source[source.index("async def _limpiar_camera_scanner"):source.index("def cerrar_scanner_qr")]
    assert cleanup.index("await polling_task") < cleanup.index("await camera.pause_preview()")
    snapshot_polling = source[source.index("async def iniciar_captura"):source.index("async def inicializar")]
    assert "lifecycle_lock" not in snapshot_polling
    initialization = source[source.index("async def inicializar()"):source.index("def _reintentar_scanner_qr")]
    assert (
        initialization.index('print("[QR-SCAN][LIFECYCLE] resume_preview lock released")')
        < initialization.index("recovery_from_resume = True")
        < initialization.index("await lock.acquire()")
    )

    # QR-KIOSK-0B3B-2B: la descripción es una única caché técnica del runtime.
    # Se crea tras enumeración y se reutiliza exclusivamente durante recovery
    # por controller perdido; no se invalida ni se recupera desde teardown.
    assert runtime_one.camera_description is None
    assert source.count("qr_runtime.camera_description") == 2
    for marker in (
        'description = qr_runtime.camera_description if recovery_from_resume else None',
        'print("[QR-SCAN][LIFECYCLE] Reusing cached CameraDescription for recovery")',
        'enumerate_cameras_with_retry(',
        'qr_runtime.camera_description = description',
        'await camera.initialize(',
        'if not is_camera_transient(ex) or initialize_attempt == initialize_attempts:',
    ):
        assert marker in source, marker
    assert '"qr_scanner_description"' not in source
    teardown = source[source.index("def _desmontar_scanner_overlay"):source.index("def _log_identidad_scanner")]
    assert "recovery_from_resume" not in teardown
    assert "buscar_qr_llegadas" not in initialization
    print("OK - QR camera characterization contract preserved.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
