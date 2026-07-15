from __future__ import annotations

from typing import Any

import flet as ft

from components.stat_card import stat_card


def _get(source: dict[str, Any] | None, key: str, default: str = "-") -> Any:
    if not source:
        return default
    value = source.get(key)
    return default if value in (None, "") else value


def dashboard_view(contexto: dict[str, Any]) -> ft.Control:
    cuenta = contexto.get("cuenta_actual") or {}
    evento = contexto.get("evento_actual") or {}
    cuentas = contexto.get("cuentas_permitidas") or []
    eventos = contexto.get("eventos_permitidos") or []

    if not cuenta or not evento:
        return ft.Container(
            content=ft.Column(
                [
                    ft.Text("Contexto incompleto", size=22, weight=ft.FontWeight.BOLD),
                    ft.Text(
                        "No hay una cuenta o evento actual disponible para este usuario. "
                        "Por ahora solo puedes salir de la sesion.",
                        size=15,
                    ),
                ],
                spacing=8,
            ),
            padding=16,
            border_radius=8,
            bgcolor=ft.Colors.ERROR_CONTAINER,
        )

    return ft.ListView(
        controls=[
            ft.Text("Dashboard", size=26, weight=ft.FontWeight.BOLD),
            ft.Text(
                "Resumen inicial del contexto operativo del evento.",
                size=14,
                color=ft.Colors.ON_SURFACE_VARIANT,
            ),
            ft.ResponsiveRow(
                [
                    ft.Container(
                        stat_card("Evento actual", str(_get(evento, "nombre_evento"))),
                        col={"xs": 12, "sm": 6, "lg": 4},
                    ),
                    ft.Container(
                        stat_card("Fase del evento", str(_get(evento, "fase_evento"))),
                        col={"xs": 12, "sm": 6, "lg": 4},
                    ),
                    ft.Container(
                        stat_card("Cuenta actual", str(_get(cuenta, "nombre_cuenta"))),
                        col={"xs": 12, "sm": 6, "lg": 4},
                    ),
                    ft.Container(
                        stat_card(
                            "Rol del usuario",
                            str(_get(contexto, "rol_global_calculado")),
                        ),
                        col={"xs": 12, "sm": 6, "lg": 4},
                    ),
                    ft.Container(
                        stat_card("Cuentas permitidas", str(len(cuentas))),
                        col={"xs": 12, "sm": 6, "lg": 4},
                    ),
                    ft.Container(
                        stat_card("Eventos permitidos", str(len(eventos))),
                        col={"xs": 12, "sm": 6, "lg": 4},
                    ),
                ],
                spacing=12,
                run_spacing=12,
            ),
        ],
        spacing=16,
        expand=True,
    )
