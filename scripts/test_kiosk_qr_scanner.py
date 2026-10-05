from __future__ import annotations

import asyncio
import contextlib
import inspect
import io
import sys
from pathlib import Path
from types import SimpleNamespace

import cv2

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import flet_camera as fcam

from components.kiosk_qr_scanner import KioskQrScanner
from views.kiosk_view import KioskPhase, KioskState


async def _no_delay(_seconds: float) -> None:
    return None


async def _cooperative_delay(_seconds: float) -> None:
    """Da tiempo al test para simular el corte del transporte Web."""
    await asyncio.sleep(0.01)


class FakePage:
    def __init__(self) -> None:
        self.tasks: list[asyncio.Task[object]] = []
        self.on_route_change = None

    def run_task(self, task_factory):
        if not inspect.iscoroutinefunction(task_factory):
            raise TypeError("handler must be a coroutine function")
        task = asyncio.create_task(task_factory())
        self.tasks.append(task)
        return task

    def run_thread(self, worker) -> None:
        worker()


class DisconnectedPage(FakePage):
    def __init__(self) -> None:
        super().__init__()
        self.session = SimpleNamespace(connection=None)
        self.run_task_calls = 0

    def run_task(self, task_factory):
        self.run_task_calls += 1
        raise AssertionError("disconnect must not schedule a Page task")


class FakeDescription:
    lens_direction = fcam.CameraLensDirection.BACK


class FakeCamera:
    def __init__(self, page: FakePage) -> None:
        self.page = page
        self.description = FakeDescription()
        self.fail_discovery: Exception | None = None
        self.resume_error: Exception | None = None
        self.discovery_calls = 0
        self.initialize_calls = 0
        self.start_stream_calls = 0
        self.stop_stream_calls = 0
        self.pause_calls = 0
        self.resume_calls = 0
        self.order: list[str] = []
        self.streaming_supported = True
        self.snapshot_payload = b""
        self.on_state_change = None
        self.emit_ready = True
        self.supports_calls = 0

    async def get_available_cameras(self):
        self.discovery_calls += 1
        if self.fail_discovery is not None:
            raise self.fail_discovery
        return [self.description]

    async def initialize(self, *_args, **_kwargs) -> None:
        self.initialize_calls += 1
        self.order.append("initialize")
        if self.emit_ready and callable(self.on_state_change):
            self.on_state_change(
                SimpleNamespace(is_preview_paused=False, has_error=False, is_initialized=True)
            )

    async def supports_image_streaming(self) -> bool:
        self.supports_calls += 1
        return self.streaming_supported

    async def take_picture(self) -> bytes:
        return self.snapshot_payload

    async def start_image_stream(self) -> None:
        self.start_stream_calls += 1
        self.order.append("start_stream")

    async def stop_image_stream(self) -> None:
        self.stop_stream_calls += 1
        self.order.append("stop_stream")

    async def pause_preview(self) -> None:
        self.pause_calls += 1
        self.order.append("pause_preview")

    async def resume_preview(self) -> None:
        self.resume_calls += 1
        self.order.append("resume_preview")
        if self.resume_error is not None:
            raise self.resume_error


class BlockingDiscoveryCamera(FakeCamera):
    def __init__(self, page: FakePage) -> None:
        super().__init__(page)
        self.discovery_started = asyncio.Event()
        self._release_discovery = asyncio.Event()
        self._block_discovery = False

    def block_next_discovery(self) -> None:
        self.discovery_started = asyncio.Event()
        self._release_discovery = asyncio.Event()
        self._block_discovery = True

    async def get_available_cameras(self):
        if self._block_discovery:
            self.discovery_started.set()
            await self._release_discovery.wait()
        return await super().get_available_cameras()


class BlockingResumeCamera(FakeCamera):
    def __init__(self, page: FakePage) -> None:
        super().__init__(page)
        self.resume_started = asyncio.Event()
        self._release_resume = asyncio.Event()
        self._block_resume = False

    def block_next_resume(self) -> None:
        self.resume_started = asyncio.Event()
        self._release_resume = asyncio.Event()
        self._block_resume = True

    async def resume_preview(self) -> None:
        await super().resume_preview()
        if self._block_resume:
            self.resume_started.set()
            await self._release_resume.wait()


class RetryDiscoveryCamera(FakeCamera):
    def __init__(self, page: FakePage) -> None:
        super().__init__(page)
        self.discovery_attempts = 0

    async def get_available_cameras(self):
        self.discovery_attempts += 1
        if self.discovery_attempts == 1:
            raise RuntimeError("cameraNotReadable")
        return await super().get_available_cameras()


