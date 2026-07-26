from __future__ import annotations

from typing import Any

import flet as ft

from config import is_checkin_mode
from components.app_shell import app_shell
from components.bottom_navigation import bottom_navigation
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
    cargar_grupo_invitacion,
    confirmar_llegada,
    confirmar_llegadas_invitados,
    crear_invitado_planificado,
    crear_invitado_imprevisto,
    eliminar_invitado_imprevisto,
    listar_invitaciones_evento,
    listar_invitados,
    obtener_invitado_por_id,
    puede_administrar_invitados_planificados,
    puede_confirmar_llegada,
    puede_eliminar_imprevisto,
    puede_registrar_imprevisto,
    puede_reversar_llegada,
    reversar_llegada,
)
from views.arrivals_view import arrivals_view
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
    checkin_mode = is_checkin_mode()
    state: dict[str, Any] = {
        "selected": "arrivals" if checkin_mode else "dashboard",
        "eventos_estado": "loading",
        "eventos": [],
        "eventos_mensaje": "Cargando eventos...",
        "eventos_loading": False,
        "eventos_consulta_iniciada": False,
        "invitados_estado": "idle",
        "invitados": [],
        "invitados_mensaje": "",
        "invitados_tipo_busqueda": "invitado",
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
        "arrivals_estado": "idle",
        "arrivals_mensaje": "",
        "arrivals_busqueda": "",
        "arrivals_resultados": [],
        "arrivals_invitacion": None,
        "arrivals_integrantes": [],
        "arrivals_seleccionados": set(),
        "arrivals_loading": False,
        "arrivals_saving": False,
        "arrivals_request_id": 0,
        "arrivals_event_key": None,
    }

    def build_content() -> ft.Control:
        if state["selected"] == "guests":
            can_manage_planned = False if checkin_mode else puede_administrar_invitados_planificados(contexto_usuario)
            can_manage_unexpected = False if checkin_mode else puede_registrar_imprevisto(contexto_usuario)
            can_delete_unexpected = False if checkin_mode else puede_eliminar_imprevisto(contexto_usuario)
            return invitados_view(
                contexto=contexto_usuario,
                estado=state["invitados_estado"],
                invitados=state["invitados"],
                mensaje=state["invitados_mensaje"],
                tipo_busqueda=state["invitados_tipo_busqueda"],
                busqueda=state["invitados_busqueda"],
                filtro=state["invitados_filtro"],
                has_more=state["invitados_has_more"],
                is_loading=state["invitados_loading"],
                invitado_detalle=state["invitado_detalle"],
                can_manage_planned=can_manage_planned,
                can_confirm_arrival=puede_confirmar_llegada(contexto_usuario),
                can_reverse_arrival=puede_reversar_llegada(contexto_usuario),
                can_manage_unexpected=can_manage_unexpected,
                can_delete_unexpected=can_delete_unexpected,
                invitaciones=state["invitaciones"],
                form_state=state["invitado_form"],
                form_message=state["invitado_form_message"],
                is_saving=state["invitado_saving"],
                on_search=buscar_invitados,
                on_search_type_change=cambiar_tipo_busqueda_invitados,
                on_clear=limpiar_busqueda_invitados,
                on_filter=filtrar_invitados,
                on_retry=reintentar_invitados,
                on_load_more=cargar_mas_invitados,
                on_detail=seleccionar_invitado_detalle,
                on_close_detail=cerrar_detalle_invitado,
                on_go_dashboard=go_dashboard,
                on_new_guest=abrir_form_crear_invitado,
                on_new_unexpected_guest=abrir_form_crear_imprevisto,
                on_edit_guest=abrir_form_editar_invitado,
                on_save_guest=guardar_form_invitado,
                on_cancel_form=cancelar_form_invitado,
                on_confirm_arrival=confirmar_llegada_invitado,
                on_reverse_arrival=confirmar_reversion_llegada,
                on_delete_unexpected=confirmar_eliminacion_imprevisto,
            )

        if state["selected"] == "arrivals":
            if contexto_usuario.get("puede_registrar_llegadas"):
                return arrivals_view(
                    contexto=contexto_usuario,
                    estado=state["arrivals_estado"],
                    mensaje=state["arrivals_mensaje"],
                    busqueda=state["arrivals_busqueda"],
                    resultados=state["arrivals_resultados"],
                    invitacion=state["arrivals_invitacion"],
                    integrantes=state["arrivals_integrantes"],
                    seleccionados=state["arrivals_seleccionados"],
                    can_reverse_arrival=puede_reversar_llegada(contexto_usuario),
                    is_loading=state["arrivals_loading"],
                    is_saving=state["arrivals_saving"],
                    on_search=buscar_llegadas,
                    on_clear=limpiar_llegadas,
                    on_select_guest=seleccionar_invitado_llegadas,
                    on_toggle_guest=alternar_invitado_llegadas,
                    on_select_pending=seleccionar_pendientes_llegadas,
                    on_confirm_selected=confirmar_seleccion_llegadas,
                    on_reverse_arrival=confirmar_reversion_llegadas,
                    on_retry=reintentar_llegadas,
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
            on_change_context=cambiar_contexto_evento,
        )

    def configure_navigation_bar() -> None:
        can_use_app = bool(
            contexto_usuario.get("cuenta_actual")
            and (contexto_usuario.get("evento_actual") or contexto_usuario.get("eventos_permitidos"))
        )
        can_register_arrivals = bool(contexto_usuario.get("puede_registrar_llegadas"))
        page.navigation_bar = bottom_navigation(
            selected=state["selected"],
            can_use_app=can_use_app,
            can_register_arrivals=can_register_arrivals,
            on_select=select_tab,
        )

    def render() -> None:
        home_control = build_shell()
        if home_control is None:
            raise RuntimeError("build_home_view devolvio None; se esperaba un control Flet.")

        configure_navigation_bar()
        page.clean()
        page.add(home_control)
        page.update()

    def reset_invitados() -> None:
        state["invitados_estado"] = "idle"
        state["invitados"] = []
        state["invitados_mensaje"] = ""
        state["invitados_tipo_busqueda"] = "invitado"
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

    def reset_llegadas() -> None:
        state["arrivals_estado"] = "idle"
        state["arrivals_mensaje"] = ""
        state["arrivals_busqueda"] = ""
        state["arrivals_resultados"] = []
        state["arrivals_invitacion"] = None
        state["arrivals_integrantes"] = []
        state["arrivals_seleccionados"] = set()
        state["arrivals_loading"] = False
        state["arrivals_saving"] = False
        state["arrivals_request_id"] += 1
        state["arrivals_event_key"] = None

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
        tipo_busqueda = str(state["invitados_tipo_busqueda"])
        filtro = str(state["invitados_filtro"])
        print("[INVITADOS][INFO] Pantalla abierta:", f"tipo_busqueda={tipo_busqueda}")
        print("[INVITADOS][INFO] Evento activo utilizado:", active_key[0], active_key[1])
        cargar_invitaciones()
        render()

        def worker() -> None:
            try:
                resultado = listar_invitados(
                    contexto_usuario.get("evento_actual"),
                    busqueda=busqueda,
                    tipo_busqueda=tipo_busqueda,
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
        print(
            "[INVITADOS][INFO] Busqueda aplicada:",
            f"tipo={state['invitados_tipo_busqueda']}",
            f"patron='{state['invitados_busqueda']}'",
        )
        cargar_invitados(reset=True)

    def cambiar_tipo_busqueda_invitados(tipo_busqueda: str) -> None:
        tipo = tipo_busqueda if tipo_busqueda in {"invitado", "mesa"} else "invitado"
        if tipo != tipo_busqueda:
            print("[INVITADOS][WARNING] Tipo de busqueda invalido en vista:", tipo_busqueda)
        state["invitados_tipo_busqueda"] = tipo
        state["invitados"] = []
        state["invitados_offset"] = 0
        state["invitados_has_more"] = False
        state["invitado_detalle"] = None
        state["invitados_estado"] = "idle"
        state["invitados_mensaje"] = "Presiona Buscar para consultar con el nuevo tipo."
        print("[INVITADOS][INFO] Tipo de busqueda cambiado:", tipo)
        render()

    def limpiar_busqueda_invitados() -> None:
        state["invitados_busqueda"] = ""
        state["invitados_filtro"] = "todos"
        print("[INVITADOS][INFO] Busqueda limpiada.")
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
        if checkin_mode:
            print("[CHECKIN][WARN] Operacion bloqueada en modo CHECKIN: crear_invitado")
            state["invitado_form_message"] = "Esta operacion no esta disponible en modo Check-in."
            render()
            return
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

    def abrir_form_crear_imprevisto() -> None:
        print("[INVITADOS][INFO] Apertura del formulario imprevisto.")
        if checkin_mode:
            print("[CHECKIN][WARN] Operacion bloqueada en modo CHECKIN: crear_imprevisto")
            state["invitado_form_message"] = "Esta operacion no esta disponible en modo Check-in."
            render()
            return
        if not puede_registrar_imprevisto(contexto_usuario):
            state["invitado_form_message"] = "No tienes permisos para registrar invitados imprevistos en este evento."
            render()
            return
        cargar_invitaciones()
        if not state["invitaciones"]:
            state["invitado_form_message"] = "No hay invitaciones activas para registrar invitados imprevistos."
            render()
            return
        state["invitado_form"] = {
            "modo": "imprevisto",
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
        if checkin_mode:
            print("[CHECKIN][WARN] Operacion bloqueada en modo CHECKIN: editar_invitado")
            state["invitado_form_message"] = "Esta operacion no esta disponible en modo Check-in."
            render()
            return
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
        if checkin_mode:
            print("[CHECKIN][WARN] Operacion bloqueada en modo CHECKIN: guardar_invitado")
            state["invitado_form_message"] = "Esta operacion no esta disponible en modo Check-in."
            render()
            return
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
                elif form.get("modo") == "imprevisto":
                    resultado = crear_invitado_imprevisto(contexto_usuario, payload, supabase=supabase)
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

    def ejecutar_operacion_invitado(
        invitado: dict[str, Any],
        operacion: Any,
        etiqueta: str,
        cerrar_detalle: bool = False,
    ) -> None:
        active_key = evento_activo_key()
        invitado_key = (invitado.get("cuenta_id"), invitado.get("evento_id"))
        if active_key is None or invitado_key != active_key:
            print("[INVITADOS][WARNING] Cambio de evento antes de ejecutar operacion:", etiqueta)
            state["invitado_form_message"] = "El evento activo cambio. Abre nuevamente la operacion."
            render()
            return
        if state["invitado_saving"]:
            return
        state["invitado_saving"] = True
        state["invitado_form_message"] = ""
        print("[INVITADOS][INFO] Ejecutando operacion:", etiqueta)
        render()

        def worker() -> None:
            try:
                resultado = operacion(contexto_usuario, invitado, supabase=supabase)
                state["invitado_form_message"] = resultado.mensaje
                if resultado.ok:
                    if cerrar_detalle:
                        state["invitado_detalle"] = None
                    elif resultado.invitado:
                        state["invitado_detalle"] = resultado.invitado
                    print("[INVITADOS][INFO]", resultado.mensaje)
                    cargar_invitados(reset=True)
                    return
                if resultado.invitado and not cerrar_detalle:
                    state["invitado_detalle"] = resultado.invitado
                print("[INVITADOS][WARNING] Operacion rechazada:", resultado.estado)
            finally:
                state["invitado_saving"] = False
                render()

        page.run_thread(worker)

    def confirmar_llegada_invitado(invitado: dict[str, Any]) -> None:
        ejecutar_operacion_invitado(
            invitado,
            confirmar_llegada,
            "confirmar_llegada",
        )

    def mostrar_dialogo_confirmacion(
        titulo: str,
        mensaje: str,
        texto_confirmar: str,
        on_confirm: Any,
    ) -> None:
        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text(titulo),
            content=ft.Text(mensaje),
            actions=[
                ft.TextButton(content="Cancelar", on_click=lambda e: cerrar_dialogo()),
                ft.ElevatedButton(content=texto_confirmar, on_click=lambda e: aceptar_dialogo()),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )

        def cerrar_dialogo() -> None:
            dialog.open = False
            page.update()

        def aceptar_dialogo() -> None:
            dialog.open = False
            page.update()
            on_confirm()

        page.show_dialog(dialog)

    def confirmar_reversion_llegada(invitado: dict[str, Any]) -> None:
        mostrar_dialogo_confirmacion(
            "Reversar llegada",
            "Deseas reversar la llegada de este invitado? Esta accion modificara el estado registrado.",
            "Reversar",
            lambda: ejecutar_operacion_invitado(
                invitado,
                reversar_llegada,
                "reversar_llegada",
            ),
        )

    def confirmar_eliminacion_imprevisto(invitado: dict[str, Any]) -> None:
        if checkin_mode:
            print("[CHECKIN][WARN] Operacion bloqueada en modo CHECKIN: eliminar_imprevisto")
            state["invitado_form_message"] = "Esta operacion no esta disponible en modo Check-in."
            render()
            return
        mostrar_dialogo_confirmacion(
            "Eliminar invitado imprevisto",
            "Deseas eliminar este invitado imprevisto? Se inactivara el registro en el evento actual.",
            "Eliminar",
            lambda: ejecutar_operacion_invitado(
                invitado,
                eliminar_invitado_imprevisto,
                "eliminar_imprevisto",
                cerrar_detalle=True,
            ),
        )

    def preparar_llegadas() -> None:
        active_key = evento_activo_key()
        if active_key is None:
            reset_llegadas()
            state["arrivals_estado"] = "event_required"
            state["arrivals_mensaje"] = "Selecciona un evento antes de registrar llegadas."
            render()
            return
        if not contexto_usuario.get("puede_registrar_llegadas"):
            state["arrivals_estado"] = "error"
            state["arrivals_mensaje"] = "El registro de llegadas solo esta disponible cuando el evento se encuentra en fase Evento en proceso."
        else:
            state["arrivals_estado"] = "idle"
            state["arrivals_mensaje"] = "Busca un invitado para cargar su invitacion completa."
        state["arrivals_event_key"] = active_key

    def buscar_llegadas(texto: str) -> None:
        active_key = evento_activo_key()
        if active_key is None:
            reset_llegadas()
            state["arrivals_estado"] = "event_required"
            state["arrivals_mensaje"] = "Selecciona un evento antes de registrar llegadas."
            render()
            return
        busqueda = (texto or "").strip()
        state["arrivals_busqueda"] = busqueda
        state["arrivals_resultados"] = []
        state["arrivals_invitacion"] = None
        state["arrivals_integrantes"] = []
        state["arrivals_seleccionados"] = set()
        if not busqueda:
            state["arrivals_estado"] = "idle"
            state["arrivals_mensaje"] = "Escribe un nombre para buscar invitados."
            render()
            return
        if state["arrivals_loading"]:
            return

        state["arrivals_loading"] = True
        state["arrivals_estado"] = "loading"
        state["arrivals_mensaje"] = "Buscando invitados..."
        state["arrivals_request_id"] += 1
        request_id = state["arrivals_request_id"]
        state["arrivals_event_key"] = active_key
        print("[INVITADOS][INFO] Busqueda en Registro de llegadas:", "si")
        render()

        def worker() -> None:
            try:
                resultado = listar_invitados(
                    contexto_usuario.get("evento_actual"),
                    busqueda=busqueda,
                    filtro="todos",
                    limit=20,
                    offset=0,
                    supabase=supabase,
                )
                if request_id != state["arrivals_request_id"] or active_key != evento_activo_key():
                    print("[INVITADOS][WARNING] Resultado antiguo de llegadas ignorado.")
                    return
                state["arrivals_estado"] = resultado.estado if resultado.ok else "error"
                state["arrivals_mensaje"] = resultado.mensaje
                state["arrivals_resultados"] = resultado.invitados if resultado.ok else []
            finally:
                state["arrivals_loading"] = False
                render()

        page.run_thread(worker)

    def limpiar_llegadas() -> None:
        print("[INVITADOS][INFO] Registro de llegadas limpiado.")
        reset_llegadas()
        preparar_llegadas()
        render()

    def reintentar_llegadas() -> None:
        buscar_llegadas(str(state["arrivals_busqueda"]))

    def seleccionar_invitado_llegadas(invitado: dict[str, Any]) -> None:
        active_key = evento_activo_key()
        if active_key is None or (invitado.get("cuenta_id"), invitado.get("evento_id")) != active_key:
            state["arrivals_estado"] = "error"
            state["arrivals_mensaje"] = "El evento activo cambio. Busca nuevamente al invitado."
            render()
            return
        if state["arrivals_loading"]:
            return
        state["arrivals_loading"] = True
        state["arrivals_estado"] = "loading"
        state["arrivals_mensaje"] = "Cargando invitacion..."
        state["arrivals_seleccionados"] = set()
        state["arrivals_request_id"] += 1
        request_id = state["arrivals_request_id"]
        print("[INVITADOS][INFO] Invitado seleccionado para cargar invitacion.")
        render()

        def worker() -> None:
            try:
                resultado = cargar_grupo_invitacion(
                    contexto_usuario.get("evento_actual"),
                    invitado,
                    supabase=supabase,
                )
                if request_id != state["arrivals_request_id"] or active_key != evento_activo_key():
                    print("[INVITADOS][WARNING] Grupo antiguo de llegadas ignorado.")
                    return
                state["arrivals_estado"] = resultado.estado if resultado.ok else "error"
                state["arrivals_mensaje"] = resultado.mensaje
                state["arrivals_invitacion"] = resultado.invitacion
                state["arrivals_integrantes"] = resultado.invitados
                state["arrivals_resultados"] = []
                pendientes = [item for item in resultado.invitados if not item.get("llegada_confirmada")]
                confirmados = [item for item in resultado.invitados if item.get("llegada_confirmada")]
                print(
                    "[LLEGADAS][INFO] Invitacion cargada:",
                    f"integrantes={len(resultado.invitados)}",
                    f"pendientes={len(pendientes)}",
                    f"confirmados={len(confirmados)}",
                )
            finally:
                state["arrivals_loading"] = False
                render()

        page.run_thread(worker)

    def alternar_invitado_llegadas(invitado: dict[str, Any], seleccionado: bool) -> None:
        if invitado.get("llegada_confirmada"):
            return
        selected = set(state["arrivals_seleccionados"])
        invitado_uuid = str(invitado.get("invitado_uuid", ""))
        if seleccionado:
            selected.add(invitado_uuid)
        else:
            selected.discard(invitado_uuid)
        state["arrivals_seleccionados"] = selected
        render()

    def seleccionar_pendientes_llegadas() -> None:
        pendientes = {
            str(item.get("invitado_uuid"))
            for item in state["arrivals_integrantes"]
            if item.get("invitado_uuid") and not item.get("llegada_confirmada")
        }
        state["arrivals_seleccionados"] = pendientes
        print("[INVITADOS][INFO] Pendientes seleccionados:", len(pendientes))
        render()

    def confirmar_seleccion_llegadas() -> None:
        if state["arrivals_saving"]:
            return
        seleccionados = set(state["arrivals_seleccionados"])
        integrantes = [
            item
            for item in state["arrivals_integrantes"]
            if str(item.get("invitado_uuid")) in seleccionados and not item.get("llegada_confirmada")
        ]
        if not integrantes:
            state["arrivals_mensaje"] = "Selecciona al menos un invitado pendiente para confirmar."
            render()
            return
        active_key = evento_activo_key()
        if active_key is None or active_key != state.get("arrivals_event_key"):
            state["arrivals_mensaje"] = "El evento activo cambio. Busca nuevamente la invitacion."
            render()
            return
        state["arrivals_saving"] = True
        state["arrivals_mensaje"] = "Confirmando llegadas..."
        print("[INVITADOS][INFO] Confirmacion multiple solicitada:", len(integrantes))
        render()

        def worker() -> None:
            try:
                resultado = confirmar_llegadas_invitados(
                    contexto_usuario,
                    state["arrivals_invitacion"],
                    integrantes,
                    supabase=supabase,
                )
                state["arrivals_estado"] = "ready" if resultado.ok else "error"
                state["arrivals_mensaje"] = resultado.mensaje
                state["arrivals_integrantes"] = resultado.invitados
                state["arrivals_seleccionados"] = set()
                print("[INVITADOS][INFO] Resultado confirmacion multiple:", resultado.estado)
            finally:
                state["arrivals_saving"] = False
                render()

        page.run_thread(worker)

    def confirmar_reversion_llegadas(invitado: dict[str, Any]) -> None:
        nombre = str(invitado.get("nombre_completo") or "este invitado")
        mostrar_dialogo_confirmacion(
            "Revertir llegada",
            f"Deseas revertir la llegada de {nombre}?",
            "Revertir",
            lambda: ejecutar_reversion_llegadas(invitado),
        )

    def ejecutar_reversion_llegadas(invitado: dict[str, Any]) -> None:
        active_key = evento_activo_key()
        invitado_key = (invitado.get("cuenta_id"), invitado.get("evento_id"))
        if active_key is None or active_key != state.get("arrivals_event_key") or invitado_key != active_key:
            state["arrivals_mensaje"] = "El evento activo cambio. Busca nuevamente la invitacion."
            render()
            return
        if state["arrivals_saving"]:
            return
        state["arrivals_saving"] = True
        state["arrivals_mensaje"] = "Revirtiendo llegada..."
        print(
            "[INVITADOS][INFO] Intento de revertir llegada desde Registro:",
            f"rol={contexto_usuario.get('rol_global_calculado')}",
            f"cuenta={active_key[0]}",
            f"evento={active_key[1]}",
            f"invitado={invitado.get('invitado_id')}",
        )
        render()

        def worker() -> None:
            try:
                resultado = reversar_llegada(contexto_usuario, invitado, supabase=supabase)
                state["arrivals_mensaje"] = resultado.mensaje
                if resultado.ok:
                    grupo = cargar_grupo_invitacion(
                        contexto_usuario.get("evento_actual"),
                        resultado.invitado or invitado,
                        supabase=supabase,
                    )
                    if grupo.ok:
                        state["arrivals_invitacion"] = grupo.invitacion
                        state["arrivals_integrantes"] = grupo.invitados
                    state["arrivals_seleccionados"] = set()
                    state["arrivals_estado"] = "ready"
                    print("[INVITADOS][INFO] Reversion ejecutada desde Registro.")
                else:
                    state["arrivals_estado"] = "error" if resultado.estado == "connection_error" else state["arrivals_estado"]
                    if resultado.invitado:
                        grupo = cargar_grupo_invitacion(
                            contexto_usuario.get("evento_actual"),
                            resultado.invitado,
                            supabase=supabase,
                        )
                        if grupo.ok:
                            state["arrivals_invitacion"] = grupo.invitacion
                            state["arrivals_integrantes"] = grupo.invitados
                    print("[INVITADOS][WARNING] Reversion no aplicada:", resultado.estado)
            finally:
                state["arrivals_saving"] = False
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
                        if checkin_mode:
                            state["selected"] = "arrivals"
                            preparar_llegadas()
                        print(
                            "[EVENTOS][INFO] Evento activo:",
                            evento_activo.get("cuenta_id"),
                            evento_activo.get("evento_id"),
                        )
                        if checkin_mode:
                            print(
                                "[CHECKIN][INFO] Evento activo seleccionado:",
                                f"cuenta={evento_activo.get('cuenta_id')}",
                                f"evento={evento_activo.get('evento_id')}",
                            )
                            print("[CHECKIN][INFO] Entrada directa a Registrar llegadas.")
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
        reset_llegadas()
        if checkin_mode:
            state["selected"] = "arrivals"
            preparar_llegadas()
        print(
            "[EVENTOS][INFO] Cambio de evento activo:",
            evento_activo.get("cuenta_id"),
            evento_activo.get("evento_id"),
        )
        if checkin_mode:
            print(
                "[CHECKIN][INFO] Evento activo seleccionado:",
                f"cuenta={evento_activo.get('cuenta_id')}",
                f"evento={evento_activo.get('evento_id')}",
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
            preparar_llegadas()
            render()
            return
        if tab == "arrivals":
            state["selected"] = "arrivals"
            preparar_llegadas()
            render()
            return
        if tab == "preferences":
            if checkin_mode:
                print("[CHECKIN][WARN] Operacion bloqueada en modo CHECKIN: preferencias")
                return
            print("[EVENTOS][INFO] Apertura de Preferencias desde menu de usuario.")
        state["selected"] = tab
        render()

    def cambiar_contexto_evento() -> None:
        print("[CHECKIN][INFO] Cambio de evento solicitado desde menu de usuario.")
        limpiar_evento_activo(contexto_usuario)
        contexto_usuario["evento_activo_seleccionado"] = False
        guardar_contexto_sesion(page.session.store, contexto_usuario)
        reset_invitados()
        reset_llegadas()
        state["selected"] = "dashboard"
        state["eventos_consulta_iniciada"] = False
        state["eventos_estado"] = "loading"
        state["eventos_mensaje"] = "Selecciona un evento para continuar."
        cargar_eventos()

    def logout() -> None:
        print("[EVENTOS][INFO] Cierre de sesion solicitado desde menu de usuario.")
        try:
            sign_out_local_session(supabase)
        except Exception:
            pass
        try:
            limpiar_contexto_sesion(page.session.store)
            print("[EVENTOS][INFO] Contexto de evento eliminado durante logout.")
        except Exception:
            pass
        page.navigation_bar = None
        page.clean()
        from views.login_view import build_login_view

        build_login_view(page, supabase)
        page.update()

    configure_navigation_bar()
    home_control = build_shell()
    home_control.data = {"start_eventos": cargar_eventos}
    return home_control
