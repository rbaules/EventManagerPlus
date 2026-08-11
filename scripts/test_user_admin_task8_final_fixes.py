from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    checks = 0
    def check(value: bool, label: str) -> None:
        nonlocal checks
        assert value, label
        checks += 1

    migration = (ROOT / "supabase/migrations/202608110001_user_admin_task8_final_fixes.sql").read_text(encoding="utf-8").lower()
    rollback = (ROOT / "supabase/migrations/202608110001_user_admin_task8_final_fixes_rollback.sql").read_text(encoding="utf-8").lower()
    edit_guard = (ROOT / "supabase/migrations/202608110002_user_edit_status_guard.sql").read_text(encoding="utf-8").lower()
    edit_rollback = (ROOT / "supabase/migrations/202608110002_user_edit_status_guard_rollback.sql").read_text(encoding="utf-8").lower()
    service = (ROOT / "services/usuario_admin_service.py").read_text(encoding="utf-8")
    access_sql = (ROOT / "supabase/migrations/202608100001_user_access_defaults_preferences.sql").read_text(encoding="utf-8").lower()
    home = (ROOT / "views/home_view.py").read_text(encoding="utf-8")
    view = (ROOT / "views/user_admin_view.py").read_text(encoding="utf-8")
    capabilities = (ROOT / "services/authorization_service.py").read_text(encoding="utf-8")

    promote = migration.split("create or replace function public.evp_admin_convertir_master", 1)[1].split("$$;", 1)[0]
    state = migration.split("create or replace function public.evp_admin_cambiar_estado_usuario", 1)[1].split("$$;", 1)[0]
    edit_applied = access_sql.split("create or replace function public.evp_admin_actualizar_usuario", 1)[1].split("$$;", 1)[0]
    effective = access_sql.split("create or replace function public.evp_priv_usuario_tiene_acceso", 1)[1].split("$$;", 1)[0]

    check("t.usr_estado not in ('activo','preregistrado')" in promote, "Promocion admite Activo/Preregistrado")
    check("usr_es_usuario_master=true" in promote, "Promocion activa Master")
    check("update public.evp_ucu_usuario_cuenta set ucu_estado='inactivo'" in promote, "Promocion inactiva UCU")
    check("usr_estado=" not in promote, "Promocion no altera estado")
    check("invalid_master_target_status" in promote, "Estado objetivo invalido tiene codigo claro")
    check("usr_estado='activo'" in effective and "preregistrado" not in effective, "Acceso operativo sigue rechazando Preregistrado")

    check("p_estado='inactivo' and t.usr_estado not in ('activo','preregistrado')" in state, "Preregistrado puede inactivarse")
    check("p_estado='activo' and t.usr_usuario_auth_uuid is null" in state, "Reactivacion exige Auth")
    check("self_deactivation_forbidden" in state and "last_master" in state, "Protecciones globales conservadas")
    check("usr_cuenta_id_default" not in state and "usr_evento_id_default" not in state, "Inactivacion conserva defaults")

    check("usr_creado_por" not in edit_applied, "RPC de edicion no autoriza por creador")
    check("a.ucu_rol='administrador'" in edit_applied and "t.ucu_rol in ('operador','consulta')" in edit_applied, "RPC edita por alcance compartido")
    check("detalle.creado_por_actor" not in home, "UI no autoriza por creador")
    check("if capacidades.usuarios_admin_editar_global:" in home, "Edicion global se evalua antes del rol objetivo")
    check("if detalle.es_master:" in home, "Solo Admin restringe objetivo Master")
    check("usuarios_admin_editar_datos" in capabilities, "Capability de edicion separada")
    for name in ("usuarios_admin_inactivar_global", "usuarios_admin_activar_global", "usuarios_admin_inactivar_en_cuenta", "usuarios_admin_convertir_master", "usuarios_admin_retirar_master", "usuarios_admin_cambiar_rol"):
        check(name in capabilities, f"Capability presente: {name}")

    check('{"Activo", "Preregistrado"}' in service, "Grid cuenta alcance configurado para Preregistrado")
    check("Cuentas permitidas" in view and "Eventos permitidos" in view, "Encabezados aclaran semantica")
    check('detalle.estado in {"Activo", "Preregistrado"}' in view, "UI permite inactivar Preregistrado")
    check("Inactivo — sin identidad de autenticación vinculada" in view, "UI explica Inactivo sin Auth")
    check('"usuarios_admin_listado_request"' in home, "Listado usa generacion de consulta")
    check("listado obsoleto descartado" in home, "Respuestas stale del listado se ignoran")
    check("detalle obsoleto descartado" in home, "Respuestas stale del detalle se ignoran")
    check("cargar_detalle_usuario(target_id, on_complete=cargar_usuarios_admin)" in home, "Refresco secuencia detalle antes de listado")
    check('or state["usuarios_admin_loading"]' not in home, "Loading no se convierte en acceso denegado")
    check("update public.evp_ucu_usuario_cuenta" not in state and "update public.evp_uev_usuario_evento" not in state, "Inactivacion global conserva UCU/UEV")
    check('("Master",)' in service and 'item.get("ucu_estado") == "Activo"' in service, "Grid muestra solo roles vigentes y Master dominante")
    check("puede_cambiar_rol" in view and "usuarios_admin_cambiar_rol" in home, "Cambio de rol conectado a capability")
    check('detalle.estado in {"Activo", "Preregistrado"}' in view, "Conversion Master visible solo para estados permitidos")
    edit_rpc = edit_guard.split("create or replace function public.evp_admin_actualizar_usuario", 1)[1].split("$$;", 1)[0]
    check("v_target.usr_estado not in ('activo','preregistrado')" in edit_rpc, "RPC rechaza Inactivo/Suspendido")
    check("user_edit_invalid_status" in edit_rpc, "RPC devuelve codigo controlado por estado")
    check("update public.evp_ucu_usuario_cuenta" not in edit_rpc and "update public.evp_uev_usuario_evento" not in edit_rpc, "Guard de edicion no mantiene UCU/UEV")
    check("create or replace function public.evp_admin_actualizar_usuario" in edit_rollback, "Rollback restaura RPC anterior")
    check('detalle.estado not in {"Activo", "Preregistrado"}' in home, "Capability UI considera estado objetivo")
    check("if puede_editar_datos:" in view, "Vista no omite capability para actor Master")
    check("create or replace function public.evp_admin_convertir_master" in rollback and "create or replace function public.evp_admin_cambiar_estado_usuario" in rollback, "Rollback restaura ambas RPC")
    print(f"OK: {checks} comprobaciones de correcciones finales de Tarea 8.")


if __name__ == "__main__":
    main()
