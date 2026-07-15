from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from db import get_supabase_client
from services.evento_context_service import evento_key
from services.response_utils import extract_data, safe_get, to_dict


SELECT_EVENTO = (
    "eve_cuenta_id,"
    "eve_evento_id,"
    "eve_nombre_evento,"
    "eve_nombre_evento_abrev,"
    "eve_fase_evento,"
    "eve_lugar_id,"
    "eve_salon_id,"
    "eve_fecha_hora_inicio,"
    "eve_fecha_hora_fin,"
    "eve_estado"
)


@dataclass(frozen=True)
class ResultadoEventos:
    ok: bool
    estado: str
    mensaje: str
    eventos: list[dict[str, Any]]


class EventoServiceError(RuntimeError):
    """Error controlado al consultar eventos disponibles."""


def _normalizar_id(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _fecha_panama_legible(value: Any) -> str | None:
    if not value:
        return None
    texto = str(value)
    try:
        normalizado = texto.replace("Z", "+00:00")
        fecha = datetime.fromisoformat(normalizado)
        return fecha.strftime("%d/%m/%Y %I:%M %p")
    except ValueError:
        return texto


def normalizar_evento(
    row: dict[str, Any],
    contexto_evento: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    cuenta_id = _normalizar_id(safe_get(row, "eve_cuenta_id"))
    evento_id = _normalizar_id(safe_get(row, "eve_evento_id"))
    if cuenta_id is None or evento_id is None:
        return None

    contexto_evento = contexto_evento or {}
    rol = safe_get(contexto_evento, "rol", "Sin rol")
    nombre = safe_get(row, "eve_nombre_evento", f"Evento {evento_id}")
    inicio = safe_get(row, "eve_fecha_hora_inicio")

    return {
        "cuenta_id": cuenta_id,
        "evento_id": evento_id,
        "nombre_evento": nombre,
        "nombre_evento_abrev": safe_get(row, "eve_nombre_evento_abrev"),
        "fase_evento": safe_get(row, "eve_fase_evento"),
        "estado": safe_get(row, "eve_estado"),
        "fecha_hora_inicio": inicio,
        "fecha_hora_inicio_legible": _fecha_panama_legible(inicio),
        "fecha_hora_fin": safe_get(row, "eve_fecha_hora_fin"),
        "lugar_id": _normalizar_id(safe_get(row, "eve_lugar_id")),
        "salon_id": _normalizar_id(safe_get(row, "eve_salon_id")),
        "rol": rol,
    }


def _extraer_primera_fila(response: Any) -> dict[str, Any] | None:
    data = extract_data(response)
    if not data:
        return None
    return to_dict(data[0])


def _consultar_evento(
    supabase: Any,
    cuenta_id: int,
    evento_id: int,
) -> dict[str, Any] | None:
    response = (
        supabase
        .table("evp_eve_evento")
        .select(SELECT_EVENTO)
        .eq("eve_cuenta_id", cuenta_id)
        .eq("eve_evento_id", evento_id)
        .limit(1)
        .execute()
    )
    return _extraer_primera_fila(response)


def obtener_eventos_disponibles(
    contexto_usuario: dict[str, Any] | None,
    supabase: Any = None,
) -> ResultadoEventos:
    if not contexto_usuario or not contexto_usuario.get("usr_usuario_id"):
        print("[EVENTOS][WARNING] Sesion no valida al consultar eventos.")
        return ResultadoEventos(
            ok=False,
            estado="session_invalid",
            mensaje="La sesion no es valida. Inicia sesion nuevamente.",
            eventos=[],
        )

    eventos_contexto = contexto_usuario.get("eventos_permitidos") or []
    if not eventos_contexto:
        print("[EVENTOS][INFO] Consulta sin eventos permitidos en contexto.")
        return ResultadoEventos(
            ok=True,
            estado="empty",
            mensaje="No tienes eventos disponibles en este momento.",
            eventos=[],
        )

    supabase = supabase or get_supabase_client()
    print(
        "[EVENTOS][INFO] Consultando eventos disponibles para usuario:",
        contexto_usuario.get("usr_usuario_id"),
    )

    eventos: list[dict[str, Any]] = []
    vistos: set[tuple[int, int]] = set()
    try:
        for contexto_evento in eventos_contexto:
            key = evento_key(contexto_evento)
            if key is None or key in vistos:
                continue
            vistos.add(key)
            row = _consultar_evento(supabase, key[0], key[1])
            if not row:
                continue
            evento = normalizar_evento(row, contexto_evento)
            if evento:
                eventos.append(evento)
    except EventoServiceError:
        raise
    except Exception as ex:
        print("[EVENTOS][ERROR] Error al consultar eventos:", type(ex).__name__, str(ex))
        return ResultadoEventos(
            ok=False,
            estado="connection_error",
            mensaje="No fue posible cargar los eventos. Verifica la conexion e intentalo nuevamente.",
            eventos=[],
        )

    eventos.sort(key=lambda item: (item["cuenta_id"], item["evento_id"]))
    print("[EVENTOS][INFO] Eventos obtenidos:", len(eventos))

    if not eventos:
        return ResultadoEventos(
            ok=True,
            estado="empty",
            mensaje="No tienes eventos disponibles en este momento.",
            eventos=[],
        )

    return ResultadoEventos(
        ok=True,
        estado="ready",
        mensaje="Eventos cargados correctamente.",
        eventos=eventos,
    )
