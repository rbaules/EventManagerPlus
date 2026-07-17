from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import unicodedata
from typing import Any

from config import is_checkin_mode
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
    "ivt_usuario_conf_llegada,"
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

TIPO_BUSQUEDA_INVITADO = "invitado"
TIPO_BUSQUEDA_MESA = "mesa"
TIPOS_BUSQUEDA_INVITADOS = {TIPO_BUSQUEDA_INVITADO, TIPO_BUSQUEDA_MESA}


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
    mesas_coincidentes: int = 0


@dataclass(frozen=True)
class ResultadoInvitadoDetalle:
    ok: bool
    estado: str
    mensaje: str
    invitado: dict[str, Any] | None


@dataclass(frozen=True)
class ResultadoOperacionInvitado:
    ok: bool
    estado: str
    mensaje: str
    invitado: dict[str, Any] | None = None


@dataclass(frozen=True)
class ResultadoInvitaciones:
    ok: bool
    estado: str
    mensaje: str
    invitaciones: list[dict[str, Any]]


@dataclass(frozen=True)
class ResultadoGrupoInvitacion:
    ok: bool
    estado: str
    mensaje: str
    invitacion: dict[str, Any] | None
    invitados: list[dict[str, Any]]


@dataclass(frozen=True)
class ResultadoConfirmacionGrupo:
    ok: bool
    estado: str
    mensaje: str
    confirmados: int
    omitidos: int
    invitados: list[dict[str, Any]]


def _normalizar_texto_formulario(value: Any) -> str:
    return " ".join(_texto(value).split())


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


def _normalizar_nombre_bd(value: str) -> str:
    return _normalizar_busqueda(value)


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
        "usuario_conf_llegada": _texto(safe_get(row, "ivt_usuario_conf_llegada")),
        "tiene_novedad": _normalizar_bool(safe_get(row, "ivt_tiene_novedad")),
        "descripcion_novedad": _texto(safe_get(row, "ivt_descripcion_novedad")),
        "estado": _texto(safe_get(row, "ivt_estado")) or "Sin estado",
    }


def normalizar_invitacion(row: dict[str, Any]) -> dict[str, Any] | None:
    cuenta_id = _normalizar_id(safe_get(row, "inv_cuenta_id"))
    evento_id = _normalizar_id(safe_get(row, "inv_evento_id"))
    invitacion_id = _normalizar_id(safe_get(row, "inv_invitacion_id"))
    if None in (cuenta_id, evento_id, invitacion_id):
        return None
    destinatario = _texto(safe_get(row, "inv_destinatario_invitacion"))
    return {
        "cuenta_id": cuenta_id,
        "evento_id": evento_id,
        "invitacion_id": invitacion_id,
        "destinatario": destinatario or f"Invitacion {invitacion_id}",
        "codigo": _texto(safe_get(row, "inv_cod_abrev_invitacion")),
        "estado": _texto(safe_get(row, "inv_estado")) or "Sin estado",
    }


def _evento_activo_valido(evento_activo: dict[str, Any] | None) -> tuple[int, int] | None:
    return evento_key(evento_activo)


def _rol_evento(contexto: dict[str, Any]) -> str:
    evento = contexto.get("evento_actual") or {}
    return str(evento.get("rol") or contexto.get("rol_global_calculado") or "")


def _evento_autorizado(contexto: dict[str, Any]) -> bool:
    key = _evento_activo_valido(contexto.get("evento_actual"))
    if key is None:
        return False
    for evento in contexto.get("eventos_permitidos", []) or []:
        if evento_key(evento) == key:
            return True
    return False


def puede_administrar_invitados_planificados(contexto: dict[str, Any] | None) -> bool:
    if not contexto or not contexto.get("usr_usuario_id"):
        return False
    evento = contexto.get("evento_actual") or {}
    rol = _rol_evento(contexto)
    fase = str(evento.get("fase_evento") or "")
    estado = str(evento.get("estado") or "Activo")
    permitido = (
        rol in {"Master", "Administrador"}
        and fase == "Pre_evento"
        and estado == "Activo"
        and _evento_autorizado(contexto)
    )
    print(
        "[INVITADOS][INFO] Autorizacion invitados planificados:",
        f"rol={rol or 'Sin rol'}",
        f"fase={fase or 'Sin fase'}",
        f"estado={estado}",
        f"permitido={permitido}",
    )
    return permitido


def _puede_operar_evento_en_proceso(
    contexto: dict[str, Any] | None,
    roles_permitidos: set[str],
    etiqueta: str,
) -> bool:
    if not contexto or not contexto.get("usr_usuario_id"):
        return False
    evento = contexto.get("evento_actual") or {}
    rol = _rol_evento(contexto)
    fase = str(evento.get("fase_evento") or "")
    estado = str(evento.get("estado") or "")
    permitido = (
        rol in roles_permitidos
        and fase == "En_proceso"
        and estado == "Activo"
        and _evento_autorizado(contexto)
        and _evento_activo_valido(evento) is not None
    )
    print(
        "[INVITADOS][INFO] Autorizacion operativa:",
        f"accion={etiqueta}",
        f"rol={rol or 'Sin rol'}",
        f"fase={fase or 'Sin fase'}",
        f"estado={estado or 'Sin estado'}",
        f"permitido={permitido}",
    )
    return permitido


def puede_confirmar_llegada(contexto: dict[str, Any] | None) -> bool:
    return _puede_operar_evento_en_proceso(
        contexto,
        {"Master", "Administrador", "Operador"},
        "confirmar_llegada",
    )


def puede_reversar_llegada(contexto: dict[str, Any] | None) -> bool:
    return _puede_operar_evento_en_proceso(
        contexto,
        {"Master", "Administrador", "Operador"},
        "reversar_llegada",
    )


def puede_registrar_imprevisto(contexto: dict[str, Any] | None) -> bool:
    return _puede_operar_evento_en_proceso(
        contexto,
        {"Master", "Administrador", "Operador"},
        "registrar_imprevisto",
    )


def puede_eliminar_imprevisto(contexto: dict[str, Any] | None) -> bool:
    return _puede_operar_evento_en_proceso(
        contexto,
        {"Master", "Administrador", "Operador"},
        "eliminar_imprevisto",
    )


