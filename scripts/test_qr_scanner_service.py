from __future__ import annotations

import asyncio
import inspect
import sys
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services import qr_scanner_service as scanner


class Detector:
    def __init__(self, value: str | None = "") -> None:
        self.value = value

    def detectAndDecode(self, _image: object) -> tuple[str | None, None, None]:
        return self.value, None, None


class SnapshotOwner:
    def __init__(self) -> None:
        self.snapshot_task: asyncio.Task[object] | None = None


def test_decoder() -> None:
    with patch.object(scanner.cv2, "imdecode", return_value=object()), patch.object(scanner.cv2, "QRCodeDetector", return_value=Detector(" t3a1 ")):
        assert scanner.decode_qr_frame(b"encoded") == "T3A1"
    with patch.object(scanner.cv2, "imdecode", return_value=object()), patch.object(scanner.cv2, "QRCodeDetector", return_value=Detector("")):
        assert scanner.decode_qr_frame(b"encoded") is None
    with patch.object(scanner.cv2, "imdecode", return_value=object()), patch.object(scanner.cv2, "QRCodeDetector", return_value=Detector("ABC")):
        assert scanner.decode_qr_frame(b"encoded") is None
    with patch.object(scanner.cv2, "imdecode", return_value=object()), patch.object(scanner.cv2, "QRCodeDetector", return_value=Detector("A-12")):
        assert scanner.decode_qr_frame(b"encoded") is None
    assert scanner.decode_qr_frame(b"not-an-image") is None
    with patch.object(scanner.cv2, "imdecode", side_effect=RuntimeError("decoder failure")):
        assert scanner.decode_qr_frame(b"encoded") is None


def test_gate_throttles_and_accepts_once() -> None:
    gate = scanner.QrFrameGate(throttle_seconds=0.25)
    gate.start()
    assert gate.try_begin_decode(now=1.0)
    assert not gate.try_begin_decode(now=1.1)
    assert gate.finish_decode(None) is None
    assert gate.try_begin_decode(now=1.3)
    assert gate.finish_decode("T3A1") == "T3A1"
    assert not gate.try_begin_decode(now=2.0)
    gate.stop()
    assert gate.finish_decode("T3A1") is None


def test_stream_frame_processing_preserves_gate_and_worker_boundaries() -> None:
    def schedule_worker(worker: object) -> None:
        assert callable(worker)
        scheduled.append(worker)

    # Una sesión vencida no abre el gate ni programa trabajo.
    expired_gate = scanner.QrFrameGate()
    expired_gate.start()
    scheduled: list[object] = []
    expired_codes: list[str] = []
    scanner.process_qr_camera_frame(
        b"frame", lambda: False, expired_gate, schedule_worker, expired_codes.append
    )
    assert scheduled == [] and expired_codes == []
    assert not expired_gate.decode_busy and not expired_gate.code_already_detected

    # Un gate ocupado también evita programar otro worker concurrente.
    busy_gate = scanner.QrFrameGate()
    busy_gate.start()
    assert busy_gate.try_begin_decode()
    scheduled = []
    scanner.process_qr_camera_frame(
        b"frame", lambda: True, busy_gate, schedule_worker, expired_codes.append
    )
    assert scheduled == []

    # Una sesión vigente programa exactamente un worker; finish_decode ocurre
    # dentro de éste y deja pasar un único código aceptado.
    gate = scanner.QrFrameGate()
    gate.start()
    scheduled = []
    accepted: list[str] = []
    with patch.object(scanner, "decode_qr_frame", return_value="T3A1"):
        scanner.process_qr_camera_frame(
            b"valid-frame", lambda: True, gate, schedule_worker, accepted.append
        )
        assert len(scheduled) == 1
        assert gate.decode_busy and accepted == []
        scheduled[0]()
    assert accepted == ["T3A1"]
    assert not gate.decode_busy and gate.code_already_detected

    scanner.process_qr_camera_frame(
        b"duplicate-frame", lambda: True, gate, schedule_worker, accepted.append
    )
    assert len(scheduled) == 1 and accepted == ["T3A1"]

    # Bytes vacíos o un decode recuperable sin QR limpian el gate y no llaman
    # al callback; decode_qr_frame ya contiene el manejo de excepciones OpenCV.
    no_code_gate = scanner.QrFrameGate()
    no_code_gate.start()
    scheduled = []
    with patch.object(scanner, "decode_qr_frame", return_value=None):
        scanner.process_qr_camera_frame(
            b"", lambda: True, no_code_gate, schedule_worker, accepted.append
        )
        assert len(scheduled) == 1
        scheduled[0]()
    assert accepted == ["T3A1"]
    assert not no_code_gate.decode_busy and not no_code_gate.code_already_detected

    decode_error_gate = scanner.QrFrameGate()
    decode_error_gate.start()
    scheduled = []
    with patch.object(scanner.cv2, "imdecode", side_effect=RuntimeError("decoder failure")):
        scanner.process_qr_camera_frame(
            b"encoded", lambda: True, decode_error_gate, schedule_worker, accepted.append
        )
        assert len(scheduled) == 1
        scheduled[0]()
    assert accepted == ["T3A1"]
    assert not decode_error_gate.decode_busy and not decode_error_gate.code_already_detected


