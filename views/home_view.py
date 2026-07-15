from __future__ import annotations

from typing import Any

import flet as ft

from components.app_shell import app_shell
from services.auth_service import sign_out_local_session
from views.dashboard_view import dashboard_view


def _placeholder(title: str, message: str) -> ft.Control:
    return ft.Container(
        content=ft.Column(
            [
                ft.Text(title, size=24, weight=ft.FontWeight.BOLD),
                ft.Text(message, size=15, color=ft.Colors.ON_SURFACE_VARIANT),
            ],
            spacing=8,
        ),
        padding=16,
        border_radius=8,
        bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
        border=ft.Border.all(
            width=1,
            color=ft.Colors.OUTLINE_VARIANT,
        ),
    )


def build_home_view(
    page: ft.Page,
    contexto_usuario: dict[str, Any],
    supabase: Any = None,
) -> ft.Control:
    state = {"selected": "dashboard"}

    def build_content() -> ft.Control:
        if state["selected"] == "arrivals":
            if contexto_usuario.get("puede_registrar_llegadas"):
                return _placeholder(
                    "Registro de llegadas",
                    "Registro de llegadas se implementara en el proximo incremento.",
                )
            return _placeholder(
                "Acceso no permitido",
                "El evento actual no permite registrar llegadas con tu rol o fase actual.",
            )

        if state["selected"] == "preferences":
            return _placeholder(
                "Preferencias",
                "Preferencias se implementara en un proximo incremento.",
            )

        return dashboard_view(contexto_usuario)

    def build_shell() -> ft.Control:
        content = build_content()
        if content is None:
            raise RuntimeError("La vista solicitada devolvio None; se esperaba un control Flet.")

        return app_shell(
            contexto=contexto_usuario,
            selected=state["selected"],
            content=content,
            on_select=select_tab,
            on_logout=logout,
        )

    def render() -> None:
        home_control = build_shell()
        if home_control is None:
            raise RuntimeError("build_home_view devolvio None; se esperaba un control Flet.")

        page.clean()
        page.add(home_control)
        page.update()

    def select_tab(tab: str) -> None:
        if not (contexto_usuario.get("cuenta_actual") and contexto_usuario.get("evento_actual")):
            state["selected"] = "dashboard"
            render()
            return

        if tab == "arrivals" and not contexto_usuario.get("puede_registrar_llegadas"):
            state["selected"] = "arrivals"
        else:
            state["selected"] = tab
        render()

    def logout() -> None:
        try:
            sign_out_local_session()
        except Exception:
            pass
        try:
            page.session.store.remove("usuario_contexto")
            page.session.store.remove("diagnostico_login")
        except Exception:
            pass
        page.clean()
        from views.login_view import build_login_view

        build_login_view(page)
        page.update()

    return build_shell()
