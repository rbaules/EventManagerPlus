from __future__ import annotations

from typing import Any

from db import get_supabase_client
from services.response_utils import extract_data, safe_get, to_dict


SELECT_USUARIO = (
    "usr_usuario_id,"
    "usr_nombre_usuario,"
    "usr_nombre_usuario_abrev,"
    "usr_email,"
    "usr_usuario_auth_uuid,"
    "usr_es_usuario_master,"
    "usr_cuenta_id_default,"
    "usr_evento_id_default,"
    "usr_estado"
)


class UsuarioContextoError(RuntimeError):
    """Error controlado al cargar permisos y contexto del usuario."""


def buscar_usuario_eventplus_por_auth_uuid(auth_user_id: str) -> dict[str, Any] | None:
    supabase = get_supabase_client()
    response = (
        supabase
        .table("evp_usr_usuario")
        .select(SELECT_USUARIO)
        .eq("usr_usuario_auth_uuid", auth_user_id)
        .limit(1)
        .execute()
    )

    data = extract_data(response)
    if not data:
        return None

    return to_dict(data[0])


def _extraer_filas(response: Any) -> list[dict[str, Any]]:
    filas: list[dict[str, Any]] = []
    for item in extract_data(response):
        row = to_dict(item)
        if row:
            filas.append(row)
    return filas


def _trazar_filas(label: str, filas: list[dict[str, Any]]) -> None:
    keys = sorted(filas[0].keys()) if filas else []
    print(f"[CONTEXTO][INFO] {label}: tipo=list cantidad={len(filas)} keys={keys}")


def _trazar_error(fase: str, ex: Exception) -> None:
    print(f"[CONTEXTO][ERROR] fase={fase} tipo={type(ex).__name__} mensaje={ex}")