async def _without_wait(_seconds: float) -> None:
    return None


def test_stream_or_snapshot_strategy() -> None:
    assert scanner.scanner_strategy(True) == "stream"
    assert scanner.scanner_strategy(False) == "snapshot"


def test_camera_resume_outcome_classification() -> None:
    assert scanner.classify_camera_resume_outcome(None) == "resumed"
    assert scanner.classify_camera_resume_outcome(
        RuntimeError("Camera is not initialized. Call initialize() first.")
    ) == "controller_lost"
    assert scanner.classify_camera_resume_outcome(
        RuntimeError("CAMERA IS NOT INITIALIZED. CALL INITIALIZE() FIRST.")
    ) == "controller_lost"
    assert scanner.classify_camera_resume_outcome(
        RuntimeError("plugin: Camera is not initialized. Call initialize() first. [web]")
    ) == "controller_lost"
    for error in (
        RuntimeError("cameraNotReadable"),
        RuntimeError("cameraAbort"),
        RuntimeError("unexpected failure"),
        RuntimeError("Camera is not initialized"),
        RuntimeError("Call initialize first"),
        RuntimeError("Camera initialize failed"),
    ):
        assert scanner.classify_camera_resume_outcome(error) == "error"

    classifier_source = inspect.getsource(scanner.classify_camera_resume_outcome)
    for forbidden in (
        "QrCameraRuntime",
        "lifecycle_lock",
        "Camera(",
        "home_view",
        "recovery",
        "enumerate",
        "initialize_camera",
        "buscar_qr_llegadas",
    ):
        assert forbidden not in classifier_source, forbidden


