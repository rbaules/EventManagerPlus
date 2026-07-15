from __future__ import annotations

from dataclasses import dataclass
import unicodedata
from typing import Any

from db import get_supabase_client
from services.evento_context_service import evento_key
from services.response_utils import extract_data, safe_get, to_dict


INVITADOS_PAGE_SIZE = 50

SELECT_INVITADO = (
    "ivt_cuenta_id,"
    "ivt_evento_id,"
    "ivt_invitacion_id,"
    "ivt_invitado_id,"
    "ivt_invitado_uuid,"
    "ivt_nombre_invitado,"
    "ivt_es_invitado_principal,"
    "ivt_es_invitado_imprevisto,"
    "ivt_email,"
    "ivt_telefono,"
    "ivt_mesa_id,"
    "ivt_puesto_id,"
    "ivt_llegada_confirmada,"
    "ivt_fecha_hora_conf_llegada,"
    "ivt_tiene_novedad,"
    "ivt_descripcion_novedad,"
    "ivt_estado"
)

FILTROS_INVITADOS = {
    "todos",
    "llegaron",
    "pendientes",
    "con_mesa",
    "sin_mesa",
    "previstos",
    "imprevistos",
}


@dataclass(frozen=True)
class ResultadoInvitados:
    ok: bool
    estado: str
    mensaje: str
    invitados: list[dict[str, Any]]
    total_recibidos: int
    limit: int
    offset: int
    has_more: bool


@dataclass(frozen=True)
class ResultadoInvitadoDetalle:
    ok: bool
    estado: str
    mensaje: str
    invitado: dict[str, Any] | None