def _resultado_operacion(estado: str, mensaje: str, invitado: dict[str, Any] | None = None) -> ResultadoOperacionInvitado:
    return ResultadoOperacionInvitado(ok=estado == "success", estado=estado, mensaje=mensaje, invitado=invitado)


def _bloquear_operacion_checkin(operacion: str) -> ResultadoOperacionInvitado | None:
    if not is_checkin_mode():
        return None
    print("[CHECKIN][WARN] Operacion bloqueada en modo CHECKIN:", operacion)
    return _resultado_operacion("checkin_blocked", "Esta operacion no esta disponible en modo Check-in.")


def _validar_contexto_escritura(contexto: dict[str, Any] | None) -> ResultadoOperacionInvitado | None:
    if not contexto or not contexto.get("usr_usuario_id"):
        return _resultado_operacion("session_invalid", "La sesion no es valida. Inicia sesion nuevamente.")
    if _evento_activo_valido(contexto.get("evento_actual")) is None:
        return _resultado_operacion("event_required", "Selecciona un evento valido antes de administrar invitados.")
    if not _evento_autorizado(contexto):
        return _resultado_operacion("event_not_allowed", "No tienes acceso al evento activo.")
    if _rol_evento(contexto) not in {"Master", "Administrador"}:
        return _resultado_operacion("role_denied", "No tienes permisos para modificar invitados planificados.")
    if str((contexto.get("evento_actual") or {}).get("fase_evento") or "") != "Pre_evento":
        return _resultado_operacion(
            "phase_denied",
            "Los invitados planificados solo pueden modificarse durante Pre-evento.",
        )
    if str((contexto.get("evento_actual") or {}).get("estado") or "Activo") != "Activo":
        return _resultado_operacion("event_inactive", "El evento activo no esta disponible para modificar invitados.")
    return None


def _validar_contexto_operativo(
    contexto: dict[str, Any] | None,
    roles_permitidos: set[str],
) -> ResultadoOperacionInvitado | None:
    if not contexto or not contexto.get("usr_usuario_id"):
        return _resultado_operacion("session_invalid", "La sesion no es valida. Inicia sesion nuevamente.")
    if _evento_activo_valido(contexto.get("evento_actual")) is None:
        return _resultado_operacion("event_required", "Selecciona un evento valido antes de administrar invitados.")
    if not _evento_autorizado(contexto):
        return _resultado_operacion("event_not_allowed", "No tienes acceso al evento activo.")
    if _rol_evento(contexto) not in roles_permitidos:
        return _resultado_operacion("role_denied", "No tienes permisos para realizar esta accion.")
    evento = contexto.get("evento_actual") or {}
    if str(evento.get("fase_evento") or "") != "En_proceso":
        return _resultado_operacion("phase_denied", "El evento ya no esta en fase Evento en proceso.")
    if str(evento.get("estado") or "") != "Activo":
        return _resultado_operacion("event_inactive", "El evento activo no esta disponible para esta accion.")
    return None


def _validar_evento_real_operativo(
    evento_activo: dict[str, Any] | None,
    supabase: Any,
) -> ResultadoOperacionInvitado | None:
    key = _evento_activo_valido(evento_activo)
    if key is None:
        return _resultado_operacion("event_required", "Selecciona un evento valido antes de administrar invitados.")
    try:
        response = (
            supabase
            .table("evp_eve_evento")
            .select("eve_cuenta_id,eve_evento_id,eve_fase_evento,eve_estado")
            .eq("eve_cuenta_id", key[0])
            .eq("eve_evento_id", key[1])
            .limit(1)
            .execute()
        )
    except Exception as ex:
        print("[INVITADOS][ERROR] Error al validar fase real:", type(ex).__name__, str(ex))
        return _resultado_error_operacion(ex)

    data = extract_data(response)
    if not data:
        return _resultado_operacion("event_not_allowed", "El evento activo ya no esta disponible.")
    row = to_dict(data[0]) or {}
    fase = _texto(safe_get(row, "eve_fase_evento"))
    estado = _texto(safe_get(row, "eve_estado"))
    if fase != "En_proceso":
        print("[INVITADOS][WARNING] Cambio de fase detectado:", fase or "Sin fase")
        return _resultado_operacion("phase_denied", "El evento ya no esta en fase Evento en proceso.")
    if estado != "Activo":
        return _resultado_operacion("event_inactive", "El evento activo no esta disponible para esta accion.")
    return None


def _validar_formulario(payload: dict[str, Any], requiere_invitacion: bool) -> tuple[dict[str, Any] | None, str | None]:
    nombre = _normalizar_texto_formulario(payload.get("nombre_completo"))
    if not nombre:
        return None, "Completa el nombre del invitado."
    if len(nombre) > 80:
        return None, "El nombre del invitado no puede superar 80 caracteres."

    email = _normalizar_texto_formulario(payload.get("email"))
    if len(email) > 254:
        return None, "El email no puede superar 254 caracteres."

    telefono = _normalizar_texto_formulario(payload.get("telefono"))
    if len(telefono) > 20:
        return None, "El telefono no puede superar 20 caracteres."

    invitacion_id = _normalizar_id(payload.get("invitacion_id"))
    if requiere_invitacion and invitacion_id is None:
        return None, "Selecciona una invitacion para agregar el invitado."

    mesa_id = _normalizar_id(payload.get("mesa_id"))
    puesto_id = _normalizar_id(payload.get("puesto_id"))
    if payload.get("mesa_id") not in (None, "") and mesa_id is None:
        return None, "La mesa debe ser numerica."
    if payload.get("puesto_id") not in (None, "") and puesto_id is None:
        return None, "El puesto debe ser numerico."
    if mesa_id is not None and mesa_id < 0:
        return None, "La mesa no puede ser negativa."
    if puesto_id is not None and puesto_id < 0:
        return None, "El puesto no puede ser negativo."

    return {
        "invitacion_id": invitacion_id,
        "nombre_completo": nombre,
        "email": email or None,
        "telefono": telefono or None,
        "mesa_id": mesa_id,
        "puesto_id": puesto_id,
        "es_invitado_principal": bool(payload.get("es_invitado_principal")),
    }, None


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