def test_stop_camera_capture() -> None:
    async def run_case(
        *, stream_active: bool, should_pause: bool, stream_error: BaseException | None = None,
        pause_error: BaseException | None = None,
    ) -> tuple[scanner.CameraCaptureStopResult, list[str]]:
        calls: list[str] = []

        async def stop() -> None:
            calls.append("stop")
            if stream_error is not None:
                raise stream_error

        async def pause() -> None:
            calls.append("pause")
            if pause_error is not None:
                raise pause_error

        result = await scanner.stop_camera_capture(
            stop_stream=stop,
            pause_preview=pause,
            stream_active=stream_active,
            should_pause=should_pause,
        )
        return result, calls

    result, calls = asyncio.run(run_case(stream_active=False, should_pause=False))
    assert calls == [] and not result.stream_attempted and not result.pause_attempted
    assert result.stream_error is None and result.pause_error is None
    result, calls = asyncio.run(run_case(stream_active=True, should_pause=False))
    assert calls == ["stop"] and result.stream_attempted and not result.pause_attempted
    result, calls = asyncio.run(run_case(stream_active=False, should_pause=True))
    assert calls == ["pause"] and not result.stream_attempted and result.pause_attempted
    result, calls = asyncio.run(run_case(stream_active=True, should_pause=True))
    assert calls == ["stop", "pause"] and result.stream_error is None and result.pause_error is None

    stop_failure = RuntimeError("stop failed")
    result, calls = asyncio.run(run_case(stream_active=True, should_pause=True, stream_error=stop_failure))
    assert calls == ["stop", "pause"] and result.stream_error is stop_failure and result.pause_error is None
    pause_failure = RuntimeError("pause failed")
    result, calls = asyncio.run(run_case(stream_active=True, should_pause=True, pause_error=pause_failure))
    assert calls == ["stop", "pause"] and result.stream_error is None and result.pause_error is pause_failure
    result, calls = asyncio.run(run_case(stream_active=True, should_pause=True, stream_error=stop_failure, pause_error=pause_failure))
    assert calls == ["stop", "pause"] and result.stream_error is stop_failure and result.pause_error is pause_failure

    async def cancel_from_stop() -> None:
        await scanner.stop_camera_capture(
            stop_stream=lambda: (_ for _ in ()).throw(asyncio.CancelledError()),
            pause_preview=lambda: asyncio.sleep(0),
            stream_active=True,
            should_pause=True,
        )

    try:
        asyncio.run(cancel_from_stop())
        raise AssertionError("CancelledError de stop debe propagarse")
    except asyncio.CancelledError:
        pass

    async def cancelled_pause() -> None:
        raise asyncio.CancelledError()

    async def cancel_from_pause() -> None:
        await scanner.stop_camera_capture(
            stop_stream=lambda: asyncio.sleep(0),
            pause_preview=cancelled_pause,
            stream_active=True,
            should_pause=True,
        )

    try:
        asyncio.run(cancel_from_pause())
        raise AssertionError("CancelledError de pause debe propagarse")
    except asyncio.CancelledError:
        pass


def test_camera_description_selection() -> None:
    back = object()
    front = object()
    external = object()

    class CameraDescription:
        def __init__(self, lens_direction: object, name: str, device_id: str) -> None:
            self.lens_direction = lens_direction
            self.name = name
            self.device_id = device_id

    first_back = CameraDescription(back, "first back", "back-1")
    second_back = CameraDescription(back, "second back", "back-2")
    first_front = CameraDescription(front, "front", "front-1")
    external_camera = CameraDescription(external, "external", "usb-1")

    assert scanner.select_camera_description([first_back], back) is first_back
    assert scanner.select_camera_description([first_front, first_back], back) is first_back
    assert scanner.select_camera_description([first_front, first_back, second_back], back) is first_back
    assert scanner.select_camera_description([first_front, external_camera], back) is first_front
    assert scanner.select_camera_description([external_camera], back) is external_camera
    assert scanner.select_camera_description([], back) is None

    cameras = [first_front, first_back, second_back]
    original_order = list(cameras)
    assert scanner.select_camera_description(cameras, back) is first_back
    assert cameras == original_order