def test_page_scheduler_requires_coroutine_function() -> None:
    page = FakePage()
    try:
        page.run_task(lambda: _no_delay(0))
        raise AssertionError("El scheduler debia rechazar un handler sync")
    except TypeError as ex:
        assert str(ex) == "handler must be a coroutine function"


async def _wait_page_tasks(page: FakePage) -> None:
    while page.tasks:
        tasks, page.tasks = page.tasks[:], []
        await asyncio.gather(*tasks)


async def test_session_acceptance_duplicate_and_reset() -> None:
    page = FakePage()
    camera = FakeCamera(page)
    events: list[str] = []

    def on_qr_finalized(code: str) -> None:
        camera.order.append("callback")
        events.append(f"callback:{code}")

    scanner = KioskQrScanner(
        page=page,
        on_qr_finalized=on_qr_finalized,
        on_camera_error=lambda message: events.append(f"error:{message}"),
        camera=camera,
        sleep=_no_delay,
        create_host=False,
    )
    await scanner.start_scan()
    generation = scanner.runtime.generation
    session_key = scanner._session_key
    assert scanner.active and session_key is not None
    assert camera.initialize_calls == 1 and camera.start_stream_calls == 1
    assert scanner._accept_code("T3A1", generation, session_key)
    assert not scanner._accept_code("T3A2", generation, session_key)
    await _wait_page_tasks(page)
    assert events == ["callback:T3A1"]
    assert camera.order.index("stop_stream") < camera.order.index("callback")
    assert camera.pause_calls == 1
    assert scanner.runtime.controller_initialized
    assert scanner.runtime.preview_paused

    old_generation = generation
    await scanner.restart_scan()
    assert scanner.runtime.generation != old_generation
    assert scanner._session_key is not None
    assert not scanner._accept_code("T3A3", old_generation, session_key)
    await scanner.stop_scan()
    assert not scanner.active
    assert camera.pause_calls == 2


async def test_camera_error_retry_and_cleanup() -> None:
    page = FakePage()
    camera = FakeCamera(page)
    errors: list[str] = []
    scanner = KioskQrScanner(
        page=page,
        on_qr_finalized=lambda _code: None,
        on_camera_error=errors.append,
        camera=camera,
        sleep=_no_delay,
        create_host=False,
    )
    camera.fail_discovery = RuntimeError("permission denied")
    await scanner.start_scan()
    assert not scanner.active
    assert errors and "permiso" in errors[-1].lower()

    camera.fail_discovery = None
    await scanner.start_scan()
    assert scanner.active
    await scanner.stop_scan()
    assert not scanner.active
    assert scanner.runtime.snapshot_task is None


def _qr_jpeg(code: str) -> bytes:
    image = cv2.QRCodeEncoder_create().encode(code)
    # El detector OpenCV requiere zona silenciosa y una resolución suficiente.
    image = cv2.copyMakeBorder(
        image,
        16,
        16,
        16,
        16,
        cv2.BORDER_CONSTANT,
        value=255,
    )
    image = cv2.resize(image, None, fx=8, fy=8, interpolation=cv2.INTER_NEAREST)
    ok, encoded = cv2.imencode(".png", image)
    assert ok
    return encoded.tobytes()


async def test_snapshot_pipeline_with_realistic_jpeg_payload() -> None:
    page = FakePage()
    camera = FakeCamera(page)
    camera.streaming_supported = False
    camera.snapshot_payload = _qr_jpeg("T3A1")
    callbacks: list[str] = []
    scanner = KioskQrScanner(
        page=page,
        on_qr_finalized=callbacks.append,
        on_camera_error=lambda message: callbacks.append(f"error:{message}"),
        camera=camera,
        sleep=_no_delay,
        create_host=False,
    )

    await scanner.start_scan()
    await _wait_page_tasks(page)
    assert callbacks == ["T3A1"]
    assert not scanner.active
    assert scanner.runtime.snapshot_task is None


