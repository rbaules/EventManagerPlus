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

TIPO_BUSQUEDA_LABELS = {
    "invitado": "Invitado",
    "mesa": "Mesa",
}


def _tipo_busqueda_valido(tipo_busqueda: str | None) -> str:
    return tipo_busqueda if tipo_busqueda in TIPO_BUSQUEDA_LABELS else "invitado"


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
        content=ft.ResponsiveRow(
            [
                ft.Container(
                    content=ft.Column(
                        [
                            ft.Text(
                                str(_get(invitado, "nombre_completo", "Invitado sin nombre")),
                                size=15,
                                weight=ft.FontWeight.W_600,
                                overflow=ft.TextOverflow.ELLIPSIS,
                            ),
                            ft.Text(
                                str(_get(invitado, "mesa_texto", "Sin mesa")),
                                size=12,
                                color=ft.Colors.ON_SURFACE_VARIANT,
                            ),
                        ],
                        spacing=2,
                    ),
                    col={"xs": 12, "sm": 6, "md": 6},
                ),
                ft.Container(
                    content=_chip(
                        "Llego" if llegada else "Pendiente",
                        ft.Colors.PRIMARY_CONTAINER if llegada else ft.Colors.SECONDARY_CONTAINER,
                    ),
                    col={"xs": 6, "sm": 2, "md": 2},
                ),
                ft.Container(
                    content=ft.Text(
                        "Con novedad" if invitado.get("tiene_novedad") else "Sin novedad",
                        size=12,
                        color=ft.Colors.ON_SURFACE_VARIANT,
                    ),
                    col={"xs": 6, "sm": 2, "md": 2},
                ),
                ft.Container(
                    content=ft.IconButton(
                        icon=ft.Icons.PERSON,
                        tooltip="Ver detalle",
                        on_click=lambda e: on_detail(invitado),
                    ),
                    alignment=ft.Alignment.CENTER_RIGHT,
                    col={"xs": 12, "sm": 2, "md": 2},
                ),
            ],
            columns=12,
            spacing=8,
            run_spacing=4,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        padding=ft.Padding.symmetric(horizontal=12, vertical=8),
        border_radius=8,
        bgcolor=ft.Colors.SURFACE,
        border=ft.Border.all(width=1, color=ft.Colors.OUTLINE_VARIANT),
    )


def _invitado_card_admin(invitado: dict[str, Any], on_detail: Any, on_edit: Any, can_manage: bool) -> ft.Control:
    card = _invitado_card(invitado, on_detail)
    if not can_manage or invitado.get("es_invitado_imprevisto"):
        return card
    content = card.content
    if isinstance(content, ft.ResponsiveRow):
        content.controls.append(
            ft.Container(
                content=ft.IconButton(
                    icon=ft.Icons.EDIT,
                    tooltip="Editar invitado",
                    on_click=lambda e: on_edit(invitado),
                ),
                alignment=ft.Alignment.CENTER_RIGHT,
                col={"xs": 12, "sm": 2, "md": 2},
            )
        )
    return card


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


def _detail_panel(
    invitado: dict[str, Any] | None,
    can_delete_unexpected: bool,
    is_saving: bool,
    on_delete_unexpected: Any,
    on_close: Any,
    show_header: bool = True,
) -> ft.Control:
    if not invitado:
        return ft.Container()

    imprevisto = bool(invitado.get("es_invitado_imprevisto"))
    acciones: list[ft.Control] = []
    if can_delete_unexpected and imprevisto:
        acciones.append(
            ft.TextButton(
                content="Eliminar imprevisto",
                icon=ft.Icons.DELETE,
                disabled=is_saving,
                on_click=lambda e: on_delete_unexpected(invitado),
            )
        )

    detalles: list[ft.Control] = []
    if show_header:
        detalles.append(ft.Row(
            [
                ft.Text("Detalle del invitado", size=18, weight=ft.FontWeight.BOLD, expand=True),
                ft.TextButton(content="Cerrar", icon=ft.Icons.CLOSE, on_click=lambda e: on_close()),
            ],
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ))
    detalles.extend([
        _detail_row("Nombre", invitado.get("nombre_completo")),
        _detail_row("Llegada", invitado.get("estado_llegada")),
        _detail_row("Fecha de llegada", invitado.get("fecha_hora_conf_llegada")),
        _detail_row("Mesa", invitado.get("mesa_texto")),
        _detail_row("Puesto", invitado.get("puesto_texto")),
        _detail_row("Tipo", invitado.get("tipo_invitado")),
        _detail_row("Origen", invitado.get("origen_invitado")),
        _detail_row("Email", invitado.get("email")),
        _detail_row("Telefono", invitado.get("telefono")),
        _detail_row("Novedad", "Si" if invitado.get("tiene_novedad") else "No"),
        _detail_row("Descripcion de novedad", invitado.get("descripcion_novedad")),
    ])
    if acciones:
        detalles.append(ft.Row(acciones, spacing=8, wrap=True))

    return ft.Container(
        content=ft.Column(detalles, spacing=4),
        padding=16,
        border_radius=8,
        bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
        border=ft.Border.all(width=1, color=ft.Colors.OUTLINE_VARIANT),
    )