def test_camera_initialize_retry_policy() -> None:
    async def no_wait(_seconds: float) -> None:
        return None

    calls = 0
    sleeps: list[float] = []
    callbacks: list[tuple[Exception, int, float]] = []

    def record_callback(error: Exception, attempt: int, delay: float) -> None:
        callbacks.append((error, attempt, delay))

    async def first_success() -> None:
        nonlocal calls
        calls += 1

    async def record_sleep(delay: float) -> None:
        sleeps.append(delay)

    assert asyncio.run(scanner.initialize_camera_with_retry(
        first_success, lambda: True, record_callback, sleep=record_sleep,
    )) == 1
    assert calls == 1 and sleeps == [] and callbacks == []

    calls = 0
    sleeps = []
    callbacks = []
    first_error = RuntimeError("cameraNotReadable")

    async def transient_then_success() -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise first_error

    assert asyncio.run(scanner.initialize_camera_with_retry(
        transient_then_success, lambda: True, record_callback, sleep=record_sleep,
    )) == 2
    assert calls == 2 and sleeps == [0.25] and callbacks == [(first_error, 1, 0.25)]

    calls = 0
    sleeps = []
    callbacks = []
    first_abort = RuntimeError("cameraAbort")
    second_abort = RuntimeError("cameraAbort")

    async def two_transients_then_success() -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise first_abort
        if calls == 2:
            raise second_abort

    assert asyncio.run(scanner.initialize_camera_with_retry(
        two_transients_then_success, lambda: True, record_callback, sleep=record_sleep,
    )) == 3
    assert calls == 3 and sleeps == [0.25, 0.5]
    assert callbacks == [(first_abort, 1, 0.25), (second_abort, 2, 0.5)]

    calls = 0
    sleeps = []
    terminal_error = RuntimeError("cameraNotReadable")

    async def always_transient() -> None:
        nonlocal calls
        calls += 1
        raise terminal_error

    try:
        asyncio.run(scanner.initialize_camera_with_retry(
            always_transient, lambda: True, sleep=record_sleep,
        ))
        raise AssertionError("Se esperaba el tercer error transitorio")
    except RuntimeError as ex:
        assert ex is terminal_error and calls == 3 and sleeps == [0.25, 0.5]

    calls = 0
    sleeps = []
    non_transient = RuntimeError("permissionDenied")

    async def fail_without_retry() -> None:
        nonlocal calls
        calls += 1
        raise non_transient

    try:
        asyncio.run(scanner.initialize_camera_with_retry(
            fail_without_retry, lambda: True, sleep=record_sleep,
        ))
        raise AssertionError("Se esperaba error no transitorio")
    except RuntimeError as ex:
        assert ex is non_transient and calls == 1 and sleeps == []

    calls = 0
    assert asyncio.run(scanner.initialize_camera_with_retry(
        first_success, lambda: False, sleep=record_sleep,
    )) is None
    assert calls == 0

    active = {"value": True}
    calls = 0
    sleeps = []

    async def transient_deactivates_in_callback() -> None:
        nonlocal calls
        calls += 1
        raise RuntimeError("cameraNotReadable")

    def deactivate(_ex: Exception, _attempt: int, _delay: float) -> None:
        active["value"] = False

    assert asyncio.run(scanner.initialize_camera_with_retry(
        transient_deactivates_in_callback, lambda: active["value"], deactivate, sleep=record_sleep,
    )) is None
    assert calls == 1 and sleeps == []

    active = {"value": True}
    calls = 0
    sleeps = []

    async def deactivate_during_sleep(delay: float) -> None:
        sleeps.append(delay)
        active["value"] = False

    assert asyncio.run(scanner.initialize_camera_with_retry(
        transient_deactivates_in_callback, lambda: active["value"], sleep=deactivate_during_sleep,
    )) is None
    assert calls == 1 and sleeps == [0.25]

    cancel_callbacks: list[tuple[Exception, int, float]] = []

    def record_cancel_callback(error: Exception, attempt: int, delay: float) -> None:
        cancel_callbacks.append((error, attempt, delay))

    async def cancelled_initialize() -> None:
        raise asyncio.CancelledError()

    try:
        asyncio.run(scanner.initialize_camera_with_retry(
            cancelled_initialize, lambda: True, record_cancel_callback, sleep=no_wait,
        ))
        raise AssertionError("Se esperaba CancelledError desde initialize_once")
    except asyncio.CancelledError:
        assert cancel_callbacks == []

    async def transient_then_cancelled_sleep(_delay: float) -> None:
        raise asyncio.CancelledError()

    calls = 0
    try:
        asyncio.run(scanner.initialize_camera_with_retry(
            always_transient, lambda: True, record_cancel_callback, sleep=transient_then_cancelled_sleep,
        ))
        raise AssertionError("Se esperaba CancelledError durante sleep")
    except asyncio.CancelledError:
        assert calls == 1

    calls = 0
    sleeps = []
    try:
        asyncio.run(scanner.initialize_camera_with_retry(
            always_transient,
            lambda: True,
            max_attempts=2,
            retry_delays=(0.75,),
            sleep=record_sleep,
        ))
        raise AssertionError("Se esperaba error terminal con max_attempts=2")
    except RuntimeError as ex:
        assert ex is terminal_error and calls == 2 and sleeps == [0.75]