async def test_startup_perf_instrumentation_distinguishes_sources_without_new_tasks() -> None:
    page = FakePage()
    page.session = SimpleNamespace(connection=object())
    camera = FakeCamera(page)
    camera.streaming_supported = False
    callbacks: list[str] = []
    scanner = KioskQrScanner(
        page=page,
        on_qr_finalized=callbacks.append,
        on_camera_error=lambda message: callbacks.append(f"error:{message}"),
        camera=camera,
        sleep=_no_delay,
        create_host=False,
    )

    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        camera.snapshot_payload = _qr_jpeg("T3A1")
        scanner.start()
        await _wait_page_tasks(page)

        camera.snapshot_payload = _qr_jpeg("T3A2")
        scanner.restart()
        await _wait_page_tasks(page)

        camera.snapshot_payload = _qr_jpeg("T3A3")
        scanner.recover_after_reconnect()
        await _wait_page_tasks(page)

    trace = output.getvalue()
    required_initial = (
        "startup_id=1 source=initial stage=startup_begin",
        "startup_id=1 source=initial stage=camera_discovery_begin",
        "startup_id=1 source=initial stage=camera_discovery_end",
        "startup_id=1 source=initial stage=initialize_begin",
        "startup_id=1 source=initial stage=initialize_end",
        "startup_id=1 source=initial stage=polling_started",
        "startup_id=1 source=initial stage=first_take_picture_begin",
        "startup_id=1 source=initial stage=first_take_picture_end",
    )
    for marker in required_initial:
        assert marker in trace, marker
    assert "startup_id=2 source=reset stage=startup_begin" in trace
    assert "startup_id=2 source=reset stage=polling_started" in trace
    assert "startup_id=2 source=reset stage=first_take_picture_end" in trace
    assert "startup_id=3 source=reconnect stage=camera_discovery_begin" in trace
    assert "startup_id=3 source=reconnect stage=initialize_end" in trace
    assert callbacks == ["T3A1", "T3A2", "T3A3"]
    assert scanner.runtime.snapshot_task is None
    assert not page.tasks


async def test_startup_perf_instrumentation_records_discovery_retry_backoff() -> None:
    page = FakePage()
    camera = RetryDiscoveryCamera(page)
    camera.streaming_supported = False
    camera.snapshot_payload = _qr_jpeg("T3A1")
    scanner = KioskQrScanner(
        page=page,
        on_qr_finalized=lambda _code: None,
        on_camera_error=lambda _message: None,
        camera=camera,
        sleep=_no_delay,
        create_host=False,
    )

    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        scanner.start()
        await _wait_page_tasks(page)

    trace = output.getvalue()
    assert camera.discovery_attempts == 2
    assert "stage=camera_discovery_attempt_1" in trace
    assert "stage=camera_discovery_retry attempt=1/3 backoff_ms=400.0" in trace
    assert "stage=camera_discovery_attempt_2" in trace
    assert "stage=camera_discovery_end" in trace


async def test_initial_startup_keeps_mounted_discovery_then_initialize_after_mount_wait() -> None:
    """El bypass de reset no puede alterar la secuencia del primer montaje."""
    page = FakePage()
    page.session = SimpleNamespace(connection=object())
    camera = FakeCamera(page)
    camera.streaming_supported = False
    camera.snapshot_payload = _qr_jpeg("T3A1")
    sleep_calls: list[float] = []

    async def record_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)

    scanner = KioskQrScanner(
        page=page,
        on_qr_finalized=lambda _code: None,
        on_camera_error=lambda _message: None,
        camera=camera,
        sleep=record_sleep,
        create_host=False,
    )
    # Simula el único dato que el fast path podría reutilizar. En `initial`
    # debe ignorarse y discovery debe seguir siendo obligatorio.
    scanner.runtime.camera_description = camera.description

    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        scanner.start()
        await _wait_page_tasks(page)

    trace = output.getvalue()
    assert sleep_calls == [0.3]
    assert camera.discovery_calls == 1
    assert camera.initialize_calls == 1
    assert "source=initial phase=call_enter" in trace
    assert "source=initial phase=call_return" in trace
    assert "camera_mounted=True" in trace
    assert "page_id=" in trace
    assert "camera_in_overlay=False" in trace
    assert trace.index("phase=call_enter") < trace.index("phase=call_return")
    assert trace.index("phase=call_return") < trace.index("stage=initialize_begin")


async def test_startup_perf_preview_ready_waits_for_native_state_callback() -> None:
    page = FakePage()
    camera = FakeCamera(page)
    scanner = KioskQrScanner(
        page=page,
        on_qr_finalized=lambda _code: None,
        on_camera_error=lambda _message: None,
        camera=camera,
        sleep=_no_delay,
        create_host=False,
    )

    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        await scanner.start_scan()

    trace = output.getvalue()
    assert "stage=initialize_return" in trace
    assert "stage=preview_ready" in trace
    assert trace.index("stage=preview_ready") < trace.index("stage=initialize_return")
    await scanner.stop_scan()


