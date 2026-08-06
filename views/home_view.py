from __future__ import annotations

import asyncio
from copy import deepcopy
from datetime import datetime
from pathlib import Path
import traceback
import threading
from typing import Any

import flet as ft

from config import is_checkin_mode
from components.app_shell import app_shell
from components.bottom_navigation import bottom_navigation
from services.auth_service import sign_out_local_session
from services.authorization_service import puede_administrar_lugares, puede_ver_administracion_eventos, puede_ver_importacion_excel
from services.excel_import_service import consultar_evento_tiene_datos, ejecutar_importacion, generar_archivo_errores, leer_archivo_excel, preview_coincide_contexto, validar_contexto_importacion, vincular_preview_contexto
from services.excel_template_service import TEMPLATE_FILENAME, generar_plantilla_excel
from services.dashboard_service import DashboardRefreshController, IndicadoresDashboard, obtener_indicadores_dashboard
from services.evento_context_service import (
    buscar_evento_por_key,
    construir_contexto_evento_activo,
    evento_key,
    guardar_contexto_sesion,
    guardar_eventos_disponibles,
    limpiar_contexto_sesion,
    limpiar_evento_activo,
    sincronizar_evento_activo,
    establecer_evento_activo,
    es_evento_autorizado,
)
from services.evento_service import (
    actualizar_evento,
    cambiar_estado_evento,
    cerrar_evento,
    crear_evento,
    establecer_evento_predeterminado,
    iniciar_evento,
    listar_eventos_administrables,
    listar_lugares_disponibles,
    listar_salones_disponibles,
    obtener_eventos_disponibles,
)
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
from services.session_service import PageSessionController
from services.navigation_service import ROUTES, parse_app_route, route_for
from services.lugar_service import (
    actualizar_lugar,
    actualizar_salon,
    cambiar_estado_lugar,
    cambiar_estado_salon,
    crear_lugar,
    crear_salon,
    listar_salones,
    refrescar_catalogo_lugares,
)
from views.arrivals_view import arrivals_view
from views.dashboard_view import dashboard_view
from views.invitados_view import invitado_detail_view, invitado_form_view, invitados_view
from views.lugares_view import lugar_form_view, lugares_view
from views.eventos_admin_view import evento_detail_view, evento_form_view, eventos_admin_view
from views.event_selection_view import event_selection_view
from views.excel_import_view import excel_import_view


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


def _registrar_resultado_form_evento(state: dict[str, Any], result: Any) -> None:
    """Aplica siempre una respuesta visible al estado del formulario de eventos."""
    state["eventos_admin_form_message"] = result.mensaje
    state["eventos_admin_mensaje"] = result.mensaje
    if result.ok:
        state["eventos_admin_form"] = None


