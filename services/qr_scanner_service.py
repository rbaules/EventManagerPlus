from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
import re
from threading import Lock
from time import monotonic
from typing import Awaitable, Callable, Protocol, TypeVar

import cv2
import numpy as np


T = TypeVar("T")


class SnapshotTaskOwner(Protocol):
    """Contrato mínimo para conservar la única referencia de polling."""

    snapshot_task: asyncio.Task[object] | None


@dataclass(frozen=True)
class CameraEnumerationResult:
    """Resultado de la enumeración, incluyendo los intentos realmente hechos."""

    cameras: list[object]
    attempts: int


def is_camera_not_readable(error: Exception) -> bool:
    """Reconoce exclusivamente el código estable emitido por camera_web.

    Flet propaga el error remoto como texto en las versiones actualmente
    soportadas. Se acepta sólo el token completo ``cameraNotReadable``; errores
    de permiso, seguridad, dispositivo ausente o texto desconocido no pasan.
    """
    code = str(getattr(error, "code", "") or getattr(error, "error_code", ""))
    if code == "cameraNotReadable":
        return True
    text = str(error)
    return bool(re.search(r"(?:^|[\s(:,])cameraNotReadable(?:$|[\s,):])", text))


def is_camera_transient(error: Exception) -> bool:
    """Errores Web que pueden aparecer mientras el dispositivo se libera."""
    if is_camera_not_readable(error):
        return True
    code = str(getattr(error, "code", "") or getattr(error, "error_code", ""))
    if code == "cameraAbort":
        return True
    return bool(re.search(r"(?:^|[\s(:,])cameraAbort(?:$|[\s,):])", str(error)))