def _normalizar_id(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _normalizar_bool(value: Any) -> bool:
    return bool(value) if value is not None else False


def _texto(value: Any) -> str:
    return str(value).strip() if value not in (None, "") else ""


def _normalizar_busqueda(value: str | None) -> str:
    texto = _texto(value).lower()
    texto = " ".join(texto.split())
    texto = unicodedata.normalize("NFKD", texto)
    return "".join(char for char in texto if not unicodedata.combining(char))


def _estado_llegada(confirmada: bool) -> str:
    return "Llegada confirmada" if confirmada else "Pendiente de llegada"


def normalizar_invitado(row: dict[str, Any]) -> dict[str, Any] | None:
    cuenta_id = _normalizar_id(safe_get(row, "ivt_cuenta_id"))
    evento_id = _normalizar_id(safe_get(row, "ivt_evento_id"))
    invitacion_id = _normalizar_id(safe_get(row, "ivt_invitacion_id"))
    invitado_id = _normalizar_id(safe_get(row, "ivt_invitado_id"))
    invitado_uuid = _texto(safe_get(row, "ivt_invitado_uuid"))
    nombre = _texto(safe_get(row, "ivt_nombre_invitado"))

    if None in (cuenta_id, evento_id, invitacion_id, invitado_id) or not invitado_uuid:
        return None

    llegada_confirmada = _normalizar_bool(safe_get(row, "ivt_llegada_confirmada"))
    es_imprevisto = _normalizar_bool(safe_get(row, "ivt_es_invitado_imprevisto"))
    es_principal = _normalizar_bool(safe_get(row, "ivt_es_invitado_principal"))
    mesa_id = _normalizar_id(safe_get(row, "ivt_mesa_id"))
    puesto_id = _normalizar_id(safe_get(row, "ivt_puesto_id"))

    return {
        "cuenta_id": cuenta_id,
        "evento_id": evento_id,
        "invitacion_id": invitacion_id,
        "invitado_id": invitado_id,
        "invitado_uuid": invitado_uuid,
        "nombre_completo": nombre or "Invitado sin nombre",
        "es_invitado_principal": es_principal,
        "tipo_invitado": "Principal" if es_principal else "Acompanante",
        "es_invitado_imprevisto": es_imprevisto,
        "origen_invitado": "Imprevisto" if es_imprevisto else "Previsto",
        "email": _texto(safe_get(row, "ivt_email")),
        "telefono": _texto(safe_get(row, "ivt_telefono")),
        "mesa_id": mesa_id,
        "mesa_texto": f"Mesa {mesa_id}" if mesa_id is not None else "Sin mesa",
        "puesto_id": puesto_id,
        "puesto_texto": f"Puesto {puesto_id}" if puesto_id is not None else "Sin puesto",
        "llegada_confirmada": llegada_confirmada,
        "estado_llegada": _estado_llegada(llegada_confirmada),
        "fecha_hora_conf_llegada": safe_get(row, "ivt_fecha_hora_conf_llegada"),
        "tiene_novedad": _normalizar_bool(safe_get(row, "ivt_tiene_novedad")),
        "descripcion_novedad": _texto(safe_get(row, "ivt_descripcion_novedad")),
        "estado": _texto(safe_get(row, "ivt_estado")) or "Sin estado",
    }


def _evento_activo_valido(evento_activo: dict[str, Any] | None) -> tuple[int, int] | None:
    return evento_key(evento_activo)


def _aplicar_filtro(query: Any, filtro: str) -> Any:
    if filtro == "llegaron":
        return query.eq("ivt_llegada_confirmada", True)
    if filtro == "pendientes":
        return query.eq("ivt_llegada_confirmada", False)
    if filtro == "con_mesa":
        return query.not_.is_("ivt_mesa_id", "null")
    if filtro == "sin_mesa":
        return query.is_("ivt_mesa_id", "null")
    if filtro == "previstos":
        return query.eq("ivt_es_invitado_imprevisto", False)
    if filtro == "imprevistos":
        return query.eq("ivt_es_invitado_imprevisto", True)
    return query


def _resultado_error_consulta(ex: Exception, limit: int, offset: int) -> ResultadoInvitados:
    detalle = str(ex)
    estado = "permission_denied" if "permission" in detalle.lower() or "42501" in detalle else "connection_error"
    mensaje = (
        "No tienes permisos para consultar los invitados de este evento."
        if estado == "permission_denied"
        else "No fue posible cargar los invitados. Verifica la conexion e intentalo nuevamente."
    )
    return ResultadoInvitados(
        ok=False,
        estado=estado,
        mensaje=mensaje,
        invitados=[],
        total_recibidos=0,
        limit=limit,
        offset=offset,
        has_more=False,
    )


def listar_invitados(
    evento_activo: dict[str, Any] | None,
    busqueda: str = "",
    filtro: str = "todos",
    limit: int = INVITADOS_PAGE_SIZE,
    offset: int = 0,
    supabase: Any = None,
) -> ResultadoInvitados:
    key = _evento_activo_valido(evento_activo)
    if key is None:
        print("[INVITADOS][WARNING] Consulta sin evento activo.")
        return ResultadoInvitados(
            ok=False,
            estado="event_required",
            mensaje="Selecciona un evento antes de consultar los invitados.",
            invitados=[],
            total_recibidos=0,
            limit=limit,
            offset=offset,
            has_more=False,
        )

    filtro = filtro if filtro in FILTROS_INVITADOS else "todos"
    limit = max(1, min(int(limit or INVITADOS_PAGE_SIZE), 100))
    offset = max(0, int(offset or 0))
    busqueda_normalizada = _normalizar_busqueda(busqueda)

    print(
        "[INVITADOS][INFO] Consultando invitados:",
        f"cuenta={key[0]}",
        f"evento={key[1]}",
        f"filtro={filtro}",
        f"busqueda={'si' if busqueda_normalizada else 'no'}",
        f"offset={offset}",
        f"limit={limit}",
    )

    supabase = supabase or get_supabase_client()
    try:
        query = (
            supabase
            .table("evp_ivt_invitado")
            .select(SELECT_INVITADO)
            .eq("ivt_cuenta_id", key[0])
            .eq("ivt_evento_id", key[1])
            .eq("ivt_estado", "Activo")
        )
        if busqueda_normalizada:
            query = query.ilike("ivt_nombre_invitado_normalizado", f"%{busqueda_normalizada}%")
        query = _aplicar_filtro(query, filtro)
        response = (
            query
            .order("ivt_nombre_invitado")
            .range(offset, offset + limit)
            .execute()
        )
    except Exception as ex:
        print("[INVITADOS][ERROR] Error al consultar invitados:", type(ex).__name__, str(ex))
        return _resultado_error_consulta(ex, limit, offset)

    invitados = [
        invitado
        for row in extract_data(response)
        if (invitado := normalizar_invitado(to_dict(row) or {})) is not None
    ]
    has_more = len(invitados) > limit
    invitados = invitados[:limit]
    estado = "ready" if invitados else ("no_results" if busqueda_normalizada or filtro != "todos" else "empty")
    mensaje = (
        "Invitados cargados correctamente."
        if invitados
        else (
            "No se encontraron invitados con los criterios seleccionados."
            if estado == "no_results"
            else "Este evento todavia no tiene invitados registrados."
        )
    )
    print("[INVITADOS][INFO] Invitados recibidos:", len(invitados), "has_more=", has_more)

    return ResultadoInvitados(
        ok=True,
        estado=estado,
        mensaje=mensaje,
        invitados=invitados,
        total_recibidos=len(invitados),
        limit=limit,
        offset=offset,
        has_more=has_more,
    )


def obtener_invitado_por_id(
    evento_activo: dict[str, Any] | None,
    invitado_uuid: str,
    supabase: Any = None,
) -> ResultadoInvitadoDetalle:
    key = _evento_activo_valido(evento_activo)
    if key is None:
        return ResultadoInvitadoDetalle(
            ok=False,
            estado="event_required",
            mensaje="Selecciona un evento antes de consultar los invitados.",
            invitado=None,
        )

    invitado_uuid = _texto(invitado_uuid)
    if not invitado_uuid:
        return ResultadoInvitadoDetalle(
            ok=False,
            estado="not_found",
            mensaje="No fue posible identificar el invitado seleccionado.",
            invitado=None,
        )

    print("[INVITADOS][INFO] Consultando detalle de invitado.")
    supabase = supabase or get_supabase_client()
    try:
        response = (
            supabase
            .table("evp_ivt_invitado")
            .select(SELECT_INVITADO)
            .eq("ivt_cuenta_id", key[0])
            .eq("ivt_evento_id", key[1])
            .eq("ivt_invitado_uuid", invitado_uuid)
            .eq("ivt_estado", "Activo")
            .limit(1)
            .execute()
        )
    except Exception as ex:
        print("[INVITADOS][ERROR] Error al consultar detalle:", type(ex).__name__, str(ex))
        return ResultadoInvitadoDetalle(
            ok=False,
            estado="connection_error",
            mensaje="No fue posible consultar el detalle del invitado.",
            invitado=None,
        )

    data = extract_data(response)
    if not data:
        print("[INVITADOS][WARNING] Invitado no encontrado o no autorizado.")
        return ResultadoInvitadoDetalle(
            ok=False,
            estado="not_found",
            mensaje="El invitado ya no esta disponible o no tienes acceso.",
            invitado=None,
        )

    invitado = normalizar_invitado(to_dict(data[0]) or {})
    if not invitado:
        return ResultadoInvitadoDetalle(
            ok=False,
            estado="not_found",
            mensaje="El invitado no tiene datos validos para mostrar.",
            invitado=None,
        )

    return ResultadoInvitadoDetalle(
        ok=True,
        estado="ready",
        mensaje="Detalle cargado correctamente.",
        invitado=invitado,
    )
