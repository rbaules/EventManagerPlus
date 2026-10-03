from __future__ import annotations

import asyncio
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


def main() -> int:
    test_decoder()
    test_gate_throttles_and_accepts_once()
    test_stream_frame_processing_preserves_gate_and_worker_boundaries()
    test_stream_or_snapshot_strategy()
    test_camera_enumeration_retry_policy()
    test_camera_enumeration_stops_during_backoff()
    test_snapshot_polling_detects_once_and_stops()
    test_snapshot_polling_ignores_late_result_after_cancel_or_event_change()
    test_snapshot_polling_retries_one_error_and_stops_after_persistent_errors()
    print("OK - QR scanner decoder, stream/snapshot and duplicate/throttle gate tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