def _normalizar_tipo_busqueda(tipo_busqueda: str | None) -> str:
    tipo = _normalizar_busqueda(tipo_busqueda)
    if tipo in TIPOS_BUSQUEDA_INVITADOS:
        return tipo
    print("[INVITADOS][WARNING] Tipo de busqueda invalido; usando invitado:", tipo_busqueda)
    return TIPO_BUSQUEDA_INVITADO


def _mesa_visible_normalizada(mesa_id: int) -> str:
    return _normalizar_busqueda(f"Mesa {mesa_id}")


def _mesa_coincide(mesa_id: int, patron: str) -> bool:
    if not patron:
        return True
    mesa_texto = _mesa_visible_normalizada(mesa_id)
    mesa_numero = _normalizar_busqueda(str(mesa_id))
    return patron in mesa_texto or patron in mesa_numero


def _obtener_mesas_coincidentes(
    supabase: Any,
    key: tuple[int, int],
    patron: str,
) -> list[int]:
    response = (
        supabase
        .table("evp_ivt_invitado")
        .select("ivt_mesa_id")
        .eq("ivt_cuenta_id", key[0])
        .eq("ivt_evento_id", key[1])
        .eq("ivt_estado", "Activo")
        .not_.is_("ivt_mesa_id", "null")
        .execute()
    )
    mesas: set[int] = set()
    for row in extract_data(response):
        mesa_id = _normalizar_id(safe_get(to_dict(row) or {}, "ivt_mesa_id"))
        if mesa_id is not None and _mesa_coincide(mesa_id, patron):
            mesas.add(mesa_id)
    return sorted(mesas)


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


def _resultado_error_operacion(ex: Exception) -> ResultadoOperacionInvitado:
    detalle = str(ex)
    detalle_lower = detalle.lower()
    if "permission" in detalle_lower or "42501" in detalle_lower:
        estado = "permission_denied"
        mensaje = "No tienes permisos para guardar invitados en este evento."
    elif "duplicate" in detalle_lower or "23505" in detalle_lower or "unique" in detalle_lower:
        estado = "duplicate"
        mensaje = "Ya existe un invitado con esos datos en este evento. Agrega un diferenciador para identificarlo."
    else:
        estado = "connection_error"
        mensaje = "No fue posible guardar el invitado. Verifica la conexion e intentalo nuevamente."
    return ResultadoOperacionInvitado(ok=False, estado=estado, mensaje=mensaje)


def listar_invitados(
    evento_activo: dict[str, Any] | None,
    busqueda: str = "",
    tipo_busqueda: str = TIPO_BUSQUEDA_INVITADO,
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
    tipo_busqueda = _normalizar_tipo_busqueda(tipo_busqueda)

    print(
        "[INVITADOS][INFO] Consulta iniciada:",
        f"cuenta={key[0]}",
        f"evento={key[1]}",
        f"tipo={tipo_busqueda}",
        f"patron='{busqueda_normalizada}'",
        f"filtro={filtro}",
        f"offset={offset}",
        f"limit={limit}",
    )

    supabase = supabase or get_supabase_client()
    mesas_coincidentes = 0
    try:
        mesas_filtradas: list[int] = []
        if tipo_busqueda == TIPO_BUSQUEDA_MESA and busqueda_normalizada:
            mesas_filtradas = _obtener_mesas_coincidentes(supabase, key, busqueda_normalizada)
            mesas_coincidentes = len(mesas_filtradas)
            print("[INVITADOS][INFO] Mesas coincidentes:", mesas_coincidentes)
            if not mesas_filtradas:
                return ResultadoInvitados(
                    ok=True,
                    estado="no_results",
                    mensaje="No se encontraron mesas o invitados con ese patron.",
                    invitados=[],
                    total_recibidos=0,
                    limit=limit,
                    offset=offset,
                    has_more=False,
                    mesas_coincidentes=0,
                )

        query = (
            supabase
            .table("evp_ivt_invitado")
            .select(SELECT_INVITADO)
            .eq("ivt_cuenta_id", key[0])
            .eq("ivt_evento_id", key[1])
            .eq("ivt_estado", "Activo")
        )
        if tipo_busqueda == TIPO_BUSQUEDA_INVITADO and busqueda_normalizada:
            query = query.ilike("ivt_nombre_invitado_normalizado", f"%{busqueda_normalizada}%")
        if tipo_busqueda == TIPO_BUSQUEDA_MESA and busqueda_normalizada:
            query = query.in_("ivt_mesa_id", mesas_filtradas)
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
    if estado == "no_results" and tipo_busqueda == TIPO_BUSQUEDA_MESA and busqueda_normalizada:
        mensaje_no_results = "No se encontraron mesas o invitados con ese patron."
    else:
        mensaje_no_results = "No se encontraron invitados con ese nombre." if tipo_busqueda == TIPO_BUSQUEDA_INVITADO else "No se encontraron invitados con los criterios seleccionados."
    mensaje = (
        "Invitados cargados correctamente."
        if invitados
        else (
            mensaje_no_results
            if estado == "no_results"
            else "Este evento todavia no tiene invitados registrados."
        )
    )
    if tipo_busqueda == TIPO_BUSQUEDA_MESA:
        print(
            "[INVITADOS][INFO] Mesas coincidentes:",
            mesas_coincidentes if busqueda_normalizada else "sin_patron",
            "invitados_recibidos=",
            len(invitados),
            "has_more=",
            has_more,
        )
    else:
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
        mesas_coincidentes=mesas_coincidentes,
    )