def _form_panel(
    form_state: dict[str, Any] | None,
    invitaciones: list[dict[str, Any]],
    can_manage: bool,
    is_saving: bool,
    form_message: str,
    on_save: Any,
    on_cancel: Any,
) -> ft.Control:
    if not form_state:
        return ft.Container()

    modo = form_state.get("modo", "crear")
    datos = form_state.get("datos", {})
    titulo = "Agregar invitado imprevisto" if modo == "imprevisto" else ("Agregar invitado" if modo == "crear" else "Editar invitado")

    nombre = ft.TextField(
        label="Nombre",
        value=str(datos.get("nombre_completo") or ""),
        max_length=80,
        disabled=is_saving or not can_manage,
    )
    email = ft.TextField(
        label="Email",
        value=str(datos.get("email") or ""),
        max_length=254,
        disabled=is_saving or not can_manage,
    )
    telefono = ft.TextField(
        label="Telefono",
        value=str(datos.get("telefono") or ""),
        max_length=20,
        disabled=is_saving or not can_manage,
    )
    mesa = ft.TextField(
        label="Mesa",
        value="" if datos.get("mesa_id") is None else str(datos.get("mesa_id")),
        disabled=is_saving or not can_manage,
    )
    puesto = ft.TextField(
        label="Puesto",
        value="" if datos.get("puesto_id") is None else str(datos.get("puesto_id")),
        disabled=is_saving or not can_manage,
    )
    principal = ft.Checkbox(
        label="Invitado principal",
        value=bool(datos.get("es_invitado_principal")),
        disabled=is_saving or not can_manage,
    )

    invitacion = ft.Dropdown(
        label="Invitacion",
        value=str(datos.get("invitacion_id") or ""),
        disabled=is_saving or not can_manage or modo != "crear",
        options=[
            ft.DropdownOption(
                key=str(item["invitacion_id"]),
                text=f"{item['destinatario']}" + (f" ({item['codigo']})" if item.get("codigo") else ""),
            )
            for item in invitaciones
        ],
        hint_text="Selecciona una invitacion",
    )

    def collect_payload() -> dict[str, Any]:
        return {
            "invitacion_id": invitacion.value,
            "nombre_completo": nombre.value,
            "email": email.value,
            "telefono": telefono.value,
            "mesa_id": mesa.value,
            "puesto_id": puesto.value,
            "es_invitado_principal": principal.value,
        }

    controls: list[ft.Control] = [
        ft.Row(
            [
                ft.Text(titulo, size=20, weight=ft.FontWeight.BOLD, expand=True),
                _chip("Evento en proceso" if modo == "imprevisto" and can_manage else ("Pre-evento" if can_manage else "Modo consulta")),
            ]
        ),
        ft.Text("La cuenta y el evento se toman del evento activo; no son editables.", size=13, color=ft.Colors.ON_SURFACE_VARIANT),
    ]
    if form_message:
        controls.append(ft.Text(form_message, size=13, color=ft.Colors.ERROR))

    controls.extend(
        [
            ft.ResponsiveRow(
                [
                    ft.Container(invitacion, col={"xs": 12, "md": 6}),
                    ft.Container(nombre, col={"xs": 12, "md": 6}),
                    ft.Container(email, col={"xs": 12, "md": 6}),
                    ft.Container(telefono, col={"xs": 12, "md": 6}),
                    ft.Container(mesa, col={"xs": 12, "md": 4}),
                    ft.Container(puesto, col={"xs": 12, "md": 4}),
                    ft.Container(principal, col={"xs": 12, "md": 4}),
                ],
                spacing=12,
                run_spacing=12,
            ),
            ft.Row(
                [
                    ft.Button(
                        content="Guardar" if modo in {"crear", "imprevisto"} else "Guardar cambios",
                        icon=ft.Icons.SAVE,
                        disabled=is_saving or not can_manage,
                        on_click=lambda e: on_save(collect_payload()),
                    ),
                    ft.OutlinedButton(
                        content="Cancelar",
                        icon=ft.Icons.CLOSE,
                        disabled=is_saving,
                        on_click=lambda e: on_cancel(),
                    ),
                    ft.ProgressRing(width=22, height=22, visible=is_saving),
                ],
                spacing=8,
            ),
        ]
    )

    return ft.Container(
        content=ft.Column(controls, spacing=12),
        padding=16,
        border_radius=8,
        bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
        border=ft.Border.all(width=1, color=ft.Colors.OUTLINE_VARIANT),
    )


