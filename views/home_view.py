from __future__ import annotations

from typing import Any

import flet as ft

from components.app_shell import app_shell
from services.auth_service import sign_out_local_session
from services.evento_context_service import (
    guardar_contexto_sesion,
    guardar_eventos_disponibles,
    limpiar_contexto_sesion,
    limpiar_evento_activo,
    sincronizar_evento_activo,
    establecer_evento_activo,
)
from services.evento_service import obtener_eventos_disponibles
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
    state: dict[str, Any] = {
        "selected": "dashboard",
        "eventos_estado": "loading",
        "eventos": [],
        "eventos_mensaje": "Cargando eventos...",
        "eventos_loading": False,
        "eventos_consulta_iniciada": False,
    }

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

        return dashboard_view(
            contexto_usuario,
            eventos_estado=state["eventos_estado"],
            eventos=state["eventos"],
            eventos_mensaje=state["eventos_mensaje"],
            on_select_event=select_event,
            on_retry_events=cargar_eventos,
        )

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

    def cargar_eventos() -> None:
        if state["eventos_loading"]:
            return

        state["eventos_loading"] = True
        state["eventos_estado"] = "loading"
        state["eventos_mensaje"] = "Cargando eventos..."
        print("[EVENTOS][INFO] Inicio de carga de eventos.")
        render()

        def worker() -> None:
            try:
                resultado = obtener_eventos_disponibles(contexto_usuario, supabase=supabase)
                state["eventos"] = resultado.eventos
                state["eventos_mensaje"] = resultado.mensaje
                state["eventos_estado"] = resultado.estado if resultado.ok else "error"

                if resultado.ok:
                    if (
                        len(resultado.eventos) > 1
                        and not contexto_usuario.get("usr_evento_id_default")
                        and not contexto_usuario.get("evento_activo_seleccionado")
                    ):
                        limpiar_evento_activo(contexto_usuario)
                        evento_activo = None
                        print("[EVENTOS][INFO] Varios eventos disponibles; se requiere seleccion explicita.")
                    else:
                        evento_activo = sincronizar_evento_activo(contexto_usuario, resultado.eventos)
                    guardar_contexto_sesion(page.session.store, contexto_usuario)
                    guardar_eventos_disponibles(page.session.store, resultado.eventos)
                    if evento_activo:
                        print(
                            "[EVENTOS][INFO] Evento activo:",
                            evento_activo.get("cuenta_id"),
                            evento_activo.get("evento_id"),
                        )
                    elif not resultado.eventos:
                        print("[EVENTOS][INFO] Consulta de eventos vacia.")
                    else:
                        print("[EVENTOS][INFO] Esperando seleccion explicita de evento.")
                else:
                    print("[EVENTOS][ERROR]", resultado.estado, resultado.mensaje)
            finally:
                state["eventos_loading"] = False
                render()

        page.run_thread(worker)

    def select_event(evento: dict[str, Any]) -> None:
        evento_activo = establecer_evento_activo(contexto_usuario, evento)
        contexto_usuario["evento_activo_seleccionado"] = True
        guardar_contexto_sesion(page.session.store, contexto_usuario)
        print(
            "[EVENTOS][INFO] Cambio de evento activo:",
            evento_activo.get("cuenta_id"),
            evento_activo.get("evento_id"),
        )
        render()

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
            limpiar_contexto_sesion(page.session.store)
            print("[EVENTOS][INFO] Contexto de evento eliminado durante logout.")
        except Exception:
            pass
        page.clean()
        from views.login_view import build_login_view

        build_login_view(page)
        page.update()

    home_control = build_shell()
    home_control.data = {"start_eventos": cargar_eventos}
    return home_control
