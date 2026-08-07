from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.authorization_service import puede_ver_administracion_usuarios
from services.navigation_service import parse_app_route, route_for
from services.usuario_admin_service import listar_usuarios, obtener_detalle_usuario
from views.user_admin_view import user_admin_detail_view, user_admin_view


@dataclass
class Response:
    data: list[dict[str, Any]]
    count: int | None = None


class Query:
    def __init__(self, db: "FakeSupabase", table: str):
        self.db, self.table = db, table
        self.rows = [dict(row) for row in db.tables.get(table, [])]
        self.want_count = False
        self.range_value: tuple[int, int] | None = None

    def select(self, columns: str, count: str | None = None) -> "Query":
        self.want_count = count == "exact"
        self.db.operations.append(("SELECT", self.table))
        return self

    def eq(self, key: str, value: Any) -> "Query":
        self.rows = [row for row in self.rows if row.get(key) == value]
        return self

    def in_(self, key: str, values: list[Any]) -> "Query":
        allowed = {str(value) for value in values}
        self.rows = [row for row in self.rows if str(row.get(key)) in allowed]
        return self

    def or_(self, expression: str) -> "Query":
        terms = expression.split(",")
        needles = []
        for term in terms:
            parts = term.split(".ilike.%", 1)
            if len(parts) == 2:
                needles.append((parts[0], parts[1].rstrip("%").casefold()))
        self.rows = [row for row in self.rows if any(needle in str(row.get(key) or "").casefold() for key, needle in needles)]
        return self

    def order(self, key: str, desc: bool = False) -> "Query":
        self.rows.sort(key=lambda row: str(row.get(key) or "").casefold(), reverse=desc)
        return self

    def range(self, start: int, end: int) -> "Query":
        self.range_value = (start, end)
        return self

    def limit(self, value: int) -> "Query":
        self.range_value = (0, value - 1)
        return self

    def execute(self) -> Response:
        total = len(self.rows)
        rows = self.rows
        if self.range_value:
            rows = rows[self.range_value[0]:self.range_value[1] + 1]
        return Response(rows, total if self.want_count else None)

    def insert(self, *args: Any, **kwargs: Any) -> None:
        raise AssertionError("INSERT no permitido")

    update = insert
    delete = insert


class FakeSupabase:
    def __init__(self, tables: dict[str, list[dict[str, Any]]]):
        self.tables = tables
        self.operations: list[tuple[str, str]] = []

    def table(self, name: str) -> Query:
        return Query(self, name)


