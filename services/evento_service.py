from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import traceback
from typing import Any, Callable

from services.authorization_service import (
    puede_activar_evento,
    puede_cambiar_ubicacion_evento,
    puede_cerrar_evento,
    puede_crear_evento,
    puede_desactivar_evento,
    puede_editar_evento,
    puede_establecer_evento_predeterminado,
    puede_iniciar_evento,
    puede_ver_administracion_eventos,
)
from services.evento_context_service import evento_key
from services.response_utils import extract_data, safe_get, to_dict


FASES_EVENTO = frozenset({"Pre_evento", "En_proceso", "Post_evento", "Cerrado"})
ESTADOS_EVENTO = frozenset({"Activo", "Suspendido", "Inactivo"})
TIPOS_EVENTO_VALIDOS = (
    "Boda",
    "Cumpleaños",
    "Quinceaños",
    "Corporativo",
    "Otro",
)
TRANSICIONES_FASE = {
    "Pre_evento": ("En_proceso",),
    "En_proceso": ("Post_evento",),
    "Post_evento": (),
    "Cerrado": (),
}
SELECT_EVENTO = (
    "eve_cuenta_id,eve_evento_id,eve_nombre_evento,eve_nombre_evento_abrev,"
    "eve_fase_evento,eve_tipo_evento,eve_lugar_id,eve_salon_id,eve_cant_mesas,"
    "eve_fecha_hora_inicio,eve_fecha_hora_fin,eve_estado"
)
_CAMPOS_EDITABLES = frozenset(
    {
        "nombre_evento",
        "nombre_evento_abrev",
        "tipo_evento",
        "fecha_hora_inicio",
        "fecha_hora_fin",
        "cant_mesas",
    }
)
CAMPOS_ESTRUCTURALES = frozenset({"lugar_id", "salon_id", "cant_mesas"})
CAMPOS_NO_ESTRUCTURALES = frozenset(
    {
        "nombre_evento",
        "nombre_evento_abrev",
        "tipo_evento",
        "fecha_hora_inicio",
        "fecha_hora_fin",
    }
)


@dataclass(frozen=True)
class ResultadoEventos:
    ok: bool
    estado: str
    mensaje: str
    eventos: list[dict[str, Any]]


@dataclass(frozen=True)
class ResultadoEvento:
    ok: bool
    estado: str
    mensaje: str
    evento: dict[str, Any] | None = None


@dataclass(frozen=True)
class ResultadoDependenciasEvento:
    ok: bool
    bloquea: bool
    mensaje: str
    conteos: dict[str, int]


class EventoServiceError(RuntimeError):
    """Error controlado al consultar o administrar eventos."""


