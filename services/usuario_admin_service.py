from __future__ import annotations

import math
from typing import Any, Iterable

from models.usuario_admin_models import (
    AccesoEfectivoUsuario,
    ResultadoDetalleUsuario,
    ResultadoPaginadoUsuarios,
    UsuarioCuentaResumen,
    UsuarioDetalle,
    UsuarioEventoResumen,
    UsuarioResumen,
    ActualizarUsuarioRequest,
    ActualizarPreferenciasRequest,
    CambiarEstadoUsuarioRequest,
    CambiarMasterRequest,
    CambiarRolCuentaRequest,
    CambiarEstadoCuentaRequest,
    AgregarCuentaUsuarioRequest,
    CambiarEstadoEventoUsuarioRequest,
    UsuarioElegibleCuenta,
    CrearUsuarioRequest,
    PromoverMasterRequest,
    RetirarMasterRequest,
    ResultadoUsuarioOperacion,
)
from services.authorization_service import ROL_ADMINISTRADOR, puede_ver_administracion_usuarios
from services.response_utils import extract_data, safe_get, to_dict


PAGE_SIZE_DEFAULT = 20
ESTADOS_FILTRO = frozenset({"Todos", "Activo", "Inactivo", "Preregistrado"})
TIPOS_FILTRO = frozenset({"Todos", "Master", "No Master"})
ROLES_FILTRO = frozenset({"Todos", "Administrador", "Operador", "Consulta"})
ORDENES = {"nombre": "usr_nombre_usuario", "correo": "usr_email", "estado": "usr_estado"}
MENSAJE_SIN_PERMISO = "No tiene permisos para consultar la administración de usuarios."
MENSAJE_SIN_RESULTADOS = "No se encontraron usuarios con los filtros seleccionados."
MENSAJE_ERROR = "No fue posible cargar la información de usuarios."
MENSAJE_DETALLE_DENEGADO = "No tiene acceso al usuario solicitado."
MENSAJE_DETALLE_NO_ENCONTRADO = "Usuario no encontrado."
MENSAJE_DETALLE_ERROR = "No fue posible cargar el usuario solicitado."

_SELECT_USUARIO = (
    "usr_usuario_id,usr_nombre_usuario,usr_nombre_usuario_abrev,usr_email,"
    "usr_usuario_auth_uuid,usr_es_usuario_master,usr_cuenta_id_default,"
    "usr_evento_id_default,usr_telefono,usr_creado,usr_modificado,usr_estado"
    ",usr_creado_por"
)

MENSAJES_OPERACION = {
    "OK": "Operación completada.",
    "USER_ADMIN_FORBIDDEN": "No tiene permisos para realizar esta acción.",
    "USER_NOT_FOUND": "El usuario solicitado no existe o no está disponible.",
    "USER_EMAIL_EXISTS": "Ya existe un usuario con ese correo.",
    "INVALID_USER_NAME": "Ingrese un nombre válido de hasta 50 caracteres.",
    "INVALID_EMAIL": "Ingrese un correo válido de hasta 254 caracteres.",
    "ACCOUNT_REQUIRED": "Seleccione una cuenta.",
    "ACTIVE_CONTEXT_REQUIRED": "Para crear un usuario, seleccione primero una cuenta y un evento activos.",
    "ROLE_REQUIRED": "Seleccione el rol inicial.",
    "INVALID_ACCOUNT": "La cuenta seleccionada no está disponible.",
    "INVALID_ACCOUNT_ROLE": "El Administrador solo puede asignar los roles Operador o Consulta.",
    "INVALID_EVENT": "El evento seleccionado no estÃ¡ disponible.",
    "EVENT_REQUIRED": "Seleccione un evento inicial.",
    "ACCOUNT_FORBIDDEN": "No tiene permisos para crear usuarios en la cuenta seleccionada.",
    "USER_EDIT_FORBIDDEN": "No tiene permisos para editar este usuario en las cuentas que administra.",
    "USER_EDIT_INVALID_STATUS": "Solo puede editar usuarios Activos o Preregistrados.",
    "INVALID_PREFERENCES": "Seleccione una cuenta y un evento permitidos.",
    "ROLE_CHANGE_FORBIDDEN": "No tiene permisos para cambiar este rol de cuenta.",
    "ACCOUNT_RELATION_FORBIDDEN": "No tiene permisos para cambiar esta relación de cuenta.",
    "DEFAULTS_FORBIDDEN": "No tiene permisos para asignar predeterminados.",
    "DEFAULT_ACCOUNT_REQUIRED": "Seleccione una cuenta predeterminada.",
    "INVALID_DEFAULT_ACCOUNT": "La cuenta predeterminada no es válida.",
    "DEFAULT_ACCOUNT_FORBIDDEN": "El usuario no tiene acceso a la cuenta predeterminada.",
    "INVALID_DEFAULT_EVENT": "El evento predeterminado no es válido para la cuenta seleccionada.",
    "INVALID_STATUS": "El cambio de estado solicitado no es válido.",
    "INVALID_MASTER_TARGET_STATUS": "Solo puede convertir en Master usuarios Activos o Preregistrados.",
    "AUTH_REQUIRED": "Este usuario aún no tiene una identidad de autenticación vinculada.",
    "LAST_MASTER": "La acción dejaría el sistema sin ningún Master activo.",
    "SELF_MASTER_CHANGE_FORBIDDEN": "No puede retirar su propia condición Master.",
    "SELF_DEACTIVATION_FORBIDDEN": "No puede inactivar su propio usuario.",
    "USER_ADMIN_INTERNAL_ERROR": "No fue posible completar la operación.",
    "ACCOUNT_RELATION_EXISTS": "El usuario ya tiene una relación activa con esta cuenta.",
    "EVENT_RELATION_EXISTS": "El usuario ya tiene una asignación activa a este evento.",
    "EVENT_RELATION_FORBIDDEN": "No tiene permisos para cambiar esta asignación de evento.",
    "TARGET_STATUS_FORBIDDEN": "Reactive globalmente al usuario antes de modificar sus accesos.",
    "TARGET_ACCOUNT_ADMIN_FORBIDDEN": "La relación Administrador de esta cuenta solo puede ser administrada por un usuario Master.",
    "SEARCH_TOO_SHORT": "Ingrese al menos 3 caracteres para buscar.",
}