def listar_invitaciones_evento(
    evento_activo: dict[str, Any] | None,
    supabase: Any = None,
) -> ResultadoInvitaciones:
    key = _evento_activo_valido(evento_activo)
    if key is None:
        return ResultadoInvitaciones(
            ok=False,
            estado="event_required",
            mensaje="Selecciona un evento valido antes de administrar invitados.",
            invitaciones=[],
        )

    supabase = supabase or get_supabase_client()
    try:
        response = (
            supabase
            .table("evp_inv_invitacion")
            .select(
                "inv_cuenta_id,inv_evento_id,inv_invitacion_id,"
                "inv_cod_abrev_invitacion,inv_destinatario_invitacion,inv_estado"
            )
            .eq("inv_cuenta_id", key[0])
            .eq("inv_evento_id", key[1])
            .eq("inv_estado", "Activo")
            .order("inv_destinatario_invitacion")
            .execute()
        )
    except Exception as ex:
        print("[INVITADOS][ERROR] Error al consultar invitaciones:", type(ex).__name__, str(ex))
        return ResultadoInvitaciones(
            ok=False,
            estado="connection_error",
            mensaje="No fue posible cargar las invitaciones del evento.",
            invitaciones=[],
        )

    invitaciones = [
        invitacion
        for row in extract_data(response)
        if (invitacion := normalizar_invitacion(to_dict(row) or {})) is not None
    ]
    return ResultadoInvitaciones(
        ok=True,
        estado="ready" if invitaciones else "empty",
        mensaje=(
            "Invitaciones cargadas correctamente."
            if invitaciones
            else "No hay invitaciones activas para agregar invitados."
        ),
        invitaciones=invitaciones,
    )


def validar_duplicado_invitado(
    evento_activo: dict[str, Any] | None,
    nombre_completo: str,
    excluir: dict[str, Any] | None = None,
    supabase: Any = None,
) -> ResultadoOperacionInvitado:
    key = _evento_activo_valido(evento_activo)
    if key is None:
        return _resultado_operacion("event_required", "Selecciona un evento valido antes de administrar invitados.")

    nombre_normalizado = _normalizar_nombre_bd(nombre_completo)
    supabase = supabase or get_supabase_client()
    try:
        response = (
            supabase
            .table("evp_ivt_invitado")
            .select(SELECT_INVITADO)
            .eq("ivt_cuenta_id", key[0])
            .eq("ivt_evento_id", key[1])
            .eq("ivt_estado", "Activo")
            .eq("ivt_nombre_invitado_normalizado", nombre_normalizado)
            .execute()
        )
    except Exception as ex:
        print("[INVITADOS][ERROR] Error al validar duplicado:", type(ex).__name__, str(ex))
        return _resultado_error_operacion(ex)

    excluir_key = None
    if excluir:
        excluir_key = (
            excluir.get("cuenta_id"),
            excluir.get("evento_id"),
            excluir.get("invitacion_id"),
            excluir.get("invitado_id"),
        )

    for row in extract_data(response):
        invitado = normalizar_invitado(to_dict(row) or {})
        if not invitado:
            continue
        actual_key = (
            invitado.get("cuenta_id"),
            invitado.get("evento_id"),
            invitado.get("invitacion_id"),
            invitado.get("invitado_id"),
        )
        if excluir_key and actual_key == excluir_key:
            continue
        print("[INVITADOS][WARNING] Duplicado detectado en evento activo.")
        return _resultado_operacion(
            "duplicate",
            "Ya existe un invitado con ese nombre en este evento. Usa un nombre visible que lo diferencie.",
        )

    return _resultado_operacion("success", "No se detectaron duplicados.")


def _obtener_invitado_por_clave(
    evento_activo: dict[str, Any] | None,
    invitacion_id: Any,
    invitado_id: Any,
    supabase: Any,
) -> dict[str, Any] | None:
    key = _evento_activo_valido(evento_activo)
    invitacion_id = _normalizar_id(invitacion_id)
    invitado_id = _normalizar_id(invitado_id)
    if key is None or invitacion_id is None or invitado_id is None:
        return None
    response = (
        supabase
        .table("evp_ivt_invitado")
        .select(SELECT_INVITADO)
        .eq("ivt_cuenta_id", key[0])
        .eq("ivt_evento_id", key[1])
        .eq("ivt_invitacion_id", invitacion_id)
        .eq("ivt_invitado_id", invitado_id)
        .eq("ivt_estado", "Activo")
        .limit(1)
        .execute()
    )
    data = extract_data(response)
    return normalizar_invitado(to_dict(data[0]) or {}) if data else None


def crear_invitado_planificado(
    contexto: dict[str, Any] | None,
    payload: dict[str, Any],
    supabase: Any = None,
) -> ResultadoOperacionInvitado:
    bloqueo_checkin = _bloquear_operacion_checkin("crear_invitado_planificado")
    if bloqueo_checkin:
        return bloqueo_checkin
    bloqueo = _validar_contexto_escritura(contexto)
    if bloqueo:
        return bloqueo
    datos, error = _validar_formulario(payload, requiere_invitacion=True)
    if error:
        print("[INVITADOS][WARNING] Validacion fallida al crear invitado.")
        return _resultado_operacion("invalid_data", error)

    evento_activo = contexto.get("evento_actual") if contexto else None
    duplicado = validar_duplicado_invitado(evento_activo, datos["nombre_completo"], supabase=supabase)
    if not duplicado.ok:
        return duplicado

    key = _evento_activo_valido(evento_activo)
    assert key is not None
    supabase = supabase or get_supabase_client()
    print("[INVITADOS][INFO] Inicio guardado invitado planificado: operacion=crear", f"cuenta={key[0]}", f"evento={key[1]}")
    insert_data = {
        "ivt_cuenta_id": key[0],
        "ivt_evento_id": key[1],
        "ivt_invitacion_id": datos["invitacion_id"],
        "ivt_nombre_invitado": datos["nombre_completo"],
        "ivt_es_invitado_principal": datos["es_invitado_principal"],
        "ivt_es_invitado_imprevisto": False,
        "ivt_email": datos["email"],
        "ivt_telefono": datos["telefono"],
        "ivt_mesa_id": datos["mesa_id"],
        "ivt_puesto_id": datos["puesto_id"],
        "ivt_llegada_confirmada": False,
        "ivt_estado": "Activo",
    }
    try:
        response = supabase.table("evp_ivt_invitado").insert(insert_data).execute()
    except Exception as ex:
        print("[INVITADOS][ERROR] Error al crear invitado:", type(ex).__name__, str(ex))
        return _resultado_error_operacion(ex)

    data = extract_data(response)
    invitado = normalizar_invitado(to_dict(data[0]) or {}) if data else None
    if not invitado:
        return _resultado_operacion("unexpected_response", "El invitado fue guardado, pero no pudimos leer el registro resultante.")
    print("[INVITADOS][INFO] Insercion satisfactoria.")
    return _resultado_operacion("success", "Invitado agregado correctamente.", invitado)