async def enumerate_cameras_with_retry(
    enumerate_cameras: Callable[[], Awaitable[list[T]]],
    is_active: Callable[[], bool],
    on_transient_error: Callable[[int, int], None],
    *,
    max_attempts: int = 3,
    retry_delays: tuple[float, ...] = (0.4, 0.8),
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> CameraEnumerationResult | None:
    """Enumera cámaras con retry sólo para ``cameraNotReadable``.

    Devuelve ``None`` si la sesión deja de ser vigente durante un backoff. El
    resto de excepciones, incluido el tercer ``cameraNotReadable``, se propaga
    a la capa de UI para su único fallback manual.
    """
    if max_attempts < 1:
        raise ValueError("max_attempts debe ser mayor o igual a 1")
    for attempt in range(1, max_attempts + 1):
        if not is_active():
            return None
        try:
            cameras = await enumerate_cameras()
            return CameraEnumerationResult(cameras=list(cameras), attempts=attempt)
        except Exception as ex:
            if not is_camera_transient(ex) or attempt == max_attempts:
                raise
            on_transient_error(attempt, max_attempts)
            delay = retry_delays[min(attempt - 1, len(retry_delays) - 1)]
            await sleep(delay)
    return None


async def initialize_camera_with_retry(
    initialize_once: Callable[[], Awaitable[object]],
    is_active: Callable[[], bool],
    on_transient_error: Callable[[Exception, int, float], None] | None = None,
    *,
    max_attempts: int = 3,
    retry_delays: tuple[float, ...] = (0.25, 0.5),
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> int | None:
    """Inicializa mediante un callback, con retry sólo ante errores transitorios."""
    if max_attempts < 1:
        raise ValueError("max_attempts debe ser mayor o igual a 1")
    for attempt in range(1, max_attempts + 1):
        if not is_active():
            return None
        try:
            await initialize_once()
            return attempt
        except Exception as ex:
            if not is_camera_transient(ex) or attempt == max_attempts:
                raise
            delay = retry_delays[min(attempt - 1, len(retry_delays) - 1)]
            if on_transient_error is not None:
                on_transient_error(ex, attempt, delay)
            if not is_active():
                return None
            await sleep(delay)
            print("[QR-SCAN][LIFECYCLE] initialize end")
    return None


def select_camera_description(
    cameras: list[T],
    preferred_lens: object,
) -> T | None:
    """Selecciona la primera cámara del lente preferido o la primera disponible."""
    for camera in cameras:
        if getattr(camera, "lens_direction", None) == preferred_lens:
            return camera
    return cameras[0] if cameras else None


def _normalizar_codigo_qr(value: str | None) -> str | None:
    codigo = (value or "").strip().upper()
    return codigo if re.fullmatch(r"[A-Z0-9]{4}", codigo) else None


def decode_qr_frame(image_bytes: bytes | None) -> str | None:
    """Decodifica un frame JPEG/PNG en memoria; nunca persiste ni transmite la imagen."""
    if not image_bytes:
        return None
    try:
        image = cv2.imdecode(np.frombuffer(image_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            return None
        decoded, _points, _straight = cv2.QRCodeDetector().detectAndDecode(image)
        return _normalizar_codigo_qr(decoded)
    except Exception as ex:
        print("[QR-SCAN][ERROR] Frame decode failed:", type(ex).__name__)
        return None


@dataclass
class QrFrameGate:
    """Limita trabajo de frames y acepta un único código válido por sesión."""

    throttle_seconds: float = 0.25
    active: bool = False
    decode_busy: bool = False
    code_already_detected: bool = False
    _last_attempt: float = field(default=0.0, init=False, repr=False)
    _lock: Lock = field(default_factory=Lock, init=False, repr=False)

    def start(self) -> None:
        with self._lock:
            self.active = True
            self.decode_busy = False
            self.code_already_detected = False
            self._last_attempt = 0.0

    def stop(self) -> None:
        with self._lock:
            self.active = False
            self.decode_busy = False

    def try_begin_decode(self, now: float | None = None) -> bool:
        current = monotonic() if now is None else now
        with self._lock:
            if (
                not self.active
                or self.decode_busy
                or self.code_already_detected
                or current - self._last_attempt < self.throttle_seconds
            ):
                return False
            self.decode_busy = True
            self._last_attempt = current
            return True

    def finish_decode(self, codigo: str | None) -> str | None:
        with self._lock:
            self.decode_busy = False
            if not self.active or self.code_already_detected or not codigo:
                return None
            self.code_already_detected = True
            return codigo


def _decode_and_accept_qr_frame(
    image_bytes: bytes | None,
    gate: QrFrameGate,
    on_code_accepted: Callable[[str], None],
) -> None:
    """Decodifica un frame ya admitido por el gate y entrega sólo un código válido."""
    codigo = decode_qr_frame(image_bytes)
    accepted = gate.finish_decode(codigo)
    if accepted:
        on_code_accepted(accepted)


def process_qr_camera_frame(
    image_bytes: bytes | None,
    is_session_current: Callable[[], bool],
    gate: QrFrameGate,
    schedule_worker: Callable[[Callable[[], None]], None],
    on_code_accepted: Callable[[str], None],
) -> None:
    """Conserva el flujo stream: validar sesión, abrir gate y programar un worker."""
    if not is_session_current() or not gate.try_begin_decode():
        return
    schedule_worker(lambda: _decode_and_accept_qr_frame(image_bytes, gate, on_code_accepted))


def scanner_strategy(streaming_supported: bool) -> str:
    """Selecciona el transporte de cámara sin cambiar el decoder ni el flujo de negocio."""
    return "stream" if streaming_supported else "snapshot"


async def poll_qr_snapshots(
    take_picture: Callable[[], Awaitable[bytes]],
    is_active: Callable[[], bool],
    on_code: Callable[[str], bool],
    on_capture_error: Callable[[int, Exception], None],
    *,
    interval_seconds: float = 0.65,
    max_consecutive_errors: int = 3,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> bool:
    """Hace capturas secuenciales en memoria hasta detectar un QR o invalidar la sesión.

    No conoce Flet, Supabase ni estado de UI. La persona llamadora decide si el código
    sigue vigente mediante ``on_code`` y puede invalidar resultados tardíos con
    ``is_active``. Sólo hay un ``take_picture`` pendiente por iteración.
    """
    consecutive_errors = 0
    while is_active():
        image_bytes: bytes | None = None
        try:
            image_bytes = await take_picture()
        except Exception as ex:
            if not is_active():
                return False
            consecutive_errors += 1
            on_capture_error(consecutive_errors, ex)
            if consecutive_errors >= max_consecutive_errors:
                return False
            await sleep(interval_seconds)
            continue

        if not is_active():
            return False
        consecutive_errors = 0
        codigo = await asyncio.to_thread(decode_qr_frame, image_bytes)
        image_bytes = None
        if not is_active():
            return False
        if codigo and on_code(codigo):
            return True
        await sleep(interval_seconds)
    return False


async def take_qr_snapshot(
    take_picture: Callable[[], Awaitable[bytes]],
    generation: int,
) -> bytes:
    """Captura un snapshot sin adquirir lifecycle_lock ni conocer Camera."""
    print(
        "[QR-SCAN][LIFECYCLE] take_picture begin",
        f"generation={generation}",
        f"task_id={id(asyncio.current_task())}",
    )
    try:
        return await take_picture()
    finally:
        print(
            "[QR-SCAN][LIFECYCLE] take_picture end",
            f"generation={generation}",
            f"task_id={id(asyncio.current_task())}",
        )


async def run_qr_snapshot_polling(
    runtime: SnapshotTaskOwner,
    take_picture: Callable[[], Awaitable[bytes]],
    is_session_current: Callable[[], bool],
    on_code: Callable[[str], bool],
    on_capture_error: Callable[[int, Exception], None],
    *,
    generation: int,
    interval_seconds: float = 0.65,
    max_consecutive_errors: int = 3,
) -> bool:
    """Orquesta polling y conserva en runtime la única task de snapshot."""
    polling_task = asyncio.current_task()
    runtime.snapshot_task = polling_task
    try:
        return await poll_qr_snapshots(
            lambda: take_qr_snapshot(take_picture, generation),
            is_session_current,
            on_code,
            on_capture_error,
            interval_seconds=interval_seconds,
            max_consecutive_errors=max_consecutive_errors,
        )
    finally:
        if runtime.snapshot_task is polling_task:
            runtime.snapshot_task = None
        print(
            "[QR-SCAN][LIFECYCLE] polling task finished",
            f"generation={generation}",
            f"task_id={id(polling_task)}",
        )
