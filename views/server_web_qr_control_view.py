from __future__ import annotations

from dataclasses import dataclass
import json

import flet as ft

from evkor_web_qr_probe import EvkorServerWebQrProbe


SERVER_WEB_QR_CONTROL_ROUTE = "/diagnostics/server-web-qr-control"
SERVER_WEB_QR_TEST_EVENT = "SERVER_WEB_QR_TEST"


@dataclass
class ServerWebQrProbeSession:
    """Per-page state: stream, detector and preview have independent lifecycles."""

    qr_count: int = 0
    last_qr: str = ""
    active: bool = False
    detector_enabled: bool = False
    preview_visible: bool = True
    facing_mode: str = "user"
    generation: int = 0
    get_user_media_count: int = 0

    def accept_qr(self, raw_value: object) -> str | None:
        if not self.detector_enabled:
            return None
        value = str(raw_value or "").strip()
        if not value:
            return None
        self.qr_count += 1
        self.last_qr = value
        self.detector_enabled = False
        return value

    def apply_action(self, action: str) -> bool:
        if action == "start":
            self.active, self.detector_enabled, self.preview_visible = True, True, True
        elif action == "stop":
            self.active, self.detector_enabled = False, False
        elif action == "activate_detector":
            self.detector_enabled = True
        elif action == "pause_detector":
            self.detector_enabled = False
        elif action == "show_preview":
            self.preview_visible = True
        elif action == "hide_preview":
            self.preview_visible = False
        elif action == "next_guest":
            self.generation += 1
            self.detector_enabled, self.preview_visible = True, True
        elif action == "switch_camera":
            self.facing_mode = "environment" if self.facing_mode == "user" else "user"
        else:
            return False
        return True


def is_server_web_qr_control_route(route: str | None) -> bool:
    clean = str(route or "").split("?", 1)[0].rstrip("/") or "/"
    return clean == SERVER_WEB_QR_CONTROL_ROUTE


def build_server_web_qr_control_view(page: ft.Page) -> None:
    """Mount the browser scanner diagnostic without any product QR side effects."""

    status = ft.Text("Esperando evento server-side", size=20)
    scanner_status = ft.Text("Estado scanner: idle")
    last_qr = ft.Text("Ultimo QR detectado: ninguno")
    qr_count = ft.Text("QR recibidos: 0")
    generation = ft.Text("Generation: 0")
    get_user_media_count = ft.Text("getUserMedia count: 0")
    scanner_metrics = ft.Text("Metricas: pendientes", selectable=True)
    scanner_error = ft.Text("")
    callback_count = 0
    qr_session = ServerWebQrProbeSession()

    def sync_probe() -> None:
        probe.active = qr_session.active
        probe.detector_enabled = qr_session.detector_enabled
        probe.preview_visible = qr_session.preview_visible
        probe.facing_mode = qr_session.facing_mode
        probe.generation = qr_session.generation

    def on_test_event(event: ft.Event[EvkorServerWebQrProbe]) -> None:
        nonlocal callback_count
        if event.data != SERVER_WEB_QR_TEST_EVENT:
            status.value = "Evento diagnostico invalido"
            page.update()
            return
        callback_count += 1
        status.value = f"Evento recibido: {SERVER_WEB_QR_TEST_EVENT}"
        page.update()

    def on_lifecycle_action(event: ft.Event[EvkorServerWebQrProbe]) -> None:
        action = str(event.data or "")
        if not qr_session.apply_action(action):
            scanner_error.value = f"Accion scanner invalida: {action}"
            page.update()
            return
        if action == "next_guest":
            status.value = "Listo para siguiente invitado"
        elif action == "stop":
            status.value = "Camara detenida"
        generation.value = f"Generation: {qr_session.generation}"
        sync_probe()
        page.update()

    def on_qr_detected(event: ft.Event[EvkorServerWebQrProbe]) -> None:
        value = qr_session.accept_qr(event.data)
        if value is None:
            return
        print(f"[WEB-QR-PROBE][qr_detected] length={len(value)} generation={qr_session.generation}")
        last_qr.value = f"Ultimo QR detectado: {value}"
        qr_count.value = f"QR recibidos: {qr_session.qr_count}"
        status.value = "QR recibido - detector pausado"
        scanner_status.value = "Estado scanner: detector_paused"
        sync_probe()
        page.update()

    def on_scanner_state(event: ft.Event[EvkorServerWebQrProbe]) -> None:
        scanner_status.value = f"Estado scanner: {str(event.data or 'unknown')}"
        page.update()

    def on_scanner_metrics(event: ft.Event[EvkorServerWebQrProbe]) -> None:
        raw = str(event.data or "{}")
        scanner_metrics.value = f"Metricas: {raw}"
        try:
            count = json.loads(raw).get("getUserMedia_count")
        except json.JSONDecodeError:
            count = None
        if isinstance(count, int):
            qr_session.get_user_media_count = count
            get_user_media_count.value = f"getUserMedia count: {count}"
        page.update()

    def on_scanner_error(event: ft.Event[EvkorServerWebQrProbe]) -> None:
        scanner_error.value = f"Error scanner: {str(event.data or 'unknown')}"
        page.update()

    probe = EvkorServerWebQrProbe(
        on_test_event=on_test_event,
        on_lifecycle_action=on_lifecycle_action,
        on_qr_detected=on_qr_detected,
        on_scanner_state=on_scanner_state,
        on_scanner_metrics=on_scanner_metrics,
        on_scanner_error=on_scanner_error,
    )
    sync_probe()
    page.title = "EVKOR Server Web QR Control"
    page.clean()
    page.add(
        ft.Container(
            expand=True,
            alignment=ft.Alignment.CENTER,
            content=ft.Column(
                [
                    ft.Text("EVKOR Server Web QR Control", size=26), status, scanner_status,
                    last_qr, qr_count, generation, get_user_media_count, scanner_metrics,
                    scanner_error, probe,
                ],
                tight=True,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=18,
            ),
            data={"diagnostic": "server_web_qr_control"},
        )
    )
    page.update()
