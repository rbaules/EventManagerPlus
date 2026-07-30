from __future__ import annotations

from dataclasses import dataclass
import unicodedata
from typing import Any

from services.authorization_service import (
    puede_administrar_lugares,
    puede_crear_lugar,
    puede_crear_salon,
    puede_desactivar_lugar,
    puede_desactivar_salon,
    puede_editar_lugar,
    puede_editar_salon,
)
from services.response_utils import extract_data, safe_get, to_dict


ESTADOS = frozenset({"Activo", "Suspendido", "Inactivo"})
TIPOS_LUGAR = frozenset({"Hotel", "Sala de eventos", "Otro"})
SELECT_LUGAR = (
    "lug_cuenta_id,lug_lugar_id,lug_nombre_lugar,lug_direccion,"
    "lug_ciudad,lug_pais_id,lug_tipo_lugar,lug_estado"
)
SELECT_SALON = (
    "sal_cuenta_id,sal_lugar_id,sal_salon_id,sal_nombre_salon,"
    "sal_ubicacion,sal_cant_max_mesas,sal_cant_max_invitados,sal_estado"
)


@dataclass(frozen=True)
class ResultadoLista:
    ok: bool
    estado: str
    mensaje: str
    items: list[dict[str, Any]]


@dataclass(frozen=True)
class ResultadoOperacion:
    ok: bool
    estado: str
    mensaje: str
    item: dict[str, Any] | None = None


@dataclass(frozen=True)
class ResultadoDependencias:
    ok: bool
    bloquea: bool
    mensaje: str
    eventos: list[dict[str, Any]]