def _codigo_error(ex: Exception) -> str:
    text = str(ex).upper()
    for code in MENSAJES_OPERACION:
        if code != "OK" and code in text:
            return code
    return "USER_ADMIN_INTERNAL_ERROR"


def _operar(supabase: Any, contexto: dict[str, Any] | None, rpc: str, params: dict[str, Any], *, solo_master: bool | None) -> ResultadoUsuarioOperacion:
    actor = str((contexto or {}).get("usr_usuario_id") or "")
    permitido = bool(actor and (True if solo_master is None else (_es_master(contexto) if solo_master else _actor_valido(contexto))))
    if not permitido:
        return ResultadoUsuarioOperacion(False, "USER_ADMIN_FORBIDDEN", MENSAJES_OPERACION["USER_ADMIN_FORBIDDEN"])
    try:
        response = supabase.rpc(rpc, params).execute()
        data = extract_data(response)
        payload = to_dict(data[0] if isinstance(data, list) and data else data)
        code = str(payload.get("codigo") or "OK")
        uid = payload.get("usuario_id")
        print("[USUARIOS_ADMIN][INFO] operacion", f"actor={actor}", f"rpc={rpc}", f"resultado={code}")
        return ResultadoUsuarioOperacion(bool(payload.get("ok", True)), code, MENSAJES_OPERACION.get(code, MENSAJES_OPERACION["USER_ADMIN_INTERNAL_ERROR"]), str(uid) if uid else None, payload)
    except Exception as ex:
        code = _codigo_error(ex)
        print("[USUARIOS_ADMIN][WARNING] operacion", f"actor={actor}", f"rpc={rpc}", f"resultado={code}", f"tipo={type(ex).__name__}")
        return ResultadoUsuarioOperacion(False, code, MENSAJES_OPERACION[code])


def crear_usuario(supabase: Any, contexto: dict[str, Any] | None, request: CrearUsuarioRequest) -> ResultadoUsuarioOperacion:
    if request.rol in {"Master", "Administrador"} and not _es_master(contexto):
        return ResultadoUsuarioOperacion(False, "USER_ADMIN_FORBIDDEN", MENSAJES_OPERACION["USER_ADMIN_FORBIDDEN"])
    if not _es_master(contexto):
        if request.rol not in {"Operador", "Consulta"}:
            return ResultadoUsuarioOperacion(False, "INVALID_ACCOUNT_ROLE", MENSAJES_OPERACION["INVALID_ACCOUNT_ROLE"])
    params = {
        "p_nombre": request.nombre, "p_email": request.email,
        "p_rol": request.rol, "p_cuenta_id": request.cuenta_id,
        "p_evento_id": request.evento_id,
    }
    return _operar(supabase, contexto, "evp_admin_crear_usuario", params, solo_master=False)


def actualizar_preferencias(supabase: Any, contexto: dict[str, Any] | None, request: ActualizarPreferenciasRequest) -> ResultadoUsuarioOperacion:
    return _operar(
        supabase, contexto, "evp_usuario_actualizar_preferencias",
        {"p_cuenta_id": request.cuenta_id, "p_evento_id": request.evento_id},
        solo_master=None,
    )


def cambiar_rol_cuenta(supabase: Any, contexto: dict[str, Any] | None, request: CambiarRolCuentaRequest) -> ResultadoUsuarioOperacion:
    return _operar(supabase, contexto, "evp_admin_cambiar_rol_cuenta", {"p_usuario_id": request.usuario_id, "p_cuenta_id": request.cuenta_id, "p_nuevo_rol": request.rol, "p_evento_id": request.evento_id}, solo_master=False)


