from __future__ import annotations

from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import flet as ft

from components.bottom_navigation import bottom_navigation
from services import usuario_service
from services.authorization_service import (
    capacidades_rol,
    evento_autorizado,
    puede_consultar,
    puede_registrar_llegada,
    ROL_ADMINISTRADOR,
    ROL_CONSULTA,
    ROL_MASTER,
    ROL_OPERADOR,
)
from services.invitado_service import (
    actualizar_invitado_planificado,
    confirmar_llegada,
    confirmar_llegadas_invitados,
    crear_invitado_imprevisto,
    crear_invitado_planificado,
    eliminar_invitado_imprevisto,
    reversar_llegada,
)
from views.invitados_view import invitados_view


USUARIO = {
    "usr_usuario_id": "consulta-1",
    "usr_usuario_auth_uuid": "auth-consulta",
    "usr_nombre_usuario": "Usuario Consulta",
    "usr_nombre_usuario_abrev": "UC",
    "usr_email": "consulta@example.com",
    "usr_es_usuario_master": False,
    "usr_estado": "Activo",
    "usr_cuenta_id_default": 1,
    "usr_evento_id_default": 10,
}
CUENTA = {"cuenta_id": 1, "nombre_cuenta": "Cuenta 1", "estado": "Activo", "rol": ROL_CONSULTA}
EVENTO = {
    "cuenta_id": 1,
    "evento_id": 10,
    "nombre_evento": "Evento asignado",
    "fase_evento": "En_proceso",
    "estado": "Activo",
    "rol": ROL_CONSULTA,
}
INVITADO = {
    "cuenta_id": 1,
    "evento_id": 10,
    "invitacion_id": 100,
    "invitado_id": 1,
    "invitado_uuid": "ivt-1",
    "nombre_completo": "Ana Consulta",
    "es_invitado_imprevisto": False,
    "llegada_confirmada": False,
}
PAYLOAD = {
    "nombre_completo": "Intento Escritura",
    "invitacion_id": 100,
    "cuenta_id": 999,
    "evento_id": 999,
}


class NoWriteSupabase:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def table(self, name: str) -> Any:
        self.calls.append(f"table:{name}")
        raise AssertionError("Consulta fue autorizado a alcanzar el backend de escritura")


def contexto_consulta() -> dict[str, Any]:
    return {
        **USUARIO,
        "rol_global_calculado": ROL_CONSULTA,
        "cuentas_permitidas": [dict(CUENTA)],
        "eventos_permitidos": [dict(EVENTO)],
        "cuenta_actual": dict(CUENTA),
        "evento_actual": dict(EVENTO),
        "puede_registrar_llegadas": False,
        "puede_administrar_usuarios": False,
    }


def _patch_temporal(reemplazos: dict[str, Any]) -> dict[str, Any]:
    originales = {}
    for nombre, valor in reemplazos.items():
        originales[nombre] = getattr(usuario_service, nombre)
        setattr(usuario_service, nombre, valor)
    return originales


def _restaurar(originales: dict[str, Any]) -> None:
    for nombre, valor in originales.items():
        setattr(usuario_service, nombre, valor)


