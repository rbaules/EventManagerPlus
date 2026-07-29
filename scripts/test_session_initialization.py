from __future__ import annotations

import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import services.usuario_service as usuario_service
from services.usuario_service import UsuarioContextoError, cargar_contexto_usuario


USUARIO = {
    "usr_usuario_id": "user-1",
    "usr_usuario_auth_uuid": "auth-1",
    "usr_nombre_usuario": "Usuario Demo",
    "usr_nombre_usuario_abrev": "UD",
    "usr_email": "usuario@example.com",
    "usr_es_usuario_master": False,
    "usr_cuenta_id_default": None,
    "usr_evento_id_default": None,
    "usr_estado": "Activo",
}

CUENTA_1 = {
    "cuenta_id": 1,
    "nombre_cuenta": "Cuenta Uno",
    "nombre_cuenta_abrev": "C1",
    "estado": "Activo",
    "rol": "Administrador",
}

CUENTA_2 = {
    "cuenta_id": 2,
    "nombre_cuenta": "Cuenta Dos",
    "nombre_cuenta_abrev": "C2",
    "estado": "Activo",
    "rol": "Consulta",
}

EVENTO_1 = {
    "cuenta_id": 1,
    "evento_id": 10,
    "nombre_evento": "Evento Uno",
    "fase_evento": "Pre_evento",
    "estado": "Activo",
    "rol": "Administrador",
}

EVENTO_2 = {
    "cuenta_id": 1,
    "evento_id": 11,
    "nombre_evento": "Evento Dos",
    "fase_evento": "En_proceso",
    "estado": "Activo",
    "rol": "Administrador",
}


def patch(monkeypatches: dict[str, Any]) -> dict[str, Any]:
    originals = {}
    for name, value in monkeypatches.items():
        originals[name] = getattr(usuario_service, name)
        setattr(usuario_service, name, value)
    return originals


def restore(originals: dict[str, Any]) -> None:
    for name, value in originals.items():
        setattr(usuario_service, name, value)


def run_with(cuentas: list[dict[str, Any]], eventos_por_cuenta: dict[int, list[dict[str, Any]]]) -> dict[str, Any]:
    supabase = object()
    originals = patch(
        {
            "buscar_usuario_eventplus_por_auth_uuid": lambda client, auth: dict(USUARIO),
            "_consultar_cuentas_vinculadas": lambda client, user_id: list(cuentas),
            "_consultar_eventos_por_cuenta": lambda client, cuenta_id, rol: [
                dict(evento, rol=rol) for evento in eventos_por_cuenta.get(cuenta_id, [])
            ],
            "_consultar_eventos_asignados": (
                lambda client, user_id, cuenta_id, rol: [
                    dict(evento, rol=rol)
                    for evento in eventos_por_cuenta.get(cuenta_id, [])
                ]
            ),
        }
    )
    try:
        return cargar_contexto_usuario(supabase, "auth-1")
    finally:
        restore(originals)


def test_usuario_con_cuenta_sin_eventos_no_falla() -> None:
    contexto = run_with([CUENTA_1], {1: []})
    assert len(contexto["cuentas_permitidas"]) == 1
    assert contexto["eventos_permitidos"] == []
    assert contexto["cuenta_actual"]["cuenta_id"] == 1
    assert contexto["evento_actual"] is None
    assert contexto["puede_registrar_llegadas"] is False


def test_usuario_con_una_cuenta_y_varios_eventos() -> None:
    contexto = run_with([CUENTA_1], {1: [EVENTO_1, EVENTO_2]})
    assert len(contexto["eventos_permitidos"]) == 2
    assert contexto["cuenta_actual"]["cuenta_id"] == 1
    assert contexto["evento_actual"]["evento_id"] == 10


def test_usuario_con_varias_cuentas_y_eventos_parciales() -> None:
    contexto = run_with([CUENTA_1, CUENTA_2], {1: [EVENTO_1, EVENTO_2], 2: []})
    assert len(contexto["cuentas_permitidas"]) == 2
    assert len(contexto["eventos_permitidos"]) == 2
    assert contexto["cuenta_actual"]["cuenta_id"] == 1


def test_error_al_cargar_cuentas_es_controlado() -> None:
    originals = patch(
        {
            "buscar_usuario_eventplus_por_auth_uuid": lambda client, auth: dict(USUARIO),
            "_consultar_cuentas_vinculadas": lambda client, user_id: (_ for _ in ()).throw(RuntimeError("permission denied")),
        }
    )
    try:
        try:
            cargar_contexto_usuario(object(), "auth-1")
        except UsuarioContextoError as ex:
            assert "cuentas disponibles" in str(ex)
        else:
            raise AssertionError("Se esperaba UsuarioContextoError.")
    finally:
        restore(originals)


def test_error_al_cargar_eventos_es_controlado() -> None:
    originals = patch(
        {
            "buscar_usuario_eventplus_por_auth_uuid": lambda client, auth: dict(USUARIO),
            "_consultar_cuentas_vinculadas": lambda client, user_id: [CUENTA_1],
            "_consultar_eventos_por_cuenta": lambda client, cuenta_id, rol: (_ for _ in ()).throw(RuntimeError("network down")),
        }
    )
    try:
        try:
            cargar_contexto_usuario(object(), "auth-1")
        except UsuarioContextoError as ex:
            assert "eventos disponibles" in str(ex)
        else:
            raise AssertionError("Se esperaba UsuarioContextoError.")
    finally:
        restore(originals)


def main() -> int:
    test_usuario_con_cuenta_sin_eventos_no_falla()
    test_usuario_con_una_cuenta_y_varios_eventos()
    test_usuario_con_varias_cuentas_y_eventos_parciales()
    test_error_al_cargar_cuentas_es_controlado()
    test_error_al_cargar_eventos_es_controlado()
    print("OK - session initialization handles zero, one, and multiple events with controlled errors.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