def test_camera_enumeration_retry_policy() -> None:
    async def no_wait(_seconds: float) -> None:
        return None

    async def first_try() -> list[str]:
        first_try.calls += 1
        return ["camera"]
    first_try.calls = 0
    result = asyncio.run(scanner.enumerate_cameras_with_retry(
        first_try, lambda: True, lambda _retry, _maximum: None, sleep=no_wait,
    ))
    assert result and result.cameras == ["camera"] and result.attempts == 1 and first_try.calls == 1

    async def transient_once() -> list[str]:
        transient_once.calls += 1
        if transient_once.calls == 1:
            raise RuntimeError("cameraNotReadable, device is not ready")
        return ["camera"]
    transient_once.calls = 0
    retries: list[tuple[int, int]] = []
    result = asyncio.run(scanner.enumerate_cameras_with_retry(
        transient_once, lambda: True, lambda retry, maximum: retries.append((retry, maximum)), sleep=no_wait,
    ))
    assert result and result.attempts == 2 and transient_once.calls == 2 and retries == [(1, 3)]

    async def transient_twice() -> list[str]:
        transient_twice.calls += 1
        if transient_twice.calls < 3:
            raise RuntimeError("cameraNotReadable: device is not ready")
        return ["camera"]
    transient_twice.calls = 0
    retries = []
    result = asyncio.run(scanner.enumerate_cameras_with_retry(
        transient_twice, lambda: True, lambda retry, maximum: retries.append((retry, maximum)), sleep=no_wait,
    ))
    assert result and result.attempts == 3 and transient_twice.calls == 3 and retries == [(1, 3), (2, 3)]

    async def abort_once() -> list[str]:
        abort_once.calls += 1
        if abort_once.calls == 1:
            raise RuntimeError("cameraAbort: device is being released")
        return ["camera"]
    abort_once.calls = 0
    result = asyncio.run(scanner.enumerate_cameras_with_retry(
        abort_once, lambda: True, lambda _retry, _maximum: None, sleep=no_wait,
    ))
    assert result and result.attempts == 2 and abort_once.calls == 2
    assert scanner.is_camera_transient(RuntimeError("cameraNotReadable"))
    assert scanner.is_camera_transient(RuntimeError("cameraAbort"))

    async def always_not_readable() -> list[str]:
        always_not_readable.calls += 1
        raise RuntimeError("cameraNotReadable, device is not ready")
    always_not_readable.calls = 0
    try:
        asyncio.run(scanner.enumerate_cameras_with_retry(
            always_not_readable, lambda: True, lambda _retry, _maximum: None, sleep=no_wait,
        ))
        raise AssertionError("Se esperaba cameraNotReadable tras el tercer intento")
    except RuntimeError as ex:
        assert scanner.is_camera_not_readable(ex) and always_not_readable.calls == 3

    for message in ("permissionDenied", "NotAllowedError", "SecurityError", "cameraNotFound", "unexpected failure"):
        calls = 0
        async def non_retryable() -> list[str]:
            nonlocal calls
            calls += 1
            raise RuntimeError(message)
        try:
            asyncio.run(scanner.enumerate_cameras_with_retry(
                non_retryable, lambda: True, lambda _retry, _maximum: None, sleep=no_wait,
            ))
            raise AssertionError(f"Se esperaba error no reintentable: {message}")
        except RuntimeError:
            assert calls == 1


def test_camera_enumeration_stops_during_backoff() -> None:
    active = {"value": True}
    calls = 0

    async def not_readable() -> list[str]:
        nonlocal calls
        calls += 1
        raise RuntimeError("cameraNotReadable, device is not ready")

    async def cancel_during_sleep(_seconds: float) -> None:
        active["value"] = False

    result = asyncio.run(scanner.enumerate_cameras_with_retry(
        not_readable, lambda: active["value"], lambda _retry, _maximum: None, sleep=cancel_during_sleep,
    ))
    assert result is None and calls == 1


