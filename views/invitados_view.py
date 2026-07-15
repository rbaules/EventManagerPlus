from __future__ import annotations

from typing import Any

import flet as ft


FILTRO_LABELS = {
    "todos": "Todos",
    "llegaron": "Llegaron",
    "pendientes": "Pendientes",
    "con_mesa": "Con mesa",
    "sin_mesa": "Sin mesa",
    "previstos": "Previstos",
    "imprevistos": "Imprevistos",
}


def _get(source: dict[str, Any] | None, key: str, default: str = "-") -> Any:
    if not source:
        return default
    value = source.get(key)
    return default if value in (None, "") else value


def _state_card(title: str, message: str, icon: Any, on_retry: Any | None = None) -> ft.Control:
    controls: list[ft.Control] = [
        ft.Icon(icon, size=36, color=ft.Colors.ON_SURFACE_VARIANT),
        ft.Text(title, size=18, weight=ft.FontWeight.BOLD),
        ft.Text(message, size=14, color=ft.Colors.ON_SURFACE_VARIANT, text_align=ft.TextAlign.CENTER),
    ]
    if on_retry:
        controls.append(
            ft.OutlinedButton(
                content="Reintentar",
                icon=ft.Icons.REFRESH,
                on_click=lambda e: on_retry(),
            )
        )
    return ft.Container(
        content=ft.Column(
            controls,
            spacing=10,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        padding=24,
        border_radius=8,
        bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
        border=ft.Border.all(width=1, color=ft.Colors.OUTLINE_VARIANT),
    )


def _chip(text: str, bgcolor: Any = ft.Colors.SURFACE_CONTAINER) -> ft.Control:
    return ft.Container(
        content=ft.Text(text, size=12, weight=ft.FontWeight.W_600),
        padding=ft.Padding.symmetric(horizontal=10, vertical=4),
        border_radius=16,
        bgcolor=bgcolor,
    )


def _invitado_card(invitado: dict[str, Any], on_detail: Any) -> ft.Control:
    llegada = bool(invitado.get("llegada_confirmada"))
    return ft.Container(
        content=ft.Column(
            [
                ft.Row(
                    [
                        ft.Text(
                            str(_get(invitado, "nombre_completo", "Invitado sin nombre")),
                            size=16,
                            weight=ft.FontWeight.BOLD,
                            expand=True,
                            overflow=ft.TextOverflow.ELLIPSIS,
                        ),
                        _chip(
                            str(_get(invitado, "estado_llegada")),
                            ft.Colors.PRIMARY_CONTAINER if llegada else ft.Colors.SECONDARY_CONTAINER,
                        ),
                    ],
                    spacing=8,
                    vertical_alignment=ft.CrossAxisAlignment.START,
                ),
                ft.ResponsiveRow(
                    [
                        ft.Container(
                            ft.Text(str(_get(invitado, "mesa_texto")), size=13),
                            col={"xs": 6, "md": 3},
                        ),
                        ft.Container(
                            ft.Text(str(_get(invitado, "puesto_texto")), size=13),
                            col={"xs": 6, "md": 3},
                        ),
                        ft.Container(
                            ft.Text(str(_get(invitado, "origen_invitado")), size=13),
                            col={"xs": 6, "md": 3},
                        ),
                        ft.Container(
                            ft.Text(str(_get(invitado, "tipo_invitado")), size=13),
                            col={"xs": 6, "md": 3},
                        ),
                    ],
                    spacing=8,
                    run_spacing=4,
                ),
                ft.Row(
                    [
                        ft.Text(
                            "Con novedad" if invitado.get("tiene_novedad") else "Sin novedad",
                            size=12,
                            color=ft.Colors.ON_SURFACE_VARIANT,
                            expand=True,
                        ),
                        ft.OutlinedButton(
                            content="Ver detalle",
                            icon=ft.Icons.PERSON,
                            on_click=lambda e: on_detail(invitado),
                        ),
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                ),
            ],
            spacing=8,
        ),
        padding=16,
        border_radius=8,
        bgcolor=ft.Colors.SURFACE,
        border=ft.Border.all(width=1, color=ft.Colors.OUTLINE_VARIANT),
    )


def _detail_row(label: str, value: Any) -> ft.Control:
    return ft.Container(
        content=ft.Column(
            [
                ft.Text(label, size=12, color=ft.Colors.ON_SURFACE_VARIANT),
                ft.Text(str(value or "-"), size=14, selectable=True),
            ],
            spacing=2,
            tight=True,
        ),
        padding=ft.Padding.only(bottom=8),
    )


def _detail_panel(invitado: dict[str, Any] | None, on_close: Any) -> ft.Control:
    if not invitado:
        return ft.Container()

    return ft.Container(
        content=ft.Column(
            [
                ft.Row(
                    [
                        ft.Text("Detalle del invitado", size=18, weight=ft.FontWeight.BOLD, expand=True),
                        ft.TextButton(content="Cerrar", icon=ft.Icons.CLOSE, on_click=lambda e: on_close()),
                    ],
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                _detail_row("Nombre", invitado.get("nombre_completo")),
                _detail_row("Llegada", invitado.get("estado_llegada")),
                _detail_row("Mesa", invitado.get("mesa_texto")),
                _detail_row("Puesto", invitado.get("puesto_texto")),
                _detail_row("Tipo", invitado.get("tipo_invitado")),
                _detail_row("Origen", invitado.get("origen_invitado")),
                _detail_row("Email", invitado.get("email")),
                _detail_row("Telefono", invitado.get("telefono")),
                _detail_row("Novedad", "Si" if invitado.get("tiene_novedad") else "No"),
                _detail_row("Descripcion de novedad", invitado.get("descripcion_novedad")),
            ],
            spacing=4,
        ),
        padding=16,
        border_radius=8,
        bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
        border=ft.Border.all(width=1, color=ft.Colors.OUTLINE_VARIANT),
    )


def invitados_view(
    contexto: dict[str, Any],
    estado: str,
    invitados: list[dict[str, Any]],
    mensaje: str,
    busqueda: str,
    filtro: str,
    has_more: bool,
    is_loading: bool,
    invitado_detalle: dict[str, Any] | None,
    on_search: Any,
    on_clear: Any,
    on_filter: Any,
    on_retry: Any,
    on_load_more: Any,
    on_detail: Any,
    on_close_detail: Any,
    on_go_dashboard: Any,
) -> ft.Control:
    evento = contexto.get("evento_actual") or {}
    if not evento:
        print("[INVITADOS][WARNING] Vista abierta sin evento activo.")
        return ft.ListView(
            controls=[
                _state_card(
                    "Selecciona un evento",
                    "Selecciona un evento antes de consultar los invitados.",
                    ft.Icons.EVENT_BUSY,
                ),
                ft.OutlinedButton(
                    content="Ir al Dashboard",
                    icon=ft.Icons.DASHBOARD,
                    on_click=lambda e: on_go_dashboard(),
                ),
            ],
            spacing=16,
            expand=True,
        )

    search_field = ft.TextField(
        label="Buscar invitado",
        hint_text="Nombre del invitado",
        value=busqueda,
        prefix_icon=ft.Icons.SEARCH,
        on_submit=lambda e: on_search(e.control.value),
        disabled=is_loading,
    )
    filtro_dropdown = ft.Dropdown(
        label="Filtro",
        value=filtro,
        options=[
            ft.DropdownOption(key=key, text=label)
            for key, label in FILTRO_LABELS.items()
        ],
        on_select=lambda e: on_filter(e.control.value),
        disabled=is_loading,
    )

    controls: list[ft.Control] = [
        ft.Row(
            [
                ft.Column(
                    [
                        ft.Text("Invitados", size=26, weight=ft.FontWeight.BOLD),
                        ft.Text(
                            f"{_get(evento, 'nombre_evento', 'Evento activo')} - {_get(evento, 'fase_evento', 'Sin fase')}",
                            size=14,
                            color=ft.Colors.ON_SURFACE_VARIANT,
                        ),
                    ],
                    spacing=4,
                    expand=True,
                ),
                _chip(f"Mostrando {len(invitados)}"),
            ],
            vertical_alignment=ft.CrossAxisAlignment.START,
        ),
        ft.ResponsiveRow(
            [
                ft.Container(search_field, col={"xs": 12, "md": 6}),
                ft.Container(filtro_dropdown, col={"xs": 12, "md": 3}),
                ft.Container(
                    ft.Row(
                        [
                            ft.ElevatedButton(
                                content="Buscar",
                                icon=ft.Icons.SEARCH,
                                disabled=is_loading,
                                on_click=lambda e: on_search(search_field.value),
                            ),
                            ft.OutlinedButton(
                                content="Limpiar",
                                icon=ft.Icons.CLEAR,
                                disabled=is_loading,
                                on_click=lambda e: on_clear(),
                            ),
                        ],
                        spacing=8,
                    ),
                    col={"xs": 12, "md": 3},
                ),
            ],
            spacing=12,
            run_spacing=12,
        ),
    ]

    if busqueda.strip() or filtro != "todos":
        controls.append(
            ft.Text(
                f"Criterio activo: busqueda {'si' if busqueda.strip() else 'no'}; filtro {FILTRO_LABELS.get(filtro, 'Todos')}.",
                size=12,
                color=ft.Colors.ON_SURFACE_VARIANT,
            )
        )

    if estado == "loading":
        controls.append(
            ft.Container(
                content=ft.Row(
                    [ft.ProgressRing(width=24, height=24), ft.Text("Cargando invitados...")],
                    spacing=12,
                ),
                padding=16,
            )
        )
    elif estado == "error":
        controls.append(_state_card("Error", mensaje, ft.Icons.ERROR_OUTLINE, on_retry))
    elif estado in {"empty", "no_results"} and not invitados:
        title = "Sin resultados" if estado == "no_results" else "Sin invitados"
        controls.append(_state_card(title, mensaje, ft.Icons.PEOPLE_OUTLINE, on_clear if estado == "no_results" else None))
    else:
        controls.append(
            ft.Column(
                [_invitado_card(invitado, on_detail) for invitado in invitados],
                spacing=10,
            )
        )
        controls.append(
            ft.Row(
                [
                    ft.Text(
                        "Hay mas resultados disponibles." if has_more else "No hay mas resultados para mostrar.",
                        size=13,
                        color=ft.Colors.ON_SURFACE_VARIANT,
                        expand=True,
                    ),
                    ft.OutlinedButton(
                        content="Cargar mas",
                        icon=ft.Icons.EXPAND_MORE,
                        disabled=(not has_more) or is_loading,
                        on_click=lambda e: on_load_more(),
                    ),
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            )
        )

    if invitado_detalle:
        controls.append(_detail_panel(invitado_detalle, on_close_detail))

    return ft.ListView(controls=controls, spacing=16, expand=True)
