from __future__ import annotations

import asyncio
import json
import re
import time
import traceback
from collections.abc import Awaitable, Callable
from typing import Any

import flet as ft
import flet_camera as fcam

from services.kiosk_diagnostic_log import kiosk_log
from services.qr_camera_runtime import QrCameraRuntime
from services.qr_scanner_service import (
    QrFrameGate,
    decode_qr_frame,
    enumerate_cameras_with_retry,
    initialize_camera_with_retry,
    is_camera_transient,
    process_qr_camera_frame,
    scanner_strategy,
    select_front_first_camera_description,
    stop_camera_capture,
)


KIOSK_CAMERA_DESCRIPTION_CACHE_KEY = "eventplus.kiosk.camera_description.v1"


class _CachedCameraDescriptionUnavailable(RuntimeError):
    """Internal signal: retry the stable discovery path, not the UI error path."""


class _FastResumeFallback(RuntimeError):
    """Internal signal to leave the warm path before one full restart."""


class _WarmResumeSnapshotCaptureFailure(RuntimeError):
    """Preserve the native snapshot error until the warm-resume fallback logs it."""

    def __init__(self, error: Exception) -> None:
        super().__init__(str(error))
        self.error = error


def _description_to_cache_value(description: fcam.CameraDescription) -> str | None:
    """Persist only the fields Flet 0.85.3 needs to recreate a description."""
    try:
        name = str(description.name)
        lens_direction = str(description.lens_direction.value)
        sensor_orientation = int(description.sensor_orientation)
        lens_type = str(description.lens_type.value)
    except (AttributeError, TypeError, ValueError):
        return None
    if not name:
        return None
    return json.dumps(
        {
            "name": name,
            "lens_direction": lens_direction,
            "sensor_orientation": sensor_orientation,
            "lens_type": lens_type,
        },
        separators=(",", ":"),
        sort_keys=True,
    )


