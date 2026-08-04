from __future__ import annotations

from typing import Any

import flet as ft


def _chip(text: str, color: Any = ft.Colors.SURFACE_CONTAINER) -> ft.Control:
    return ft.Container(
        content=ft.Text(text, size=12, weight=ft.FontWeight.W_600),
        padding=ft.Padding.symmetric(horizontal=10, vertical=4),
        border_radius=16,
        bgcolor=color,
    )


def _state(title: str, message: str, icon: Any, on_retry: Any | None = None) -> ft.Control:
    controls: list[ft.Control] = [
        ft.Icon(icon, size=38, color=ft.Colors.ON_SURFACE_VARIANT),
        ft.Text(title, size=20, weight=ft.FontWeight.BOLD),
        ft.Text(message, text_align=ft.TextAlign.CENTER, color=ft.Colors.ON_SURFACE_VARIANT),
    ]
    if on_retry:
        controls.append(ft.OutlinedButton(content="Reintentar", icon=ft.Icons.REFRESH, on_click=lambda e: on_retry()))
    return ft.Container(
        content=ft.Column(controls, spacing=10, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
        padding=24,
        border_radius=10,
        bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
        border=ft.Border.all(width=1, color=ft.Colors.OUTLINE_VARIANT),
    )


def _numero(value: Any) -> str:
    return "-" if value in (None, "") else str(value)


def _lugar_card(
    lugar: dict[str, Any],
    seleccionado: bool,
    salones_count: int,
    can_manage: bool,
    on_select: Any,
    on_edit: Any,
    on_change_state: Any,
) -> ft.Control:
    acciones: list[ft.Control] = [
        ft.OutlinedButton(
            content="Ver salones",
            icon=ft.Icons.MEETING_ROOM,
            on_click=lambda e: on_select(lugar),
        )
    ]
    if can_manage:
        acciones.extend(
            [
                ft.IconButton(
                    icon=ft.Icons.EDIT,
                    tooltip="Editar lugar",
                    on_click=lambda e: on_edit(lugar),
                ),
                ft.IconButton(
                    icon=ft.Icons.TOGGLE_OFF if lugar.get("estado") == "Activo" else ft.Icons.TOGGLE_ON,
                    tooltip="Desactivar lugar" if lugar.get("estado") == "Activo" else "Activar lugar",
                    on_click=lambda e: on_change_state(
                        lugar,
                        "Inactivo" if lugar.get("estado") == "Activo" else "Activo",
                    ),
                ),
            ]
        )
    return ft.Container(
        content=ft.Column(
            [
                ft.Row(
                    [
                        ft.Text(str(lugar.get("nombre") or "Lugar sin nombre"), size=17, weight=ft.FontWeight.BOLD, expand=True),
                        _chip(
                            str(lugar.get("estado") or "Sin estado"),
                            ft.Colors.PRIMARY_CONTAINER if lugar.get("estado") == "Activo" else ft.Colors.SURFACE_CONTAINER,
                        ),
                    ]
                ),
                ft.Text(
                    " · ".join(
                        value
                        for value in (
                            str(lugar.get("tipo") or ""),
                            str(lugar.get("ciudad") or ""),
                            str(lugar.get("pais_nombre") or lugar.get("pais_id") or ""),
                        )
                        if value
                    )
                    or "Sin ubicación detallada",
                    size=13,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                ),
                ft.Text(str(lugar.get("direccion") or "Sin dirección"), size=13),
                ft.Text(f"{salones_count} salón(es)", size=12, color=ft.Colors.ON_SURFACE_VARIANT),
                ft.Row(acciones, alignment=ft.MainAxisAlignment.END, wrap=True),
            ],
            spacing=7,
        ),
        padding=14,
        border_radius=10,
        bgcolor=ft.Colors.PRIMARY_CONTAINER if seleccionado else ft.Colors.SURFACE,
        border=ft.Border.all(
            width=2 if seleccionado else 1,
            color=ft.Colors.PRIMARY if seleccionado else ft.Colors.OUTLINE_VARIANT,
        ),
    )


def _salon_card(
    salon: dict[str, Any],
    can_manage: bool,
    on_edit: Any,
    on_change_state: Any,
) -> ft.Control:
    acciones: list[ft.Control] = []
    if can_manage:
        acciones = [
            ft.IconButton(icon=ft.Icons.EDIT, tooltip="Editar salón", on_click=lambda e: on_edit(salon)),
            ft.IconButton(
                icon=ft.Icons.TOGGLE_OFF if salon.get("estado") == "Activo" else ft.Icons.TOGGLE_ON,
                tooltip="Desactivar salón" if salon.get("estado") == "Activo" else "Activar salón",
                on_click=lambda e: on_change_state(
                    salon,
                    "Inactivo" if salon.get("estado") == "Activo" else "Activo",
                ),
            ),
        ]
    return ft.Container(
        content=ft.Column(
            [
                ft.Row(
                    [
                        ft.Text(str(salon.get("nombre") or "Salón sin nombre"), size=16, weight=ft.FontWeight.BOLD, expand=True),
                        _chip(str(salon.get("estado") or "Sin estado")),
                    ]
                ),
                ft.Text(str(salon.get("ubicacion") or "Sin ubicación interna"), size=13),
                ft.Text(
                    f"Máximo: {_numero(salon.get('cant_max_mesas'))} mesas · "
                    f"{_numero(salon.get('cant_max_invitados'))} invitados",
                    size=12,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                ),
                ft.Row(acciones, alignment=ft.MainAxisAlignment.END) if acciones else ft.Container(),
            ],
            spacing=7,
        ),
        padding=12,
        border_radius=8,
        bgcolor=ft.Colors.SURFACE,
        border=ft.Border.all(width=1, color=ft.Colors.OUTLINE_VARIANT),
    )


def _formulario_lugar(
    form: dict[str, Any],
    paises: list[dict[str, Any]],
    saving: bool,
    message: str,
    on_save: Any,
    on_cancel: Any,
) -> ft.Control:
    item = form.get("item") or {}
    nombre = ft.TextField(label="Nombre *", value=str(item.get("nombre") or ""), max_length=50)
    tipo = ft.Dropdown(
        label="Tipo *",
        value=str(item.get("tipo") or "Otro"),
        options=[ft.DropdownOption(key=value, text=value) for value in ("Hotel", "Sala de eventos", "Otro")],
    )
    direccion = ft.TextField(label="Dirección", value=str(item.get("direccion") or ""), max_length=150)
    ciudad = ft.TextField(label="Ciudad", value=str(item.get("ciudad") or ""), max_length=50)
    pais = ft.Dropdown(
        label="País",
        value=str(item.get("pais_id") or "") or None,
        options=[
            ft.DropdownOption(key=str(value.get("pais_id")), text=str(value.get("nombre")))
            for value in paises
        ],
    )
    return ft.Container(
        content=ft.Column(
            [
                ft.Text("Editar lugar" if form.get("modo") == "editar_lugar" else "Agregar lugar", size=20, weight=ft.FontWeight.BOLD),
                ft.ResponsiveRow(
                    [
                        ft.Container(nombre, col={"xs": 12, "md": 7}),
                        ft.Container(tipo, col={"xs": 12, "md": 5}),
                        ft.Container(direccion, col={"xs": 12}),
                        ft.Container(ciudad, col={"xs": 12, "md": 6}),
                        ft.Container(pais, col={"xs": 12, "md": 6}),
                    ],
                    spacing=10,
                    run_spacing=10,
                ),
                ft.Text(message, color=ft.Colors.ERROR) if message else ft.Container(),
                ft.Row(
                    [
                        ft.Button(
                            content="Guardar",
                            icon=ft.Icons.SAVE,
                            disabled=saving,
                            on_click=lambda e: on_save(
                                {
                                    "nombre": nombre.value,
                                    "tipo": tipo.value,
                                    "direccion": direccion.value,
                                    "ciudad": ciudad.value,
                                    "pais_id": pais.value,
                                }
                            ),
                        ),
                        ft.OutlinedButton(content="Cancelar", disabled=saving, on_click=lambda e: on_cancel()),
                        ft.ProgressRing(width=22, height=22, visible=saving),
                    ],
                    wrap=True,
                ),
            ],
            spacing=12,
        ),
        padding=16,
        border_radius=10,
        bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
    )


def _formulario_salon(
    form: dict[str, Any],
    saving: bool,
    message: str,
    on_save: Any,
    on_cancel: Any,
) -> ft.Control:
    item = form.get("item") or {}
    nombre = ft.TextField(label="Nombre *", value=str(item.get("nombre") or ""), max_length=60)
    ubicacion = ft.TextField(label="Ubicación dentro del lugar", value=str(item.get("ubicacion") or ""), max_length=100)
    mesas = ft.TextField(label="Cantidad máxima de mesas", value=_numero(item.get("cant_max_mesas")).replace("-", ""), keyboard_type=ft.KeyboardType.NUMBER)
    invitados = ft.TextField(label="Cantidad máxima de invitados", value=_numero(item.get("cant_max_invitados")).replace("-", ""), keyboard_type=ft.KeyboardType.NUMBER)
    return ft.Container(
        content=ft.Column(
            [
                ft.Text("Editar salón" if form.get("modo") == "editar_salon" else "Agregar salón", size=20, weight=ft.FontWeight.BOLD),
                ft.ResponsiveRow(
                    [
                        ft.Container(nombre, col={"xs": 12, "md": 6}),
                        ft.Container(ubicacion, col={"xs": 12, "md": 6}),
                        ft.Container(mesas, col={"xs": 12, "md": 6}),
                        ft.Container(invitados, col={"xs": 12, "md": 6}),
                    ],
                    spacing=10,
                    run_spacing=10,
                ),
                ft.Text(message, color=ft.Colors.ERROR) if message else ft.Container(),
                ft.Row(
                    [
                        ft.Button(
                            content="Guardar",
                            icon=ft.Icons.SAVE,
                            disabled=saving,
                            on_click=lambda e: on_save(
                                {
                                    "nombre": nombre.value,
                                    "ubicacion": ubicacion.value,
                                    "cant_max_mesas": mesas.value,
                                    "cant_max_invitados": invitados.value,
                                }
                            ),
                        ),
                        ft.OutlinedButton(content="Cancelar", disabled=saving, on_click=lambda e: on_cancel()),
                        ft.ProgressRing(width=22, height=22, visible=saving),
                    ],
                    wrap=True,
                ),
            ],
            spacing=12,
        ),
        padding=16,
        border_radius=10,
        bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
    )


def lugares_view(
    contexto: dict[str, Any],
    estado: str,
    mensaje: str,
    lugares: list[dict[str, Any]],
    lugar_seleccionado: dict[str, Any] | None,
    salones: list[dict[str, Any]],
    paises: list[dict[str, Any]],
    form: dict[str, Any] | None,
    form_message: str,
    saving: bool,
    can_manage: bool,
    on_retry: Any,
    on_select_place: Any,
    on_new_place: Any,
    on_edit_place: Any,
    on_change_place_state: Any,
    on_new_room: Any,
    on_edit_room: Any,
    on_change_room_state: Any,
    on_save_form: Any,
    on_cancel_form: Any,
) -> ft.Control:
    cuenta = contexto.get("cuenta_actual") or {}
    if not cuenta:
        return _state("Sin cuenta seleccionada", "Selecciona una cuenta antes de administrar lugares.", ft.Icons.ACCOUNT_BALANCE)
    if not can_manage:
        return _state("Acceso denegado", "Tu rol no permite acceder a la administración de lugares y salones.", ft.Icons.LOCK_OUTLINE)
    if estado == "loading":
        return _state("Cargando", "Consultando lugares y salones de la cuenta activa.", ft.Icons.HOURGLASS_TOP)
    if estado == "error":
        return _state("No fue posible cargar el módulo", mensaje, ft.Icons.ERROR_OUTLINE, on_retry)

    paises_por_id = {str(item.get("pais_id")): str(item.get("nombre")) for item in paises}
    salones_por_lugar: dict[int, int] = {}
    for salon in salones:
        lugar_id = int(salon.get("lugar_id") or 0)
        salones_por_lugar[lugar_id] = salones_por_lugar.get(lugar_id, 0) + 1
    lugares_visibles = [
        {**lugar, "pais_nombre": paises_por_id.get(str(lugar.get("pais_id")), "")}
        for lugar in lugares
    ]
    selected_id = (lugar_seleccionado or {}).get("lugar_id")
    controls: list[ft.Control] = [
        ft.Row(
            [
                ft.Text("Lugares y salones", size=26, weight=ft.FontWeight.BOLD, expand=True),
                ft.Button(content="Agregar lugar", icon=ft.Icons.ADD_LOCATION, on_click=lambda e: on_new_place()),
            ],
            vertical_alignment=ft.CrossAxisAlignment.START,
        )
    ]
    if mensaje:
        controls.append(ft.Text(mensaje, color=ft.Colors.ON_SURFACE_VARIANT))
    if not lugares_visibles:
        controls.append(_state("Sin lugares", "Esta cuenta todavía no tiene lugares registrados.", ft.Icons.LOCATION_OFF))
    else:
        left = ft.Column(
            [
                _lugar_card(
                    lugar,
                    lugar.get("lugar_id") == selected_id,
                    salones_por_lugar.get(int(lugar.get("lugar_id") or 0), 0),
                    can_manage,
                    on_select_place,
                    on_edit_place,
                    on_change_place_state,
                )
                for lugar in lugares_visibles
            ],
            spacing=10,
        )
        if lugar_seleccionado:
            salon_controls: list[ft.Control] = [
                ft.Row(
                    [
                        ft.Text(
                            f"Salones de {lugar_seleccionado.get('nombre')}",
                            size=20,
                            weight=ft.FontWeight.BOLD,
                            expand=True,
                        ),
                        ft.Button(content="Agregar salón", icon=ft.Icons.ADD, on_click=lambda e: on_new_room()),
                    ]
                )
            ]
            salon_controls.extend(
                [_salon_card(salon, can_manage, on_edit_room, on_change_room_state) for salon in salones]
                or [ft.Text("Este lugar todavía no tiene salones.", color=ft.Colors.ON_SURFACE_VARIANT)]
            )
            right: ft.Control = ft.Column(salon_controls, spacing=10)
        else:
            right = _state("Selecciona un lugar", "Elige un lugar para consultar sus salones.", ft.Icons.MEETING_ROOM)
        controls.append(
            ft.ResponsiveRow(
                [
                    ft.Container(left, col={"xs": 12, "lg": 6}),
                    ft.Container(right, col={"xs": 12, "lg": 6}),
                ],
                spacing=14,
                run_spacing=14,
            )
        )
    return ft.ListView(controls=controls, spacing=16, expand=True)


def lugar_form_view(
    form: dict[str, Any], paises: list[dict[str, Any]], saving: bool,
    message: str, on_save: Any, on_back: Any,
) -> ft.Control:
    modo = str(form.get("modo") or "")
    title = {
        "crear_lugar": "Agregar lugar", "editar_lugar": "Editar lugar",
        "crear_salon": "Agregar salón", "editar_salon": "Editar salón",
    }.get(modo, "Formulario")
    panel = (
        _formulario_lugar(form, paises, saving, message, on_save, on_back)
        if modo in {"crear_lugar", "editar_lugar"}
        else _formulario_salon(form, saving, message, on_save, on_back)
    )
    return ft.ListView(
        controls=[
            ft.Row([
                ft.IconButton(icon=ft.Icons.ARROW_BACK, tooltip="Regresar a lugares y salones", on_click=lambda e: on_back()),
                ft.Text(title, size=26, weight=ft.FontWeight.BOLD),
            ]),
            panel,
        ], spacing=16, expand=True,
    )
