from __future__ import annotations

from typing import Any

import flet as ft

from services.dashboard_service import IndicadoresDashboard


def _card(title: str, icon: Any, controls: list[ft.Control], col: dict[str, int]) -> ft.Control:
    return ft.Container(
        content=ft.Column(
            [
                ft.Row([
                    ft.Icon(icon, size=24, color=ft.Colors.PRIMARY),
                    ft.Text(title, size=18, weight=ft.FontWeight.BOLD, expand=True),
                ]),
                *controls,
            ],
            spacing=10,
        ),
        padding=16,
        border_radius=12,
        bgcolor=ft.Colors.SURFACE_CONTAINER,
        border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
        col=col,
    )


def _progress(value: float, color: Any = ft.Colors.PRIMARY) -> ft.Control:
    return ft.ProgressBar(value=max(0.0, min(1.0, value / 100)), color=color, bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST)


def _afluencia(data: IndicadoresDashboard) -> ft.Control:
    if not data.inicio_evento_valido:
        return ft.Text(
            "Defina la hora de inicio del evento para visualizar la afluencia.",
            color=ft.Colors.ON_SURFACE_VARIANT,
        )
    maximum = max((item.cantidad for item in data.intervalos_llegadas), default=0)
    rows: list[ft.Control] = []
    for item in data.intervalos_llegadas:
        rows.append(
            ft.Column([
                ft.Row([
                    ft.Text(item.etiqueta, size=12, expand=True),
                    ft.Text(str(item.cantidad), size=13, weight=ft.FontWeight.BOLD),
                ]),
                ft.ProgressBar(
                    value=(item.cantidad / maximum) if maximum else 0,
                    color=ft.Colors.TERTIARY,
                    bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
                    tooltip=f"{item.etiqueta}: {item.cantidad} llegadas",
                ),
            ], spacing=3)
        )
    return ft.Column(rows, spacing=8)


def dashboard_view(
    contexto: dict[str, Any],
    estado: str = "idle",
    indicadores: IndicadoresDashboard | None = None,
    mensaje: str = "",
    on_retry: Any | None = None,
    ultima_actualizacion: str = "",
) -> ft.Control:
    if not contexto.get("evento_actual"):
        return ft.Container(
            content=ft.Column([
                ft.Icon(ft.Icons.EVENT_BUSY, size=36),
                ft.Text("Selecciona un evento activo", size=20, weight=ft.FontWeight.BOLD),
                ft.Text("Usa el menú principal para elegir el evento con el que deseas trabajar."),
            ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=10),
            padding=24,
        )
    if estado in {"idle", "loading"}:
        return ft.Container(
            content=ft.Row([ft.ProgressRing(width=24, height=24), ft.Text("Cargando indicadores...")], spacing=12),
            padding=24,
        )
    if estado == "error":
        return ft.Container(
            content=ft.Column([
                ft.Text("No fue posible cargar el dashboard", size=20, weight=ft.FontWeight.BOLD),
                ft.Text(mensaje, color=ft.Colors.ON_SURFACE_VARIANT),
                ft.OutlinedButton(content="Reintentar", icon=ft.Icons.REFRESH, on_click=lambda e: on_retry()),
            ], spacing=10),
            padding=24,
        )

    data = indicadores or IndicadoresDashboard()
    invitados = _card("Invitados", ft.Icons.GROUP, [
        ft.Text(f"{data.invitados_llegaron} de {data.total_invitados}", size=28, weight=ft.FontWeight.BOLD),
        ft.Text(f"{data.porcentaje_llegadas:.1f} % llegaron", color=ft.Colors.ON_SURFACE_VARIANT),
        _progress(data.porcentaje_llegadas),
        ft.Text(f"{data.invitados_pendientes} pendientes · {data.porcentaje_pendientes:.1f} %", size=13),
    ], {"xs": 12, "md": 6})
    mesas = _card("Mesas", ft.Icons.TABLE_RESTAURANT, [
        ft.Text(f"{data.mesas_completas} completas", size=28, weight=ft.FontWeight.BOLD),
        ft.Text(f"{data.porcentaje_mesas_completas:.1f} % de {data.mesas_con_invitados} mesas con invitados", color=ft.Colors.ON_SURFACE_VARIANT),
        _progress(data.porcentaje_mesas_completas, ft.Colors.SECONDARY),
        ft.Text(f"{data.total_mesas} activas · {data.mesas_parciales} parciales · {data.mesas_sin_llegadas} sin llegadas", size=13),
    ], {"xs": 12, "md": 6})
    novedades = _card("Novedades", ft.Icons.NOTIFICATIONS_ACTIVE, [
        ft.Text(str(data.invitados_con_novedades), size=30, weight=ft.FontWeight.BOLD),
        ft.Text("invitados únicos con novedades", color=ft.Colors.ON_SURFACE_VARIANT),
    ], {"xs": 12, "sm": 6, "lg": 4})
    horarios = _card("Horarios de llegada", ft.Icons.SCHEDULE, [
        ft.Row([ft.Text("Primera", expand=True), ft.Text(data.primera_llegada, weight=ft.FontWeight.BOLD)]),
        ft.Row([ft.Text("Última", expand=True), ft.Text(data.ultima_llegada, weight=ft.FontWeight.BOLD)]),
    ], {"xs": 12, "sm": 6, "lg": 4})
    estado_mesas = _card("Asistencia por mesas", ft.Icons.DONUT_SMALL, [
        ft.Text(f"{data.mesas_completas} completas", weight=ft.FontWeight.BOLD),
        ft.Text(f"{data.mesas_parciales} parciales"),
        ft.Text(f"{data.mesas_sin_llegadas} sin llegadas"),
    ], {"xs": 12, "lg": 4})
    afluencia = _card("Afluencia — primeras 2 horas", ft.Icons.BAR_CHART, [_afluencia(data)], {"xs": 12})

    return ft.ListView(
        controls=[
            ft.Row([
                ft.Text("Dashboard", size=26, weight=ft.FontWeight.BOLD, expand=True),
                ft.Text(ultima_actualizacion, size=12, color=ft.Colors.ON_SURFACE_VARIANT),
                ft.IconButton(icon=ft.Icons.REFRESH, tooltip="Actualizar dashboard", on_click=lambda e: on_retry()),
            ], vertical_alignment=ft.CrossAxisAlignment.CENTER),
            ft.ResponsiveRow([invitados, mesas], spacing=12, run_spacing=12),
            ft.ResponsiveRow([novedades, horarios, estado_mesas], spacing=12, run_spacing=12),
            ft.ResponsiveRow([afluencia], spacing=12, run_spacing=12),
        ],
        spacing=14,
        expand=True,
    )
