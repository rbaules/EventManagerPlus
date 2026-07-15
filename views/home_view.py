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
from services.invitado_service import (
    INVITADOS_PAGE_SIZE,
    actualizar_invitado_planificado,
    crear_invitado_planificado,
    listar_invitaciones_evento,
    listar_invitados,
    obtener_invitado_por_id,
    puede_administrar_invitados_planificados,
)
from views.dashboard_view import dashboard_view
from views.invitados_view import invitados_view


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
        "invitados_estado": "idle",
        "invitados": [],
        "invitados_mensaje": "",
        "invitados_busqueda": "",
        "invitados_filtro": "todos",
        "invitados_offset": 0,
        "invitados_has_more": False,
        "invitados_loading": False,
        "invitado_detalle": None,
        "invitados_request_id": 0,
        "invitados_event_key": None,
        "invitaciones": [],
        "invitado_form": None,
        "invitado_form_message": "",
        "invitado_saving": False,
    }

    def build_content() -> ft.Control:
        if state["selected"] == "guests":
            return invitados_view(
                contexto=contexto_usuario,
                estado=state["invitados_estado"],
                invitados=state["invitados"],
                mensaje=state["invitados_mensaje"],
                busqueda=state["invitados_busqueda"],
                filtro=state["invitados_filtro"],
                has_more=state["invitados_has_more"],
                is_loading=state["invitados_loading"],
                invitado_detalle=state["invitado_detalle"],
                can_manage_planned=puede_administrar_invitados_planificados(contexto_usuario),
                invitaciones=state["invitaciones"],
                form_state=state["invitado_form"],
                form_message=state["invitado_form_message"],
                is_saving=state["invitado_saving"],
                on_search=buscar_invitados,
                on_clear=limpiar_busqueda_invitados,
                on_filter=filtrar_invitados,
                on_retry=reintentar_invitados,
                on_load_more=cargar_mas_invitados,
                on_detail=seleccionar_invitado_detalle,
                on_close_detail=cerrar_detalle_invitado,
                on_go_dashboard=go_dashboard,
                on_new_guest=abrir_form_crear_invitado,
                on_edit_guest=abrir_form_editar_invitado,
                on_save_guest=guardar_form_invitado,
                on_cancel_form=cancelar_form_invitado,
            )

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

    def reset_invitados() -> None:
        state["invitados_estado"] = "idle"
        state["invitados"] = []
        state["invitados_mensaje"] = ""
        state["invitados_busqueda"] = ""
        state["invitados_filtro"] = "todos"
        state["invitados_offset"] = 0
        state["invitados_has_more"] = False
        state["invitados_loading"] = False
        state["invitado_detalle"] = None
        state["invitaciones"] = []
        state["invitado_form"] = None
        state["invitado_form_message"] = ""
        state["invitado_saving"] = False
        state["invitados_request_id"] += 1
        state["invitados_event_key"] = None

    def evento_activo_key() -> tuple[int, int] | None:
        from services.evento_context_service import evento_key

        return evento_key(contexto_usuario.get("evento_actual"))

    def cargar_invitados(reset: bool = True) -> None:
        active_key = evento_activo_key()
        if active_key is None:
            print("[INVITADOS][WARNING] Intento de abrir invitados sin evento activo.")
            reset_invitados()
            state["invitados_estado"] = "event_required"
            state["invitados_mensaje"] = "Selecciona un evento antes de consultar los invitados."
            render()
            return

        if state["invitados_loading"]:
            return

        if reset:
            state["invitados"] = []
            state["invitados_offset"] = 0
            state["invitado_detalle"] = None
        state["invitados_loading"] = True
        state["invitados_estado"] = "loading"
        state["invitados_mensaje"] = "Cargando invitados..."
        state["invitados_request_id"] += 1
        request_id = state["invitados_request_id"]
        state["invitados_event_key"] = active_key
        offset = int(state["invitados_offset"])
        busqueda = str(state["invitados_busqueda"])
        filtro = str(state["invitados_filtro"])
        print("[INVITADOS][INFO] Entrada al modulo Invitados.")
        print("[INVITADOS][INFO] Evento activo utilizado:", active_key[0], active_key[1])
        cargar_invitaciones()
        render()

        def worker() -> None:
            try:
                resultado = listar_invitados(
                    contexto_usuario.get("evento_actual"),
                    busqueda=busqueda,
                    filtro=filtro,
                    limit=INVITADOS_PAGE_SIZE,
                    offset=offset,
                    supabase=supabase,
                )
                if request_id != state["invitados_request_id"] or active_key != evento_activo_key():
                    print("[INVITADOS][WARNING] Resultado antiguo ignorado.")
                    return
                state["invitados_mensaje"] = resultado.mensaje
                state["invitados_estado"] = resultado.estado if resultado.ok else "error"
                if resultado.ok:
                    if reset:
                        state["invitados"] = resultado.invitados
                    else:
                        existentes = {item.get("invitado_uuid") for item in state["invitados"]}
                        state["invitados"].extend(
                            item
                            for item in resultado.invitados
                            if item.get("invitado_uuid") not in existentes
                        )
                    state["invitados_has_more"] = resultado.has_more
                    state["invitados_offset"] = len(state["invitados"])
                else:
                    state["invitados_has_more"] = False
                if resultado.estado == "empty":
                    print("[INVITADOS][INFO] Evento sin invitados.")
                if resultado.estado == "no_results":
                    print("[INVITADOS][INFO] Busqueda sin coincidencias.")
            finally:
                state["invitados_loading"] = False
                render()

        page.run_thread(worker)

    def cargar_invitaciones() -> None:
        resultado = listar_invitaciones_evento(contexto_usuario.get("evento_actual"), supabase=supabase)
        if resultado.ok:
            state["invitaciones"] = resultado.invitaciones
        else:
            state["invitaciones"] = []
            print("[INVITADOS][WARNING] No se pudieron cargar invitaciones:", resultado.estado)

    def buscar_invitados(texto: str) -> None:
        state["invitados_busqueda"] = (texto or "").strip()
        print("[INVITADOS][INFO] Busqueda aplicada:", "si" if state["invitados_busqueda"] else "no")
        cargar_invitados(reset=True)

    def limpiar_busqueda_invitados() -> None:
        state["invitados_busqueda"] = ""
        state["invitados_filtro"] = "todos"
        print("[INVITADOS][INFO] Busqueda y filtros limpiados.")
        cargar_invitados(reset=True)

    def filtrar_invitados(filtro: str) -> None:
        state["invitados_filtro"] = filtro or "todos"
        print("[INVITADOS][INFO] Filtro aplicado:", state["invitados_filtro"])
        cargar_invitados(reset=True)

    def reintentar_invitados() -> None:
        print("[INVITADOS][INFO] Reintento de consulta.")
        cargar_invitados(reset=True)

    def cargar_mas_invitados() -> None:
        print("[INVITADOS][INFO] Cargando lote adicional.")
        cargar_invitados(reset=False)

    def seleccionar_invitado_detalle(invitado: dict[str, Any]) -> None:
        active_key = evento_activo_key()
        if active_key is None:
            state["invitado_detalle"] = None
            state["invitados_mensaje"] = "Selecciona un evento antes de consultar los invitados."
            render()
            return
        invitado_uuid = str(invitado.get("invitado_uuid", ""))
        print("[INVITADOS][INFO] Invitado seleccionado para detalle.")
        resultado = obtener_invitado_por_id(
            contexto_usuario.get("evento_actual"),
            invitado_uuid,
            supabase=supabase,
        )
        if resultado.ok:
            state["invitado_detalle"] = resultado.invitado
        else:
            state["invitado_detalle"] = None
            state["invitados_mensaje"] = resultado.mensaje
            state["invitados_estado"] = "error" if resultado.estado == "connection_error" else state["invitados_estado"]
        render()

    def abrir_form_crear_invitado() -> None:
        print("[INVITADOS][INFO] Intento de abrir formulario: operacion=crear")
        if not puede_administrar_invitados_planificados(contexto_usuario):
            state["invitado_form_message"] = "No tienes permisos para modificar invitados planificados."
            render()
            return
        cargar_invitaciones()
        if not state["invitaciones"]:
            state["invitado_form_message"] = "No hay invitaciones activas para agregar invitados."
            render()
            return
        state["invitado_form"] = {
            "modo": "crear",
            "original": None,
            "event_key": evento_activo_key(),
            "datos": {
                "invitacion_id": "",
                "nombre_completo": "",
                "email": "",
                "telefono": "",
                "mesa_id": "",
                "puesto_id": "",
                "es_invitado_principal": False,
            },
        }
        state["invitado_form_message"] = ""
        state["invitado_detalle"] = None
        render()

    def abrir_form_editar_invitado(invitado: dict[str, Any]) -> None:
        print("[INVITADOS][INFO] Intento de abrir formulario: operacion=editar")
        if not puede_administrar_invitados_planificados(contexto_usuario):
            state["invitado_form_message"] = "No tienes permisos para modificar invitados planificados."
            render()
            return
        resultado = obtener_invitado_por_id(
            contexto_usuario.get("evento_actual"),
            str(invitado.get("invitado_uuid", "")),
            supabase=supabase,
        )
        if not resultado.ok or not resultado.invitado:
            state["invitado_form_message"] = resultado.mensaje
            render()
            return
        invitado_actual = resultado.invitado
        if invitado_actual.get("es_invitado_imprevisto"):
            state["invitado_form_message"] = "Solo se pueden editar invitados planificados en esta tarea."
            render()
            return
        state["invitado_form"] = {
            "modo": "editar",
            "original": invitado_actual,
            "event_key": evento_activo_key(),
            "datos": {
                "invitacion_id": invitado_actual.get("invitacion_id"),
                "nombre_completo": invitado_actual.get("nombre_completo"),
                "email": invitado_actual.get("email"),
                "telefono": invitado_actual.get("telefono"),
                "mesa_id": invitado_actual.get("mesa_id"),
                "puesto_id": invitado_actual.get("puesto_id"),
                "es_invitado_principal": invitado_actual.get("es_invitado_principal"),
            },
        }
        state["invitado_form_message"] = ""
        state["invitado_detalle"] = None
        render()

    def guardar_form_invitado(payload: dict[str, Any]) -> None:
        form = state.get("invitado_form")
        if not form:
            return
        if form.get("event_key") != evento_activo_key():
            print("[INVITADOS][WARNING] Cambio de evento mientras el formulario estaba abierto.")
            state["invitado_form_message"] = "El evento activo cambio. Vuelve a abrir el formulario."
            render()
            return
        if state["invitado_saving"]:
            return
        state["invitado_saving"] = True
        state["invitado_form_message"] = ""
        render()

        def worker() -> None:
            try:
                if form.get("modo") == "crear":
                    resultado = crear_invitado_planificado(contexto_usuario, payload, supabase=supabase)
                else:
                    resultado = actualizar_invitado_planificado(
                        contexto_usuario,
                        form.get("original"),
                        payload,
                        supabase=supabase,
                    )
                if resultado.ok:
                    state["invitado_form"] = None
                    state["invitado_form_message"] = resultado.mensaje
                    state["invitado_detalle"] = None
                    print("[INVITADOS][INFO]", resultado.mensaje)
                    cargar_invitados(reset=True)
                    return
                state["invitado_form_message"] = resultado.mensaje
                print("[INVITADOS][WARNING] Guardado rechazado:", resultado.estado)
            finally:
                state["invitado_saving"] = False
                render()

        page.run_thread(worker)

    def cancelar_form_invitado() -> None:
        print("[INVITADOS][INFO] Formulario cancelado.")
        state["invitado_form"] = None
        state["invitado_form_message"] = ""
        render()

    def cerrar_detalle_invitado() -> None:
        state["invitado_detalle"] = None
        state["invitado_form"] = None
        render()

    def go_dashboard() -> None:
        state["selected"] = "dashboard"
        render()

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
        reset_invitados()
        print(
            "[EVENTOS][INFO] Cambio de evento activo:",
            evento_activo.get("cuenta_id"),
            evento_activo.get("evento_id"),
        )
        render()

    def select_tab(tab: str) -> None:
        if not (contexto_usuario.get("cuenta_actual") and contexto_usuario.get("evento_actual")):
            if tab == "guests":
                state["selected"] = "guests"
                cargar_invitados(reset=True)
                return
            state["selected"] = "dashboard"
            render()
            return

        if tab == "guests":
            state["selected"] = "guests"
            cargar_invitados(reset=True)
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
