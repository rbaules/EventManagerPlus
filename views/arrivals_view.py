from __future__ import annotations

from typing import Any

import flet as ft


def _get(source: dict[str, Any] | None, key: str, default: str = "-") -> Any:
    if not source:
        return default
    value = source.get(key)
    return default if value in (None, "") else value


def _chip(text: str, bgcolor: Any = ft.Colors.SURFACE_CONTAINER) -> ft.Control:
    return ft.Container(
        content=ft.Text(text, size=12, weight=ft.FontWeight.W_600),
        padding=ft.Padding.symmetric(horizontal=10, vertical=4),
        border_radius=16,
        bgcolor=bgcolor,
    )


def _state_card(title: str, message: str, icon: Any, on_retry: Any | None = None) -> ft.Control:
    controls: list[ft.Control] = [
        ft.Icon(icon, size=36, color=ft.Colors.ON_SURFACE_VARIANT),
        ft.Text(title, size=18, weight=ft.FontWeight.BOLD),
        ft.Text(message, size=14, color=ft.Colors.ON_SURFACE_VARIANT, text_align=ft.TextAlign.CENTER),
    ]
    if on_retry:
        controls.append(ft.OutlinedButton(content="Reintentar", icon=ft.Icons.REFRESH, on_click=lambda e: on_retry()))
    return ft.Container(
        content=ft.Column(controls, spacing=10, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
        padding=24,
        border_radius=8,
        bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
        border=ft.Border.all(width=1, color=ft.Colors.OUTLINE_VARIANT),
    )


def _resultado_card(invitado: dict[str, Any], on_select: Any) -> ft.Control:
    llegada = bool(invitado.get("llegada_confirmada"))
    return ft.Container(
        content=ft.Row(
            [
                ft.Column(
                    [
                        ft.Text(str(_get(invitado, "nombre_completo", "Invitado sin nombre")), size=15, weight=ft.FontWeight.BOLD),
                        ft.Text(
                            f"{_get(invitado, 'mesa_texto')} - {_get(invitado, 'puesto_texto')}",
                            size=12,
                            color=ft.Colors.ON_SURFACE_VARIANT,
                        ),
                    ],
                    spacing=3,
                    expand=True,
                ),
                _chip("Llego" if llegada else "Pendiente", ft.Colors.PRIMARY_CONTAINER if llegada else ft.Colors.SECONDARY_CONTAINER),
                ft.FilledTonalButton(content="Seleccionar", icon=ft.Icons.GROUP, on_click=lambda e: on_select(invitado)),
            ],
            spacing=8,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        padding=12,
        border_radius=8,
        bgcolor=ft.Colors.SURFACE,
        border=ft.Border.all(width=1, color=ft.Colors.OUTLINE_VARIANT),
    )


def construir_fila_llegada(
    invitado: dict[str, Any],
    selected: bool,
    is_saving: bool,
    can_reverse_arrival: bool,
    on_toggle: Any,
    on_reverse_arrival: Any,
) -> ft.Control:
    llegada = bool(invitado.get("llegada_confirmada"))
    invitado_id = _get(invitado, "invitado_id", "sin_id")
    nombre = str(_get(invitado, "nombre_completo", "Invitado sin nombre"))
    mesa = str(_get(invitado, "mesa_texto", "Sin mesa"))
    puesto = str(_get(invitado, "puesto_texto", "Sin puesto"))
    print("[LLEGADAS][INFO] Construyendo fila de invitado:", invitado_id)

    accion: ft.Control
    if llegada and can_reverse_arrival:
        accion = ft.OutlinedButton(
            content="Revertir llegada",
            icon=ft.Icons.UNDO,
            disabled=is_saving,
            on_click=lambda e: on_reverse_arrival(invitado),
        )
    elif llegada:
        accion = ft.Text("Llegada confirmada", size=12, color=ft.Colors.ON_SURFACE_VARIANT)
    else:
        accion = ft.Checkbox(
            label="Seleccionar",
            value=selected,
            disabled=is_saving,
            on_change=lambda e: on_toggle(invitado, bool(e.control.value)),
        )

    return ft.Container(
        content=ft.ResponsiveRow(
            [
                ft.Container(
                    content=ft.Column(
                        [
                            ft.Text(nombre, size=15, weight=ft.FontWeight.W_600, overflow=ft.TextOverflow.ELLIPSIS),
                            ft.Text(f"{mesa} - {puesto}", size=12, color=ft.Colors.ON_SURFACE_VARIANT),
                        ],
                        spacing=3,
                    ),
                    col={"xs": 12, "sm": 7, "md": 7},
                ),
                ft.Container(
                    content=_chip(
                        "Llego" if llegada else "Pendiente",
                        ft.Colors.PRIMARY_CONTAINER if llegada else ft.Colors.SECONDARY_CONTAINER,
                    ),
                    col={"xs": 6, "sm": 2, "md": 2},
                ),
                ft.Container(
                    content=accion,
                    alignment=ft.Alignment.CENTER_RIGHT,
                    col={"xs": 6, "sm": 3, "md": 3},
                ),
            ],
            columns=12,
            spacing=8,
            run_spacing=6,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        padding=12,
        border_radius=8,
        bgcolor=ft.Colors.SECONDARY_CONTAINER if selected and not llegada else ft.Colors.SURFACE,
        border=ft.Border.all(width=1, color=ft.Colors.OUTLINE_VARIANT),
    )


def arrivals_view(
    contexto: dict[str, Any],
    estado: str,
    mensaje: str,
    busqueda: str,
    resultados: list[dict[str, Any]],
    invitacion: dict[str, Any] | None,
    integrantes: list[dict[str, Any]],
    seleccionados: set[str],
    can_reverse_arrival: bool,
    is_loading: bool,
    is_saving: bool,
    on_search: Any,
    on_clear: Any,
    on_select_guest: Any,
    on_toggle_guest: Any,
    on_select_pending: Any,
    on_confirm_selected: Any,
    on_reverse_arrival: Any,
    on_retry: Any,
) -> ft.Control:
    evento = contexto.get("evento_actual") or {}
    if not contexto.get("puede_registrar_llegadas"):
        return ft.ListView(
            controls=[
                _state_card(
                    "Registro no disponible",
                    "El registro de llegadas solo esta disponible cuando el evento esta Activo y en fase Evento en proceso.",
                    ft.Icons.EVENT_BUSY,
                )
            ],
            spacing=16,
            expand=True,
        )

    search_field = ft.TextField(
        label="Buscar invitado",
        hint_text="Escribe parte del nombre y presiona Enter",
        value=busqueda,
        prefix_icon=ft.Icons.SEARCH,
        autofocus=True,
        disabled=is_loading or is_saving,
        on_submit=lambda e: on_search(e.control.value),
    )

    pendientes = [item for item in integrantes if not item.get("llegada_confirmada")]
    confirmados = [item for item in integrantes if item.get("llegada_confirmada")]
    seleccion_count = len(seleccionados)
    controls: list[ft.Control] = [
        ft.Row(
            [
                ft.Column(
                    [
                        ft.Text("Registrar llegadas", size=26, weight=ft.FontWeight.BOLD),
                        ft.Text(
                            f"{_get(evento, 'nombre_evento', 'Evento activo')} - {_get(evento, 'fase_evento', 'Sin fase')}",
                            size=14,
                            color=ft.Colors.ON_SURFACE_VARIANT,
                        ),
                    ],
                    spacing=4,
                    expand=True,
                ),
                _chip("Evento en proceso"),
            ],
            vertical_alignment=ft.CrossAxisAlignment.START,
        ),
        ft.ResponsiveRow(
            [
                ft.Container(search_field, col={"xs": 12, "md": 8}),
                ft.Container(
                    ft.Row(
                        [
                            ft.ElevatedButton(
                                content="Buscar",
                                icon=ft.Icons.SEARCH,
                                disabled=is_loading or is_saving,
                                on_click=lambda e: on_search(search_field.value),
                            ),
                            ft.OutlinedButton(
                                content="Limpiar",
                                icon=ft.Icons.CLEAR,
                                disabled=is_loading or is_saving,
                                on_click=lambda e: on_clear(),
                            ),
                        ],
                        spacing=8,
                        wrap=True,
                    ),
                    col={"xs": 12, "md": 4},
                ),
            ],
            spacing=12,
            run_spacing=12,
        ),
    ]

    if mensaje:
        controls.append(ft.Text(mensaje, size=13, color=ft.Colors.ON_SURFACE_VARIANT))

    if is_loading:
        controls.append(
            ft.Container(
                content=ft.Row([ft.ProgressRing(width=24, height=24), ft.Text("Buscando invitados...")], spacing=12),
                padding=16,
            )
        )
    elif estado == "error":
        controls.append(_state_card("No fue posible cargar la informacion", mensaje, ft.Icons.ERROR_OUTLINE, on_retry))
    elif estado == "no_results":
        controls.append(_state_card("Sin resultados", "No se encontraron invitados con ese criterio.", ft.Icons.PEOPLE_OUTLINE))
    elif resultados:
        controls.append(ft.Text("Selecciona una persona para cargar toda su invitacion.", size=14, weight=ft.FontWeight.W_600))
        controls.append(ft.Column([_resultado_card(item, on_select_guest) for item in resultados], spacing=8))

    if invitacion:
        print(
            "[LLEGADAS][INFO] Invitacion seleccionada:",
            _get(invitacion, "invitacion_id", _get(invitacion, "codigo", "sin_id")),
        )
        print("[LLEGADAS][INFO] Integrantes recuperados:", len(integrantes))
        print("[LLEGADAS][INFO] Pendientes:", len(pendientes), "confirmados:", len(confirmados))
        filas_integrantes: list[ft.Control] = []
        for item in integrantes:
            try:
                filas_integrantes.append(
                    construir_fila_llegada(
                        item,
                        str(item.get("invitado_uuid")) in seleccionados,
                        is_saving,
                        can_reverse_arrival,
                        on_toggle_guest,
                        on_reverse_arrival,
                    )
                )
            except Exception as ex:
                print(
                    "[LLEGADAS][ERROR] No fue posible construir la fila del invitado:",
                    item.get("invitado_id"),
                    type(ex).__name__,
                    str(ex),
                )
        print("[LLEGADAS][INFO] Filas construidas:", len(filas_integrantes))
        print("[LLEGADAS][INFO] Controles agregados a la lista visible:", len(filas_integrantes))
        print("[LLEGADAS][INFO] Lista visual actualizada.")

        lista_integrantes: ft.Control
        if filas_integrantes:
            lista_integrantes = ft.Column(filas_integrantes, spacing=8)
        else:
            lista_integrantes = ft.Container(
                content=ft.Text(
                    "No se encontraron integrantes para esta invitacion.",
                    size=14,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                ),
                padding=12,
                border_radius=8,
                bgcolor=ft.Colors.SURFACE,
                border=ft.Border.all(width=1, color=ft.Colors.OUTLINE_VARIANT),
            )
            if integrantes:
                print("[LLEGADAS][ERROR] Control de lista no montado o no disponible.")

        controls.append(
            ft.Container(
                content=ft.Column(
                    [
                        ft.Row(
                            [
                                ft.Column(
                                    [
                                        ft.Text(str(_get(invitacion, "destinatario", "Invitacion")), size=18, weight=ft.FontWeight.BOLD),
                                        ft.Text(
                                            f"{len(integrantes)} integrantes - {len(pendientes)} pendientes",
                                            size=13,
                                            color=ft.Colors.ON_SURFACE_VARIANT,
                                        ),
                                    ],
                                    expand=True,
                                ),
                                _chip(str(_get(invitacion, "codigo", "")) if _get(invitacion, "codigo", "") != "-" else "Sin codigo"),
                            ],
                            vertical_alignment=ft.CrossAxisAlignment.START,
                        ),
                        ft.Row(
                            [
                                ft.OutlinedButton(
                                    content="Seleccionar pendientes",
                                    icon=ft.Icons.CHECKLIST,
                                    disabled=is_saving or not pendientes,
                                    on_click=lambda e: on_select_pending(),
                                ),
                                ft.ElevatedButton(
                                    content=f"Confirmar seleccionados ({seleccion_count})",
                                    icon=ft.Icons.HOW_TO_REG,
                                    disabled=is_saving or seleccion_count == 0,
                                    on_click=lambda e: on_confirm_selected(),
                                ),
                                ft.ProgressRing(width=22, height=22, visible=is_saving),
                            ],
                            spacing=8,
                            wrap=True,
                        ),
                        lista_integrantes,
                    ],
                    spacing=12,
                ),
                padding=16,
                border_radius=8,
                bgcolor=ft.Colors.SURFACE,
                border=ft.Border.all(width=1, color=ft.Colors.OUTLINE_VARIANT),
            )
        )

    return ft.ListView(controls=controls, spacing=16, expand=True)