def build_home_view(
    page: ft.Page,
    contexto_usuario: dict[str, Any],
    supabase: Any = None,
    session_controller: PageSessionController | None = None,
) -> ft.Control:
    checkin_mode = is_checkin_mode()
    excel_file_picker = ft.FilePicker()
    if hasattr(page, "services"):
        page.services.append(excel_file_picker)
    state: dict[str, Any] = {
        "selected": "arrivals" if checkin_mode else "dashboard",
        "eventos_estado": "loading",
        "eventos": [],
        "eventos_mensaje": "Cargando eventos...",
        "eventos_loading": False,
        "eventos_consulta_iniciada": False,
        "dashboard_estado": "idle",
        "dashboard_mensaje": "",
        "dashboard_indicadores": IndicadoresDashboard(),
        "dashboard_event_key": None,
        "dashboard_ultima_actualizacion": "",
        "dashboard_refresh": DashboardRefreshController(),
        "session_active": True,
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
        "lugares_estado": "idle",
        "lugares_mensaje": "",
        "lugares": [],
        "lugares_paises": [],
        "lugar_seleccionado": None,
        "lugares_salones": [],
        "lugares_form": None,
        "lugares_form_message": "",
        "lugares_saving": False,
        "eventos_admin_estado": "idle",
        "eventos_admin_mensaje": "",
        "eventos_admin_items": [],
        "eventos_admin_lugares": [],
        "eventos_admin_salones": [],
        "eventos_admin_form": None,
        "eventos_admin_form_message": "",
        "eventos_admin_saving": False,
        "eventos_admin_filtros": {"busqueda": "", "fase": "Todas", "estado": "Todos", "desde": "", "hasta": ""},
        "route_identifier": None,
        "route_action": None,
        "previous_section": "dashboard",
        "excel_import_estado": "idle",
        "excel_import_mensaje": "",
        "excel_import_filename": "",
        "excel_import_size": 0,
        "excel_import_preview": None,
        "excel_import_has_existing_data": None,
        "excel_import_importing": False,
        "excel_import_result": None,
    }

    def build_content() -> ft.Control:
        if state["selected"] == "excel_import":
            if checkin_mode or not puede_ver_importacion_excel(contexto_usuario):
                return _placeholder("Acceso denegado", "Tu rol o modo de aplicación no permite importar invitados.")
            return excel_import_view(
                contexto_usuario, state["excel_import_estado"], state["excel_import_mensaje"],
                state["excel_import_filename"], state["excel_import_size"], state["excel_import_preview"],
                descargar_plantilla_excel, seleccionar_archivo_excel, descargar_errores_excel,
                confirmar_importacion_excel, state["excel_import_importing"], state["excel_import_result"],
                bool(state["excel_import_preview"] and preview_coincide_contexto(state["excel_import_preview"], contexto_usuario) and state["excel_import_has_existing_data"] is False),
            )
        if state["selected"] == "event_selection":
            return event_selection_view(
                eventos=state["eventos"], evento_actual=contexto_usuario.get("evento_actual"),
                estado=state["eventos_estado"], mensaje=state["eventos_mensaje"],
                on_select=select_event, on_back=lambda: navigate("dashboard"),
                on_retry=cargar_eventos,
            )
        if state["selected"] == "guest_detail":
            return invitado_detail_view(
                state["invitado_detalle"],
                False if checkin_mode else puede_eliminar_imprevisto(contexto_usuario),
                state["invitado_saving"], state["invitados_mensaje"],
                confirmar_eliminacion_imprevisto, lambda: navigate("guests"),
            )
        if state["selected"] == "guest_form" and state.get("invitado_form"):
            form = state["invitado_form"]
            can_manage = (
                puede_registrar_imprevisto(contexto_usuario)
                if form.get("modo") == "imprevisto"
                else puede_administrar_invitados_planificados(contexto_usuario)
            )
            return invitado_form_view(
                form, state["invitaciones"], can_manage, state["invitado_saving"],
                state["invitado_form_message"], guardar_form_invitado, cancelar_form_invitado,
            )
        if state["selected"] == "event_form" and state.get("eventos_admin_form"):
            return evento_form_view(
                state["eventos_admin_form"], state["eventos_admin_lugares"], state["eventos_admin_salones"],
                state["eventos_admin_saving"], state["eventos_admin_form_message"],
                cargar_salones_evento, guardar_form_evento, cancelar_form_evento,
            )
        if state["selected"] == "event_detail":
            return evento_detail_view(
                buscar_evento_admin(state.get("route_identifier")), state["eventos_admin_lugares"],
                state["eventos_admin_salones"], lambda: navigate("events_admin"), abrir_form_editar_evento,
            )
        if state["selected"] == "location_form" and state.get("lugares_form"):
            return lugar_form_view(
                state["lugares_form"], state["lugares_paises"], state["lugares_saving"],
                state["lugares_form_message"], guardar_form_lugares, cancelar_form_lugares,
            )
        if state["selected"] == "events_admin":
            if checkin_mode or not puede_ver_administracion_eventos(contexto_usuario):
                return eventos_admin_view(
                    contexto_usuario, "denied", "", [], [], [], None, "", False, {},
                    cargar_eventos_admin, abrir_form_crear_evento, abrir_form_editar_evento,
                    cargar_salones_evento, guardar_form_evento, cancelar_form_evento,
                    aplicar_filtros_eventos, solicitar_estado_evento, solicitar_inicio_evento,
                    solicitar_cierre_evento, hacer_evento_predeterminado, abrir_detalle_evento,
                )
            return eventos_admin_view(
                contexto=contexto_usuario,
                estado=state["eventos_admin_estado"],
                mensaje=state["eventos_admin_mensaje"],
                eventos=state["eventos_admin_items"],
                lugares=state["eventos_admin_lugares"],
                salones=state["eventos_admin_salones"],
                form=state["eventos_admin_form"],
                form_message=state["eventos_admin_form_message"],
                saving=state["eventos_admin_saving"],
                filtros=state["eventos_admin_filtros"],
                on_retry=cargar_eventos_admin,
                on_new=abrir_form_crear_evento,
                on_edit=abrir_form_editar_evento,
                on_detail=abrir_detalle_evento,
                on_place_change=cargar_salones_evento,
                on_save=guardar_form_evento,
                on_cancel=cancelar_form_evento,
                on_filter=aplicar_filtros_eventos,
                on_state=solicitar_estado_evento,
                on_start=solicitar_inicio_evento,
                on_close=solicitar_cierre_evento,
                on_default=hacer_evento_predeterminado,
            )
        if state["selected"] == "locations":
            if checkin_mode or not puede_administrar_lugares(contexto_usuario):
                return _placeholder(
                    "Acceso denegado",
                    "Tu rol o modo de aplicacion no permite administrar lugares y salones.",
                )
            return lugares_view(
                contexto=contexto_usuario,
                estado=state["lugares_estado"],
                mensaje=state["lugares_mensaje"],
                lugares=state["lugares"],
                lugar_seleccionado=state["lugar_seleccionado"],
                salones=state["lugares_salones"],
                paises=state["lugares_paises"],
                form=state["lugares_form"],
                form_message=state["lugares_form_message"],
                saving=state["lugares_saving"],
                can_manage=puede_administrar_lugares(contexto_usuario),
                on_retry=cargar_lugares,
                on_select_place=seleccionar_lugar,
                on_new_place=abrir_form_crear_lugar,
                on_edit_place=abrir_form_editar_lugar,
                on_change_place_state=confirmar_estado_lugar,
                on_new_room=abrir_form_crear_salon,
                on_edit_room=abrir_form_editar_salon,
                on_change_room_state=confirmar_estado_salon,
                on_save_form=guardar_form_lugares,
                on_cancel_form=cancelar_form_lugares,
            )

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
            contexto_usuario, estado=state["dashboard_estado"],
            indicadores=state["dashboard_indicadores"], mensaje=state["dashboard_mensaje"],
            on_retry=cargar_dashboard, ultima_actualizacion=state["dashboard_ultima_actualizacion"],
            on_select_event=lambda: navigate("event_selection"),
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
            on_manage_locations=lambda: select_tab("locations"),
            on_manage_events=lambda: select_tab("events_admin"),
            on_select_event=lambda: select_tab("event_selection"),
            on_excel_import=lambda: select_tab("excel_import"),
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
        _sincronizar_actualizacion_dashboard()
        home_control = build_shell()
        if home_control is None:
            raise RuntimeError("build_home_view devolvio None; se esperaba un control Flet.")

        home_control.data = _home_callbacks()
        configure_navigation_bar()
        page.clean()
        page.add(home_control)
        page.update()

    def _marca_actualizacion() -> str:
        now = datetime.now().astimezone()
        hour = now.hour % 12 or 12
        suffix = "a. m." if now.hour < 12 else "p. m."
        return f"Actualizado {hour}:{now.minute:02d} {suffix}"

    async def _actualizar_dashboard_periodicamente(generation: int) -> None:
        try:
            while (
                state["session_active"]
                and state["selected"] == "dashboard"
                and state["dashboard_refresh"].is_current(generation)
            ):
                await asyncio.sleep(30)
                if (
                    not state["session_active"]
                    or state["selected"] != "dashboard"
                    or not state["dashboard_refresh"].is_current(generation)
                ):
                    break
                key = evento_activo_key()
                if key is None:
                    break
                result = await asyncio.to_thread(obtener_indicadores_dashboard, contexto_usuario, supabase)
                if key != evento_activo_key() or state["selected"] != "dashboard":
                    continue
                state["dashboard_estado"] = result.estado if result.ok else "error"
                state["dashboard_mensaje"] = result.mensaje
                if result.ok:
                    state["dashboard_indicadores"] = result.indicadores
                    state["dashboard_event_key"] = key
                    state["dashboard_ultima_actualizacion"] = _marca_actualizacion()
                render()
        except asyncio.CancelledError:
            pass
        except Exception as ex:
            print("[DASHBOARD][ERROR] actualizacion automatica", type(ex).__name__, str(ex))
        finally:
            state["dashboard_refresh"].finish(generation)

    def _detener_actualizacion_dashboard() -> None:
        state["dashboard_refresh"].stop()

    def _pausar_home() -> None:
        state["session_active"] = False
        _detener_actualizacion_dashboard()

    def _reanudar_home() -> None:
        state["session_active"] = True
        _sincronizar_actualizacion_dashboard()

    def _home_callbacks() -> dict[str, Any]:
        return {
            "start_eventos": cargar_eventos,
            "pause_dashboard": _pausar_home,
            "resume_dashboard": _reanudar_home,
            "select_event": select_event,
            "state": state,
        }

    def _sincronizar_actualizacion_dashboard() -> None:
        should_run = bool(
            state["session_active"]
            and state["selected"] == "dashboard"
            and contexto_usuario.get("evento_actual")
        )
        controller = state["dashboard_refresh"]
        task = controller.task
        if not should_run:
            if task is not None:
                _detener_actualizacion_dashboard()
            return
        if task is None or task.done():
            controller.start(page, _actualizar_dashboard_periodicamente)

    def cargar_dashboard() -> None:
        key = evento_activo_key()
        if key is None:
            state["dashboard_estado"] = "event_required"
            state["dashboard_indicadores"] = IndicadoresDashboard()
            render()
            return
        if state["dashboard_estado"] == "loading" and state["dashboard_event_key"] == key:
            return
        state["dashboard_estado"] = "loading"
        state["dashboard_mensaje"] = "Cargando indicadores..."
        state["dashboard_event_key"] = key
        render()

        def worker() -> None:
            result = obtener_indicadores_dashboard(contexto_usuario, supabase)
            if key != evento_activo_key():
                return
            state["dashboard_estado"] = result.estado if result.ok else "error"
            state["dashboard_mensaje"] = result.mensaje
            state["dashboard_indicadores"] = result.indicadores
            state["dashboard_event_key"] = key
            if result.ok:
                state["dashboard_ultima_actualizacion"] = _marca_actualizacion()
            render()

        page.run_thread(worker)

    def navigate(section: str, identifier: Any = None, action: str | None = None) -> None:
        current = state.get("selected")
        if current not in {"guest_detail", "guest_form", "event_detail", "event_form"}:
            state["previous_section"] = current or "dashboard"
        state["route_identifier"] = None if identifier is None else str(identifier)
        state["route_action"] = action
        state["selected"] = section
        if section == "guest_detail":
            route = route_for("guests", identifier)
        elif section == "guest_form":
            route = route_for("guests", identifier or "nuevo", action)
        elif section == "event_detail":
            route = route_for("events_admin", identifier)
        elif section == "event_form":
            route = route_for("events_admin", identifier or "nuevo", action)
        elif section == "location_form":
            route = route_for("locations", "form", action or str(identifier or ""))
        else:
            route = ROUTES.get(section, ROUTES["dashboard"])
        if str(getattr(page, "route", "") or "") != route:
            page.go(route)
        else:
            render()

    async def _guardar_descarga(nombre: str, contenido: bytes, extension: str) -> None:
        selected_path = await excel_file_picker.save_file(
            dialog_title="Guardar archivo de EventPlus", file_name=nombre,
            file_type=ft.FilePickerFileType.CUSTOM, allowed_extensions=[extension], src_bytes=contenido,
        )
        if selected_path and not page.web:
            Path(selected_path).write_bytes(contenido)

    def descargar_plantilla_excel() -> None:
        permitido, error = validar_contexto_importacion(contexto_usuario, full_mode=not checkin_mode)
        if not permitido:
            state["excel_import_estado"], state["excel_import_mensaje"] = "error", error
            render(); return
        async def worker() -> None:
            await _guardar_descarga(TEMPLATE_FILENAME, generar_plantilla_excel(), "xlsx")
        page.run_task(worker)

    def seleccionar_archivo_excel() -> None:
        permitido, error = validar_contexto_importacion(contexto_usuario, full_mode=not checkin_mode)
        if not permitido:
            state["excel_import_estado"], state["excel_import_mensaje"] = "error", error
            render(); return
        async def worker() -> None:
            files = await excel_file_picker.pick_files(
                dialog_title="Seleccionar archivo XLSX", file_type=ft.FilePickerFileType.CUSTOM,
                allowed_extensions=["xlsx"], allow_multiple=False, with_data=True,
            )
            if not files: return
            selected = files[0]
            content = selected.bytes
            if content is None and selected.path:
                content = await asyncio.to_thread(Path(selected.path).read_bytes)
            content = bytes(content or b"")
            state["excel_import_estado"] = "loading"
            state["excel_import_filename"], state["excel_import_size"] = selected.name, len(content)
            state["excel_import_mensaje"] = "Validando el archivo completo..."
            render()
            preview = await asyncio.to_thread(leer_archivo_excel, selected.name, content)
            if preview.is_valid:
                preview = vincular_preview_contexto(preview, contexto_usuario)
            state["excel_import_preview"] = preview
            state["excel_import_result"] = None
            blocked = state.get("excel_import_has_existing_data") is True
            state["excel_import_estado"] = "valid" if preview.is_valid and not blocked else "error"
            state["excel_import_mensaje"] = (
                "Este evento ya contiene información y no admite importación inicial."
                if blocked else "Archivo válido y listo para importación."
                if preview.is_valid else "El archivo contiene errores; no se habilitó la importación."
            )
            render()
        page.run_task(worker)

    def descargar_errores_excel() -> None:
        preview = state.get("excel_import_preview")
        if not preview: return
        async def worker() -> None:
            await _guardar_descarga("EventPlus_Errores_Importacion.csv", generar_archivo_errores(preview), "csv")
        page.run_task(worker)

    def confirmar_importacion_excel() -> None:
        if state["excel_import_importing"]:
            return
        preview = state.get("excel_import_preview")
        if not preview or not preview_coincide_contexto(preview, contexto_usuario) or state.get("excel_import_has_existing_data") is not False:
            state["excel_import_estado"] = "error"
            state["excel_import_mensaje"] = "El evento cambió después de validar el archivo. Vuelva a seleccionar y validar el archivo."
            render()
            return

        async def ejecutar_confirmado() -> None:
            state["excel_import_mensaje"] = "Importando en una sola transacción..."
            render()
            try:
                result = await asyncio.to_thread(ejecutar_importacion, supabase, contexto_usuario, preview)
                state["excel_import_result"] = result
                state["excel_import_mensaje"] = result.message
                if result.ok:
                    state["excel_import_estado"] = "success"
                    state["excel_import_filename"] = ""
                    state["excel_import_size"] = 0
                    state["excel_import_preview"] = None
                    state["excel_import_has_existing_data"] = True
                    reset_invitados()
                    reset_llegadas()
                    invalidar_dashboard()
                else:
                    state["excel_import_estado"] = "error"
            finally:
                state["excel_import_importing"] = False
                render()

        def iniciar_importacion() -> None:
            if state["excel_import_importing"]:
                return
            state["excel_import_importing"] = True
            render()
            page.run_task(ejecutar_confirmado)

        mostrar_dialogo_confirmacion(
            "Confirmar importación",
            "La importación se realizará en una sola transacción. Si ocurre un error no se conservará ningún registro parcial.",
            "Importar",
            iniciar_importacion,
        )

    def handle_route_change(e: ft.RouteChangeEvent) -> None:
        section, identifier, action = parse_app_route(getattr(e, "route", None) or page.route)
        state["route_identifier"] = identifier
        state["route_action"] = action
        if section == "guests" and identifier:
            if identifier in {"nuevo", "imprevisto"} or action == "editar":
                state["selected"] = "guest_form"
            else:
                state["selected"] = "guest_detail"
                if not state.get("invitado_detalle") or str(state["invitado_detalle"].get("invitado_uuid")) != identifier:
                    cargar_detalle_invitado_uuid(identifier, navegar=False)
                    return
        elif section == "events_admin" and identifier:
            state["selected"] = "event_form" if identifier == "nuevo" or action == "editar" else "event_detail"
        elif section == "locations" and identifier == "form":
            state["selected"] = "location_form"
        else:
            state["selected"] = section
        if section == "dashboard" and contexto_usuario.get("evento_actual") and state["dashboard_event_key"] != evento_activo_key():
            cargar_dashboard()
            return
        render()

    page.on_route_change = handle_route_change

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

    def invalidar_dashboard() -> None:
        state["dashboard_event_key"] = None
        state["dashboard_ultima_actualizacion"] = ""

    def evento_activo_key() -> tuple[int, int] | None:
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

    def cargar_detalle_invitado_uuid(invitado_uuid: str, navegar: bool = True) -> None:
        active_key = evento_activo_key()
        if active_key is None:
            state["invitado_detalle"] = None
            state["invitados_mensaje"] = "Selecciona un evento antes de consultar los invitados."
            render()
            return
        print("[INVITADOS][INFO] Invitado seleccionado para detalle.")
        resultado = obtener_invitado_por_id(
            contexto_usuario.get("evento_actual"),
            invitado_uuid,
            supabase=supabase,
        )
        if resultado.ok:
            state["invitado_detalle"] = resultado.invitado
            if navegar:
                navigate("guest_detail", invitado_uuid)
                return
        else:
            state["invitado_detalle"] = None
            state["invitados_mensaje"] = resultado.mensaje
            state["invitados_estado"] = "error" if resultado.estado == "connection_error" else state["invitados_estado"]
        render()

    def seleccionar_invitado_detalle(invitado: dict[str, Any]) -> None:
        cargar_detalle_invitado_uuid(str(invitado.get("invitado_uuid", "")))

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
        navigate("guest_form", "nuevo")

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
        navigate("guest_form", "imprevisto")

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
        navigate("guest_form", invitado_actual.get("invitado_uuid"), "editar")

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
                    invalidar_dashboard()
                    state["invitado_form"] = None
                    state["invitado_form_message"] = resultado.mensaje
                    state["invitado_detalle"] = None
                    print("[INVITADOS][INFO]", resultado.mensaje)
                    cargar_invitados(reset=True)
                    navigate("guests")
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
                    invalidar_dashboard()
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
                ft.Button(content=texto_confirmar, on_click=lambda e: aceptar_dialogo()),
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

    def _refrescar_lugares_desde_fuente() -> bool:
        selected_id = (state.get("lugar_seleccionado") or {}).get("lugar_id")
        resultado = refrescar_catalogo_lugares(supabase, contexto_usuario, selected_id)
        state["lugares_estado"] = resultado.estado if resultado.ok else "error"
        state["lugares_mensaje"] = resultado.mensaje
        state["lugares"] = resultado.lugares
        state["lugares_paises"] = resultado.paises
        state["lugar_seleccionado"] = resultado.lugar_seleccionado
        state["lugares_salones"] = resultado.salones
        return resultado.ok

    def cargar_lugares() -> None:
        if checkin_mode or not puede_administrar_lugares(contexto_usuario):
            state["lugares_estado"] = "denied"
            state["lugares_mensaje"] = "No tienes permisos para administrar lugares y salones."
            render()
            return
        if state["lugares_estado"] == "loading":
            return
        state["lugares_estado"] = "loading"
        state["lugares_mensaje"] = "Cargando lugares..."
        render()

        def worker() -> None:
            _refrescar_lugares_desde_fuente()
            render()

        page.run_thread(worker)

    def cargar_salones(lugar: dict[str, Any], *, render_after: bool = True) -> None:
        resultado = listar_salones(
            supabase,
            contexto_usuario,
            lugar.get("lugar_id"),
        )
        state["lugares_salones"] = resultado.items if resultado.ok else []
        if not resultado.ok:
            state["lugares_mensaje"] = resultado.mensaje
        if render_after:
            render()

    def seleccionar_lugar(lugar: dict[str, Any]) -> None:
        state["lugar_seleccionado"] = lugar
        state["lugares_form"] = None
        state["lugares_form_message"] = ""
        cargar_salones(lugar)

    def abrir_form_crear_lugar() -> None:
        if not puede_administrar_lugares(contexto_usuario):
            state["lugares_form_message"] = "No tienes permisos para crear lugares."
            render()
            return
        state["lugares_form"] = {"modo": "crear_lugar", "item": {}}
        state["lugares_form_message"] = ""
        navigate("location_form", action="crear_lugar")

    def abrir_form_editar_lugar(lugar: dict[str, Any]) -> None:
        if not puede_administrar_lugares(contexto_usuario):
            state["lugares_form_message"] = "No tienes permisos para editar lugares."
            render()
            return
        state["lugares_form"] = {"modo": "editar_lugar", "item": dict(lugar)}
        state["lugares_form_message"] = ""
        navigate("location_form", action="editar_lugar")

    def abrir_form_crear_salon() -> None:
        if not state.get("lugar_seleccionado"):
            state["lugares_mensaje"] = "Selecciona un lugar antes de agregar un salon."
            render()
            return
        state["lugares_form"] = {"modo": "crear_salon", "item": {}}
        state["lugares_form_message"] = ""
        navigate("location_form", action="crear_salon")

    def abrir_form_editar_salon(salon: dict[str, Any]) -> None:
        state["lugares_form"] = {"modo": "editar_salon", "item": dict(salon)}
        state["lugares_form_message"] = ""
        navigate("location_form", action="editar_salon")

    def cancelar_form_lugares() -> None:
        state["lugares_form"] = None
        state["lugares_form_message"] = ""
        navigate("locations")

    def guardar_form_lugares(payload: dict[str, Any]) -> None:
        form = state.get("lugares_form")
        if not form or state["lugares_saving"]:
            return
        state["lugares_saving"] = True
        state["lugares_form_message"] = ""
        render()

        def worker() -> None:
            try:
                modo = form.get("modo")
                if modo == "crear_lugar":
                    resultado = crear_lugar(supabase, contexto_usuario, payload)
                elif modo == "editar_lugar":
                    resultado = actualizar_lugar(
                        supabase,
                        contexto_usuario,
                        (form.get("item") or {}).get("lugar_id"),
                        payload,
                    )
                elif modo == "crear_salon":
                    resultado = crear_salon(
                        supabase,
                        contexto_usuario,
                        (state.get("lugar_seleccionado") or {}).get("lugar_id"),
                        payload,
                    )
                else:
                    item = form.get("item") or {}
                    resultado = actualizar_salon(
                        supabase,
                        contexto_usuario,
                        item.get("lugar_id"),
                        item.get("salon_id"),
                        payload,
                    )
                state["lugares_form_message"] = resultado.mensaje
                if resultado.ok:
                    state["lugares_form"] = None
                    if _refrescar_lugares_desde_fuente():
                        navigate("locations")
            finally:
                state["lugares_saving"] = False
                render()

        page.run_thread(worker)

    def confirmar_estado_lugar(lugar: dict[str, Any], estado: str) -> None:
        mostrar_dialogo_confirmacion(
            f"{'Activar' if estado == 'Activo' else 'Desactivar'} lugar",
            "Se verificaran eventos activos o no cerrados antes de aplicar el cambio.",
            "Confirmar",
            lambda: ejecutar_estado_lugar(lugar, estado),
        )

    def ejecutar_estado_lugar(lugar: dict[str, Any], estado: str) -> None:
        resultado = cambiar_estado_lugar(
            supabase,
            contexto_usuario,
            lugar.get("lugar_id"),
            estado,
        )
        state["lugares_mensaje"] = resultado.mensaje
        cargar_lugares()

    def confirmar_estado_salon(salon: dict[str, Any], estado: str) -> None:
        mostrar_dialogo_confirmacion(
            f"{'Activar' if estado == 'Activo' else 'Desactivar'} salon",
            "Se verificaran eventos activos o no cerrados antes de aplicar el cambio.",
            "Confirmar",
            lambda: ejecutar_estado_salon(salon, estado),
        )

    def ejecutar_estado_salon(salon: dict[str, Any], estado: str) -> None:
        resultado = cambiar_estado_salon(
            supabase,
            contexto_usuario,
            salon.get("lugar_id"),
            salon.get("salon_id"),
            estado,
        )
        state["lugares_mensaje"] = resultado.mensaje
        if state.get("lugar_seleccionado"):
            cargar_salones(state["lugar_seleccionado"])

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
                if resultado.ok:
                    invalidar_dashboard()
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
                    invalidar_dashboard()
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
        navigate("guests")

    def cerrar_detalle_invitado() -> None:
        state["invitado_detalle"] = None
        state["invitado_form"] = None
        navigate("guests")

    def go_dashboard() -> None:
        state["selected"] = "dashboard"
        render()

    def cargar_eventos_admin(mensaje_exito: str = "") -> None:
        if checkin_mode or not puede_ver_administracion_eventos(contexto_usuario):
            state["eventos_admin_estado"] = "denied"
            render()
            return
        state["eventos_admin_estado"] = "loading"
        state["eventos_admin_mensaje"] = mensaje_exito or "Cargando eventos..."
        render()

        def worker() -> None:
            try:
                result = listar_eventos_administrables(
                    contexto_usuario,
                    contexto_usuario.get("cuenta_actual"),
                    supabase,
                )
                state["eventos_admin_items"] = result.eventos
                state["eventos_admin_estado"] = result.estado if result.ok else "error"
                state["eventos_admin_mensaje"] = mensaje_exito or result.mensaje
                if result.ok:
                    places = listar_lugares_disponibles(
                        contexto_usuario,
                        contexto_usuario.get("cuenta_actual"),
                        supabase,
                    )
                    rooms: list[dict[str, Any]] = []
                    for place in places:
                        rooms.extend(
                            listar_salones_disponibles(
                                contexto_usuario,
                                place.get("lug_lugar_id"),
                                contexto_usuario.get("cuenta_actual"),
                                supabase,
                            )
                        )
                    state["eventos_admin_lugares"] = places
                    state["eventos_admin_salones"] = rooms
            finally:
                render()

        page.run_thread(worker)

    def abrir_form_crear_evento() -> None:
        from views.eventos_admin_view import EventFormState
        state["eventos_admin_form"] = {
            "modo": "crear",
            "evento": {"tipo_evento": "Otro", "estado": "Activo"},
            "estado_form": EventFormState.desde_evento("crear"),
        }
        state["eventos_admin_form_message"] = ""
        state["eventos_admin_salones"] = []
        navigate("event_form", "nuevo")

    def abrir_form_editar_evento(evento: dict[str, Any]) -> None:
        from views.eventos_admin_view import EventFormState
        state["eventos_admin_form"] = {
            "modo": "editar",
            "evento": dict(evento),
            "estado_form": EventFormState.desde_evento("editar", evento),
        }
        state["eventos_admin_form_message"] = ""
        salon_id = evento.get("salon_id")
        cargar_salones_evento(evento.get("lugar_id"), renderizar=False)
        state["eventos_admin_form"]["estado_form"].salon_id = salon_id
        navigate("event_form", evento.get("evento_id"), "editar")

    def buscar_evento_admin(evento_id: Any) -> dict[str, Any] | None:
        try:
            target = int(evento_id)
        except (TypeError, ValueError):
            return None
        return next((item for item in state["eventos_admin_items"] if int(item.get("evento_id") or -1) == target), None)

    def abrir_detalle_evento(evento: dict[str, Any]) -> None:
        navigate("event_detail", evento.get("evento_id"))

    def cargar_salones_evento(lugar_id: Any, valores: dict[str, Any] | None = None, renderizar: bool = False) -> list[dict[str, Any]]:
        try:
            form = state.get("eventos_admin_form")
            if form and valores:
                form["estado_form"].actualizar(valores)
            state["eventos_admin_salones"] = listar_salones_disponibles(
                contexto_usuario,
                lugar_id,
                contexto_usuario.get("cuenta_actual"),
                supabase,
            )
            if form:
                form["estado_form"].lugar_id = lugar_id
                validos = {str(item.get("sal_salon_id")) for item in state["eventos_admin_salones"]}
                if form["estado_form"].salon_id is not None and str(form["estado_form"].salon_id) not in validos:
                    form["estado_form"].salon_id = None
        except Exception as ex:
            print("[EVENTOS_ADMIN][ERROR] cargar_salones", type(ex).__name__, str(ex))
            state["eventos_admin_salones"] = []
            state["eventos_admin_form_message"] = "No fue posible cargar los salones del lugar."
        if renderizar:
            render()
        return state["eventos_admin_salones"]

    def cancelar_form_evento() -> None:
        state["eventos_admin_form"] = None
        state["eventos_admin_form_message"] = ""
        navigate("events_admin")
        cargar_eventos_admin()

    def _sincronizar_evento_modificado(evento: dict[str, Any] | None) -> None:
        if not evento:
            return
        key = (evento.get("cuenta_id"), evento.get("evento_id"))
        state["eventos_admin_items"] = [
            dict(evento) if (item.get("cuenta_id"), item.get("evento_id")) == key else item
            for item in state["eventos_admin_items"]
        ]
        context_items = contexto_usuario.get("eventos_permitidos") or []
        found_context = False
        for index, item in enumerate(context_items):
            if (item.get("cuenta_id"), item.get("evento_id")) == key:
                context_items[index] = {**item, **evento}
                found_context = True
        if not found_context:
            role = (contexto_usuario.get("cuenta_actual") or {}).get("rol") or contexto_usuario.get("rol_global_calculado")
            context_items.append({**evento, "rol": role})
            contexto_usuario["eventos_permitidos"] = context_items
        found_dashboard = False
        for index, item in enumerate(state["eventos"]):
            if (item.get("cuenta_id"), item.get("evento_id")) == key:
                state["eventos"][index] = {**item, **evento}
                found_dashboard = True
        if not found_dashboard:
            state["eventos"].append({**evento, "rol": (contexto_usuario.get("cuenta_actual") or {}).get("rol")})
        if (
            (contexto_usuario.get("evento_actual") or {}).get("cuenta_id"),
            (contexto_usuario.get("evento_actual") or {}).get("evento_id"),
        ) == key:
            establecer_evento_activo(contexto_usuario, evento)
            reset_invitados()
            reset_llegadas()
        guardar_contexto_sesion(page.session.store, contexto_usuario)

    def guardar_form_evento(payload: dict[str, Any]) -> None:
        form = state.get("eventos_admin_form")
        if not form or state["eventos_admin_saving"]:
            if not form:
                state["eventos_admin_mensaje"] = "El formulario ya no esta disponible. Vuelve a abrirlo."
                render()
            return
        state["eventos_admin_saving"] = True
        state["eventos_admin_form_message"] = "Guardando..."
        print("[EVENTOS_ADMIN][INFO] Inicio de guardado:", f"modo={form.get('modo')}")
        render()

        def worker() -> None:
            try:
                if form["modo"] == "crear":
                    print("[EVENTOS_ADMIN][INFO] Llamando crear_evento.")
                    result = crear_evento(contexto_usuario, payload, contexto_usuario.get("cuenta_actual"), supabase)
                else:
                    original = form["evento"]
                    editable = {
                        key: value
                        for key, value in payload.items()
                        if key not in {"fase_evento", "estado"}
                    }
                    result = actualizar_evento(
                        contexto_usuario,
                        original.get("evento_id"),
                        editable,
                        contexto_usuario.get("cuenta_actual"),
                        supabase,
                    )
                print(
                    "[EVENTOS_ADMIN][INFO] Resultado de guardado:",
                    f"modo={form.get('modo')}",
                    f"estado={result.estado}",
                    f"ok={result.ok}",
                )
                _registrar_resultado_form_evento(state, result)
                if result.ok:
                    _sincronizar_evento_modificado(result.evento)
                    refreshed = listar_eventos_administrables(
                        contexto_usuario,
                        contexto_usuario.get("cuenta_actual"),
                        supabase,
                    )
                    if refreshed.ok:
                        state["eventos_admin_items"] = refreshed.eventos
                        state["eventos_admin_estado"] = refreshed.estado
                        state["eventos_admin_mensaje"] = result.mensaje
                    else:
                        state["eventos_admin_estado"] = "ready"
                        state["eventos_admin_mensaje"] = (
                            f"{result.mensaje} No fue posible recargar la lista: "
                            f"{refreshed.mensaje}"
                        )
                    navigate("events_admin")
                    return
            except Exception as ex:
                print(
                    "[EVENTOS_ADMIN][ERROR] Excepcion inesperada al guardar:",
                    type(ex).__name__,
                    str(ex),
                )
                message = "Ocurrio un error inesperado al guardar el evento. Intenta nuevamente."
                state["eventos_admin_form_message"] = message
                state["eventos_admin_mensaje"] = message
            finally:
                state["eventos_admin_saving"] = False
                render()

        page.run_thread(worker)

    def aplicar_filtros_eventos(filters: dict[str, str]) -> None:
        state["eventos_admin_filtros"] = filters
        render()

    def _ejecutar_accion_evento(action: Any, event: dict[str, Any], *args: Any) -> None:
        if state["eventos_admin_saving"]:
            return
        state["eventos_admin_saving"] = True
        state["eventos_admin_mensaje"] = "Procesando..."
        render()

        def worker() -> None:
            try:
                result = action(
                    contexto_usuario,
                    event.get("evento_id"),
                    *args,
                    contexto_usuario.get("cuenta_actual"),
                    supabase,
                )
                state["eventos_admin_mensaje"] = result.mensaje
                if result.ok:
                    _sincronizar_evento_modificado(result.evento)
                    if result.evento and result.evento.get("estado") != "Activo":
                        current = contexto_usuario.get("evento_actual") or {}
                        if (current.get("cuenta_id"), current.get("evento_id")) == (
                            result.evento.get("cuenta_id"),
                            result.evento.get("evento_id"),
                        ):
                            limpiar_evento_activo(contexto_usuario)
                            guardar_contexto_sesion(page.session.store, contexto_usuario)
            finally:
                state["eventos_admin_saving"] = False
                render()

        page.run_thread(worker)

    def solicitar_estado_evento(event: dict[str, Any], estado: str) -> None:
        mostrar_dialogo_confirmacion(
            f"{'Activar' if estado == 'Activo' else 'Desactivar'} evento",
            "Confirma el cambio de estado administrativo. Si es el evento activo, se limpiará la selección.",
            "Confirmar",
            lambda: _ejecutar_accion_evento(cambiar_estado_evento, event, estado),
        )

    def solicitar_inicio_evento(event: dict[str, Any]) -> None:
        mostrar_dialogo_confirmacion(
            "Iniciar evento",
            "El evento pasará a En_proceso y habilitará las operaciones de check-in autorizadas.",
            "Iniciar",
            lambda: _ejecutar_accion_evento(iniciar_evento, event),
        )

    def solicitar_cierre_evento(event: dict[str, Any]) -> None:
        mostrar_dialogo_confirmacion(
            "Cerrar evento",
            "El evento pasará a Post_evento y dejará de admitir nuevas llegadas.",
            "Cerrar",
            lambda: _ejecutar_accion_evento(cerrar_evento, event),
        )

    def hacer_evento_predeterminado(event: dict[str, Any]) -> None:
        _ejecutar_accion_evento(establecer_evento_predeterminado, event)

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
                        else:
                            state["selected"] = "dashboard"
                            state["dashboard_event_key"] = None
                            result_dashboard = obtener_indicadores_dashboard(contexto_usuario, supabase)
                            state["dashboard_estado"] = result_dashboard.estado if result_dashboard.ok else "error"
                            state["dashboard_mensaje"] = result_dashboard.mensaje
                            state["dashboard_indicadores"] = result_dashboard.indicadores
                            state["dashboard_event_key"] = evento_activo_key()
                            if result_dashboard.ok:
                                state["dashboard_ultima_actualizacion"] = _marca_actualizacion()
                    elif not resultado.eventos:
                        print("[EVENTOS][INFO] Consulta de eventos vacia.")
                    else:
                        print("[EVENTOS][INFO] Esperando seleccion explicita de evento.")
                        state["selected"] = "event_selection"
                else:
                    print("[EVENTOS][ERROR]", resultado.estado, resultado.mensaje)
            finally:
                state["eventos_loading"] = False
                render()

        page.run_thread(worker)

    async def select_event(evento: dict[str, Any]) -> None:
        try:
            asyncio.get_running_loop()
            loop_activo = True
        except RuntimeError:
            loop_activo = False
        print(
            "[EVENTOS][DEBUG] select_event",
            f"thread={threading.current_thread().name}",
            f"thread_id={threading.get_ident()}",
            f"loop_activo={loop_activo}",
        )
        requested_key = evento_key(evento)
        if requested_key is None or not es_evento_autorizado(state["eventos"], evento):
            state["eventos_estado"] = "error"
            state["eventos_mensaje"] = "No tiene acceso al evento seleccionado."
            render()
            return
        if checkin_mode:
            evento_activo = establecer_evento_activo(contexto_usuario, evento)
            contexto_usuario["evento_activo_seleccionado"] = True
            guardar_contexto_sesion(page.session.store, contexto_usuario)
            reset_invitados()
            reset_llegadas()
            invalidar_dashboard()
            state["selected"] = "arrivals"
            preparar_llegadas()
            print("[CHECKIN][INFO] Evento activo seleccionado:", *requested_key)
            render()
            return
        state["eventos_estado"] = "loading"
        state["eventos_mensaje"] = "Validando el evento seleccionado..."
        print("[EVENTOS][DEBUG] antes de page.update", f"loop_activo={loop_activo}")
        render()
        print("[EVENTOS][DEBUG] page.update completado")

        contexto_anterior = deepcopy(contexto_usuario)
        estado_anterior = {
            key: deepcopy(state[key])
            for key in (
                "selected", "dashboard_estado", "dashboard_mensaje", "dashboard_indicadores",
                "dashboard_event_key", "dashboard_ultima_actualizacion", "invitados_estado",
                "invitados", "invitados_mensaje", "arrivals_estado", "arrivals_mensaje",
                "excel_import_estado", "excel_import_mensaje", "excel_import_filename",
                "excel_import_size", "excel_import_preview", "excel_import_has_existing_data",
                "excel_import_importing", "excel_import_result",
            )
        }
        applied = False
        phase = "cargar_evento"
        try:
            def cargar_eventos_bloqueante() -> Any:
                print(
                    "[EVENTOS][DEBUG] consulta thread",
                    f"thread={threading.current_thread().name}",
                    f"thread_id={threading.get_ident()}",
                    "loop_activo=False",
                )
                return obtener_eventos_disponibles(contexto_usuario, supabase=supabase)

            print("[EVENTOS][DEBUG] consulta iniciada")
            resultado = await asyncio.to_thread(
                cargar_eventos_bloqueante,
            )
            print("[EVENTOS][DEBUG] consulta finalizada")
            if not resultado.ok:
                state["eventos_estado"] = "error"
                state["eventos_mensaje"] = "No fue posible cargar el evento seleccionado."
                print("[EVENTOS][ERROR] Seleccion no aplicada:", resultado.estado, resultado.mensaje)
                return
            evento_validado = buscar_evento_por_key(resultado.eventos, requested_key)
            if evento_validado is None:
                state["eventos_estado"] = "error"
                state["eventos_mensaje"] = "El evento seleccionado ya no está disponible."
                print("[EVENTOS][WARNING] Evento autorizado no disponible:", requested_key)
                return

            phase = "construir_contexto"
            contexto_nuevo = construir_contexto_evento_activo(
                contexto_anterior, resultado.eventos, requested_key,
            )
            phase = "cargar_dashboard"
            resultado_dashboard = await asyncio.to_thread(
                obtener_indicadores_dashboard, contexto_nuevo, supabase,
            )
            if not resultado_dashboard.ok:
                raise RuntimeError("No fue posible preparar el Dashboard del evento seleccionado.")
            phase = "aplicar_contexto"
            guardar_contexto_sesion(page.session.store, contexto_nuevo)
            contexto_usuario.clear()
            contexto_usuario.update(contexto_nuevo)
            applied = True
            state["eventos"] = resultado.eventos
            reset_invitados()
            reset_llegadas()
            invalidar_dashboard()
            state["excel_import_estado"] = "idle"
            state["excel_import_mensaje"] = ""
            state["excel_import_filename"] = ""
            state["excel_import_size"] = 0
            state["excel_import_preview"] = None
            state["excel_import_has_existing_data"] = None
            state["excel_import_importing"] = False
            state["excel_import_result"] = None
            state["eventos_estado"] = "ready"
            state["eventos_mensaje"] = "Evento seleccionado correctamente."
            state["selected"] = "dashboard"
            state["dashboard_estado"] = resultado_dashboard.estado
            state["dashboard_mensaje"] = resultado_dashboard.mensaje
            state["dashboard_indicadores"] = resultado_dashboard.indicadores
            state["dashboard_event_key"] = requested_key
            state["dashboard_ultima_actualizacion"] = _marca_actualizacion()
            print("[EVENTOS][INFO] Cambio de evento activo:", *requested_key)
            print("[EVENTOS][DEBUG] contexto aplicado")
            phase = "refrescar_controles"
            print("[EVENTOS][DEBUG] antes de page.update", "loop_activo=True")
            render()
            print("[EVENTOS][DEBUG] controles refrescados")
            print("[EVENTOS][DEBUG] page.update completado")
            try:
                page.show_dialog(ft.SnackBar(content=ft.Text("Evento seleccionado correctamente.")))
            except Exception as notification_error:
                print("[EVENTOS][WARNING] No se pudo mostrar confirmacion:", type(notification_error).__name__)
        except Exception as ex:
            if applied:
                contexto_usuario.clear()
                contexto_usuario.update(contexto_anterior)
                for key, value in estado_anterior.items():
                    state[key] = value
                try:
                    guardar_contexto_sesion(page.session.store, contexto_anterior)
                except Exception:
                    pass
            state["eventos_estado"] = "error"
            state["eventos_mensaje"] = "No fue posible cambiar de evento. Se mantuvo el evento anterior."
            state["selected"] = "event_selection"
            print(
                "[EVENTOS][ERROR] Cambio de evento no aplicado:",
                f"cuenta={requested_key[0]}", f"evento={requested_key[1]}",
                f"fase={phase}", type(ex).__name__, str(ex),
            )
            print("[EVENTOS][ERROR] traceback=", traceback.format_exc())
        finally:
            render()

    def select_tab(tab: str) -> None:
        if tab == "excel_import":
            navigate("excel_import")
            def verificar_vacio() -> None:
                has_data, message = consultar_evento_tiene_datos(contexto_usuario, supabase)
                state["excel_import_has_existing_data"] = has_data
                state["excel_import_mensaje"] = message
                state["excel_import_estado"] = "error" if has_data is not False else "idle"
                render()
            page.run_thread(verificar_vacio)
            return
        if tab == "dashboard":
            navigate("dashboard")
            cargar_dashboard()
            return
        if tab == "event_selection":
            state["selected"] = "event_selection"
            navigate("event_selection")
            if not state["eventos"]:
                cargar_eventos()
            return
        if tab == "events_admin":
            navigate("events_admin")
            cargar_eventos_admin()
            return
        if tab == "locations":
            if checkin_mode or not puede_administrar_lugares(contexto_usuario):
                navigate("locations")
                render()
                return
            navigate("locations")
            cargar_lugares()
            return
        if not (contexto_usuario.get("cuenta_actual") and contexto_usuario.get("evento_actual")):
            if tab == "guests":
                navigate("guests")
                cargar_invitados(reset=True)
                return
            navigate("dashboard")
            return

        if tab == "guests":
            navigate("guests")
            cargar_invitados(reset=True)
            return

        if tab == "arrivals" and not contexto_usuario.get("puede_registrar_llegadas"):
            navigate("arrivals")
            preparar_llegadas()
            render()
            return
        if tab == "arrivals":
            navigate("arrivals")
            preparar_llegadas()
            render()
            return
        if tab == "preferences":
            if checkin_mode:
                print("[CHECKIN][WARN] Operacion bloqueada en modo CHECKIN: preferencias")
                return
            print("[EVENTOS][INFO] Apertura de Preferencias desde menu de usuario.")
        navigate(tab)

    def cambiar_contexto_evento() -> None:
        print("[CHECKIN][INFO] Cambio de evento solicitado desde menu de usuario.")
        limpiar_evento_activo(contexto_usuario)
        contexto_usuario["evento_activo_seleccionado"] = False
        guardar_contexto_sesion(page.session.store, contexto_usuario)
        reset_invitados()
        reset_llegadas()
        state["selected"] = "event_selection"
        state["eventos_consulta_iniciada"] = False
        state["eventos_estado"] = "loading"
        state["eventos_mensaje"] = "Selecciona un evento para continuar."
        navigate("event_selection")
        cargar_eventos()

    def logout() -> None:
        print("[EVENTOS][INFO] Cierre de sesion solicitado desde menu de usuario.")
        _pausar_home()
        had_server_session = bool(
            session_controller is not None
            and session_controller.has_server_session
        )
        if session_controller is not None:
            logout_started = session_controller.logout()
            if not logout_started:
                return
        else:
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

        build_login_view(
            page,
            supabase,
            session_controller=session_controller,
        )
        page.update()
        if had_server_session and page.web:
            async def navigate_to_server_logout() -> None:
                await ft.UrlLauncher().launch_url(
                    "/session/logout",
                    web_only_window_name=ft.UrlTarget.SELF,
                )

            page.run_task(navigate_to_server_logout)

    configure_navigation_bar()
    home_control = build_shell()
    home_control.data = _home_callbacks()
    return home_control