def fixture() -> FakeSupabase:
    users = [
        {"usr_usuario_id": "master", "usr_nombre_usuario": "Ana Master", "usr_nombre_usuario_abrev": "AM", "usr_email": "ana@example.com", "usr_usuario_auth_uuid": "auth-master", "usr_es_usuario_master": True, "usr_cuenta_id_default": 1, "usr_evento_id_default": 1, "usr_telefono": None, "usr_creado": "2026-01-01", "usr_modificado": None, "usr_estado": "Activo"},
        {"usr_usuario_id": "admin-a", "usr_nombre_usuario": "Beto Admin", "usr_nombre_usuario_abrev": "BA", "usr_email": "beto@example.com", "usr_usuario_auth_uuid": "auth-admin", "usr_es_usuario_master": False, "usr_cuenta_id_default": 1, "usr_evento_id_default": 2, "usr_telefono": None, "usr_creado": "2026-01-02", "usr_modificado": None, "usr_estado": "Activo"},
        {"usr_usuario_id": "shared", "usr_nombre_usuario": "Carla Compartida", "usr_nombre_usuario_abrev": "CC", "usr_email": "carla@example.com", "usr_usuario_auth_uuid": None, "usr_es_usuario_master": False, "usr_cuenta_id_default": 1, "usr_evento_id_default": 99, "usr_telefono": None, "usr_creado": "2026-01-03", "usr_modificado": None, "usr_estado": "Activo"},
        {"usr_usuario_id": "foreign", "usr_nombre_usuario": "Dora Externa", "usr_nombre_usuario_abrev": "DE", "usr_email": "dora@example.com", "usr_usuario_auth_uuid": "auth-foreign", "usr_es_usuario_master": False, "usr_cuenta_id_default": 2, "usr_evento_id_default": 1, "usr_telefono": None, "usr_creado": "2026-01-04", "usr_modificado": None, "usr_estado": "Activo"},
        {"usr_usuario_id": "pre", "usr_nombre_usuario": "Eva Pendiente", "usr_nombre_usuario_abrev": "EP", "usr_email": "eva@example.com", "usr_usuario_auth_uuid": None, "usr_es_usuario_master": False, "usr_cuenta_id_default": 1, "usr_evento_id_default": None, "usr_telefono": None, "usr_creado": "2026-01-05", "usr_modificado": None, "usr_estado": "Preregistrado"},
        {"usr_usuario_id": "lonely", "usr_nombre_usuario": "Felipe Sin Cuenta", "usr_nombre_usuario_abrev": "FS", "usr_email": "felipe@example.com", "usr_usuario_auth_uuid": None, "usr_es_usuario_master": False, "usr_cuenta_id_default": None, "usr_evento_id_default": None, "usr_telefono": None, "usr_creado": "2026-01-06", "usr_modificado": None, "usr_estado": "Inactivo"},
    ]
    accounts = [
        {"cta_cuenta_id": 1, "cta_nombre_cuenta": "Cuenta A", "cta_estado": "Activo"},
        {"cta_cuenta_id": 2, "cta_nombre_cuenta": "Cuenta B", "cta_estado": "Activo"},
        {"cta_cuenta_id": 3, "cta_nombre_cuenta": "Cuenta C", "cta_estado": "Inactivo"},
    ]
    relations = [
        {"ucu_cuenta_id": 1, "ucu_usuario_id": "admin-a", "ucu_rol": "Administrador", "ucu_estado": "Activo"},
        {"ucu_cuenta_id": 1, "ucu_usuario_id": "shared", "ucu_rol": "Operador", "ucu_estado": "Inactivo"},
        {"ucu_cuenta_id": 2, "ucu_usuario_id": "shared", "ucu_rol": "Consulta", "ucu_estado": "Activo"},
        {"ucu_cuenta_id": 1, "ucu_usuario_id": "pre", "ucu_rol": "Consulta", "ucu_estado": "Activo"},
        {"ucu_cuenta_id": 2, "ucu_usuario_id": "foreign", "ucu_rol": "Administrador", "ucu_estado": "Activo"},
        {"ucu_cuenta_id": 3, "ucu_usuario_id": "admin-a", "ucu_rol": "Administrador", "ucu_estado": "Activo"},
    ]
    events = [
        {"eve_cuenta_id": 1, "eve_evento_id": 1, "eve_nombre_evento": "Activo A", "eve_estado": "Activo", "eve_fase_evento": "Pre_evento"},
        {"eve_cuenta_id": 1, "eve_evento_id": 2, "eve_nombre_evento": "Inactivo A", "eve_estado": "Inactivo", "eve_fase_evento": "Cerrado"},
        {"eve_cuenta_id": 2, "eve_evento_id": 1, "eve_nombre_evento": "Activo B", "eve_estado": "Activo", "eve_fase_evento": "Pre_evento"},
        {"eve_cuenta_id": 3, "eve_evento_id": 1, "eve_nombre_evento": "Inactivo C", "eve_estado": "Activo", "eve_fase_evento": "Pre_evento"},
    ]
    assignments = [
        {"uev_cuenta_id": 1, "uev_evento_id": 1, "uev_usuario_id": "shared", "uev_estado": "Activo"},
        {"uev_cuenta_id": 2, "uev_evento_id": 1, "uev_usuario_id": "shared", "uev_estado": "Activo"},
        {"uev_cuenta_id": 1, "uev_evento_id": 1, "uev_usuario_id": "pre", "uev_estado": "Activo"},
    ]
    return FakeSupabase({"evp_usr_usuario": users, "evp_cta_cuenta": accounts, "evp_ucu_usuario_cuenta": relations, "evp_eve_evento": events, "evp_uev_usuario_evento": assignments})


