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
        self.initialize_calls = 0
        self.start_stream_calls = 0
        self.stop_stream_calls = 0
        self.pause_calls = 0
        self.resume_calls = 0
        self.order: list[str] = []
        self.streaming_supported = True
        self.snapshot_payload = b""

    async def get_available_cameras(self):
        if self.fail_discovery is not None:
            raise self.fail_discovery
        return [self.description]

    async def initialize(self, *_args, **_kwargs) -> None:
        self.initialize_calls += 1
        self.order.append("initialize")

    async def supports_image_streaming(self) -> bool:
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
    assert camera.order.index("stop_stream") < camera.order.index("pause_preview") < camera.order.index("callback")
    assert camera.pause_calls == 1

    old_generation = generation
    await scanner.restart_scan()
    assert scanner.runtime.generation != old_generation
    assert scanner._session_key is not None
    assert not scanner._accept_code("T3A3", old_generation, session_key)
    await scanner.stop_scan()
    assert not scanner.active
    assert camera.pause_calls >= 2


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
    assert "pause_preview" in camera.order, camera.order
    assert camera.order.index("pause_preview") < camera.order.index("callback")


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
    await test_production_start_handoff_is_synchronous_and_finalizes_once()
    await test_close_after_disconnect_does_not_schedule_page_task()
    await test_close_with_active_page_schedules_normal_cleanup()


def main() -> None:
    test_adapter_has_no_business_or_rpc()
    test_page_scheduler_requires_coroutine_function()
    asyncio.run(_main_async())
    print("Kiosk QR scanner adapter tests passed.")


if __name__ == "__main__":
    main()