def actualizar_invitado_planificado(
    contexto: dict[str, Any] | None,
    invitado_original: dict[str, Any] | None,
    payload: dict[str, Any],
    supabase: Any = None,
) -> ResultadoOperacionInvitado:
    bloqueo_checkin = _bloquear_operacion_checkin("actualizar_invitado_planificado")
    if bloqueo_checkin:
        return bloqueo_checkin
    bloqueo = _validar_contexto_escritura(contexto)
    if bloqueo:
        return bloqueo
    if not invitado_original:
        return _resultado_operacion("not_found", "El invitado seleccionado ya no esta disponible.")
    if invitado_original.get("es_invitado_imprevisto"):
        return _resultado_operacion("invalid_data", "Solo se pueden editar invitados planificados en esta tarea.")

    datos, error = _validar_formulario(payload, requiere_invitacion=False)
    if error:
        print("[INVITADOS][WARNING] Validacion fallida al editar invitado.")
        return _resultado_operacion("invalid_data", error)

    evento_activo = contexto.get("evento_actual") if contexto else None
    key = _evento_activo_valido(evento_activo)
    original_key = (
        _normalizar_id(invitado_original.get("cuenta_id")),
        _normalizar_id(invitado_original.get("evento_id")),
    )
    if key is None or original_key != key:
        print("[INVITADOS][WARNING] Cambio de evento detectado antes de guardar.")
        return _resultado_operacion("event_changed", "El evento activo cambio. Vuelve a abrir el formulario.")

    supabase = supabase or get_supabase_client()
    try:
        actual = _obtener_invitado_por_clave(
            evento_activo,
            invitado_original.get("invitacion_id"),
            invitado_original.get("invitado_id"),
            supabase,
        )
    except Exception as ex:
        print("[INVITADOS][ERROR] Error al verificar invitado antes de editar:", type(ex).__name__, str(ex))
        return _resultado_error_operacion(ex)

    if not actual:
        return _resultado_operacion("not_found", "El invitado ya no existe o no tienes acceso.")
    if actual.get("es_invitado_imprevisto"):
        return _resultado_operacion("invalid_data", "Solo se pueden editar invitados planificados en esta tarea.")

    duplicado = validar_duplicado_invitado(evento_activo, datos["nombre_completo"], excluir=actual, supabase=supabase)
    if not duplicado.ok:
        return duplicado

    update_data = {
        "ivt_nombre_invitado": datos["nombre_completo"],
        "ivt_es_invitado_principal": datos["es_invitado_principal"],
        "ivt_email": datos["email"],
        "ivt_telefono": datos["telefono"],
        "ivt_mesa_id": datos["mesa_id"],
        "ivt_puesto_id": datos["puesto_id"],
    }
    print("[INVITADOS][INFO] Inicio guardado invitado planificado: operacion=editar", f"cuenta={key[0]}", f"evento={key[1]}")
    try:
        response = (
            supabase
            .table("evp_ivt_invitado")
            .update(update_data)
            .eq("ivt_cuenta_id", key[0])
            .eq("ivt_evento_id", key[1])
            .eq("ivt_invitacion_id", actual["invitacion_id"])
            .eq("ivt_invitado_id", actual["invitado_id"])
            .eq("ivt_estado", "Activo")
            .execute()
        )
    except Exception as ex:
        print("[INVITADOS][ERROR] Error al actualizar invitado:", type(ex).__name__, str(ex))
        return _resultado_error_operacion(ex)

    data = extract_data(response)
    invitado = normalizar_invitado(to_dict(data[0]) or {}) if data else None
    if not invitado:
        invitado = _obtener_invitado_por_clave(evento_activo, actual["invitacion_id"], actual["invitado_id"], supabase)
    if not invitado:
        return _resultado_operacion("unexpected_response", "El invitado fue actualizado, pero no pudimos leer el registro resultante.")
    print("[INVITADOS][INFO] Actualizacion satisfactoria.")
    return _resultado_operacion("success", "Invitado actualizado correctamente.", invitado)


def _validar_invitado_mismo_evento(
    evento_activo: dict[str, Any] | None,
    invitado: dict[str, Any] | None,
) -> tuple[tuple[int, int] | None, ResultadoOperacionInvitado | None]:
    key = _evento_activo_valido(evento_activo)
    if key is None:
        return None, _resultado_operacion("event_required", "Selecciona un evento valido antes de administrar invitados.")
    if not invitado:
        return key, _resultado_operacion("not_found", "El invitado seleccionado ya no esta disponible.")
    invitado_key = (
        _normalizar_id(invitado.get("cuenta_id")),
        _normalizar_id(invitado.get("evento_id")),
    )
    if invitado_key != key:
        print("[INVITADOS][WARNING] Invitado de otro evento rechazado.")
        return key, _resultado_operacion("event_changed", "El evento activo cambio. Abre nuevamente la operacion.")
    return key, None


