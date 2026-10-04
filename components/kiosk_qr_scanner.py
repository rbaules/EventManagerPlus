from __future__ import annotations

import asyncio
import traceback
from collections.abc import Awaitable, Callable
from typing import Any

import flet as ft
import flet_camera as fcam

from services.qr_camera_runtime import QrCameraRuntime
from services.qr_scanner_service import (
    QrFrameGate,
    classify_camera_resume_outcome,
    enumerate_cameras_with_retry,
    initialize_camera_with_retry,
    is_camera_transient,
    process_qr_camera_frame,
    run_qr_snapshot_polling,
    scanner_strategy,
    select_camera_description,
    stop_camera_capture,
)


def kiosk_camera_error_message(error: Exception | str | None) -> str:
    detail = str(error or "").lower()
    if "permission" in detail or "denied" in detail:
        return "Necesitamos permiso para usar la cámara. Intenta nuevamente."
    if "not found" in detail or "no camera" in detail:
        return "No encontramos una cámara disponible. Intenta nuevamente."
    return "No pudimos iniciar la cámara. Intenta nuevamente."


class KioskQrScanner:
    """Adapter Flet del scanner reutilizable, aislado de negocio y de Home."""

    def __init__(
        self,
        *,
        page: ft.Page,
        on_qr_finalized: Callable[[str], None],
        on_camera_error: Callable[[str], None],
        camera: Any | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        create_host: bool = True,
    ) -> None:
        self.page = page
        self.runtime = QrCameraRuntime()
        self.gate = QrFrameGate()
        self._on_qr_finalized = on_qr_finalized
        self._on_camera_error = on_camera_error
        self._sleep = sleep
        self.active = False
        self.stream_active = False
        self.strategy = "none"
        self._session_key: tuple[int, int] | None = None
        self._closing = False
        self._last_snapshot_diagnostic: tuple[str, object] | None = None
        self.camera = camera or fcam.Camera(
            preview_enabled=True,
            content=ft.Container(
                content=ft.Text("Cámara Kiosco", color=ft.Colors.ON_SURFACE),
                alignment=ft.Alignment.CENTER,
                border=ft.Border.all(width=2, color=ft.Colors.PRIMARY),
                border_radius=18,
            ),
            on_state_change=self._on_camera_state_change,
            on_stream_image=self._on_stream_image,
            height=280,
            data={"kiosk": "camera"},
        )
        self.host: ft.Container | None = None
        if create_host:
            # El host y la Camera permanecen visibles/montados. Fuera de
            # WELCOME_SCAN se ocultan con opacidad/tamaño, nunca visible=False.
            self.host = ft.Container(
                content=self.camera,
                visible=True,
                opacity=1,
                width=560,
                height=300,
                ignore_interactions=False,
                alignment=ft.Alignment.CENTER,
                border_radius=18,
                clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
                bgcolor=ft.Colors.BLACK,
                data={"kiosk": "persistent_camera_host"},
            )

    def set_preview_visible(self, visible: bool) -> None:
        if self.host is None:
            return
        self.host.visible = True
        self.host.opacity = 1 if visible else 0
        self.host.width = 560 if visible else 1
        self.host.height = 300 if visible else 1
        self.host.ignore_interactions = not visible

    def start(self) -> None:
        self.page.run_task(self.start_scan)

    def restart(self) -> None:
        self.page.run_task(self.restart_scan)

    def close(self) -> None:
        if not self._page_connection_available():
            self._invalidate_after_disconnect()
            return
        self.page.run_task(self.stop_scan)

    def _page_connection_available(self) -> bool:
        """Evita crear una coroutine cuando Flet ya cerró el transporte."""
        try:
            session = self.page.session
        except (AttributeError, RuntimeError):
            # Los doubles sin sesión representan una Page activa en pruebas.
            return True
        if session is None:
            return False
        try:
            return session.connection is not None
        except (AttributeError, RuntimeError):
            return True

    def _invalidate_after_disconnect(self) -> None:
        self.active = False
        self.gate.stop()
        self._session_key = None
        self.runtime.invalidate()
        polling_task = self.runtime.snapshot_task
        if polling_task is not None and not polling_task.done():
            polling_task.cancel()
        self.runtime.snapshot_task = None
        self.stream_active = False

    def _log_snapshot_diagnostic(self, status: str, detail: object) -> None:
        marker = (status, detail)
        if marker == self._last_snapshot_diagnostic:
            return
        self._last_snapshot_diagnostic = marker
        print("[KIOSK-QR][SNAPSHOT]", status, detail)

    async def _take_snapshot(
        self,
        generation: int,
        session_key: tuple[int, int],
    ) -> bytes:
        payload = await self.camera.take_picture()
        if not isinstance(payload, bytes):
            self._log_snapshot_diagnostic("payload_invalid_type", type(payload).__name__)
            raise TypeError("Camera.take_picture() must return bytes")
        self._log_snapshot_diagnostic(
            "capture_payload",
            (
                f"generation={generation}",
                f"type={type(payload).__name__}",
                f"bytes={len(payload)}",
                f"session_current={self._session_is_current(generation, session_key)}",
            ),
        )
        return payload

    def _session_is_current(self, generation: int, session_key: tuple[int, int]) -> bool:
        return self.runtime.is_scanner_session_current(
            generation,
            self.active,
            session_key,
            self._session_key,
            self._session_key,
        )

    def _camera_is_mounted(self) -> bool:
        try:
            return self.camera.page is self.page
        except RuntimeError:
            return False

    async def start_scan(self) -> None:
        if self.active or self._closing:
            return
        self.gate = QrFrameGate()
        self.gate.start()
        generation = self.runtime.invalidate()
        session_key = (id(self), generation)
        self._session_key = session_key
        self.active = True
        self.stream_active = False
        self.set_preview_visible(True)
        try:
            # Permite que el host persistente llegue al cliente Web antes de
            # solicitar el controller nativo.
            await self._sleep(0.3)
            if not self._session_is_current(generation, session_key):
                return
            if not self._camera_is_mounted():
                raise RuntimeError("Camera is not mounted")
            await self._initialize_or_resume(generation, session_key)
        except Exception as ex:
            await self._fail_session(ex, generation, session_key)

    async def restart_scan(self) -> None:
        await self.stop_scan()
        await self.start_scan()

    async def _initialize_or_resume(self, generation: int, session_key: tuple[int, int]) -> None:
        recovery_from_resume = False
        if self.runtime.controller_initialized:
            try:
                async with self.runtime.lifecycle_lock:
                    if not self._session_is_current(generation, session_key):
                        return
                    await self.camera.resume_preview()
                if not self._session_is_current(generation, session_key):
                    return
                self.runtime.preview_paused = False
                if self.strategy not in {"stream", "snapshot"}:
                    raise RuntimeError("Camera initialized without capture strategy")
                await self._start_capture(generation, session_key, self.strategy)
                return
            except Exception as ex:
                if classify_camera_resume_outcome(ex) == "error":
                    raise
                self.runtime.controller_initialized = False
                self.runtime.preview_paused = False
                recovery_from_resume = True

        async with self.runtime.lifecycle_lock:
            if not self._session_is_current(generation, session_key):
                return
            description = self.runtime.camera_description if recovery_from_resume else None
            if description is None:
                enumeration = await enumerate_cameras_with_retry(
                    self.camera.get_available_cameras,
                    lambda: self._session_is_current(generation, session_key),
                    lambda retry, maximum: print(
                        "[KIOSK-QR][WARN] camera discovery retry",
                        f"{retry}/{maximum}",
                    ),
                    sleep=self._sleep,
                )
                if enumeration is None:
                    return
                description = select_camera_description(
                    enumeration.cameras,
                    fcam.CameraLensDirection.BACK,
                )
                if description is None:
                    raise RuntimeError("No camera available")
                self.runtime.camera_description = description

            async def initialize_once() -> None:
                await self.camera.initialize(
                    description,
                    fcam.ResolutionPreset.LOW,
                    enable_audio=False,
                    image_format_group=fcam.ImageFormatGroup.JPEG,
                )

            attempts = await initialize_camera_with_retry(
                initialize_once,
                lambda: self._session_is_current(generation, session_key),
                lambda _error, attempt, delay: print(
                    "[KIOSK-QR][WARN] camera initialize retry",
                    f"{attempt}/3 delay={delay}",
                ),
                sleep=self._sleep,
            )
            if attempts is None:
                return
        if not self._session_is_current(generation, session_key):
            return
        self.runtime.controller_initialized = True
        self.runtime.preview_paused = False
        self.strategy = scanner_strategy(await self.camera.supports_image_streaming())
        await self._start_capture(generation, session_key, self.strategy)

    async def _start_capture(
        self,
        generation: int,
        session_key: tuple[int, int],
        strategy: str,
    ) -> None:
        if not self._session_is_current(generation, session_key):
            return
        if strategy == "stream":
            await self.camera.start_image_stream()
            self.stream_active = True
            return

        def capture_error(attempt: int, error: Exception) -> None:
            if attempt >= 3 and self._session_is_current(generation, session_key):
                async def fail_capture_session() -> None:
                    await self._fail_session(error, generation, session_key)

                self.page.run_task(fail_capture_session)

        def on_snapshot_code(code: str) -> bool:
            return self.on_snapshot_code(code, generation, session_key)

        await run_qr_snapshot_polling(
            self.runtime,
            lambda: self._take_snapshot(generation, session_key),
            lambda: self._session_is_current(generation, session_key),
            on_snapshot_code,
            capture_error,
            lambda code: self._log_snapshot_decoded(code, generation, session_key),
            generation=generation,
        )

    def on_snapshot_code(
        self,
        code: str,
        generation: int,
        session_key: tuple[int, int],
    ) -> bool:
        print("[KIOSK-QR][SNAPSHOT] on_code_enter")
        result = self._accept_snapshot_code(code, generation, session_key)
        print("[KIOSK-QR][SNAPSHOT] on_code_return", f"value={result}")
        return result

    def _log_snapshot_decoded(
        self,
        code: str | None,
        generation: int,
        session_key: tuple[int, int],
    ) -> None:
        session_current = self._session_is_current(generation, session_key)
        self._log_snapshot_diagnostic(
            "decode_result",
            (
                "qr_found" if code else "no_qr",
                f"session_current={session_current}",
            ),
        )
        if code and not session_current:
            self._log_snapshot_diagnostic(
                "code_gate",
                "session_current=False accepted=False "
                "reason=session_not_current_before_gate",
            )

    def _accept_snapshot_code(
        self,
        code: str,
        generation: int,
        session_key: tuple[int, int],
    ) -> bool:
        session_current = self._session_is_current(generation, session_key)
        print("[KIOSK-QR][SNAPSHOT] accept_snapshot_code enter")
        print(
            "[KIOSK-QR][SNAPSHOT] accept_snapshot_code",
            f"session_current={session_current}",
        )
        print(
            "[KIOSK-QR][SNAPSHOT] accept_snapshot_code",
            f"gate_begin={self.gate.active and not self.gate.decode_busy and not self.gate.code_already_detected}",
        )
        if not session_current:
            reason = "session_not_current"
        elif not self.gate.active:
            reason = "gate_inactive"
        elif self.gate.decode_busy:
            reason = "gate_busy"
        elif self.gate.code_already_detected:
            reason = "code_already_detected"
        else:
            reason = "callback_rejected"
        accepted = self.runtime.accept_snapshot_code(
            code,
            generation,
            self.active,
            session_key,
            self._session_key,
            self._session_key,
            self.gate,
            self._accept_code,
        )
        print(
            "[KIOSK-QR][SNAPSHOT] accept_snapshot_code",
            f"gate_finish={self.gate.code_already_detected}",
        )
        print(
            "[KIOSK-QR][SNAPSHOT] accept_snapshot_code",
            f"technical_callback={accepted}",
        )
        self._log_snapshot_diagnostic(
            "code_gate",
            f"session_current={session_current} accepted={accepted} "
            f"reason={'accepted' if accepted else reason}",
        )
        print("[KIOSK-QR][SNAPSHOT] accept_snapshot_code", f"return={accepted}")
        return accepted

    def _on_stream_image(self, event: fcam.CameraImageEvent) -> None:
        generation = self.runtime.generation
        session_key = self._session_key
        if session_key is None:
            return
        process_qr_camera_frame(
            event.bytes,
            lambda: self._session_is_current(generation, session_key),
            self.gate,
            self.page.run_thread,
            lambda code: self._accept_code(code, generation, session_key),
        )

    def _accept_code(self, code: str, generation: int, session_key: tuple[int, int]) -> bool:
        if not self._session_is_current(generation, session_key):
            return False
        self.active = False
        self.gate.stop()
        self.runtime.invalidate()

        async def finalize_code() -> None:
            await self._finalize_code(code)

        self.page.run_task(finalize_code)
        return True

    async def _finalize_code(self, code: str) -> None:
        await self._cleanup_capture()
        print("[KIOSK-QR][SNAPSHOT] kiosk_callback", "called")
        self._on_qr_finalized(code)

    async def stop_scan(self) -> None:
        self.active = False
        self.gate.stop()
        self._session_key = None
        self.runtime.invalidate()
        await self._cleanup_capture()

    async def _cleanup_capture(self) -> None:
        if self._closing:
            return
        self._closing = True
        try:
            polling_task = self.runtime.snapshot_task
            current_task = asyncio.current_task()
            if polling_task is not None and polling_task is not current_task and not polling_task.done():
                polling_task.cancel()
                try:
                    await polling_task
                except asyncio.CancelledError:
                    pass
            if self._camera_is_mounted():
                async with self.runtime.lifecycle_lock:
                    result = await stop_camera_capture(
                        stop_stream=self.camera.stop_image_stream,
                        pause_preview=self.camera.pause_preview,
                        stream_active=self.stream_active,
                        should_pause=self.runtime.controller_initialized,
                    )
                    if result.pause_attempted and result.pause_error is None:
                        self.runtime.preview_paused = True
                    if result.pause_error is not None:
                        self.runtime.controller_initialized = False
                    if result.stream_error is not None:
                        print("[KIOSK-QR][WARN] stream stop failed", type(result.stream_error).__name__)
            self.stream_active = False
            self.runtime.snapshot_task = None
        finally:
            self._closing = False

    async def _fail_session(
        self,
        error: Exception,
        generation: int,
        session_key: tuple[int, int],
    ) -> None:
        if not self._session_is_current(generation, session_key):
            return
        print("[KIOSK-QR][ERROR] camera session failed", type(error).__name__)
        print(traceback.format_exc())
        self.active = False
        self.gate.stop()
        self.runtime.invalidate()
        await self._cleanup_capture()
        self._on_camera_error(kiosk_camera_error_message(error))

    def _on_camera_state_change(self, event: fcam.CameraStateEvent) -> None:
        self.runtime.preview_paused = bool(event.is_preview_paused)
        if event.has_error:
            self.runtime.controller_initialized = False
            generation = self.runtime.generation
            session_key = self._session_key
            if self.active and session_key is not None:
                async def fail_camera_state() -> None:
                    await self._fail_session(
                        RuntimeError(event.error_description or "Camera error"),
                        generation,
                        session_key,
                    )

                self.page.run_task(fail_camera_state)
        elif event.is_initialized:
            self.runtime.controller_initialized = True
