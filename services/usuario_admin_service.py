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

_SELECT_USUARIO = (
    "usr_usuario_id,usr_nombre_usuario,usr_nombre_usuario_abrev,usr_email,"
    "usr_usuario_auth_uuid,usr_es_usuario_master,usr_cuenta_id_default,"
    "usr_evento_id_default,usr_telefono,usr_creado,usr_modificado,usr_estado"
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
        if (rol == "Todos" or row.get("ucu_rol") == rol)
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
        event_counts: dict[str, int] = {}
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
                event_counts[uid] = event_counts.get(uid, 0) + 1
        items: list[UsuarioResumen] = []
        for row in user_rows:
            uid = str(row.get("usr_usuario_id") or "")
            rels = by_user.get(uid, [])
            account_names = tuple(sorted({cuentas[cid] for item in rels if (cid := _int(item.get("ucu_cuenta_id"))) in cuentas}))
            roles = tuple(sorted({str(item.get("ucu_rol")) for item in rels if item.get("ucu_rol")}))
            items.append(UsuarioResumen(
                usuario_id=uid,
                nombre=str(row.get("usr_nombre_usuario") or ""),
                email=str(row.get("usr_email") or ""),
                estado=str(row.get("usr_estado") or ""),
                es_master=bool(row.get("usr_es_usuario_master")),
                auth_uuid_presente=bool(row.get("usr_usuario_auth_uuid")),
                cuentas_visibles=account_names,
                roles_visibles=roles,
                cantidad_eventos_asignados=event_counts.get(uid, 0),
                tiene_advertencia_auth=_advertencia_auth(row),
                acceso_global=bool(row.get("usr_es_usuario_master")),
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
        return ResultadoDetalleUsuario(False, "not_found", MENSAJE_DETALLE_DENEGADO)
    try:
        visible_accounts = obtener_cuentas_visibles(supabase, contexto)
        visible_relations = _relaciones_visibles(supabase, list(visible_accounts), [target_id])
        if not _es_master(contexto) and not visible_relations:
            print("[USUARIOS_ADMIN][WARNING] detalle_denegado", f"actor={contexto.get('usr_usuario_id')}", f"objetivo={target_id}")
            return ResultadoDetalleUsuario(False, "denied", MENSAJE_DETALLE_DENEGADO)
        rows = _filas(supabase.table("evp_usr_usuario").select(_SELECT_USUARIO).eq("usr_usuario_id", target_id).limit(1).execute())
        if not rows:
            return ResultadoDetalleUsuario(False, "not_found", MENSAJE_DETALLE_DENEGADO)
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
            evento_id_default=default_event, telefono=user.get("usr_telefono"), cuentas=tuple(account_models),
            eventos=tuple(event_models), acceso_efectivo=access, advertencias=tuple(warnings),
            creado=user.get("usr_creado"), modificado=user.get("usr_modificado"),
        )
        return ResultadoDetalleUsuario(True, "ready", "Usuario cargado.", detail)
    except Exception as ex:
        print("[USUARIOS_ADMIN][ERROR] detalle", f"actor={safe_get(contexto or {}, 'usr_usuario_id')}", f"objetivo={target_id}", f"tipo={type(ex).__name__}")
        return ResultadoDetalleUsuario(False, "error", MENSAJE_ERROR)