def test_snapshot_polling_detects_once_and_stops() -> None:
    snapshots = iter([b"without-qr", b"valid-qr", b"must-not-be-read"])
    accepted: list[str] = []

    async def take_picture() -> bytes:
        return next(snapshots)

    with patch.object(scanner, "decode_qr_frame", side_effect=[None, "T3A1"]):
        result = asyncio.run(scanner.poll_qr_snapshots(
            take_picture, lambda: True,
            lambda code: accepted.append(code) is None,
            lambda _attempt, _error: None, sleep=_without_wait,
        ))
    assert result is True and accepted == ["T3A1"]


def test_snapshot_polling_ignores_late_result_after_cancel_or_event_change() -> None:
    active = {"value": True}
    accepted: list[str] = []

    async def take_picture() -> bytes:
        active["value"] = False
        return b"late-qr"

    with patch.object(scanner, "decode_qr_frame", return_value="T3A1"):
        result = asyncio.run(scanner.poll_qr_snapshots(
            take_picture, lambda: active["value"],
            lambda code: accepted.append(code) is None,
            lambda _attempt, _error: None, sleep=_without_wait,
        ))
    assert result is False and accepted == []


def test_snapshot_polling_retries_one_error_and_stops_after_persistent_errors() -> None:
    attempts = iter([RuntimeError("temporary"), b"valid-qr"])
    errors: list[int] = []

    async def temporary_failure() -> bytes:
        item = next(attempts)
        if isinstance(item, Exception):
            raise item
        return item

    with patch.object(scanner, "decode_qr_frame", return_value="T3A1"):
        result = asyncio.run(scanner.poll_qr_snapshots(
            temporary_failure, lambda: True, lambda _code: True,
            lambda attempt, _error: errors.append(attempt), sleep=_without_wait,
        ))
    assert result is True and errors == [1]

    persistent_errors: list[int] = []

    async def persistent_failure() -> bytes:
        raise RuntimeError("camera unavailable")

    result = asyncio.run(scanner.poll_qr_snapshots(
        persistent_failure, lambda: True, lambda _code: True,
        lambda attempt, _error: persistent_errors.append(attempt),
        max_consecutive_errors=3, sleep=_without_wait,
    ))
    assert result is False and persistent_errors == [1, 2, 3]


