from __future__ import annotations

import flet as ft

from evkor_web_qr_probe import EvkorServerWebQrProbe


SERVER_WEB_QR_CONTROL_ROUTE = "/diagnostics/server-web-qr-control"
SERVER_WEB_QR_TEST_EVENT = "SERVER_WEB_QR_TEST"


def is_server_web_qr_control_route(route: str | None) -> bool:
    clean = str(route or "").split("?", 1)[0].rstrip("/") or "/"
    return clean == SERVER_WEB_QR_CONTROL_ROUTE


def build_server_web_qr_control_view(page: ft.Page) -> None:
    """Mount an event-only custom control in the existing server-side Page."""

    status = ft.Text("Esperando evento server-side", size=20)
    callback_count = 0

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
                    EvkorServerWebQrProbe(on_test_event=on_test_event),
                ],
                tight=True,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=18,
            ),
            data={"diagnostic": "server_web_qr_control"},
        )
    )
    page.update()