def _normalizar_id(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _cuenta_desde_row(row: dict[str, Any], rol: str) -> dict[str, Any] | None:
    cuenta = safe_get(row, "evp_cta_cuenta")
    if isinstance(cuenta, list):
        cuenta = cuenta[0] if cuenta else None
    if not isinstance(cuenta, dict):
        cuenta = row

    cuenta_id = _normalizar_id(
        safe_get(cuenta, "cta_cuenta_id", safe_get(row, "ucu_cuenta_id"))
    )
    if cuenta_id is None:
        return None

    return {
        "cuenta_id": cuenta_id,
        "nombre_cuenta": safe_get(cuenta, "cta_nombre_cuenta", f"Cuenta {cuenta_id}"),
        "nombre_cuenta_abrev": safe_get(cuenta, "cta_nombre_cuenta_abrev"),
        "estado": safe_get(cuenta, "cta_estado"),
        "rol": rol,
    }


def _evento_desde_row(row: dict[str, Any], rol: str) -> dict[str, Any] | None:
    evento = safe_get(row, "evp_eve_evento")
    if isinstance(evento, list):
        evento = evento[0] if evento else None
    if not isinstance(evento, dict):
        evento = row

    cuenta_id = _normalizar_id(
        safe_get(evento, "eve_cuenta_id", safe_get(row, "uev_cuenta_id"))
    )
    evento_id = _normalizar_id(
        safe_get(evento, "eve_evento_id", safe_get(row, "uev_evento_id"))
    )
    if cuenta_id is None or evento_id is None:
        return None

    return {
        "cuenta_id": cuenta_id,
        "evento_id": evento_id,
        "nombre_evento": safe_get(evento, "eve_nombre_evento", f"Evento {evento_id}"),
        "nombre_evento_abrev": safe_get(evento, "eve_nombre_evento_abrev"),
        "fase_evento": safe_get(evento, "eve_fase_evento"),
        "estado": safe_get(evento, "eve_estado"),
        "fecha_hora_inicio": safe_get(evento, "eve_fecha_hora_inicio"),
        "fecha_hora_fin": safe_get(evento, "eve_fecha_hora_fin"),
        "rol": rol,
    }


def _dedupe_cuentas(cuentas: list[dict[str, Any]]) -> list[dict[str, Any]]:
    prioridad = {"Master": 4, "Administrador": 3, "Operador": 2, "Consulta": 1}
    por_id: dict[int, dict[str, Any]] = {}
    for cuenta in cuentas:
        cuenta_id = cuenta["cuenta_id"]
        existente = por_id.get(cuenta_id)
        if not existente or prioridad.get(cuenta["rol"], 0) > prioridad.get(existente["rol"], 0):
            por_id[cuenta_id] = cuenta
    return list(por_id.values())


def _dedupe_eventos(eventos: list[dict[str, Any]]) -> list[dict[str, Any]]:
    prioridad = {"Master": 4, "Administrador": 3, "Operador": 2, "Consulta": 1}
    por_id: dict[tuple[int, int], dict[str, Any]] = {}
    for evento in eventos:
        key = (evento["cuenta_id"], evento["evento_id"])
        existente = por_id.get(key)
        if not existente or prioridad.get(evento["rol"], 0) > prioridad.get(existente["rol"], 0):
            por_id[key] = evento
    return list(por_id.values())


def _consultar_cuentas_master() -> list[dict[str, Any]]:
    supabase = get_supabase_client()
    response = (
        supabase
        .table("evp_cta_cuenta")
        .select("cta_cuenta_id,cta_nombre_cuenta,cta_nombre_cuenta_abrev,cta_estado")
        .order("cta_cuenta_id")
        .execute()
    )
    filas = _extraer_filas(response)
    _trazar_filas("cuentas_master", filas)
    return [
        cuenta
        for row in filas
        if (cuenta := _cuenta_desde_row(row, "Master")) is not None
    ]


def _consultar_eventos_por_cuenta(
    cuenta_id: int,
    rol: str,
    solo_activos: bool = True,
) -> list[dict[str, Any]]:
    supabase = get_supabase_client()
    query = (
        supabase
        .table("evp_eve_evento")
        .select(
            "eve_cuenta_id,eve_evento_id,eve_nombre_evento,eve_nombre_evento_abrev,"
            "eve_fase_evento,eve_fecha_hora_inicio,eve_fecha_hora_fin,eve_estado"
        )
        .eq("eve_cuenta_id", cuenta_id)
    )
    if solo_activos:
        query = query.eq("eve_estado", "Activo")
    response = query.order("eve_evento_id").execute()
    filas = _extraer_filas(response)
    _trazar_filas(f"eventos_cuenta_{cuenta_id}", filas)
    return [
        evento
        for row in filas
        if (evento := _evento_desde_row(row, rol)) is not None
    ]


def _consultar_evento_activo(cuenta_id: int, evento_id: int, rol: str) -> dict[str, Any] | None:
    supabase = get_supabase_client()
    response = (
        supabase
        .table("evp_eve_evento")
        .select(
            "eve_cuenta_id,eve_evento_id,eve_nombre_evento,eve_nombre_evento_abrev,"
            "eve_fase_evento,eve_fecha_hora_inicio,eve_fecha_hora_fin,eve_estado"
        )
        .eq("eve_cuenta_id", cuenta_id)
        .eq("eve_evento_id", evento_id)
        .eq("eve_estado", "Activo")
        .limit(1)
        .execute()
    )
    data = _extraer_filas(response)
    _trazar_filas(f"evento_activo_{cuenta_id}_{evento_id}", data)
    if not data:
        return None
    return _evento_desde_row(data[0], rol)


def _consultar_cuentas_vinculadas(usr_usuario_id: str) -> list[dict[str, Any]]:
    supabase = get_supabase_client()
    response = (
        supabase
        .table("evp_ucu_usuario_cuenta")
        .select(
            "ucu_cuenta_id,ucu_rol,ucu_estado,"
            "evp_cta_cuenta:ucu_cuenta_id("
            "cta_cuenta_id,cta_nombre_cuenta,cta_nombre_cuenta_abrev,cta_estado"
            ")"
        )
        .eq("ucu_usuario_id", usr_usuario_id)
        .eq("ucu_estado", "Activo")
        .execute()
    )

    cuentas: list[dict[str, Any]] = []
    filas = _extraer_filas(response)
    _trazar_filas("cuentas_vinculadas", filas)
    for row in filas:
        rol = str(safe_get(row, "ucu_rol", ""))
        cuenta = _cuenta_desde_row(row, rol)
        if cuenta and cuenta["estado"] == "Activo":
            cuentas.append(cuenta)
    return _dedupe_cuentas(cuentas)


def _consultar_eventos_asignados_operador(usr_usuario_id: str, cuenta_id: int) -> list[dict[str, Any]]:
    supabase = get_supabase_client()
    response = (
        supabase
        .table("evp_uev_usuario_evento")
        .select("uev_cuenta_id,uev_evento_id,uev_estado")
        .eq("uev_usuario_id", usr_usuario_id)
        .eq("uev_cuenta_id", cuenta_id)
        .eq("uev_estado", "Activo")
        .execute()
    )

    eventos: list[dict[str, Any]] = []
    filas = _extraer_filas(response)
    _trazar_filas(f"eventos_asignados_operador_cuenta_{cuenta_id}", filas)
    for row in filas:
        evento_id = _normalizar_id(safe_get(row, "uev_evento_id"))
        if evento_id is None:
            continue
        evento = _consultar_evento_activo(cuenta_id, evento_id, "Operador")
        if evento:
            eventos.append(evento)
    return eventos


def _rol_global(cuentas: list[dict[str, Any]]) -> str:
    roles = {cuenta["rol"] for cuenta in cuentas}
    if "Administrador" in roles:
        return "Administrador"
    if "Operador" in roles:
        return "Operador"
    if "Consulta" in roles:
        return "Consulta"
    return "Sin rol"


def _seleccionar_cuenta_actual(
    cuentas: list[dict[str, Any]],
    cuenta_id_default: Any,
) -> dict[str, Any] | None:
    default_id = _normalizar_id(cuenta_id_default)
    if default_id is not None:
        for cuenta in cuentas:
            if cuenta["cuenta_id"] == default_id:
                return cuenta
    return cuentas[0] if cuentas else None


def _seleccionar_evento_actual(
    eventos: list[dict[str, Any]],
    cuenta_actual: dict[str, Any] | None,
    evento_id_default: Any,
) -> dict[str, Any] | None:
    if not cuenta_actual:
        return None

    eventos_de_cuenta = [
        evento for evento in eventos if evento["cuenta_id"] == cuenta_actual["cuenta_id"]
    ]
    default_id = _normalizar_id(evento_id_default)
    if default_id is not None:
        for evento in eventos_de_cuenta:
            if evento["evento_id"] == default_id:
                return evento
    return eventos_de_cuenta[0] if eventos_de_cuenta else None


def cargar_contexto_usuario(auth_user_id: str) -> dict[str, Any]:
    try:
        usuario = buscar_usuario_eventplus_por_auth_uuid(auth_user_id)
    except Exception as ex:
        _trazar_error("cargar_usuario", ex)
        raise UsuarioContextoError(
            "No fue posible cargar la informacion de tu usuario."
        ) from ex

    if not usuario:
        raise UsuarioContextoError(
            "Tu usuario fue autenticado, pero no esta autorizado en EventPlus."
        )

    if safe_get(usuario, "usr_estado") != "Activo":
        raise UsuarioContextoError(
            "Tu usuario esta inactivo o suspendido. Contacta al administrador."
        )

    usr_usuario_id = str(safe_get(usuario, "usr_usuario_id", ""))
    if not usr_usuario_id:
        raise UsuarioContextoError(
            "No pudimos identificar tu usuario interno de EventPlus."
        )

    es_master = bool(safe_get(usuario, "usr_es_usuario_master", False))

    if es_master:
        try:
            cuentas_permitidas = _consultar_cuentas_master()
        except Exception as ex:
            _trazar_error("cargar_cuentas_master", ex)
            raise UsuarioContextoError(
                "No fue posible cargar las cuentas disponibles."
            ) from ex

        eventos_permitidos: list[dict[str, Any]] = []
        try:
            for cuenta in cuentas_permitidas:
                eventos_permitidos.extend(
                    _consultar_eventos_por_cuenta(
                        cuenta["cuenta_id"],
                        "Master",
                        solo_activos=False,
                    )
                )
        except Exception as ex:
            _trazar_error("cargar_eventos_master", ex)
            raise UsuarioContextoError(
                "No fue posible cargar los eventos disponibles."
            ) from ex
        rol_global_calculado = "Master"
    else:
        try:
            cuentas_permitidas = _consultar_cuentas_vinculadas(usr_usuario_id)
        except Exception as ex:
            _trazar_error("cargar_cuentas_usuario", ex)
            raise UsuarioContextoError(
                "No fue posible cargar las cuentas disponibles."
            ) from ex

        if not cuentas_permitidas:
            raise UsuarioContextoError(
                "Tu usuario existe, pero no tiene cuentas activas asignadas."
            )

        eventos_permitidos = []
        try:
            for cuenta in cuentas_permitidas:
                if cuenta["rol"] in {"Administrador", "Consulta"}:
                    eventos_permitidos.extend(
                        _consultar_eventos_por_cuenta(cuenta["cuenta_id"], cuenta["rol"])
                    )
                elif cuenta["rol"] == "Operador":
                    eventos_permitidos.extend(
                        _consultar_eventos_asignados_operador(
                            usr_usuario_id,
                            cuenta["cuenta_id"],
                        )
                    )
        except Exception as ex:
            _trazar_error("cargar_eventos_usuario", ex)
            raise UsuarioContextoError(
                "No fue posible cargar los eventos disponibles."
            ) from ex
        rol_global_calculado = _rol_global(cuentas_permitidas)

    cuentas_permitidas = _dedupe_cuentas(cuentas_permitidas)
    eventos_permitidos = _dedupe_eventos(eventos_permitidos)

    if not cuentas_permitidas:
        raise UsuarioContextoError(
            "Tu usuario existe, pero no tiene cuentas activas asignadas."
        )

    cuenta_actual = _seleccionar_cuenta_actual(
        cuentas_permitidas,
        safe_get(usuario, "usr_cuenta_id_default"),
    )
    evento_actual = _seleccionar_evento_actual(
        eventos_permitidos,
        cuenta_actual,
        safe_get(usuario, "usr_evento_id_default"),
    )

    if not eventos_permitidos:
        print("[CONTEXTO][WARNING] Usuario sin eventos disponibles; se abrira Dashboard en estado vacio.")

    puede_administrar_usuarios = rol_global_calculado in {"Master", "Administrador"}
    puede_registrar_llegadas = bool(
        evento_actual
        and evento_actual["rol"] in {"Master", "Administrador", "Operador"}
        and evento_actual["fase_evento"] == "En_proceso"
        and evento_actual["estado"] == "Activo"
    )

    return {
        "usr_usuario_id": safe_get(usuario, "usr_usuario_id"),
        "usr_usuario_auth_uuid": safe_get(usuario, "usr_usuario_auth_uuid"),
        "usr_nombre_usuario": safe_get(usuario, "usr_nombre_usuario"),
        "usr_nombre_usuario_abrev": safe_get(usuario, "usr_nombre_usuario_abrev"),
        "usr_email": safe_get(usuario, "usr_email"),
        "usr_es_usuario_master": es_master,
        "usr_estado": safe_get(usuario, "usr_estado"),
        "usr_cuenta_id_default": safe_get(usuario, "usr_cuenta_id_default"),
        "usr_evento_id_default": safe_get(usuario, "usr_evento_id_default"),
        "rol_global_calculado": rol_global_calculado,
        "cuentas_permitidas": cuentas_permitidas,
        "eventos_permitidos": eventos_permitidos,
        "cuenta_actual": cuenta_actual,
        "evento_actual": evento_actual,
        "puede_registrar_llegadas": puede_registrar_llegadas,
        "puede_administrar_usuarios": puede_administrar_usuarios,
    }


def buscar_usuario_eventplus_por_email(email: str) -> dict[str, Any] | None:
    supabase = get_supabase_client()
    response = (
        supabase
        .table("evp_usr_usuario")
        .select(SELECT_USUARIO)
        .ilike("usr_email", email)
        .limit(1)
        .execute()
    )

    data = extract_data(response)
    if not data:
        return None

    return to_dict(data[0])


def formato_usuario_eventplus(usuario: dict[str, Any] | None) -> str:
    if not usuario:
        return "No se encontro registro en evp_usr_usuario."

    if "_raw" in usuario:
        return (
            "La consulta devolvio una fila en formato inesperado:\n"
            f"Tipo detectado: {usuario.get('_type') or usuario.get('_parsed_type')}\n"
            f"Valor crudo:\n{usuario['_raw']}"
        )

    return "\n".join(
        [
            "Registro encontrado en evp_usr_usuario:",
            f"usr_usuario_id: {safe_get(usuario, 'usr_usuario_id')}",
            f"usr_nombre_usuario: {safe_get(usuario, 'usr_nombre_usuario')}",
            f"usr_nombre_usuario_abrev: {safe_get(usuario, 'usr_nombre_usuario_abrev')}",
            f"usr_email: {safe_get(usuario, 'usr_email')}",
            f"usr_usuario_auth_uuid: {safe_get(usuario, 'usr_usuario_auth_uuid')}",
            f"usr_es_usuario_master: {safe_get(usuario, 'usr_es_usuario_master')}",
            f"usr_estado: {safe_get(usuario, 'usr_estado')}",
        ]
    )