def invitado_detail_view(
    invitado: dict[str, Any] | None,
    can_delete_unexpected: bool,
    is_saving: bool,
    mensaje: str,
    on_delete_unexpected: Any,
    on_back: Any,
) -> ft.Control:
    if not invitado:
        return ft.ListView(
            controls=[
                ft.Row([
                    ft.IconButton(icon=ft.Icons.ARROW_BACK, tooltip="Regresar", on_click=lambda e: on_back()),
                    ft.Text("Detalle del invitado", size=26, weight=ft.FontWeight.BOLD),
                ]),
                ft.Text(mensaje or "No fue posible cargar el invitado.", color=ft.Colors.ERROR),
            ],
            spacing=16,
            expand=True,
        )
    return ft.ListView(
        controls=[
            ft.Row([
                ft.IconButton(icon=ft.Icons.ARROW_BACK, tooltip="Regresar a invitados", on_click=lambda e: on_back()),
                ft.Text("Detalle del invitado", size=26, weight=ft.FontWeight.BOLD),
            ]),
            _detail_panel(invitado, can_delete_unexpected, is_saving, on_delete_unexpected, on_back, False),
        ],
        spacing=16,
        expand=True,
    )


def invitado_form_view(
    form_state: dict[str, Any],
    invitaciones: list[dict[str, Any]],
    can_manage: bool,
    is_saving: bool,
    form_message: str,
    on_save: Any,
    on_back: Any,
) -> ft.Control:
    title = {
        "crear": "Agregar invitado planificado",
        "editar": "Editar invitado",
        "imprevisto": "Agregar invitado imprevisto",
    }.get(str(form_state.get("modo")), "Invitado")
    return ft.ListView(
        controls=[
            ft.Row([
                ft.IconButton(icon=ft.Icons.ARROW_BACK, tooltip="Regresar a invitados", on_click=lambda e: on_back()),
                ft.Text(title, size=26, weight=ft.FontWeight.BOLD),
            ]),
            _form_panel(form_state, invitaciones, can_manage, is_saving, form_message, on_save, on_back),
        ],
        spacing=16,
        expand=True,
    )