async def test_reset_uses_full_initialization_after_qr_finalization() -> None:
    page = FakePage()
    page.session = SimpleNamespace(connection=object())
    camera = FakeCamera(page)
    camera.streaming_supported = False
    callbacks: list[str] = []
    scanner = KioskQrScanner(
        page=page,
        on_qr_finalized=callbacks.append,
        on_camera_error=lambda message: callbacks.append(f"error:{message}"),
        camera=camera,
        sleep=_no_delay,
        create_host=False,
    )

    camera.snapshot_payload = _qr_jpeg("T3A1")
    scanner.start()
    await _wait_page_tasks(page)
    discovery_calls = camera.discovery_calls
    initialize_calls = camera.initialize_calls
    assert scanner.runtime.controller_initialized
    assert scanner.runtime.camera_description is camera.description
    assert camera.pause_calls == 1
    assert scanner.runtime.preview_paused

    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        camera.snapshot_payload = _qr_jpeg("T3A2")
        scanner.restart()
        await _wait_page_tasks(page)

    trace = output.getvalue()
    assert camera.discovery_calls == discovery_calls + 1
    assert camera.initialize_calls == initialize_calls + 1
    # El segundo QR también se finaliza y por tanto pausa una vez; no existe
    # un pause adicional entre Pause A y resume_preview.
    assert camera.pause_calls == 2
    assert camera.resume_calls == 0
    assert "[KIOSK-QR][WARM] capture_suspended" in trace
    assert "[KIOSK-QR][WARM] camera_reused source=reset" not in trace
    assert "source=reset stage=polling_started" in trace
    assert "source=reset stage=camera_discovery_begin" in trace
    assert "source=reset stage=initialize_begin" in trace
    assert callbacks == ["T3A1", "T3A2"]


async def test_five_guest_cycles_use_full_recovery_without_error() -> None:
    page = FakePage()
    page.session = SimpleNamespace(connection=object())
    camera = FakeCamera(page)
    camera.streaming_supported = False
    callbacks: list[str] = []
    scanner = KioskQrScanner(
        page=page,
        on_qr_finalized=callbacks.append,
        on_camera_error=lambda message: callbacks.append(f"error:{message}"),
        camera=camera,
        sleep=_no_delay,
        create_host=False,
    )

    for index, code in enumerate(("T3A1", "T3A2", "T3A3", "T3A4")):
        camera.snapshot_payload = _qr_jpeg(code)
        if index == 0:
            scanner.start()
        else:
            scanner.restart()
        await _wait_page_tasks(page)
        assert scanner.runtime.snapshot_task is None
        assert scanner.runtime.controller_initialized
        assert scanner.runtime.preview_paused

    assert callbacks == ["T3A1", "T3A2", "T3A3", "T3A4"]
    assert camera.discovery_calls == 4
    assert camera.initialize_calls == 4
    assert camera.pause_calls == 4
    assert camera.resume_calls == 0


async def test_phase_suspend_keeps_camera_warm_and_shutdown_pauses() -> None:
    page = FakePage()
    camera = FakeCamera(page)
    scanner = KioskQrScanner(
        page=page,
        on_qr_finalized=lambda _code: None,
        on_camera_error=lambda _message: None,
        camera=camera,
        sleep=_no_delay,
        create_host=False,
    )

    await scanner.start_scan()
    await scanner._suspend_capture_for_phase()
    assert scanner.runtime.controller_initialized
    assert not scanner.runtime.preview_paused
    assert camera.pause_calls == 0

    await scanner.stop_scan()

    assert camera.pause_calls == 1
    assert scanner.runtime.preview_paused


async def test_disconnect_while_warm_invalidates_without_automatic_reconnect() -> None:
    page = FakePage()
    page.session = SimpleNamespace(connection=object())
    camera = FakeCamera(page)
    camera.streaming_supported = False
    scanner = KioskQrScanner(
        page=page,
        on_qr_finalized=lambda _code: None,
        on_camera_error=lambda _message: None,
        camera=camera,
        sleep=_no_delay,
        create_host=False,
    )

    camera.snapshot_payload = _qr_jpeg("T3A1")
    scanner.start()
    await _wait_page_tasks(page)
    assert scanner.runtime.controller_initialized
    assert scanner.runtime.snapshot_task is None

    page.session.connection = None
    scanner.close()

    assert not scanner.runtime.controller_initialized
    assert scanner.runtime.camera_description is None
    assert scanner.runtime.snapshot_task is None
    assert not page.tasks
    assert camera.initialize_calls == 1


