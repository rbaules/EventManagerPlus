from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


MIGRATION = ROOT / "supabase" / "migrations" / "202610110001_kiosk_admin_pin.sql"
SERVICE = ROOT / "services" / "kiosk_admin_service.py"
FUNCTIONAL_TEST = ROOT / "scripts" / "test_kiosk_admin_pin_rpc.sql"


def test_secure_database_contract() -> None:
    source = MIGRATION.read_text(encoding="utf-8")
    assert "CREATE TABLE public.evp_kpa_kiosco_pin_administrativo" in source
    assert "PRIMARY KEY (kpa_cuenta_id, kpa_evento_id)" in source
    assert "ENABLE ROW LEVEL SECURITY" in source
    assert "REVOKE ALL ON TABLE public.evp_kpa_kiosco_pin_administrativo FROM PUBLIC, anon, authenticated" in source
    assert "extensions.crypt(p_pin, extensions.gen_salt('bf', 12))" in source
    assert "p_pin !~ '^[0-9]{6}$'" in source
    assert source.count("'KIOSK_ADMIN_DENIED'") >= 6
    assert "r.ucu_rol = 'Administrador'" in source
    assert "r.ucu_rol = 'Operador'" in source
    assert "r.ucu_rol = 'Consulta'" not in source[source.index("evp_kpa_validar_pin_administrativo"):source.index("evp_kpa_configurar_pin_administrativo")]
    assert "SECURITY DEFINER" in source and "SET search_path = ''" in source
    assert "GRANT EXECUTE ON FUNCTION public.evp_kpa_validar_pin_administrativo" in source
    assert "GRANT EXECUTE ON FUNCTION public.evp_kpa_configurar_pin_administrativo" in source


def test_client_contract_never_logs_or_authorizes_locally() -> None:
    source = SERVICE.read_text(encoding="utf-8")
    assert "print(" not in source and "logging." not in source
    assert "evp_kpa_validar_pin_administrativo" in source
    assert "evp_kpa_configurar_pin_administrativo" in source
    assert "KIOSK_ADMIN_ALLOWED" in source and "KIOSK_ADMIN_DENIED" in source
    assert "authorization_service" not in source
    assert "puede_" not in source


def test_functional_sql_keeps_the_pin_and_hash_out_of_results() -> None:
    source = FUNCTIONAL_TEST.read_text(encoding="utf-8")
    assert "'<MASTER_O_ADMIN_AUTH_UUID>'" in source
    assert "'<PIN_DE_PRUEBA>'" in source
    assert "SELECT kpa_pin_hash" not in source
    assert "set_config('request.jwt.claim.sub'" in source
    assert source.rstrip().endswith("ROLLBACK;")


def main() -> None:
    test_secure_database_contract()
    test_client_contract_never_logs_or_authorizes_locally()
    test_functional_sql_keeps_the_pin_and_hash_out_of_results()
    print("Kiosk admin PIN contract tests passed.")


if __name__ == "__main__":
    main()