def invitados_view(
    contexto: dict[str, Any],
    estado: str,
    invitados: list[dict[str, Any]],
    mensaje: str,
    tipo_busqueda: str,
    busqueda: str,
    filtro: str,
    has_more: bool,
    is_loading: bool,
    invitado_detalle: dict[str, Any] | None,
    can_manage_planned: bool,
    can_confirm_arrival: bool,
    can_reverse_arrival: bool,
    can_manage_unexpected: bool,
    can_delete_unexpected: bool,
    invitaciones: list[dict[str, Any]],
    form_state: dict[str, Any] | None,
    form_message: str,
    is_saving: bool,
    on_search: Any,
    on_search_type_change: Any,
    on_clear: Any,
    on_filter: Any,
    on_retry: Any,
    on_load_more: Any,
    on_detail: Any,
    on_close_detail: Any,
    on_go_dashboard: Any,
    on_new_guest: Any,
    on_new_unexpected_guest: Any,
    on_edit_guest: Any,
    on_save_guest: Any,
    on_cancel_form: Any,
    on_confirm_arrival: Any,
    on_reverse_arrival: Any,
    on_delete_unexpected: Any,
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

    tipo_busqueda = _tipo_busqueda_valido(tipo_busqueda)
    tipo_es_mesa = tipo_busqueda == "mesa"
    search_label = "Buscar mesa" if tipo_es_mesa else "Buscar invitado"
    search_hint = "Escribe parte del nombre o numero de la mesa" if tipo_es_mesa else "Escribe parte del nombre del invitado"
    helper_text = (
        "Se mostraran todos los invitados asignados a la mesa encontrada."
        if tipo_es_mesa
        else "La busqueda se realizara por nombre."
    )
    search_field = ft.TextField(
        label=search_label,
        hint_text=search_hint,
        value=busqueda,
        prefix_icon=ft.Icons.TABLE_RESTAURANT if tipo_es_mesa else ft.Icons.PERSON_SEARCH,
        on_submit=lambda e: on_search(e.control.value),
        disabled=is_loading,
    )
    tipo_dropdown = ft.Dropdown(
        label="Buscar por",
        value=tipo_busqueda,
        options=[
            ft.DropdownOption(key="invitado", text="Invitado"),
            ft.DropdownOption(key="mesa", text="Mesa"),
        ],
        leading_icon=ft.Icons.FILTER_ALT,
        on_select=lambda e: on_search_type_change(e.control.value),
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
                ft.Text("Invitados", size=26, weight=ft.FontWeight.BOLD, expand=True),
                _chip(f"Mostrando {len(invitados)}"),
                _chip("Operacion habilitada" if (can_manage_planned or can_confirm_arrival or can_manage_unexpected or can_delete_unexpected) else "Modo consulta"),
            ],
            vertical_alignment=ft.CrossAxisAlignment.START,
        ),
        ft.ResponsiveRow(
            [
                ft.Container(tipo_dropdown, col={"xs": 12, "md": 2}),
                ft.Container(search_field, col={"xs": 12, "md": 4}),
                ft.Container(filtro_dropdown, col={"xs": 12, "md": 3}),
                ft.Container(
                    ft.Row(
                        [
                            ft.Button(
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
                        wrap=True,
                    ),
                    col={"xs": 12, "md": 3},
                ),
            ],
            spacing=12,
            run_spacing=12,
        ),
        ft.Text(helper_text, size=12, color=ft.Colors.ON_SURFACE_VARIANT),
    ]

    if busqueda.strip() or filtro != "todos":
        criterio = (
            f"Invitados de mesas que coinciden con: \"{busqueda.strip()}\"."
            if tipo_es_mesa and busqueda.strip()
            else f"Invitados que coinciden con: \"{busqueda.strip()}\"."
            if busqueda.strip()
            else "Listado general."
        )
        controls.append(
            ft.Text(
                f"{criterio} {len(invitados)} invitados encontrados. Filtro: {FILTRO_LABELS.get(filtro, 'Todos')}.",
                size=12,
                color=ft.Colors.ON_SURFACE_VARIANT,
            )
        )

    if can_manage_planned or can_manage_unexpected:
        controls.append(
            ft.Row(
                [
                    ft.Button(
                        content="Agregar planificado",
                        icon=ft.Icons.PERSON_ADD,
                        disabled=(not can_manage_planned) or is_loading or is_saving,
                        on_click=lambda e: on_new_guest(),
                    ),
                    ft.OutlinedButton(
                        content="Agregar imprevisto",
                        icon=ft.Icons.PERSON_ADD,
                        disabled=(not can_manage_unexpected) or is_loading or is_saving,
                        on_click=lambda e: on_new_unexpected_guest(),
                    ),
                ],
                alignment=ft.MainAxisAlignment.END,
                spacing=8,
                wrap=True,
            )
        )

    if form_message:
        controls.append(ft.Text(form_message, size=13, color=ft.Colors.ON_SURFACE_VARIANT))

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
        empty_message = mensaje
        if estado == "no_results" and tipo_es_mesa:
            empty_message = "No se encontraron mesas o invitados con ese patron."
        elif estado == "no_results":
            empty_message = "No se encontraron invitados con ese nombre."
        controls.append(_state_card(title, empty_message, ft.Icons.PEOPLE_OUTLINE, on_clear if estado == "no_results" else None))
    elif estado == "idle":
        controls.append(_state_card("Busqueda pendiente", mensaje or "Presiona Buscar para consultar los invitados.", ft.Icons.SEARCH))
    else:
        controls.append(
            ft.Column(
                [
                    _invitado_card_admin(
                        invitado,
                        on_detail,
                        on_edit_guest,
                        can_manage_planned,
                    )
                    for invitado in invitados
                ],
                spacing=6,
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

    return ft.ListView(controls=controls, spacing=16, expand=True)