def confirmar_llegada(
    contexto: dict[str, Any] | None,
    invitado_original: dict[str, Any] | None,
    supabase: Any = None,
) -> ResultadoOperacionInvitado:
    bloqueo = _validar_contexto_operativo(contexto, {"Master", "Administrador", "Operador"})
    if bloqueo:
        return bloqueo
    evento_activo = contexto.get("evento_actual") if contexto else None
    key, error = _validar_invitado_mismo_evento(evento_activo, invitado_original)
    if error:
        return error
    assert key is not None
    supabase = supabase or get_supabase_client()

    bloqueo_real = _validar_evento_real_operativo(evento_activo, supabase)
    if bloqueo_real:
        return bloqueo_real

    try:
        actual = _obtener_invitado_por_clave(
            evento_activo,
            invitado_original.get("invitacion_id"),
            invitado_original.get("invitado_id"),
            supabase,
        )
    except Exception as ex:
        print("[INVITADOS][ERROR] Error al verificar invitado antes de confirmar llegada:", type(ex).__name__, str(ex))
        return _resultado_error_operacion(ex)

    if not actual:
        return _resultado_operacion("not_found", "El invitado ya no existe o no tienes acceso.")
    if actual.get("llegada_confirmada"):
        print("[INVITADOS][INFO] Llegada ya estaba confirmada.")
        return _resultado_operacion("already_confirmed", "La llegada de este invitado ya fue confirmada.", actual)

    print("[INVITADOS][INFO] Intento de confirmar llegada:", f"cuenta={key[0]}", f"evento={key[1]}")
    update_data = {
        "ivt_llegada_confirmada": True,
        "ivt_fecha_hora_conf_llegada": datetime.now(timezone.utc).isoformat(),
        "ivt_usuario_conf_llegada": contexto.get("usr_usuario_id") if contexto else None,
    }
    try:
        response = (
            supabase
            .table("evp_ivt_invitado")
            .update(update_data)
            .eq("ivt_cuenta_id", key[0])
            .eq("ivt_evento_id", key[1])
            .eq("ivt_invitacion_id", actual["invitacion_id"])
            .eq("ivt_invitado_id", actual["invitado_id"])
            .eq("ivt_estado", "Activo")
            .eq("ivt_llegada_confirmada", False)
            .execute()
        )
    except Exception as ex:
        print("[INVITADOS][ERROR] Error al confirmar llegada:", type(ex).__name__, str(ex))
        return _resultado_error_operacion(ex)

    data = extract_data(response)
    invitado = normalizar_invitado(to_dict(data[0]) or {}) if data else None
    if not invitado:
        invitado = _obtener_invitado_por_clave(evento_activo, actual["invitacion_id"], actual["invitado_id"], supabase)
        if invitado and invitado.get("llegada_confirmada"):
            return _resultado_operacion("already_confirmed", "La llegada de este invitado ya fue confirmada.", invitado)
        print("[INVITADOS][WARNING] Conflicto de concurrencia al confirmar llegada.")
        return _resultado_operacion("conflict", "No fue posible confirmar la llegada porque el registro cambio. Intenta nuevamente.", invitado)

    print("[INVITADOS][INFO] Llegada confirmada.")
    return _resultado_operacion("success", "Llegada confirmada correctamente.", invitado)


def cargar_grupo_invitacion(
    evento_activo: dict[str, Any] | None,
    invitado_base: dict[str, Any] | None,
    supabase: Any = None,
) -> ResultadoGrupoInvitacion:
    key, error = _validar_invitado_mismo_evento(evento_activo, invitado_base)
    if error:
        return ResultadoGrupoInvitacion(False, error.estado, error.mensaje, None, [])
    assert key is not None
    invitacion_id = _normalizar_id(invitado_base.get("invitacion_id") if invitado_base else None)
    if invitacion_id is None:
        return ResultadoGrupoInvitacion(
            ok=False,
            estado="invitation_invalid",
            mensaje="El invitado seleccionado no tiene una invitacion valida.",
            invitacion=None,
            invitados=[],
        )

    print(
        "[INVITADOS][INFO] Cargando grupo de invitacion:",
        f"cuenta={key[0]}",
        f"evento={key[1]}",
        f"invitacion={invitacion_id}",
    )
    supabase = supabase or get_supabase_client()
    try:
        invitacion_response = (
            supabase
            .table("evp_inv_invitacion")
            .select(
                "inv_cuenta_id,inv_evento_id,inv_invitacion_id,"
                "inv_cod_abrev_invitacion,inv_destinatario_invitacion,inv_estado"
            )
            .eq("inv_cuenta_id", key[0])
            .eq("inv_evento_id", key[1])
            .eq("inv_invitacion_id", invitacion_id)
            .eq("inv_estado", "Activo")
            .limit(1)
            .execute()
        )
        invitados_response = (
            supabase
            .table("evp_ivt_invitado")
            .select(SELECT_INVITADO)
            .eq("ivt_cuenta_id", key[0])
            .eq("ivt_evento_id", key[1])
            .eq("ivt_invitacion_id", invitacion_id)
            .eq("ivt_estado", "Activo")
            .order("ivt_puesto_id")
            .execute()
        )
    except Exception as ex:
        print("[INVITADOS][ERROR] Error al cargar grupo de invitacion:", type(ex).__name__, str(ex))
        err = _resultado_error_operacion(ex)
        return ResultadoGrupoInvitacion(False, err.estado, "No fue posible cargar la invitacion seleccionada.", None, [])

    invitacion_data = extract_data(invitacion_response)
    invitacion = normalizar_invitacion(to_dict(invitacion_data[0]) or {}) if invitacion_data else None
    invitados = [
        invitado
        for row in extract_data(invitados_response)
        if (invitado := normalizar_invitado(to_dict(row) or {})) is not None
    ]
    if not invitados:
        print("[INVITADOS][WARNING] Invitacion sin integrantes recuperables.")
        return ResultadoGrupoInvitacion(
            ok=False,
            estado="empty",
            mensaje="No se encontraron integrantes activos para esta invitacion.",
            invitacion=invitacion,
            invitados=[],
        )

    print("[INVITADOS][INFO] Integrantes recuperados:", len(invitados))
    return ResultadoGrupoInvitacion(
        ok=True,
        estado="ready",
        mensaje="Invitacion cargada correctamente.",
        invitacion=invitacion
        or {
            "cuenta_id": key[0],
            "evento_id": key[1],
            "invitacion_id": invitacion_id,
            "destinatario": f"Invitacion {invitacion_id}",
            "codigo": "",
            "estado": "Activo",
        },
        invitados=invitados,
    )