def _description_from_cache_value(value: object) -> fcam.CameraDescription | None:
    """Validate and reconstruct the exact Flet CameraDescription value object."""
    if not isinstance(value, str):
        return None
    try:
        payload = json.loads(value)
        if not isinstance(payload, dict):
            return None
        name = payload["name"]
        lens_direction = payload["lens_direction"]
        sensor_orientation = payload["sensor_orientation"]
        lens_type = payload["lens_type"]
        if not isinstance(name, str) or not name:
            return None
        if not isinstance(sensor_orientation, int):
            return None
        return fcam.CameraDescription(
            name=name,
            lens_direction=fcam.CameraLensDirection(lens_direction),
            sensor_orientation=sensor_orientation,
            lens_type=fcam.CameraLensType(lens_type),
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None


def _select_camera_description_with_preference(
    cameras: list[Any],
    preference: fcam.CameraDescription | None,
) -> Any | None:
    """Apply the Kiosk FRONT-first policy to this Page's discovered cameras."""
    return select_front_first_camera_description(cameras, preference)


def _cached_description_requires_discovery(error: Exception) -> bool:
    """Recognize only cache/device failures for the discovery fallback.

    Permission and camera availability changes are device-state changes: discovery
    runs once to obtain the native error from the normal path instead of masking it.
    Other unexpected initialize failures still reach the controlled UI fallback.
    """
    if isinstance(error, _CachedCameraDescriptionUnavailable):
        return True
    detail = str(error).lower()
    markers = (
        "cameramissingmetadata",
        "make sure to call availablecameras before creating a camera",
        "cameranotreadable",
        "cameraabort",
        "camera not found",
        "no camera",
        "not available",
        "not found",
        "permission",
        "denied",
        "description",
    )
    return any(marker in detail for marker in markers)


def _is_camera_missing_metadata(error: Exception) -> bool:
    detail = str(error).lower()
    return (
        "cameramissingmetadata" in detail
        or "make sure to call availablecameras before creating a camera" in detail
    )


def _safe_camera_error_detail(error: Exception) -> str:
    """Keep a useful plugin error diagnostic without exposing sensitive text."""
    detail = " ".join(str(error).split())
    if re.search(
        r"(?:token|cookie|authorization|bearer|password|pin|https?://)",
        detail,
        re.IGNORECASE,
    ):
        return "<redacted_sensitive_error>"
    return detail[:240] or "<empty>"


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
        startup_origin: float | None = None,
        camera_description_preferences: Any | None = None,
        e2e_profiler: Any | None = None,
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
        self._admin_suspended = False
        self._startup_id = 0
        self._startup_task: Any | None = None
        self._startup_generation: tuple[int, int, str] | None = None
        self._perf_startups: dict[int, dict[str, Any]] = {}
        self._startup_origin = startup_origin
        self._camera_description_preferences = camera_description_preferences
        self._e2e_profiler = e2e_profiler
        self._native_ready_generation: int | None = None
        self._last_snapshot_diagnostic: tuple[str, object] | None = None
        self._last_camera_state: dict[str, bool | None] = {}
        self._snapshot_controller_recovery_active = False
        self._snapshot_keepalive_active = False
        self._snapshot_polling_owner_token: object | None = None
        self._snapshot_polling_finished: asyncio.Event | None = None
        self._snapshot_recovery_task: asyncio.Task[object] | None = None
        self._snapshot_recovery_owner_token: object | None = None
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
        if camera is not None and hasattr(self.camera, "on_state_change"):
            # Los doubles y adaptadores inyectados deben observar el mismo
            # contrato nativo de readiness que la Camera creada por Kiosk.
            self.camera.on_state_change = self._on_camera_state_change
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
        self._log_camera_identity("preview_visible" if visible else "preview_hidden")

    def start(self) -> None:
        self._schedule_startup("initial")

    def restart(self) -> None:
        self._schedule_startup("reset", restart=True)

    def resume_for_next_guest(self) -> None:
        """Reactivate capture after the normal QR warm-idle transition."""
        startup_task = self._startup_task
        if self._closing or self.active or (startup_task is not None and not startup_task.done()):
            kiosk_log(
                self.page,
                "KIOSK-QR",
                "full_restart_fallback",
                **self._diagnostic_fields(reason="scanner_not_idle"),
            )
            self.restart()
            return

        async def resume_next_guest() -> None:
            await self._resume_warm_capture()

        self._startup_id += 1
        startup_id = self._startup_id
        print(f"[KIOSK-QR][CYCLE] next_guest begin startup_id={startup_id}")
        self._startup_task = self.page.run_task(resume_next_guest)

    def _warm_resume_ready(self) -> bool:
        polling_task = self.runtime.snapshot_task
        snapshot_polling_ready = (
            polling_task is not None and not polling_task.done()
            if self.strategy == "snapshot"
            else polling_task is None or polling_task.done()
        )
        return (
            not self._closing
            and not self.active
            and not self._admin_suspended
            and self._page_connection_available()
            and self._camera_is_mounted()
            and self.runtime.controller_initialized
            and not self.runtime.preview_paused
            and self.runtime.camera_description is not None
            and self.runtime.camera_metadata_ready
            and snapshot_polling_ready
        )

    async def _resume_warm_capture(self) -> None:
        """Rearm capture without pausing, discovering, or initializing Camera."""
        startup_id = self._startup_id
        began = time.perf_counter()
        fallback_reason: str | None = None
        operation = "validate_preconditions"
        cached_strategy: str | None = None
        generation: int | None = None
        session_key: tuple[int, int] | None = None
        try:
            if not self._warm_resume_ready():
                fallback_reason = "warm_controller_or_capture_not_reusable"
                raise _FastResumeFallback(fallback_reason)
            async with self.runtime.lifecycle_lock:
                if not self._warm_resume_ready():
                    fallback_reason = "warm_controller_changed_while_waiting_lock"
                    raise _FastResumeFallback(fallback_reason)
                generation = self.runtime.invalidate()
                session_key = (id(self), generation)
                self._session_key = session_key
                self.gate = QrFrameGate()
                self.gate.start()
                was_keepalive = self._snapshot_keepalive_active
                self._snapshot_keepalive_active = False
                self.active = True
                self.stream_active = False
                self.set_preview_visible(True)
                self._perf_startups = {
                    generation: {
                        "startup_id": startup_id,
                        "source": "warm_resume",
                        "startup_begin": began,
                        "first_capture_completed": False,
                    }
                }
                self._startup_generation = (startup_id, generation, "warm_resume")
                self._perf_mark(generation, "startup_begin")
                kiosk_log(
                    self.page,
                    "KIOSK-QR",
                    "warm_resume_begin",
                    **self._diagnostic_fields(generation=generation, startup_id=startup_id),
                )
            if not self._session_is_current(generation, session_key):
                return
            operation = "validate_cached_strategy"
            cached_strategy = self.strategy if isinstance(self.strategy, str) else None
            if cached_strategy not in {"stream", "snapshot"}:
                fallback_reason = "cached_strategy_invalid"
                raise _FastResumeFallback(fallback_reason)
            if cached_strategy == "snapshot":
                polling_task = self.runtime.snapshot_task
                if polling_task is None or polling_task.done():
                    fallback_reason = "persistent_snapshot_task_unavailable"
                    raise _FastResumeFallback(fallback_reason)
            kiosk_log(
                self.page,
                "KIOSK-QR",
                "warm_resume_ready",
                **self._diagnostic_fields(
                    generation=generation,
                    startup_id=startup_id,
                    strategy_cached=cached_strategy,
                    elapsed_ms=round((time.perf_counter() - began) * 1000, 1),
                ),
            )
            operation = (
                "start_image_stream"
                if cached_strategy == "stream"
                else "start_snapshot_polling"
            )
            if cached_strategy == "snapshot":
                self._startup_generation = None
                self._perf_mark(generation, "capture_ready")
                kiosk_log(
                    self.page,
                    "KIOSK-QR",
                    "snapshot_gate_opened",
                    **self._diagnostic_fields(
                        generation=generation,
                        startup_id=startup_id,
                        snapshot_task_id=id(self.runtime.snapshot_task),
                        snapshot_task_done=False,
                    ),
                )
                kiosk_log(
                    self.page,
                    "KIOSK-QR",
                    "snapshot_polling_reused",
                    **self._diagnostic_fields(
                        generation=generation,
                        startup_id=startup_id,
                        snapshot_task_id=id(self.runtime.snapshot_task),
                        snapshot_task_done=False,
                    ),
                )
                if was_keepalive:
                    kiosk_log(
                        self.page,
                        "KIOSK-QR",
                        "snapshot_keepalive_exit",
                        **self._diagnostic_fields(
                            generation=generation,
                            startup_id=startup_id,
                            snapshot_task_id=id(self.runtime.snapshot_task),
                        ),
                    )
                return
            await self._start_capture(generation, session_key, cached_strategy)
        except Exception as ex:
            diagnostic_error = (
                ex.error if isinstance(ex, _WarmResumeSnapshotCaptureFailure) else ex
            )
            if isinstance(ex, _WarmResumeSnapshotCaptureFailure):
                operation = "take_picture"
            if fallback_reason is None:
                fallback_reason = type(diagnostic_error).__name__
            failure_fields = self._warm_resume_failure_fields(
                operation=operation,
                error=diagnostic_error,
                strategy_cached=cached_strategy,
                generation=generation,
                startup_id=startup_id,
            )
            self.active = False
            self.gate.stop()
            self._session_key = None
            if generation is not None:
                self.runtime.invalidate()
            kiosk_log(
                self.page,
                "KIOSK-QR",
                "warm_resume_failed",
                **failure_fields,
            )
            kiosk_log(
                self.page,
                "KIOSK-QR",
                "full_restart_fallback",
                **self._diagnostic_fields(reason=fallback_reason, startup_id=startup_id),
            )
            await self.restart_scan()
        finally:
            if self._startup_task is asyncio.current_task():
                self._startup_task = None
            print(f"[KIOSK-QR][CYCLE] next_guest end startup_id={startup_id}")

    async def suspend_for_admin(self) -> None:
        """Stop QR capture while retaining the mounted Camera/controller.

        This is intentionally narrower than ``stop_scan``/``close``: the
        administrative PIN is an in-place Kiosk overlay, not a route exit or a
        camera recovery.  It therefore keeps controller metadata, generation,
        preview state and the persistent host reusable.
        """
        if self._admin_suspended:
            return
        self._admin_suspended = True
        self.active = False
        self.gate.stop()
        await self._suspend_capture_for_phase()
        print("[KIOSK-QR][ADMIN] capture_suspended")

    async def resume_after_admin(self) -> None:
        """Resume QR capture after an administrative overlay is dismissed."""
        if not self._admin_suspended:
            return
        self._admin_suspended = False
        if self._closing or not self._page_connection_available() or not self._camera_is_mounted():
            return
        generation = self.runtime.generation
        session_key = self._session_key
        if (
            session_key is None
            or not self.runtime.controller_initialized
            or self.runtime.preview_paused
        ):
            # No live controller is available to reuse.  This follows the
            # ordinary scanner startup/recovery path rather than inventing a
            # parallel camera lifecycle.
            self._schedule_startup("admin_resume")
            return
        self.gate = QrFrameGate()
        self.gate.start()
        self._snapshot_keepalive_active = False
        self.active = True
        self.stream_active = False
        try:
            self.strategy = await self._resolve_capture_strategy(generation)
            await self._start_capture(generation, session_key, self.strategy)
            print("[KIOSK-QR][ADMIN] capture_resumed")
        except Exception as ex:
            await self._fail_session(ex, generation, session_key)

    def close(self, *, disconnected: bool = False) -> None:
        if disconnected or not self._page_connection_available():
            self._invalidate_after_disconnect()
            return

        async def stop_after_page_close() -> None:
            await self.stop_scan(reason="page_close")

        self.page.run_task(stop_after_page_close)

    def lifecycle_diagnostic_state(self) -> dict[str, object]:
        """Entrega estado Python para logs sin invocar el control Camera."""
        snapshot_task = self.runtime.snapshot_task
        startup_task = self._startup_task
        return {
            "snapshot_task_active": snapshot_task is not None and not snapshot_task.done(),
            "stream_active": self.stream_active,
            "startup_task_active": startup_task is not None and not startup_task.done(),
            "controller_initialized": self.runtime.controller_initialized,
            "preview_paused": self.runtime.preview_paused,
            "generation": self.runtime.generation,
        }

    def _diagnostic_fields(self, **fields: object) -> dict[str, object]:
        """Return PII-free identifiers for a structured Kiosk log record."""
        try:
            control_id = getattr(self.camera, "_i", None)
        except RuntimeError:
            control_id = None
        result: dict[str, object] = {
            "scanner_id": id(self),
            "camera_id": id(self.camera),
            "control_id": control_id,
            "generation": self.runtime.generation,
            "startup_id": self._startup_id,
        }
        result.update(fields)
        return result

    def _warm_resume_failure_fields(
        self,
        *,
        operation: str,
        error: Exception,
        strategy_cached: str | None,
        generation: int | None,
        startup_id: int,
    ) -> dict[str, object]:
        """Return the PII-safe technical context for a warm-resume fallback."""
        fields: dict[str, object] = {
            "reason": type(error).__name__,
            "operation": operation,
            "exception_type": type(error).__name__,
            "sanitized_error": _safe_camera_error_detail(error),
            "strategy_cached": strategy_cached or "none",
            "stream_active": self.stream_active,
            "controller_initialized": self.runtime.controller_initialized,
            "preview_paused": self.runtime.preview_paused,
            "camera_metadata_ready": self.runtime.camera_metadata_ready,
            "camera_description_cached": self.runtime.camera_description is not None,
            "generation": generation,
            "startup_id": startup_id,
        }
        fields.update(self._last_camera_state)
        return self._diagnostic_fields(**fields)

    def recover_after_reconnect(self) -> None:
        """Recupera una sesión de scanner cuyo cliente Web pudo perderse."""
        # Un F5 puede conservar esta instancia Python pero destruir el
        # controller nativo del navegador. Nunca se reutiliza ese controller.
        self._log_reconnect_runtime("begin")
        self.runtime.controller_initialized = False
        self.runtime.preview_paused = False
        self.runtime.camera_description = None
        self.runtime.camera_metadata_ready = False
        self.runtime.invalidate()
        self._session_key = None
        self._snapshot_keepalive_active = False
        self.stream_active = False
        print("[KIOSK-QR][RECONNECT] runtime_invalidated")
        self._schedule_startup("reconnect")
        self._log_reconnect_runtime("end")

    def _schedule_startup(self, source: str, *, restart: bool = False) -> None:
        startup_task = self._startup_task
        if self.active or self._closing or (startup_task is not None and not startup_task.done()):
            print(f"[KIOSK-QR][STARTUP] skipped source={source} scanner_already_active")
            return
        self._startup_id += 1
        startup_id = self._startup_id

        async def run_startup() -> None:
            print(f"[KIOSK-QR][STARTUP] startup_id={startup_id} source={source} begin")
            if source == "reconnect":
                print(f"[KIOSK-QR][RECONNECT] recovery_id={startup_id} begin")
                print("[KIOSK-QR][RECONNECT] phase=WELCOME_SCAN")
            try:
                if restart or source == "reconnect":
                    await self._suspend_capture_for_phase()
                await self.start_scan(startup_id=startup_id, startup_source=source)
                if self._startup_id != startup_id:
                    print(f"[KIOSK-QR][STARTUP] startup_id={startup_id} stale ignored")
            except asyncio.CancelledError:
                print(f"[KIOSK-QR][STARTUP] startup_id={startup_id} cancelled reason=disconnect")
                if source == "reconnect":
                    print(f"[KIOSK-QR][RECONNECT] recovery_id={startup_id} cancelled reason=disconnect")
                raise
            finally:
                if self._startup_id == startup_id:
                    self._startup_task = None
                print(f"[KIOSK-QR][STARTUP] startup_id={startup_id} cleanup_complete")
                if source == "reconnect":
                    print(f"[KIOSK-QR][RECONNECT] recovery_id={startup_id} cleanup_complete")

        self._startup_task = self.page.run_task(run_startup)

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
        self._log_disconnect_invalidation("before")
        self.active = False
        self.gate.stop()
        self._session_key = None
        self._snapshot_keepalive_active = False
        self.runtime.invalidate()
        self.runtime.controller_initialized = False
        self.runtime.preview_paused = False
        self.runtime.camera_description = None
        self.runtime.camera_metadata_ready = False
        try:
            current_task = asyncio.current_task()
        except RuntimeError:
            current_task = None
        startup_task = self._startup_task
        if startup_task is not None and startup_task is not current_task and not startup_task.done():
            startup_task.cancel()
        # El siguiente connect debe poder crear recovery nuevo sin esperar que
        # la coroutine cancelada termine su unwind.
        self._startup_task = None
        polling_task = self.runtime.snapshot_task
        if polling_task is not None and not polling_task.done():
            polling_task.cancel()
        self.runtime.snapshot_task = None
        self._snapshot_polling_owner_token = None
        self._snapshot_polling_finished = None
        recovery_task = self._snapshot_recovery_task
        if recovery_task is not None and not recovery_task.done():
            recovery_task.cancel()
        self._snapshot_recovery_task = None
        self._snapshot_recovery_owner_token = None
        self._snapshot_controller_recovery_active = False
        self.stream_active = False
        self._log_disconnect_invalidation("after")

    def _log_disconnect_invalidation(self, stage: str) -> None:
        """Registra el estado afectado por un disconnect sin modificarlo."""
        host = self.host
        try:
            host_mounted = host is not None and host.page is self.page
        except RuntimeError:
            host_mounted = False
        print(
            "[KIOSK-QR][INVALIDATE] "
            f"stage={stage} reason=page_disconnect "
            f"startup_id={self._startup_id} generation={self.runtime.generation} "
            f"controller_initialized={self.runtime.controller_initialized} "
            f"preview_paused={self.runtime.preview_paused} "
            f"camera_description_cached={self.runtime.camera_description is not None} "
            f"camera_mounted={self._camera_is_mounted()} "
            f"host_mounted={host_mounted}"
        )
        kiosk_log(
            self.page,
            "KIOSK-QR",
            "disconnect_invalidation",
            **self._diagnostic_fields(
                stage=stage,
                controller_initialized=self.runtime.controller_initialized,
                preview_paused=self.runtime.preview_paused,
                camera_description_cached=self.runtime.camera_description is not None,
                camera_mounted=self._camera_is_mounted(),
                host_mounted=host_mounted,
            ),
        )

    def _log_reconnect_runtime(self, stage: str) -> None:
        startup_task = self._startup_task
        startup_task_active = startup_task is not None and not startup_task.done()
        print(
            "[KIOSK-QR][RECONNECT] "
            f"stage={stage} full_initialization_source=reconnect "
            f"startup_id={self._startup_id} generation={self.runtime.generation} "
            f"controller_initialized={self.runtime.controller_initialized} "
            f"preview_paused={self.runtime.preview_paused} "
            f"camera_description_cached={self.runtime.camera_description is not None} "
            f"startup_task_active={startup_task_active}"
        )
        kiosk_log(
            self.page,
            "KIOSK-QR",
            "reconnect",
            **self._diagnostic_fields(
                stage=stage,
                controller_initialized=self.runtime.controller_initialized,
                preview_paused=self.runtime.preview_paused,
                camera_description_cached=self.runtime.camera_description is not None,
                startup_task_active=startup_task_active,
            ),
        )

    def _log_snapshot_diagnostic(self, status: str, detail: object) -> None:
        marker = (status, detail)
        if marker == self._last_snapshot_diagnostic:
            return
        self._last_snapshot_diagnostic = marker
        print("[KIOSK-QR][SNAPSHOT]", status, detail)

    def _log_camera_identity(self, stage: str) -> None:
        """Registra identidad Python/Flet; no la confunde con controller Web."""
        host = self.host
        try:
            control_id = getattr(self.camera, "_i", None)
        except RuntimeError:
            control_id = None
        try:
            host_mounted = host is not None and host.page is self.page
        except RuntimeError:
            host_mounted = False
        print(
            "[KIOSK-QR][IDENTITY] "
            f"stage={stage} startup_id={self._startup_id} "
            f"generation={self.runtime.generation} "
            f"camera_python_id={id(self.camera)} control_id={control_id} "
            f"page_python_id={id(self.page)} host_python_id={id(host) if host else None} "
            f"camera_mounted={self._camera_is_mounted()} "
            f"host_mounted={host_mounted} "
            f"controller_initialized={self.runtime.controller_initialized} "
            f"preview_paused={self.runtime.preview_paused} "
            f"camera_description_cached={self.runtime.camera_description is not None} "
            f"host_visible={getattr(host, 'visible', None)} "
            f"host_opacity={getattr(host, 'opacity', None)} "
            f"host_size={getattr(host, 'width', None)}x{getattr(host, 'height', None)}"
        )

    def _perf_mark(self, generation: int, stage: str) -> float:
        entry = self._perf_startups.get(generation)
        now = time.perf_counter()
        if entry is not None:
            if stage == "preview_ready" and "preview_ready" in entry:
                return now
            entry[stage] = now
            checkpoint = ""
            if stage == "polling_started":
                checkpoint = f" total_to_polling_ms={(now - entry['startup_begin']) * 1000:.1f}"
            elif stage == "preview_ready":
                checkpoint = f" total_to_preview_ready_ms={(now - entry['startup_begin']) * 1000:.1f}"
            print(
                f"[KIOSK-QR][PERF] startup_id={entry['startup_id']} "
                f"source={entry['source']} stage={stage} "
                f"total_ms={(now - entry['startup_begin']) * 1000:.1f}{checkpoint}"
            )
            if stage in {
                "startup_begin",
                "camera_discovery_begin",
                "camera_selected",
                "initialize_begin",
                "capture_ready",
            }:
                kiosk_log(
                    self.page,
                    "KIOSK-QR",
                    stage,
                    **self._diagnostic_fields(
                        generation=generation,
                        startup_id=entry["startup_id"],
                        startup_source=entry["source"],
                        total_ms=round((now - entry["startup_begin"]) * 1000, 1),
                    ),
                )
            origin = self._startup_origin or entry["startup_begin"]
            print(
                "[KIOSK-STARTUP][PERF] "
                f"stage={stage} total_ms={(now - origin) * 1000:.1f}"
            )
            if self._e2e_profiler is not None:
                e2e_stages = {
                    "camera_discovery_begin": "E8_CAMERA_DISCOVERY_BEGIN",
                    "initialize_begin": "E9_CAMERA_INITIALIZE_BEGIN",
                }
                e2e_stage = e2e_stages.get(stage)
                if e2e_stage is not None:
                    self._e2e_profiler.mark(e2e_stage)
            if stage == "polling_started":
                print(
                    "[KIOSK-STARTUP][READY] "
                    f"total_ms={(now - origin) * 1000:.1f}"
                )
                if self._e2e_profiler is not None:
                    self._e2e_profiler.ready()
        return now

    def _perf_duration(self, generation: int, stage: str, began: float) -> None:
        entry = self._perf_startups.get(generation)
        if entry is None:
            return
        now = time.perf_counter()
        checkpoint = ""
        if stage == "first_take_picture_end":
            checkpoint = f" total_to_first_capture_ms={(now - entry['startup_begin']) * 1000:.1f}"
        print(
            f"[KIOSK-QR][PERF] startup_id={entry['startup_id']} "
            f"source={entry['source']} stage={stage} "
            f"duration_ms={(now - began) * 1000:.1f} "
            f"total_ms={(now - entry['startup_begin']) * 1000:.1f}{checkpoint}"
        )
        if stage in {"mount_delay_end", "camera_discovery_end", "initialize_end"}:
            kiosk_log(
                self.page,
                "KIOSK-QR",
                stage,
                **self._diagnostic_fields(
                    generation=generation,
                    startup_id=entry["startup_id"],
                    startup_source=entry["source"],
                    duration_ms=round((now - began) * 1000, 1),
                    total_ms=round((now - entry["startup_begin"]) * 1000, 1),
                ),
            )

    def _log_discovery_retry(self, generation: int, retry: int, maximum: int) -> None:
        print("[KIOSK-QR][WARN] camera discovery retry", f"{retry}/{maximum}")
        entry = self._perf_startups.get(generation)
        if entry is not None:
            print(
                f"[KIOSK-QR][PERF] startup_id={entry['startup_id']} "
                f"source={entry['source']} stage=camera_discovery_retry "
                f"attempt={retry}/{maximum} backoff_ms={((0.4, 0.8)[min(retry - 1, 1)]) * 1000:.1f}"
            )

    def _log_initialize_retry(
        self,
        generation: int,
        error: Exception,
        attempt: int,
        delay: float,
    ) -> None:
        print("[KIOSK-QR][WARN] camera initialize retry", f"{attempt}/3 delay={delay}")
        entry = self._perf_startups.get(generation)
        if entry is not None:
            print(
                f"[KIOSK-QR][PERF] startup_id={entry['startup_id']} "
                f"source={entry['source']} stage=initialize_retry "
                f"attempt={attempt}/3 backoff_ms={delay * 1000:.1f} "
                f"error={type(error).__name__}"
            )

    def _log_discovery_call_context(
        self,
        generation: int,
        session_key: tuple[int, int],
        attempt: int,
        phase: str,
        error: Exception | None = None,
    ) -> None:
        """Registra el límite Python/cliente de la invocación de discovery.

        Esta traza no participa en las decisiones de lifecycle: permite
        distinguir una espera previa local de una espera dentro del método
        remoto ``Camera.get_available_cameras()``.
        """
        entry = self._perf_startups.get(generation, {})
        try:
            route = getattr(self.page, "route", None)
        except RuntimeError:
            route = None
        try:
            connected = self._page_connection_available()
        except RuntimeError:
            connected = False
        host = self.host
        try:
            host_mounted = host is not None and host.page is self.page
        except RuntimeError:
            host_mounted = False
        try:
            overlay = getattr(self.page, "overlay", [])
            camera_in_overlay = self.camera in overlay
        except (AttributeError, RuntimeError, TypeError):
            camera_in_overlay = False
        control_id = getattr(self.camera, "_i", None)
        details = [
            f"startup_id={entry.get('startup_id', 0)}",
            f"source={entry.get('source', 'direct')}",
            f"phase={phase}",
            f"attempt={attempt}",
            f"generation={generation}",
            f"session_current={self._session_is_current(generation, session_key)}",
            f"camera_id={id(self.camera)}",
            f"control_id={control_id}",
            f"page_id={id(self.page)}",
            f"camera_mounted={self._camera_is_mounted()}",
            f"host_mounted={host_mounted}",
            f"camera_in_overlay={camera_in_overlay}",
            f"page_connected={connected}",
            f"route={route}",
            f"lifecycle_lock_locked={self.runtime.lifecycle_lock.locked()}",
            f"controller_initialized={self.runtime.controller_initialized}",
            f"cached_description={self.runtime.camera_description is not None}",
            f"runtime_metadata_ready={self.runtime.camera_metadata_ready}",
            f"host_visible={getattr(host, 'visible', None)}",
            f"host_opacity={getattr(host, 'opacity', None)}",
            f"host_size={getattr(host, 'width', None)}x{getattr(host, 'height', None)}",
            f"host_ignore_interactions={getattr(host, 'ignore_interactions', None)}",
        ]
        if error is not None:
            details.append(f"error={type(error).__name__}")
            details.append(f"message={_safe_camera_error_detail(error)}")
        print("[KIOSK-QR][DISCOVERY]", " ".join(details))

    async def _take_snapshot(
        self,
        generation: int,
        session_key: tuple[int, int],
    ) -> bytes:
        entry = self._perf_startups.get(generation)
        first_capture = entry is not None and not entry["first_capture_completed"]
        if first_capture:
            first_capture_began = self._perf_mark(generation, "first_take_picture_begin")
        payload = await self.camera.take_picture()
        if first_capture:
            if isinstance(payload, bytes) and payload:
                entry["first_capture_completed"] = True
                self._perf_duration(generation, "first_take_picture_end", first_capture_began)
            else:
                self._perf_duration(generation, "first_take_picture_no_bytes", first_capture_began)
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

    async def start_scan(
        self,
        *,
        startup_id: int | None = None,
        startup_source: str = "direct",
    ) -> None:
        if self.active or self._closing or self._admin_suspended:
            return
        self.gate = QrFrameGate()
        self.gate.start()
        generation = self.runtime.invalidate()
        self._perf_startups = {
            generation: {
                "startup_id": startup_id if startup_id is not None else 0,
                "source": startup_source,
                "startup_begin": time.perf_counter(),
                "first_capture_completed": False,
            }
        }
        self._perf_mark(generation, "startup_begin")
        if startup_id is not None:
            self._startup_generation = (startup_id, generation, startup_source)
        session_key = (id(self), generation)
        self._session_key = session_key
        self.active = True
        self.stream_active = False
        self.set_preview_visible(True)
        self._log_camera_identity(f"startup_{startup_source}")
        if startup_source == "reset":
            print(
                "[KIOSK-QR][RESET] pre_start "
                f"controller_initialized={self.runtime.controller_initialized} "
                f"preview_paused={self.runtime.preview_paused} "
                f"camera_description_cached={self.runtime.camera_description is not None} "
                f"generation={generation} full_initialize=True"
            )
        try:
            # Permite que el host persistente llegue al cliente Web antes de
            # solicitar el controller nativo. En reset el mismo control ya
            # persistente sigue montado, por lo que no requiere esa espera.
            if startup_source != "reset":
                mount_delay_began = self._perf_mark(generation, "mount_delay_begin")
                await self._sleep(0.3)
                self._perf_duration(generation, "mount_delay_end", mount_delay_began)
            if not self._session_is_current(generation, session_key):
                return
            if not self._camera_is_mounted():
                raise RuntimeError("Camera is not mounted")
            self._perf_mark(generation, "T5_camera_control_mounted")
            await self._initialize_or_resume(generation, session_key, startup_source)
        except Exception as ex:
            await self._fail_session(ex, generation, session_key)

    async def restart_scan(self, *, preserve_snapshot_recovery: bool = False) -> None:
        await self._suspend_capture_for_phase(
            preserve_snapshot_recovery=preserve_snapshot_recovery
        )
        await self.start_scan(startup_source="reset")

    async def _initialize_or_resume(
        self,
        generation: int,
        session_key: tuple[int, int],
        startup_source: str,
    ) -> None:
            # El controller se perdió: este ya no es el fast path. Da al
            # cliente el mismo turno de estabilización de una apertura real.

        async with self.runtime.lifecycle_lock:
            if not self._session_is_current(generation, session_key):
                return
            description = None
            description_discovered = False
            persisted_preference = await self._load_cached_camera_description()
            if persisted_preference is None:
                print("[KIOSK-QR] camera cache miss")
            if (
                startup_source != "reset"
                and self.runtime.camera_metadata_ready
                and self.runtime.camera_description is not None
            ):
                description = self.runtime.camera_description
                print("[KIOSK-QR] camera cache hit")
                print("[KIOSK-QR] runtime_metadata_ready=true")
                initialize_began = self._perf_mark(generation, "initialize_begin")
                try:
                    await self._initialize_cached_description(description, generation)
                except Exception as ex:
                    self._perf_duration(generation, "initialize_end", initialize_began)
                    if not _cached_description_requires_discovery(ex):
                        raise
                    self.runtime.camera_metadata_ready = False
                    if _is_camera_missing_metadata(ex):
                        print("[KIOSK-QR] cached metadata unavailable; falling back to discovery")
                    else:
                        await self._clear_cached_camera_description()
                        print("[KIOSK-QR] cached initialize failed; falling back to discovery")
                    description = None
                else:
                    self._perf_duration(generation, "initialize_end", initialize_began)
                    print("[KIOSK-QR] cached initialize success")
            else:
                print("[KIOSK-QR] runtime_metadata_ready=false")
            if description is None:
                discovery_began = self._perf_mark(generation, "camera_discovery_begin")
                discovery_attempt = 0

                async def enumerate_once() -> list[Any]:
                    nonlocal discovery_attempt
                    discovery_attempt += 1
                    attempt_began = time.perf_counter()
                    try:
                        self._log_discovery_call_context(
                            generation,
                            session_key,
                            discovery_attempt,
                            "call_enter",
                        )
                        cameras = await self.camera.get_available_cameras()
                    except Exception as ex:
                        self._log_discovery_call_context(
                            generation,
                            session_key,
                            discovery_attempt,
                            "call_error",
                            ex,
                        )
                        raise
                    else:
                        self._log_discovery_call_context(
                            generation,
                            session_key,
                            discovery_attempt,
                            "call_return",
                        )
                        return cameras
                    finally:
                        self._perf_duration(
                            generation,
                            f"camera_discovery_attempt_{discovery_attempt}",
                            attempt_began,
                        )

                enumeration = await enumerate_cameras_with_retry(
                    enumerate_once,
                    lambda: self._session_is_current(generation, session_key),
                    lambda retry, maximum: self._log_discovery_retry(generation, retry, maximum),
                    sleep=self._sleep,
                )
                self._perf_duration(generation, "camera_discovery_end", discovery_began)
                if enumeration is None:
                    return
                self.runtime.camera_metadata_ready = True
                description = _select_camera_description_with_preference(
                    enumeration.cameras,
                    persisted_preference,
                )
                if description is None:
                    raise RuntimeError("No camera available")
                lens_direction = getattr(getattr(description, "lens_direction", None), "value", "unknown")
                print(
                    "[KIOSK-QR][PERF] camera_selected "
                    f"generation={generation} lens_direction={lens_direction}"
                )
                self._perf_mark(generation, "camera_selected")
                self.runtime.camera_description = description
                description_discovered = True

            async def initialize_once() -> None:
                self._native_ready_generation = None
                attempt_began = time.perf_counter()
                try:
                    await self.camera.initialize(
                        description,
                        fcam.ResolutionPreset.LOW,
                        enable_audio=False,
                        image_format_group=fcam.ImageFormatGroup.JPEG,
                    )
                finally:
                    self._perf_duration(generation, "initialize_attempt", attempt_began)

            if description_discovered:
                initialize_began = self._perf_mark(generation, "initialize_begin")
                attempts = await initialize_camera_with_retry(
                    initialize_once,
                    lambda: self._session_is_current(generation, session_key),
                    lambda error, attempt, delay: self._log_initialize_retry(
                        generation, error, attempt, delay
                    ),
                    sleep=self._sleep,
                )
                self._perf_duration(generation, "initialize_end", initialize_began)
                if attempts is None:
                    return
        if not self._session_is_current(generation, session_key):
            return
        if self._native_ready_generation != generation:
            raise RuntimeError("Camera initialize returned without native ready state")
        if description_discovered:
            await self._save_cached_camera_description(description)
        self._perf_mark(generation, "initialize_return")
        self.strategy = await self._resolve_capture_strategy(generation)
        await self._start_capture(generation, session_key, self.strategy)

    async def _resolve_capture_strategy(self, generation: int) -> str:
        began = self._perf_mark(generation, "supports_image_streaming_begin")
        streaming_supported = await self.camera.supports_image_streaming()
        self._perf_duration(generation, "supports_image_streaming_end", began)
        strategy = scanner_strategy(streaming_supported)
        print(f"[KIOSK-QR][PERF] capture_strategy generation={generation} strategy={strategy}")
        kiosk_log(
            self.page,
            "KIOSK-QR",
            "capture_strategy",
            **self._diagnostic_fields(generation=generation, strategy=strategy),
        )
        return strategy

    async def _initialize_cached_description(
        self,
        description: fcam.CameraDescription,
        generation: int,
    ) -> None:
        """One direct attempt; cache failures immediately return to discovery."""
        self._native_ready_generation = None
        attempt_began = time.perf_counter()
        try:
            await self.camera.initialize(
                description,
                fcam.ResolutionPreset.LOW,
                enable_audio=False,
                image_format_group=fcam.ImageFormatGroup.JPEG,
            )
            if self._native_ready_generation != generation:
                raise _CachedCameraDescriptionUnavailable(
                    "cached camera description did not report native readiness"
                )
        finally:
            self._perf_duration(generation, "cached_initialize_attempt", attempt_began)

    def _camera_preferences(self) -> Any | None:
        if not bool(getattr(self.page, "web", False)):
            return None
        if self._camera_description_preferences is None:
            self._camera_description_preferences = ft.SharedPreferences()
        return self._camera_description_preferences

    async def _load_cached_camera_description(self) -> fcam.CameraDescription | None:
        preferences = self._camera_preferences()
        if preferences is None:
            return None
        try:
            value = await preferences.get(KIOSK_CAMERA_DESCRIPTION_CACHE_KEY)
        except (AttributeError, RuntimeError):
            return None
        description = _description_from_cache_value(value)
        if description is None and value is not None:
            await self._clear_cached_camera_description()
        return description

    async def _save_cached_camera_description(self, description: fcam.CameraDescription) -> None:
        preferences = self._camera_preferences()
        value = _description_to_cache_value(description)
        if preferences is None or value is None:
            return
        try:
            await preferences.set(KIOSK_CAMERA_DESCRIPTION_CACHE_KEY, value)
        except (AttributeError, RuntimeError, ValueError):
            return

    async def _clear_cached_camera_description(self) -> None:
        preferences = self._camera_preferences()
        if preferences is None:
            return
        try:
            await preferences.remove(KIOSK_CAMERA_DESCRIPTION_CACHE_KEY)
        except (AttributeError, RuntimeError):
            return

    async def _start_capture(
        self,
        generation: int,
        session_key: tuple[int, int],
        strategy: str,
    ) -> None:
        if not self._session_is_current(generation, session_key):
            return
        self._perf_mark(generation, "polling_started")
        startup = self._startup_generation
        startup_source: str | None = None
        if startup is not None and startup[1] == generation:
            startup_id, _, startup_source = startup
            if startup_source == "reconnect":
                print("[KIOSK-QR][RECONNECT] camera_reinitialized=True")
                print(f"[KIOSK-QR][RECONNECT] polling_started generation={generation}")
            print(
                f"[KIOSK-QR][STARTUP] startup_id={startup_id} "
                f"source={startup_source} polling_started generation={generation}"
            )
            self._startup_generation = None
        if strategy == "stream":
            stream_began = self._perf_mark(generation, "start_image_stream_begin")
            await self.camera.start_image_stream()
            self.stream_active = True
            self._perf_duration(generation, "start_image_stream_end", stream_began)
            self._perf_mark(generation, "capture_ready")
            return

        self._perf_mark(generation, "snapshot_polling_begin")
        self._perf_mark(generation, "capture_ready")
        self._start_persistent_snapshot_polling()

    def _start_persistent_snapshot_polling(self) -> None:
        """Create the sole physical snapshot task for this native controller."""
        task = self.runtime.snapshot_task
        if task is not None and not task.done():
            return
        owner_token = object()
        finished = asyncio.Event()

        async def poll_snapshots() -> None:
            await self._run_persistent_snapshot_polling(owner_token, finished)

        task = self.page.run_task(poll_snapshots)
        self.runtime.snapshot_task = task
        self._snapshot_polling_owner_token = owner_token
        self._snapshot_polling_finished = finished
        self._snapshot_controller_recovery_active = False

    def _snapshot_scan_is_current(
        self,
        generation: int,
        session_key: tuple[int, int],
        gate: QrFrameGate,
    ) -> bool:
        return (
            self._session_is_current(generation, session_key)
            and self.gate is gate
            and gate.active
        )

    async def _take_snapshot_keepalive(self) -> None:
        """Exercise Camera without retaining or decoding an image."""
        payload = await self.camera.take_picture()
        if not isinstance(payload, bytes):
            raise TypeError("Camera.take_picture() must return bytes")

    async def _run_persistent_snapshot_polling(
        self,
        owner_token: object,
        finished: asyncio.Event,
    ) -> None:
        """Keep snapshot ownership alive while logical guest sessions open and close."""
        consecutive_errors = 0
        try:
            while not self._closing and self._page_connection_available():
                generation = self.runtime.generation
                session_key = self._session_key
                gate = self.gate
                if (
                    session_key is not None
                    and self._snapshot_scan_is_current(generation, session_key, gate)
                ):
                    capture_intent = "scan"
                elif self._snapshot_keepalive_active and not self._admin_suspended:
                    capture_intent = "keepalive"
                else:
                    await self._sleep(0.65)
                    await asyncio.sleep(0)
                    continue
                try:
                    if capture_intent == "scan":
                        payload = await self._take_snapshot(generation, session_key)
                    else:
                        await self._take_snapshot_keepalive()
                        payload = None
                except Exception as ex:
                    if (
                        capture_intent == "scan"
                        and not self._snapshot_scan_is_current(generation, session_key, gate)
                    ):
                        continue
                    consecutive_errors += 1
                    if consecutive_errors >= 3:
                        self._persistent_snapshot_controller_failed(ex, owner_token, finished)
                        return
                    await self._sleep(0.65)
                    await asyncio.sleep(0)
                    continue
                if capture_intent == "keepalive":
                    consecutive_errors = 0
                    await self._sleep(0.65)
                    await asyncio.sleep(0)
                    continue
                if not self._snapshot_scan_is_current(generation, session_key, gate):
                    continue
                consecutive_errors = 0
                code = await asyncio.to_thread(decode_qr_frame, payload)
                if not self._snapshot_scan_is_current(generation, session_key, gate):
                    continue
                self._log_snapshot_decoded(code, generation, session_key)
                if code:
                    self.on_snapshot_code(code, generation, session_key)
                await self._sleep(0.65)
                await asyncio.sleep(0)
        except asyncio.CancelledError:
            raise
        finally:
            if self._snapshot_polling_owner_token is owner_token:
                self.runtime.snapshot_task = None
                self._snapshot_polling_owner_token = None
                self._snapshot_polling_finished = None
            finished.set()

    def _persistent_snapshot_controller_failed(
        self,
        error: Exception,
        owner_token: object,
        finished: asyncio.Event,
    ) -> None:
        if self._snapshot_controller_recovery_active:
            return
        self._snapshot_controller_recovery_active = True
        kiosk_log(
            self.page,
            "KIOSK-QR",
            "snapshot_controller_failed",
            **self._diagnostic_fields(
                generation=self.runtime.generation,
                exception_type=type(error).__name__,
                sanitized_error=_safe_camera_error_detail(error),
                snapshot_task_id=id(self.runtime.snapshot_task),
                snapshot_task_done=False,
            ),
        )
        self._snapshot_keepalive_active = False
        self.active = False
        self.gate.stop()
        self._session_key = None
        self.runtime.invalidate()
        kiosk_log(
            self.page,
            "KIOSK-QR",
            "snapshot_recovery_scheduled",
            **self._diagnostic_fields(
                reason="persistent_snapshot_controller_failed",
                snapshot_task_id=id(self.runtime.snapshot_task),
            ),
        )

        recovery_token = object()

        async def recover_snapshot_controller() -> None:
            try:
                await finished.wait()
                if self._snapshot_recovery_owner_token is not recovery_token or self._closing:
                    return
                kiosk_log(
                    self.page,
                    "KIOSK-QR",
                    "snapshot_recovery_begin",
                    **self._diagnostic_fields(
                        reason="persistent_snapshot_controller_failed",
                        recovery_task_id=id(self._snapshot_recovery_task),
                    ),
                )
                kiosk_log(
                    self.page,
                    "KIOSK-QR",
                    "full_restart_fallback",
                    **self._diagnostic_fields(reason="persistent_snapshot_controller_failed"),
                )
                await self.restart_scan(preserve_snapshot_recovery=True)
                kiosk_log(
                    self.page,
                    "KIOSK-QR",
                    "snapshot_recovery_complete",
                    **self._diagnostic_fields(
                        recovery_task_id=id(self._snapshot_recovery_task),
                        snapshot_task_id=id(self.runtime.snapshot_task),
                    ),
                )
            except asyncio.CancelledError:
                raise
            except Exception as ex:
                kiosk_log(
                    self.page,
                    "KIOSK-QR",
                    "snapshot_recovery_failed",
                    **self._diagnostic_fields(
                        exception_type=type(ex).__name__,
                        sanitized_error=_safe_camera_error_detail(ex),
                    ),
                )
            finally:
                if self._snapshot_recovery_owner_token is recovery_token:
                    self._snapshot_recovery_task = None
                    self._snapshot_recovery_owner_token = None
                    self._snapshot_controller_recovery_active = False

        recovery_task = self.page.run_task(recover_snapshot_controller)
        self._snapshot_recovery_task = recovery_task
        self._snapshot_recovery_owner_token = recovery_token

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
        self._session_key = None
        self._log_camera_identity("qr_accepted")
        kiosk_log(
            self.page,
            "KIOSK-QR",
            "qr_accepted",
            **self._diagnostic_fields(generation=generation),
        )

        async def finalize_code() -> None:
            await self._finalize_code(code)

        self.page.run_task(finalize_code)
        return True

    async def _finalize_code(self, code: str) -> None:
        # El controller Web puede perderse durante una fase intermedia aunque
        # el control Python siga montado. Aplicamos el mismo cierre que deja
        # listo el camino manual "Intentar nuevamente" para initialize.
        await self._shutdown_camera(reason="qr_accepted")
        self._log_camera_identity("qr_finalized_after_shutdown")
        print("[KIOSK-QR][SNAPSHOT] kiosk_callback", "called")
        self._on_qr_finalized(code)

    async def stop_scan(self, *, reason: str = "route_exit") -> None:
        self.active = False
        self.gate.stop()
        self._session_key = None
        self.runtime.invalidate()
        await self._shutdown_camera(reason=reason)

    async def _suspend_capture_for_phase(
        self,
        *,
        preserve_snapshot_recovery: bool = False,
    ) -> None:
        if self._closing:
            return
        self._closing = True
        try:
            self._snapshot_keepalive_active = False
            recovery_task = self._snapshot_recovery_task
            if (
                not preserve_snapshot_recovery
                and recovery_task is not None
                and not recovery_task.done()
            ):
                recovery_task.cancel()
                try:
                    await recovery_task
                except asyncio.CancelledError:
                    pass
                self._snapshot_recovery_task = None
                self._snapshot_recovery_owner_token = None
                self._snapshot_controller_recovery_active = False
            polling_task = self.runtime.snapshot_task
            current_task = asyncio.current_task()
            if polling_task is not None and polling_task is not current_task and not polling_task.done():
                kiosk_log(
                    self.page,
                    "KIOSK-QR",
                    "snapshot_polling_stopped_strong",
                    **self._diagnostic_fields(
                        snapshot_task_id=id(polling_task),
                        snapshot_task_done=False,
                    ),
                )
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
                        should_pause=False,
                    )
                    if result.stream_error is not None:
                        print("[KIOSK-QR][WARN] stream stop failed", type(result.stream_error).__name__)
            self.stream_active = False
            self.runtime.snapshot_task = None
            self._snapshot_polling_owner_token = None
            self._snapshot_polling_finished = None
            print("[KIOSK-QR][WARM] capture_suspended")
            self._log_camera_identity("capture_suspended")
            kiosk_log(self.page, "KIOSK-QR", "capture_suspended", **self._diagnostic_fields())
        finally:
            self._closing = False

    async def _enter_warm_idle(self, *, session_already_invalidated: bool = False) -> None:
        """Stop QR capture while retaining a valid mounted native controller."""
        kiosk_log(
            self.page,
            "KIOSK-QR",
            "warm_idle_enter",
            **self._diagnostic_fields(),
        )
        self.active = False
        self.gate.stop()
        if not session_already_invalidated:
            self.runtime.invalidate()
        self._session_key = None
        if self.strategy == "snapshot":
            self._snapshot_keepalive_active = True
            polling_task = self.runtime.snapshot_task
            kiosk_log(
                self.page,
                "KIOSK-QR",
                "snapshot_gate_closed",
                **self._diagnostic_fields(
                    snapshot_task_id=id(polling_task) if polling_task is not None else None,
                    snapshot_task_done=polling_task.done() if polling_task is not None else None,
                ),
            )
            kiosk_log(
                self.page,
                "KIOSK-QR",
                "snapshot_keepalive_enter",
                **self._diagnostic_fields(
                    snapshot_task_id=id(polling_task) if polling_task is not None else None,
                ),
            )
        else:
            await self._suspend_capture_for_phase()
        self.set_preview_visible(False)
        kiosk_log(
            self.page,
            "KIOSK-QR",
            "warm_idle_ready",
            **self._diagnostic_fields(),
        )

    async def _shutdown_camera(self, *, reason: str) -> None:
        print(
            "[KIOSK-QR][SHUTDOWN] "
            f"reason={reason} startup_id={self._startup_id} "
            f"generation={self.runtime.generation} "
            f"controller_initialized={self.runtime.controller_initialized} "
            f"preview_paused={self.runtime.preview_paused}"
        )
        kiosk_log(
            self.page,
            "KIOSK-QR",
            "shutdown_begin",
            **self._diagnostic_fields(reason=reason),
        )
        if reason == "qr_accepted":
            await self._enter_warm_idle(session_already_invalidated=True)
            return
        await self._suspend_capture_for_phase()
        if not self._camera_is_mounted():
            return
        async with self.runtime.lifecycle_lock:
            result = await stop_camera_capture(
                stop_stream=self.camera.stop_image_stream,
                pause_preview=self.camera.pause_preview,
                stream_active=False,
                should_pause=(
                    self.runtime.controller_initialized
                    and not self.runtime.preview_paused
                ),
            )
            if result.pause_attempted and result.pause_error is None:
                self.runtime.preview_paused = True
            if result.pause_error is not None:
                self.runtime.controller_initialized = False
            if result.pause_attempted:
                print(
                    "[KIOSK-QR][SHUTDOWN] pause_result "
                    f"error={type(result.pause_error).__name__ if result.pause_error else 'None'} "
                    f"detail={str(result.pause_error) if result.pause_error else 'None'} "
                    f"controller_initialized={self.runtime.controller_initialized}"
                )
            self._log_camera_identity("camera_shutdown")

    async def _fail_session(
        self,
        error: Exception,
        generation: int,
        session_key: tuple[int, int],
    ) -> None:
        if not self._session_is_current(generation, session_key):
            return
        print(
            "[KIOSK-QR][ERROR] camera session failed "
            f"type={type(error).__name__} message={str(error)} "
            f"generation={generation} startup_id={self._startup_id}"
        )
        kiosk_log(
            self.page,
            "KIOSK-QR",
            "camera_error",
            **self._diagnostic_fields(generation=generation, error_type=type(error).__name__),
        )
        self._log_camera_identity("camera_session_failed")
        print(traceback.format_exc())
        self.active = False
        self.gate.stop()
        self.runtime.invalidate()
        await self._shutdown_camera(reason="fatal_error")
        self._on_camera_error(kiosk_camera_error_message(error))

    def _on_camera_state_change(self, event: fcam.CameraStateEvent) -> None:
        self._last_camera_state = {
            field: getattr(event, field, None)
            for field in (
                "is_initialized",
                "is_streaming_images",
                "is_preview_paused",
                "has_error",
            )
            if hasattr(event, field)
        }
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
            if not event.is_preview_paused:
                self._native_ready_generation = self.runtime.generation
                self._perf_mark(self.runtime.generation, "preview_ready")
