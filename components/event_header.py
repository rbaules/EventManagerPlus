from __future__ import annotations

from collections.abc import Callable
from typing import Any

import flet as ft

from config import is_checkin_mode
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
        width=44,
        height=44,
        border_radius=22,
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

    return ft.Container(
        content=ft.ResponsiveRow(
            [
                ft.Container(
                    content=ft.Image(
                        src="brand/EventPlus_logo_v2.0_horizontal.png",
                        width=180,
                        fit=ft.BoxFit.CONTAIN,
                    ),
                    col={"xs": 12, "sm": 4, "md": 3},
                    padding=ft.Padding.only(bottom=8),
                ),
                ft.Container(
                    content=ft.Column(details, spacing=6, tight=True),
                    col={"xs": 12, "sm": 8, "md": 5},
                ),
                ft.Container(
                    content=ft.Row(
                        [
                            ft.Column(
                                [
                                    ft.Text(
                                        _get(contexto, "usr_nombre_usuario", "Usuario"),
                                        size=14,
                                        weight=ft.FontWeight.W_600,
                                        overflow=ft.TextOverflow.ELLIPSIS,
                                    ),
                                    ft.Text(
                                        _get(contexto, "rol_global_calculado", "Sin rol"),
                                        size=13,
                                        color=ft.Colors.ON_SURFACE_VARIANT,
                                    ),
                                ],
                                horizontal_alignment=ft.CrossAxisAlignment.END,
                                spacing=4,
                                tight=True,
                                expand=True,
                            ),
                            _avatar_menu(
                                contexto,
                                on_preferences,
                                on_logout,
                                on_change_context,
                                on_manage_locations,
                                on_manage_events,
                                on_select_event,
                                on_excel_import,
                                on_manage_users,
                            ),
                        ],
                        alignment=ft.MainAxisAlignment.END,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=10,
                    ),
                    col={"xs": 12, "md": 4},
                    alignment=ft.Alignment.CENTER_RIGHT,
                ),
            ],
            spacing=12,
            run_spacing=8,
        ),
        padding=16,
        border=ft.Border.only(
            bottom=ft.BorderSide(width=1, color=ft.Colors.OUTLINE_VARIANT),
        ),
        bgcolor=ft.Colors.SURFACE,
    )
