from __future__ import annotations

from typing import Any, Callable

import flet as ft

from services.dashboard_service import IndicadoresDashboard


DASHBOARD_COLORS = {
    "primary": "#4F46E5",
    "primary_soft": "#EEF2FF",
    "success": "#15803D",
    "success_soft": "#ECFDF3",
    "warning": "#B45309",
    "warning_soft": "#FFF7ED",
    "danger": "#B42318",
    "danger_soft": "#FEF3F2",
    "info": "#0369A1",
    "info_soft": "#F0F9FF",
    "neutral": "#475467",
    "neutral_soft": "#F8FAFC",
    "border": "#E4E7EC",
}


def _safe_callback(callback: Callable[..., Any] | None) -> Callable[[Any], None] | None:
    return (lambda _event: callback()) if callback else None


def dashboard_kpi_card(
    label: str,
    value: str,
    detail: str,
    icon: Any,
    accent: str,
    soft: str,
    col: dict[str, int] | None = None,
) -> ft.Container:
    return ft.Container(
        content=ft.Row(
            [
                ft.Container(
                    content=ft.Icon(icon, size=24, color=accent),
                    width=46,
                    height=46,
                    border_radius=23,
                    bgcolor=soft,
                    alignment=ft.Alignment.CENTER,
                ),
                ft.Column(
                    [
                        ft.Text(label, size=13, color=DASHBOARD_COLORS["neutral"], weight=ft.FontWeight.W_600),
                        ft.Text(value, size=27, weight=ft.FontWeight.BOLD, color=ft.Colors.ON_SURFACE),
                        ft.Text(detail, size=12, color=DASHBOARD_COLORS["neutral"]),
                    ],
                    spacing=2,
                    tight=True,
                ),
            ],
            spacing=12,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        padding=16,
        border_radius=16,
        bgcolor=ft.Colors.SURFACE,
        border=ft.Border.all(1, DASHBOARD_COLORS["border"]),
        shadow=ft.BoxShadow(blur_radius=12, spread_radius=0, color="#120F172A", offset=ft.Offset(0, 3)),
        col=col or {"xs": 12, "sm": 6, "lg": 3},
        data={"dashboard_component": "kpi_card", "label": label},
    )


def _panel(title: str, subtitle: str, icon: Any, content: ft.Control, col: dict[str, int]) -> ft.Container:
    return ft.Container(
        content=ft.Column(
            [
                ft.Row(
                    [
                        ft.Icon(icon, size=21, color=DASHBOARD_COLORS["primary"]),
                        ft.Column(
                            [
                                ft.Text(title, size=17, weight=ft.FontWeight.BOLD),
                                ft.Text(subtitle, size=12, color=DASHBOARD_COLORS["neutral"]),
                            ],
                            spacing=1,
                            tight=True,
                        ),
                    ],
                    spacing=9,
                ),
                content,
            ],
            spacing=16,
        ),
        padding=18,
        border_radius=16,
        bgcolor=ft.Colors.SURFACE,
        border=ft.Border.all(1, DASHBOARD_COLORS["border"]),
        shadow=ft.BoxShadow(blur_radius=12, spread_radius=0, color="#100F172A", offset=ft.Offset(0, 3)),
        col=col,
        data={"dashboard_component": "visualization", "title": title},
    )


def _legend_item(color: str, label: str, value: str) -> ft.Control:
    return ft.Row(
        [
            ft.Container(width=10, height=10, border_radius=5, bgcolor=color),
            ft.Text(label, size=12, color=DASHBOARD_COLORS["neutral"]),
            ft.Text(value, size=12, weight=ft.FontWeight.BOLD),
        ],
        spacing=6,
    )


def attendance_distribution_chart(data: IndicadoresDashboard) -> ft.Control:
    if data.total_invitados == 0:
        return dashboard_empty_state(ft.Icons.GROUP_OFF, "Sin invitados", "No hay invitados registrados para este evento.")
    return ft.Column(
        [
            ft.Stack(
                [
                    ft.ProgressBar(
                        value=data.porcentaje_llegadas / 100,
                        color=DASHBOARD_COLORS["success"],
                        bgcolor=DASHBOARD_COLORS["warning_soft"],
                        height=18,
                        border_radius=9,
                        tooltip=f"{data.invitados_llegaron} llegaron; {data.invitados_pendientes} pendientes",
                    ),
                    ft.Container(
                        content=ft.Text(f"{data.porcentaje_llegadas:.0f}%", size=11, weight=ft.FontWeight.BOLD),
                        alignment=ft.Alignment.CENTER,
                        height=18,
                    ),
                ]
            ),
            ft.Row(
                [
                    _legend_item(DASHBOARD_COLORS["success"], "Llegaron", str(data.invitados_llegaron)),
                    _legend_item(DASHBOARD_COLORS["warning"], "Pendientes", str(data.invitados_pendientes)),
                ],
                spacing=18,
                wrap=True,
            ),
        ],
        spacing=12,
    )


def arrivals_chart(data: IndicadoresDashboard) -> ft.Control:
    if not data.inicio_evento_valido:
        return dashboard_empty_state(
            ft.Icons.SCHEDULE,
            "Horario no definido",
            "Define la hora de inicio del evento para visualizar la afluencia.",
        )
    maximum = max((item.cantidad for item in data.intervalos_llegadas), default=0)
    bars: list[ft.Control] = []
    for item in data.intervalos_llegadas:
        bar_height = 8 if not maximum else max(8, round(item.cantidad / maximum * 92))
        bars.append(
            ft.Container(
                content=ft.Column(
                    [
                        ft.Text(str(item.cantidad), size=12, weight=ft.FontWeight.BOLD),
                        ft.Container(
                            width=28,
                            height=bar_height,
                            border_radius=ft.BorderRadius.only(top_left=7, top_right=7),
                            bgcolor=DASHBOARD_COLORS["primary"] if item.cantidad else DASHBOARD_COLORS["primary_soft"],
                            tooltip=f"{item.etiqueta}: {item.cantidad} llegadas",
                        ),
                        ft.Text(item.inicio.strftime("%H:%M"), size=10, color=DASHBOARD_COLORS["neutral"]),
                    ],
                    spacing=5,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    alignment=ft.MainAxisAlignment.END,
                ),
                col={"xs": 3, "sm": 1.5},
                alignment=ft.Alignment.BOTTOM_CENTER,
            )
        )
    controls: list[ft.Control] = [
        ft.ResponsiveRow(bars, columns=12, spacing=4, run_spacing=10, vertical_alignment=ft.CrossAxisAlignment.END)
    ]
    if maximum == 0:
        controls.append(ft.Text("Todavía no se han registrado llegadas.", size=12, color=DASHBOARD_COLORS["neutral"]))
    return ft.Column(controls, spacing=8)


def dashboard_progress_card(data: IndicadoresDashboard) -> ft.Control:
    if data.total_mesas == 0:
        content = dashboard_empty_state(ft.Icons.TABLE_RESTAURANT, "Sin mesas", "No hay mesas configuradas para este evento.")
    else:
        content = ft.Column(
            [
                ft.ProgressBar(
                    value=data.porcentaje_mesas_completas / 100,
                    color=DASHBOARD_COLORS["primary"],
                    bgcolor=DASHBOARD_COLORS["neutral_soft"],
                    height=14,
                    border_radius=7,
                    tooltip=f"{data.mesas_completas} de {data.total_mesas} mesas completas",
                ),
                ft.Row(
                    [
                        _legend_item(DASHBOARD_COLORS["primary"], "Completas", str(data.mesas_completas)),
                        _legend_item(DASHBOARD_COLORS["neutral"], "Pendientes", str(data.mesas_pendientes)),
                    ],
                    spacing=18,
                    wrap=True,
                ),
            ],
            spacing=12,
        )
    return _panel(
        "Progreso de mesas",
        "Una mesa vacía nunca se considera completa",
        ft.Icons.TABLE_RESTAURANT,
        content,
        {"xs": 12},
    )


def dashboard_empty_state(icon: Any, title: str, message: str, action: ft.Control | None = None) -> ft.Control:
    controls: list[ft.Control] = [
        ft.Container(
            content=ft.Icon(icon, size=30, color=DASHBOARD_COLORS["primary"]),
            width=56,
            height=56,
            border_radius=28,
            bgcolor=DASHBOARD_COLORS["primary_soft"],
            alignment=ft.Alignment.CENTER,
        ),
        ft.Text(title, size=18, weight=ft.FontWeight.BOLD, text_align=ft.TextAlign.CENTER),
        ft.Text(message, size=13, color=DASHBOARD_COLORS["neutral"], text_align=ft.TextAlign.CENTER),
    ]
    if action is not None:
        controls.append(action)
    return ft.Column(controls, spacing=8, horizontal_alignment=ft.CrossAxisAlignment.CENTER)


def _phase_banner(evento: dict[str, Any]) -> ft.Control:
    fase = str(evento.get("fase_evento") or "")
    mapping = {
        "Pre_evento": ("El evento todavía no ha iniciado", ft.Icons.HOURGLASS_TOP, DASHBOARD_COLORS["info"], DASHBOARD_COLORS["info_soft"]),
        "En_proceso": ("Evento en proceso", ft.Icons.PLAY_CIRCLE, DASHBOARD_COLORS["success"], DASHBOARD_COLORS["success_soft"]),
        "Post_evento": ("Evento finalizado", ft.Icons.EVENT_AVAILABLE, DASHBOARD_COLORS["neutral"], DASHBOARD_COLORS["neutral_soft"]),
    }
    text, icon, color, bgcolor = mapping.get(fase, (fase.replace("_", " ") or "Estado no definido", ft.Icons.INFO, DASHBOARD_COLORS["neutral"], DASHBOARD_COLORS["neutral_soft"]))
    return ft.Container(
        content=ft.Row([ft.Icon(icon, size=17, color=color), ft.Text(text, size=13, weight=ft.FontWeight.W_600, color=color)], spacing=7),
        padding=ft.Padding.symmetric(horizontal=12, vertical=8),
        border_radius=12,
        bgcolor=bgcolor,
    )


def dashboard_view(
    contexto: dict[str, Any],
    estado: str = "idle",
    indicadores: IndicadoresDashboard | None = None,
    mensaje: str = "",
    on_retry: Any | None = None,
    ultima_actualizacion: str = "",
    on_select_event: Any | None = None,
) -> ft.Control:
    evento = contexto.get("evento_actual") or {}
    if not evento:
        action = ft.FilledButton(
            content="Seleccionar evento",
            icon=ft.Icons.EVENT_REPEAT,
            on_click=_safe_callback(on_select_event),
        ) if on_select_event else None
        return ft.Container(
            content=dashboard_empty_state(ft.Icons.EVENT_BUSY, "Selecciona un evento", "Elige el evento cuyos indicadores deseas consultar.", action),
            padding=32,
            alignment=ft.Alignment.CENTER,
            data={"dashboard_state": "event_required"},
        )
    if estado in {"idle", "loading"}:
        return ft.Container(
            content=ft.Column(
                [ft.ProgressRing(width=30, height=30, color=DASHBOARD_COLORS["primary"]), ft.Text("Cargando indicadores del evento…")],
                spacing=12,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=36,
            alignment=ft.Alignment.CENTER,
            data={"dashboard_state": "loading"},
        )
    if estado in {"error", "forbidden", "connection_error"}:
        return ft.Container(
            content=dashboard_empty_state(
                ft.Icons.ERROR_OUTLINE,
                "No fue posible cargar el dashboard",
                mensaje or "Ocurrió un error inesperado.",
                ft.OutlinedButton(content="Reintentar", icon=ft.Icons.REFRESH, on_click=_safe_callback(on_retry)) if on_retry else None,
            ),
            padding=32,
            alignment=ft.Alignment.CENTER,
            data={"dashboard_state": "error"},
        )

    data = indicadores or IndicadoresDashboard()
    no_arrivals = "Sin llegadas registradas"
    kpis = [
        dashboard_kpi_card("Total de invitados", str(data.total_invitados), "Invitados activos", ft.Icons.GROUP, DASHBOARD_COLORS["primary"], DASHBOARD_COLORS["primary_soft"]),
        dashboard_kpi_card("Llegaron", str(data.invitados_llegaron), f"{data.porcentaje_llegadas:.1f}% del total" if data.total_invitados else "Sin invitados", ft.Icons.HOW_TO_REG, DASHBOARD_COLORS["success"], DASHBOARD_COLORS["success_soft"]),
        dashboard_kpi_card("Pendientes", str(data.invitados_pendientes), f"{data.porcentaje_pendientes:.1f}% del total" if data.total_invitados else "Sin invitados", ft.Icons.PENDING_ACTIONS, DASHBOARD_COLORS["warning"], DASHBOARD_COLORS["warning_soft"]),
        dashboard_kpi_card("Con novedades", str(data.invitados_con_novedades), "Invitados activos", ft.Icons.NOTIFICATIONS_ACTIVE, DASHBOARD_COLORS["danger"], DASHBOARD_COLORS["danger_soft"]),
        dashboard_kpi_card("Total de mesas", str(data.total_mesas), "Mesas activas", ft.Icons.TABLE_RESTAURANT, DASHBOARD_COLORS["info"], DASHBOARD_COLORS["info_soft"]),
        dashboard_kpi_card("Mesas completas", str(data.mesas_completas), f"{data.porcentaje_mesas_completas:.1f}% del total" if data.total_mesas else "Sin mesas", ft.Icons.DONE_ALL, DASHBOARD_COLORS["success"], DASHBOARD_COLORS["success_soft"]),
        dashboard_kpi_card("Primera llegada", data.primera_llegada if data.invitados_llegaron else no_arrivals, "Registro más temprano", ft.Icons.FIRST_PAGE, DASHBOARD_COLORS["primary"], DASHBOARD_COLORS["primary_soft"]),
        dashboard_kpi_card("Última llegada", data.ultima_llegada if data.invitados_llegaron else no_arrivals, "Registro más reciente", ft.Icons.LAST_PAGE, DASHBOARD_COLORS["info"], DASHBOARD_COLORS["info_soft"]),
    ]
    charts = ft.ResponsiveRow(
        [
            _panel("Llegadas por intervalos", "Primeras dos horas · intervalos de 15 minutos", ft.Icons.BAR_CHART, arrivals_chart(data), {"xs": 12, "lg": 8}),
            _panel("Distribución de invitados", "Llegaron frente a pendientes", ft.Icons.DONUT_SMALL, attendance_distribution_chart(data), {"xs": 12, "lg": 4}),
        ],
        spacing=14,
        run_spacing=14,
    )
    return ft.ListView(
        controls=[
            ft.ResponsiveRow(
                [
                    ft.Container(
                        content=ft.Column(
                            [
                                ft.Text("Dashboard", size=27, weight=ft.FontWeight.BOLD),
                                ft.Text(str(evento.get("nombre_evento") or "Evento seleccionado"), size=14, color=DASHBOARD_COLORS["neutral"]),
                            ],
                            spacing=2,
                            tight=True,
                        ),
                        col={"xs": 12, "md": 6},
                    ),
                    ft.Container(
                        content=ft.Row(
                            [
                                _phase_banner(evento),
                                ft.Text(ultima_actualizacion or "Sin actualizar", size=12, color=DASHBOARD_COLORS["neutral"]),
                                ft.IconButton(icon=ft.Icons.REFRESH, tooltip="Actualizar dashboard", on_click=_safe_callback(on_retry)),
                            ],
                            spacing=9,
                            wrap=True,
                            alignment=ft.MainAxisAlignment.END,
                        ),
                        col={"xs": 12, "md": 6},
                    ),
                ],
                spacing=10,
                run_spacing=8,
            ),
            ft.ResponsiveRow(kpis, spacing=14, run_spacing=14),
            charts,
            dashboard_progress_card(data),
        ],
        spacing=16,
        expand=True,
        data={"dashboard_state": "ready"},
    )
