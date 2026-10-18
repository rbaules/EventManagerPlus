from __future__ import annotations

import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import flet as ft

from services.kiosk_diagnostic_log import kiosk_log


def _probe_type() -> type[ft.LayoutControl]:
    """Load the custom control in ASGI and standalone Kiosk sessions."""
    try:
        from evkor_web_qr_probe import EvkorServerWebQrProbe
    except ModuleNotFoundError:
        source = Path(__file__).resolve().parents[1] / "diagnostics" / "evkor_web_qr_probe" / "src"
        if str(source) not in sys.path:
            sys.path.insert(0, str(source))
        from evkor_web_qr_probe import EvkorServerWebQrProbe
    return EvkorServerWebQrProbe


class KioskWebQrScanner:
    """Product adapter for the persistent browser scanner; no Kiosk business logic."""

    def __init__(
        self,
        *,
        page: ft.Page,
        on_qr_finalized: Callable[[str], None],
        on_camera_error: Callable[[str], None],
        **_: Any,
    ) -> None:
        self.page = page
        self._on_qr_finalized = on_qr_finalized
        self._on_camera_error = on_camera_error
        self.active = False
        self.detector_enabled = False
        self.preview_visible = True
        self.generation = 0
        self._gate_open = False
        self._closed = False
        self._stream_live: bool | None = None
        probe_type = _probe_type()
        self.probe = probe_type(
            label="",
            active=False,
            detector_enabled=False,
            preview_visible=True,
            generation=0,
            diagnostic=False,
            preview_width=560,
            preview_height=300,
            on_qr_detected=self._on_qr_detected,
            on_scanner_state=self._on_state,
            on_scanner_metrics=self._on_metrics,
            on_scanner_error=self._on_error,
        )
        self.host = ft.Container(
            content=self.probe,
            visible=True,
            opacity=1,
            width=560,
            height=300,
            ignore_interactions=False,
            alignment=ft.Alignment.CENTER,
            border_radius=18,
            clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
            bgcolor=ft.Colors.BLACK,
            data={"kiosk": "persistent_web_camera_host"},
        )
        self._log("identity", lifecycle="created")

    def _identity_fields(self) -> dict[str, object]:
        try:
            control_uid = getattr(self.probe, "_i", None)
        except RuntimeError:
            control_uid = None
        return {"adapter_id": id(self), "control_id": id(self.probe), "control_uid": control_uid, "host_id": id(self.host)}

    def _log(self, event: str, **fields: object) -> None:
        fields = {**self._identity_fields(), **fields}
        kiosk_log(self.page, "KIOSK-WEB-QR", event, generation=self.generation, **fields)

    def _sync(self) -> None:
        self.probe.active = self.active
        self.probe.detector_enabled = self.detector_enabled
        self.probe.preview_visible = self.preview_visible
        self.probe.generation = self.generation

    def _publish(self) -> None:
        """Flush lifecycle properties changed from an asynchronous Admin task."""
        self._sync()
        self.page.update()

    def start(self) -> None:
        self._closed = False
        self.active = True
        self.detector_enabled = True
        self.preview_visible = True
        self._gate_open = True
        self._publish()
        self._log("state", active=True, detector_enabled=True, stream_action="ensure")

    def restart(self) -> None:
        self.resume_for_next_guest()

    def resume_for_next_guest(self) -> None:
        self.generation += 1
        self.start()
        self._log("state", action="next_guest", gate_open=True)

    def pause_detection(self) -> None:
        self.detector_enabled = False
        self._publish()
        self._log("state", detector_enabled=False)

    async def suspend_for_admin(self) -> None:
        self._gate_open = False
        self.pause_detection()
        self.set_preview_visible(False)
        self._log("admin_suspend", active=self.active, detector_enabled=self.detector_enabled,
                  preview_visible=self.preview_visible, stream_live=self._stream_live)

    async def resume_after_admin(self) -> None:
        if self._closed:
            return
        self._gate_open = True
        self.detector_enabled = True
        self.set_preview_visible(True)
        self._log("admin_resume", phase="WELCOME_SCAN", active=self.active,
                  detector_enabled=self.detector_enabled, preview_visible=self.preview_visible,
                  stream_live=self._stream_live)

    def set_preview_visible(self, visible: bool) -> None:
        self.preview_visible = visible
        self.host.visible = True
        self.host.opacity = 1 if visible else 0
        # Unlike the legacy Camera host, the Web custom control must not be
        # resized while hidden: Flutter can recreate its nested video state.
        self.host.width = 560
        self.host.height = 300
        self.host.ignore_interactions = not visible
        self._publish()
        self._log("host", width=self.host.width, height=self.host.height,
                  opacity=self.host.opacity, preview_visible=self.preview_visible,
                  ignore_interactions=self.host.ignore_interactions)

    async def stop_scan(self, *, reason: str = "route_exit") -> None:
        self.close(disconnected=reason == "disconnect")

    def close(self, *, disconnected: bool = False) -> None:
        self._closed = True
        self._gate_open = False
        self.detector_enabled = False
        self.active = False
        self._sync()
        self._log("state", action="close", disconnected=disconnected)

    def recover_after_reconnect(self) -> None:
        if not self._closed and self.active:
            self._sync()
            self._log("state", action="reconnect_recover")

    def lifecycle_diagnostic_state(self) -> dict[str, object]:
        return {"snapshot_task_active": False, "stream_active": self.active, "startup_task_active": False,
                "controller_initialized": self.active, "preview_paused": not self.preview_visible, "generation": self.generation}

    def _on_qr_detected(self, event: ft.Event[Any]) -> None:
        if not self._gate_open or not self.active:
            self._log("qr", accepted=False, reason="gate_closed")
            return
        self._gate_open = False
        self.pause_detection()
        self._log("qr", accepted=True)
        self._on_qr_finalized(str(event.data or ""))

    def _on_state(self, event: ft.Event[Any]) -> None:
        self._log("state", browser_state=str(event.data or "unknown"))

    def _on_metrics(self, event: ft.Event[Any]) -> None:
        try:
            metrics = json.loads(str(event.data or "{}"))
        except json.JSONDecodeError:
            return
        stream_live = metrics.get("stream_live")
        if isinstance(stream_live, bool):
            self._stream_live = stream_live
        self._log("metric", camera_reused=metrics.get("camera_reused"), getUserMedia_count=metrics.get("getUserMedia_count"), stream_live=metrics.get("stream_live"), detector_enabled=metrics.get("detector_enabled"))

    def _on_error(self, event: ft.Event[Any]) -> None:
        self._gate_open = False
        self.pause_detection()
        self._on_camera_error("No pudimos iniciar la cámara. Intenta nuevamente.")