async def test_reset_with_lost_warm_camera_uses_full_initialization_once() -> None:
    page = FakePage()
    page.session = SimpleNamespace(connection=object())
    camera = FakeCamera(page)
    camera.streaming_supported = False
    callbacks: list[str] = []
    scanner = KioskQrScanner(
        page=page,
        on_qr_finalized=callbacks.append,
        on_camera_error=lambda message: callbacks.append(f"error:{message}"),
        camera=camera,
        sleep=_no_delay,
        create_host=False,
    )

    camera.snapshot_payload = _qr_jpeg("T3A1")
    scanner.start()
    await _wait_page_tasks(page)
    discovery_calls = camera.discovery_calls
    initialize_calls = camera.initialize_calls
    scanner.runtime.controller_initialized = False

    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        camera.snapshot_payload = _qr_jpeg("T3A2")
        scanner.restart()
        await _wait_page_tasks(page)

    trace = output.getvalue()
    assert camera.resume_calls == 0
    assert camera.discovery_calls == discovery_calls + 1
    assert camera.initialize_calls == initialize_calls + 1
    assert "source=reset stage=camera_discovery_begin" in trace
    assert "source=reset stage=preview_ready" in trace
    assert callbacks == ["T3A1", "T3A2"]


async def test_initialize_return_without_native_readiness_fails_before_strategy() -> None:
    page = FakePage()
    camera = FakeCamera(page)
    camera.emit_ready = False
    errors: list[str] = []
    scanner = KioskQrScanner(
        page=page,
        on_qr_finalized=lambda _code: None,
        on_camera_error=errors.append,
        camera=camera,
        sleep=_no_delay,
        create_host=False,
    )

    await scanner.start_scan()

    assert camera.initialize_calls == 1
    assert camera.supports_calls == 0
    assert not scanner.active
    assert len(errors) == 1, errors
    assert errors[0].startswith("No pudimos iniciar"), errors


async def test_camera_failure_log_includes_technical_message_without_exposing_it_to_ui() -> None:
    page = FakePage()
    camera = FakeCamera(page)
    errors: list[str] = []
    scanner = KioskQrScanner(
        page=page,
        on_qr_finalized=lambda _code: None,
        on_camera_error=errors.append,
        camera=camera,
        sleep=_no_delay,
        create_host=False,
    )
    await scanner.start_scan()
    generation = scanner.runtime.generation
    session_key = scanner._session_key
    assert session_key is not None

    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        await scanner._fail_session(
            RuntimeError("Camera is not initialized. call initialize() first."),
            generation,
            session_key,
        )

    trace = output.getvalue()
    assert "type=RuntimeError" in trace
    assert "message=Camera is not initialized. call initialize() first." in trace
    assert "[KIOSK-QR][IDENTITY] stage=camera_session_failed" in trace
    assert len(errors) == 1
    assert errors[0].startswith("No pudimos iniciar")


async def test_disconnect_during_reset_fast_path_keeps_reconnect_recovery() -> None:
    page = FakePage()
    page.session = SimpleNamespace(connection=object())
    camera = BlockingResumeCamera(page)
    camera.streaming_supported = False
    callbacks: list[str] = []
    scanner = KioskQrScanner(
        page=page,
        on_qr_finalized=callbacks.append,
        on_camera_error=lambda message: callbacks.append(f"error:{message}"),
        camera=camera,
        sleep=_no_delay,
        create_host=False,
    )

    camera.snapshot_payload = _qr_jpeg("T3A1")
    scanner.start()
    await _wait_page_tasks(page)
    camera.snapshot_payload = b""
    camera.block_next_resume()
    scanner.restart()
    startup_reset = scanner._startup_task
    assert startup_reset is not None
    await camera.resume_started.wait()

    page.session.connection = None
    scanner.close()
    assert startup_reset.cancelled() or startup_reset.cancelling()
    await asyncio.sleep(0)
    assert not scanner.runtime.lifecycle_lock.locked()

    page.session.connection = object()
    camera._block_resume = False
    camera.snapshot_payload = _qr_jpeg("T3A2")
    scanner.recover_after_reconnect()
    await _drain_page_tasks_after_disconnect(page)

    assert callbacks == ["T3A1", "T3A2"]
    assert scanner.runtime.snapshot_task is None


