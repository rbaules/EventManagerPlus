"""Standalone diagnostic host for the EVKOR custom Flet Web control."""

import flet as ft

from evkor_web_qr_probe import EvkorWebQrProbe


def main(page: ft.Page) -> None:
    page.title = "EVKOR Web QR Control diagnostic"
    status = ft.Text("Estado: idle")
    last_qr = ft.Text("Último QR detectado: —")
    metrics = ft.Text("Métricas: esperando inicio")

    def on_qr_detected(event: ft.Event[EvkorWebQrProbe]) -> None:
        last_qr.value = f"Último QR detectado: {event.data}"
        last_qr.update()

    def on_scanner_state(event: ft.Event[EvkorWebQrProbe]) -> None:
        status.value = f"Estado: {event.data}"
        status.update()

    def on_scanner_metrics(event: ft.Event[EvkorWebQrProbe]) -> None:
        metrics.value = f"Métricas: {event.data}"
        metrics.update()

    def on_scanner_error(event: ft.Event[EvkorWebQrProbe]) -> None:
        status.value = f"Estado: error ({event.data})"
        status.update()

    page.add(
        ft.Column(
            controls=[
                ft.Text("Diagnóstico aislado de custom control"),
                EvkorWebQrProbe(
                    on_qr_detected=on_qr_detected,
                    on_scanner_state=on_scanner_state,
                    on_scanner_metrics=on_scanner_metrics,
                    on_scanner_error=on_scanner_error,
                ),
                status,
                last_qr,
                metrics,
            ],
            tight=True,
        )
    )


ft.run(main)