def _texto(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _id(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _normalizar(value: Any) -> str:
    texto = unicodedata.normalize("NFKD", _texto(value).lower())
    return "".join(char for char in texto if not unicodedata.combining(char))


def _filas(response: Any) -> list[dict[str, Any]]:
    return [row for value in extract_data(response) if (row := to_dict(value))]


def _resultado_error(ex: Exception) -> ResultadoOperacion:
    print("[LUGARES][ERROR]", type(ex).__name__, str(ex))
    mensaje = str(ex).lower()
    if "duplicate" in mensaje or "unique" in mensaje:
        return ResultadoOperacion(False, "duplicate", "Ya existe un registro con ese nombre.")
    if "permission" in mensaje or "row-level security" in mensaje:
        return ResultadoOperacion(False, "permission_denied", "No tienes permisos para realizar esta accion.")
    return ResultadoOperacion(False, "connection_error", "No fue posible guardar los cambios. Intenta nuevamente.")


def _cuenta_contexto(
    contexto: dict[str, Any] | None,
    cuenta_activa: dict[str, Any] | None = None,
) -> tuple[int | None, ResultadoOperacion | None]:
    if not contexto or not contexto.get("usr_usuario_id"):
        return None, ResultadoOperacion(False, "session_invalid", "La sesion no es valida.")
    cuenta = cuenta_activa or contexto.get("cuenta_actual") or {}
    cuenta_id = _id(cuenta.get("cuenta_id"))
    if cuenta_id is None:
        return None, ResultadoOperacion(False, "account_required", "Selecciona una cuenta antes de continuar.")
    permitidas = {
        _id(item.get("cuenta_id"))
        for item in contexto.get("cuentas_permitidas", []) or []
    }
    if cuenta_id not in permitidas:
        return None, ResultadoOperacion(False, "account_denied", "No tienes acceso a la cuenta seleccionada.")
    actual_id = _id((contexto.get("cuenta_actual") or {}).get("cuenta_id"))
    if actual_id is not None and cuenta_id != actual_id:
        return None, ResultadoOperacion(False, "account_changed", "La cuenta activa cambio. Vuelve a abrir el modulo.")
    return cuenta_id, None


def _autorizar(
    contexto: dict[str, Any] | None,
    capacidad: Any,
    cuenta_activa: dict[str, Any] | None = None,
) -> tuple[int | None, ResultadoOperacion | None]:
    cuenta_id, error = _cuenta_contexto(contexto, cuenta_activa)
    if error:
        return None, error
    if not capacidad(contexto):
        return None, ResultadoOperacion(False, "role_denied", "No tienes permisos para administrar lugares y salones.")
    return cuenta_id, None


def _lugar(row: dict[str, Any]) -> dict[str, Any] | None:
    cuenta_id = _id(safe_get(row, "lug_cuenta_id"))
    lugar_id = _id(safe_get(row, "lug_lugar_id"))
    if cuenta_id is None or lugar_id is None:
        return None
    return {
        "cuenta_id": cuenta_id,
        "lugar_id": lugar_id,
        "nombre": _texto(safe_get(row, "lug_nombre_lugar")),
        "direccion": _texto(safe_get(row, "lug_direccion")),
        "ciudad": _texto(safe_get(row, "lug_ciudad")),
        "pais_id": _texto(safe_get(row, "lug_pais_id")),
        "tipo": _texto(safe_get(row, "lug_tipo_lugar")) or "Otro",
        "estado": _texto(safe_get(row, "lug_estado")) or "Activo",
    }


def _salon(row: dict[str, Any]) -> dict[str, Any] | None:
    cuenta_id = _id(safe_get(row, "sal_cuenta_id"))
    lugar_id = _id(safe_get(row, "sal_lugar_id"))
    salon_id = _id(safe_get(row, "sal_salon_id"))
    if cuenta_id is None or lugar_id is None or salon_id is None:
        return None
    return {
        "cuenta_id": cuenta_id,
        "lugar_id": lugar_id,
        "salon_id": salon_id,
        "nombre": _texto(safe_get(row, "sal_nombre_salon")),
        "ubicacion": _texto(safe_get(row, "sal_ubicacion")),
        "cant_max_mesas": _id(safe_get(row, "sal_cant_max_mesas")),
        "cant_max_invitados": _id(safe_get(row, "sal_cant_max_invitados")),
        "estado": _texto(safe_get(row, "sal_estado")) or "Activo",
    }


def listar_paises(supabase: Any) -> ResultadoLista:
    try:
        rows = _filas(
            supabase.table("evp_pai_pais")
            .select("pai_pais_id,pai_nombre_pais")
            .order("pai_nombre_pais")
            .execute()
        )
    except Exception as ex:
        print("[LUGARES][ERROR] paises", type(ex).__name__, str(ex))
        return ResultadoLista(False, "connection_error", "No fue posible cargar los paises.", [])
    return ResultadoLista(
        True,
        "ready" if rows else "empty",
        "",
        [
            {"pais_id": _texto(row.get("pai_pais_id")), "nombre": _texto(row.get("pai_nombre_pais"))}
            for row in rows
        ],
    )


def listar_lugares(
    supabase: Any,
    contexto: dict[str, Any] | None,
    cuenta_activa: dict[str, Any] | None = None,
) -> ResultadoLista:
    cuenta_id, error = _autorizar(contexto, puede_administrar_lugares, cuenta_activa)
    if error:
        return ResultadoLista(False, error.estado, error.mensaje, [])
    try:
        rows = _filas(
            supabase.table("evp_lug_lugar")
            .select(SELECT_LUGAR)
            .eq("lug_cuenta_id", cuenta_id)
            .order("lug_nombre_lugar")
            .execute()
        )
    except Exception as ex:
        print("[LUGARES][ERROR] listar", type(ex).__name__, str(ex))
        return ResultadoLista(False, "connection_error", "No fue posible cargar los lugares.", [])
    items = [item for row in rows if (item := _lugar(row))]
    return ResultadoLista(True, "ready" if items else "empty", "", items)


def obtener_lugar(
    supabase: Any,
    contexto: dict[str, Any] | None,
    lugar_id: Any,
    cuenta_activa: dict[str, Any] | None = None,
) -> ResultadoOperacion:
    cuenta_id, error = _autorizar(contexto, puede_administrar_lugares, cuenta_activa)
    if error:
        return error
    lugar_id = _id(lugar_id)
    if lugar_id is None:
        return ResultadoOperacion(False, "not_found", "No fue posible identificar el lugar.")
    try:
        rows = _filas(
            supabase.table("evp_lug_lugar").select(SELECT_LUGAR)
            .eq("lug_cuenta_id", cuenta_id).eq("lug_lugar_id", lugar_id)
            .limit(1).execute()
        )
    except Exception as ex:
        return _resultado_error(ex)
    item = _lugar(rows[0]) if rows else None
    return ResultadoOperacion(bool(item), "ready" if item else "not_found", "" if item else "El lugar no existe o no esta disponible.", item)


def _validar_lugar_payload(payload: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    if {"lug_cuenta_id", "lug_lugar_id", "cuenta_id", "lugar_id"}.intersection(payload):
        return None, "No se permite modificar identificadores del lugar."
    nombre = _texto(payload.get("nombre"))
    tipo = _texto(payload.get("tipo")) or "Otro"
    if not nombre or len(nombre) > 50:
        return None, "El nombre del lugar es obligatorio y admite hasta 50 caracteres."
    if tipo not in TIPOS_LUGAR:
        return None, "El tipo de lugar no es valido."
    direccion = _texto(payload.get("direccion"))
    ciudad = _texto(payload.get("ciudad"))
    pais_id = _texto(payload.get("pais_id")).upper()
    if len(direccion) > 150 or len(ciudad) > 50 or len(pais_id) > 2:
        return None, "Uno de los campos excede la longitud permitida."
    return {
        "lug_nombre_lugar": nombre,
        "lug_direccion": direccion or None,
        "lug_ciudad": ciudad or None,
        "lug_pais_id": pais_id or None,
        "lug_tipo_lugar": tipo,
    }, None


def _duplicado_lugar(supabase: Any, cuenta_id: int, nombre: str, excluir: int | None = None) -> bool:
    rows = _filas(
        supabase.table("evp_lug_lugar").select("lug_cuenta_id,lug_lugar_id,lug_nombre_lugar")
        .eq("lug_cuenta_id", cuenta_id).execute()
    )
    normalizado = _normalizar(nombre)
    return any(
        _id(row.get("lug_lugar_id")) != excluir
        and _normalizar(row.get("lug_nombre_lugar")) == normalizado
        for row in rows
    )


def crear_lugar(supabase: Any, contexto: dict[str, Any] | None, payload: dict[str, Any], cuenta_activa: dict[str, Any] | None = None) -> ResultadoOperacion:
    cuenta_id, error = _autorizar(contexto, puede_crear_lugar, cuenta_activa)
    if error:
        return error
    datos, mensaje = _validar_lugar_payload(payload)
    if mensaje:
        return ResultadoOperacion(False, "invalid_data", mensaje)
    assert datos is not None and cuenta_id is not None
    try:
        if _duplicado_lugar(supabase, cuenta_id, datos["lug_nombre_lugar"]):
            return ResultadoOperacion(False, "duplicate", "Ya existe un lugar con ese nombre en la cuenta.")
        rows = _filas(
            supabase.table("evp_lug_lugar")
            .insert({"lug_cuenta_id": cuenta_id, **datos, "lug_estado": "Activo"})
            .execute()
        )
    except Exception as ex:
        return _resultado_error(ex)
    item = _lugar(rows[0]) if rows else None
    return ResultadoOperacion(bool(item), "success" if item else "unexpected_response", "Lugar creado correctamente." if item else "El lugar fue guardado, pero no se pudo leer.", item)


def actualizar_lugar(supabase: Any, contexto: dict[str, Any] | None, lugar_id: Any, payload: dict[str, Any], cuenta_activa: dict[str, Any] | None = None) -> ResultadoOperacion:
    cuenta_id, error = _autorizar(contexto, puede_editar_lugar, cuenta_activa)
    if error:
        return error
    actual = obtener_lugar(supabase, contexto, lugar_id, cuenta_activa)
    if not actual.ok:
        return actual
    datos, mensaje = _validar_lugar_payload(payload)
    if mensaje:
        return ResultadoOperacion(False, "invalid_data", mensaje)
    assert datos is not None and cuenta_id is not None and actual.item is not None
    if actual.item["estado"] not in ESTADOS:
        return ResultadoOperacion(False, "invalid_state", "El lugar tiene un estado no reconocido.")
    try:
        if _duplicado_lugar(supabase, cuenta_id, datos["lug_nombre_lugar"], actual.item["lugar_id"]):
            return ResultadoOperacion(False, "duplicate", "Ya existe un lugar con ese nombre en la cuenta.")
        rows = _filas(
            supabase.table("evp_lug_lugar").update(datos)
            .eq("lug_cuenta_id", cuenta_id).eq("lug_lugar_id", actual.item["lugar_id"]).execute()
        )
    except Exception as ex:
        return _resultado_error(ex)
    item = _lugar(rows[0]) if rows else None
    return ResultadoOperacion(bool(item), "success" if item else "unexpected_response", "Lugar actualizado correctamente." if item else "No se pudo confirmar la actualizacion.", item)


def verificar_dependencias_lugar(supabase: Any, contexto: dict[str, Any] | None, lugar_id: Any, cuenta_activa: dict[str, Any] | None = None) -> ResultadoDependencias:
    cuenta_id, error = _autorizar(contexto, puede_desactivar_lugar, cuenta_activa)
    if error:
        return ResultadoDependencias(False, True, error.mensaje, [])
    try:
        rows = _filas(
            supabase.table("evp_eve_evento")
            .select("eve_cuenta_id,eve_evento_id,eve_nombre_evento,eve_fase_evento,eve_estado,eve_fecha_hora_inicio")
            .eq("eve_cuenta_id", cuenta_id).eq("eve_lugar_id", _id(lugar_id)).eq("eve_estado", "Activo").execute()
        )
    except Exception as ex:
        print("[LUGARES][ERROR] dependencias_lugar", type(ex).__name__, str(ex))
        return ResultadoDependencias(False, True, "No fue posible verificar las dependencias.", [])
    eventos = [row for row in rows if _texto(row.get("eve_fase_evento")) != "Cerrado"]
    return ResultadoDependencias(True, bool(eventos), "El lugar esta asociado a eventos activos o no cerrados." if eventos else "", eventos)


def cambiar_estado_lugar(supabase: Any, contexto: dict[str, Any] | None, lugar_id: Any, estado: str, cuenta_activa: dict[str, Any] | None = None) -> ResultadoOperacion:
    cuenta_id, error = _autorizar(contexto, puede_desactivar_lugar, cuenta_activa)
    if error:
        return error
    if estado not in {"Activo", "Inactivo"}:
        return ResultadoOperacion(False, "invalid_state", "El estado solicitado no es valido.")
    actual = obtener_lugar(supabase, contexto, lugar_id, cuenta_activa)
    if not actual.ok:
        return actual
    if estado == "Inactivo":
        dependencias = verificar_dependencias_lugar(supabase, contexto, lugar_id, cuenta_activa)
        if not dependencias.ok or dependencias.bloquea:
            return ResultadoOperacion(False, "dependency_blocked", dependencias.mensaje or "No se puede desactivar el lugar.")
    try:
        rows = _filas(
            supabase.table("evp_lug_lugar").update({"lug_estado": estado})
            .eq("lug_cuenta_id", cuenta_id).eq("lug_lugar_id", _id(lugar_id)).execute()
        )
    except Exception as ex:
        return _resultado_error(ex)
    item = _lugar(rows[0]) if rows else None
    return ResultadoOperacion(bool(item), "success" if item else "unexpected_response", "Estado del lugar actualizado." if item else "No se pudo confirmar el cambio.", item)


def listar_salones(supabase: Any, contexto: dict[str, Any] | None, lugar_id: Any, cuenta_activa: dict[str, Any] | None = None) -> ResultadoLista:
    cuenta_id, error = _autorizar(contexto, puede_administrar_lugares, cuenta_activa)
    if error:
        return ResultadoLista(False, error.estado, error.mensaje, [])
    lugar = obtener_lugar(supabase, contexto, lugar_id, cuenta_activa)
    if not lugar.ok:
        return ResultadoLista(False, lugar.estado, lugar.mensaje, [])
    try:
        rows = _filas(
            supabase.table("evp_sal_salon").select(SELECT_SALON)
            .eq("sal_cuenta_id", cuenta_id).eq("sal_lugar_id", _id(lugar_id))
            .order("sal_nombre_salon").execute()
        )
    except Exception as ex:
        print("[LUGARES][ERROR] salones", type(ex).__name__, str(ex))
        return ResultadoLista(False, "connection_error", "No fue posible cargar los salones.", [])
    items = [item for row in rows if (item := _salon(row))]
    return ResultadoLista(True, "ready" if items else "empty", "", items)


def obtener_salon(supabase: Any, contexto: dict[str, Any] | None, lugar_id: Any, salon_id: Any, cuenta_activa: dict[str, Any] | None = None) -> ResultadoOperacion:
    cuenta_id, error = _autorizar(contexto, puede_administrar_lugares, cuenta_activa)
    if error:
        return error
    try:
        rows = _filas(
            supabase.table("evp_sal_salon").select(SELECT_SALON)
            .eq("sal_cuenta_id", cuenta_id).eq("sal_lugar_id", _id(lugar_id))
            .eq("sal_salon_id", _id(salon_id)).limit(1).execute()
        )
    except Exception as ex:
        return _resultado_error(ex)
    item = _salon(rows[0]) if rows else None
    return ResultadoOperacion(bool(item), "ready" if item else "not_found", "" if item else "El salon no existe o no esta disponible.", item)


def _validar_salon_payload(payload: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    if {"sal_cuenta_id", "sal_lugar_id", "sal_salon_id", "cuenta_id", "lugar_id", "salon_id"}.intersection(payload):
        return None, "No se permite modificar identificadores del salon."
    nombre = _texto(payload.get("nombre"))
    ubicacion = _texto(payload.get("ubicacion"))
    mesas = _id(payload.get("cant_max_mesas")) if payload.get("cant_max_mesas") not in (None, "") else None
    invitados = _id(payload.get("cant_max_invitados")) if payload.get("cant_max_invitados") not in (None, "") else None
    if not nombre or len(nombre) > 60 or len(ubicacion) > 100:
        return None, "Revisa el nombre y la ubicacion del salon."
    if (mesas is not None and mesas < 0) or (invitados is not None and invitados < 0):
        return None, "Las capacidades no pueden ser negativas."
    return {
        "sal_nombre_salon": nombre,
        "sal_ubicacion": ubicacion or None,
        "sal_cant_max_mesas": mesas,
        "sal_cant_max_invitados": invitados,
    }, None


def _duplicado_salon(supabase: Any, cuenta_id: int, lugar_id: int, nombre: str, excluir: int | None = None) -> bool:
    rows = _filas(
        supabase.table("evp_sal_salon").select("sal_cuenta_id,sal_lugar_id,sal_salon_id,sal_nombre_salon")
        .eq("sal_cuenta_id", cuenta_id).eq("sal_lugar_id", lugar_id).execute()
    )
    normalizado = _normalizar(nombre)
    return any(
        _id(row.get("sal_salon_id")) != excluir
        and _normalizar(row.get("sal_nombre_salon")) == normalizado
        for row in rows
    )


def crear_salon(supabase: Any, contexto: dict[str, Any] | None, lugar_id: Any, payload: dict[str, Any], cuenta_activa: dict[str, Any] | None = None) -> ResultadoOperacion:
    cuenta_id, error = _autorizar(contexto, puede_crear_salon, cuenta_activa)
    if error:
        return error
    lugar = obtener_lugar(supabase, contexto, lugar_id, cuenta_activa)
    if not lugar.ok or lugar.item is None:
        return ResultadoOperacion(False, "place_not_found", "El lugar no pertenece a la cuenta activa.")
    datos, mensaje = _validar_salon_payload(payload)
    if mensaje:
        return ResultadoOperacion(False, "invalid_data", mensaje)
    assert datos is not None and cuenta_id is not None
    try:
        if _duplicado_salon(supabase, cuenta_id, lugar.item["lugar_id"], datos["sal_nombre_salon"]):
            return ResultadoOperacion(False, "duplicate", "Ya existe un salon con ese nombre en el lugar.")
        rows = _filas(
            supabase.table("evp_sal_salon")
            .insert({"sal_cuenta_id": cuenta_id, "sal_lugar_id": lugar.item["lugar_id"], **datos, "sal_estado": "Activo"})
            .execute()
        )
    except Exception as ex:
        return _resultado_error(ex)
    item = _salon(rows[0]) if rows else None
    return ResultadoOperacion(bool(item), "success" if item else "unexpected_response", "Salon creado correctamente." if item else "El salon fue guardado, pero no se pudo leer.", item)


def actualizar_salon(supabase: Any, contexto: dict[str, Any] | None, lugar_id: Any, salon_id: Any, payload: dict[str, Any], cuenta_activa: dict[str, Any] | None = None) -> ResultadoOperacion:
    cuenta_id, error = _autorizar(contexto, puede_editar_salon, cuenta_activa)
    if error:
        return error
    actual = obtener_salon(supabase, contexto, lugar_id, salon_id, cuenta_activa)
    if not actual.ok or actual.item is None:
        return actual
    datos, mensaje = _validar_salon_payload(payload)
    if mensaje:
        return ResultadoOperacion(False, "invalid_data", mensaje)
    assert datos is not None and cuenta_id is not None
    if actual.item["estado"] not in ESTADOS:
        return ResultadoOperacion(False, "invalid_state", "El salon tiene un estado no reconocido.")
    try:
        if _duplicado_salon(supabase, cuenta_id, actual.item["lugar_id"], datos["sal_nombre_salon"], actual.item["salon_id"]):
            return ResultadoOperacion(False, "duplicate", "Ya existe un salon con ese nombre en el lugar.")
        rows = _filas(
            supabase.table("evp_sal_salon").update(datos)
            .eq("sal_cuenta_id", cuenta_id).eq("sal_lugar_id", actual.item["lugar_id"])
            .eq("sal_salon_id", actual.item["salon_id"]).execute()
        )
    except Exception as ex:
        return _resultado_error(ex)
    item = _salon(rows[0]) if rows else None
    return ResultadoOperacion(bool(item), "success" if item else "unexpected_response", "Salon actualizado correctamente." if item else "No se pudo confirmar la actualizacion.", item)


def verificar_dependencias_salon(supabase: Any, contexto: dict[str, Any] | None, lugar_id: Any, salon_id: Any, cuenta_activa: dict[str, Any] | None = None) -> ResultadoDependencias:
    cuenta_id, error = _autorizar(contexto, puede_desactivar_salon, cuenta_activa)
    if error:
        return ResultadoDependencias(False, True, error.mensaje, [])
    try:
        rows = _filas(
            supabase.table("evp_eve_evento")
            .select("eve_cuenta_id,eve_evento_id,eve_nombre_evento,eve_fase_evento,eve_estado,eve_fecha_hora_inicio")
            .eq("eve_cuenta_id", cuenta_id).eq("eve_lugar_id", _id(lugar_id))
            .eq("eve_salon_id", _id(salon_id)).eq("eve_estado", "Activo").execute()
        )
    except Exception as ex:
        print("[LUGARES][ERROR] dependencias_salon", type(ex).__name__, str(ex))
        return ResultadoDependencias(False, True, "No fue posible verificar las dependencias.", [])
    eventos = [row for row in rows if _texto(row.get("eve_fase_evento")) != "Cerrado"]
    return ResultadoDependencias(True, bool(eventos), "El salon esta asociado a eventos activos o no cerrados." if eventos else "", eventos)


def cambiar_estado_salon(supabase: Any, contexto: dict[str, Any] | None, lugar_id: Any, salon_id: Any, estado: str, cuenta_activa: dict[str, Any] | None = None) -> ResultadoOperacion:
    cuenta_id, error = _autorizar(contexto, puede_desactivar_salon, cuenta_activa)
    if error:
        return error
    if estado not in {"Activo", "Inactivo"}:
        return ResultadoOperacion(False, "invalid_state", "El estado solicitado no es valido.")
    actual = obtener_salon(supabase, contexto, lugar_id, salon_id, cuenta_activa)
    if not actual.ok:
        return actual
    if estado == "Inactivo":
        dependencias = verificar_dependencias_salon(supabase, contexto, lugar_id, salon_id, cuenta_activa)
        if not dependencias.ok or dependencias.bloquea:
            return ResultadoOperacion(False, "dependency_blocked", dependencias.mensaje or "No se puede desactivar el salon.")
    try:
        rows = _filas(
            supabase.table("evp_sal_salon").update({"sal_estado": estado})
            .eq("sal_cuenta_id", cuenta_id).eq("sal_lugar_id", _id(lugar_id))
            .eq("sal_salon_id", _id(salon_id)).execute()
        )
    except Exception as ex:
        return _resultado_error(ex)
    item = _salon(rows[0]) if rows else None
    return ResultadoOperacion(bool(item), "success" if item else "unexpected_response", "Estado del salon actualizado." if item else "No se pudo confirmar el cambio.", item)
