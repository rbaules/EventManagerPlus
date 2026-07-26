from __future__ import annotations

from typing import Any

import flet as ft

from services.evento_context_service import evento_key
from components.stat_card import stat_card


def _get(source: dict[str, Any] | None, key: str, default: str = "-") -> Any:
    if not source:
        return default
    value = source.get(key)
    return default if value in (None, "") else value


def _empty_state(message: str) -> ft.Control:
    return ft.Container(
        content=ft.Column(
            [
                ft.Icon(ft.Icons.EVENT_BUSY, size=36, color=ft.Colors.ON_SURFACE_VARIANT),
                ft.Text(message, size=16, weight=ft.FontWeight.W_600),
                ft.Text(
                    "Si necesitas acceso a un evento, contacta al administrador.",
                    size=13,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                ),
            ],
            spacing=8,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        padding=24,
        border_radius=8,
        bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
        border=ft.Border.all(width=1, color=ft.Colors.OUTLINE_VARIANT),
    )


def _error_state(message: str, on_retry: Any) -> ft.Control:
    return ft.Container(
        content=ft.Column(
            [
                ft.Text("No fue posible cargar los eventos", size=18, weight=ft.FontWeight.BOLD),
                ft.Text(message, size=14, color=ft.Colors.ON_SURFACE_VARIANT),
                ft.OutlinedButton(
                    content="Reintentar",
                    icon=ft.Icons.REFRESH,
                    on_click=lambda e: on_retry(),
                ),
            ],
            spacing=10,
        ),
        padding=16,
        border_radius=8,
        bgcolor=ft.Colors.ERROR_CONTAINER,
    )


def _loading_state() -> ft.Control:
    return ft.Container(
        content=ft.Row(
            [
                ft.ProgressRing(width=24, height=24),
                ft.Text("Cargando eventos...", size=15),
            ],
            spacing=12,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        padding=16,
        border_radius=8,
        bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
        border=ft.Border.all(width=1, color=ft.Colors.OUTLINE_VARIANT),
    )


def _evento_card(
    evento: dict[str, Any],
    is_active: bool,
    on_select: Any,
) -> ft.Control:
    nombre = str(_get(evento, "nombre_evento", "Evento sin nombre"))
    fase = str(_get(evento, "fase_evento", "Sin fase"))
    fecha = _get(evento, "fecha_hora_inicio_legible", "Fecha por definir")
    rol = str(_get(evento, "rol", "Sin rol"))
    estado = str(_get(evento, "estado", "Sin estado"))

    badge = ft.Container(
        content=ft.Text(
            "Evento activo" if is_active else "Disponible",
            size=12,
            weight=ft.FontWeight.W_600,
        ),
        padding=ft.Padding.symmetric(horizontal=10, vertical=4),
        border_radius=16,
        bgcolor=ft.Colors.PRIMARY_CONTAINER if is_active else ft.Colors.SURFACE_CONTAINER,
    )

    return ft.Container(
        content=ft.Column(
            [
                ft.Row(
                    [
                        ft.Text(nombre, size=17, weight=ft.FontWeight.BOLD, expand=True),
                        badge,
                    ],
                    spacing=8,
                    vertical_alignment=ft.CrossAxisAlignment.START,
                ),
                ft.Text(f"Fase: {fase}", size=13, color=ft.Colors.ON_SURFACE_VARIANT),
                ft.Text(f"Fecha: {fecha}", size=13, color=ft.Colors.ON_SURFACE_VARIANT),
                ft.Text(f"Estado: {estado}", size=13, color=ft.Colors.ON_SURFACE_VARIANT),
                ft.Text(f"Acceso: {rol}", size=13, color=ft.Colors.ON_SURFACE_VARIANT),
                ft.Row(
                    [
                        ft.Button(
                            content="Seleccionar evento",
                            icon=ft.Icons.CHECK_CIRCLE,
                            disabled=is_active,
                            on_click=lambda e: on_select(evento),
                        ),
                    ],
                    alignment=ft.MainAxisAlignment.END,
                ),
            ],
            spacing=8,
        ),
        padding=16,
        border_radius=8,
        bgcolor=ft.Colors.PRIMARY_CONTAINER if is_active else ft.Colors.SURFACE,
        border=ft.Border.all(
            width=2 if is_active else 1,
            color=ft.Colors.PRIMARY if is_active else ft.Colors.OUTLINE_VARIANT,
        ),
    )


def _eventos_section(
    eventos_estado: str,
    eventos: list[dict[str, Any]],
    evento_activo: dict[str, Any],
    eventos_mensaje: str,
    on_select_event: Any,
    on_retry_events: Any,
) -> ft.Control:
    if eventos_estado == "loading":
        return _loading_state()

    if eventos_estado == "error":
        return _error_state(eventos_mensaje, on_retry_events)

    if not eventos:
        return _empty_state(eventos_mensaje or "No tienes eventos disponibles en este momento.")

    active_key = evento_key(evento_activo)
    return ft.Column(
        [
            ft.Text("Eventos disponibles", size=20, weight=ft.FontWeight.BOLD),
            ft.Text(
                "Selecciona el evento con el que vas a trabajar en esta sesion.",
                size=14,
                color=ft.Colors.ON_SURFACE_VARIANT,
            ),
            ft.ResponsiveRow(
                [
                    ft.Container(
                        content=_evento_card(
                            evento,
                            evento_key(evento) == active_key,
                            on_select_event,
                        ),
                        col={"xs": 12, "md": 6, "xl": 4},
                    )
                    for evento in eventos
                ],
                spacing=12,
                run_spacing=12,
            ),
        ],
        spacing=12,
    )


def dashboard_view(
    contexto: dict[str, Any],
    eventos_estado: str = "ready",
    eventos: list[dict[str, Any]] | None = None,
    eventos_mensaje: str = "",
    on_select_event: Any | None = None,
    on_retry_events: Any | None = None,
) -> ft.Control:
    cuenta = contexto.get("cuenta_actual") or {}
    evento = contexto.get("evento_actual") or {}
    cuentas = contexto.get("cuentas_permitidas") or []
    eventos_disponibles = eventos if eventos is not None else (contexto.get("eventos_permitidos") or [])
    on_select_event = on_select_event or (lambda evento: None)
    on_retry_events = on_retry_events or (lambda: None)

    if not cuenta and not eventos_disponibles:
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
                        stat_card(
                            "Evento activo",
                            str(_get(evento, "nombre_evento", "Ningun evento seleccionado")),
                        ),
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
                        stat_card("Eventos disponibles", str(len(eventos_disponibles))),
                        col={"xs": 12, "sm": 6, "lg": 4},
                    ),
                ],
                spacing=12,
                run_spacing=12,
            ),
            _eventos_section(
                eventos_estado=eventos_estado,
                eventos=eventos_disponibles,
                evento_activo=evento,
                eventos_mensaje=eventos_mensaje,
                on_select_event=on_select_event,
                on_retry_events=on_retry_events,
            ),
        ],
        spacing=16,
        expand=True,
    )
