from __future__ import annotations

from collections.abc import Callable
from typing import Any

import flet as ft

from config import is_checkin_mode
from components.responsive import LayoutMode
from services.evento_context_service import rol_visible_contextual
from services.authorization_service import puede_administrar_lugares, puede_ver_administracion_eventos, puede_ver_administracion_usuarios, puede_ver_importacion_excel


def _get(source: dict[str, Any] | None, key: str, default: str = "-") -> Any:
    if not source:
        return default
    value = source.get(key)
    return default if value in (None, "") else value


def calcular_iniciales_usuario(nombre: Any) -> str:
    texto = " ".join(str(nombre or "").strip().split())
    if not texto:
        return "US"
    partes = texto.split()
    if len(partes) == 1:
        candidato = partes[0][:2]
    else:
        candidato = f"{partes[0][:1]}{partes[-1][:1]}"
    iniciales = "".join(char for char in candidato.upper() if char.isalpha())
    return (iniciales + "US")[:2]


def _avatar_menu(
    contexto: dict[str, Any],
    on_preferences: Callable[[], None],
    on_logout: Callable[[], None],
    on_change_context: Callable[[], None] | None = None,
    on_manage_locations: Callable[[], None] | None = None,
    on_manage_events: Callable[[], None] | None = None,
    on_select_event: Callable[[], None] | None = None,
    on_excel_import: Callable[[], None] | None = None,
    on_manage_users: Callable[[], None] | None = None,
) -> ft.Control:
    nombre = _get(contexto, "usr_nombre_usuario", "Usuario")
    iniciales = calcular_iniciales_usuario(nombre)
    avatar = ft.Container(
        content=ft.Text(iniciales, size=14, weight=ft.FontWeight.BOLD, color=ft.Colors.ON_PRIMARY),
        width=48,
        height=48,
        border_radius=24,
        bgcolor=ft.Colors.PRIMARY,
        alignment=ft.Alignment.CENTER,
        tooltip="Menu de usuario",
    )
    if is_checkin_mode():
        items = [
            ft.PopupMenuItem(
                content="Cambiar cuenta/evento",
                icon=ft.Icons.EVENT_REPEAT,
                on_click=lambda e: on_change_context() if on_change_context else on_preferences(),
            ),
            ft.PopupMenuItem(
                content="Salir",
                icon=ft.Icons.LOGOUT,
                on_click=lambda e: on_logout(),
            ),
        ]
    else:
        items = []
        if on_select_event:
            items.append(
                ft.PopupMenuItem(
                    content="Seleccionar evento activo",
                    icon=ft.Icons.EVENT_REPEAT,
                    on_click=lambda e: on_select_event(),
                )
            )
        if on_manage_locations and puede_administrar_lugares(contexto):
            items.append(
                ft.PopupMenuItem(
                    content="Lugares y salones",
                    icon=ft.Icons.LOCATION_CITY,
                    on_click=lambda e: on_manage_locations(),
                )
            )
        if on_manage_events and puede_ver_administracion_eventos(contexto):
            items.append(
                ft.PopupMenuItem(
                    content="Administración de eventos",
                    icon=ft.Icons.EVENT_NOTE,
                    on_click=lambda e: on_manage_events(),
                )
            )
        if on_excel_import and puede_ver_importacion_excel(contexto):
            items.append(ft.PopupMenuItem(
                content="Importar invitados", icon=ft.Icons.UPLOAD_FILE,
                on_click=lambda e: on_excel_import(),
            ))
        if on_manage_users and puede_ver_administracion_usuarios(contexto):
            items.append(ft.PopupMenuItem(
                content="Administración de usuarios", icon=ft.Icons.MANAGE_ACCOUNTS,
                on_click=lambda e: on_manage_users(),
            ))
        items.extend([
            ft.PopupMenuItem(
                content="Preferencias",
                icon=ft.Icons.SETTINGS,
                on_click=lambda e: on_preferences(),
            ),
            ft.PopupMenuItem(
                content="Salir",
                icon=ft.Icons.LOGOUT,
                on_click=lambda e: on_logout(),
            ),
        ])

    return ft.PopupMenuButton(
        content=avatar,
        tooltip="Menu de usuario",
        items=items,
    )


