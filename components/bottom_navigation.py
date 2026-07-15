from __future__ import annotations

from collections.abc import Callable

import flet as ft


def _icon(name: str):
    return getattr(ft.Icons, name, None)


def _nav_button(
    label: str,
    icon_name: str,
    selected: bool,
    disabled: bool,
    on_click: Callable,
) -> ft.Control:
    button_cls = ft.FilledTonalButton if selected else ft.TextButton
    return ft.Container(
        content=button_cls(
            content=label,
            icon=_icon(icon_name),
            disabled=disabled,
            on_click=on_click,
            height=48,
        ),
        expand=True,
    )


def bottom_navigation(
    selected: str,
    can_use_app: bool,
    can_register_arrivals: bool,
    on_select: Callable[[str], None],
    on_logout: Callable[[], None],
) -> ft.Container:
    return ft.Container(
        content=ft.Row(
            [
                _nav_button(
                    "Dashboard",
                    "DASHBOARD",
                    selected == "dashboard",
                    not can_use_app,
                    lambda e: on_select("dashboard"),
                ),
                _nav_button(
                    "Invitados",
                    "PEOPLE",
                    selected == "guests",
                    not can_use_app,
                    lambda e: on_select("guests"),
                ),
                _nav_button(
                    "Registrar llegadas",
                    "HOW_TO_REG",
                    selected == "arrivals",
                    (not can_use_app) or (not can_register_arrivals),
                    lambda e: on_select("arrivals"),
                ),
                _nav_button(
                    "Preferencias",
                    "SETTINGS",
                    selected == "preferences",
                    not can_use_app,
                    lambda e: on_select("preferences"),
                ),
                _nav_button(
                    "Salir",
                    "LOGOUT",
                    selected == "logout",
                    False,
                    lambda e: on_logout(),
                ),
            ],
            spacing=8,
        ),
        padding=ft.Padding.symmetric(
            horizontal=12,
            vertical=10,
        ),
        border=ft.Border.only(
            top=ft.BorderSide(width=1, color=ft.Colors.OUTLINE_VARIANT),
        ),
        bgcolor=ft.Colors.SURFACE,
    )
