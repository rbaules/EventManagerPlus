from __future__ import annotations

from collections.abc import Callable
from typing import Any

import flet as ft

from views.kiosk_view import build_kiosk_view, is_kiosk_route


def authenticated_route_target(route: str | None) -> str:
    """La única decisión de raíz para una sesión ya autenticada."""
    return "kiosk" if is_kiosk_route(route) else "home"


class AuthenticatedViewRouter:
    """Monta Home o Kiosco conservando la intención de ruta actual."""

    def __init__(
        self,
        *,
        page: ft.Page,
        contexto_usuario: dict[str, Any],
        supabase: object,
        session_controller: object,
        home_builder: Callable[..., ft.Control] | None = None,
        kiosk_builder: Callable[..., ft.Control] | None = None,
    ) -> None:
        self.page = page
        self.contexto_usuario = contexto_usuario
        self.supabase = supabase
        self.session_controller = session_controller
        self._home_builder = home_builder
        self._kiosk_builder = kiosk_builder or build_kiosk_view
        self.active_control: ft.Control | None = None

    def mount_current_route(self) -> ft.Control:
        target = authenticated_route_target(getattr(self.page, "route", None))
        if target == "kiosk":
            control = self._kiosk_builder(
                page=self.page,
                contexto_usuario=self.contexto_usuario,
                supabase=self.supabase,
                on_authenticated_route_change=self.mount_current_route,
            )
        else:
            home_builder = self._home_builder
            if home_builder is None:
                from views.home_view import build_home_view

                home_builder = build_home_view
            control = home_builder(
                page=self.page,
                contexto_usuario=self.contexto_usuario,
                supabase=self.supabase,
                session_controller=self.session_controller,
                on_authenticated_route_change=self.mount_current_route,
            )
        self.page.clean()
        self.page.add(control)
        self.page.update()
        self.active_control = control
        if target == "home" and isinstance(control.data, dict):
            start_eventos = control.data.get("start_eventos")
            if callable(start_eventos):
                start_eventos()
        return control