def confirmar_llegadas_invitados(
    contexto: dict[str, Any] | None,
    invitacion: dict[str, Any] | None,
    invitados_seleccionados: list[dict[str, Any]],
    supabase: Any = None,
) -> ResultadoConfirmacionGrupo:
    bloqueo = _validar_contexto_operativo(contexto, {"Master", "Administrador", "Operador"})
    if bloqueo:
        return ResultadoConfirmacionGrupo(False, bloqueo.estado, bloqueo.mensaje, 0, 0, [])
    evento_activo = contexto.get("evento_actual") if contexto else None
    key = _evento_activo_valido(evento_activo)
    invitacion_id = _normalizar_id((invitacion or {}).get("invitacion_id"))
    invitacion_key = (
        _normalizar_id((invitacion or {}).get("cuenta_id")),
        _normalizar_id((invitacion or {}).get("evento_id")),
    )
    if key is None or invitacion_id is None or invitacion_key != key:
        return ResultadoConfirmacionGrupo(
            False,
            "event_changed",
            "El evento activo cambio. Vuelve a cargar la invitacion.",
            0,
            0,
            [],
        )
    if not invitados_seleccionados:
        return ResultadoConfirmacionGrupo(
            False,
            "empty_selection",
            "Selecciona al menos un invitado pendiente para confirmar.",
            0,
            0,
            [],
        )

    supabase = supabase or get_supabase_client()
    bloqueo_real = _validar_evento_real_operativo(evento_activo, supabase)
    if bloqueo_real:
        return ResultadoConfirmacionGrupo(False, bloqueo_real.estado, bloqueo_real.mensaje, 0, 0, [])

    confirmados = 0
    omitidos = 0
    actualizados: list[dict[str, Any]] = []
    print("[INVITADOS][INFO] Llegadas solicitadas:", len(invitados_seleccionados))
    for invitado in invitados_seleccionados:
        invitado_key = (
            _normalizar_id(invitado.get("cuenta_id")),
            _normalizar_id(invitado.get("evento_id")),
        )
        if invitado_key != key or _normalizar_id(invitado.get("invitacion_id")) != invitacion_id:
            omitidos += 1
            print("[INVITADOS][WARNING] Invitado fuera de invitacion rechazado.")
            continue
        resultado = confirmar_llegada(contexto, invitado, supabase=supabase)
        if resultado.ok:
            confirmados += 1
        else:
            omitidos += 1
        if resultado.invitado:
            actualizados.append(resultado.invitado)

    grupo = cargar_grupo_invitacion(
        evento_activo,
        {
            "cuenta_id": key[0],
            "evento_id": key[1],
            "invitacion_id": invitacion_id,
            "invitado_id": invitados_seleccionados[0].get("invitado_id"),
        },
        supabase=supabase,
    )
    invitados_actuales = grupo.invitados if grupo.ok else actualizados
    if confirmados == 0:
        return ResultadoConfirmacionGrupo(
            ok=False,
            estado="no_updates",
            mensaje="No se confirmaron nuevas llegadas. El estado fue actualizado para revisar la invitacion.",
            confirmados=0,
            omitidos=omitidos,
            invitados=invitados_actuales,
        )
    mensaje = (
        f"Se confirmo correctamente {confirmados} llegada."
        if confirmados == 1
        else f"Se confirmaron correctamente {confirmados} llegadas."
    )
    if omitidos:
        mensaje = f"{mensaje} {omitidos} seleccion no requirio actualizacion."
    print("[INVITADOS][INFO] Llegadas confirmadas:", confirmados, "omitidas:", omitidos)
    return ResultadoConfirmacionGrupo(
        ok=True,
        estado="success",
        mensaje=mensaje,
        confirmados=confirmados,
        omitidos=omitidos,
        invitados=invitados_actuales,
    )


def reversar_llegada(
    contexto: dict[str, Any] | None,
    invitado_original: dict[str, Any] | None,
    supabase: Any = None,
) -> ResultadoOperacionInvitado:
    bloqueo = _validar_contexto_operativo(contexto, {"Master", "Administrador", "Operador"})
    if bloqueo:
        return bloqueo
    evento_activo = contexto.get("evento_actual") if contexto else None
    key, error = _validar_invitado_mismo_evento(evento_activo, invitado_original)
    if error:
        return error
    assert key is not None
    supabase = supabase or get_supabase_client()

    bloqueo_real = _validar_evento_real_operativo(evento_activo, supabase)
    if bloqueo_real:
        return bloqueo_real

    try:
        actual = _obtener_invitado_por_clave(
            evento_activo,
            invitado_original.get("invitacion_id"),
            invitado_original.get("invitado_id"),
            supabase,
        )
    except Exception as ex:
        print("[INVITADOS][ERROR] Error al verificar invitado antes de reversar llegada:", type(ex).__name__, str(ex))
        return _resultado_error_operacion(ex)

    if not actual:
        return _resultado_operacion("not_found", "El invitado ya no existe o no tienes acceso.")
    if not actual.get("llegada_confirmada"):
        return _resultado_operacion("arrival_not_confirmed", "La llegada de este invitado no esta confirmada.", actual)

    print("[INVITADOS][INFO] Intento de reversar llegada:", f"cuenta={key[0]}", f"evento={key[1]}")
    update_data = {
        "ivt_llegada_confirmada": False,
        "ivt_fecha_hora_conf_llegada": None,
        "ivt_usuario_conf_llegada": None,
    }
    try:
        response = (
            supabase
            .table("evp_ivt_invitado")
            .update(update_data)
            .eq("ivt_cuenta_id", key[0])
            .eq("ivt_evento_id", key[1])
            .eq("ivt_invitacion_id", actual["invitacion_id"])
            .eq("ivt_invitado_id", actual["invitado_id"])
            .eq("ivt_estado", "Activo")
            .eq("ivt_llegada_confirmada", True)
            .execute()
        )
    except Exception as ex:
        print("[INVITADOS][ERROR] Error al reversar llegada:", type(ex).__name__, str(ex))
        return _resultado_error_operacion(ex)

    data = extract_data(response)
    invitado = normalizar_invitado(to_dict(data[0]) or {}) if data else None
    if not invitado:
        invitado = _obtener_invitado_por_clave(evento_activo, actual["invitacion_id"], actual["invitado_id"], supabase)
        if invitado and not invitado.get("llegada_confirmada"):
            return _resultado_operacion("arrival_not_confirmed", "La llegada de este invitado no esta confirmada.", invitado)
        print("[INVITADOS][WARNING] Conflicto de concurrencia al reversar llegada.")
        return _resultado_operacion("conflict", "No fue posible reversar la llegada porque el registro cambio. Intenta nuevamente.", invitado)

    print("[INVITADOS][INFO] Reversion satisfactoria.")
    return _resultado_operacion("success", "La llegada fue reversada correctamente.", invitado)


