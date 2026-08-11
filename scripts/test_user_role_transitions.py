from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from models.usuario_admin_models import CambiarRolCuentaRequest, PromoverMasterRequest, RetirarMasterRequest
from services.usuario_admin_service import cambiar_rol_cuenta, promover_master, retirar_master

MASTER = {"usr_usuario_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", "usr_es_usuario_master": True, "usr_estado": "Activo"}
ADMIN = {"usr_usuario_id": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb", "usr_es_usuario_master": False, "rol_global_calculado": "Administrador"}
TARGET = "cccccccc-cccc-cccc-cccc-cccccccccccc"


class Response:
    data = {"ok": True, "codigo": "OK", "usuario_id": TARGET}


class FakeSupabase:
    def __init__(self): self.calls = []
    def rpc(self, name, params): self.calls.append((name, params)); return self
    def execute(self): return Response()


def rejected(factory, code):
    try: factory()
    except ValueError as ex: return str(ex) == code
    return False


def main():
    checks = 0
    def check(value, label):
        nonlocal checks
        assert value, label; checks += 1

    migration = (ROOT / "supabase/migrations/202608100002_user_role_transition_finalization.sql").read_text(encoding="utf-8").lower()
    rollback = (ROOT / "supabase/migrations/202608100002_user_role_transition_finalization_rollback.sql").read_text(encoding="utf-8").lower()
    home = (ROOT / "views/home_view.py").read_text(encoding="utf-8")
    view = (ROOT / "views/user_admin_view.py").read_text(encoding="utf-8")

    promote = migration.split("evp_admin_convertir_master", 1)[1].split("$$;", 1)[0]
    retire = migration.split("evp_admin_retirar_master", 1)[1].split("$$;", 1)[0]
    role = migration.split("create or replace function public.evp_admin_cambiar_rol_cuenta", 1)[1].split("$$;", 1)[0]
    check("usr_es_usuario_master=true" in promote, "Promocion activa Master")
    check("update public.evp_ucu_usuario_cuenta set ucu_estado='inactivo'" in promote, "Promocion inactiva UCU")
    check("evp_uev_usuario_evento" not in promote, "Promocion conserva UEV")
    check("cta_estado='activo'" in promote and "eve_estado='activo'" in promote, "Promocion valida defaults")
    check("pg_advisory_xact_lock(817301)" in promote, "Promocion usa lock Master")
    check("not a.usr_es_usuario_master" in promote, "Solo Master promueve")

    check("account_required" in retire and "event_required" in retire, "Retiro exige destino coherente")
    check("if p_evento_id is null" in retire and "p_rol in ('operador','consulta') and p_evento_id" not in retire, "Evento obligatorio para todo rol destino")
    check("self_master_change_forbidden" in retire and "last_master" in retire, "Retiro mantiene protecciones")
    check("on conflict (ucu_cuenta_id,ucu_usuario_id)" in retire, "Retiro reutiliza UCU")
    check("on conflict (uev_cuenta_id,uev_evento_id,uev_usuario_id)" in retire, "Retiro reutiliza UEV")
    check("update public.evp_uev_usuario_evento set uev_estado='inactivo'" in retire, "Retiro no reactiva UEV historicas")
    check("usr_cuenta_id_default=p_cuenta_id" in retire and "usr_evento_id_default=p_evento_id" in retire, "Retiro alinea defaults")

    check("r.ucu_rol not in ('operador','consulta')" in role, "Admin limitado a Operador/Consulta")
    check("r.ucu_rol='administrador'" in role and "event_required" in role, "Degradacion Admin exige evento")
    check("on conflict (uev_cuenta_id,uev_evento_id,uev_usuario_id)" in role, "Cambio rol reactiva UEV sin duplicar")
    check(role.count("update public.evp_uev_usuario_evento set uev_estado='inactivo'") == 2, "Ambas transiciones con Administrador inactivan UEV")
    check("where uev_usuario_id=p_usuario_id and uev_cuenta_id=p_cuenta_id" in role, "Inactivacion UEV limitada a la cuenta")
    check("delete" not in role, "Cambio rol conserva historico")
    check("evp_priv_limpiar_defaults" in role, "Cambio rol limpia defaults invalidos")

    check("security definer set search_path=''" in migration, "RPC Security Definer endurecidas")
    check("revoke all on function public.evp_admin_cambiar_master" in migration, "Ruta booleana insegura revocada")
    check(all(f"from {role_name};" in migration for role_name in ("public", "anon", "authenticated")), "ACL defensivas explicitas")
    check("grant execute on function public.evp_admin_convertir_master" in migration, "Solo authenticated ejecuta transiciones")
    check("grant execute on function public.evp_admin_cambiar_master" in rollback, "Rollback restaura promocion anterior")
    check("grant execute on function public.evp_admin_cambiar_rol_cuenta(uuid,integer,text)" in rollback, "Rollback restaura rol anterior")

    db = FakeSupabase(); check(promover_master(db, MASTER, PromoverMasterRequest(TARGET)).ok, "Servicio promueve")
    check(db.calls[-1][0] == "evp_admin_convertir_master", "Servicio usa RPC promocion")
    check(not promover_master(FakeSupabase(), ADMIN, PromoverMasterRequest(TARGET)).ok, "Admin no promueve")
    check(rejected(lambda: RetirarMasterRequest(TARGET, 0, "Administrador"), "ACCOUNT_REQUIRED"), "Retiro sin cuenta rechazado")
    check(rejected(lambda: RetirarMasterRequest(TARGET, 1, ""), "INVALID_ACCOUNT_ROLE"), "Retiro sin rol rechazado")
    check(rejected(lambda: RetirarMasterRequest(TARGET, 1, "Operador"), "EVENT_REQUIRED"), "Operador sin evento rechazado")
    check(rejected(lambda: RetirarMasterRequest(TARGET, 1, "Administrador"), "EVENT_REQUIRED"), "Administrador sin evento rechazado")
    check(retirar_master(FakeSupabase(), MASTER, RetirarMasterRequest(TARGET, 1, "Administrador", 10)).ok, "Retiro a Administrador")
    check(retirar_master(FakeSupabase(), MASTER, RetirarMasterRequest(TARGET, 1, "Operador", 10)).ok, "Retiro a Operador")
    check(not retirar_master(FakeSupabase(), MASTER, RetirarMasterRequest(MASTER["usr_usuario_id"], 1, "Administrador", 10)).ok, "Auto retiro rechazado")
    db = FakeSupabase(); check(cambiar_rol_cuenta(db, ADMIN, CambiarRolCuentaRequest(TARGET, 1, "Consulta")).ok, "Admin cambia Operador/Consulta")
    check(db.calls[-1][1]["p_evento_id"] is None, "Operador/Consulta no exige nuevo evento")
    check("Cambiar rol" in view and "on_role" in view, "Accion de rol en detalle")
    check("Cuenta inicial" in home and "Evento inicial" in home, "Dialogo retiro completo")
    check('evento.disabled = not bool(cuenta.value)' in home, "Selector evento disponible para Administrador")
    check("cargar_usuarios_admin()" in home, "Operaciones refrescan fuente autoritativa")
    check("Pendiente de autenticación" in view, "Preregistrado sin activar")
    rpc_tests = (ROOT / "scripts/test_user_role_transitions_rpc.sql").read_text(encoding="utf-8").lower()
    check(all(section in rpc_tests for section in ("a. verificacion read-only", "b. pruebas funcionales con escritura", "c. pruebas con jwt reales", "d. pruebas de concurrencia")), "Script SQL dividido en cuatro secciones")
    check("begin;" in rpc_tests and "rollback;" in rpc_tests, "Pruebas de escritura transaccionales")
    print(f"OK: {checks} comprobaciones de transiciones finales de rol.")


if __name__ == "__main__": main()
