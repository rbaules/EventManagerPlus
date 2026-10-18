from __future__ import annotations

from dataclasses import dataclass

import flet as ft

from evkor_web_qr_probe import EvkorServerWebQrProbe


SERVER_WEB_QR_CONTROL_ROUTE = "/diagnostics/server-web-qr-control"
SERVER_WEB_QR_TEST_EVENT = "SERVER_WEB_QR_TEST"


@dataclass
class ServerWebQrProbeSession:
    """Diagnostic state held only for the current server-side Flet Page."""

    qr_count: int = 0
    last_qr: str = ""

    def accept_qr(self, raw_value: object) -> str | None:
        value = str(raw_value or "").strip()
        if not value:
            return None
        self.qr_count += 1
        self.last_qr = value
        return value


def is_server_web_qr_control_route(route: str | None) -> bool:
    clean = str(route or "").split("?", 1)[0].rstrip("/") or "/"
    return clean == SERVER_WEB_QR_CONTROL_ROUTE


def build_server_web_qr_control_view(page: ft.Page) -> None:
    """Mount an event-only custom control in the existing server-side Page."""

    status = ft.Text("Esperando evento server-side", size=20)
    scanner_status = ft.Text("Estado scanner: idle")
    last_qr = ft.Text("Ultimo QR detectado: ninguno")
    qr_count = ft.Text("QR recibidos: 0")
    scanner_metrics = ft.Text("Metricas: pendientes", selectable=True)
    scanner_error = ft.Text("")
    callback_count = 0
    qr_session = ServerWebQrProbeSession()

    def on_test_event(event: ft.Event[EvkorServerWebQrProbe]) -> None:
        nonlocal callback_count
        if event.data != SERVER_WEB_QR_TEST_EVENT:
            status.value = "Evento diagnÃ³stico invÃ¡lido"
            page.update()
            return
        callback_count += 1
        print(
            "[WEB-QR-PROBE][server_event] "
            f"value={SERVER_WEB_QR_TEST_EVENT} count={callback_count}"
        )
        status.value = f"Evento recibido: {SERVER_WEB_QR_TEST_EVENT}"
        page.update()

    def on_qr_detected(event: ft.Event[EvkorServerWebQrProbe]) -> None:
        value = qr_session.accept_qr(event.data)
        if value is None:
            return
        print(f"[WEB-QR-PROBE][qr_detected] length={len(value)}")
        last_qr.value = f"Ultimo QR detectado: {value}"
        qr_count.value = f"QR recibidos: {qr_session.qr_count}"
        scanner_status.value = "Estado scanner: qr_detected"
        page.update()

    def on_scanner_state(event: ft.Event[EvkorServerWebQrProbe]) -> None:
        scanner_status.value = f"Estado scanner: {str(event.data or 'unknown')}"
        page.update()

    def on_scanner_metrics(event: ft.Event[EvkorServerWebQrProbe]) -> None:
        scanner_metrics.value = f"Metricas: {str(event.data or '{}')}"
        page.update()

    def on_scanner_error(event: ft.Event[EvkorServerWebQrProbe]) -> None:
        scanner_error.value = f"Error scanner: {str(event.data or 'unknown')}"
        page.update()

    page.title = "EVKOR Server Web QR Control"
    page.clean()
    page.add(
        ft.Container(
            expand=True,
            alignment=ft.Alignment.CENTER,
            content=ft.Column(
                [
                    ft.Text("EVKOR Server Web QR Control", size=26),
                    status,
                    scanner_status,
                    last_qr,
                    qr_count,
                    scanner_metrics,
                    scanner_error,
                    EvkorServerWebQrProbe(
                        on_test_event=on_test_event,
                        on_qr_detected=on_qr_detected,
                        on_scanner_state=on_scanner_state,
                        on_scanner_metrics=on_scanner_metrics,
                        on_scanner_error=on_scanner_error,
                    ),
                ],
                tight=True,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=18,
            ),
            data={"diagnostic": "server_web_qr_control"},
        )
    )
    page.update()
