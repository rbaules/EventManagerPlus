from __future__ import annotations

from collections.abc import Callable
from typing import Any

import flet as ft

from components.event_header import event_header


def app_shell(
    contexto: dict[str, Any],
    selected: str,
    content: ft.Control,
    on_select: Callable[[str], None],
    on_logout: Callable[[], None],
    on_change_context: Callable[[], None] | None = None,
    on_manage_locations: Callable[[], None] | None = None,
    on_manage_events: Callable[[], None] | None = None,
    on_select_event: Callable[[], None] | None = None,
    on_excel_import: Callable[[], None] | None = None,
    on_manage_users: Callable[[], None] | None = None,
) -> ft.Control:
    return ft.SafeArea(
        content=ft.Column(
            [
                event_header(
                    contexto,
                    on_preferences=lambda: on_select("preferences"),
                    on_logout=on_logout,
                    on_change_context=on_change_context,
                    on_manage_locations=on_manage_locations,
                    on_manage_events=on_manage_events,
                    on_select_event=on_select_event,
                    on_excel_import=on_excel_import,
                    on_manage_users=on_manage_users,
                ),
                ft.Container(
                    content=content,
                    expand=True,
                    padding=16,
                    clip_behavior=ft.ClipBehavior.HARD_EDGE,
                ),
            ],
            expand=True,
            spacing=0,
        ),
        expand=True,
    )
