from __future__ import annotations

from copy import deepcopy
from typing import Any

from services.authorization_service import capacidades_contexto, resumen_capacidades

EVENTOS_DISPONIBLES_SESSION_KEY = "eventos_disponibles"
USUARIO_CONTEXTO_SESSION_KEY = "usuario_contexto"


def evento_key(evento: dict[str, Any] | None) -> tuple[int, int] | None:
    if not evento:
        return None
    try:
        return int(evento["cuenta_id"]), int(evento["evento_id"])
    except (KeyError, TypeError, ValueError):
        return None


def buscar_evento_por_key(
    eventos: list[dict[str, Any]],
    key: tuple[int, int] | None,
) -> dict[str, Any] | None:
    if key is None:
        return None
    for evento in eventos:
        if evento_key(evento) == key:
            return evento
    return None


def es_evento_autorizado(
    eventos: list[dict[str, Any]],
    evento: dict[str, Any] | None,
) -> bool:
    key = evento_key(evento)
    return key is not None and buscar_evento_por_key(eventos, key) is not None


def establecer_evento_activo(
    contexto: dict[str, Any],
    evento: dict[str, Any],
) -> dict[str, Any]:
    evento_activo = dict(evento)
    contexto["evento_actual"] = evento_activo

    cuenta_id = evento_activo.get("cuenta_id")
    for cuenta in contexto.get("cuentas_permitidas", []) or []:
        if cuenta.get("cuenta_id") == cuenta_id:
            contexto["cuenta_actual"] = cuenta
            break

    capacidades = capacidades_contexto(contexto)
    contexto["puede_registrar_llegadas"] = bool(
        capacidades.puede_registrar_llegada
        and evento_activo.get("fase_evento") == "En_proceso"
        and evento_activo.get("estado") == "Activo"
    )
    contexto["puede_administrar_usuarios"] = capacidades.puede_administrar
    contexto["capacidades"] = resumen_capacidades(contexto)
    return evento_activo


def construir_contexto_evento_activo(
    contexto: dict[str, Any],
    eventos_validados: list[dict[str, Any]],
    key: tuple[int, int],
) -> dict[str, Any]:
    """Construye un contexto independiente; no muta el contexto vigente."""
    evento = buscar_evento_por_key(eventos_validados, key)
    if evento is None:
        raise LookupError("El evento seleccionado no está disponible.")
    nuevo = deepcopy(contexto)
    establecer_evento_activo(nuevo, evento)
    nuevo["evento_activo_seleccionado"] = True
    return nuevo


def limpiar_evento_activo(contexto: dict[str, Any]) -> None:
    contexto["evento_actual"] = None
    contexto["puede_registrar_llegadas"] = False
    contexto["capacidades"] = resumen_capacidades(contexto)


def sincronizar_evento_activo(
    contexto: dict[str, Any],
    eventos_disponibles: list[dict[str, Any]],
) -> dict[str, Any] | None:
    actual = buscar_evento_por_key(eventos_disponibles, evento_key(contexto.get("evento_actual")))
    if actual:
        return establecer_evento_activo(contexto, actual)

    limpiar_evento_activo(contexto)
    if len(eventos_disponibles) == 1:
        print("[EVENTOS][INFO] Un solo evento disponible; se establece como evento activo.")
        return establecer_evento_activo(contexto, eventos_disponibles[0])

    return None


def guardar_contexto_sesion(session_store: Any, contexto: dict[str, Any]) -> None:
    session_store.set(USUARIO_CONTEXTO_SESSION_KEY, contexto)


def guardar_eventos_disponibles(session_store: Any, eventos: list[dict[str, Any]]) -> None:
    session_store.set(EVENTOS_DISPONIBLES_SESSION_KEY, eventos)


def limpiar_contexto_sesion(session_store: Any) -> None:
    for key in (
        USUARIO_CONTEXTO_SESSION_KEY,
        EVENTOS_DISPONIBLES_SESSION_KEY,
        "diagnostico_login",
    ):
        try:
            session_store.remove(key)
        except Exception:
            pass
