"""Contrato QR-3B previo a QR-KIOSK-0B; no modifica producción."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.qr_scanner_service import QrFrameGate, is_camera_transient
from services.qr_camera_runtime import QrCameraRuntime


def main() -> int:
    source = (ROOT / "views" / "home_view.py").read_text(encoding="utf-8")
    runtime = (ROOT / "services" / "qr_camera_runtime.py").read_text(encoding="utf-8")
    scanner_service = (ROOT / "services" / "qr_scanner_service.py").read_text(encoding="utf-8")
    for marker in (
        "QrCameraRuntime",
        "generation",
        "snapshot_task",
        "controller_initialized",
        "preview_paused",
        "lifecycle_lock",
        "camera_description",
        "def invalidate",
        "def is_scanner_session_current",
        "def accept_snapshot_code",
    ):
        assert marker in runtime, marker
    for marker in ("qr_runtime.lifecycle_lock", "persistent_camera_host", "qr finalizer"):
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
        'initialize_camera_with_retry(',
    ):
        assert marker in source, marker
    assert '"qr_scanner_description"' not in source
    teardown = source[source.index("def _desmontar_scanner_overlay"):source.index("def _log_identidad_scanner")]
    assert "recovery_from_resume" not in teardown
    assert "buscar_qr_llegadas" not in initialization

    # QR-KIOSK-0B4B-5C: Home conserva el lifecycle y el ownership de caché;
    # discovery/retry y la selección BACK/fallback viven en el servicio.
    discovery = initialization[
        initialization.index("description = qr_runtime.camera_description"):initialization.index(
            'print("[QR-SCAN][LIFECYCLE] initialize begin")'
        )
    ]
    assert discovery.index("if description is not None:") < discovery.index("else:")
    assert discovery.index("else:") < discovery.index("await enumerate_cameras_with_retry(")
    assert "camera.get_available_cameras" in discovery
    assert "select_camera_description(" in discovery
    assert "if description is None:" in discovery
    assert 'cerrar_scanner_qr(\n                                "No se encontr' in discovery
    assert "fcam.CameraLensDirection.BACK" in discovery
    assert "item for item in cameras" not in discovery
    assert "cameras[0]" not in discovery
    assert "qr_runtime.camera_description = description" in discovery
    assert "Cameras available after retry=" in discovery
    assert "enumerate_cameras_with_retry" not in teardown
    cached_recovery = discovery[:discovery.index("else:")]
    assert "enumerate_cameras_with_retry" not in cached_recovery
    assert "select_camera_description" not in cached_recovery
    assert scanner_service.count("def select_camera_description(") == 1
    assert source.count("select_camera_description(") == 1
    assert "qr_runtime.camera_description" not in scanner_service
    transient_initialization_error = initialization[
        initialization.rindex("if is_camera_transient(ex):"):initialization.rindex("cerrar_scanner_qr(")
    ]
    for marker in (
        "qr_runtime.controller_initialized = False",
        'state["qr_scanner_camera_state"] = "error"',
        "Transient camera recovery exhausted; scanner remains open",
        "render()",
        "return",
    ):
        assert marker in transient_initialization_error, marker

    # QR-KIOSK-0B4B-6C: Home conserva el adapter Flet, lock, estados y
    # recovery; el servicio contiene el loop retry de initialize.
    initialize_block = initialization[
        initialization.index('print("[QR-SCAN][LIFECYCLE] initialize begin")'):initialization.index(
            'print("[QR-SCAN][LIFECYCLE] initialize lock released")'
        )
    ]
    assert "initialize_camera_with_retry(" in initialize_block
    assert "initialize_attempts" not in initialize_block
    assert "for initialize_attempt" not in initialize_block
    assert "(0.25, 0.5)" not in initialize_block
    assert "await asyncio.sleep(delay)" not in initialize_block
    assert initialize_block.count("await camera.initialize(") == 1
    assert "fcam.ResolutionPreset.LOW" in initialize_block
    assert "enable_audio=False" in initialize_block
    assert "image_format_group=fcam.ImageFormatGroup.JPEG" in initialize_block
    assert "async def initialize_once() -> None:" in initialize_block
    assert "on_initialize_transient_error" in initialize_block
    assert discovery.index("qr_runtime.camera_description = description") < initialization.index(
        'print("[QR-SCAN][LIFECYCLE] initialize begin")'
    )
    assert initialization.index("await lock.acquire()") < initialization.index("await camera.initialize(")
    assert initialization.index("await camera.initialize(") < initialization.index("lock.release()")
    assert initialization.index("lock.release()") < initialization.index("qr_runtime.controller_initialized = True")
    assert initialization.index("qr_runtime.controller_initialized = True") < initialization.index(
        "await iniciar_captura(scanner_strategy(await camera.supports_image_streaming()))"
    )
    assert 'state["qr_scanner_camera_state"] = "initialized"' in initialization
    assert "buscar_qr_llegadas" not in initialize_block
    assert "_controller_camera_no_inicializado(ex)" not in initialize_block
    assert scanner_service.count("async def initialize_camera_with_retry(") == 1
    assert source.count("initialize_camera_with_retry(") == 1
    initialize_helper = scanner_service[scanner_service.index("async def initialize_camera_with_retry("):scanner_service.index("def select_camera_description(")]
    for forbidden in (
        "controller_initialized",
        "preview_paused",
        "camera_description",
        "qr_scanner_camera_state",
        "generation",
        "lifecycle_lock",
        "buscar_qr_llegadas",
    ):
        assert forbidden not in initialize_helper, forbidden
    assert "asyncio.CancelledError" not in initialize_helper
    assert "except BaseException" not in initialize_helper

    # QR-KIOSK-0B4A: la infraestructura entrega el código al puente y el
    # negocio sólo empieza después del cleanup del finalizador externo.
    qr_callback = source[source.index("def _on_qr_detected"):source.index("def _on_scanner_stream_image")]
    assert "buscar_qr_llegadas" not in qr_callback
    finalizer = source[source.index("async def finalizar_qr"):source.index("page.run_task(finalizar_qr)")]
    assert finalizer.index("await _limpiar_camera_scanner(") < finalizer.index("buscar_qr_llegadas(codigo_qr)")
    assert finalizer.index("qr finalizer polling completed") < finalizer.index("buscar_qr_llegadas(codigo_qr)")
    assert "buscar_qr_llegadas" not in snapshot_polling
    assert "is_camera_transient(ex)" in initialization

    # QR-KIOSK-0B4B-1B: vigencia de sesión tiene una única implementación en
    # runtime; Home aporta solamente los valores técnicos de sesión.
    session_key = (2, 9)
    assert runtime_one.is_scanner_session_current(0, True, session_key, session_key, session_key)
    assert not runtime_one.is_scanner_session_current(1, True, session_key, session_key, session_key)
    assert not runtime_one.is_scanner_session_current(0, False, session_key, session_key, session_key)
    assert not runtime_one.is_scanner_session_current(0, True, session_key, None, session_key)
    assert not runtime_one.is_scanner_session_current(0, True, session_key, session_key, None)
    assert not runtime_one.is_scanner_session_current(0, True, session_key, (2, 10), session_key)
    assert not runtime_one.is_scanner_session_current(0, True, session_key, session_key, (2, 10))
    runtime_one.invalidate()
    assert not runtime_one.is_scanner_session_current(0, True, session_key, session_key, session_key)
    assert "_scanner_sigue_vigente" not in source
    # Un call site de Home fue absorbido por accept_snapshot_code(); los otros
    # siete continúan validando sus decisiones de lifecycle directamente.
    assert source.count("qr_runtime.is_scanner_session_current(") == 8

    # QR-KIOSK-0B4B-2B: la aceptación de snapshots tiene una única
    # implementación técnica. Primero valida sesión, luego abre/cierra el
    # gate; sólo después entrega el código aceptado al callback de Home.
    assert "_aceptar_codigo_snapshot" not in source
    assert source.count("qr_runtime.accept_snapshot_code(") == 1
    accept_method = runtime[runtime.index("    def accept_snapshot_code"):]
    assert accept_method.count("self.is_scanner_session_current(") == 1
    for forbidden in ("buscar_qr_llegadas", "arrivals", "rpc", "state", "page", "overlay"):
        assert forbidden not in accept_method, forbidden

    snapshot_runtime = QrCameraRuntime()
    callback_calls: list[tuple[str, int, tuple[int, int], bool, bool]] = []
    valid_gate = QrFrameGate()
    valid_gate.start()

    def on_accepted(codigo: str, generation: int, key: tuple[int, int]) -> bool:
        callback_calls.append(
            (codigo, generation, key, valid_gate.decode_busy, valid_gate.code_already_detected)
        )
        return True

    assert snapshot_runtime.accept_snapshot_code(
        "T3A1", 0, True, session_key, session_key, session_key, valid_gate, on_accepted
    )
    # finish_decode() ya liberó el decode y marcó el código antes del callback.
    assert callback_calls == [("T3A1", 0, session_key, False, True)]
    assert not snapshot_runtime.accept_snapshot_code(
        "T3A2", 0, True, session_key, session_key, session_key, valid_gate, on_accepted
    )
    assert len(callback_calls) == 1

    def assert_rejected_without_callback(
        generation: int,
        scanner_active: bool,
        candidate_session_key: tuple[int, int] | None,
        candidate_current_key: tuple[int, int] | None,
    ) -> None:
        gate = QrFrameGate()
        gate.start()
        calls: list[str] = []
        assert not snapshot_runtime.accept_snapshot_code(
            "T3A1",
            generation,
            scanner_active,
            session_key,
            candidate_session_key,
            candidate_current_key,
            gate,
            lambda codigo, _generation, _key: calls.append(codigo) or True,
        )
        assert calls == []
        assert not gate.decode_busy
        assert not gate.code_already_detected

    assert_rejected_without_callback(1, True, session_key, session_key)
    assert_rejected_without_callback(0, False, session_key, session_key)
    assert_rejected_without_callback(0, True, None, session_key)
    assert_rejected_without_callback(0, True, session_key, None)
    assert_rejected_without_callback(0, True, (2, 10), session_key)
    assert_rejected_without_callback(0, True, session_key, (2, 10))

    busy_gate = QrFrameGate()
    busy_gate.start()
    assert busy_gate.try_begin_decode()
    busy_calls: list[str] = []
    assert not snapshot_runtime.accept_snapshot_code(
        "T3A1",
        0,
        True,
        session_key,
        session_key,
        session_key,
        busy_gate,
        lambda codigo, _generation, _key: busy_calls.append(codigo) or True,
    )
    assert busy_calls == []

    empty_gate = QrFrameGate()
    empty_gate.start()
    empty_calls: list[str] = []
    assert not snapshot_runtime.accept_snapshot_code(
        "",
        0,
        True,
        session_key,
        session_key,
        session_key,
        empty_gate,
        lambda codigo, _generation, _key: empty_calls.append(codigo) or True,
    )
    assert empty_calls == []
    assert not empty_gate.decode_busy
    assert not empty_gate.code_already_detected

    false_callback_gate = QrFrameGate()
    false_callback_gate.start()
    false_callback_calls: list[str] = []
    assert not snapshot_runtime.accept_snapshot_code(
        "T3A1",
        0,
        True,
        session_key,
        session_key,
        session_key,
        false_callback_gate,
        lambda codigo, _generation, _key: false_callback_calls.append(codigo) or False,
    )
    assert false_callback_calls == ["T3A1"]
    assert false_callback_gate.code_already_detected

    # QR-KIOSK-0B4B-3B: el stream conserva un adapter Flet mínimo en Home.
    # La validación, gate, worker y decode viven una sola vez en el servicio.
    scanner_service = (ROOT / "services" / "qr_scanner_service.py").read_text(encoding="utf-8")
    assert "_scanner_frame_received" not in source
    assert "def decode_worker" not in source
    assert source.count("process_qr_camera_frame(") == 1
    assert scanner_service.count("def process_qr_camera_frame(") == 1
    assert scanner_service.count("def _decode_and_accept_qr_frame(") == 1
    stream_adapter = source[
        source.index("def _on_scanner_stream_image"):source.index("def abrir_scanner_qr")
    ]
    for marker in (
        "event.bytes",
        "process_qr_camera_frame(",
        "qr_runtime.is_scanner_session_current(",
        "page.run_thread",
        "_on_qr_detected",
    ):
        assert marker in stream_adapter, marker
    for forbidden in (
        "decode_qr_frame",
        "try_begin_decode",
        "finish_decode",
        "buscar_qr_llegadas",
        "rpc",
        "invitacion",
        "lifecycle_lock",
    ):
        assert forbidden not in stream_adapter, forbidden
    stream_processor = scanner_service[
        scanner_service.index("def process_qr_camera_frame"):scanner_service.index("def scanner_strategy")
    ]
    assert stream_processor.index("is_session_current()") < stream_processor.index("gate.try_begin_decode()")
    assert stream_processor.index("gate.try_begin_decode()") < stream_processor.index("schedule_worker(")
    stream_worker = scanner_service[
        scanner_service.index("def _decode_and_accept_qr_frame"):scanner_service.index("def scanner_strategy")
    ]
    assert stream_worker.index("decode_qr_frame") < stream_worker.index("gate.finish_decode")
    for forbidden in ("buscar_qr_llegadas", "arrivals", "rpc", "supabase", "page", "overlay"):
        assert forbidden not in stream_processor, forbidden
    assert "on_stream_image=_on_scanner_stream_image" in source
    assert "poll_qr_snapshots(" in scanner_service and "qr_runtime.accept_snapshot_code(" in source

    # QR-KIOSK-0B4B-4B: Home sólo coordina estrategia/UI y adapta callbacks;
    # servicio posee el loop y la única referencia técnica de snapshot_task.
    assert "async def take_snapshot" not in source
    capture_adapter = source[source.index("async def iniciar_captura"):source.index("async def inicializar")]
    assert "run_qr_snapshot_polling(" in capture_adapter
    for forbidden in ("poll_qr_snapshots(", "snapshot_task =", "async def take_snapshot"):
        assert forbidden not in capture_adapter, forbidden
    assert scanner_service.count("async def run_qr_snapshot_polling(") == 1
    assert scanner_service.count("async def take_qr_snapshot(") == 1
    snapshot_runner = scanner_service[
        scanner_service.index("async def run_qr_snapshot_polling"):]
    for marker in (
        "runtime.snapshot_task = polling_task",
        "if runtime.snapshot_task is polling_task:",
        "runtime.snapshot_task = None",
        "await poll_qr_snapshots(",
        "lambda: take_qr_snapshot(take_picture, generation)",
    ):
        assert marker in snapshot_runner, marker
    snapshot_capture = scanner_service[
        scanner_service.index("async def take_qr_snapshot"):scanner_service.index("async def run_qr_snapshot_polling")
    ]
    assert "qr_runtime.lifecycle_lock" not in snapshot_capture
    assert "await take_picture()" in snapshot_capture
    assert "take_picture begin" in snapshot_capture and "take_picture end" in snapshot_capture
    assert "buscar_qr_llegadas" not in snapshot_runner
    assert "qr_runtime.snapshot_task" not in capture_adapter
    assert "await polling_task" in cleanup
    assert cleanup.index("await polling_task") < cleanup.index("await camera.pause_preview()")
    assert finalizer.index("await polling_task") < finalizer.index("await _limpiar_camera_scanner(")
    print("OK - QR camera characterization contract preserved.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
