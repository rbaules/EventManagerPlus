from __future__ import annotations

from collections.abc import Callable

import flet as ft

from config import is_checkin_mode


def _icon(name: str):
    return getattr(ft.Icons, name, None)


_NAV_ITEMS = (
    ("dashboard", "Dashboard", "DASHBOARD", False),
    ("guests", "Invitados", "PEOPLE", False),
    ("arrivals", "Registrar llegadas", "HOW_TO_REG", True),
)

_CHECKIN_NAV_ITEMS = (
    ("guests", "Invitados", "PEOPLE", False),
    ("arrivals", "Registrar llegadas", "HOW_TO_REG", True),
)


def bottom_navigation(
    selected: str,
    can_use_app: bool,
    can_register_arrivals: bool,
    on_select: Callable[[str], None],
) -> ft.NavigationBar:
    print("[NAVEGACION][INFO] Aplicando estilo visual a la barra.")
    base_items = _CHECKIN_NAV_ITEMS if is_checkin_mode() else _NAV_ITEMS
    nav_items = tuple(
        item for item in base_items
        if item[0] != "arrivals" or can_register_arrivals
    )
    if is_checkin_mode():
        print("[CHECKIN][INFO] Navegacion disponible: Invitados, Registrar llegadas")
    selected_keys = [item[0] for item in nav_items]
    selected_index = selected_keys.index(selected) if selected in selected_keys else 0

    def destination_disabled(key: str, requires_arrivals: bool) -> bool:
        if key == "dashboard":
            return False
        if requires_arrivals:
            return (not can_use_app) or (not can_register_arrivals)
        return not can_use_app

    def handle_change(e: ft.ControlEvent) -> None:
        index = int(getattr(e.control, "selected_index", 0) or 0)
        if index < 0 or index >= len(nav_items):
            return
        key, _, _, requires_arrivals = nav_items[index]
        if destination_disabled(key, requires_arrivals):
            e.control.selected_index = selected_index
            e.control.update()
            return
        on_select(key)

    print("[NAVEGACION][INFO] Fondo, elevacion e indicador configurados.")
    return ft.NavigationBar(
        selected_index=selected_index,
        destinations=[
            ft.NavigationBarDestination(
                icon=_icon(icon_name),
                selected_icon=_icon(icon_name),
                label=label,
                disabled=destination_disabled(key, requires_arrivals),
            )
            for key, label, icon_name, requires_arrivals in nav_items
        ],
        label_behavior=ft.NavigationBarLabelBehavior.ALWAYS_SHOW,
        bgcolor=ft.Colors.SURFACE_CONTAINER,
        elevation=8,
        shadow_color=ft.Colors.OUTLINE_VARIANT,
        indicator_color=ft.Colors.PRIMARY_CONTAINER,
        border=ft.Border.only(
            top=ft.BorderSide(width=1, color=ft.Colors.OUTLINE_VARIANT),
        ),
        on_change=handle_change,
        data={"responsive_component": "bottom_navigation"},
    )
