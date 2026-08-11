from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from models.usuario_admin_models import (
    ActualizarPreferenciasRequest, ActualizarUsuarioRequest, CambiarEstadoUsuarioRequest,
    CambiarMasterRequest, CrearUsuarioRequest,
)
from services.usuario_admin_service import (
    actualizar_preferencias, actualizar_usuario, cambiar_estado_usuario, cambiar_master, crear_usuario,
)


class FakeRPC:
    def __init__(self, owner, name, params): self.owner, self.name, self.params = owner, name, params
    def execute(self):
        self.owner.executions += 1
        if self.owner.error: raise RuntimeError(self.owner.error)
        return SimpleNamespace(data={"ok": True, "codigo": "OK", "usuario_id": self.params.get("p_usuario_id") or "11111111-1111-1111-1111-111111111111"})


class FakeSupabase:
    def __init__(self, error=""): self.calls, self.executions, self.error = [], 0, error
    def rpc(self, name, params): self.calls.append((name, params)); return FakeRPC(self, name, params)
    def table(self, name): raise AssertionError("No debe existir escritura administrativa directa")


MASTER = {"usr_usuario_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", "usr_es_usuario_master": True}
ADMIN = {"usr_usuario_id": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb", "rol_global_calculado": "Administrador"}
OPERADOR = {"usr_usuario_id": "cccccccc-cccc-cccc-cccc-cccccccccccc", "rol_global_calculado": "Operador"}
TARGET = "dddddddd-dddd-dddd-dddd-dddddddddddd"


def main() -> None:
    for rol in ("Master", "Administrador", "Operador", "Consulta"):
        db = FakeSupabase()
        result = crear_usuario(db, MASTER, CrearUsuarioRequest("Ana Pérez", "ANA@EXAMPLE.COM", rol, 2, 8))
        assert result.ok
        assert db.calls == [("evp_admin_crear_usuario", {"p_nombre": "Ana Pérez", "p_email": "ana@example.com", "p_rol": rol, "p_cuenta_id": 2, "p_evento_id": 8})]
    for rol in ("Operador", "Consulta"):
        assert crear_usuario(FakeSupabase(), ADMIN, CrearUsuarioRequest("Ana", "ana@example.com", rol, 2, 8)).ok
    for rol in ("Master", "Administrador"):
        assert crear_usuario(FakeSupabase(), ADMIN, CrearUsuarioRequest("Ana", "ana@example.com", rol, 2, 8)).codigo == "USER_ADMIN_FORBIDDEN"
    assert not crear_usuario(FakeSupabase(), OPERADOR, CrearUsuarioRequest("Ana", "ana@example.com", "Operador", 2, 8)).ok
    for args in (("Ana", "a@b.com", "", 2, 8), ("Ana", "a@b.com", "Operador", 0, 8), ("Ana", "a@b.com", "Operador", 2, 0)):
        try: CrearUsuarioRequest(*args)
        except ValueError: pass
        else: raise AssertionError("Request inválido aceptado")
    db = FakeSupabase(); assert actualizar_usuario(db, ADMIN, ActualizarUsuarioRequest(TARGET, "Nuevo", "nuevo@example.com")).ok
    assert not cambiar_estado_usuario(FakeSupabase(), MASTER, CambiarEstadoUsuarioRequest(MASTER["usr_usuario_id"], "Inactivo")).ok
    assert cambiar_estado_usuario(FakeSupabase(), MASTER, CambiarEstadoUsuarioRequest(TARGET, "Inactivo")).ok
    assert not cambiar_master(FakeSupabase(), ADMIN, CambiarMasterRequest(TARGET, True)).ok
    db = FakeSupabase(); assert actualizar_preferencias(db, OPERADOR, ActualizarPreferenciasRequest(2, 8)).ok
    assert db.calls[0] == ("evp_usuario_actualizar_preferencias", {"p_cuenta_id": 2, "p_evento_id": 8})

    sql = (ROOT / "supabase/migrations/202608100001_user_access_defaults_preferences.sql").read_text(encoding="utf-8").lower()
    home = (ROOT / "views/home_view.py").read_text(encoding="utf-8")
    service = (ROOT / "services/usuario_admin_service.py").read_text(encoding="utf-8")
    assert "usr_creado_por is distinct from" not in sql
    assert all(name in sql for name in ("evp_admin_crear_usuario", "evp_admin_actualizar_usuario", "evp_admin_cambiar_rol_cuenta", "evp_admin_cambiar_estado_cuenta", "evp_usuario_actualizar_preferencias"))
    create = sql.split("create or replace function public.evp_admin_crear_usuario", 1)[1].split("$$;", 1)[0]
    assert create.index("insert into public.evp_usr_usuario") < create.index("insert into public.evp_ucu_usuario_cuenta") < create.index("insert into public.evp_uev_usuario_evento") < create.index("update public.evp_usr_usuario")
    assert "p_rol<>'master'" in create and "p_rol in ('operador','consulta')" in create
    assert "relacion_cuenta_creada" in create and "relacion_evento_creada" in create
    assert "auth.uid()" in sql and "security definer set search_path=''" in sql
    assert "revoke all" in sql and "service_role" not in service and ".insert(" not in service
    assert "Cuenta inicial / predeterminada" in home and "read_only=True" in home
    assert "nombre_cuenta" in home and "nombre_evento" in home
    assert "DropdownOption(key=str(cid), text=name)" in home
    assert "DropdownOption(key=str(item[\"evento_id\"]), text=str(item.get(\"nombre_evento\")" in home
    assert "Preferencias actualizadas correctamente." in home and "construir_preferencias" in home
    acceso = sql.split("create or replace function public.evp_priv_usuario_tiene_acceso", 1)[1].split("$$;", 1)[0]
    elegibilidad = sql.split("create or replace function public.evp_priv_usuario_puede_tener_default", 1)[1].split("$$;", 1)[0]
    limpieza = sql.split("create or replace function public.evp_priv_limpiar_defaults", 1)[1].split("$$;", 1)[0]
    preferencias = sql.split("create or replace function public.evp_usuario_actualizar_preferencias", 1)[1].split("$$;", 1)[0]
    estado_cuenta = sql.split("create or replace function public.evp_admin_cambiar_estado_cuenta", 1)[1].split("$$;", 1)[0]
    assert "u.usr_estado='activo'" in acceso and "preregistrado" not in acceso
    assert "u.usr_estado in ('activo','preregistrado')" in elegibilidad
    assert "evp_priv_usuario_puede_tener_default" in limpieza and "evp_priv_usuario_tiene_acceso" not in limpieza
    assert "usr_estado='activo'" in preferencias and "evp_priv_usuario_tiene_acceso" in preferencias
    assert "a.usr_es_usuario_master" in estado_cuenta
    assert "r.ucu_rol not in ('operador','consulta')" in estado_cuenta
    assert "update public.evp_ucu_usuario_cuenta set ucu_estado=p_estado" in estado_cuenta
    assert "delete from public.evp_uev_usuario_evento" not in estado_cuenta
    assert "evp_priv_limpiar_defaults(p_usuario_id)" in estado_cuenta
    assert "usr_cuenta_id_default=" not in estado_cuenta and "usr_evento_id_default=" not in estado_cuenta
    acl_test = (ROOT / "scripts/test_user_access_defaults_preferences_rpc.sql").read_text(encoding="utf-8").lower()
    assert all(name in acl_test for name in (
        "evp_admin_crear_usuario", "evp_admin_actualizar_usuario", "evp_admin_cambiar_rol_cuenta",
        "evp_admin_cambiar_estado_cuenta", "evp_usuario_actualizar_preferencias",
        "evp_admin_cambiar_estado_usuario", "evp_priv_usuario_tiene_acceso",
        "evp_priv_usuario_puede_tener_default", "evp_priv_limpiar_defaults",
    ))
    assert all(token in acl_test for token in ("prosecdef", "proconfig", "owner_name", "authenticated", "anon", "grantee=0", "firma obsoleta"))
    rollback_new = (ROOT / "supabase/migrations/202608100001_user_access_defaults_preferences_rollback.sql").read_text(encoding="utf-8").lower()
    assert "drop function if exists public.evp_priv_usuario_puede_tener_default" in rollback_new
    print("OK: perfil, acceso, defaults y preferencias de usuarios")


if __name__ == "__main__": main()
