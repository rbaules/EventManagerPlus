from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.authorization_service import puede_ver_administracion_usuarios
from services.navigation_service import parse_app_route, route_for
from services.usuario_admin_service import listar_usuarios, obtener_detalle_usuario, obtener_eventos_creacion
from views.user_admin_view import _default_text, user_admin_detail_view, user_admin_view


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
        {"usr_usuario_id": "pre", "usr_nombre_usuario": "Eva Pendiente", "usr_nombre_usuario_abrev": "EP", "usr_email": "eva@example.com", "usr_usuario_auth_uuid": None, "usr_es_usuario_master": False, "usr_cuenta_id_default": 1, "usr_evento_id_default": None, "usr_telefono": None, "usr_creado": "2026-01-05", "usr_modificado": None, "usr_estado": "Preregistrado", "usr_creado_por": "admin-a"},
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

    def control_texts(control: Any) -> set[str]:
        found: set[str] = set()
        pending = [control]
        seen: set[int] = set()
        while pending:
            item = pending.pop()
            if item is None or id(item) in seen:
                continue
            seen.add(id(item))
            for attribute in ("content", "title", "subtitle"):
                value = getattr(item, attribute, None)
                if isinstance(value, str):
                    found.add(value)
                elif value is not None:
                    pending.append(value)
            controls = getattr(item, "controls", None)
            if controls:
                pending.extend(controls)
        return found

    db = fixture()
    check(obtener_eventos_creacion(db, MASTER, 1) == {1: "Activo A"}, "Eventos default filtrados por cuenta y estado")
    check(obtener_eventos_creacion(db, ADMIN, 2) == {}, "Admin no consulta eventos de cuenta ajena")
    master = listar_usuarios(db, MASTER, tamano_pagina=20)
    check(master.total == 6, "Master ve todos")
    check(any(item.usuario_id == "lonely" for item in master.items), "Master ve sin cuenta")
    check(any(item.estado == "Preregistrado" for item in master.items), "Master ve preregistrados")
    master_summary = next(item for item in master.items if item.usuario_id == "master")
    check(master_summary.cantidad_cuentas_accesibles == 2, "Master cuenta solo cuentas activas sin UCU")
    check(master_summary.cantidad_eventos_accesibles == 2, "Master cuenta eventos activos de cuentas activas sin UEV")
    check(master_summary.roles_visibles == ("Master",), "Master domina roles historicos del grid")
    prereg_summary = next(item for item in master.items if item.usuario_id == "pre")
    check(prereg_summary.cantidad_cuentas_accesibles == 1, "Preregistrado muestra cuenta configurada")
    check(prereg_summary.cantidad_eventos_accesibles == 1, "Preregistrado muestra evento configurado")
    check(next(item for item in master.items if item.usuario_id == "lonely").cantidad_eventos_accesibles == 0, "Inactivo sin acceso efectivo")
    prereg_master_db = fixture()
    next(row for row in prereg_master_db.tables["evp_usr_usuario"] if row["usr_usuario_id"] == "pre")["usr_es_usuario_master"] = True
    prereg_master = next(item for item in listar_usuarios(prereg_master_db, MASTER).items if item.usuario_id == "pre")
    check(prereg_master.cantidad_cuentas_accesibles == 2, "Master Preregistrado muestra todas las cuentas activas")
    check(prereg_master.cantidad_eventos_accesibles == 2, "Master Preregistrado muestra todos los eventos permitidos")
    suspended_db = fixture()
    next(row for row in suspended_db.tables["evp_usr_usuario"] if row["usr_usuario_id"] == "pre")["usr_estado"] = "Suspendido"
    suspended = next(item for item in listar_usuarios(suspended_db, MASTER).items if item.usuario_id == "pre")
    check(suspended.cantidad_cuentas_accesibles == 0 and suspended.cantidad_eventos_accesibles == 0, "Suspendido muestra 0/0")
    detail_master = obtener_detalle_usuario(db, MASTER, "master")
    check({item.estado_cuenta for item in detail_master.detalle.cuentas} >= {"Activo", "Inactivo"}, "Master ve cuentas inactivas")
    check(any(item.estado_evento == "Inactivo" for item in detail_master.detalle.eventos), "Master ve eventos inactivos")
    check(all(item.tipo_acceso == "Global" for item in detail_master.detalle.eventos), "Acceso global")
    check(detail_master.ok and detail_master.detalle is not None, "Detalle completo")
    check(detail_master.detalle.cuenta_default_nombre == "Cuenta A", "Nombre directo de cuenta default Master")
    check(detail_master.detalle.evento_default_nombre == "Activo A", "Nombre directo de evento default Master sin UEV")

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
    admin_summary = next(item for item in master.items if item.usuario_id == "admin-a")
    check(admin_summary.cantidad_cuentas_accesibles == 1, "Admin cuenta UCU Administrador activa en cuenta activa")
    check(admin_summary.cantidad_eventos_accesibles == 1, "Admin hereda eventos activos sin UEV")
    check(admin_detail.detalle.evento_default_nombre == "Inactivo A", "Default Admin se resuelve directo aunque no tenga UEV")
    check(any(item.cantidad_eventos_asignados for item in admin.items), "Ve asignaciones")

    shared_summary = next(item for item in master.items if item.usuario_id == "shared")
    check(shared_summary.cantidad_cuentas_accesibles == 1, "Operador/Consulta cuenta solo UCU activa")
    check(shared_summary.cantidad_eventos_accesibles == 1, "Operador/Consulta exige UEV activa y UCU activa")
    check(shared_summary.roles_visibles == ("Consulta",), "UCU Inactiva no aparece como rol vigente")
    multi_role_db = fixture()
    next(row for row in multi_role_db.tables["evp_ucu_usuario_cuenta"] if row["ucu_usuario_id"] == "shared" and row["ucu_cuenta_id"] == 1)["ucu_estado"] = "Activo"
    multi_role = next(item for item in listar_usuarios(multi_role_db, MASTER).items if item.usuario_id == "shared")
    check(multi_role.roles_visibles == ("Consulta", "Operador"), "Roles activos distintos aparecen sin duplicados")

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
    check(_default_text(None, None, "Sin cuenta predeterminada") == "Sin cuenta predeterminada", "NULL cuenta amigable")
    check(_default_text(None, None, "Sin evento predeterminado") == "Sin evento predeterminado", "NULL evento amigable")
    check(_default_text("Cuenta A", 1, "") == "Cuenta A (ID 1)", "Nombre visible conserva ID interno")
    master_actions = user_admin_detail_view(
        shared.detalle, estado="ready", mensaje="", loading=False,
        on_back=lambda: None, on_retry=lambda: None, es_master_actor=True,
        actor_id="master", on_edit=lambda x: None, on_state=lambda x, y: None,
        on_master=lambda x, y: None, puede_editar_datos=True,
    )
    master_texts = control_texts(master_actions)
    check({"Editar datos", "Inactivar usuario", "Convertir en Master"}.issubset(master_texts), "Acciones Master visibles")
    admin_actions = user_admin_detail_view(
        shared.detalle, estado="ready", mensaje="", loading=False,
        on_back=lambda: None, on_retry=lambda: None, es_master_actor=False,
        actor_id="admin-a", on_edit=lambda x: None, on_state=lambda x, y: None,
        on_master=lambda x, y: None,
        puede_editar_datos=False,
    )
    check(not ({"Editar datos", "Inactivar usuario", "Activar usuario", "Convertir en Master", "Retirar condición Master"} & control_texts(admin_actions)), "Acciones ocultas para Admin ajeno")
    admin_owned = user_admin_detail_view(
        prereg_detail.detalle if 'prereg_detail' in locals() else obtener_detalle_usuario(db, ADMIN, "pre").detalle,
        estado="ready", mensaje="", loading=False, on_back=lambda: None, on_retry=lambda: None,
        es_master_actor=False, actor_id="admin-a", on_edit=lambda x: None,
        on_state=lambda x, y: None, on_master=lambda x, y: None, puede_editar_datos=True,
    )
    check("Editar datos" in control_texts(admin_owned), "Admin edita Operador/Consulta administrable sin depender del creador")
    actor_detail = obtener_detalle_usuario(db, MASTER, "master")
    actor_view = user_admin_detail_view(
        actor_detail.detalle, estado="ready", mensaje="", loading=False,
        on_back=lambda: None, on_retry=lambda: None, es_master_actor=True,
        actor_id="master", on_edit=lambda x: None, on_state=lambda x, y: None,
        on_master=lambda x, y: None, puede_editar_datos=True,
    )
    check("Inactivar usuario" not in control_texts(actor_view) and "Retirar condición Master" not in control_texts(actor_view), "Protecciones del propio Master")
    other_master_view = user_admin_detail_view(
        replace(actor_detail.detalle, usuario_id="other-master"), estado="ready", mensaje="", loading=False,
        on_back=lambda: None, on_retry=lambda: None, es_master_actor=True,
        actor_id="master", on_edit=lambda x: None, on_state=lambda x, y: None,
        on_master=lambda x, y: None, puede_editar_datos=True,
    )
    check("Editar datos" in control_texts(other_master_view), "Master puede editar otro Master sin UCU/UEV")
    master_role_view = user_admin_detail_view(
        admin_detail.detalle, estado="ready", mensaje="", loading=False,
        on_back=lambda: None, on_retry=lambda: None, es_master_actor=True, actor_id="master",
        on_edit=lambda x: None, on_state=lambda x, y: None, on_master=lambda x, y: None,
        on_role=lambda x, y: None, puede_cambiar_rol=True,
    )
    check("Cambiar rol" in control_texts(master_role_view), "Master ve cambio de rol sobre UCU vigente")
    admin_role_detail = obtener_detalle_usuario(db, ADMIN, "pre")
    admin_role_view = user_admin_detail_view(
        admin_role_detail.detalle, estado="ready", mensaje="", loading=False,
        on_back=lambda: None, on_retry=lambda: None, es_master_actor=False, actor_id="admin-a",
        on_edit=lambda x: None, on_state=lambda x, y: None, on_master=lambda x, y: None,
        on_role=lambda x, y: None, puede_cambiar_rol=True,
    )
    check("Cambiar rol" in control_texts(admin_role_view), "Admin ve cambio Operador/Consulta en cuenta administrada")
    prereg_detail = obtener_detalle_usuario(db, MASTER, "pre")
    prereg_view = user_admin_detail_view(
        prereg_detail.detalle, estado="ready", mensaje="", loading=False,
        on_back=lambda: None, on_retry=lambda: None, es_master_actor=True,
        actor_id="master", on_edit=lambda x: None, on_state=lambda x, y: None,
        on_master=lambda x, y: None, puede_editar_datos=True,
    )
    check("Activar usuario" not in control_texts(prereg_view), "Preregistrado sin Auth no activa")
    check("Inactivar usuario" in control_texts(prereg_view), "Master puede inactivar Preregistrado")
    check("Convertir en Master" in control_texts(prereg_view), "Preregistrado permite conversion a Master")
    check("Editar datos" in control_texts(prereg_view), "Master edita Preregistrado")
    active_detail = obtener_detalle_usuario(db, MASTER, "foreign")
    inactive_detail = replace(active_detail.detalle, estado="Inactivo")
    inactive_view = user_admin_detail_view(
        inactive_detail, estado="ready", mensaje="", loading=False,
        on_back=lambda: None, on_retry=lambda: None, es_master_actor=True,
        actor_id="master", on_edit=lambda x: None, on_state=lambda x, y: None,
        on_master=lambda x, y: None,
    )
    check("Activar usuario" in control_texts(inactive_view), "Inactivo con Auth permite activar")
    check("Editar datos" not in control_texts(inactive_view), "Master no edita Inactivo")
    check("Convertir en Master" not in control_texts(inactive_view), "Inactivo no ofrece conversion a Master")
    suspended_view = user_admin_detail_view(
        replace(active_detail.detalle, estado="Suspendido"), estado="ready", mensaje="", loading=False,
        on_back=lambda: None, on_retry=lambda: None, es_master_actor=True, actor_id="master",
        on_edit=lambda x: None, on_state=lambda x, y: None, on_master=lambda x, y: None,
    )
    check("Convertir en Master" not in control_texts(suspended_view), "Suspendido no ofrece conversion a Master")
    check("Editar datos" not in control_texts(suspended_view), "Master no edita Suspendido")
    admin_inactive_view = user_admin_detail_view(
        replace(admin_role_detail.detalle, estado="Inactivo"), estado="ready", mensaje="", loading=False,
        on_back=lambda: None, on_retry=lambda: None, es_master_actor=False, actor_id="admin-a",
        on_edit=lambda x: None, on_state=lambda x, y: None, on_master=lambda x, y: None,
        puede_editar_datos=False,
    )
    check("Editar datos" not in control_texts(admin_inactive_view), "Admin no edita Operador/Consulta Inactivo")
    admin_suspended_view = user_admin_detail_view(
        replace(admin_role_detail.detalle, estado="Suspendido"), estado="ready", mensaje="", loading=False,
        on_back=lambda: None, on_retry=lambda: None, es_master_actor=False, actor_id="admin-a",
        on_edit=lambda x: None, on_state=lambda x, y: None, on_master=lambda x, y: None,
        puede_editar_datos=False,
    )
    check("Editar datos" not in control_texts(admin_suspended_view), "Admin no edita Operador/Consulta Suspendido")
    not_found = obtener_detalle_usuario(db, MASTER, "ausente")
    denied = obtener_detalle_usuario(db, ADMIN, "foreign")
    check(not_found.estado == "not_found" and not_found.mensaje == "Usuario no encontrado.", "Detalle no encontrado diferenciado")
    check(denied.estado == "denied" and "No tiene acceso" in denied.mensaje, "Detalle denegado diferenciado")
    empty_view = user_admin_view(listar_usuarios(db, MASTER, busqueda="nadie"), {}, is_mobile=False, loading=False, on_apply_filters=lambda x: None, on_refresh=lambda: None, on_page=lambda x: None, on_detail=lambda x: None)
    check(empty_view is not None, "Sin resultados UI")
    error_view = user_admin_detail_view(None, estado="error", mensaje="Error", loading=False, on_back=lambda: None, on_retry=lambda: None)
    check(error_view is not None, "Error controlado UI")
    check(callable(getattr(desktop, "controls", None).__iter__), "Actualizar integrado")
    assert checks >= 45, f"Se esperaban al menos 45 pruebas, se ejecutaron {checks}"
    print(f"OK: {checks} comprobaciones de administración de usuarios en solo lectura.")


if __name__ == "__main__":
    main()