def cambiar_estado_cuenta(supabase: Any, contexto: dict[str, Any] | None, request: CambiarEstadoCuentaRequest) -> ResultadoUsuarioOperacion:
    return _operar(supabase, contexto, "evp_admin_cambiar_estado_cuenta", {"p_usuario_id": request.usuario_id, "p_cuenta_id": request.cuenta_id, "p_estado": request.estado}, solo_master=False)


def agregar_cuenta_usuario(supabase: Any, contexto: dict[str, Any] | None, request: AgregarCuentaUsuarioRequest) -> ResultadoUsuarioOperacion:
    return _operar(supabase, contexto, "evp_admin_agregar_cuenta_usuario", {
        "p_usuario_id": request.usuario_id, "p_cuenta_id": request.cuenta_id,
        "p_rol": request.rol, "p_evento_inicial_id": request.evento_inicial_id,
    }, solo_master=False)


def agregar_evento_usuario(supabase: Any, contexto: dict[str, Any] | None, request: CambiarEstadoEventoUsuarioRequest) -> ResultadoUsuarioOperacion:
    return _operar(supabase, contexto, "evp_admin_agregar_evento_usuario", {
        "p_usuario_id": request.usuario_id, "p_cuenta_id": request.cuenta_id, "p_evento_id": request.evento_id,
    }, solo_master=False)


def cambiar_estado_evento_usuario(supabase: Any, contexto: dict[str, Any] | None, request: CambiarEstadoEventoUsuarioRequest) -> ResultadoUsuarioOperacion:
    return _operar(supabase, contexto, "evp_admin_cambiar_estado_evento_usuario", {
        "p_usuario_id": request.usuario_id, "p_cuenta_id": request.cuenta_id,
        "p_evento_id": request.evento_id, "p_estado": request.estado,
    }, solo_master=False)


def buscar_usuario_para_cuenta(supabase: Any, contexto: dict[str, Any] | None, cuenta_id: int, busqueda: str) -> tuple[UsuarioElegibleCuenta, ...]:
    if not _actor_valido(contexto) or int(cuenta_id) <= 0 or len(str(busqueda or "").strip()) < 3:
        return ()
    try:
        data = extract_data(supabase.rpc("evp_admin_buscar_usuario_para_cuenta", {
            "p_cuenta_id": int(cuenta_id), "p_busqueda": str(busqueda).strip(),
        }).execute())
        if isinstance(data, dict):
            data = data.get("data") or []
        return tuple(UsuarioElegibleCuenta(
            usuario_id=str(row.get("usuario_id") or ""), nombre=str(row.get("nombre") or ""),
            email=str(row.get("email") or ""), estado=str(row.get("estado") or ""),
            rol_cuenta=str(row.get("rol_cuenta")) if row.get("rol_cuenta") else None,
            estado_relacion=str(row.get("estado_relacion")) if row.get("estado_relacion") else None,
        ) for item in (data or []) if (row := to_dict(item)) and row.get("usuario_id"))
    except Exception as ex:
        print("[USUARIOS_ADMIN][WARNING] busqueda_controlada", f"actor={(contexto or {}).get('usr_usuario_id')}", f"tipo={type(ex).__name__}")
        return ()


def actualizar_usuario(supabase: Any, contexto: dict[str, Any] | None, request: ActualizarUsuarioRequest) -> ResultadoUsuarioOperacion:
    return _operar(supabase, contexto, "evp_admin_actualizar_usuario", {"p_usuario_id": request.usuario_id, "p_nombre": request.nombre, "p_email": request.email}, solo_master=False)


def cambiar_estado_usuario(supabase: Any, contexto: dict[str, Any] | None, request: CambiarEstadoUsuarioRequest) -> ResultadoUsuarioOperacion:
    actor = str((contexto or {}).get("usr_usuario_id") or "")
    if request.usuario_id == actor and request.estado == "Inactivo":
        return ResultadoUsuarioOperacion(False, "SELF_DEACTIVATION_FORBIDDEN", MENSAJES_OPERACION["SELF_DEACTIVATION_FORBIDDEN"])
    return _operar(supabase, contexto, "evp_admin_cambiar_estado_usuario", {"p_usuario_id": request.usuario_id, "p_estado": request.estado}, solo_master=True)


def cambiar_master(supabase: Any, contexto: dict[str, Any] | None, request: CambiarMasterRequest) -> ResultadoUsuarioOperacion:
    actor = str((contexto or {}).get("usr_usuario_id") or "")
    if request.usuario_id == actor and not request.es_master:
        return ResultadoUsuarioOperacion(False, "SELF_MASTER_CHANGE_FORBIDDEN", MENSAJES_OPERACION["SELF_MASTER_CHANGE_FORBIDDEN"])
    return _operar(supabase, contexto, "evp_admin_cambiar_master", {"p_usuario_id": request.usuario_id, "p_es_master": request.es_master}, solo_master=True)


def promover_master(supabase: Any, contexto: dict[str, Any] | None, request: PromoverMasterRequest) -> ResultadoUsuarioOperacion:
    return _operar(supabase, contexto, "evp_admin_convertir_master", {"p_usuario_id": request.usuario_id}, solo_master=True)