def _id(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _texto(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def normalizar_tipo_evento(value: Any) -> str | None:
    text = _texto(value)
    return text or None


def _filas(response: Any) -> list[dict[str, Any]]:
    return [row for item in extract_data(response) if (row := to_dict(item))]


def _payload_seguro(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        key: ("<redactado>" if key in {"eve_nombre_evento", "eve_nombre_evento_abrev"} else value)
        for key, value in payload.items()
    }


def _fecha_legible(value: Any) -> str | None:
    if not value:
        return None
    text = str(value)
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).strftime("%d/%m/%Y %I:%M %p")
    except ValueError:
        return text


def normalizar_evento(row: dict[str, Any], contexto_evento: dict[str, Any] | None = None) -> dict[str, Any] | None:
    cuenta_id = _id(safe_get(row, "eve_cuenta_id"))
    evento_id = _id(safe_get(row, "eve_evento_id"))
    if cuenta_id is None or evento_id is None:
        return None
    contexto_evento = contexto_evento or {}
    inicio = safe_get(row, "eve_fecha_hora_inicio")
    return {
        "cuenta_id": cuenta_id,
        "evento_id": evento_id,
        "nombre_evento": _texto(safe_get(row, "eve_nombre_evento")) or f"Evento {evento_id}",
        "nombre_evento_abrev": _texto(safe_get(row, "eve_nombre_evento_abrev")),
        "fase_evento": _texto(safe_get(row, "eve_fase_evento")),
        "tipo_evento": normalizar_tipo_evento(safe_get(row, "eve_tipo_evento")) or "",
        "lugar_id": _id(safe_get(row, "eve_lugar_id")),
        "salon_id": _id(safe_get(row, "eve_salon_id")),
        "cant_mesas": _id(safe_get(row, "eve_cant_mesas")),
        "fecha_hora_inicio": inicio,
        "fecha_hora_inicio_legible": _fecha_legible(inicio),
        "fecha_hora_fin": safe_get(row, "eve_fecha_hora_fin"),
        "estado": _texto(safe_get(row, "eve_estado")),
        "rol": safe_get(contexto_evento, "rol", "Sin rol"),
    }


def _error(ex: Exception, operacion: str = "OPERACION") -> ResultadoEvento:
    attrs = {
        name: getattr(ex, name, None)
        for name in ("code", "message", "details", "hint", "response", "status_code")
        if getattr(ex, name, None) is not None
    }
    logged_attrs = dict(attrs)
    if "details" in logged_attrs and "failing row" in str(logged_attrs["details"]).lower():
        logged_attrs["details"] = "<fila redactada>"
    print(
        "[EVENTOS_ADMIN][ERROR]",
        f"operacion={operacion}",
        f"tipo={type(ex).__module__}.{type(ex).__name__}",
        f"repr={ex!r}",
        f"mensaje={str(ex)}",
        f"atributos={logged_attrs}",
    )
    trace = traceback.format_exc()
    if trace.strip() == "NoneType: None":
        trace = "".join(traceback.format_exception(ex))
    print("[EVENTOS_ADMIN][ERROR] traceback=", trace.rstrip())
    text = " ".join([str(ex), *(str(value) for value in attrs.values())]).lower()
    code = str(attrs.get("code") or "").upper()
    if code == "23505" or "duplicate" in text or "unique" in text:
        return ResultadoEvento(False, "duplicate", "Ya existe un evento con los datos indicados.")
    if "permission" in text or "row-level security" in text:
        return ResultadoEvento(False, "permission_denied", "No tienes permisos para realizar esta accion.")
    network_markers = (
        "timeout", "timed out", "dns", "name resolution", "connection refused",
        "connecterror", "ssl", "network unavailable", "network down",
    )
    if any(marker in text for marker in network_markers):
        return ResultadoEvento(False, "connection_error", "No fue posible comunicarse con el servicio de datos. Intente nuevamente.")
    constraint_messages = {
        "chk_eve_tipo_evento": "El tipo de evento seleccionado no es valido.",
        "chk_eve_fechas": "La fecha y hora final deben ser posteriores al inicio.",
        "chk_eve_estado": "El estado del evento no es valido.",
        "chk_eve_fase_evento": "La fase del evento no es valida.",
        "chk_eve_cant_mesas": "La cantidad de mesas no puede ser negativa.",
    }
    for constraint, message in constraint_messages.items():
        if constraint in text:
            return ResultadoEvento(False, "constraint_error", message)
    if code in {"23514", "23502", "23503", "22P02"} or code.startswith("PGRST"):
        return ResultadoEvento(False, "constraint_error", "No fue posible guardar el evento porque uno de los valores no es valido.")
    if any(marker in text for marker in ("check constraint", "violates check", "invalid input", "null value", "pgrst", "apierror", "400", "409", "422")):
        return ResultadoEvento(False, "constraint_error", "No fue posible guardar el evento porque uno de los valores no es valido.")
    return ResultadoEvento(False, "data_error", "El servicio de datos rechazo la operacion. Revisa el detalle tecnico registrado.")


def _autorizar(
    contexto: dict[str, Any] | None,
    cuenta_activa: dict[str, Any] | None,
    capacidad: Callable[[dict[str, Any] | None], bool],
) -> tuple[int | None, ResultadoEvento | None]:
    if not contexto or not contexto.get("usr_usuario_id"):
        return None, ResultadoEvento(False, "session_invalid", "La sesion no es valida.")
    cuenta = cuenta_activa or contexto.get("cuenta_actual") or {}
    cuenta_id = _id(cuenta.get("cuenta_id"))
    actual_id = _id((contexto.get("cuenta_actual") or {}).get("cuenta_id"))
    permitidas = {_id(item.get("cuenta_id")) for item in contexto.get("cuentas_permitidas", []) or []}
    if cuenta_id is None:
        return None, ResultadoEvento(False, "account_required", "Selecciona una cuenta antes de continuar.")
    if cuenta_id not in permitidas:
        return None, ResultadoEvento(False, "account_denied", "No tienes acceso a la cuenta seleccionada.")
    if actual_id is not None and actual_id != cuenta_id:
        return None, ResultadoEvento(False, "account_changed", "La cuenta activa cambio. Vuelve a abrir el modulo.")
    if not capacidad(contexto):
        return None, ResultadoEvento(False, "role_denied", "No tienes permisos para administrar eventos.")
    return cuenta_id, None


def _obtener_fila(supabase: Any, cuenta_id: int, evento_id: int) -> dict[str, Any] | None:
    rows = _filas(
        supabase.table("evp_eve_evento").select(SELECT_EVENTO)
        .eq("eve_cuenta_id", cuenta_id).eq("eve_evento_id", evento_id).limit(1).execute()
    )
    return rows[0] if rows else None


def _validar_fechas(inicio: Any, fin: Any) -> str | None:
    if not inicio:
        return "La fecha y hora de inicio son requeridas."
    try:
        ini = datetime.fromisoformat(str(inicio).replace("Z", "+00:00"))
        final = datetime.fromisoformat(str(fin).replace("Z", "+00:00")) if fin else None
    except ValueError:
        return "La fecha u hora no tiene un formato valido."
    if final is not None and final <= ini:
        return "La fecha y hora final deben ser posteriores al inicio."
    return None


def _datetime_normalizado(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    parsed = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
    parsed = parsed.replace(microsecond=0)
    if parsed.tzinfo is not None:
        return parsed.astimezone(timezone.utc)
    return parsed


def _datetime_equivalente(left: Any, right: Any) -> bool:
    try:
        return _datetime_normalizado(left) == _datetime_normalizado(right)
    except (TypeError, ValueError):
        return str(left or "").strip() == str(right or "").strip()


def _datetime_iso(value: Any) -> str | None:
    if value in (None, ""):
        return None
    parsed = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00")).replace(microsecond=0)
    return parsed.isoformat() if parsed is not None else None


def listar_eventos_administrables(
    contexto_usuario: dict[str, Any] | None,
    cuenta_activa: dict[str, Any] | None = None,
    supabase: Any = None,
) -> ResultadoEventos:
    cuenta_id, error = _autorizar(contexto_usuario, cuenta_activa, puede_ver_administracion_eventos)
    if error:
        return ResultadoEventos(False, error.estado, error.mensaje, [])
    try:
        rows = _filas(
            supabase.table("evp_eve_evento").select(SELECT_EVENTO)
            .eq("eve_cuenta_id", cuenta_id).order("eve_fecha_hora_inicio", desc=True).execute()
        )
        eventos = [item for row in rows if (item := normalizar_evento(row))]
        return ResultadoEventos(True, "ready" if eventos else "empty", "Eventos cargados." if eventos else "La cuenta no tiene eventos.", eventos)
    except Exception as ex:
        result = _error(ex)
        return ResultadoEventos(False, result.estado, result.mensaje, [])


def obtener_evento(
    contexto_usuario: dict[str, Any] | None,
    evento_id: Any,
    cuenta_activa: dict[str, Any] | None = None,
    supabase: Any = None,
) -> ResultadoEvento:
    cuenta_id, error = _autorizar(contexto_usuario, cuenta_activa, puede_ver_administracion_eventos)
    if error:
        return error
    target_id = _id(evento_id)
    if target_id is None:
        return ResultadoEvento(False, "validation", "El evento no es valido.")
    try:
        row = _obtener_fila(supabase, cuenta_id, target_id)
        event = normalizar_evento(row) if row else None
        return ResultadoEvento(bool(event), "ready" if event else "not_found", "Evento cargado." if event else "El evento no existe en la cuenta activa.", event)
    except Exception as ex:
        return _error(ex)


def validar_ubicacion_evento(
    contexto_usuario: dict[str, Any] | None,
    lugar_id: Any,
    salon_id: Any,
    cuenta_activa: dict[str, Any] | None = None,
    supabase: Any = None,
) -> ResultadoEvento:
    cuenta_id, error = _autorizar(contexto_usuario, cuenta_activa, puede_cambiar_ubicacion_evento)
    if error:
        return error
    lugar, salon = _id(lugar_id), _id(salon_id)
    if lugar is None or salon is None:
        return ResultadoEvento(False, "validation", "Selecciona un lugar y un salon.")
    try:
        places = _filas(
            supabase.table("evp_lug_lugar").select("lug_lugar_id,lug_estado")
            .eq("lug_cuenta_id", cuenta_id).eq("lug_lugar_id", lugar).eq("lug_estado", "Activo").limit(1).execute()
        )
        rooms = _filas(
            supabase.table("evp_sal_salon").select("sal_salon_id,sal_estado")
            .eq("sal_cuenta_id", cuenta_id).eq("sal_lugar_id", lugar)
            .eq("sal_salon_id", salon).eq("sal_estado", "Activo").limit(1).execute()
        )
        if not places or not rooms:
            return ResultadoEvento(False, "invalid_location", "El lugar y el salon deben pertenecer a la cuenta, estar relacionados y activos.")
        return ResultadoEvento(True, "valid", "Ubicacion valida.")
    except Exception as ex:
        return _error(ex)


def listar_lugares_disponibles(contexto_usuario: dict[str, Any] | None, cuenta_activa: dict[str, Any] | None = None, supabase: Any = None) -> list[dict[str, Any]]:
    cuenta_id, error = _autorizar(contexto_usuario, cuenta_activa, puede_ver_administracion_eventos)
    if error:
        return []
    return _filas(supabase.table("evp_lug_lugar").select("lug_cuenta_id,lug_lugar_id,lug_nombre_lugar,lug_estado").eq("lug_cuenta_id", cuenta_id).eq("lug_estado", "Activo").order("lug_nombre_lugar").execute())


def listar_salones_disponibles(contexto_usuario: dict[str, Any] | None, lugar_id: Any, cuenta_activa: dict[str, Any] | None = None, supabase: Any = None) -> list[dict[str, Any]]:
    cuenta_id, error = _autorizar(contexto_usuario, cuenta_activa, puede_ver_administracion_eventos)
    lugar = _id(lugar_id)
    if error or lugar is None:
        return []
    return _filas(supabase.table("evp_sal_salon").select("sal_cuenta_id,sal_lugar_id,sal_salon_id,sal_nombre_salon,sal_cant_max_mesas,sal_cant_max_invitados,sal_estado").eq("sal_cuenta_id", cuenta_id).eq("sal_lugar_id", lugar).eq("sal_estado", "Activo").order("sal_nombre_salon").execute())


def crear_evento(
    contexto_usuario: dict[str, Any] | None,
    datos: dict[str, Any],
    cuenta_activa: dict[str, Any] | None = None,
    supabase: Any = None,
) -> ResultadoEvento:
    print("[EVENTOS_ADMIN][INFO] Inicio de creacion de evento.")
    cuenta_id, error = _autorizar(contexto_usuario, cuenta_activa, puede_crear_evento)
    if error:
        return error
    nombre = _texto(datos.get("nombre_evento"))
    if not nombre:
        return ResultadoEvento(False, "validation", "El nombre del evento es requerido.")
    date_error = _validar_fechas(datos.get("fecha_hora_inicio"), datos.get("fecha_hora_fin"))
    if date_error:
        return ResultadoEvento(False, "validation", date_error)
    fase = _texto(datos.get("fase_evento")) or "Pre_evento"
    estado = _texto(datos.get("estado")) or "Activo"
    tipo = normalizar_tipo_evento(datos.get("tipo_evento"))
    if tipo not in TIPOS_EVENTO_VALIDOS:
        return ResultadoEvento(False, "invalid_type", "El tipo de evento seleccionado no es valido.")
    if fase != "Pre_evento" or estado not in ESTADOS_EVENTO:
        return ResultadoEvento(False, "validation", "La fase o estado inicial no es valido.")
    location = validar_ubicacion_evento(contexto_usuario, datos.get("lugar_id"), datos.get("salon_id"), cuenta_activa, supabase)
    if not location.ok:
        return location
    payload = {
        "eve_cuenta_id": cuenta_id,
        "eve_nombre_evento": nombre,
        "eve_nombre_evento_abrev": _texto(datos.get("nombre_evento_abrev")) or None,
        "eve_fase_evento": fase,
        "eve_tipo_evento": tipo,
        "eve_lugar_id": _id(datos.get("lugar_id")),
        "eve_salon_id": _id(datos.get("salon_id")),
        "eve_cant_mesas": _id(datos.get("cant_mesas")),
        "eve_fecha_hora_inicio": _datetime_iso(datos.get("fecha_hora_inicio")),
        "eve_fecha_hora_fin": _datetime_iso(datos.get("fecha_hora_fin")),
        "eve_estado": estado,
    }
    try:
        print(
            "[EVENTOS_ADMIN][INFO] Validacion superada; insertando evento:",
            f"cuenta={cuenta_id}",
            f"fase={fase}",
            f"estado={estado}",
            f"payload={_payload_seguro(payload)}",
        )
        rows = _filas(supabase.table("evp_eve_evento").insert(payload).execute())
        print("[EVENTOS_ADMIN][INFO] Respuesta de insercion:", f"filas={len(rows)}")
        if not rows:
            return ResultadoEvento(
                False,
                "empty_response",
                "Supabase no devolvio el evento creado. Recarga la lista antes de intentar nuevamente.",
            )
        event = normalizar_evento(rows[0]) if rows else None
        return ResultadoEvento(True, "created", "Evento creado correctamente.", event)
    except Exception as ex:
        return _error(ex, "INSERT")


def verificar_dependencias_evento(
    contexto_usuario: dict[str, Any] | None,
    evento_id: Any,
    cuenta_activa: dict[str, Any] | None = None,
    supabase: Any = None,
) -> ResultadoDependenciasEvento:
    cuenta_id, error = _autorizar(contexto_usuario, cuenta_activa, puede_ver_administracion_eventos)
    target = _id(evento_id)
    if error or target is None:
        return ResultadoDependenciasEvento(False, True, error.mensaje if error else "Evento invalido.", {})
    specs = {
        "mesas": ("evp_mes_mesa", "mes_cuenta_id", "mes_evento_id"),
        "invitaciones": ("evp_inv_invitacion", "inv_cuenta_id", "inv_evento_id"),
        "invitados": ("evp_ivt_invitado", "ivt_cuenta_id", "ivt_evento_id"),
    }
    try:
        counts: dict[str, int] = {}
        for label, (table, account_col, event_col) in specs.items():
            rows = _filas(supabase.table(table).select(event_col).eq(account_col, cuenta_id).eq(event_col, target).limit(1).execute())
            counts[label] = len(rows)
        blocked = any(counts.values())
        return ResultadoDependenciasEvento(True, blocked, "Existen dependencias estructurales." if blocked else "No hay dependencias incompatibles.", counts)
    except Exception as ex:
        print("[EVENTOS_ADMIN][ERROR] dependencias", type(ex).__name__, str(ex))
        return ResultadoDependenciasEvento(False, True, "No fue posible verificar las dependencias.", {})


def actualizar_evento(
    contexto_usuario: dict[str, Any] | None,
    evento_id: Any,
    cambios: dict[str, Any],
    cuenta_activa: dict[str, Any] | None = None,
    supabase: Any = None,
) -> ResultadoEvento:
    cuenta_id, error = _autorizar(contexto_usuario, cuenta_activa, puede_editar_evento)
    if error:
        return error
    target = _id(evento_id)
    current = _obtener_fila(supabase, cuenta_id, target) if target is not None else None
    if not current:
        return ResultadoEvento(False, "not_found", "El evento no existe en la cuenta activa.")
    fase_actual = str(safe_get(current, "eve_fase_evento") or "")
    if fase_actual in {"Post_evento", "Cerrado"}:
        return ResultadoEvento(
            False,
            "phase_denied",
            f"El evento esta en fase {fase_actual} y permanece en solo lectura.",
        )
    forbidden = set(cambios) - _CAMPOS_EDITABLES - {"lugar_id", "salon_id"}
    if forbidden:
        return ResultadoEvento(False, "protected_field", "La solicitud contiene campos protegidos.")
    payload: dict[str, Any] = {}
    if "nombre_evento" in cambios and not _texto(cambios.get("nombre_evento")):
        return ResultadoEvento(False, "validation", "El nombre del evento es requerido.")
    inicio = cambios.get("fecha_hora_inicio", safe_get(current, "eve_fecha_hora_inicio"))
    fin = cambios.get("fecha_hora_fin", safe_get(current, "eve_fecha_hora_fin"))
    date_error = _validar_fechas(inicio, fin)
    if date_error:
        return ResultadoEvento(False, "validation", date_error)
    text_specs = {
        "nombre_evento": ("eve_nombre_evento", "eve_nombre_evento"),
        "nombre_evento_abrev": ("eve_nombre_evento_abrev", "eve_nombre_evento_abrev"),
        "tipo_evento": ("eve_tipo_evento", "eve_tipo_evento"),
    }
    for key, (column, current_column) in text_specs.items():
        if key not in cambios:
            continue
        new_value = normalizar_tipo_evento(cambios[key]) if key == "tipo_evento" else _texto(cambios[key])
        old_value = normalizar_tipo_evento(safe_get(current, current_column)) if key == "tipo_evento" else _texto(safe_get(current, current_column))
        if new_value != old_value:
            if key == "tipo_evento" and new_value not in TIPOS_EVENTO_VALIDOS:
                return ResultadoEvento(False, "invalid_type", "El tipo de evento seleccionado no es valido.")
            payload[column] = new_value or None

    for key, column in (
        ("fecha_hora_inicio", "eve_fecha_hora_inicio"),
        ("fecha_hora_fin", "eve_fecha_hora_fin"),
    ):
        if key in cambios and not _datetime_equivalente(cambios[key], safe_get(current, column)):
            payload[column] = _datetime_iso(cambios[key])

    structural_changes: set[str] = set()
    if "cant_mesas" in cambios:
        new_tables = _id(cambios.get("cant_mesas"))
        if new_tables != _id(safe_get(current, "eve_cant_mesas")):
            payload["eve_cant_mesas"] = new_tables
            structural_changes.add("cant_mesas")

    current_place = _id(safe_get(current, "eve_lugar_id"))
    current_room = _id(safe_get(current, "eve_salon_id"))
    new_place = _id(cambios.get("lugar_id", current_place))
    new_room = _id(cambios.get("salon_id", current_room))
    if new_place != current_place:
        structural_changes.add("lugar_id")
    if new_room != current_room:
        structural_changes.add("salon_id")

    if fase_actual == "En_proceso" and (structural_changes or "eve_tipo_evento" in payload):
        return ResultadoEvento(
            False,
            "phase_denied",
            "Este evento solo permite modificar datos no estructurales mientras esta En_proceso.",
        )
    if structural_changes:
        deps = verificar_dependencias_evento(contexto_usuario, target, cuenta_activa, supabase)
        if not deps.ok or deps.bloquea:
            return ResultadoEvento(False, "dependencies", deps.mensaje)
        if structural_changes & {"lugar_id", "salon_id"}:
            valid = validar_ubicacion_evento(
                contexto_usuario,
                new_place,
                new_room,
                cuenta_activa,
                supabase,
            )
            if not valid.ok:
                return valid
            payload.update({"eve_lugar_id": new_place, "eve_salon_id": new_room})
    if not payload:
        return ResultadoEvento(False, "no_changes", "No se realizaron cambios.")
    try:
        print(
            "[EVENTOS_ADMIN][INFO] Actualizando evento:",
            f"cuenta={cuenta_id}",
            f"evento={target}",
            f"fase={fase_actual}",
            f"payload={_payload_seguro(payload)}",
            f"filtros={{'eve_cuenta_id': {cuenta_id}, 'eve_evento_id': {target}, 'eve_fase_evento': {fase_actual!r}}}",
        )
        rows = _filas(
            supabase.table("evp_eve_evento").update(payload)
            .eq("eve_cuenta_id", cuenta_id).eq("eve_evento_id", target)
            .eq("eve_fase_evento", fase_actual).execute()
        )
        if not rows:
            return ResultadoEvento(False, "not_updated", "No se encontro el evento o ya no esta disponible para modificacion.")
        return ResultadoEvento(True, "updated", "Evento actualizado correctamente.", normalizar_evento(rows[0]))
    except Exception as ex:
        return _error(ex, "UPDATE")


def cambiar_estado_evento(contexto_usuario: dict[str, Any] | None, evento_id: Any, nuevo_estado: str, cuenta_activa: dict[str, Any] | None = None, supabase: Any = None) -> ResultadoEvento:
    capability = puede_activar_evento if nuevo_estado == "Activo" else puede_desactivar_evento
    cuenta_id, error = _autorizar(contexto_usuario, cuenta_activa, capability)
    if error:
        return error
    if nuevo_estado not in ESTADOS_EVENTO:
        return ResultadoEvento(False, "validation", "El estado solicitado no es valido.")
    target = _id(evento_id)
    current = _obtener_fila(supabase, cuenta_id, target) if target is not None else None
    if not current:
        return ResultadoEvento(False, "not_found", "El evento no existe en la cuenta activa.")
    if safe_get(current, "eve_fase_evento") in {"Post_evento", "Cerrado"}:
        return ResultadoEvento(False, "phase_denied", "Un evento cerrado no admite cambios ordinarios de estado.")
    try:
        rows = _filas(supabase.table("evp_eve_evento").update({"eve_estado": nuevo_estado}).eq("eve_cuenta_id", cuenta_id).eq("eve_evento_id", target).eq("eve_estado", safe_get(current, "eve_estado")).execute())
        if not rows:
            return ResultadoEvento(False, "conflict", "El estado cambio mientras realizabas la operacion.")
        return ResultadoEvento(True, "updated", "Estado actualizado.", normalizar_evento(rows[0]))
    except Exception as ex:
        return _error(ex)


def obtener_transiciones_permitidas(evento: dict[str, Any] | None) -> tuple[str, ...]:
    if not evento or evento.get("estado") != "Activo":
        return ()
    return TRANSICIONES_FASE.get(str(evento.get("fase_evento") or ""), ())


def cambiar_fase_evento(contexto_usuario: dict[str, Any] | None, evento_id: Any, nueva_fase: str, cuenta_activa: dict[str, Any] | None = None, supabase: Any = None) -> ResultadoEvento:
    capability = puede_iniciar_evento if nueva_fase == "En_proceso" else puede_cerrar_evento
    cuenta_id, error = _autorizar(contexto_usuario, cuenta_activa, capability)
    if error:
        return error
    target = _id(evento_id)
    current = _obtener_fila(supabase, cuenta_id, target) if target is not None else None
    event = normalizar_evento(current) if current else None
    if not event:
        return ResultadoEvento(False, "not_found", "El evento no existe en la cuenta activa.")
    if nueva_fase not in obtener_transiciones_permitidas(event):
        return ResultadoEvento(False, "invalid_transition", "La transicion de fase solicitada no esta permitida.")
    if nueva_fase == "En_proceso":
        if not event.get("fecha_hora_inicio") or not event.get("lugar_id") or not event.get("salon_id"):
            return ResultadoEvento(False, "validation", "El evento no tiene la configuracion minima para iniciar.")
        location = validar_ubicacion_evento(contexto_usuario, event["lugar_id"], event["salon_id"], cuenta_activa, supabase)
        if not location.ok:
            return location
    try:
        rows = _filas(supabase.table("evp_eve_evento").update({"eve_fase_evento": nueva_fase}).eq("eve_cuenta_id", cuenta_id).eq("eve_evento_id", target).eq("eve_fase_evento", event["fase_evento"]).eq("eve_estado", "Activo").execute())
        if not rows:
            return ResultadoEvento(False, "conflict", "La fase o el estado cambio mientras realizabas la operacion.")
        return ResultadoEvento(True, "updated", "Fase actualizada.", normalizar_evento(rows[0]))
    except Exception as ex:
        return _error(ex)


def iniciar_evento(contexto_usuario: dict[str, Any] | None, evento_id: Any, cuenta_activa: dict[str, Any] | None = None, supabase: Any = None) -> ResultadoEvento:
    return cambiar_fase_evento(contexto_usuario, evento_id, "En_proceso", cuenta_activa, supabase)


def cerrar_evento(contexto_usuario: dict[str, Any] | None, evento_id: Any, cuenta_activa: dict[str, Any] | None = None, supabase: Any = None) -> ResultadoEvento:
    return cambiar_fase_evento(contexto_usuario, evento_id, "Post_evento", cuenta_activa, supabase)


def establecer_evento_predeterminado(contexto_usuario: dict[str, Any] | None, evento_id: Any, cuenta_activa: dict[str, Any] | None = None, supabase: Any = None) -> ResultadoEvento:
    cuenta_id, error = _autorizar(contexto_usuario, cuenta_activa, puede_establecer_evento_predeterminado)
    if error:
        return error
    target = _id(evento_id)
    current = _obtener_fila(supabase, cuenta_id, target) if target is not None else None
    event = normalizar_evento(current) if current else None
    if not event or event.get("estado") != "Activo":
        return ResultadoEvento(False, "validation", "Solo un evento activo de la cuenta puede ser predeterminado.")
    try:
        rows = _filas(
            supabase.table("evp_usr_usuario")
            .update({"usr_cuenta_id_default": cuenta_id, "usr_evento_id_default": target})
            .eq("usr_usuario_id", contexto_usuario.get("usr_usuario_id")).execute()
        )
        if not rows:
            return ResultadoEvento(False, "conflict", "No fue posible actualizar la preferencia del usuario.")
        contexto_usuario["usr_cuenta_id_default"] = cuenta_id
        contexto_usuario["usr_evento_id_default"] = target
        return ResultadoEvento(True, "updated", "Evento predeterminado actualizado para tu usuario.", event)
    except Exception as ex:
        return _error(ex)


def obtener_eventos_disponibles(contexto_usuario: dict[str, Any] | None, supabase: Any = None) -> ResultadoEventos:
    if not contexto_usuario or not contexto_usuario.get("usr_usuario_id"):
        return ResultadoEventos(False, "session_invalid", "La sesion no es valida. Inicia sesion nuevamente.", [])
    allowed = contexto_usuario.get("eventos_permitidos") or []
    if not allowed:
        return ResultadoEventos(True, "empty", "No tienes eventos disponibles en este momento.", [])
    events: list[dict[str, Any]] = []
    seen: set[tuple[int, int]] = set()
    try:
        for context_event in allowed:
            key = evento_key(context_event)
            if key is None or key in seen:
                continue
            seen.add(key)
            row = _obtener_fila(supabase, *key)
            event = normalizar_evento(row, context_event) if row else None
            if event:
                events.append(event)
    except Exception as ex:
        result = _error(ex)
        return ResultadoEventos(False, result.estado, result.mensaje, [])
    events.sort(key=lambda item: (item["cuenta_id"], item["evento_id"]))
    return ResultadoEventos(True, "ready" if events else "empty", "Eventos cargados correctamente." if events else "No tienes eventos disponibles en este momento.", events)