MASTER = {"usr_usuario_id": "master", "usr_es_usuario_master": True, "rol_global_calculado": "Master"}
ADMIN = {"usr_usuario_id": "admin-a", "usr_es_usuario_master": False, "rol_global_calculado": "Administrador"}
OPERATOR = {"usr_usuario_id": "shared", "usr_es_usuario_master": False, "rol_global_calculado": "Operador"}
CONSULTA = {"usr_usuario_id": "pre", "usr_es_usuario_master": False, "rol_global_calculado": "Consulta"}


def main() -> None:
    checks = 0

    def check(condition: bool, label: str) -> None:
        nonlocal checks
        assert condition, label
        checks += 1

    db = fixture()
    master = listar_usuarios(db, MASTER, tamano_pagina=20)
    check(master.total == 6, "Master ve todos")
    check(any(item.usuario_id == "lonely" for item in master.items), "Master ve sin cuenta")
    check(any(item.estado == "Preregistrado" for item in master.items), "Master ve preregistrados")
    detail_master = obtener_detalle_usuario(db, MASTER, "master")
    check({item.estado_cuenta for item in detail_master.detalle.cuentas} >= {"Activo", "Inactivo"}, "Master ve cuentas inactivas")
    check(any(item.estado_evento == "Inactivo" for item in detail_master.detalle.eventos), "Master ve eventos inactivos")
    check(all(item.tipo_acceso == "Global" for item in detail_master.detalle.eventos), "Acceso global")
    check(detail_master.ok and detail_master.detalle is not None, "Detalle completo")

    admin = listar_usuarios(db, ADMIN)
    check({item.usuario_id for item in admin.items} == {"admin-a", "shared", "pre"}, "Admin ve su cuenta")
    check("foreign" not in {item.usuario_id for item in admin.items}, "Admin no ve ajenos")
    check(sum(item.usuario_id == "shared" for item in admin.items) == 1, "Compartido sin duplicar")
    shared = obtener_detalle_usuario(db, ADMIN, "shared")
    check({item.cuenta_id for item in shared.detalle.cuentas} == {1}, "Solo relaciones visibles")
    check({item.cuenta_id for item in shared.detalle.eventos} == {1}, "Solo eventos visibles")
    check({item.rol for item in shared.detalle.cuentas} == {"Operador"}, "No roles ajenos")
    check(obtener_detalle_usuario(db, ADMIN, "foreign").estado == "denied", "Detalle ajeno rechazado")
    admin_detail = obtener_detalle_usuario(db, ADMIN, "admin-a")
    check(all(item.tipo_acceso == "Heredado" for item in admin_detail.detalle.eventos), "Admin heredado")
    check(any(item.cantidad_eventos_asignados for item in admin.items), "Ve asignaciones")

    check(not puede_ver_administracion_usuarios(OPERATOR), "Operador sin menú")
    check(listar_usuarios(db, OPERATOR).estado == "denied", "Operador ruta rechazada")
    check(not puede_ver_administracion_usuarios(CONSULTA), "Consulta sin menú")
    check(listar_usuarios(db, CONSULTA).estado == "denied", "Consulta ruta rechazada")
    admin_en_evento_operador = {**ADMIN, "evento_actual": {"rol": "Operador"}}
    check(puede_ver_administracion_usuarios(admin_en_evento_operador), "Admin conserva módulo aunque el evento actual tenga otro rol")

    check(not shared.detalle.cuentas[0].acceso_efectivo, "Relación inactiva sin acceso")
    check(any("asignación activa" in warning for warning in shared.detalle.advertencias), "Inconsistencia visible")
    check(any("predeterminado" in warning for warning in shared.detalle.advertencias), "Default inválido")
    check(any(item.tiene_advertencia_auth for item in admin.items), "Advertencia Auth")
    lonely = obtener_detalle_usuario(db, MASTER, "lonely")
    check(lonely.ok and any("no tiene cuentas" in warning.lower() for warning in lonely.detalle.advertencias), "Sin cuentas controlado")

    check([item.usuario_id for item in listar_usuarios(db, MASTER, busqueda="Carla").items] == ["shared"], "Busca nombre")
    check([item.usuario_id for item in listar_usuarios(db, MASTER, busqueda="dora@").items] == ["foreign"], "Busca correo")
    check(all(item.estado == "Preregistrado" for item in listar_usuarios(db, MASTER, estado="Preregistrado").items), "Filtro estado")
    check(all(item.es_master for item in listar_usuarios(db, MASTER, tipo="Master").items), "Filtro Master")
    check({item.usuario_id for item in listar_usuarios(db, MASTER, rol="Consulta").items} == {"shared", "pre"}, "Filtro rol")
    page1 = listar_usuarios(db, MASTER, tamano_pagina=2, pagina=1)
    page2 = listar_usuarios(db, MASTER, tamano_pagina=2, pagina=2)
    check(not ({item.usuario_id for item in page1.items} & {item.usuario_id for item in page2.items}), "Paginación sin duplicar")
    check(page1.total == 6 and page1.total_paginas == 3, "Totales")
    check(listar_usuarios(db, MASTER, pagina=20, tamano_pagina=2).estado == "empty", "Página vacía")

    check(obtener_detalle_usuario(db, ADMIN, "manipulado").estado in {"denied", "not_found"}, "UUID manipulado")
    check(listar_usuarios(db, ADMIN, cuenta_id=2).estado == "denied", "Cuenta manipulada")
    check(all(op == "SELECT" for op, _ in db.operations), "Solo SELECT")
    check(not any(op == "INSERT" for op, _ in db.operations), "Sin INSERT")
    check(not any(op == "UPDATE" for op, _ in db.operations), "Sin UPDATE")
    check(not any(op == "DELETE" for op, _ in db.operations), "Sin DELETE")
    check("service_role" not in (ROOT / "services" / "usuario_admin_service.py").read_text(encoding="utf-8"), "Sin service_role")

    check(parse_app_route(route_for("users_admin"))[0] == "users_admin", "Ruta listado")
    check(parse_app_route(route_for("users_admin", "shared"))[:2] == ("users_admin", "shared"), "Ruta detalle")
    desktop = user_admin_view(master, {}, is_mobile=False, loading=False, on_apply_filters=lambda x: None, on_refresh=lambda: None, on_page=lambda x: None, on_detail=lambda x: None)
    check(desktop is not None, "Tabla escritorio")
    mobile = user_admin_view(master, {}, is_mobile=True, loading=False, on_apply_filters=lambda x: None, on_refresh=lambda: None, on_page=lambda x: None, on_detail=lambda x: None)
    check(mobile is not None, "Tarjetas móvil")
    detail_view = user_admin_detail_view(shared.detalle, estado="ready", mensaje="", loading=False, on_back=lambda: None, on_retry=lambda: None)
    check(detail_view is not None, "Vista detalle")
    empty_view = user_admin_view(listar_usuarios(db, MASTER, busqueda="nadie"), {}, is_mobile=False, loading=False, on_apply_filters=lambda x: None, on_refresh=lambda: None, on_page=lambda x: None, on_detail=lambda x: None)
    check(empty_view is not None, "Sin resultados UI")
    error_view = user_admin_detail_view(None, estado="error", mensaje="Error", loading=False, on_back=lambda: None, on_retry=lambda: None)
    check(error_view is not None, "Error controlado UI")
    check(callable(getattr(desktop, "controls", None).__iter__), "Actualizar integrado")
    assert checks >= 45, f"Se esperaban al menos 45 pruebas, se ejecutaron {checks}"
    print(f"OK: {checks} comprobaciones de administración de usuarios en solo lectura.")


if __name__ == "__main__":
    main()