def test_take_qr_snapshot_and_snapshot_runtime_ownership() -> None:
    async def capture() -> bytes:
        return b"snapshot"

    assert asyncio.run(scanner.take_qr_snapshot(capture, 7)) == b"snapshot"

    async def failed_capture() -> bytes:
        raise RuntimeError("capture failed")

    async def assert_capture_error_propagates() -> None:
        try:
            await scanner.take_qr_snapshot(failed_capture, 7)
            raise AssertionError("Se esperaba error de captura")
        except RuntimeError as ex:
            assert str(ex) == "capture failed"

    asyncio.run(assert_capture_error_propagates())

    async def valid_then_detected() -> None:
        owner = SnapshotOwner()
        snapshots = iter([b"without-qr", b"valid-qr"])
        accepted: list[str] = []
        result = await scanner.run_qr_snapshot_polling(
            owner,
            lambda: _next_snapshot(snapshots),
            lambda: True,
            lambda code: accepted.append(code) is None,
            lambda _attempt, _error: None,
            generation=7,
            interval_seconds=0,
        )
        assert result is True and accepted == ["T3A1"] and owner.snapshot_task is None

    async def expired_session() -> None:
        owner = SnapshotOwner()
        calls = 0

        async def should_not_capture() -> bytes:
            nonlocal calls
            calls += 1
            return b"unexpected"

        result = await scanner.run_qr_snapshot_polling(
            owner,
            should_not_capture,
            lambda: False,
            lambda _code: True,
            lambda _attempt, _error: None,
            generation=8,
            interval_seconds=0,
        )
        assert result is False and calls == 0 and owner.snapshot_task is None

    async def retry_and_terminal_error() -> None:
        owner = SnapshotOwner()
        outcomes = iter([RuntimeError("temporary"), b"valid-qr"])
        errors: list[int] = []

        async def take_with_one_error() -> bytes:
            item = next(outcomes)
            if isinstance(item, Exception):
                raise item
            return item

        with patch.object(scanner, "decode_qr_frame", return_value="T3A1"):
            result = await scanner.run_qr_snapshot_polling(
                owner,
                take_with_one_error,
                lambda: True,
                lambda _code: True,
                lambda attempt, _error: errors.append(attempt),
                generation=9,
                interval_seconds=0,
            )
        assert result is True and errors == [1] and owner.snapshot_task is None

        owner = SnapshotOwner()
        terminal_errors: list[int] = []

        async def always_fails() -> bytes:
            raise RuntimeError("camera unavailable")

        result = await scanner.run_qr_snapshot_polling(
            owner,
            always_fails,
            lambda: True,
            lambda _code: True,
            lambda attempt, _error: terminal_errors.append(attempt),
            generation=10,
            interval_seconds=0,
            max_consecutive_errors=3,
        )
        assert result is False and terminal_errors == [1, 2, 3] and owner.snapshot_task is None

    async def cancellation_and_new_task_ownership() -> None:
        owner = SnapshotOwner()
        started = asyncio.Event()
        never_finish = asyncio.Event()

        async def blocking_capture() -> bytes:
            started.set()
            await never_finish.wait()
            return b"unreachable"

        polling_task = asyncio.create_task(
            scanner.run_qr_snapshot_polling(
                owner,
                blocking_capture,
                lambda: True,
                lambda _code: True,
                lambda _attempt, _error: None,
                generation=11,
                interval_seconds=0,
            )
        )
        await started.wait()
        assert owner.snapshot_task is polling_task
        polling_task.cancel()
        try:
            await polling_task
            raise AssertionError("Se esperaba CancelledError")
        except asyncio.CancelledError:
            pass
        assert owner.snapshot_task is None

        owner = SnapshotOwner()
        replacement_wait = asyncio.Event()
        replacement_task = asyncio.create_task(replacement_wait.wait())
        active = {"value": True}

        async def replace_task_then_invalidate() -> bytes:
            owner.snapshot_task = replacement_task
            active["value"] = False
            return b"late"

        result = await scanner.run_qr_snapshot_polling(
            owner,
            replace_task_then_invalidate,
            lambda: active["value"],
            lambda _code: True,
            lambda _attempt, _error: None,
            generation=12,
            interval_seconds=0,
        )
        assert result is False and owner.snapshot_task is replacement_task
        replacement_task.cancel()
        try:
            await replacement_task
        except asyncio.CancelledError:
            pass

    async def _next_snapshot(snapshots: object) -> bytes:
        return next(snapshots)  # type: ignore[arg-type, return-value]

    with patch.object(scanner, "decode_qr_frame", side_effect=[None, "T3A1"]):
        asyncio.run(valid_then_detected())
    asyncio.run(expired_session())
    asyncio.run(retry_and_terminal_error())
    asyncio.run(cancellation_and_new_task_ownership())


def main() -> int:
    test_decoder()
    test_gate_throttles_and_accepts_once()
    test_stream_frame_processing_preserves_gate_and_worker_boundaries()
    test_stream_or_snapshot_strategy()
    test_camera_resume_outcome_classification()
    test_stop_camera_capture()
    test_camera_description_selection()
    test_camera_initialize_retry_policy()
    test_camera_enumeration_retry_policy()
    test_camera_enumeration_stops_during_backoff()
    test_snapshot_polling_detects_once_and_stops()
    test_snapshot_polling_ignores_late_result_after_cancel_or_event_change()
    test_snapshot_polling_retries_one_error_and_stops_after_persistent_errors()
    test_take_qr_snapshot_and_snapshot_runtime_ownership()
    print("OK - QR scanner decoder, stream/snapshot and duplicate/throttle gate tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