def crear_invitado_imprevisto(
    contexto: dict[str, Any] | None,
    payload: dict[str, Any],
    supabase: Any = None,
) -> ResultadoOperacionInvitado:
    bloqueo_checkin = _bloquear_operacion_checkin("crear_invitado_imprevisto")
    if bloqueo_checkin:
        return bloqueo_checkin
    bloqueo = _validar_contexto_operativo(contexto, {"Master", "Administrador", "Operador"})
    if bloqueo:
        return bloqueo
    datos, error = _validar_formulario(payload, requiere_invitacion=True)
    if error:
        print("[INVITADOS][WARNING] Validacion fallida al crear imprevisto.")
        return _resultado_operacion("invalid_data", error)

    evento_activo = contexto.get("evento_actual") if contexto else None
    supabase = supabase or get_supabase_client()
    bloqueo_real = _validar_evento_real_operativo(evento_activo, supabase)
    if bloqueo_real:
        return bloqueo_real

    duplicado = validar_duplicado_invitado(evento_activo, datos["nombre_completo"], supabase=supabase)
    if not duplicado.ok:
        return duplicado

    key = _evento_activo_valido(evento_activo)
    assert key is not None
    print("[INVITADOS][INFO] Insercion de invitado imprevisto:", f"cuenta={key[0]}", f"evento={key[1]}")
    insert_data = {
        "ivt_cuenta_id": key[0],
        "ivt_evento_id": key[1],
        "ivt_invitacion_id": datos["invitacion_id"],
        "ivt_nombre_invitado": datos["nombre_completo"],
        "ivt_es_invitado_principal": False,
        "ivt_es_invitado_imprevisto": True,
        "ivt_email": datos["email"],
        "ivt_telefono": datos["telefono"],
        "ivt_mesa_id": datos["mesa_id"],
        "ivt_puesto_id": datos["puesto_id"],
        "ivt_llegada_confirmada": False,
        "ivt_estado": "Activo",
    }
    try:
        response = supabase.table("evp_ivt_invitado").insert(insert_data).execute()
    except Exception as ex:
        print("[INVITADOS][ERROR] Error al crear invitado imprevisto:", type(ex).__name__, str(ex))
        return _resultado_error_operacion(ex)

    data = extract_data(response)
    invitado = normalizar_invitado(to_dict(data[0]) or {}) if data else None
    if not invitado:
        return _resultado_operacion("unexpected_response", "El invitado fue guardado, pero no pudimos leer el registro resultante.")
    print("[INVITADOS][INFO] Invitado imprevisto agregado.")
    return _resultado_operacion("success", "Invitado imprevisto agregado correctamente.", invitado)


def eliminar_invitado_imprevisto(
    contexto: dict[str, Any] | None,
    invitado_original: dict[str, Any] | None,
    supabase: Any = None,
) -> ResultadoOperacionInvitado:
    bloqueo_checkin = _bloquear_operacion_checkin("eliminar_invitado_imprevisto")
    if bloqueo_checkin:
        return bloqueo_checkin
    bloqueo = _validar_contexto_operativo(contexto, {"Master", "Administrador", "Operador"})
    if bloqueo:
        return bloqueo
    evento_activo = contexto.get("evento_actual") if contexto else None
    key, error = _validar_invitado_mismo_evento(evento_activo, invitado_original)
    if error:
        return error
    assert key is not None
    supabase = supabase or get_supabase_client()

    bloqueo_real = _validar_evento_real_operativo(evento_activo, supabase)
    if bloqueo_real:
        return bloqueo_real

    try:
        actual = _obtener_invitado_por_clave(
            evento_activo,
            invitado_original.get("invitacion_id"),
            invitado_original.get("invitado_id"),
            supabase,
        )
    except Exception as ex:
        print("[INVITADOS][ERROR] Error al verificar invitado antes de eliminar imprevisto:", type(ex).__name__, str(ex))
        return _resultado_error_operacion(ex)

    if not actual:
        return _resultado_operacion("not_found", "El invitado ya no existe o no tienes acceso.")
    if not actual.get("es_invitado_imprevisto"):
        return _resultado_operacion("not_unexpected", "Solo se pueden eliminar invitados imprevistos desde esta accion.", actual)
    if actual.get("llegada_confirmada"):
        return _resultado_operacion(
            "arrival_confirmed",
            "No se puede eliminar un invitado cuya llegada ya fue confirmada sin una regla de negocio explicita.",
            actual,
        )

    print("[INVITADOS][INFO] Intento de eliminar invitado imprevisto:", f"cuenta={key[0]}", f"evento={key[1]}")
    try:
        response = (
            supabase
            .table("evp_ivt_invitado")
            .update({"ivt_estado": "Inactivo"})
            .eq("ivt_cuenta_id", key[0])
            .eq("ivt_evento_id", key[1])
            .eq("ivt_invitacion_id", actual["invitacion_id"])
            .eq("ivt_invitado_id", actual["invitado_id"])
            .eq("ivt_es_invitado_imprevisto", True)
            .eq("ivt_llegada_confirmada", False)
            .eq("ivt_estado", "Activo")
            .execute()
        )
    except Exception as ex:
        print("[INVITADOS][ERROR] Error al eliminar invitado imprevisto:", type(ex).__name__, str(ex))
        return _resultado_error_operacion(ex)

    data = extract_data(response)
    invitado = normalizar_invitado(to_dict(data[0]) or {}) if data else None
    if not invitado:
        nuevo_estado = _obtener_invitado_por_clave(evento_activo, actual["invitacion_id"], actual["invitado_id"], supabase)
        if nuevo_estado is None:
            return _resultado_operacion("success", "Invitado imprevisto eliminado correctamente.")
        print("[INVITADOS][WARNING] Conflicto de concurrencia al eliminar imprevisto.")
        return _resultado_operacion("conflict", "No fue posible eliminar el invitado porque el registro cambio. Intenta nuevamente.", nuevo_estado)

    print("[INVITADOS][INFO] Inactivacion satisfactoria.")
    return _resultado_operacion("success", "Invitado imprevisto eliminado correctamente.", invitado)


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