async def test_production_start_handoff_is_synchronous_and_finalizes_once() -> None:
    page = FakePage()
    camera = FakeCamera(page)
    camera.streaming_supported = False
    camera.snapshot_payload = _qr_jpeg("T3A1")
    state = KioskState()

    def finalized(code: str) -> None:
        camera.order.append("callback")
        assert state.accept_scanned_qr(code)

    scanner = KioskQrScanner(
        page=page,
        on_qr_finalized=finalized,
        on_camera_error=lambda message: state.show_error(message),
        camera=camera,
        sleep=_no_delay,
        create_host=False,
    )

    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        scanner.start()
        await _wait_page_tasks(page)

    assert state.phase == KioskPhase.RESOLVING
    assert scanner.runtime.snapshot_task is None
    assert not scanner.active
    assert not inspect.iscoroutinefunction(scanner.on_snapshot_code)
    trace = output.getvalue()
    markers = (
        "[QR-SCAN][SNAPSHOT] qr_found",
        "[QR-SCAN][SNAPSHOT] before_on_code",
        "[KIOSK-QR][SNAPSHOT] on_code_enter",
        "[KIOSK-QR][SNAPSHOT] code_gate session_current=True accepted=True reason=accepted",
        "[QR-SCAN][SNAPSHOT] on_code_return value=True",
        "[QR-SCAN][SNAPSHOT] polling_exit reason=code_accepted",
        "[QR-SCAN][LIFECYCLE] polling task finished",
        "[KIOSK-QR][SNAPSHOT] kiosk_callback called",
    )
    for marker in markers:
        assert marker in trace, marker
    assert [trace.index(marker) for marker in markers] == sorted(
        trace.index(marker) for marker in markers
    )
    assert camera.order == ["initialize", "pause_preview", "callback"]


async def test_close_after_disconnect_does_not_schedule_page_task() -> None:
    page = DisconnectedPage()
    camera = FakeCamera(page)
    scanner = KioskQrScanner(
        page=page,
        on_qr_finalized=lambda _code: None,
        on_camera_error=lambda _message: None,
        camera=camera,
        sleep=_no_delay,
        create_host=False,
    )
    scanner.gate.start()
    scanner.active = True
    scanner._session_key = (id(scanner), scanner.runtime.invalidate())
    previous_generation = scanner.runtime.generation

    scanner.close()

    assert page.run_task_calls == 0
    assert not scanner.active and not scanner.gate.active
    assert scanner.runtime.generation == previous_generation + 1
    assert scanner.runtime.snapshot_task is None


async def test_close_with_active_page_schedules_normal_cleanup() -> None:
    page = FakePage()
    camera = FakeCamera(page)
    scanner = KioskQrScanner(
        page=page,
        on_qr_finalized=lambda _code: None,
        on_camera_error=lambda _message: None,
        camera=camera,
        sleep=_no_delay,
        create_host=False,
    )
    await scanner.start_scan()
    assert scanner.active
    scanner.close()
    await _wait_page_tasks(page)
    assert not scanner.active
    assert camera.pause_calls == 1


async def _drain_page_tasks_after_disconnect(page: FakePage) -> None:
    while page.tasks:
        tasks, page.tasks = page.tasks[:], []
        outcomes = await asyncio.gather(*tasks, return_exceptions=True)
        for outcome in outcomes:
            if isinstance(outcome, BaseException) and not isinstance(outcome, asyncio.CancelledError):
                raise outcome


async def test_same_page_reconnect_restarts_one_snapshot_session() -> None:
    page = FakePage()
    page.session = SimpleNamespace(connection=object())
    camera = FakeCamera(page)
    camera.streaming_supported = False
    callbacks: list[str] = []
    state = KioskState()
    scanner = KioskQrScanner(
        page=page,
        on_qr_finalized=lambda code: (callbacks.append(code), state.accept_scanned_qr(code)),
        on_camera_error=lambda message: callbacks.append(f"error:{message}"),
        camera=camera,
        sleep=_cooperative_delay,
        create_host=False,
    )

    scanner.start()
    await asyncio.sleep(0.03)
    first_generation = scanner.runtime.generation
    first_polling_task = scanner.runtime.snapshot_task
    assert scanner.active and first_polling_task is not None

    page.session.connection = None
    scanner.close()
    assert not scanner.active
    assert first_polling_task.cancelled() or first_polling_task.cancelling()

    page.session.connection = object()
    camera.snapshot_payload = _qr_jpeg("T3A1")
    scanner.recover_after_reconnect()
    scanner.recover_after_reconnect()
    scanner.recover_after_reconnect()
    assert len(page.tasks) == 2  # polling cancelado + una sola recuperacion encolada
    await _drain_page_tasks_after_disconnect(page)

    assert scanner.runtime.generation > first_generation
    assert camera.initialize_calls == 2
    assert callbacks == ["T3A1"]
    assert state.phase == KioskPhase.RESOLVING
    assert scanner.runtime.snapshot_task is None