def event_header(
    contexto: dict[str, Any],
    on_preferences: Callable[[], None],
    on_logout: Callable[[], None],
    on_change_context: Callable[[], None] | None = None,
    on_manage_locations: Callable[[], None] | None = None,
    on_manage_events: Callable[[], None] | None = None,
    on_select_event: Callable[[], None] | None = None,
    on_excel_import: Callable[[], None] | None = None,
    on_manage_users: Callable[[], None] | None = None,
    layout: LayoutMode = LayoutMode.DESKTOP_WIDE,
) -> ft.Container:
    cuenta = contexto.get("cuenta_actual") or {}
    evento = contexto.get("evento_actual") or {}
    fase = _get(evento, "fase_evento", "")
    evento_nombre = _get(evento, "nombre_evento", "Ningun evento seleccionado")

    details = [
        ft.Text(
            evento_nombre,
            size=18,
            weight=ft.FontWeight.BOLD,
            overflow=ft.TextOverflow.ELLIPSIS,
        ),
        ft.Text(
            f"Cuenta: {_get(cuenta, 'nombre_cuenta', 'Sin cuenta actual')}",
            size=13,
            color=ft.Colors.ON_SURFACE_VARIANT,
            overflow=ft.TextOverflow.ELLIPSIS,
        ),
    ]
    if fase:
        details.append(
            ft.Container(
                content=ft.Text(fase, size=12, weight=ft.FontWeight.W_600),
                padding=ft.Padding.symmetric(
                    horizontal=10,
                    vertical=4,
                ),
                border_radius=16,
                bgcolor=ft.Colors.SECONDARY_CONTAINER,
            )
        )

    logo = ft.Image(
        src="brand/EventPlus_logo_v2.0_horizontal.png",
        width=125 if layout == LayoutMode.PHONE else 150 if layout in {LayoutMode.PHONE_LARGE, LayoutMode.TABLET_PORTRAIT} else 180,
        fit=ft.BoxFit.CONTAIN,
    )
    user = ft.Row(
        [
            ft.Column(
                [
                    ft.Text(_get(contexto, "usr_nombre_usuario", "Usuario"), size=14, weight=ft.FontWeight.W_600, overflow=ft.TextOverflow.ELLIPSIS),
                    ft.Text(rol_visible_contextual(contexto), size=13, color=ft.Colors.ON_SURFACE_VARIANT),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.END,
                spacing=3,
                tight=True,
                expand=True,
            ),
            _avatar_menu(contexto, on_preferences, on_logout, on_change_context, on_manage_locations, on_manage_events, on_select_event, on_excel_import, on_manage_users),
        ],
        alignment=ft.MainAxisAlignment.END,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
        spacing=8,
    )
    if layout in {LayoutMode.TABLET_LANDSCAPE, LayoutMode.DESKTOP_WIDE}:
        content: ft.Control = ft.Row(
            [logo, ft.Column(details, spacing=4, tight=True, expand=True), ft.Container(user, width=240)],
            spacing=16,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )
    elif layout == LayoutMode.TABLET_PORTRAIT:
        context_line: list[ft.Control] = [ft.Column(details[:2], spacing=3, tight=True, expand=True)]
        if len(details) > 2:
            context_line.append(details[2])
        content = ft.Column(
            [
                ft.Row([logo, ft.Container(user, expand=True)], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                ft.Row(context_line, spacing=10, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            ],
            spacing=7,
            tight=True,
        )
    else:
        content = ft.Column(
            [ft.Row([logo, ft.Container(user, expand=True)], spacing=8), ft.Column(details, spacing=4, tight=True)],
            spacing=8,
            tight=True,
        )

    return ft.Container(
        content=content,
        padding=12 if layout in {LayoutMode.PHONE, LayoutMode.PHONE_LARGE, LayoutMode.TABLET_PORTRAIT} else 16,
        border=ft.Border.only(
            bottom=ft.BorderSide(width=1, color=ft.Colors.OUTLINE_VARIANT),
        ),
        bgcolor=ft.Colors.SURFACE,
        data={"responsive_component": "event_header", "layout_mode": layout.value},
    )