def retirar_master(supabase: Any, contexto: dict[str, Any] | None, request: RetirarMasterRequest) -> ResultadoUsuarioOperacion:
    actor = str((contexto or {}).get("usr_usuario_id") or "")
    if request.usuario_id == actor:
        return ResultadoUsuarioOperacion(False, "SELF_MASTER_CHANGE_FORBIDDEN", MENSAJES_OPERACION["SELF_MASTER_CHANGE_FORBIDDEN"])
    return _operar(
        supabase, contexto, "evp_admin_retirar_master",
        {"p_usuario_id": request.usuario_id, "p_cuenta_id": request.cuenta_id, "p_rol": request.rol, "p_evento_id": request.evento_id},
        solo_master=True,
    )


def _filas(response: Any) -> list[dict[str, Any]]:
    return [row for item in extract_data(response) if (row := to_dict(item))]


def _int(value: Any) -> int | None:
    try:
        return int(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _ids(values: Iterable[Any]) -> list[Any]:
    return list(dict.fromkeys(value for value in values if value not in (None, "")))


def _es_master(contexto: dict[str, Any] | None) -> bool:
    return bool(contexto and contexto.get("usr_usuario_id") and contexto.get("usr_es_usuario_master"))


def _actor_valido(contexto: dict[str, Any] | None) -> bool:
    return bool(contexto and contexto.get("usr_usuario_id") and puede_ver_administracion_usuarios(contexto))


def _cuentas_admin_activas(supabase: Any, contexto: dict[str, Any]) -> dict[int, str]:
    actor_id = str(contexto.get("usr_usuario_id") or "")
    rows = _filas(
        supabase.table("evp_ucu_usuario_cuenta")
        .select("ucu_cuenta_id,ucu_rol,ucu_estado")
        .eq("ucu_usuario_id", actor_id)
        .eq("ucu_rol", ROL_ADMINISTRADOR)
        .eq("ucu_estado", "Activo")
        .execute()
    )
    ids = _ids(_int(row.get("ucu_cuenta_id")) for row in rows)
    if not ids:
        return {}
    accounts = _filas(
        supabase.table("evp_cta_cuenta")
        .select("cta_cuenta_id,cta_nombre_cuenta,cta_estado")
        .in_("cta_cuenta_id", ids)
        .eq("cta_estado", "Activo")
        .order("cta_nombre_cuenta")
        .execute()
    )
    return {
        int(row["cta_cuenta_id"]): str(row.get("cta_nombre_cuenta") or f"Cuenta {row['cta_cuenta_id']}")
        for row in accounts
    }


def _cuentas_master(supabase: Any) -> dict[int, str]:
    rows = _filas(
        supabase.table("evp_cta_cuenta")
        .select("cta_cuenta_id,cta_nombre_cuenta,cta_estado")
        .order("cta_nombre_cuenta")
        .execute()
    )
    return {
        int(row["cta_cuenta_id"]): str(row.get("cta_nombre_cuenta") or f"Cuenta {row['cta_cuenta_id']}")
        for row in rows
    }


def obtener_cuentas_visibles(supabase: Any, contexto: dict[str, Any] | None) -> dict[int, str]:
    if not _actor_valido(contexto):
        return {}
    return _cuentas_master(supabase) if _es_master(contexto) else _cuentas_admin_activas(supabase, contexto or {})


def obtener_cuentas_creacion(supabase: Any, contexto: dict[str, Any] | None) -> dict[int, str]:
    cuentas = obtener_cuentas_visibles(supabase, contexto)
    if not _es_master(contexto):
        return cuentas
    rows = _filas(
        supabase.table("evp_cta_cuenta")
        .select("cta_cuenta_id,cta_nombre_cuenta,cta_estado")
        .eq("cta_estado", "Activo").order("cta_nombre_cuenta").execute()
    )
    return {int(row["cta_cuenta_id"]): str(row.get("cta_nombre_cuenta") or f"Cuenta {row['cta_cuenta_id']}") for row in rows}


def obtener_eventos_creacion(supabase: Any, contexto: dict[str, Any] | None, cuenta_id: Any) -> dict[int, str]:
    account_id = _int(cuenta_id)
    if account_id is None or account_id not in obtener_cuentas_creacion(supabase, contexto):
        return {}
    rows = _filas(
        supabase.table("evp_eve_evento")
        .select("eve_cuenta_id,eve_evento_id,eve_nombre_evento,eve_estado")
        .eq("eve_cuenta_id", account_id).eq("eve_estado", "Activo")
        .order("eve_nombre_evento").execute()
    )
    return {int(row["eve_evento_id"]): str(row.get("eve_nombre_evento") or f"Evento {row['eve_evento_id']}") for row in rows}


def _relaciones_visibles(supabase: Any, cuenta_ids: list[int], usuario_ids: list[str] | None = None) -> list[dict[str, Any]]:
    if not cuenta_ids:
        return []
    query = (
        supabase.table("evp_ucu_usuario_cuenta")
        .select("ucu_cuenta_id,ucu_usuario_id,ucu_rol,ucu_estado")
        .in_("ucu_cuenta_id", cuenta_ids)
    )
    if usuario_ids is not None:
        if not usuario_ids:
            return []
        query = query.in_("ucu_usuario_id", usuario_ids)
    return _filas(query.execute())


def _aplicar_candidatos(
    relations: list[dict[str, Any]], rol: str, cuenta_id: int | None,
) -> list[str]:
    return _ids(
        str(row.get("ucu_usuario_id") or "")
        for row in relations
        if (rol == "Todos" or (row.get("ucu_rol") == rol and row.get("ucu_estado") == "Activo"))
        and (cuenta_id is None or _int(row.get("ucu_cuenta_id")) == cuenta_id)
    )


def _advertencia_auth(row: dict[str, Any]) -> bool:
    estado = str(row.get("usr_estado") or "")
    tiene_auth = bool(row.get("usr_usuario_auth_uuid"))
    return (estado == "Preregistrado" and not tiene_auth) or (estado == "Activo" and not tiene_auth)


def listar_usuarios(
    supabase: Any,
    contexto: dict[str, Any] | None,
    *,
    busqueda: str = "",
    estado: str = "Todos",
    tipo: str = "Todos",
    rol: str = "Todos",
    cuenta_id: Any = None,
    pagina: int = 1,
    tamano_pagina: int = PAGE_SIZE_DEFAULT,
    orden: str = "nombre",
) -> ResultadoPaginadoUsuarios:
    if not _actor_valido(contexto):
        return ResultadoPaginadoUsuarios(estado="denied", mensaje=MENSAJE_SIN_PERMISO)
    pagina = max(1, _int(pagina) or 1)
    tamano_pagina = min(100, max(1, _int(tamano_pagina) or PAGE_SIZE_DEFAULT))
    estado = estado if estado in ESTADOS_FILTRO else "Todos"
    tipo = tipo if tipo in TIPOS_FILTRO else "Todos"
    rol = rol if rol in ROLES_FILTRO else "Todos"
    cuenta_filtro = _int(cuenta_id)
    try:
        cuentas = obtener_cuentas_visibles(supabase, contexto)
        if not _es_master(contexto) and cuenta_filtro not in (None, *cuentas.keys()):
            print("[USUARIOS_ADMIN][WARNING] filtro_cuenta_denegado", f"actor={contexto.get('usr_usuario_id')}", f"cuenta={cuenta_filtro}")
            return ResultadoPaginadoUsuarios(estado="denied", mensaje=MENSAJE_SIN_PERMISO)
        scope_ids = [cuenta_filtro] if cuenta_filtro is not None else list(cuentas)
        relations = _relaciones_visibles(supabase, scope_ids)
        candidate_ids: list[str] | None = None
        if not _es_master(contexto) or cuenta_filtro is not None or rol != "Todos":
            candidate_ids = _aplicar_candidatos(relations, rol, cuenta_filtro)
            if not candidate_ids:
                return ResultadoPaginadoUsuarios(
                    pagina=pagina, tamano_pagina=tamano_pagina, estado="empty",
                    mensaje=MENSAJE_SIN_RESULTADOS, cuentas_filtro=tuple(cuentas.items()),
                )
        query = supabase.table("evp_usr_usuario").select(_SELECT_USUARIO, count="exact")
        if candidate_ids is not None:
            query = query.in_("usr_usuario_id", candidate_ids)
        if estado != "Todos":
            query = query.eq("usr_estado", estado)
        if tipo == "Master":
            query = query.eq("usr_es_usuario_master", True)
        elif tipo == "No Master":
            query = query.eq("usr_es_usuario_master", False)
        search = " ".join(str(busqueda or "").strip().split())[:100]
        if search:
            safe_search = search.replace(",", " ").replace("(", " ").replace(")", " ")
            query = query.or_(f"usr_nombre_usuario.ilike.%{safe_search}%,usr_email.ilike.%{safe_search}%")
        start = (pagina - 1) * tamano_pagina
        response = query.order(ORDENES.get(orden, ORDENES["nombre"])).range(start, start + tamano_pagina - 1).execute()
        user_rows = _filas(response)
        total = int(getattr(response, "count", None) or len(user_rows))
        visible_user_ids = [str(row.get("usr_usuario_id")) for row in user_rows]
        page_relations = _relaciones_visibles(supabase, list(cuentas), visible_user_ids)
        by_user: dict[str, list[dict[str, Any]]] = {}
        for relation in page_relations:
            by_user.setdefault(str(relation.get("ucu_usuario_id")), []).append(relation)
        active_account_ids = set(cuentas)
        if _es_master(contexto) and cuentas:
            active_account_ids = {
                int(item["cta_cuenta_id"])
                for item in _filas(
                    supabase.table("evp_cta_cuenta")
                    .select("cta_cuenta_id,cta_estado")
                    .in_("cta_cuenta_id", list(cuentas))
                    .eq("cta_estado", "Activo")
                    .execute()
                )
            }
        active_event_keys: set[tuple[int, int]] = set()
        if active_account_ids:
            event_rows = _filas(
                supabase.table("evp_eve_evento")
                .select("eve_cuenta_id,eve_evento_id,eve_estado")
                .in_("eve_cuenta_id", list(active_account_ids))
                .eq("eve_estado", "Activo")
                .execute()
            )
            active_event_keys = {
                (account_id, event_id)
                for item in event_rows
                if (account_id := _int(item.get("eve_cuenta_id"))) is not None
                and (event_id := _int(item.get("eve_evento_id"))) is not None
            }
        active_assignments: dict[str, set[tuple[int, int]]] = {}
        if visible_user_ids:
            assignments = _filas(
                supabase.table("evp_uev_usuario_evento")
                .select("uev_usuario_id,uev_cuenta_id,uev_evento_id,uev_estado")
                .in_("uev_usuario_id", visible_user_ids)
                .in_("uev_cuenta_id", list(cuentas))
                .execute()
            ) if cuentas else []
            for assignment in assignments:
                uid = str(assignment.get("uev_usuario_id"))
                key = (_int(assignment.get("uev_cuenta_id")), _int(assignment.get("uev_evento_id")))
                if assignment.get("uev_estado") == "Activo" and key in active_event_keys:
                    active_assignments.setdefault(uid, set()).add(key)  # type: ignore[arg-type]
        items: list[UsuarioResumen] = []
        for row in user_rows:
            uid = str(row.get("usr_usuario_id") or "")
            rels = by_user.get(uid, [])
            has_configured_access = str(row.get("usr_estado") or "") in {"Activo", "Preregistrado"}
            is_master = bool(row.get("usr_es_usuario_master"))
            effective_relations = {
                cid: str(item.get("ucu_rol") or "")
                for item in rels
                if item.get("ucu_estado") == "Activo"
                and (cid := _int(item.get("ucu_cuenta_id"))) in active_account_ids
                and item.get("ucu_rol") in {"Administrador", "Operador", "Consulta"}
            } if has_configured_access else {}
            effective_account_ids = active_account_ids if has_configured_access and is_master else set(effective_relations)
            if has_configured_access and is_master:
                effective_event_keys = active_event_keys
            else:
                inherited_accounts = {cid for cid, role_name in effective_relations.items() if role_name == ROL_ADMINISTRADOR}
                assigned_accounts = {cid for cid, role_name in effective_relations.items() if role_name in {"Operador", "Consulta"}}
                effective_event_keys = {
                    key for key in active_event_keys if key[0] in inherited_accounts
                } | {
                    key for key in active_assignments.get(uid, set()) if key[0] in assigned_accounts
                }
            account_names = tuple(sorted(cuentas[cid] for cid in effective_account_ids))
            roles = (
                ("Master",)
                if is_master
                else tuple(sorted({
                    str(item.get("ucu_rol"))
                    for item in rels
                    if item.get("ucu_estado") == "Activo" and item.get("ucu_rol")
                }))
            )
            items.append(UsuarioResumen(
                usuario_id=uid,
                nombre=str(row.get("usr_nombre_usuario") or ""),
                email=str(row.get("usr_email") or ""),
                estado=str(row.get("usr_estado") or ""),
                es_master=bool(row.get("usr_es_usuario_master")),
                auth_uuid_presente=bool(row.get("usr_usuario_auth_uuid")),
                cuentas_visibles=account_names,
                roles_visibles=roles,
                cantidad_eventos_asignados=len(active_assignments.get(uid, set())),
                cantidad_cuentas_accesibles=len(effective_account_ids),
                cantidad_eventos_accesibles=len(effective_event_keys),
                tiene_advertencia_auth=_advertencia_auth(row),
                acceso_global=is_master,
            ))
        total_pages = math.ceil(total / tamano_pagina) if total else 0
        return ResultadoPaginadoUsuarios(
            items=tuple(items), pagina=pagina, tamano_pagina=tamano_pagina,
            total=total, total_paginas=total_pages, has_previous=pagina > 1,
            has_next=pagina < total_pages, estado="ready" if items else "empty",
            mensaje="Usuarios cargados." if items else MENSAJE_SIN_RESULTADOS,
            cuentas_filtro=tuple(cuentas.items()),
        )
    except Exception as ex:
        print("[USUARIOS_ADMIN][ERROR] listado", f"actor={safe_get(contexto or {}, 'usr_usuario_id')}", f"pagina={pagina}", f"tipo={type(ex).__name__}")
        return ResultadoPaginadoUsuarios(pagina=pagina, tamano_pagina=tamano_pagina, estado="error", mensaje=MENSAJE_ERROR)


def _cuentas_por_ids(supabase: Any, ids: list[int]) -> dict[int, dict[str, Any]]:
    if not ids:
        return {}
    rows = _filas(supabase.table("evp_cta_cuenta").select("cta_cuenta_id,cta_nombre_cuenta,cta_estado").in_("cta_cuenta_id", ids).execute())
    return {int(row["cta_cuenta_id"]): row for row in rows}


def _eventos_cuentas(supabase: Any, ids: list[int]) -> dict[tuple[int, int], dict[str, Any]]:
    if not ids:
        return {}
    rows = _filas(
        supabase.table("evp_eve_evento")
        .select("eve_cuenta_id,eve_evento_id,eve_nombre_evento,eve_estado,eve_fase_evento")
        .in_("eve_cuenta_id", ids).order("eve_cuenta_id").order("eve_evento_id").execute()
    )
    return {(int(row["eve_cuenta_id"]), int(row["eve_evento_id"])): row for row in rows}


def obtener_detalle_usuario(supabase: Any, contexto: dict[str, Any] | None, usuario_id: Any) -> ResultadoDetalleUsuario:
    if not _actor_valido(contexto):
        return ResultadoDetalleUsuario(False, "denied", MENSAJE_SIN_PERMISO)
    target_id = str(usuario_id or "").strip()
    if not target_id:
        return ResultadoDetalleUsuario(False, "not_found", MENSAJE_DETALLE_NO_ENCONTRADO)
    try:
        visible_accounts = obtener_cuentas_visibles(supabase, contexto)
        visible_relations = _relaciones_visibles(supabase, list(visible_accounts), [target_id])
        if not _es_master(contexto) and not visible_relations:
            print("[USUARIOS_ADMIN][WARNING] detalle_denegado", f"actor={contexto.get('usr_usuario_id')}", f"objetivo={target_id}")
            return ResultadoDetalleUsuario(False, "denied", MENSAJE_DETALLE_DENEGADO)
        rows = _filas(supabase.table("evp_usr_usuario").select(_SELECT_USUARIO).eq("usr_usuario_id", target_id).limit(1).execute())
        if not rows:
            return ResultadoDetalleUsuario(False, "not_found", MENSAJE_DETALLE_NO_ENCONTRADO)
        user = rows[0]
        if _es_master(contexto):
            all_relations = _filas(
                supabase.table("evp_ucu_usuario_cuenta")
                .select("ucu_cuenta_id,ucu_usuario_id,ucu_rol,ucu_estado")
                .eq("ucu_usuario_id", target_id).execute()
            )
            visible_relations = all_relations
        relation_account_ids = _ids(_int(row.get("ucu_cuenta_id")) for row in visible_relations)
        target_is_master = bool(user.get("usr_es_usuario_master"))
        account_ids = list(visible_accounts) if target_is_master else relation_account_ids
        account_rows = _cuentas_por_ids(supabase, account_ids)
        account_models: list[UsuarioCuentaResumen] = []
        relation_by_account = {_int(row.get("ucu_cuenta_id")): row for row in visible_relations}
        for account_id in account_ids:
            account = account_rows.get(account_id, {})
            relation = relation_by_account.get(account_id, {})
            role = "Master" if target_is_master else str(relation.get("ucu_rol") or "")
            relation_state = "Heredado" if target_is_master and not relation else str(relation.get("ucu_estado") or "Sin relación")
            active = str(user.get("usr_estado")) == "Activo" and str(account.get("cta_estado")) == "Activo" and (target_is_master or relation_state == "Activo")
            account_models.append(UsuarioCuentaResumen(
                cuenta_id=account_id,
                cuenta_nombre=str(account.get("cta_nombre_cuenta") or visible_accounts.get(account_id) or f"Cuenta {account_id}"),
                rol=role, estado_relacion=relation_state,
                estado_cuenta=str(account.get("cta_estado") or ""),
                es_predeterminada=_int(user.get("usr_cuenta_id_default")) == account_id,
                acceso_heredado=target_is_master or role == ROL_ADMINISTRADOR,
                acceso_efectivo=active,
            ))
        events = _eventos_cuentas(supabase, account_ids)
        assignments = _filas(
            supabase.table("evp_uev_usuario_evento")
            .select("uev_cuenta_id,uev_evento_id,uev_usuario_id,uev_estado")
            .eq("uev_usuario_id", target_id)
            .in_("uev_cuenta_id", account_ids).execute()
        ) if account_ids else []
        assignment_by_key = {(_int(row.get("uev_cuenta_id")), _int(row.get("uev_evento_id"))): row for row in assignments}
        inherited_accounts = {item.cuenta_id for item in account_models if item.rol == ROL_ADMINISTRADOR}
        event_keys = set(events) if target_is_master else set(assignment_by_key)
        event_keys.update(key for key in events if key[0] in inherited_accounts)
        event_models: list[UsuarioEventoResumen] = []
        warnings: list[str] = []
        account_model_by_id = {item.cuenta_id: item for item in account_models}
        for key in sorted(event_keys):
            event = events.get(key)
            if not event:
                warnings.append(f"La asignación del evento {key[0]}/{key[1]} no corresponde a un evento visible.")
                continue
            assignment = assignment_by_key.get(key)
            account_model = account_model_by_id.get(key[0])
            if target_is_master:
                access_type = "Global"
                relation_state = None
            elif key[0] in inherited_accounts:
                access_type = "Heredado"
                relation_state = str(assignment.get("uev_estado")) if assignment else None
            else:
                access_type = "Asignado" if assignment else "Sin acceso"
                relation_state = str(assignment.get("uev_estado")) if assignment else None
            effective = bool(
                account_model and account_model.acceso_efectivo
                and str(event.get("eve_estado")) == "Activo"
                and (access_type in {"Global", "Heredado"} or relation_state == "Activo")
            )
            if assignment and assignment.get("uev_estado") == "Activo" and account_model and account_model.estado_relacion not in {"Activo", "Heredado"}:
                warnings.append(f"Evento {key[0]}/{key[1]} tiene asignación activa con relación de cuenta inactiva.")
                effective = False
            event_models.append(UsuarioEventoResumen(
                cuenta_id=key[0], cuenta_nombre=account_model.cuenta_nombre if account_model else f"Cuenta {key[0]}",
                evento_id=key[1], evento_nombre=str(event.get("eve_nombre_evento") or f"Evento {key[1]}"),
                estado_evento=str(event.get("eve_estado") or ""), fase_evento=str(event.get("eve_fase_evento") or ""),
                estado_relacion=relation_state,
                es_predeterminado=_int(user.get("usr_cuenta_id_default")) == key[0] and _int(user.get("usr_evento_id_default")) == key[1],
                tipo_acceso=access_type, acceso_efectivo=effective,
            ))
        if not account_models:
            warnings.append("El usuario no tiene cuentas visibles vinculadas.")
        if str(user.get("usr_estado")) == "Preregistrado" and not user.get("usr_usuario_auth_uuid"):
            warnings.append("Usuario preregistrado sin vínculo Auth.")
        elif str(user.get("usr_estado")) == "Activo" and not user.get("usr_usuario_auth_uuid"):
            warnings.append("Usuario activo sin UUID Auth.")
        default_account = _int(user.get("usr_cuenta_id_default"))
        default_event = _int(user.get("usr_evento_id_default"))
        if not _es_master(contexto) and default_account not in account_ids:
            default_account = None
            default_event = None
        default_account_row = account_rows.get(default_account or -1, {})
        if default_account is not None and not default_account_row:
            default_account_row = _cuentas_por_ids(supabase, [default_account]).get(default_account, {})
        default_event_row = events.get((default_account, default_event), {})
        if default_account is not None and default_event is not None and not default_event_row:
            default_event_row = _eventos_cuentas(supabase, [default_account]).get((default_account, default_event), {})
        default_account_name = str(default_account_row.get("cta_nombre_cuenta") or "") or None
        default_event_name = str(default_event_row.get("eve_nombre_evento") or "") or None
        if default_account is not None and not any(item.cuenta_id == default_account and item.acceso_efectivo for item in account_models):
            warnings.append("La cuenta predeterminada no pertenece al acceso efectivo visible.")
        if default_event is not None and not any(item.cuenta_id == default_account and item.evento_id == default_event and item.acceso_efectivo for item in event_models):
            warnings.append("El evento predeterminado no pertenece al acceso efectivo visible.")
        accessible_accounts = tuple(item.cuenta_id for item in account_models if item.acceso_efectivo)
        accessible_events = tuple((item.cuenta_id, item.evento_id) for item in event_models if item.acceso_efectivo)
        if str(user.get("usr_estado")) == "Activo" and not accessible_events:
            warnings.append("Usuario activo sin acceso efectivo a eventos.")
        reasons = tuple(dict.fromkeys(item.tipo_acceso for item in event_models if item.acceso_efectivo))
        access = AccesoEfectivoUsuario(target_is_master, accessible_accounts, accessible_events, reasons, tuple(warnings))
        detail = UsuarioDetalle(
            usuario_id=target_id, nombre=str(user.get("usr_nombre_usuario") or ""),
            nombre_abreviado=str(user.get("usr_nombre_usuario_abrev") or ""), email=str(user.get("usr_email") or ""),
            estado=str(user.get("usr_estado") or ""), es_master=target_is_master,
            auth_uuid_presente=bool(user.get("usr_usuario_auth_uuid")), cuenta_id_default=default_account,
            evento_id_default=default_event, cuenta_default_nombre=default_account_name,
            evento_default_nombre=default_event_name, telefono=user.get("usr_telefono"), cuentas=tuple(account_models),
            eventos=tuple(event_models), acceso_efectivo=access, advertencias=tuple(warnings),
            creado=user.get("usr_creado"), modificado=user.get("usr_modificado"),
            creado_por_actor=str(user.get("usr_creado_por") or "") == str((contexto or {}).get("usr_usuario_id") or ""),
        )
        return ResultadoDetalleUsuario(True, "ready", "Usuario cargado.", detail)
    except Exception as ex:
        print("[USUARIOS_ADMIN][ERROR] detalle", f"actor={safe_get(contexto or {}, 'usr_usuario_id')}", f"objetivo={target_id}", f"tipo={type(ex).__name__}")
        return ResultadoDetalleUsuario(False, "error", MENSAJE_DETALLE_ERROR)