async def test_reconnect_cycles_do_not_duplicate_camera_or_polling() -> None:
    page = FakePage()
    page.session = SimpleNamespace(connection=object())
    camera = FakeCamera(page)
    camera.streaming_supported = False
    callbacks: list[str] = []
    scanner = KioskQrScanner(
        page=page,
        on_qr_finalized=callbacks.append,
        on_camera_error=lambda message: callbacks.append(f"error:{message}"),
        camera=camera,
        sleep=_cooperative_delay,
        create_host=False,
    )
    scanner.start()
    await asyncio.sleep(0.03)

    for code in ("T3A1", "T3A2", "T3A3"):
        page.session.connection = None
        scanner.close()
        page.session.connection = object()
        camera.snapshot_payload = _qr_jpeg(code)
        scanner.recover_after_reconnect()
        await _drain_page_tasks_after_disconnect(page)
        assert callbacks[-1] == code
        assert scanner.runtime.snapshot_task is None
        assert not scanner.active
        if code != "T3A3":
            camera.snapshot_payload = b""
            scanner.start()
            await asyncio.sleep(0.03)
            assert scanner.active and scanner.runtime.snapshot_task is not None

    assert callbacks == ["T3A1", "T3A2", "T3A3"]
    assert camera.initialize_calls == 6


async def test_reconnect_after_cancelled_discovery_starts_fresh_recovery() -> None:
    page = FakePage()
    page.session = SimpleNamespace(connection=object())
    camera = BlockingDiscoveryCamera(page)
    camera.streaming_supported = False
    callbacks: list[str] = []
    state = KioskState()
    scanner = KioskQrScanner(
        page=page,
        on_qr_finalized=lambda code: (callbacks.append(code), state.accept_scanned_qr(code)),
        on_camera_error=lambda message: callbacks.append(f"error:{message}"),
        camera=camera,
        sleep=_cooperative_delay,
        create_host=False,
    )
    scanner.start()
    await asyncio.sleep(0.03)
    first_generation = scanner.runtime.generation

    page.session.connection = None
    scanner.close()
    page.session.connection = object()
    camera.block_next_discovery()
    scanner.recover_after_reconnect()
    recovery_a = page.tasks[-1]
    await camera.discovery_started.wait()

    page.session.connection = None
    scanner.close()
    assert recovery_a.cancelled() or recovery_a.cancelling()
    page.session.connection = object()
    camera._block_discovery = False
    camera.snapshot_payload = _qr_jpeg("T3A1")
    scanner.recover_after_reconnect()
    await _drain_page_tasks_after_disconnect(page)

    assert scanner.runtime.generation > first_generation
    assert camera.initialize_calls == 2
    assert callbacks == ["T3A1"]
    assert state.phase == KioskPhase.RESOLVING
    assert scanner._startup_task is None


async def test_stale_recovery_cannot_publish_over_new_recovery() -> None:
    page = FakePage()
    page.session = SimpleNamespace(connection=object())
    camera = FakeCamera(page)
    camera.streaming_supported = False
    callbacks: list[str] = []
    scanner = KioskQrScanner(
        page=page,
        on_qr_finalized=callbacks.append,
        on_camera_error=lambda message: callbacks.append(f"error:{message}"),
        camera=camera,
        sleep=_cooperative_delay,
        create_host=False,
    )
    scanner.start()
    await asyncio.sleep(0.03)

    page.session.connection = None
    scanner.close()
    page.session.connection = object()
    for _ in range(2):
        scanner.recover_after_reconnect()
        recovery_task = scanner._startup_task
        assert recovery_task is not None
        page.session.connection = None
        scanner.close()
        assert recovery_task.cancelled() or recovery_task.cancelling()
        page.session.connection = object()

    camera.snapshot_payload = _qr_jpeg("T3A1")
    scanner.recover_after_reconnect()
    final_recovery = scanner._startup_task
    assert final_recovery is not None
    await _drain_page_tasks_after_disconnect(page)

    assert callbacks == ["T3A1"]
    assert camera.initialize_calls == 2
    assert scanner._startup_task is None


