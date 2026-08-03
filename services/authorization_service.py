from __future__ import annotations

from dataclasses import dataclass
from typing import Any


ROL_MASTER = "Master"
ROL_ADMINISTRADOR = "Administrador"
ROL_OPERADOR = "Operador"
ROL_CONSULTA = "Consulta"

ROLES_CUENTA = frozenset({ROL_ADMINISTRADOR, ROL_OPERADOR, ROL_CONSULTA})
ROLES_VALIDOS = frozenset({ROL_MASTER, *ROLES_CUENTA})


@dataclass(frozen=True)
class Capacidades:
    puede_consultar: bool
    puede_administrar: bool
    puede_operar_evento: bool
    puede_registrar_llegada: bool
    puede_revertir_llegada: bool
    puede_crear_invitado: bool
    puede_editar_invitado: bool
    puede_eliminar_invitado: bool
    puede_registrar_imprevisto: bool
    puede_administrar_lugares: bool
    puede_crear_lugar: bool
    puede_editar_lugar: bool
    puede_desactivar_lugar: bool
    puede_crear_salon: bool
    puede_editar_salon: bool
    puede_desactivar_salon: bool
    puede_ver_administracion_eventos: bool
    puede_crear_evento: bool
    puede_editar_evento: bool
    puede_cambiar_ubicacion_evento: bool
    puede_activar_evento: bool
    puede_desactivar_evento: bool
    puede_iniciar_evento: bool
    puede_cerrar_evento: bool
    puede_establecer_evento_predeterminado: bool


_SIN_CAPACIDADES = Capacidades(
    False, False, False, False, False, False, False, False, False,
    False, False, False, False, False, False, False,
    False, False, False, False, False, False, False, False, False,
)
_CAPACIDADES_POR_ROL = {
    ROL_MASTER: Capacidades(
        True, True, True, True, True, True, True, True, True,
        True, True, True, True, True, True, True,
        True, True, True, True, True, True, True, True, True,
    ),
    ROL_ADMINISTRADOR: Capacidades(
        True, True, True, True, True, True, True, True, True,
        True, True, True, True, True, True, True,
        True, True, True, True, True, True, True, True, True,
    ),
    ROL_OPERADOR: Capacidades(
        True, False, True, True, True, False, False, True, True,
        False, False, False, False, False, False, False,
        False, False, False, False, False, False, False, False, False,
    ),
    ROL_CONSULTA: Capacidades(
        True, False, False, False, False, False, False, False, False,
        False, False, False, False, False, False, False,
        False, False, False, False, False, False, False, False, False,
    ),
}


def rol_cuenta_valido(rol: Any) -> bool:
    return isinstance(rol, str) and rol in ROLES_CUENTA


def rol_contexto(contexto: dict[str, Any] | None) -> str:
    if not contexto:
        return ""
    evento = contexto.get("evento_actual") or {}
    rol = str(evento.get("rol") or contexto.get("rol_global_calculado") or "")
    return rol if rol in ROLES_VALIDOS else ""


def capacidades_rol(rol: Any) -> Capacidades:
    return _CAPACIDADES_POR_ROL.get(str(rol or ""), _SIN_CAPACIDADES)


def capacidades_contexto(contexto: dict[str, Any] | None) -> Capacidades:
    return capacidades_rol(rol_contexto(contexto))


def evento_autorizado(contexto: dict[str, Any] | None) -> bool:
    if not contexto:
        return False
    evento_actual = contexto.get("evento_actual") or {}
    try:
        key = (int(evento_actual["cuenta_id"]), int(evento_actual["evento_id"]))
    except (KeyError, TypeError, ValueError):
        return False
    for evento in contexto.get("eventos_permitidos", []) or []:
        try:
            if (int(evento["cuenta_id"]), int(evento["evento_id"])) == key:
                return True
        except (KeyError, TypeError, ValueError):
            continue
    return False


def evento_operativo(contexto: dict[str, Any] | None) -> bool:
    if not contexto or not contexto.get("usr_usuario_id") or not evento_autorizado(contexto):
        return False
    evento = contexto.get("evento_actual") or {}
    return evento.get("fase_evento") == "En_proceso" and evento.get("estado") == "Activo"