def test_contexto_y_alcance_asignado() -> None:
    llamadas = {"todos_eventos": 0, "asignados": 0}

    def todos_eventos(*args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        llamadas["todos_eventos"] += 1
        return [{**EVENTO, "evento_id": 99}]

    def asignados(*args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        llamadas["asignados"] += 1
        assert args[3] == ROL_CONSULTA
        return [dict(EVENTO)]

    originales = _patch_temporal(
        {
            "buscar_usuario_eventplus_por_auth_uuid": lambda *args: dict(USUARIO),
            "_consultar_cuentas_vinculadas": lambda *args: [dict(CUENTA)],
            "_consultar_eventos_por_cuenta": todos_eventos,
            "_consultar_eventos_asignados": asignados,
        }
    )
    try:
        contexto = usuario_service.cargar_contexto_usuario(object(), "auth-consulta")
    finally:
        _restaurar(originales)

    assert contexto["rol_global_calculado"] == ROL_CONSULTA
    assert contexto["cuentas_permitidas"] == [CUENTA]
    assert [e["evento_id"] for e in contexto["eventos_permitidos"]] == [10]
    assert llamadas == {"todos_eventos": 0, "asignados": 1}
    assert contexto["puede_registrar_llegadas"] is False
    assert contexto["capacidades"]["puede_consultar"] is True
    assert contexto["capacidades"]["puede_operar_evento"] is False


def test_capacidades_y_roles_existentes() -> None:
    consulta = contexto_consulta()
    assert puede_consultar(consulta)
    assert evento_autorizado(consulta)
    assert not puede_registrar_llegada(consulta)

    cap_consulta = capacidades_rol(ROL_CONSULTA)
    assert cap_consulta.puede_consultar
    assert not any(
        getattr(cap_consulta, nombre)
        for nombre in cap_consulta.__dataclass_fields__
        if nombre != "puede_consultar"
    )
    assert capacidades_rol(ROL_ADMINISTRADOR).puede_administrar
    assert capacidades_rol(ROL_ADMINISTRADOR).puede_registrar_llegada
    assert capacidades_rol(ROL_OPERADOR).puede_operar_evento
    assert capacidades_rol(ROL_OPERADOR).puede_registrar_llegada
    assert not capacidades_rol(ROL_OPERADOR).puede_administrar
    assert capacidades_rol(ROL_MASTER).puede_administrar
    assert capacidades_rol(ROL_MASTER).puede_registrar_llegada


def test_escrituras_denegadas_antes_del_backend() -> None:
    contexto = contexto_consulta()
    db = NoWriteSupabase()
    operaciones = [
        crear_invitado_planificado(contexto, PAYLOAD, supabase=db),
        actualizar_invitado_planificado(contexto, INVITADO, PAYLOAD, supabase=db),
        confirmar_llegada(contexto, INVITADO, supabase=db),
        confirmar_llegadas_invitados(
            contexto,
            {"cuenta_id": 1, "evento_id": 10, "invitacion_id": 100},
            [INVITADO],
            supabase=db,
        ),
        reversar_llegada(contexto, INVITADO, supabase=db),
        crear_invitado_imprevisto(contexto, PAYLOAD, supabase=db),
        eliminar_invitado_imprevisto(contexto, INVITADO, supabase=db),
    ]
    assert all(not resultado.ok and resultado.estado == "role_denied" for resultado in operaciones)
    assert db.calls == []

    alterado = contexto_consulta()
    alterado["evento_actual"] = {**EVENTO, "cuenta_id": 999, "evento_id": 999}
    resultado = confirmar_llegada(alterado, {**INVITADO, "cuenta_id": 999, "evento_id": 999}, supabase=db)
    assert not resultado.ok and resultado.estado == "event_not_allowed"
    assert db.calls == []


def _walk(control: Any) -> list[Any]:
    encontrados = [control]
    for attr in ("controls", "destinations"):
        for child in getattr(control, attr, None) or []:
            encontrados.extend(_walk(child))
    for attr in ("content", "leading", "trailing"):
        child = getattr(control, attr, None)
        if child is not None and not isinstance(child, (str, int, float, bool)):
            encontrados.extend(_walk(child))
    return encontrados


def test_interfaz_solo_lectura() -> None:
    nav = bottom_navigation("guests", True, False, lambda key: None)
    labels = [destino.label for destino in nav.destinations]
    assert "Dashboard" in labels and "Invitados" in labels
    assert "Registrar llegadas" not in labels

    vista = invitados_view(
        contexto=contexto_consulta(),
        estado="ready",
        mensaje="",
        busqueda="",
        tipo_busqueda="invitado",
        filtro="todos",
        invitados=[dict(INVITADO)],
        has_more=False,
        invitado_detalle=dict(INVITADO),
        invitaciones=[],
        form_state=None,
        can_manage_planned=False,
        can_confirm_arrival=False,
        can_reverse_arrival=False,
        can_manage_unexpected=False,
        can_delete_unexpected=False,
        is_loading=False,
        is_saving=False,
        form_message="",
        on_search=lambda *args: None,
        on_clear=lambda: None,
        on_filter=lambda value: None,
        on_search_type_change=lambda value: None,
        on_load_more=lambda: None,
        on_detail=lambda item: None,
        on_close_detail=lambda: None,
        on_go_dashboard=lambda: None,
        on_new_guest=lambda: None,
        on_new_unexpected_guest=lambda: None,
        on_edit_guest=lambda item: None,
        on_confirm_arrival=lambda item: None,
        on_reverse_arrival=lambda item: None,
        on_delete_unexpected=lambda item: None,
        on_save_guest=lambda payload: None,
        on_cancel_form=lambda: None,
        on_retry=lambda: None,
    )
    controles = _walk(vista)
    botones = [
        str(getattr(control, "content", ""))
        for control in controles
        if isinstance(control, (ft.Button, ft.OutlinedButton, ft.FilledTonalButton))
    ]
    prohibidos = {"Agregar invitado", "Editar", "Eliminar", "Confirmar llegada", "Revertir", "Registrar imprevisto"}
    assert not prohibidos.intersection(botones)
    assert any(
        isinstance(control, ft.Text) and control.value == "Ana Consulta"
        for control in controles
    )


def test_rol_desconocido_rechazado() -> None:
    cuenta_invalida = {**CUENTA, "rol": "Supervisor"}
    originales = _patch_temporal(
        {
            "buscar_usuario_eventplus_por_auth_uuid": lambda *args: dict(USUARIO),
            "_consultar_cuentas_vinculadas": lambda *args: [cuenta_invalida],
        }
    )
    try:
        try:
            usuario_service.cargar_contexto_usuario(object(), "auth-consulta")
        except usuario_service.UsuarioContextoError as ex:
            assert "rol no reconocido" in str(ex)
        else:
            raise AssertionError("El rol desconocido no fue rechazado")
    finally:
        _restaurar(originales)


def main() -> int:
    test_contexto_y_alcance_asignado()
    test_capacidades_y_roles_existentes()
    test_escrituras_denegadas_antes_del_backend()
    test_interfaz_solo_lectura()
    test_rol_desconocido_rechazado()
    print("OK - rol Consulta: contexto, alcance, capacidades, backend, UI y rechazo de roles.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
