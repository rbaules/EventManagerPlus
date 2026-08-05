from __future__ import annotations

import inspect
from typing import Any

import flet as ft

from services.evento_context_service import evento_key


def event_selection_view(
    eventos: list[dict[str, Any]],
    evento_actual: dict[str, Any] | None,
    estado: str,
    mensaje: str,
    on_select: Any,
    on_back: Any,
    on_retry: Any,
) -> ft.Control:
    def crear_handler_seleccion(item: dict[str, Any]) -> Any:
        async def handler(_event: ft.ControlEvent) -> None:
            result = on_select(item)
            if inspect.isawaitable(result):
                await result
        return handler

    controls: list[ft.Control] = [
        ft.Row(
            [
                ft.IconButton(icon=ft.Icons.ARROW_BACK, tooltip="Regresar", on_click=lambda e: on_back()),
                ft.Text("Seleccionar evento activo", size=26, weight=ft.FontWeight.BOLD),
            ],
            spacing=8,
        )
    ]
    if estado == "loading":
        controls.append(ft.Row([ft.ProgressRing(width=24, height=24), ft.Text("Cargando eventos autorizados...")], spacing=12))
        return ft.ListView(controls=controls, spacing=16, expand=True)
    if estado == "error":
        controls.extend([
            ft.Text(mensaje, color=ft.Colors.ERROR),
            ft.OutlinedButton(content="Reintentar", icon=ft.Icons.REFRESH, on_click=lambda e: on_retry()),
        ])
        return ft.ListView(controls=controls, spacing=16, expand=True)
    active_key = evento_key(evento_actual)
    for evento in eventos:
        is_active = evento_key(evento) == active_key
        controls.append(
            ft.Container(
                content=ft.Row(
                    [
                        ft.Column(
                            [
                                ft.Text(str(evento.get("nombre_evento") or "Evento sin nombre"), weight=ft.FontWeight.BOLD),
                                ft.Text(str(evento.get("fecha_hora_inicio_legible") or "Fecha por definir"), color=ft.Colors.ON_SURFACE_VARIANT),
                            ],
                            expand=True,
                            spacing=3,
                        ),
                        ft.Container(
                            content=ft.Text("Activo", size=12, weight=ft.FontWeight.BOLD),
                            visible=is_active,
                            padding=ft.Padding.symmetric(horizontal=10, vertical=4),
                            border_radius=14,
                            bgcolor=ft.Colors.PRIMARY_CONTAINER,
                        ),
                        ft.Button(
                            content="Seleccionar",
                            icon=ft.Icons.CHECK_CIRCLE,
                            disabled=is_active,
                            on_click=crear_handler_seleccion(evento),
                        ),
                    ],
                    spacing=10,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                padding=14,
                border=ft.Border.all(2 if is_active else 1, ft.Colors.PRIMARY if is_active else ft.Colors.OUTLINE_VARIANT),
                border_radius=8,
            )
        )
    if not eventos:
        controls.append(ft.Text(mensaje or "No tienes eventos autorizados disponibles."))
    return ft.ListView(controls=controls, spacing=12, expand=True)
