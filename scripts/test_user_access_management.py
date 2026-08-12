from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from models.usuario_admin_models import AgregarCuentaUsuarioRequest, CambiarEstadoEventoUsuarioRequest
from services.usuario_admin_service import agregar_cuenta_usuario, agregar_evento_usuario, cambiar_estado_evento_usuario, buscar_usuario_para_cuenta

class Response:
    def __init__(self, data): self.data = data


class RPC:
    def __init__(self, owner, name, params): self.owner, self.name, self.params = owner, name, params
    def execute(self):
        self.owner.calls.append((self.name, self.params))
        if self.name == "evp_admin_buscar_usuario_para_cuenta":
            return Response([{"usuario_id": "00000000-0000-0000-0000-000000000002", "nombre": "Ana", "email": "ana@example.com", "estado": "Preregistrado", "rol_cuenta": None, "estado_relacion": None}])
        return Response({"ok": True, "codigo": "OK"})


class DB:
    def __init__(self): self.calls = []
    def rpc(self, name, params): return RPC(self, name, params)


def main() -> None:
    # Estas son pruebas Python de contrato de servicio/UI y estructura SQL.
    # La integración PostgreSQL real está preparada por separado en el script .sql.
    db = DB(); context = {"usr_usuario_id": "actor", "usr_es_usuario_master": True}
    uid = "00000000-0000-0000-0000-000000000001"
    assert agregar_cuenta_usuario(db, context, AgregarCuentaUsuarioRequest(uid, 1, "Operador", 2)).ok
    event = CambiarEstadoEventoUsuarioRequest(uid, 1, 2, "Activo")
    assert agregar_evento_usuario(db, context, event).ok
    assert cambiar_estado_evento_usuario(db, context, event).ok
    candidates = buscar_usuario_para_cuenta(db, context, 1, "ana")
    assert len(candidates) == 1 and candidates[0].estado == "Preregistrado" and candidates[0].rol_cuenta is None
    assert not buscar_usuario_para_cuenta(db, context, 1, "a")
    assert [call[0] for call in db.calls] == ["evp_admin_agregar_cuenta_usuario", "evp_admin_agregar_evento_usuario", "evp_admin_cambiar_estado_evento_usuario", "evp_admin_buscar_usuario_para_cuenta"]
    sql = (ROOT / "supabase/migrations/202608110003_user_access_management.sql").read_text(encoding="utf-8").lower()
    for name in ("evp_admin_agregar_cuenta_usuario", "evp_admin_agregar_evento_usuario", "evp_admin_cambiar_estado_evento_usuario", "evp_admin_buscar_usuario_para_cuenta"):
        assert f"create or replace function public.{name}" in sql
    assert "security definer set search_path=''" in sql and "auth.uid()" in sql
    assert "delete from public.evp_ucu_usuario_cuenta" not in sql and "delete from public.evp_uev_usuario_evento" not in sql
    assert "target_account_admin_forbidden" in sql
    assert "r.ucu_cuenta_id=p_cuenta_id" in sql and "limit 20" in sql
    search_sql = sql.split("create or replace function public.evp_admin_buscar_usuario_para_cuenta", 1)[1].split("end; $$;", 1)[0]
    assert "usr_es_usuario_master" in search_sql and "usr_estado in ('activo','preregistrado')" in search_sql
    assert "'rol_cuenta'" in search_sql and "'estado_relacion'" in search_sql
    assert "cuenta_nombre" not in search_sql and "evento" not in search_sql
    add_sql = sql.split("create or replace function public.evp_admin_agregar_cuenta_usuario", 1)[1].split("end; $$;", 1)[0]
    assert "r.ucu_rol='administrador'" in add_sql and "r.ucu_cuenta_id" not in add_sql  # r ya fue bloqueada por la clave p_cuenta_id.
    assert "evp_priv_8d_aplicar_transicion_rol" in add_sql and "p_evento_inicial_id,true" in add_sql
    assert "old_default_account:=t.usr_cuenta_id_default" in add_sql
    assert "usr_cuenta_id_default=p_cuenta_id" not in add_sql and "usr_evento_id_default=p_evento_inicial_id" not in add_sql
    assert add_sql.index("usr_cuenta_id_default=old_default_account") < add_sql.index("evp_priv_limpiar_defaults(p_usuario_id)")
    helper_sql = sql.split("create function public.evp_priv_8d_aplicar_transicion_rol", 1)[1].split("end; $$;", 1)[0]
    assert "p_rol_anterior in ('operador','consulta') and p_rol_nuevo='administrador'" in helper_sql
    assert "p_rol_anterior='administrador' and p_rol_nuevo in ('operador','consulta')" in helper_sql
    assert "set uev_estado='inactivo'" in helper_sql and "on conflict" in helper_sql
    assert "p_es_reactivacion and p_rol_nuevo in ('operador','consulta')" in helper_sql
    assert "delete from" not in helper_sql
    role_sql = sql.split("create or replace function public.evp_priv_8d_cambiar_rol_cuenta", 1)[1].split("end; $$;", 1)[0]
    assert "evp_priv_8d_aplicar_transicion_rol" in role_sql
    for signature in (
        "evp_priv_8d_cambiar_rol_cuenta(uuid,integer,text,integer)",
        "evp_priv_8d_cambiar_estado_cuenta(uuid,integer,text)",
        "evp_priv_8d_aplicar_transicion_rol(uuid,integer,text,text,integer,boolean)",
    ):
        assert f"revoke all on function public.{signature} from public,anon,authenticated" in sql
    assert "alter function public.evp_priv_8d_cambiar_estado_cuenta(uuid,integer,text) security definer" in sql
    assert "alter function public.evp_priv_8d_cambiar_estado_cuenta(uuid,integer,text) set search_path=''" in sql
    view = (ROOT / "views/user_admin_view.py").read_text(encoding="utf-8")
    for label in ("Agregar cuenta", "Agregar evento", "Usuario Master"):
        assert label in view
    print("OK: administracion general UCU/UEV")


if __name__ == "__main__": main()
