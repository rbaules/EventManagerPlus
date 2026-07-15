from __future__ import annotations

from collections.abc import Callable
from typing import Any

import flet as ft

from components.bottom_navigation import bottom_navigation
from components.event_header import event_header


def app_shell(
    contexto: dict[str, Any],
    selected: str,
    content: ft.Control,
    on_select: Callable[[str], None],
    on_logout: Callable[[], None],
) -> ft.Control:
    can_use_app = bool(contexto.get("cuenta_actual") and contexto.get("evento_actual"))
    can_register_arrivals = bool(contexto.get("puede_registrar_llegadas"))

    return ft.SafeArea(
        content=ft.Column(
            [
                event_header(contexto),
                ft.Container(
                    content=content,
                    expand=True,
                    padding=16,
                ),
                bottom_navigation(
                    selected=selected,
                    can_use_app=can_use_app,
                    can_register_arrivals=can_register_arrivals,
                    on_select=on_select,
                    on_logout=on_logout,
                ),
            ],
            expand=True,
            spacing=0,
        ),
        expand=True,
    )
