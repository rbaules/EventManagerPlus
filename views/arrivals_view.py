from __future__ import annotations

from typing import Any
import unicodedata

import flet as ft

from components.responsive import LayoutMode, uses_operational_cards
from services.time_service import hora_panama


def _get(source: dict[str, Any] | None, key: str, default: str = "-") -> Any:
    if not source:
        return default
    value = source.get(key)
    return default if value in (None, "") else value


def _guest_sort_key(invitado: dict[str, Any]) -> tuple[str, str, str]:
    nombre = " ".join(str(invitado.get("nombre_completo") or "").strip().split()).casefold()
    nombre = "".join(
        char for char in unicodedata.normalize("NFKD", nombre)
        if not unicodedata.combining(char)
    )
    secondary = str(invitado.get("invitado_uuid") or invitado.get("invitado_id") or "")
    invitation = str(invitado.get("invitacion_id") or "")
    return nombre, invitation, secondary


def _sorted_guests(invitados: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(invitados, key=_guest_sort_key)


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


def _resultado_card(invitado: dict[str, Any], on_select: Any, *, compact: bool = False) -> ft.Control:
    llegada = bool(invitado.get("llegada_confirmada"))
    return ft.Container(
        content=ft.ResponsiveRow(
            [
                ft.Container(
                    ft.Column(
                        [
                            ft.Text(str(_get(invitado, "nombre_completo", "Invitado sin nombre")), size=15, weight=ft.FontWeight.BOLD),
                            ft.Text(f"Invitación {_get(invitado, 'invitacion_id', '—')} · {('Prin' if invitado.get('es_invitado_principal') else 'Acom')}", size=12, color=ft.Colors.ON_SURFACE_VARIANT),
                            ft.Text(f"{_get(invitado, 'mesa_texto')} - {_get(invitado, 'puesto_texto')} · Novedad: {'Sí' if invitado.get('tiene_novedad') else 'No'}", size=12, color=ft.Colors.ON_SURFACE_VARIANT),
                        ],
                        spacing=3,
                    ),
                    col={"xs": 12, "sm": 7},
                ),
                ft.Container(_chip("Llego" if llegada else "Pendiente", ft.Colors.PRIMARY_CONTAINER if llegada else ft.Colors.SECONDARY_CONTAINER), col={"xs": 5, "sm": 2}),
                ft.Container(ft.FilledTonalButton(content="Seleccionar", icon=ft.Icons.GROUP, on_click=lambda e: on_select(invitado)), col={"xs": 7, "sm": 3}, alignment=ft.Alignment.CENTER_RIGHT),
            ],
            spacing=8,
            run_spacing=6,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        padding=12,
        border_radius=8,
        bgcolor=ft.Colors.SURFACE,
        border=ft.Border.all(width=1, color=ft.Colors.OUTLINE_VARIANT),
        data={"arrivals_row": "search_compact" if compact else "search_card"},
    )


def _resultados_table(resultados: list[dict[str, Any]], on_select: Any, *, compact: bool = False) -> ft.Control:
    rows = []
    for invitado in _sorted_guests(resultados):
        llegada = bool(invitado.get("llegada_confirmada"))
        grupo = "Prin" if invitado.get("es_invitado_principal") else "Acom"
        invitacion = invitado.get("invitacion_id")
        rows.append(ft.DataRow(cells=[
            ft.DataCell(ft.Text(str(_get(invitado, "nombre_completo", "Invitado sin nombre")))),
            ft.DataCell(ft.Text(f"{invitacion} - {grupo}" if invitacion is not None else grupo)),
            ft.DataCell(ft.Text(str(_get(invitado, "mesa_texto", "Sin mesa")))),
            ft.DataCell(ft.Row([ft.Icon(ft.Icons.CHECK_CIRCLE if llegada else ft.Icons.SCHEDULE, size=18), ft.Text("Llegó" if llegada else "Pendiente")], spacing=6)),
            ft.DataCell(ft.Text("Sí" if invitado.get("tiene_novedad") else "No")),
            ft.DataCell(ft.FilledTonalButton(content="Seleccionar", icon=ft.Icons.GROUP, on_click=lambda e, item=invitado: on_select(item))),
        ], data={"guest_sort_id": str(invitado.get("invitado_uuid") or invitado.get("invitado_id") or "")}))
    return ft.Row([ft.DataTable(
        columns=[ft.DataColumn(label) for label in ("Invitado", "Invitación / Grupo", "Mesa", "Estado", "Novedad", "Acciones")],
        rows=rows,
        column_spacing=10 if compact else 18,
        heading_row_color=ft.Colors.SURFACE_CONTAINER_HIGHEST,
        border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
        border_radius=10,
        data_row_min_height=48 if compact else 52,
        data_row_max_height=64 if compact else 72,
        data={"arrivals_grid": "search"},
    )], scroll=ft.ScrollMode.AUTO)


def _novedad_action(invitado: dict[str, Any], on_novelty: Any, can_edit_novelty: bool) -> ft.Control | None:
    if not invitado.get("tiene_novedad") and not can_edit_novelty:
        return None
    readonly = not can_edit_novelty
    return ft.IconButton(
        icon=ft.Icons.VISIBILITY if readonly else (ft.Icons.EDIT_NOTE if invitado.get("tiene_novedad") else ft.Icons.NOTE_ADD),
        tooltip="Ver novedad" if readonly else ("Ver / Editar novedad" if invitado.get("tiene_novedad") else "Registrar novedad"),
        on_click=lambda e: on_novelty(invitado),
    )


def construir_fila_llegada(
    invitado: dict[str, Any],
    selected: bool,
    is_saving: bool,
    can_reverse_arrival: bool,
    on_toggle: Any,
    on_reverse_arrival: Any,
    on_novelty: Any,
    can_edit_novelty: bool = True,
) -> ft.Control:
    llegada = bool(invitado.get("llegada_confirmada"))
    invitado_id = _get(invitado, "invitado_id", "sin_id")
    nombre = str(_get(invitado, "nombre_completo", "Invitado sin nombre"))
    mesa = str(_get(invitado, "mesa_texto", "Sin mesa"))
    puesto = str(_get(invitado, "puesto_texto", "Sin puesto"))
    hora_llegada = hora_panama(invitado.get("fecha_hora_conf_llegada")) if llegada else None
    print("[LLEGADAS][INFO] Construyendo fila de invitado:", invitado_id)

    accion: ft.Control
    if llegada and can_reverse_arrival:
        accion = ft.IconButton(
            icon=ft.Icons.RESTORE,
            tooltip="Revertir llegada",
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
                            ft.Text(
                                f"Novedad: {'Sí' if invitado.get('tiene_novedad') else 'No'}",
                                size=12,
                                color=ft.Colors.ON_SURFACE_VARIANT,
                                tooltip=invitado.get("descripcion_novedad") or None,
                            ),
                            ft.Text(
                                f"Hora de llegada: {hora_llegada}",
                                size=12,
                                color=ft.Colors.ON_SURFACE_VARIANT,
                                visible=bool(hora_llegada),
                            ),
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
                    content=ft.Row([item for item in (_novedad_action(invitado, on_novelty, can_edit_novelty), accion) if item is not None], spacing=8, alignment=ft.MainAxisAlignment.END),
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
    on_novelty: Any = None,
    layout: LayoutMode = LayoutMode.DESKTOP_WIDE,
    can_edit_novelty: bool = True,
) -> ft.Control:
    on_novelty = on_novelty or (lambda invitado: None)
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
        autofocus=False,
        disabled=is_loading or is_saving,
        on_submit=lambda e: on_search(e.control.value),
    )

    resultados_ordenados = _sorted_guests(resultados)
    integrantes_ordenados = _sorted_guests(integrantes)
    pendientes = [item for item in integrantes_ordenados if not item.get("llegada_confirmada")]
    confirmados = [item for item in integrantes_ordenados if item.get("llegada_confirmada")]
    seleccion_count = len(seleccionados)
    controls: list[ft.Control] = [
        ft.Row(
            [
                ft.Text("Registrar llegadas", size=26, weight=ft.FontWeight.BOLD, expand=True),
            ],
            vertical_alignment=ft.CrossAxisAlignment.START,
        ),
        ft.ResponsiveRow(
            [
                ft.Container(search_field, col={"xs": 12, "md": 8}),
                ft.Container(
                    ft.Row(
                        [
                            ft.Button(
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
        if uses_operational_cards(layout):
            controls.append(ft.Column(
                [_resultado_card(item, on_select_guest) for item in resultados_ordenados],
                spacing=8,
                data={"arrivals_grid": "search_cards"},
            ))
        else:
            controls.append(_resultados_table(
                resultados_ordenados,
                on_select_guest,
                compact=layout == LayoutMode.TABLET_PORTRAIT,
            ))

    if invitacion:
        print(
            "[LLEGADAS][INFO] Invitacion seleccionada:",
            _get(invitacion, "invitacion_id", _get(invitacion, "codigo", "sin_id")),
        )
        print("[LLEGADAS][INFO] Integrantes recuperados:", len(integrantes))
        print("[LLEGADAS][INFO] Pendientes:", len(pendientes), "confirmados:", len(confirmados))
        local_controls: dict[str, ft.Control] = {}

        def handle_local_toggle(item: dict[str, Any], selected: bool) -> None:
            on_toggle_guest(item, selected)
            button = local_controls.get("confirm_selected")
            if button is None:
                return
            count = len(seleccionados)
            button.content = f"Confirmar seleccionados ({count})"
            button.disabled = is_saving or count == 0
            try:
                button.update()
            except RuntimeError as ex:
                if "must be added to the page first" not in str(ex):
                    raise

        filas_integrantes: list[ft.Control] = []
        for item in integrantes_ordenados:
            try:
                filas_integrantes.append(
                    construir_fila_llegada(
                        item,
                        str(item.get("invitado_uuid")) in seleccionados,
                        is_saving,
                        can_reverse_arrival,
                        handle_local_toggle,
                        on_reverse_arrival,
                        on_novelty,
                        can_edit_novelty,
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

        def confirm_selected_button() -> ft.Button:
            button = ft.Button(
                content=f"Confirmar seleccionados ({seleccion_count})",
                icon=ft.Icons.HOW_TO_REG,
                bgcolor=ft.Colors.PRIMARY,
                color=ft.Colors.ON_PRIMARY,
                disabled=is_saving or seleccion_count == 0,
                on_click=lambda e: on_confirm_selected(),
                data={"arrivals_action": "confirm_selected"},
            )
            local_controls["confirm_selected"] = button
            return button

        lista_integrantes: ft.Control
        if filas_integrantes:
            if uses_operational_cards(layout):
                lista_integrantes = ft.Column(
                    filas_integrantes,
                    spacing=8,
                    data={"arrivals_grid": "confirmation_cards"},
                )
            else:
                desktop_rows = []
                for item in integrantes_ordenados:
                    llegada = bool(item.get("llegada_confirmada"))
                    selected = str(item.get("invitado_uuid")) in seleccionados
                    if llegada and can_reverse_arrival:
                        confirm_action = ft.IconButton(icon=ft.Icons.RESTORE, tooltip="Revertir llegada", disabled=is_saving, on_click=lambda e, row=item: on_reverse_arrival(row))
                    elif llegada:
                        confirm_action = ft.Text("Confirmada", size=12)
                    else:
                        confirm_action = ft.Checkbox(value=selected, disabled=is_saving, on_change=lambda e, row=item: handle_local_toggle(row, bool(e.control.value)))
                    novelty_action = _novedad_action(item, on_novelty, can_edit_novelty)
                    desktop_rows.append(ft.DataRow(cells=[
                        ft.DataCell(ft.Text(f"{_get(item, 'nombre_completo', 'Invitado')} · {('Prin' if item.get('es_invitado_principal') else 'Acom')}")),
                        ft.DataCell(ft.Text(str(_get(item, "mesa_texto", "Sin mesa")))),
                        ft.DataCell(ft.Row([ft.Icon(ft.Icons.CHECK_CIRCLE if llegada else ft.Icons.SCHEDULE, size=18), ft.Text("Llegó" if llegada else "Pendiente")], spacing=6)),
                        ft.DataCell(ft.Text(hora_panama(item.get("fecha_hora_conf_llegada")) or "—")),
                        ft.DataCell(ft.Row([ft.Text("Sí" if item.get("tiene_novedad") else "No"), *([novelty_action] if novelty_action else [])], spacing=8)),
                        ft.DataCell(confirm_action),
                    ], data={"guest_sort_id": str(item.get("invitado_uuid") or item.get("invitado_id") or "")}))
                lista_integrantes = ft.Row([ft.DataTable(
                    columns=[
                        *[ft.DataColumn(label) for label in ("Invitado", "Mesa", "Estado", "Hora llegada", "Novedad")],
                        ft.DataColumn(ft.Text("Llegada"), data={"arrivals_column": "confirmation"}),
                    ],
                    rows=desktop_rows,
                    column_spacing=10 if layout == LayoutMode.TABLET_PORTRAIT else 18,
                    heading_row_color=ft.Colors.SURFACE_CONTAINER_HIGHEST,
                    border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
                    border_radius=10,
                    data_row_min_height=48 if layout == LayoutMode.TABLET_PORTRAIT else 52,
                    data_row_max_height=64 if layout == LayoutMode.TABLET_PORTRAIT else 72,
                    data={"arrivals_grid": "confirmation"},
                )], scroll=ft.ScrollMode.AUTO)
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
                                    data={"arrivals_action": "select_pending"},
                                ),
                                confirm_selected_button(),
                                ft.ProgressRing(width=22, height=22, visible=is_saving),
                            ],
                            spacing=8,
                            wrap=True,
                            data={"arrivals_action_row": "group_confirmation"},
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