def puede_consultar(contexto: dict[str, Any] | None) -> bool:
    return bool(
        contexto
        and contexto.get("usr_usuario_id")
        and capacidades_contexto(contexto).puede_consultar
        and evento_autorizado(contexto)
    )


def puede_administrar(contexto: dict[str, Any] | None) -> bool:
    return capacidades_contexto(contexto).puede_administrar


def puede_operar_evento(contexto: dict[str, Any] | None) -> bool:
    return capacidades_contexto(contexto).puede_operar_evento and evento_operativo(contexto)


def puede_registrar_llegada(contexto: dict[str, Any] | None) -> bool:
    return capacidades_contexto(contexto).puede_registrar_llegada and evento_operativo(contexto)


def puede_revertir_llegada(contexto: dict[str, Any] | None) -> bool:
    return capacidades_contexto(contexto).puede_revertir_llegada and evento_operativo(contexto)


def puede_crear_invitado(contexto: dict[str, Any] | None) -> bool:
    return capacidades_contexto(contexto).puede_crear_invitado


def puede_editar_invitado(contexto: dict[str, Any] | None) -> bool:
    return capacidades_contexto(contexto).puede_editar_invitado


def puede_eliminar_invitado(contexto: dict[str, Any] | None) -> bool:
    return capacidades_contexto(contexto).puede_eliminar_invitado


def puede_registrar_imprevisto(contexto: dict[str, Any] | None) -> bool:
    return capacidades_contexto(contexto).puede_registrar_imprevisto and evento_operativo(contexto)


def puede_administrar_lugares(contexto: dict[str, Any] | None) -> bool:
    return capacidades_contexto(contexto).puede_administrar_lugares


def puede_crear_lugar(contexto: dict[str, Any] | None) -> bool:
    return capacidades_contexto(contexto).puede_crear_lugar


def puede_editar_lugar(contexto: dict[str, Any] | None) -> bool:
    return capacidades_contexto(contexto).puede_editar_lugar


def puede_desactivar_lugar(contexto: dict[str, Any] | None) -> bool:
    return capacidades_contexto(contexto).puede_desactivar_lugar


def puede_crear_salon(contexto: dict[str, Any] | None) -> bool:
    return capacidades_contexto(contexto).puede_crear_salon


def puede_editar_salon(contexto: dict[str, Any] | None) -> bool:
    return capacidades_contexto(contexto).puede_editar_salon


def puede_desactivar_salon(contexto: dict[str, Any] | None) -> bool:
    return capacidades_contexto(contexto).puede_desactivar_salon


def puede_ver_administracion_eventos(contexto: dict[str, Any] | None) -> bool:
    return capacidades_contexto(contexto).puede_ver_administracion_eventos


def puede_crear_evento(contexto: dict[str, Any] | None) -> bool:
    return capacidades_contexto(contexto).puede_crear_evento


def puede_editar_evento(contexto: dict[str, Any] | None) -> bool:
    return capacidades_contexto(contexto).puede_editar_evento


def puede_cambiar_ubicacion_evento(contexto: dict[str, Any] | None) -> bool:
    return capacidades_contexto(contexto).puede_cambiar_ubicacion_evento


def puede_activar_evento(contexto: dict[str, Any] | None) -> bool:
    return capacidades_contexto(contexto).puede_activar_evento


def puede_desactivar_evento(contexto: dict[str, Any] | None) -> bool:
    return capacidades_contexto(contexto).puede_desactivar_evento


def puede_iniciar_evento(contexto: dict[str, Any] | None) -> bool:
    return capacidades_contexto(contexto).puede_iniciar_evento


def puede_cerrar_evento(contexto: dict[str, Any] | None) -> bool:
    return capacidades_contexto(contexto).puede_cerrar_evento


def puede_establecer_evento_predeterminado(contexto: dict[str, Any] | None) -> bool:
    return capacidades_contexto(contexto).puede_establecer_evento_predeterminado


def resumen_capacidades(contexto: dict[str, Any] | None) -> dict[str, bool]:
    capacidades = capacidades_contexto(contexto)
    return {
        campo: bool(getattr(capacidades, campo))
        for campo in capacidades.__dataclass_fields__
    }