async def test_reset_startup_cancelled_by_disconnect_releases_lock_for_reconnect() -> None:
    page = FakePage()
    page.session = SimpleNamespace(connection=object())
    camera = BlockingDiscoveryCamera(page)
    camera.streaming_supported = False
    callbacks: list[str] = []
    scanner = KioskQrScanner(
        page=page,
        on_qr_finalized=callbacks.append,
        on_camera_error=lambda message: callbacks.append(f"error:{message}"),
        camera=camera,
        sleep=_cooperative_delay,
        create_host=False,
    )

    camera.snapshot_payload = _qr_jpeg("T3A1")
    scanner.start()
    await _drain_page_tasks_after_disconnect(page)
    assert callbacks == ["T3A1"]

    camera.snapshot_payload = b""
    camera.block_next_discovery()
    scanner.runtime.controller_initialized = False
    scanner.runtime.camera_description = None
    scanner.restart()
    startup_a = scanner._startup_task
    assert startup_a is not None
    await camera.discovery_started.wait()
    assert scanner.runtime.lifecycle_lock.locked()

    page.session.connection = None
    scanner.close()
    assert startup_a.cancelled() or startup_a.cancelling()
    await asyncio.sleep(0)
    assert not scanner.runtime.lifecycle_lock.locked()
    assert scanner._startup_task is None

    page.session.connection = object()
    camera._block_discovery = False
    camera.snapshot_payload = _qr_jpeg("T3A2")
    scanner.recover_after_reconnect()
    startup_b = scanner._startup_task
    assert startup_b is not None and startup_b is not startup_a
    await _drain_page_tasks_after_disconnect(page)

    assert callbacks == ["T3A1", "T3A2"]
    assert scanner.runtime.snapshot_task is None
    assert scanner._startup_task is None


def test_adapter_has_no_business_or_rpc() -> None:
    source = (ROOT / "components" / "kiosk_qr_scanner.py").read_text(encoding="utf-8")
    for forbidden in (
        "buscar_qr_llegadas",
        "resolver_invitacion_qr",
        "confirmar_llegada",
        "supabase",
        "rpc(",
        "arrivals_",
    ):
        assert forbidden not in source, forbidden


async def _main_async() -> None:
    await test_session_acceptance_duplicate_and_reset()
    await test_camera_error_retry_and_cleanup()
    await test_snapshot_pipeline_with_realistic_jpeg_payload()
    await test_startup_perf_instrumentation_distinguishes_sources_without_new_tasks()
    await test_startup_perf_instrumentation_records_discovery_retry_backoff()
    await test_initial_startup_keeps_mounted_discovery_then_initialize_after_mount_wait()
    await test_startup_perf_preview_ready_waits_for_native_state_callback()
    await test_reset_uses_full_initialization_after_qr_finalization()
    await test_five_guest_cycles_use_full_recovery_without_error()
    await test_phase_suspend_keeps_camera_warm_and_shutdown_pauses()
    await test_disconnect_while_warm_invalidates_without_automatic_reconnect()
    await test_reset_with_lost_warm_camera_uses_full_initialization_once()
    await test_initialize_return_without_native_readiness_fails_before_strategy()
    await test_camera_failure_log_includes_technical_message_without_exposing_it_to_ui()
    await test_production_start_handoff_is_synchronous_and_finalizes_once()
    await test_close_after_disconnect_does_not_schedule_page_task()
    await test_close_with_active_page_schedules_normal_cleanup()
    await test_same_page_reconnect_restarts_one_snapshot_session()
    await test_reconnect_cycles_do_not_duplicate_camera_or_polling()
    await test_reconnect_after_cancelled_discovery_starts_fresh_recovery()
    await test_stale_recovery_cannot_publish_over_new_recovery()
    await test_reset_startup_cancelled_by_disconnect_releases_lock_for_reconnect()


def main() -> None:
    test_adapter_has_no_business_or_rpc()
    test_page_scheduler_requires_coroutine_function()
    asyncio.run(_main_async())
    print("Kiosk QR scanner adapter tests passed.")


if __name__ == "__main__":
    main()
